#!/usr/bin/env python3
"""
Agent C — Loader PostgreSQL TCE-SP Municípios
Prata → tabela tcesp_municipios (UPSERT idempotente)

Cria a tabela na primeira execução. Chave: slug_tcesp.
FK id_ibge → municipios(id_ibge) garante que nunca carregamos
um município que não exista na base territorial IBGE.

USO:
    python agent_c_loader.py [--dry-run]
"""
import json
import argparse
import os
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import Json

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

DB_CONFIG = {
    'host':     'localhost',
    'port':     5432,
    'dbname':   'prisma_data',
    'user':     'postgres',
    'password': DB_PASSWORD,
}

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS tcesp_municipios (
    slug_tcesp       text PRIMARY KEY,
    nome_tcesp       text NOT NULL,
    uf               character(2) NOT NULL DEFAULT 'SP',
    id_ibge          character(7) REFERENCES municipios(id_ibge),
    nome_ibge        text,
    match_status     text NOT NULL,          -- exato | fuzzy | manual
    match_confidence numeric(4,3),
    ativo            boolean DEFAULT true,
    raw_payload      jsonb,
    dt_extracao      timestamptz,
    created_at       timestamptz DEFAULT now(),
    updated_at       timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tcesp_municipios_ibge ON tcesp_municipios (id_ibge);
"""

UPSERT_SQL = """
INSERT INTO tcesp_municipios (
    slug_tcesp, nome_tcesp, uf, id_ibge, nome_ibge,
    match_status, match_confidence, raw_payload, dt_extracao
) VALUES (
    %(slug_tcesp)s, %(nome_tcesp)s, %(uf)s, %(id_ibge)s, %(nome_ibge)s,
    %(match_status)s, %(match_confidence)s, %(raw_payload)s, %(dt_extracao)s
)
ON CONFLICT (slug_tcesp) DO UPDATE SET
    nome_tcesp       = EXCLUDED.nome_tcesp,
    id_ibge          = EXCLUDED.id_ibge,
    nome_ibge        = EXCLUDED.nome_ibge,
    match_status     = CASE WHEN tcesp_municipios.match_status = 'manual'
                            THEN tcesp_municipios.match_status
                            ELSE EXCLUDED.match_status END,
    match_confidence = CASE WHEN tcesp_municipios.match_status = 'manual'
                            THEN tcesp_municipios.match_confidence
                            ELSE EXCLUDED.match_confidence END,
    raw_payload      = EXCLUDED.raw_payload,
    dt_extracao      = EXCLUDED.dt_extracao,
    updated_at       = now();
"""

ETL_LOG_SQL = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     registros_atualizados, erro_mensagem, duracao_seg,
                     iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    pratas = sorted(PRATA_DIR.glob("*prata.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not pratas:
        print("❌ Nenhum arquivo Prata encontrado em", PRATA_DIR)
        raise SystemExit(1)

    prata_path = pratas[0]
    print(f"📂 Prata: {prata_path.name}")

    with open(prata_path, encoding='utf-8') as f:
        prata = json.load(f)

    records = prata.get('records', [])
    print(f"📊 Registros a carregar: {len(records)}")

    if args.dry_run:
        print("🔍 DRY-RUN — nenhum dado será gravado")
        print(f"✅ Simulação OK: {len(records)} registros prontos para carga")
        return

    inicio = datetime.now(timezone.utc)
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute(CREATE_SQL)
    conn.commit()

    carregados = erros = 0
    BATCH = 200

    for i in range(0, len(records), BATCH):
        lote = [{**r, "raw_payload": Json(r["raw_payload"])} for r in records[i:i+BATCH]]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            carregados += len(lote)
            print(f"  ✅ Lote {i//BATCH + 1}: {len(lote)} registros")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//BATCH + 1} falhou: {e}")

    fim = datetime.now(timezone.utc)
    duracao = (fim - inicio).total_seconds()

    cur.execute(ETL_LOG_SQL, (
        'tcesp_municipal', 'fase_1_cadastro', 'sucesso' if erros == 0 else 'parcial',
        len(records), carregados, 0, None if erros == 0 else f'{erros} erros',
        round(duracao, 2), inicio, fim
    ))
    conn.commit()

    cur.execute("""
        SELECT match_status, count(*), round(avg(match_confidence), 3)
        FROM tcesp_municipios GROUP BY match_status ORDER BY 2 DESC
    """)
    print("\n── ESTADO DA TABELA tcesp_municipios ──")
    for status, n, conf in cur.fetchall():
        print(f"   {status:>8}: {n:>4} municípios (confiança média {conf})")

    cur.close()
    conn.close()

    print(f"\n✅ Carga concluída em {duracao:.1f}s")
    print(f"   Carregados: {carregados} | Erros: {erros}")

if __name__ == '__main__':
    main()
