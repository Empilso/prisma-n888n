#!/usr/bin/env python3
"""Agent C — Loader Sorocaba Verba de Gabinete: Prata → tabela sorocaba_verba_gabinete"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PRATA_PATH = BASE_DIR / "data/sorocaba_verba_gabinete/prata/sorocaba_verba_prata.json"

DB = dict(host="localhost", port=5432, dbname="prisma_data", user="postgres", password=DB_PASSWORD)

DDL = """
CREATE TABLE IF NOT EXISTS sorocaba_verba_gabinete (
    id                text PRIMARY KEY,
    politico_id       text,
    vereador_nome     text NOT NULL,
    categoria         text NOT NULL,
    valor             numeric NOT NULL,
    mes               integer NOT NULL,
    ano               integer NOT NULL,
    competencia       text NOT NULL,
    status_lneg       status_lneg_enum,
    fonte_arquivo     text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sorocaba_verba_competencia ON sorocaba_verba_gabinete (competencia);
CREATE INDEX IF NOT EXISTS idx_sorocaba_verba_politico ON sorocaba_verba_gabinete (politico_id);
CREATE INDEX IF NOT EXISTS idx_sorocaba_verba_categoria ON sorocaba_verba_gabinete (categoria);
"""

UPSERT_SQL = """
INSERT INTO sorocaba_verba_gabinete (
    id, politico_id, vereador_nome, categoria,
    valor, mes, ano, competencia, status_lneg, fonte_arquivo
) VALUES (
    %(id)s, %(politico_id)s, %(vereador_nome)s, %(categoria)s,
    %(valor)s, %(mes)s, %(ano)s, %(competencia)s, %(status_lneg)s, %(fonte_arquivo)s
)
ON CONFLICT (id) DO NOTHING
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

CAMPOS = [
    "id", "politico_id", "vereador_nome", "categoria",
    "valor", "mes", "ano", "competencia", "status_lneg", "fonte_arquivo",
]


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader Sorocaba Verba de Gabinete")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prata", default=str(PRATA_PATH))
    args = parser.parse_args()

    prata_path = Path(args.prata)
    if not prata_path.exists():
        print(f"❌ Prata não encontrado: {prata_path}")
        return

    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    records = prata.get("records", [])
    print(f"📊 {len(records):,} registros")

    if args.dry_run:
        erros = sum(1 for r in records[:200] if not r.get("id") or not r.get("vereador_nome"))
        print(f"🔍 DRY-RUN — {len(records):,} prontos | Erros validação: {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    print("  📐 DDL ok (sorocaba_verba_gabinete)")

    novos = erros = 0
    rows = [{k: r.get(k) for k in CAMPOS} for r in records]

    for i in range(0, len(rows), 500):
        lote = rows[i:i + 500]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            if (i // 500 + 1) % 20 == 0:
                print(f"  ✅ {novos:,} inseridos...")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//500+1} falhou: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    cur.execute(
        ETL_LOG,
        (
            "sorocaba_verba_gabinete", "fase_1",
            "sucesso" if erros == 0 else "parcial",
            len(records), novos, None if erros == 0 else f"{erros} erros",
            round(dur, 2), inicio, fim,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Carga concluída em {dur:.1f}s | Inseridos: {novos:,} | Erros: {erros}")
    print("\n✅ Agent C concluído.")


if __name__ == "__main__":
    main()
