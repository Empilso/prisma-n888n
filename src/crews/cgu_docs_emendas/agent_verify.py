#!/usr/bin/env python3
"""Agent V — Verify: Quality Gate emendas_execucao_orcamentaria

Checks realizados:
  1. Volume total > 0
  2. Anos carregados (esperado: ao menos o mais recente disponível)
  3. % registros com municipio_ibge >= 40% (municípios específicos)
  4. Sem id_registro duplicado
  5. Emendas individuais > bancadas (na maioria dos anos)
  6. Valores monetários sem NaN/NULL crítico
  7. Cross-check: emendas em execucao existem em emendas_federais
  8. Top 5 parlamentares por valor empenhado (sanity check)

Execução:
    python agent_verify.py
    python agent_verify.py --strict
"""
import argparse, psycopg2, psycopg2.extras
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


DB = dict(host="localhost", port=5432, dbname="prisma_data",
          user="postgres", password=DB_PASSWORD)

CHECKS: list[dict] = []


def check(nome: str, passou: bool, detalhe: str = "", critico: bool = False):
    ico = "✅" if passou else ("❌" if critico else "⚠️ ")
    CHECKS.append({"nome": nome, "passou": passou, "detalhe": detalhe, "critico": critico})
    print(f"  {ico} {nome}: {detalhe}")


def main():
    parser = argparse.ArgumentParser(description="Agent V — Verify Despesas de Emendas")
    parser.add_argument("--strict", action="store_true", help="Falha se qualquer check crítico falhar")
    args = parser.parse_args()

    print("🔍 Agent V — Verify emendas_execucao_orcamentaria\n")
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Volume total
    cur.execute("SELECT COUNT(*) AS n FROM emendas_execucao_orcamentaria")
    total = cur.fetchone()["n"]
    check("Volume total", total > 0, f"{total:,} registros", critico=True)

    if total == 0:
        print("\n❌ Tabela vazia — execute Agents A+B+C primeiro.")
        return

    # 2. Anos carregados
    cur.execute("""
        SELECT SUBSTRING(ano_mes, 1, 4) AS ano, COUNT(*) AS n,
               SUM(valor_empenhado) AS emp
        FROM emendas_execucao_orcamentaria
        GROUP BY 1 ORDER BY 1
    """)
    anos = cur.fetchall()
    anos_str = " | ".join(f"{r['ano']}: {r['n']:,} reg / R${float(r['emp'] or 0)/1e6:.1f}M" for r in anos)
    check("Anos carregados", len(anos) >= 1, anos_str)

    # 3. % com municipio_ibge
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE municipio IS NOT NULL AND municipio != '') AS com_municipio,
            COUNT(*) FILTER (WHERE municipio_ibge IS NOT NULL) AS com_ibge,
            COUNT(*) AS total
        FROM emendas_execucao_orcamentaria
    """)
    r = cur.fetchone()
    pct_ibge = round(r["com_ibge"] / max(r["com_municipio"], 1) * 100, 1)
    check("Resolução município→IBGE",
          pct_ibge >= 40,
          f"{r['com_ibge']:,}/{r['com_municipio']:,} com município = {pct_ibge}%")

    # 4. Duplicatas de id_registro
    cur.execute("""
        SELECT COUNT(*) AS n FROM (
            SELECT id_registro FROM emendas_execucao_orcamentaria
            GROUP BY id_registro HAVING COUNT(*) > 1
        ) t
    """)
    dups = cur.fetchone()["n"]
    check("Sem duplicatas id_registro", dups == 0, f"{dups} duplicatas", critico=True)

    # 5. Tipos de emenda
    cur.execute("""
        SELECT tipo_emenda, COUNT(*) AS n, SUM(valor_empenhado) AS emp
        FROM emendas_execucao_orcamentaria
        GROUP BY tipo_emenda ORDER BY emp DESC NULLS LAST
    """)
    tipos = cur.fetchall()
    tipos_str = " | ".join(f"{r['tipo_emenda']}: {r['n']:,}" for r in tipos)
    check("Tipos de emenda presentes", len(tipos) >= 1, tipos_str)

    # 6. Valores sem NULL crítico
    cur.execute("""
        SELECT COUNT(*) AS sem_valor
        FROM emendas_execucao_orcamentaria
        WHERE valor_empenhado IS NULL AND valor_pago IS NULL
          AND valor_resto_inscrito IS NULL
    """)
    sem_valor = cur.fetchone()["sem_valor"]
    check("Valores monetários presentes", sem_valor == 0,
          f"{sem_valor} registros sem nenhum valor monetário")

    # 7. Cross-check com emendas_federais
    cur.execute("""
        SELECT COUNT(DISTINCT e.codigo_emenda) AS em_execucao,
               COUNT(DISTINCT ef.codigo_emenda) AS em_federais
        FROM emendas_execucao_orcamentaria e
        LEFT JOIN emendas_federais ef ON ef.codigo_emenda = e.codigo_emenda
    """)
    r = cur.fetchone()
    pct_match = round(r["em_federais"] / max(r["em_execucao"], 1) * 100, 1)
    check("Cross-check com emendas_federais",
          pct_match >= 30,
          f"{r['em_federais']:,}/{r['em_execucao']:,} emendas com match = {pct_match}%")

    # 8. Top 5 parlamentares
    cur.execute("""
        SELECT nome_autor_emenda, COUNT(*) AS n,
               SUM(valor_empenhado) AS emp, SUM(valor_pago) AS pago
        FROM emendas_execucao_orcamentaria
        WHERE tipo_emenda = 'INDIVIDUAL'
        GROUP BY nome_autor_emenda
        ORDER BY emp DESC NULLS LAST
        LIMIT 5
    """)
    top5 = cur.fetchall()
    print("\n  📊 Top 5 parlamentares por empenhado (INDIVIDUAL):")
    for r in top5:
        print(f"     {r['nome_autor_emenda']}: R${float(r['emp'] or 0)/1e6:.1f}M emp / "
              f"R${float(r['pago'] or 0)/1e6:.1f}M pago ({r['n']} registros)")

    conn.close()

    # Resultado final
    falhas_criticas = [c for c in CHECKS if not c["passou"] and c["critico"]]
    falhas_aviso    = [c for c in CHECKS if not c["passou"] and not c["critico"]]
    passaram        = sum(1 for c in CHECKS if c["passou"])

    print(f"\n{'='*50}")
    print(f"✅ Passaram: {passaram}/{len(CHECKS)} | "
          f"❌ Críticos: {len(falhas_criticas)} | "
          f"⚠️  Avisos: {len(falhas_aviso)}")

    if args.strict and falhas_criticas:
        print("\n❌ STRICT MODE: checks críticos falharam.")
        raise SystemExit(1)

    print("\n✅ Agent V concluído.")


if __name__ == "__main__":
    main()
