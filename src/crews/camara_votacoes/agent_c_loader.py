#!/usr/bin/env python3
"""Agent C — Loader Câmara Votações: Prata → PostgreSQL (prisma_data)

Cria as tabelas (IF NOT EXISTS) e insere em lote, sem duplicar:
  - camara_votacoes         (ON CONFLICT (id) DO UPDATE em campos voláteis)
  - camara_votos_nominais   (ON CONFLICT (votacao_id, deputado_id_camara) DO NOTHING)

Para a tabela de votos nominais, usa COPY FROM STDIN em CSV (rápido em massa)
contra uma TEMP TABLE, depois INSERT ... SELECT ... ON CONFLICT DO NOTHING.
Isso permite re-execução idempotente sem duplicar.

Execução:
    python agent_c_loader.py --dry-run
    python agent_c_loader.py --prata votacoes_57_2024_05_prata.json
    python agent_c_loader.py --todos
"""
import json
import argparse
import os
import io
import csv
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/camara_votacoes/prata"

DB = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 5432)),
    dbname   = os.getenv("DB_NAME", "prisma_data"),
    user     = os.getenv("DB_USER", "postgres"),
    password = DB_PASSWORD,
)

DDL_VOTACOES = """
CREATE TABLE IF NOT EXISTS camara_votacoes (
    id                  TEXT PRIMARY KEY,
    legislatura         INT NOT NULL,
    data                DATE,
    data_hora_registro  TIMESTAMPTZ,
    sigla_orgao         TEXT,
    proposicao_id       BIGINT,
    descricao           TEXT,
    aprovacao           INT,
    sim                 INT,
    nao                 INT,
    outros              INT,
    abstencoes          INT,
    raw_hash            TEXT UNIQUE,
    dt_carga            TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_votacoes_leg_data
    ON camara_votacoes(legislatura, data);
CREATE INDEX IF NOT EXISTS idx_votacoes_proposicao
    ON camara_votacoes(proposicao_id)
    WHERE proposicao_id IS NOT NULL;
"""

DDL_VOTOS = """
CREATE TABLE IF NOT EXISTS camara_votos_nominais (
    votacao_id          TEXT NOT NULL REFERENCES camara_votacoes(id) ON DELETE CASCADE,
    deputado_id_camara  INT NOT NULL,
    politico_id         TEXT,
    nome                TEXT,
    sigla_partido       TEXT,
    sigla_uf            TEXT,
    tipo_voto           TEXT,
    data_hora_voto      TIMESTAMPTZ,
    PRIMARY KEY (votacao_id, deputado_id_camara)
);
CREATE INDEX IF NOT EXISTS idx_votos_nominais_pol
    ON camara_votos_nominais(politico_id) WHERE politico_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_votos_nominais_dep
    ON camara_votos_nominais(deputado_id_camara);
"""

DDL_ETL_LOG = """
CREATE TABLE IF NOT EXISTS etl_log (
    id                SERIAL PRIMARY KEY,
    portal            TEXT,
    fase              TEXT,
    status            TEXT,
    total_registros   INT,
    registros_novos   INT,
    erro_mensagem     TEXT,
    duracao_seg       NUMERIC,
    iniciado_em       TIMESTAMPTZ,
    finalizado_em     TIMESTAMPTZ
);
"""

UPSERT_VOTACAO = """
INSERT INTO camara_votacoes (
    id, legislatura, data, data_hora_registro,
    sigla_orgao, proposicao_id, descricao, aprovacao,
    sim, nao, outros, abstencoes, raw_hash
) VALUES (
    %(id)s, %(legislatura)s, %(data)s, %(data_hora_registro)s,
    %(sigla_orgao)s, %(proposicao_id)s, %(descricao)s, %(aprovacao)s,
    %(sim)s, %(nao)s, %(outros)s, %(abstencoes)s, %(raw_hash)s
)
ON CONFLICT (id) DO UPDATE SET
    aprovacao  = EXCLUDED.aprovacao,
    sim        = EXCLUDED.sim,
    nao        = EXCLUDED.nao,
    outros     = EXCLUDED.outros,
    abstencoes = EXCLUDED.abstencoes,
    descricao  = COALESCE(EXCLUDED.descricao, camara_votacoes.descricao)
"""

ETL_LOG_INS = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

CAMPOS_VOTACAO = [
    "id", "legislatura", "data", "data_hora_registro",
    "sigla_orgao", "proposicao_id", "descricao", "aprovacao",
    "sim", "nao", "outros", "abstencoes", "raw_hash",
]
CAMPOS_VOTO = [
    "votacao_id", "deputado_id_camara", "politico_id",
    "nome", "sigla_partido", "sigla_uf", "tipo_voto", "data_hora_voto",
]


def garantir_schema(conn) -> None:
    cur = conn.cursor()
    cur.execute(DDL_VOTACOES)
    cur.execute(DDL_VOTOS)
    cur.execute(DDL_ETL_LOG)
    conn.commit()
    cur.close()


def _csv_value(v):
    """Converte para representação CSV-segura. None → string vazia (NULL)."""
    if v is None:
        return ""
    return str(v)


def carregar_votos_em_lote(conn, votos: list[dict]) -> int:
    """Carrega votos via COPY em TEMP TABLE e depois INSERT ... ON CONFLICT DO NOTHING.

    Retorna número de registros novos efetivamente inseridos.
    """
    if not votos:
        return 0

    cur = conn.cursor()

    # TEMP TABLE sem chave (vai herdar tipos da definitiva via SELECT)
    cur.execute("""
        CREATE TEMP TABLE _tmp_votos (
            votacao_id          TEXT,
            deputado_id_camara  INT,
            politico_id         TEXT,
            nome                TEXT,
            sigla_partido       TEXT,
            sigla_uf            TEXT,
            tipo_voto           TEXT,
            data_hora_voto      TIMESTAMPTZ
        ) ON COMMIT DROP
    """)

    # Monta CSV em memória
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    for r in votos:
        writer.writerow([_csv_value(r.get(c)) for c in CAMPOS_VOTO])
    buf.seek(0)

    cur.copy_expert(
        sql=("COPY _tmp_votos ("
             + ", ".join(CAMPOS_VOTO)
             + ") FROM STDIN WITH (FORMAT CSV, NULL '')"),
        file=buf,
    )

    # Insere ignorando duplicatas (idempotente)
    cur.execute(f"""
        INSERT INTO camara_votos_nominais (
            {', '.join(CAMPOS_VOTO)}
        )
        SELECT {', '.join(CAMPOS_VOTO)}
        FROM _tmp_votos
        ON CONFLICT (votacao_id, deputado_id_camara) DO NOTHING
    """)
    novos = cur.rowcount
    conn.commit()
    cur.close()
    return novos


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"Prata: {prata_path.name}")
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    votacoes = prata.get("records_votacoes", []) or []
    votos    = prata.get("records_votos_nominais", []) or []
    meta     = prata.get("meta", {})
    print(f"  {len(votacoes):,} votações | {len(votos):,} votos nominais")

    if dry_run:
        print("  DRY-RUN — nenhum dado gravado")
        # Sanity-check
        erros = 0
        for r in votacoes[:50]:
            for c in ("id", "legislatura", "data_hora_registro", "raw_hash"):
                if not r.get(c):
                    print(f"  ! Campo ausente '{c}' em votação {r.get('id','?')}")
                    erros += 1
        for r in votos[:200]:
            for c in ("votacao_id", "deputado_id_camara", "tipo_voto"):
                if r.get(c) in (None, ""):
                    print(f"  ! Campo ausente '{c}' em voto "
                          f"{r.get('votacao_id','?')}/{r.get('deputado_id_camara','?')}")
                    erros += 1
        print(f"  Dry-run OK | Erros validação: {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    garantir_schema(conn)
    cur    = conn.cursor()

    # ── Votações: upsert em lotes
    novos_vot = 0
    erros_vot = 0
    rows = [{k: r.get(k) for k in CAMPOS_VOTACAO} for r in votacoes]
    for i in range(0, len(rows), 1000):
        lote = rows[i:i+1000]
        try:
            cur.executemany(UPSERT_VOTACAO, lote)
            conn.commit()
            novos_vot += len(lote)
        except Exception as e:
            conn.rollback()
            erros_vot += len(lote)
            print(f"  ! Lote votações {i//1000+1} falhou: {e}")

    # ── Votos nominais: COPY em lotes de 50k
    novos_votos = 0
    erros_votos = 0
    for i in range(0, len(votos), 50000):
        lote = votos[i:i+50000]
        try:
            n = carregar_votos_em_lote(conn, lote)
            novos_votos += n
            print(f"  Lote votos {i//50000+1}: {n:,} novos (de {len(lote):,} no lote)")
        except Exception as e:
            conn.rollback()
            erros_votos += len(lote)
            print(f"  ! Lote votos {i//50000+1} falhou: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    leg = meta.get("legislatura", "?")
    ano = meta.get("ano", "?")
    mes = meta.get("mes", "?")
    try:
        cur.execute(ETL_LOG_INS, (
            f"camara_votacoes_{leg}_{ano}_{mes}", "fase_1",
            "sucesso" if (erros_vot + erros_votos) == 0 else "parcial",
            len(votacoes) + len(votos),
            novos_vot + novos_votos,
            None if (erros_vot + erros_votos) == 0
                  else f"{erros_vot} erros votacoes, {erros_votos} erros votos",
            round(dur, 2), inicio, fim,
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"  ! Falha ao registrar etl_log: {e}")

    cur.close()
    conn.close()

    print(f"  Concluído em {dur:.1f}s | Votações: {novos_vot:,} | "
          f"Votos: {novos_votos:,} | Erros: {erros_vot + erros_votos}")


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader Câmara Votações")
    parser.add_argument("--dry-run", action="store_true", help="Valida sem gravar")
    parser.add_argument("--prata",   help="Arquivo prata específico")
    parser.add_argument("--todos",   action="store_true", help="Todos os pratas")
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("votacoes_*_prata.json"))
        if not pratas:
            print("Nenhum Prata encontrado"); return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("votacoes_*_prata.json"),
                        key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("Nenhum Prata encontrado"); return
        carregar_prata(pratas[0], args.dry_run)

    print("\n✅ Agent C concluído.")


if __name__ == "__main__":
    main()
