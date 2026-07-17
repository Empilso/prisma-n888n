#!/usr/bin/env python3
"""Recarga completa de 2008 com a chave corrigida (inclui UF), corrigindo a
sobrescrita entre-UF causada pela constraint antiga (sq_candidato, ano_eleicao, nr_ordem)."""
import json, glob, os, time
import psycopg2

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido")

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)
PRATA_DIR = "/home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma/data/tse_bens_declarados/prata"

UPSERT_SQL = """
INSERT INTO bens_declarados (
    sq_candidato, ano_eleicao, uf, nr_ordem,
    tipo_bem_cod, tipo_bem, descricao, valor
) VALUES (
    %(sq_candidato)s, %(ano_eleicao)s, %(uf)s, %(nr_ordem)s,
    %(tipo_bem_cod)s, %(tipo_bem)s, %(descricao)s, %(valor)s
)
ON CONFLICT (sq_candidato, ano_eleicao, nr_ordem, uf)
DO UPDATE SET valor = EXCLUDED.valor, descricao = EXCLUDED.descricao,
              tipo_bem = EXCLUDED.tipo_bem, tipo_bem_cod = EXCLUDED.tipo_bem_cod
"""

conn = psycopg2.connect(**DB)
cur = conn.cursor()
total = 0
for f in sorted(glob.glob(f"{PRATA_DIR}/bens_2008_*_prata.json")):
    with open(f, encoding='utf-8') as fh:
        prata = json.load(fh)
    records = prata.get('records', [])
    rows = [{k: v for k, v in r.items() if k != 'prisma_id'} for r in records]
    inicio = time.time()
    for i in range(0, len(rows), 500):
        lote = rows[i:i+500]
        cur.executemany(UPSERT_SQL, lote)
        conn.commit()
    total += len(rows)
    print(f"{os.path.basename(f)}: {len(rows)} registros em {time.time()-inicio:.1f}s (total acumulado {total})")

cur.close()
conn.close()
print(f"\nRECARGA 2008 CONCLUÍDA: {total} registros inseridos/atualizados")
