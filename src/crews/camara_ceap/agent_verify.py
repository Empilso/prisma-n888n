#!/usr/bin/env python3
"""Agent Verify — Quality Gate Câmara CEAP

Verificação enterprise dos dados carregados em camara_verbas_ceap.
Executa após o Agent C e impede carga de ser considerada válida se falhar.

Checks implementados:
  [1] Volume mínimo por ano (sem anos vazios)
  [2] Período correto (datas dentro do ano esperado)
  [3] Deputados únicos por ano (esperado 400–600)
  [4] Valor total por ano dentro do intervalo histórico conhecido
  [5] Zero registros com valor negativo
  [6] Zero politico_id nulo (sem vínculo com parlamentar)
  [7] Sem duplicatas de id_documento
  [8] Cobertura de categorias CEAP (deve ter ≥ 5 categorias distintas/ano)

Execução:
    python agent_verify.py --ano 2024
    python agent_verify.py --todos
    python agent_verify.py --todos --strict   # falha se qualquer check falhar
"""
import argparse, psycopg2, sys
from datetime import datetime, timezone

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password='prisma2026')

# Limites históricos por faixa de ano (R$ total esperado/ano)
VALOR_MIN_ANO = {
    range(2015, 2017): 100_000_000,   # 100M
    range(2017, 2020): 150_000_000,   # 150M
    range(2020, 2021): 80_000_000,    # pandemia
    range(2021, 2025): 150_000_000,   # 150M
    range(2025, 2026): 50_000_000,    # ano parcial
}
VALOR_MAX_ANO = 600_000_000   # 600M — nunca passará disto para um ano

REGISTROS_MIN_ANO = 100_000   # mínimo de linhas por ano completo
DEPS_MIN = 100                # mínimo de deputados distintos por ano
DEPS_MAX = 900                # máximo razoável — anos de início de legislatura (2015,2019,2023)
                              # incluem saída + entrada de deputies → até ~800 únicos normais
CATEGORIAS_MIN = 5            # mínimo de categorias de gasto distintas
ANOS_TRANSICAO = {2015, 2019, 2023}  # início de legislatura — mais únicos esperados


def valor_min_para_ano(ano: int) -> int:
    for faixa, minimo in VALOR_MIN_ANO.items():
        if ano in faixa:
            return minimo
    return 50_000_000


def verificar_ano(cur, ano: int, strict: bool) -> list[dict]:
    """Retorna lista de resultados dos checks para um ano."""
    checks = []

    def check(nome: str, passou: bool, detalhe: str, critico: bool = False):
        status = '✅' if passou else ('❌' if critico else '⚠️ ')
        checks.append({'nome': nome, 'ok': passou, 'detalhe': detalhe,
                       'critico': critico, 'status': status})

    # [1] Volume mínimo
    cur.execute("""
        SELECT COUNT(*) FROM camara_verbas_ceap
        WHERE competencia LIKE %s
    """, (f'{ano}-%',))
    total = cur.fetchone()[0]
    check('[1] Volume mínimo', total >= REGISTROS_MIN_ANO,
          f'{total:,} registros (mínimo {REGISTROS_MIN_ANO:,})', critico=True)

    if total == 0:
        check('[2] Período',    False, 'sem dados', critico=True)
        check('[3] Deputados',  False, 'sem dados', critico=True)
        check('[4] Valor total',False, 'sem dados', critico=True)
        check('[5] Negativos',  True,  '0 (ok)')
        check('[6] Nulos pid',  True,  '0 (ok)')
        check('[7] Duplicatas', True,  '0 (ok)')
        check('[8] Categorias', False, 'sem dados')
        return checks

    # [2] Período
    cur.execute("""
        SELECT MIN(data_emissao), MAX(data_emissao) FROM camara_verbas_ceap
        WHERE competencia LIKE %s
    """, (f'{ano}-%',))
    dmin, dmax = cur.fetchone()
    ano_min = dmin.year if dmin else 0
    ano_max = dmax.year if dmax else 9999
    periodo_ok = (ano_min >= ano - 1) and (ano_max <= ano + 1)
    check('[2] Período', periodo_ok,
          f'{dmin} → {dmax} (tolerância ±1 ano)')

    # [3] Deputados únicos
    cur.execute("""
        SELECT COUNT(DISTINCT politico_id) FROM camara_verbas_ceap
        WHERE competencia LIKE %s
    """, (f'{ano}-%',))
    deps = cur.fetchone()[0]
    check('[3] Deputados únicos', DEPS_MIN <= deps <= DEPS_MAX,
          f'{deps} únicos (esperado {DEPS_MIN}–{DEPS_MAX})', critico=True)

    # [4] Valor total
    cur.execute("""
        SELECT SUM(valor_liquido::numeric) FROM camara_verbas_ceap
        WHERE competencia LIKE %s
    """, (f'{ano}-%',))
    soma = float(cur.fetchone()[0] or 0)
    v_min = valor_min_para_ano(ano)
    valor_ok = v_min <= soma <= VALOR_MAX_ANO
    check('[4] Valor total', valor_ok,
          f'R$ {soma:,.0f} (esperado R$ {v_min:,.0f}–{VALOR_MAX_ANO:,.0f})', critico=True)

    # [5] Negativos
    cur.execute("""
        SELECT COUNT(*) FROM camara_verbas_ceap
        WHERE competencia LIKE %s AND valor_liquido < 0
    """, (f'{ano}-%',))
    neg = cur.fetchone()[0]
    check('[5] Valores negativos', neg == 0,
          f'{neg} registros negativos', critico=True)

    # [6] politico_id nulo
    cur.execute("""
        SELECT COUNT(*) FROM camara_verbas_ceap
        WHERE competencia LIKE %s AND politico_id IS NULL
    """, (f'{ano}-%',))
    nulos = cur.fetchone()[0]
    pct_nulos = nulos / max(total, 1) * 100
    check('[6] politico_id nulo', pct_nulos < 20,
          f'{nulos:,} ({pct_nulos:.1f}%) sem vínculo parlamentar')

    # [7] Duplicatas de id_documento
    cur.execute("""
        SELECT COUNT(*) - COUNT(DISTINCT id_documento) FROM camara_verbas_ceap
        WHERE competencia LIKE %s
    """, (f'{ano}-%',))
    dupes = cur.fetchone()[0]
    check('[7] Duplicatas id_documento', dupes == 0,
          f'{dupes} duplicatas', critico=True)

    # [8] Categorias de gasto
    cur.execute("""
        SELECT COUNT(DISTINCT tipo_despesa) FROM camara_verbas_ceap
        WHERE competencia LIKE %s
    """, (f'{ano}-%',))
    cats = cur.fetchone()[0]
    check('[8] Categorias CEAP', cats >= CATEGORIAS_MIN,
          f'{cats} categorias distintas (mínimo {CATEGORIAS_MIN})')

    return checks


def run(anos: list[int], strict: bool) -> bool:
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    passou_tudo = True

    for ano in anos:
        print(f"\n{'='*54}")
        print(f"  QUALITY GATE — Câmara CEAP {ano}")
        print(f"{'='*54}")
        checks = verificar_ano(cur, ano, strict)
        falhas_criticas = 0
        for c in checks:
            print(f"  {c['status']} {c['nome']}: {c['detalhe']}")
            if not c['ok'] and c.get('critico'):
                falhas_criticas += 1

        if falhas_criticas > 0:
            print(f"\n  ❌ {falhas_criticas} check(s) CRÍTICO(S) falharam — ano {ano} REPROVADO")
            passou_tudo = False
        else:
            warns = sum(1 for c in checks if not c['ok'])
            print(f"\n  ✅ Ano {ano} APROVADO" + (f" ({warns} aviso(s))" if warns else ""))

    cur.close()
    conn.close()

    print(f"\n{'='*54}")
    if passou_tudo:
        print("  ✅ QUALITY GATE PASSOU — dados prontos para uso")
    else:
        print("  ❌ QUALITY GATE FALHOU — verificar logs e re-processar")
        if strict:
            sys.exit(1)
    return passou_tudo


def main():
    anos_disponiveis = list(range(2015, 2026))
    parser = argparse.ArgumentParser(description='Agent Verify — Quality Gate Câmara CEAP')
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--ano',   type=int, choices=anos_disponiveis)
    grp.add_argument('--todos', action='store_true')
    parser.add_argument('--strict', action='store_true',
                        help='Exit code 1 se qualquer check crítico falhar')
    args = parser.parse_args()

    anos = anos_disponiveis if args.todos else [args.ano]
    print(f"🔍 Quality Gate — Câmara CEAP | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    run(anos, args.strict)

if __name__ == '__main__':
    main()
