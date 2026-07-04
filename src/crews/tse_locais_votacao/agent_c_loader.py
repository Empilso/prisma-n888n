#!/usr/bin/env python3
"""Agent C — Loader TSE Locais de Votação → PostgreSQL

Prata:  data/tse_locais/bronze/locais_*.json
Tabela: locais_votacao_tse

Idempotente — ON CONFLICT (sg_uf, cd_municipio, nr_local) DO UPDATE.

Execução:
    python agent_c_loader.py                    # carrega BR inteiro
    python agent_c_loader.py --uf SP            # carrega só SP
    python agent_c_loader.py --dry-run
"""
import json, argparse, os, time
import psycopg2, psycopg2.extras
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/tse_locais/bronze"

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "prisma_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)

DDL = """
CREATE TABLE IF NOT EXISTS locais_votacao_tse (
    id            SERIAL PRIMARY KEY,
    sg_uf         CHAR(2)       NOT NULL,
    cd_municipio  INTEGER       NOT NULL,
    nm_municipio  VARCHAR(200)  NOT NULL,
    nr_local      INTEGER       NOT NULL,
    nm_local      VARCHAR(300)  NOT NULL,
    ds_endereco   VARCHAR(400),
    nm_bairro     VARCHAR(200),
    nr_cep        CHAR(8),
    latitude      NUMERIC(12,7),
    longitude     NUMERIC(12,7),
    qt_eleitores  INTEGER       DEFAULT 0,
    ds_situacao   VARCHAR(50)   DEFAULT 'ATIVO',
    atualizado_em TIMESTAMP     DEFAULT NOW(),
    UNIQUE (sg_uf, cd_municipio, nr_local)
);
CREATE INDEX IF NOT EXISTS idx_locais_uf_mun
    ON locais_votacao_tse (sg_uf, nm_municipio);
CREATE INDEX IF NOT EXISTS idx_locais_uf_cd
    ON locais_votacao_tse (sg_uf, cd_municipio);
CREATE INDEX IF NOT EXISTS idx_locais_coords
    ON locais_votacao_tse (sg_uf, cd_municipio)
    WHERE latitude IS NOT NULL;
"""

UPSERT = """
INSERT INTO locais_votacao_tse
    (sg_uf, cd_municipio, nm_municipio, nr_local, nm_local,
     ds_endereco, nm_bairro, nr_cep, latitude, longitude,
     qt_eleitores, ds_situacao)
VALUES
    (%(sg_uf)s, %(cd_municipio)s, %(nm_municipio)s, %(nr_local)s, %(nm_local)s,
     %(ds_endereco)s, %(nm_bairro)s, %(nr_cep)s, %(latitude)s, %(longitude)s,
     %(qt_eleitores)s, %(ds_situacao)s)
ON CONFLICT (sg_uf, cd_municipio, nr_local) DO UPDATE SET
    nm_local      = EXCLUDED.nm_local,
    ds_endereco   = COALESCE(EXCLUDED.ds_endereco, locais_votacao_tse.ds_endereco),
    latitude      = COALESCE(EXCLUDED.latitude,    locais_votacao_tse.latitude),
    longitude     = COALESCE(EXCLUDED.longitude,   locais_votacao_tse.longitude),
    qt_eleitores  = EXCLUDED.qt_eleitores,
    atualizado_em = NOW()
"""

BATCH = 500


def carregar(uf_filter: str | None, dry_run: bool) -> None:
    sufixo = f"_{uf_filter}" if uf_filter else "_BR"
    bronze_path = BRONZE_DIR / f"locais{sufixo}_bronze.json"

    if not bronze_path.exists():
        raise FileNotFoundError(
            f"Bronze não encontrado: {bronze_path}\nExecute agent_b_normalizador.py primeiro."
        )

    with open(bronze_path, encoding="utf-8") as f:
        registros = json.load(f)

    print(f"📂 Bronze: {len(registros):,} locais")

    if dry_run:
        print("🔍 DRY-RUN — nenhuma gravação.")
        for r in registros[:3]:
            print(" ", r)
        return

    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    cur = conn.cursor()

    # Garante DDL
    cur.execute(DDL)
    conn.commit()

    t0 = time.time()
    inseridos = 0

    for i in range(0, len(registros), BATCH):
        batch = registros[i:i + BATCH]
        psycopg2.extras.execute_batch(cur, UPSERT, batch, page_size=BATCH)
        inseridos += len(batch)
        conn.commit()
        pct = 100 * inseridos / len(registros)
        print(f"\r  ⬆️  {inseridos:,}/{len(registros):,} ({pct:.0f}%)", end="", flush=True)

    print()

    # ETL log
    cur.execute("""
        INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                             duracao_seg, iniciado_em, finalizado_em)
        VALUES (%s, %s, %s, %s, %s, %s, NOW() - interval '%s seconds', NOW())
    """, (
        "tse_locais_votacao", "loader", "sucesso",
        len(registros), inseridos, time.time() - t0, int(time.time() - t0),
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ {inseridos:,} locais carregados em {time.time()-t0:.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf",      default=None,  help="Filtrar UF (ex: SP)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=" * 60)
    print("TSE LOCAIS DE VOTAÇÃO — Agent C: Loader")
    print("=" * 60)
    carregar(args.uf, args.dry_run)


if __name__ == "__main__":
    main()
