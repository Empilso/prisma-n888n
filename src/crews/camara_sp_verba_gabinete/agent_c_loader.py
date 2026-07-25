#!/usr/bin/env python3
"""Agent C — Loader Câmara SP Verba de Gabinete: Prata → tabela camara_sp_verba_gabinete"""
import json
import argparse
import psycopg2
from pathlib import Path
from datetime import datetime, timezone
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PRATA_PATH = BASE_DIR / "data/camara_sp_verba_gabinete/prata/camara_sp_verba_prata.json"

DB = dict(host="localhost", port=5432, dbname="prisma_data", user="postgres", password=DB_PASSWORD)

DDL = """
CREATE TABLE IF NOT EXISTS camara_sp_verba_gabinete (
    id                text PRIMARY KEY,
    politico_id       text,
    centro_custos_id  integer NOT NULL,
    vereador_nome     text NOT NULL,
    cnpj_fornecedor   text,
    nome_fornecedor   text,
    tipo_despesa      text,
    valor             numeric NOT NULL,
    mes               integer NOT NULL,
    ano               integer NOT NULL,
    competencia       text NOT NULL,
    status_lneg       status_lneg_enum,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_camara_sp_verba_competencia ON camara_sp_verba_gabinete (competencia);
CREATE INDEX IF NOT EXISTS idx_camara_sp_verba_politico ON camara_sp_verba_gabinete (politico_id);
CREATE INDEX IF NOT EXISTS idx_camara_sp_verba_cnpj ON camara_sp_verba_gabinete (cnpj_fornecedor);
"""

UPSERT_SQL = """
INSERT INTO camara_sp_verba_gabinete (
    id, politico_id, centro_custos_id, vereador_nome,
    cnpj_fornecedor, nome_fornecedor, tipo_despesa,
    valor, mes, ano, competencia, status_lneg
) VALUES (
    %(id)s, %(politico_id)s, %(centro_custos_id)s, %(vereador_nome)s,
    %(cnpj_fornecedor)s, %(nome_fornecedor)s, %(tipo_despesa)s,
    %(valor)s, %(mes)s, %(ano)s, %(competencia)s, %(status_lneg)s
)
ON CONFLICT (id) DO NOTHING
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

CAMPOS = [
    "id", "politico_id", "centro_custos_id", "vereador_nome", "cnpj_fornecedor",
    "nome_fornecedor", "tipo_despesa", "valor", "mes", "ano", "competencia", "status_lneg",
]


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader Câmara SP Verba de Gabinete")
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
        erros = sum(1 for r in records[:200] if not r.get("id") or r.get("centro_custos_id") is None)
        print(f"🔍 DRY-RUN — {len(records):,} prontos | Erros validação: {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    print("  📐 DDL ok (camara_sp_verba_gabinete)")

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
            "camara_sp_verba_gabinete", "fase_1",
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
