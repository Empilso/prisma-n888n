#!/usr/bin/env python3
"""SAPL Genérico — Agent Verify: Quality Gate

Checks:
  1. Volume total > 0 (crítico)
  2. Sem (dominio, id_sapl) duplicado em nenhuma das 2 tabelas (crítico —
     é a chave única, não deveria nem ser possível)
  3. Taxa de câmaras confirmadas na descoberta (sapl_instancias) vs. taxa
     realmente coletada (sapl_parlamentares) — mede cobertura da Fase 1
     sobre a Fase 0
  4. % de politico_id resolvido (medido, não comparado a baseline — é a
     primeira vez que essa métrica existe; próxima rodada compara contra
     este valor)
  5. Top 5 municípios por nº de matérias (sanity check de volume)

Execução:
    python agent_verify.py
    python agent_verify.py --strict
"""
import argparse
import os

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "prisma_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)

CHECKS: list[dict] = []


def check(nome: str, passou: bool, detalhe: str = "", critico: bool = False):
    ico = "✅" if passou else ("❌" if critico else "⚠️ ")
    CHECKS.append({"nome": nome, "passou": passou, "critico": critico})
    print(f"  {ico} {nome}: {detalhe}")


def main():
    ap = argparse.ArgumentParser(description="SAPL Genérico — Agent Verify")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    print("🔍 Agent Verify — sapl_generico\n")
    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT count(*) AS n FROM sapl_parlamentares")
    n_parl = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM sapl_materias")
    n_mat = cur.fetchone()["n"]
    check("Volume parlamentares", n_parl > 0, f"{n_parl:,} registros", critico=True)
    check("Volume matérias", n_mat > 0, f"{n_mat:,} registros", critico=True)
    if n_parl == 0:
        print("\n❌ Tabelas vazias — execute Agents 0+A+B+C primeiro.")
        return

    cur.execute("""
        SELECT count(*) AS n FROM (
            SELECT dominio, id_sapl FROM sapl_parlamentares GROUP BY 1, 2 HAVING count(*) > 1
        ) t
    """)
    dups_parl = cur.fetchone()["n"]
    check("Sem duplicata (dominio,id_sapl) em parlamentares", dups_parl == 0, f"{dups_parl} duplicata(s)", critico=True)

    cur.execute("""
        SELECT count(*) AS n FROM (
            SELECT dominio, id_sapl FROM sapl_materias GROUP BY 1, 2 HAVING count(*) > 1
        ) t
    """)
    dups_mat = cur.fetchone()["n"]
    check("Sem duplicata (dominio,id_sapl) em matérias", dups_mat == 0, f"{dups_mat} duplicata(s)", critico=True)

    cur.execute("SELECT count(*) AS n FROM sapl_instancias WHERE status = 'ativo'")
    confirmadas = cur.fetchone()["n"]
    cur.execute("SELECT count(DISTINCT dominio) AS n FROM sapl_parlamentares")
    coletadas = cur.fetchone()["n"]
    pct_cobertura = round(100 * coletadas / max(confirmadas, 1), 1)
    check("Cobertura Fase 1 sobre Fase 0", coletadas > 0,
          f"{coletadas}/{confirmadas} câmara(s) confirmadas já coletadas ({pct_cobertura}%)")

    cur.execute("""
        SELECT round(100.0 * count(politico_id) / count(*), 1) AS pct
        FROM sapl_parlamentares
    """)
    pct_match = float(cur.fetchone()["pct"] or 0)
    check("% politico_id resolvido (medido, sem baseline ainda)", True, f"{pct_match}%")

    cur.execute("""
        SELECT m.municipio_ibge, mu.nome, mu.uf, count(*) AS n
        FROM sapl_materias m JOIN municipios mu ON mu.id_ibge = m.municipio_ibge
        GROUP BY 1, 2, 3 ORDER BY n DESC LIMIT 5
    """)
    print("\n  📊 Top 5 municípios por nº de matérias coletadas:")
    for r in cur.fetchall():
        print(f"     {r['nome']}/{r['uf']}: {r['n']:,} matérias")

    conn.close()

    falhas_criticas = [c for c in CHECKS if not c["passou"] and c["critico"]]
    passaram = sum(1 for c in CHECKS if c["passou"])
    print(f"\n{'='*50}")
    print(f"✅ Passaram: {passaram}/{len(CHECKS)} | ❌ Críticos: {len(falhas_criticas)}")

    if args.strict and falhas_criticas:
        print("\n❌ STRICT MODE: checks críticos falharam.")
        raise SystemExit(1)

    print("\n✅ Agent Verify concluído.")


if __name__ == "__main__":
    main()
