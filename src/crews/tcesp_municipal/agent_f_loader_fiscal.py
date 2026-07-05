#!/usr/bin/env python3
"""
Agent F — Loader PostgreSQL TCE-SP Fiscal
Prata → tabelas tcesp_receitas / tcesp_despesas

Idempotência por SUBSTITUIÇÃO DE MÊS: para cada (slug, exercicio, mes)
presente no Prata, DELETE + INSERT em uma transação. Re-rodar o mesmo
mês nunca duplica nem soma em cima — substitui. (Hash de linha não
serve aqui: o payload pode ter linhas legitimamente idênticas.)

USO:
    python agent_f_loader_fiscal.py --municipio votorantim --ano 2025 [--dry-run]
"""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/raw/tcesp/prata"

DB_CONFIG = {"host": "localhost", "port": 5432, "dbname": "prisma_data",
             "user": "postgres", "password": DB_PASSWORD}

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS tcesp_receitas (
    id             bigserial PRIMARY KEY,
    slug_tcesp     text NOT NULL REFERENCES tcesp_municipios(slug_tcesp),
    id_ibge        character(7) NOT NULL,
    exercicio      integer NOT NULL,
    mes            smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
    orgao          text,
    fonte_recurso  text,
    aplicacao      text,
    alinea         text,
    subalinea      text,
    vl_arrecadacao numeric(18,2) NOT NULL,
    dt_extracao    timestamptz,
    dt_carga       timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tcesp_receitas_mun_ano
    ON tcesp_receitas (slug_tcesp, exercicio, mes);
CREATE INDEX IF NOT EXISTS idx_tcesp_receitas_ibge
    ON tcesp_receitas (id_ibge, exercicio);

CREATE TABLE IF NOT EXISTS tcesp_despesas (
    id                  bigserial PRIMARY KEY,
    slug_tcesp          text NOT NULL REFERENCES tcesp_municipios(slug_tcesp),
    id_ibge             character(7) NOT NULL,
    exercicio           integer NOT NULL,
    mes                 smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
    orgao               text,
    evento              text,
    nr_empenho          text,
    fornecedor_tipo_doc text,
    fornecedor_doc      text,
    fornecedor_nome     text,
    dt_emissao          date,
    vl_despesa          numeric(18,2) NOT NULL,
    dt_extracao         timestamptz,
    dt_carga            timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tcesp_despesas_mun_ano
    ON tcesp_despesas (slug_tcesp, exercicio, mes);
CREATE INDEX IF NOT EXISTS idx_tcesp_despesas_fornecedor
    ON tcesp_despesas (fornecedor_doc);
CREATE INDEX IF NOT EXISTS idx_tcesp_despesas_ibge
    ON tcesp_despesas (id_ibge, exercicio);
"""

COLS = {
    "receitas": ["slug_tcesp", "id_ibge", "exercicio", "mes", "orgao",
                 "fonte_recurso", "aplicacao", "alinea", "subalinea",
                 "vl_arrecadacao", "dt_extracao"],
    "despesas": ["slug_tcesp", "id_ibge", "exercicio", "mes", "orgao",
                 "evento", "nr_empenho", "fornecedor_tipo_doc", "fornecedor_doc",
                 "fornecedor_nome", "dt_emissao", "vl_despesa", "dt_extracao"],
}

ETL_LOG_SQL = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     registros_atualizados, erro_mensagem, duracao_seg,
                     iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
"""


def carregar_tipo(conn, tipo: str, slug: str, ano: int, dry_run: bool):
    tabela = f"tcesp_{tipo}"
    prata_path = PRATA_DIR / f"{tipo}_{slug}_{ano}_prata.json"
    if not prata_path.exists():
        print(f"⚠️  Prata não encontrado: {prata_path.name} (pulando {tipo})")
        return 0

    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)
    records = prata["records"]
    meses = sorted({r["mes"] for r in records})
    print(f"📂 {prata_path.name}: {len(records)} registros, meses {meses}")

    if dry_run:
        print(f"🔍 DRY-RUN {tipo} — nada gravado")
        return len(records)

    cols = COLS[tipo]
    cur = conn.cursor()
    total = 0
    for mes in meses:
        do_mes = [r for r in records if r["mes"] == mes]
        cur.execute(
            f"DELETE FROM {tabela} WHERE slug_tcesp=%s AND exercicio=%s AND mes=%s",
            (slug, ano, mes))
        apagados = cur.rowcount
        execute_values(
            cur,
            f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES %s",
            [tuple(r.get(c) for c in cols) for r in do_mes],
            page_size=1000)
        conn.commit()
        total += len(do_mes)
        print(f"  ✅ {tipo} {ano}/{mes:02d}: {len(do_mes)} inseridos"
              + (f" (substituiu {apagados})" if apagados else ""))
    cur.close()
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--municipio", required=True)
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--tipo", choices=["receitas", "despesas", "ambos"], default="ambos")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tipos = ["receitas", "despesas"] if args.tipo == "ambos" else [args.tipo]
    inicio = datetime.now(timezone.utc)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(CREATE_SQL)
    conn.commit()
    cur.close()

    total = 0
    erro_msg = None
    try:
        for tipo in tipos:
            total += carregar_tipo(conn, tipo, args.municipio, args.ano, args.dry_run)
        status = "sucesso"
    except Exception as e:
        conn.rollback()
        status, erro_msg = "erro", str(e)[:500]
        print(f"❌ {e}")

    fim = datetime.now(timezone.utc)
    if not args.dry_run:
        cur = conn.cursor()
        cur.execute(ETL_LOG_SQL, (
            "tcesp_municipal", f"fase_2_fiscal_{args.municipio}_{args.ano}", status,
            total, total, 0, erro_msg, round((fim - inicio).total_seconds(), 2),
            inicio, fim))
        conn.commit()
        cur.close()
    conn.close()

    if status == "sucesso":
        print(f"\n✅ Carga concluída: {total} registros em {(fim - inicio).total_seconds():.1f}s")
    else:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
