#!/usr/bin/env python3
"""Agent V — Quality Gate ALMT/SIGCON Emendas MT

Execução:
    python agent_verify.py
    python agent_verify.py --strict
"""
import argparse
import os
from datetime import datetime

import psycopg2

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

CHECKS = []


def check(nome, desc):
    def dec(fn):
        CHECKS.append((nome, desc, fn))
        return fn
    return dec


@check("VOLUME_MINIMO", "≥ 50 emendas agregadas em emendas_estaduais (uf=MT)")
def c1(cur, strict):
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais WHERE uf = 'MT'")
    total = cur.fetchone()[0]
    ok = total >= 50
    return ok, f"{total:,} emendas", not ok and strict


@check("APLICACOES_VOLUME", "≥ 100 aplicações granulares (emendas_estaduais_aplicacoes)")
def c2(cur, strict):
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais_aplicacoes WHERE uf = 'MT'")
    total = cur.fetchone()[0]
    ok = total >= 100
    return ok, f"{total:,} aplicações", not ok and strict


@check("ANOS_COBERTOS", "≥ 2 anos distintos carregados")
def c3(cur, strict):
    cur.execute("SELECT COUNT(DISTINCT ano_orcamento) FROM emendas_estaduais WHERE uf = 'MT'")
    anos = cur.fetchone()[0]
    cur.execute("SELECT DISTINCT ano_orcamento FROM emendas_estaduais WHERE uf = 'MT' ORDER BY 1")
    lista = [r[0] for r in cur.fetchall()]
    ok = anos >= 2
    return ok, f"{anos} anos: {lista}", not ok


@check("SEM_DUPLICATAS_PK", "PK (uf,numero_emenda,ano_orcamento) sem duplicata")
def c4(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT uf, numero_emenda, ano_orcamento FROM emendas_estaduais
            WHERE uf = 'MT' GROUP BY 1,2,3 HAVING COUNT(*) > 1
        ) t
    """)
    dups = cur.fetchone()[0]
    ok = dups == 0
    return ok, f"{dups} chaves duplicadas", not ok and strict


@check("VALOR_PAGO", "≥ 90% das emendas com valor_pago > 0")
def c5(cur, strict):
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais WHERE uf = 'MT'")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia (uf=MT)", strict
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais WHERE uf = 'MT' AND valor_pago > 0")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 90
    return ok, f"{pct:.1f}% com valor_pago > 0 ({com:,}/{total:,})", not ok


@check("ATRIBUICAO_SO_COM_AUTOR_REAL", "politico_id só existe junto com parlamentar_nome")
def c6(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM emendas_estaduais
        WHERE uf = 'MT' AND politico_id IS NOT NULL AND parlamentar_nome IS NULL
    """)
    ruins = cur.fetchone()[0]
    ok = ruins == 0
    return ok, f"{ruins:,} atribuições sem autor de origem", not ok and strict


@check("MATCH_POLITICO_ID", "≥ 50% das emendas individuais (excl. Lideranças/Comissão) com politico_id")
def c7(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM emendas_estaduais
        WHERE uf = 'MT' AND parlamentar_nome NOT IN ('Lideranças Partidárias', 'Comissão de Fiscalização')
    """)
    total = cur.fetchone()[0]
    if total == 0:
        return False, "sem emendas individuais", strict
    cur.execute("""
        SELECT COUNT(*) FROM emendas_estaduais
        WHERE uf = 'MT' AND politico_id IS NOT NULL
          AND parlamentar_nome NOT IN ('Lideranças Partidárias', 'Comissão de Fiscalização')
    """)
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 50
    return ok, f"{pct:.1f}% com politico_id ({com:,}/{total:,})", not ok


@check("SOMA_APLICACOES_BATE_COM_AGREGADO", "soma de valor_utilizado por emenda == valor_pago agregado (tolerância R$1)")
def c8(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT a.uf, a.numero_emenda, a.ano_orcamento,
                   SUM(ap.valor_utilizado) AS soma_apl, a.valor_pago
            FROM emendas_estaduais a
            JOIN emendas_estaduais_aplicacoes ap
              ON ap.uf = a.uf AND ap.numero_emenda = a.numero_emenda AND ap.ano_orcamento = a.ano_orcamento
            WHERE a.uf = 'MT'
            GROUP BY a.uf, a.numero_emenda, a.ano_orcamento, a.valor_pago
            HAVING ABS(SUM(ap.valor_utilizado) - a.valor_pago) > 1
        ) t
    """)
    divergentes = cur.fetchone()[0]
    ok = divergentes == 0
    return ok, f"{divergentes:,} emendas com soma divergente do agregado", not ok and strict


@check("PARLAMENTARES_DISTINTOS", "≥ 10 parlamentares distintos")
def c9(cur, strict):
    cur.execute("""
        SELECT COUNT(DISTINCT parlamentar_nome) FROM emendas_estaduais
        WHERE uf = 'MT' AND parlamentar_nome IS NOT NULL
    """)
    count = cur.fetchone()[0]
    ok = count >= 10
    return ok, f"{count} parlamentares distintos", not ok


@check("MUNICIPIO_FK_VALIDO", "municipio_ibge preenchido só referencia UF=MT")
def c10(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM emendas_estaduais_aplicacoes ap
        JOIN municipios m ON m.id_ibge = ap.municipio_ibge
        WHERE ap.uf = 'MT' AND m.uf != 'MT'
    """)
    ruins = cur.fetchone()[0]
    ok = ruins == 0
    return ok, f"{ruins:,} aplicações com município fora de MT", not ok and strict


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent V — Quality Gate ALMT/SIGCON Emendas MT")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    print(f"🔍 Quality Gate — emendas_estaduais (uf=MT) | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

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


if __name__ == "__main__":
    main()
