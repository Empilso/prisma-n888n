#!/usr/bin/env python3
"""Agent V — Quality Gate SIGA-BA Emendas Estaduais

Execução:
    python agent_verify.py
    python agent_verify.py --strict
"""
import argparse, psycopg2
from datetime import datetime
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

CHECKS = []
def check(nome, desc):
    def dec(fn):
        CHECKS.append((nome, desc, fn))
        return fn
    return dec

@check("VOLUME_MINIMO", "Total de registros ≥ 100")
def c1(cur, strict):
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais")
    total = cur.fetchone()[0]
    ok = total >= 100
    return ok, f"{total:,} registros", not ok and strict

@check("ANOS_COBERTOS", "≥ 3 anos distintos carregados")
def c2(cur, strict):
    cur.execute("SELECT COUNT(DISTINCT ano_loa) FROM emendas_estaduais")
    anos = cur.fetchone()[0]
    ok = anos >= 3
    cur.execute("SELECT DISTINCT ano_loa FROM emendas_estaduais ORDER BY ano_loa")
    lista = [r[0] for r in cur.fetchall()]
    return ok, f"{anos} anos: {lista}", not ok

@check("VALOR_AUTORIZADO", "≥ 90% com valor_autorizado > 0")
def c3(cur, strict):
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia", strict
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais WHERE valor_autorizado > 0")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 90
    return ok, f"{pct:.1f}% com valor > 0 ({com:,}/{total:,})", not ok

@check("MUNICIPIO_PREENCHIDO", "≥ 60% com municipio_destino")
def c4(cur, strict):
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia", strict
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais WHERE municipio_destino IS NOT NULL")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 60
    return ok, f"{pct:.1f}% com municipio ({com:,}/{total:,})", not ok

@check("SEM_DUPLICATAS", "Nenhum id_emenda duplicado")
def c5(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT id_emenda FROM emendas_estaduais
            GROUP BY id_emenda HAVING COUNT(*) > 1
        ) t
    """)
    dups = cur.fetchone()[0]
    ok = dups == 0
    return ok, f"{dups} ids duplicados", not ok and strict

@check("VALOR_TOTAL_RAZOAVEL", "Total autorizado > R$ 100k")
def c6(cur, strict):
    cur.execute("SELECT COALESCE(SUM(valor_autorizado), 0) FROM emendas_estaduais")
    total = float(cur.fetchone()[0])
    ok = total > 100_000
    return ok, f"R$ {total:,.2f} total autorizado", not ok

@check("PARLAMENTARES_DISTINTOS", "≥ 5 parlamentares distintos")
def c7(cur, strict):
    cur.execute("SELECT COUNT(DISTINCT parlamentar_nome) FROM emendas_estaduais WHERE parlamentar_nome IS NOT NULL")
    count = cur.fetchone()[0]
    ok = count >= 5
    return ok, f"{count} parlamentares distintos", not ok


def main():
    parser = argparse.ArgumentParser(description='Agent V — Quality Gate SIGA-BA Emendas')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()

    print(f"🔍 Quality Gate — emendas_estaduais | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()

    passou = falhou = 0
    falhas_criticas = []

    for nome, desc, fn in CHECKS:
        try:
            ok, detalhe, critico = fn(cur, args.strict)
        except Exception as e:
            ok, detalhe, critico = False, f"ERRO: {e}", True

        emoji = "✅" if ok else ("🔴" if critico else "🟡")
        status = "PASS" if ok else ("FAIL" if critico else "WARN")
        print(f"{emoji} [{status}] {nome}")
        print(f"       {desc}")
        print(f"       → {detalhe}\n")

        if ok:
            passou += 1
        else:
            falhou += 1
            if critico:
                falhas_criticas.append(nome)

    cur.close()
    conn.close()

    print("─" * 50)
    print(f"Resultado: {passou} PASS | {falhou} FAIL")
    if falhas_criticas:
        print(f"🔴 Críticos: {falhas_criticas}")
        exit(1)
    else:
        print("✅ Quality Gate aprovado.")

if __name__ == '__main__':
    main()
