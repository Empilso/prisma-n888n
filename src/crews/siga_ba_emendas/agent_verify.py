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
    # fix 2026-07-12: colunas reais da tabela são ano_orcamento/municipio_ibge/
    # numero_emenda — o verify antigo usava os nomes da Prata (ano_loa etc.)
    # e por isso NUNCA certificou o schema carregado (auditoria QI Codex)
    cur.execute("SELECT COUNT(DISTINCT ano_orcamento) FROM emendas_estaduais")
    anos = cur.fetchone()[0]
    ok = anos >= 3
    cur.execute("SELECT DISTINCT ano_orcamento FROM emendas_estaduais ORDER BY ano_orcamento")
    lista = [r[0] for r in cur.fetchall()]
    return ok, f"{anos} anos: {lista}", not ok

@check("VALOR_PAGO", "≥ 90% com valor_pago > 0")
def c3(cur, strict):
    # valor_pago é o ÚNICO valor real da fonte (view CKAN só publica pagamentos);
    # autorizado/empenhado/liquidado são NULL honesto desde 2026-07-12
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia", strict
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais WHERE valor_pago > 0")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 90
    return ok, f"{pct:.1f}% com valor_pago > 0 ({com:,}/{total:,})", not ok

@check("MUNICIPIO_PREENCHIDO", "≥ 60% com municipio_ibge (esperado FALHAR até Fase 2 — CKAN não publica)")
def c4(cur, strict):
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais")
    total = cur.fetchone()[0]
    if total == 0:
        return False, "tabela vazia", strict
    cur.execute("SELECT COUNT(*) FROM emendas_estaduais WHERE municipio_ibge IS NOT NULL")
    com = cur.fetchone()[0]
    pct = com / total * 100
    ok = pct >= 60
    return ok, f"{pct:.1f}% com municipio ({com:,}/{total:,})", not ok

@check("SEM_DUPLICATAS", "Nenhum numero_emenda+ano duplicado")
def c5(cur, strict):
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT numero_emenda, ano_orcamento FROM emendas_estaduais
            GROUP BY numero_emenda, ano_orcamento HAVING COUNT(*) > 1
        ) t
    """)
    dups = cur.fetchone()[0]
    ok = dups == 0
    return ok, f"{dups} chaves duplicadas", not ok and strict

@check("CHAVE_COMPOSTA", "PK protege numero_emenda+ano_orcamento")
def c5b(cur, strict):
    cur.execute("""
        SELECT COALESCE(array_agg(a.attname ORDER BY k.ord), ARRAY[]::name[])
        FROM pg_constraint c
        CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.conrelid = 'emendas_estaduais'::regclass
          AND c.contype = 'p'
    """)
    cols = list(cur.fetchone()[0] or [])
    ok = cols == ['numero_emenda', 'ano_orcamento']
    return ok, f"PK atual: {cols}", not ok

@check("VALOR_TOTAL_RAZOAVEL", "Total pago > R$ 100k")
def c6(cur, strict):
    cur.execute("SELECT COALESCE(SUM(valor_pago), 0) FROM emendas_estaduais")
    total = float(cur.fetchone()[0])
    ok = total > 100_000
    return ok, f"R$ {total:,.2f} total pago", not ok

@check("VALORES_NAO_FORJADOS", "autorizado/empenhado/liquidado não podem ser cópia de pago")
def c6b(cur, strict):
    # regressão do bug corrigido em 2026-07-12: Agent B copiava valor_pago 4×
    # e o banco exibia pct_execucao=100% falso em 15.555/15.557 registros
    cur.execute("""
        SELECT COUNT(*) FROM emendas_estaduais
        WHERE valor_autorizado IS NOT NULL
          AND valor_autorizado = valor_empenhado
          AND valor_empenhado = valor_liquidado
          AND valor_liquidado = valor_pago
    """)
    forjados = cur.fetchone()[0]
    ok = forjados == 0
    return ok, f"{forjados:,} registros com os 4 valores idênticos", not ok

@check("ATRIBUICAO_SO_COM_AUTOR_REAL", "politico_id só pode existir junto com parlamentar_nome")
def c6c(cur, strict):
    # guarda de dado sensível: nunca atribuir emenda a político sem autor da fonte
    cur.execute("""
        SELECT COUNT(*) FROM emendas_estaduais
        WHERE politico_id IS NOT NULL AND parlamentar_nome IS NULL
    """)
    ruins = cur.fetchone()[0]
    ok = ruins == 0
    return ok, f"{ruins:,} atribuições sem autor de origem", not ok and strict

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
