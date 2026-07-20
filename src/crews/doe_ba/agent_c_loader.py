#!/usr/bin/env python3
"""
DOE-BA — Agent C (Loader)

Prata → PostgreSQL (`doe_publicacoes`, tabela já existente/modelada).
DDL idempotente adiciona colunas de rastreabilidade forense que a tabela
original não tinha (nenhuma delas é destrutiva — só ADD COLUMN IF NOT EXISTS):

  fonte_crew  — qual crew escreveu a linha (tabela pode ganhar outras fontes
                de DOE no futuro, ex. contratos publicados)
  ato_numero/ato_ano/diario_id/pagina/url_fonte — permitem abrir a edição
                original e conferir o ato "documento a documento", mesmo
                princípio de rastreabilidade forense usado em emendas
                (ver PROTOCOLO_EMENDAS_DADOS_SENSIVEIS.md)
  ato_hash    — chave natural (data+número do ato+ano+nome+verbo) pra
                idempotência: re-rodar a crew nunca duplica linha.

NUNCA faz TRUNCATE — a tabela pode acumular linhas de outras fontes no
futuro; inserção é sempre incremental via ON CONFLICT (ato_hash) DO NOTHING.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "doe_ba"
PRATA = DATA_DIR / "prata"

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido")
DB = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
          dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
          password=DB_PASSWORD)

DDL = """
ALTER TABLE doe_publicacoes ADD COLUMN IF NOT EXISTS fonte_crew text DEFAULT 'doe_ba';
ALTER TABLE doe_publicacoes ADD COLUMN IF NOT EXISTS ato_numero text;
ALTER TABLE doe_publicacoes ADD COLUMN IF NOT EXISTS ato_ano smallint;
ALTER TABLE doe_publicacoes ADD COLUMN IF NOT EXISTS diario_id text;
ALTER TABLE doe_publicacoes ADD COLUMN IF NOT EXISTS pagina integer;
ALTER TABLE doe_publicacoes ADD COLUMN IF NOT EXISTS url_fonte text;
ALTER TABLE doe_publicacoes ADD COLUMN IF NOT EXISTS ato_hash text;
CREATE UNIQUE INDEX IF NOT EXISTS idx_doe_ato_hash ON doe_publicacoes (ato_hash);
CREATE INDEX IF NOT EXISTS idx_doe_fonte_crew ON doe_publicacoes (fonte_crew);
CREATE INDEX IF NOT EXISTS idx_doe_nome_referencia ON doe_publicacoes (nome_referencia);
"""


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    log("DDL ok (colunas de rastreabilidade + índice único ato_hash)")

    atos = json.loads((PRATA / "atos.json").read_text(encoding="utf-8"))
    linhas = [(
        a["data_publicacao"], a["tipo_ato"], a["texto_resumido"], a["cpf_cnpj_referencia"],
        a["nome_referencia"], a["secao"], None, a["orgao"], False,
        "doe_ba", a["ato_numero"], a["ato_ano"], a["diario_id"], a["pagina"],
        a["url_fonte"], a["ato_hash"],
    ) for a in atos]
    log(f"{len(linhas):,} atos de pessoal (prata) prontos pra carga")

    if args.dry_run:
        log("dry-run — nada gravado")
        return

    psycopg2.extras.execute_values(cur, """
        INSERT INTO doe_publicacoes (
            data_publicacao, tipo_ato, texto_resumido, cpf_cnpj_referencia,
            nome_referencia, secao, numero_doe, orgao, alerta_nepotismo,
            fonte_crew, ato_numero, ato_ano, diario_id, pagina, url_fonte, ato_hash
        ) VALUES %s
        ON CONFLICT (ato_hash) DO NOTHING
    """, linhas, page_size=1000)
    conn.commit()
    cur.execute("SELECT count(*) FROM doe_publicacoes WHERE fonte_crew = 'doe_ba'")
    total = cur.fetchone()[0]
    log(f"✅ doe_publicacoes: {total:,} linhas da crew doe_ba no banco (após dedupe por ato_hash)")
    conn.close()


if __name__ == "__main__":
    main()
