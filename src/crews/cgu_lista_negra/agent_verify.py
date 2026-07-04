#!/usr/bin/env python3
"""Agent V — Quality Gate CGU Lista Negra

8 checks enterprise para garantir integridade da carga.

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

@check("VOLUME_MINIMO", "Total de registros ≥ 5.000")
def c1(cur, strict):
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo")
    total = cur.fetchone()[0]
    ok = total >= 5000
    return ok, f"{total:,} registros", not ok and strict

@check("TRES_FONTES", "CEIS, CNEP e CEPIM presentes (coluna: origem)")
def c2(cur, strict):
    cur.execute("SELECT DISTINCT origem FROM lista_negra_governo ORDER BY origem")
    fontes = [r[0] for r in cur.fetchall()]
    esperadas = {'CEIS', 'CNEP', 'CEPIM'}
    faltando = esperadas - set(fontes)
    ok = len(faltando) == 0
    return ok, f"Fontes: {fontes} | Faltando: {faltando or 'nenhuma'}", not ok and strict

@check("CNPJ_CPF_PREENCHIDO", "≥ 85% com cnpj ou cpf_sancionado preenchido")
def c3(cur, strict):
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia", strict
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo WHERE cnpj IS NOT NULL OR cpf_sancionado IS NOT NULL")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 85
    return ok, f"{pct:.1f}% com cnpj/cpf ({com:,}/{total:,})", not ok

@check("DATAS_VALIDAS", "≥ 80% com data_inicio válida")
def c4(cur, strict):
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia", strict
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo WHERE data_inicio IS NOT NULL")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 80
    return ok, f"{pct:.1f}% com data_inicio ({com:,}/{total:,})", not ok

@check("SEM_DUPLICATAS", "Nenhum id_registro duplicado")
def c5(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT id_registro FROM lista_negra_governo
            GROUP BY id_registro HAVING COUNT(*) > 1
        ) t
    """)
    dups = cur.fetchone()[0]
    ok = dups == 0
    return ok, f"{dups} id_registro duplicados", not ok and strict

@check("CEIS_VOLUME", "CEIS com ≥ 3.000 registros (maior lista)")
def c6(cur, strict):
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo WHERE origem = 'CEIS'")
    total = cur.fetchone()[0]
    ok = total >= 3000
    return ok, f"CEIS: {total:,} registros", not ok

@check("SANCOES_ATIVAS", "Registros ativos (ativo=TRUE) existem")
def c7(cur, strict):
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo WHERE ativo = TRUE")
    total = cur.fetchone()[0]
    ok = total > 0
    return ok, f"{total:,} registros ativos", not ok

@check("ORGAOS_PREENCHIDOS", "≥ 70% com orgao_sancionador")
def c8(cur, strict):
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia", strict
    cur.execute("SELECT COUNT(*) FROM lista_negra_governo WHERE orgao_sancionador IS NOT NULL")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 70
    return ok, f"{pct:.1f}% com orgao_sancionador", not ok


def main():
    parser = argparse.ArgumentParser(description='Agent V — Quality Gate CGU Lista Negra')
    parser.add_argument('--strict', action='store_true', help='Falha em qualquer check negativo')
    args = parser.parse_args()

    print(f"🔍 Quality Gate — lista_negra_governo | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

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
        print(f"🔴 Checks críticos falharam: {falhas_criticas}")
        exit(1)
    else:
        print("✅ Quality Gate aprovado.")

if __name__ == '__main__':
    main()
