#!/usr/bin/env python3
"""
Agent C — Loader PostgreSQL IBGE
Prata → tabela municipios (UPSERT idempotente)
"""
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


BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/raw/ibge/prata"

DB_CONFIG = {
    'host':     'localhost',
    'port':     5432,
    'dbname':   'prisma_data',
    'user':     'postgres',
    'password': DB_PASSWORD,
}

UPSERT_SQL = """
INSERT INTO municipios (
    id_ibge, nome, uf, uf_nome,
    regiao_sigla, regiao_nome,
    mesorregiao_id, mesorregiao_nome,
    microrregiao_id, microrregiao_nome,
    lat, lng, capital, ddd, fuso_horario
) VALUES (
    %(id_ibge)s, %(nome)s, %(uf)s, %(uf_nome)s,
    %(regiao_sigla)s, %(regiao_nome)s,
    %(mesorregiao_id)s, %(mesorregiao_nome)s,
    %(microrregiao_id)s, %(microrregiao_nome)s,
    %(lat)s, %(lng)s, %(capital)s, %(ddd)s, %(fuso_horario)s
)
ON CONFLICT (id_ibge) DO UPDATE SET
    nome              = EXCLUDED.nome,
    uf                = EXCLUDED.uf,
    uf_nome           = EXCLUDED.uf_nome,
    regiao_sigla      = EXCLUDED.regiao_sigla,
    regiao_nome       = EXCLUDED.regiao_nome,
    mesorregiao_id    = EXCLUDED.mesorregiao_id,
    mesorregiao_nome  = EXCLUDED.mesorregiao_nome,
    microrregiao_id   = EXCLUDED.microrregiao_id,
    microrregiao_nome = EXCLUDED.microrregiao_nome,
    lat               = EXCLUDED.lat,
    lng               = EXCLUDED.lng,
    capital           = EXCLUDED.capital,
    ddd               = EXCLUDED.ddd,
    fuso_horario      = EXCLUDED.fuso_horario;
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

    # Pega o Prata mais recente
    pratas = sorted(PRATA_DIR.glob("*prata.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not pratas:
        print("❌ Nenhum arquivo Prata encontrado em", PRATA_DIR)
        return

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
    cur  = conn.cursor()

    novos = atualizados = erros = 0
    BATCH = 500

    for i in range(0, len(records), BATCH):
        lote = records[i:i+BATCH]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            print(f"  ✅ Lote {i//BATCH + 1}: {len(lote)} registros")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//BATCH + 1} falhou: {e}")

    fim = datetime.now(timezone.utc)
    duracao = (fim - inicio).total_seconds()

    # Registrar em etl_log
    cur.execute(ETL_LOG_SQL, (
        'ibge_municipios', 'fase_0', 'sucesso' if erros == 0 else 'parcial',
        len(records), novos, atualizados, None if erros == 0 else f'{erros} erros',
        round(duracao, 2), inicio, fim
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"\n✅ Carga concluída em {duracao:.1f}s")
    print(f"   Inseridos/atualizados: {novos}")
    print(f"   Erros: {erros}")

if __name__ == '__main__':
    main()
