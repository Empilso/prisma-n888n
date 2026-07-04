#!/usr/bin/env python3
"""Agent C — Loader: Prata → tabela emendas_execucao_orcamentaria

UPSERT por id_registro (UNIQUE) — idempotente, pode re-executar sem duplicar.

Schema da tabela:
    id, codigo_emenda, nome_autor_emenda, tipo_emenda, ano_mes,
    uf, municipio, municipio_ibge, cod_orgao_superior, orgao_superior,
    orgao_subordinado, unidade_gestora, funcao, subfuncao, programa,
    cod_acao, acao, plano_orcamentario, categoria_economica, grupo_despesa,
    elemento_despesa, modalidade_despesa,
    valor_empenhado, valor_liquidado, valor_pago,
    valor_resto_inscrito, valor_resto_cancelado, valor_resto_pago,
    id_registro, created_at

Execução:
    python agent_c_loader.py --dry-run
    python agent_c_loader.py --prata despesas_emendas_202501_prata.json
    python agent_c_loader.py --todos
"""
import json, argparse, psycopg2, psycopg2.extras
from pathlib import Path
from datetime import datetime, timezone
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/cgu_docs_emendas/prata"

DB = dict(host="localhost", port=5432, dbname="prisma_data",
          user="postgres", password=DB_PASSWORD)

UPSERT_SQL = """
INSERT INTO emendas_execucao_orcamentaria (
    codigo_emenda, nome_autor_emenda, tipo_emenda, ano_mes,
    uf, municipio, municipio_ibge,
    cod_orgao_superior, orgao_superior, orgao_subordinado, unidade_gestora,
    funcao, subfuncao, programa, cod_acao, acao, plano_orcamentario,
    categoria_economica, grupo_despesa, elemento_despesa, modalidade_despesa,
    valor_empenhado, valor_liquidado, valor_pago,
    valor_resto_inscrito, valor_resto_cancelado, valor_resto_pago,
    id_registro
) VALUES (
    %(codigo_emenda)s, %(nome_autor_emenda)s, %(tipo_emenda)s, %(ano_mes)s,
    %(uf)s, %(municipio)s, %(municipio_ibge)s,
    %(cod_orgao_superior)s, %(orgao_superior)s, %(orgao_subordinado)s, %(unidade_gestora)s,
    %(funcao)s, %(subfuncao)s, %(programa)s, %(cod_acao)s, %(acao)s, %(plano_orcamentario)s,
    %(categoria_economica)s, %(grupo_despesa)s, %(elemento_despesa)s, %(modalidade_despesa)s,
    %(valor_empenhado)s, %(valor_liquidado)s, %(valor_pago)s,
    %(valor_resto_inscrito)s, %(valor_resto_cancelado)s, %(valor_resto_pago)s,
    %(id_registro)s
)
ON CONFLICT (id_registro) DO UPDATE SET
    valor_empenhado        = EXCLUDED.valor_empenhado,
    valor_liquidado        = EXCLUDED.valor_liquidado,
    valor_pago             = EXCLUDED.valor_pago,
    valor_resto_inscrito   = EXCLUDED.valor_resto_inscrito,
    valor_resto_cancelado  = EXCLUDED.valor_resto_cancelado,
    valor_resto_pago       = EXCLUDED.valor_resto_pago,
    municipio_ibge         = COALESCE(EXCLUDED.municipio_ibge, emendas_execucao_orcamentaria.municipio_ibge)
"""

ETL_LOG_SQL = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""

LOTE = 500


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 {prata_path.name}")
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    records = prata.get("records", [])
    meta    = prata.get("meta", {})
    print(f"  📊 {len(records):,} registros | {meta.get('pct_municipio_ibge', '?')}% com IBGE")

    if dry_run:
        sem_id = sum(1 for r in records if not r.get("id_registro"))
        sem_cod = sum(1 for r in records if not r.get("codigo_emenda"))
        print(f"  🔍 DRY-RUN: {len(records):,} prontos | sem id_registro: {sem_id} | sem codigo: {sem_cod}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    cur    = conn.cursor()
    inseridos = atualizados = erros = 0

    for i in range(0, len(records), LOTE):
        lote = records[i:i + LOTE]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            inseridos += len(lote)
            if (i // LOTE + 1) % 20 == 0:
                print(f"  ⏳ {inseridos:,} processados...")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i // LOTE + 1}: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    ano_mes = meta.get("ano_mes", "?")
    cur.execute(ETL_LOG_SQL, (
        f"cgu_docs_emendas_{ano_mes}", "fase_2",
        "sucesso" if erros == 0 else "parcial",
        len(records), inseridos,
        None if erros == 0 else f"{erros} erros",
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"  ✅ {inseridos:,} upserts em {dur:.1f}s | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader Despesas de Emendas")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prata",   help="Arquivo prata específico")
    parser.add_argument("--todos",   action="store_true")
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("despesas_emendas_*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado. Execute Agent B primeiro.")
            return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        parser.print_help()
        return

    print("\n✅ Agent C concluído.")


if __name__ == "__main__":
    main()
