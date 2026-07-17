#!/usr/bin/env python3
"""Agent V — Vigia TSE Bens Declarados: gates de sanidade pós-carga.

Roda DEPOIS do Agent C. Não escreve nada — só mede e reporta. Sai com
exit code 1 se qualquer gate obrigatório falhar (uso em cron/CI)."""
import argparse, os, psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

# Gates conforme .context/PLANO_ENRIQUECIMENTO_DADOS_2026-07-12.md item 1.3
VOLUME_MINIMO_ESPERADO = 1_000_000
ANOS_MINIMOS_COBERTOS  = 5
PCT_MINIMO_COM_POLITICO_ID = 95.0
VALOR_MAXIMO_SANIDADE = 10_000_000_000  # R$ 10 bi


def gate(nome: str, ok: bool, detalhe: str) -> bool:
    icone = "✅" if ok else "❌"
    print(f"{icone} {nome}: {detalhe}")
    return ok


def main():
    parser = argparse.ArgumentParser(description='Agent V — Vigia TSE Bens Declarados')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    resultados = []

    cur.execute("SELECT count(*) FROM bens_declarados")
    total = cur.fetchone()[0]
    resultados.append(gate(
        "VOLUME_MINIMO", total >= VOLUME_MINIMO_ESPERADO,
        f"{total:,} registros (esperado >= {VOLUME_MINIMO_ESPERADO:,})"
    ))

    cur.execute("SELECT count(DISTINCT ano_eleicao) FROM bens_declarados")
    anos = cur.fetchone()[0]
    resultados.append(gate(
        "ANOS_COBERTOS", anos >= ANOS_MINIMOS_COBERTOS,
        f"{anos} anos distintos (esperado >= {ANOS_MINIMOS_COBERTOS})"
    ))

    cur.execute("""
        SELECT count(*) FILTER (WHERE politico_id IS NOT NULL) * 100.0 / NULLIF(count(*), 0)
        FROM bens_declarados
    """)
    pct_pid = cur.fetchone()[0] or 0
    resultados.append(gate(
        "PCT_COM_POLITICO_ID", pct_pid >= PCT_MINIMO_COM_POLITICO_ID,
        f"{pct_pid:.1f}% (esperado >= {PCT_MINIMO_COM_POLITICO_ID}%)"
    ))

    cur.execute("SELECT count(*) FROM bens_declarados WHERE valor < 0")
    negativos = cur.fetchone()[0]
    resultados.append(gate(
        "VALOR_POSITIVO", negativos == 0,
        f"{negativos} valores negativos (esperado 0)"
    ))

    cur.execute("""
        SELECT sq_candidato, ano_eleicao, nr_ordem, count(*)
        FROM bens_declarados
        GROUP BY sq_candidato, ano_eleicao, nr_ordem
        HAVING count(*) > 1
        LIMIT 1
    """)
    dup = cur.fetchone()
    resultados.append(gate(
        "SEM_DUPLICATAS", dup is None,
        "0 duplicatas na chave natural" if dup is None else f"duplicata encontrada: {dup}"
    ))

    cur.execute("SELECT count(*) FROM bens_declarados WHERE valor > %s", (VALOR_MAXIMO_SANIDADE,))
    absurdos = cur.fetchone()[0]
    resultados.append(gate(
        "SANIDADE_VALOR", absurdos == 0,
        f"{absurdos} bens > R$ 10bi (possível erro de vírgula, esperado 0)"
    ))

    cur.close()
    conn.close()

    if all(resultados):
        print("\n✅ Agent V: TODOS OS GATES PASSARAM")
        return 0
    else:
        falhas = sum(1 for r in resultados if not r)
        print(f"\n❌ Agent V: {falhas} gate(s) falharam")
        return 1

if __name__ == '__main__':
    exit(main())
