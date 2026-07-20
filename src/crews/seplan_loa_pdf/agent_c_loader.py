#!/usr/bin/env python3
"""
SEPLAN LOA — Agent C (Loader)

Prata → PostgreSQL (`loa_emendas_pdf`, tabela já modelada — nunca criada por
nenhuma crew antes desta). `status_cruzamento` grava sempre 'PENDENTE': não
existe cruzamento automático seguro com `emendas_estaduais` hoje (achado do
recon 2026-07-20 — o `numero_emenda` de lá é na verdade nº de PAGAMENTO do
CKAN, sistema de numeração diferente do nº de emenda da LOA). 'PENDENTE'
documenta honestamente que a reconciliação ainda não foi tentada, não que
falhou.

Idempotente via `numero_emenda` (PK já existe na tabela, formato
"LOA{ano}-{nº}" pra nunca colidir entre anos). ON CONFLICT atualiza os campos
(permite reprocessar um PDF sem duplicar).
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "seplan_loa_pdf"
PRATA = DATA_DIR / "prata"

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido")
DB = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
          dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
          password=DB_PASSWORD)


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    registros = json.loads((PRATA / "loa.json").read_text(encoding="utf-8"))
    linhas = [(
        r["numero_emenda"], r["politico_id"], r["municipio_ibge"],
        r["valor_aprovado"], r["ano_loa"], "PENDENTE",
    ) for r in registros if r["valor_aprovado"] is not None]
    descartadas = len(registros) - len(linhas)
    log(f"{len(linhas):,} linhas prontas pra carga ({descartadas} descartadas por falta de valor — nunca estimamos)")

    if args.dry_run:
        log("dry-run — nada gravado")
        return

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    psycopg2.extras.execute_values(cur, """
        INSERT INTO loa_emendas_pdf (numero_emenda, politico_id, municipio_ibge, valor_aprovado, ano_loa, status_cruzamento)
        VALUES %s
        ON CONFLICT (numero_emenda) DO UPDATE SET
            politico_id = EXCLUDED.politico_id,
            municipio_ibge = EXCLUDED.municipio_ibge,
            valor_aprovado = EXCLUDED.valor_aprovado,
            ano_loa = EXCLUDED.ano_loa
    """, linhas, page_size=1000)
    conn.commit()
    cur.execute("SELECT count(*), count(politico_id), count(municipio_ibge) FROM loa_emendas_pdf")
    total, com_politico, com_municipio = cur.fetchone()
    log(f"✅ loa_emendas_pdf: {total:,} linhas ({com_politico:,} com politico_id, {com_municipio:,} com municipio_ibge)")
    conn.close()


if __name__ == "__main__":
    main()
