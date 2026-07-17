#!/usr/bin/env python3
"""Crew TSE Votos por Seção → tse_votos_cache

Baixa o ZIP oficial "votação por seção eleitoral" do CDN do TSE, agrega por
(município, zona, local, candidato, turno) e faz upsert idempotente na tabela
`tse_votos_cache` do Postgres local `prisma_data` — a MESMA tabela e o MESMO
formato que o backend Forbes (`backend/src/api/core/tse_locais.py`) usa nos
mapas eleitorais. Também atualiza `tse_votos_cache_status`.

Diferenças em relação ao endpoint do Forbes (POST /api/tse/carregar-votos):
  * ZIP vai para DISCO (data/tse_votos_municipio/raw/), não para a RAM —
    seguro para os ZIPs de eleição geral (SP 2022 = 769 MB).
  * Raw preservado: rodar de novo pula o download se o ZIP já existe.
  * Roda standalone, sem backend de pé.

Idempotente — ON CONFLICT (sg_uf, cd_municipio, nr_zona, nr_local,
nm_votavel, nr_turno, ano_eleicao) DO UPDATE.

Execução (DB_PASSWORD precisa estar no ambiente ou num .env):
    python main.py --ano 2022 --uf SP                # uma UF
    python main.py --ano 2022 --uf SP BA MG          # várias
    python main.py --ano 2022 --uf 7ufs              # BA MG PE PR RJ RS SP
    python main.py --ano 2018 --uf SP --force        # re-baixa o ZIP
"""
import argparse
import csv
import io
import os
import sys
import time
import zipfile
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina no ambiente ou no .env")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR = BASE_DIR / "data/tse_votos_municipio/raw"

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "prisma_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)

URL_VOTOS = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_{ano}_{uf}.zip"

# Catálogo de eleições no CDN do TSE (mesmo do Forbes tse_locais.py)
ELEICOES = {
    2024: "Municipal", 2022: "Geral", 2020: "Municipal", 2018: "Geral",
    2016: "Municipal", 2014: "Geral", 2012: "Municipal", 2010: "Geral",
}

SETE_UFS = ["BA", "MG", "PE", "PR", "RJ", "RS", "SP"]

DDL = """
CREATE TABLE IF NOT EXISTS tse_votos_cache (
    id            SERIAL PRIMARY KEY,
    sg_uf         CHAR(2)       NOT NULL,
    cd_municipio  INTEGER       NOT NULL,
    nm_municipio  VARCHAR(200),
    nr_zona       INTEGER       NOT NULL,
    nr_local      INTEGER       NOT NULL,
    nm_votavel    VARCHAR(300)  NOT NULL,
    sq_candidato  VARCHAR(20),
    cd_cargo      SMALLINT,
    ds_cargo      VARCHAR(100),
    qt_votos      INTEGER       NOT NULL DEFAULT 0,
    nr_turno      SMALLINT      DEFAULT 1,
    ano_eleicao   SMALLINT      NOT NULL,
    UNIQUE (sg_uf, cd_municipio, nr_zona, nr_local, nm_votavel, nr_turno, ano_eleicao)
);
CREATE INDEX IF NOT EXISTS idx_votos_cache_lookup
    ON tse_votos_cache (sg_uf, cd_municipio, nm_votavel, ano_eleicao);
CREATE INDEX IF NOT EXISTS idx_votos_cache_uf_ano
    ON tse_votos_cache (sg_uf, ano_eleicao);
CREATE INDEX IF NOT EXISTS idx_votos_cache_cargo
    ON tse_votos_cache (sg_uf, ano_eleicao, ds_cargo);
CREATE TABLE IF NOT EXISTS tse_votos_cache_status (
    sg_uf        CHAR(2)      NOT NULL,
    ano_eleicao  SMALLINT     NOT NULL,
    status       VARCHAR(20)  DEFAULT 'pendente',
    total_linhas INTEGER,
    erro         TEXT,
    iniciado_em  TIMESTAMP,
    concluido_em TIMESTAMP,
    PRIMARY KEY (sg_uf, ano_eleicao)
);
"""

UPSERT = """
    INSERT INTO tse_votos_cache
        (sg_uf, cd_municipio, nm_municipio, nr_zona, nr_local,
         nm_votavel, sq_candidato, cd_cargo, ds_cargo, qt_votos, nr_turno, ano_eleicao)
    VALUES
        (%(sg_uf)s, %(cd_municipio)s, %(nm_municipio)s, %(nr_zona)s, %(nr_local)s,
         %(nm_votavel)s, %(sq_candidato)s, %(cd_cargo)s, %(ds_cargo)s,
         %(qt_votos)s, %(nr_turno)s, %(ano_eleicao)s)
    ON CONFLICT (sg_uf, cd_municipio, nr_zona, nr_local, nm_votavel, nr_turno, ano_eleicao)
    DO UPDATE SET qt_votos = EXCLUDED.qt_votos, ds_cargo = EXCLUDED.ds_cargo
"""


def log(msg: str):
    print(f"[tse_votos] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def garantir_ddl(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def set_status(conn, uf: str, ano: int, status: str, total: int | None = None, erro: str | None = None):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tse_votos_cache_status (sg_uf, ano_eleicao, status, total_linhas, erro, iniciado_em, concluido_em)
            VALUES (%s, %s, %s, %s, %s,
                    CASE WHEN %s = 'carregando' THEN NOW() ELSE NULL END,
                    CASE WHEN %s IN ('pronto', 'erro') THEN NOW() ELSE NULL END)
            ON CONFLICT (sg_uf, ano_eleicao) DO UPDATE SET
                status = EXCLUDED.status,
                total_linhas = COALESCE(EXCLUDED.total_linhas, tse_votos_cache_status.total_linhas),
                erro = EXCLUDED.erro,
                iniciado_em = COALESCE(tse_votos_cache_status.iniciado_em, NOW()),
                concluido_em = CASE WHEN EXCLUDED.status IN ('pronto', 'erro') THEN NOW()
                                    ELSE tse_votos_cache_status.concluido_em END
            """,
            [uf, ano, status, total, erro, status, status],
        )
    conn.commit()


def baixar_zip(uf: str, ano: int, force: bool) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / f"votacao_secao_{ano}_{uf}.zip"
    if destino.exists() and not force:
        log(f"{uf}/{ano}: ZIP já existe ({destino.stat().st_size / 1_048_576:.0f} MB) — pulando download")
        return destino

    url = URL_VOTOS.format(ano=ano, uf=uf)
    log(f"{uf}/{ano}: baixando {url}")
    tmp = destino.with_suffix(".zip.part")
    with requests.get(url, stream=True, timeout=900) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(1_048_576):
                fh.write(chunk)
    tmp.rename(destino)
    log(f"{uf}/{ano}: ZIP salvo ({destino.stat().st_size / 1_048_576:.0f} MB)")
    return destino


def agregar_csv(zip_path: Path, uf: str, ano: int) -> list[dict]:
    """Lê o CSV de dentro do ZIP (streaming do disco) e agrega votos por local."""
    agg: dict[tuple, dict] = {}
    total = 0
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(csv_name) as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="latin-1", errors="replace"),
                delimiter=";", quotechar='"',
            )
            for row in reader:
                total += 1
                try:
                    key = (
                        int(row["CD_MUNICIPIO"]),
                        int(row["NR_ZONA"]),
                        int(row["NR_LOCAL_VOTACAO"]),
                        row["NM_VOTAVEL"].strip(),
                        int(row["NR_TURNO"]),
                    )
                except (ValueError, KeyError):
                    continue
                if key not in agg:
                    try:
                        cd_cargo = int(row.get("CD_CARGO", 0) or 0)
                    except ValueError:
                        cd_cargo = None
                    agg[key] = {
                        "sg_uf": uf,
                        "cd_municipio": key[0],
                        "nm_municipio": row.get("NM_MUNICIPIO", "").strip().title(),
                        "nr_zona": key[1],
                        "nr_local": key[2],
                        "nm_votavel": key[3],
                        "sq_candidato": row.get("SQ_CANDIDATO", "").strip() or None,
                        "cd_cargo": cd_cargo,
                        "ds_cargo": row.get("DS_CARGO", "").strip() or None,
                        "qt_votos": 0,
                        "nr_turno": key[4],
                        "ano_eleicao": ano,
                    }
                agg[key]["qt_votos"] += int(row.get("QT_VOTOS", 0) or 0)
                if total % 2_000_000 == 0:
                    log(f"{uf}/{ano}: {total:,} linhas lidas, {len(agg):,} agregadas...")
    log(f"{uf}/{ano}: {total:,} linhas → {len(agg):,} registros agregados")
    return list(agg.values())


def upsert_registros(conn, registros: list[dict], uf: str, ano: int):
    with conn.cursor() as cur:
        BATCH = 1000
        for i in range(0, len(registros), BATCH):
            psycopg2.extras.execute_batch(cur, UPSERT, registros[i:i + BATCH], page_size=BATCH)
            conn.commit()
            if i and i % 100_000 == 0:
                log(f"{uf}/{ano}: {i:,}/{len(registros):,} upserted...")
    conn.commit()


def carregar_uf(uf: str, ano: int, force: bool) -> bool:
    conn = psycopg2.connect(**DB)
    try:
        garantir_ddl(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM tse_votos_cache WHERE sg_uf = %s AND ano_eleicao = %s",
                [uf, ano],
            )
            existentes = cur.fetchone()[0]
        if existentes and not force:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM tse_votos_cache_status WHERE sg_uf = %s AND ano_eleicao = %s",
                    [uf, ano],
                )
                row = cur.fetchone()
            if row and row[0] == "pronto":
                log(f"{uf}/{ano}: já pronto com {existentes:,} registros — pulando (use --force pra recarregar)")
                return True
            log(f"{uf}/{ano}: {existentes:,} registros parciais no banco — retomando (upsert idempotente)")

        set_status(conn, uf, ano, "carregando")
        zip_path = baixar_zip(uf, ano, force)
        registros = agregar_csv(zip_path, uf, ano)
        upsert_registros(conn, registros, uf, ano)
        set_status(conn, uf, ano, "pronto", total=len(registros))
        log(f"{uf}/{ano}: ✅ pronto — {len(registros):,} registros em tse_votos_cache")
        return True
    except Exception as exc:
        log(f"{uf}/{ano}: ❌ ERRO {exc}")
        try:
            conn.rollback()
            set_status(conn, uf, ano, "erro", erro=str(exc)[:500])
        except Exception:
            pass
        return False
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Carrega votos TSE por seção em tse_votos_cache")
    parser.add_argument("--ano", type=int, required=True, choices=sorted(ELEICOES.keys()))
    parser.add_argument("--uf", nargs="+", required=True,
                        help="UFs (ex: SP BA) ou '7ufs' para BA MG PE PR RJ RS SP")
    parser.add_argument("--force", action="store_true", help="re-baixa ZIP e recarrega mesmo se pronto")
    args = parser.parse_args()

    ufs = SETE_UFS if [u.lower() for u in args.uf] == ["7ufs"] else [u.upper() for u in args.uf]
    log(f"Eleição {args.ano} ({ELEICOES[args.ano]}) — UFs: {', '.join(ufs)}")

    falhas = []
    for uf in ufs:
        if not carregar_uf(uf, args.ano, args.force):
            falhas.append(uf)

    if falhas:
        log(f"Concluído com FALHAS: {', '.join(falhas)}")
        sys.exit(1)
    log("Concluído sem falhas.")


if __name__ == "__main__":
    main()
