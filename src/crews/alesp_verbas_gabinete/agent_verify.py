#!/usr/bin/env python3
"""Agent Verify — Quality Gate ALESP Verbas Gabinete

Checks:
  [1] Volume total (>= 50.000 registros)
  [2] Período (anos 2015 a atual)
  [3] Deputados únicos (esperado 80–200)
  [4] Valor total dentro do intervalo histórico (R$ 50M–R$ 2B)
  [5] Zero valores negativos ou zero
  [6] Cobertura politico_id (>= 60% vinculados)
  [7] Zero duplicatas de id
  [8] Categorias de despesa distintas (>= 5)
"""
import argparse, psycopg2, sys
from datetime import datetime, timezone

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password='prisma2026')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()

    print(f"🔍 Quality Gate — ALESP Verbas Gabinete | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 54)

    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    checks = []

    def check(nome, ok, detalhe, critico=False):
        s = '✅' if ok else ('❌' if critico else '⚠️ ')
        checks.append({'ok': ok, 'critico': critico})
        print(f"  {s} {nome}: {detalhe}")

    cur.execute('SELECT COUNT(*) FROM alesp_verbas_gabinete')
    total = cur.fetchone()[0]
    check('[1] Volume total', total >= 50_000, f'{total:,} registros (mínimo 50.000)', critico=True)

    cur.execute('SELECT MIN(ano), MAX(ano) FROM alesp_verbas_gabinete')
    ano_min, ano_max = cur.fetchone()
    check('[2] Período', (ano_min or 9999) <= 2016 and (ano_max or 0) >= 2024,
          f'{ano_min} → {ano_max}', critico=True)

    cur.execute('SELECT COUNT(DISTINCT nome_deputado) FROM alesp_verbas_gabinete')
    deps = cur.fetchone()[0]
    check('[3] Deputados únicos', 80 <= deps <= 600, f'{deps} (esperado 80–600 — histórico multilegisl.)', critico=True)

    cur.execute('SELECT SUM(valor::numeric) FROM alesp_verbas_gabinete')
    soma = float(cur.fetchone()[0] or 0)
    check('[4] Valor total', 50_000_000 <= soma <= 2_000_000_000,
          f'R$ {soma:,.0f}', critico=True)

    cur.execute('SELECT COUNT(*) FROM alesp_verbas_gabinete WHERE valor::numeric <= 0')
    neg = cur.fetchone()[0]
    check('[5] Valores inválidos (<=0)', neg == 0, f'{neg} registros', critico=True)

    cur.execute('SELECT COUNT(*) FROM alesp_verbas_gabinete WHERE politico_id IS NOT NULL')
    com_pid = cur.fetchone()[0]
    pct = com_pid / max(total, 1) * 100
    check('[6] Cobertura politico_id', pct >= 60, f'{com_pid:,} ({pct:.1f}%) vinculados')

    cur.execute('SELECT COUNT(*) - COUNT(DISTINCT id) FROM alesp_verbas_gabinete')
    dupes = cur.fetchone()[0]
    check('[7] Duplicatas', dupes == 0, f'{dupes}', critico=True)

    cur.execute('SELECT COUNT(DISTINCT tipo_despesa) FROM alesp_verbas_gabinete')
    cats = cur.fetchone()[0]
    check('[8] Categorias', cats >= 5, f'{cats} categorias distintas')

    cur.close(); conn.close()

    falhas = sum(1 for c in checks if not c['ok'] and c.get('critico'))
    avisos = sum(1 for c in checks if not c['ok'] and not c.get('critico'))
    print("=" * 54)
    if falhas == 0:
        print(f"  ✅ QUALITY GATE PASSOU" + (f" ({avisos} aviso(s))" if avisos else ""))
    else:
        print(f"  ❌ QUALITY GATE FALHOU — {falhas} check(s) crítico(s)")
        if args.strict:
            sys.exit(1)

if __name__ == '__main__':
    main()
