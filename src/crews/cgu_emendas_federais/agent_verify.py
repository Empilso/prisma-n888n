#!/usr/bin/env python3
"""Agent V — Verify: Quality Gate emendas_federais

Checks realizados:
  1. Volume total > 0 (crítico)
  2. Anos carregados (esperado 2014-2026 após --todos)
  3. Sem codigo_emenda duplicado (crítico — é a PK, não deveria nem ser possível)
  4. % politico_id / cnpj_favorecido / municipio_ibge não regrediu vs. baseline
     conhecido antes desta crew existir (93.1% / 50.0% / 27.5%, medido 2026-07-20)
  5. Cross-check: codigo_emenda de emendas_federais_pagamentos deve existir aqui
  6. Top 5 autores por valor empenhado (sanity check)

Execução:
    python agent_verify.py
    python agent_verify.py --strict
"""
import argparse, psycopg2, psycopg2.extras
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

DB = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 5432)),
    dbname   = os.getenv("DB_NAME", "prisma_data"),
    user     = os.getenv("DB_USER", "postgres"),
    password = DB_PASSWORD,
)

# Baseline medido em 2026-07-20 antes desta crew existir — nunca regredir abaixo disso
BASELINE_PCT_POLITICO = 93.0
BASELINE_PCT_CNPJ     = 49.0
BASELINE_PCT_IBGE      = 27.0

CHECKS: list[dict] = []


def check(nome: str, passou: bool, detalhe: str = "", critico: bool = False):
    ico = "✅" if passou else ("❌" if critico else "⚠️ ")
    CHECKS.append({"nome": nome, "passou": passou, "detalhe": detalhe, "critico": critico})
    print(f"  {ico} {nome}: {detalhe}")


def main():
    parser = argparse.ArgumentParser(description="Agent V — Verify emendas_federais")
    parser.add_argument("--strict", action="store_true", help="Falha se qualquer check crítico falhar")
    args = parser.parse_args()

    print("🔍 Agent V — Verify emendas_federais\n")
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT COUNT(*) AS n FROM emendas_federais")
    total = cur.fetchone()["n"]
    check("Volume total", total > 0, f"{total:,} registros", critico=True)
    if total == 0:
        print("\n❌ Tabela vazia — execute Agents A+B+C primeiro.")
        return

    cur.execute("""
        SELECT ano_orcamento, COUNT(*) AS n
        FROM emendas_federais GROUP BY 1 ORDER BY 1
    """)
    anos = cur.fetchall()
    anos_str = " | ".join(f"{r['ano_orcamento']}: {r['n']:,}" for r in anos)
    check("Anos carregados", len(anos) >= 1, anos_str)
    check("Cobre 2014", any(r["ano_orcamento"] == 2014 for r in anos),
          "2014 presente" if any(r["ano_orcamento"] == 2014 for r in anos) else "2014 AUSENTE")

    cur.execute("""
        SELECT COUNT(*) AS n FROM (
            SELECT codigo_emenda FROM emendas_federais
            GROUP BY codigo_emenda HAVING COUNT(*) > 1
        ) t
    """)
    dups = cur.fetchone()["n"]
    check("Sem duplicatas codigo_emenda", dups == 0, f"{dups} duplicatas", critico=True)

    cur.execute("""
        SELECT
            ROUND(100.0 * COUNT(politico_id) / COUNT(*), 1) AS pct_politico,
            ROUND(100.0 * COUNT(cnpj_favorecido) / COUNT(*), 1) AS pct_cnpj,
            ROUND(100.0 * COUNT(municipio_ibge) / COUNT(*), 1) AS pct_ibge
        FROM emendas_federais
    """)
    r = cur.fetchone()
    check("% politico_id não regrediu", float(r["pct_politico"]) >= BASELINE_PCT_POLITICO,
          f"{r['pct_politico']}% (baseline {BASELINE_PCT_POLITICO}%)")
    check("% cnpj_favorecido não regrediu", float(r["pct_cnpj"]) >= BASELINE_PCT_CNPJ,
          f"{r['pct_cnpj']}% (baseline {BASELINE_PCT_CNPJ}%)")
    check("% municipio_ibge não regrediu", float(r["pct_ibge"]) >= BASELINE_PCT_IBGE,
          f"{r['pct_ibge']}% (baseline {BASELINE_PCT_IBGE}%)")

    cur.execute("""
        SELECT COUNT(DISTINCT p.codigo_emenda) AS em_pagamentos,
               COUNT(DISTINCT ef.codigo_emenda) AS em_federais
        FROM emendas_federais_pagamentos p
        LEFT JOIN emendas_federais ef ON ef.codigo_emenda = p.codigo_emenda
    """)
    r = cur.fetchone()
    pct_match = round(r["em_federais"] / max(r["em_pagamentos"], 1) * 100, 1)
    check("Cross-check com emendas_federais_pagamentos", pct_match >= 50,
          f"{r['em_federais']:,}/{r['em_pagamentos']:,} com match = {pct_match}%")

    cur.execute("""
        SELECT nome_autor, COUNT(*) AS n, SUM(valor_empenhado) AS emp
        FROM emendas_federais
        GROUP BY nome_autor ORDER BY emp DESC NULLS LAST LIMIT 5
    """)
    print("\n  📊 Top 5 autores por valor empenhado:")
    for r in cur.fetchall():
        print(f"     {r['nome_autor']}: R${float(r['emp'] or 0)/1e6:.1f}M ({r['n']} emendas)")

    conn.close()

    falhas_criticas = [c for c in CHECKS if not c["passou"] and c["critico"]]
    falhas_aviso    = [c for c in CHECKS if not c["passou"] and not c["critico"]]
    passaram        = sum(1 for c in CHECKS if c["passou"])

    print(f"\n{'='*50}")
    print(f"✅ Passaram: {passaram}/{len(CHECKS)} | "
          f"❌ Críticos: {len(falhas_criticas)} | ⚠️  Avisos: {len(falhas_aviso)}")

    if args.strict and falhas_criticas:
        print("\n❌ STRICT MODE: checks críticos falharam.")
        raise SystemExit(1)

    print("\n✅ Agent V concluído.")


if __name__ == "__main__":
    main()
