#!/usr/bin/env python3
# Agent C - Loader TransfereGov Convenios: Prata -> convenios_federais (UPSERT por nr_convenio)
# Execucao:
#     python agent_c_loader.py --dry-run
#     python agent_c_loader.py --prata planos_acao_especial_2024_prata.json
#     python agent_c_loader.py --todos
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch
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
PRATA_DIR = BASE_DIR / "data/transferegov_convenios/prata"

DB = dict(host="localhost", port=5432, dbname="prisma_data", user="postgres", password=DB_PASSWORD)

UPSERT_SQL = (
    "INSERT INTO convenios_federais ("
    "nr_convenio, ano, situacao, vigencia_inicio, vigencia_fim, orgao_concedente, "
    "cnpj_proponente, nome_proponente, municipio_ibge, uf, valor_global, valor_repasse, "
    "valor_contrapartida, modalidade, justificativa_resumo, emenda_codigo_associada, "
    "politico_id, parlamentar_nome, origem_fonte, executor_cnpj, executor_nome, "
    "data_assinatura, objeto"
    ") VALUES ("
    "%(nr_convenio)s, %(ano)s, %(situacao)s, %(vigencia_inicio)s, %(vigencia_fim)s, %(orgao_concedente)s, "
    "%(cnpj_proponente)s, %(nome_proponente)s, %(municipio_ibge)s, %(uf)s, %(valor_global)s, %(valor_repasse)s, "
    "%(valor_contrapartida)s, %(modalidade)s, %(justificativa_resumo)s, %(emenda_codigo_associada)s, "
    "%(politico_id)s, %(parlamentar_nome)s, %(origem_fonte)s, %(executor_cnpj)s, %(executor_nome)s, "
    "%(data_assinatura)s, %(objeto)s"
    ") ON CONFLICT (nr_convenio) DO UPDATE SET "
    "ano = EXCLUDED.ano, situacao = EXCLUDED.situacao, vigencia_inicio = EXCLUDED.vigencia_inicio, "
    "orgao_concedente = EXCLUDED.orgao_concedente, cnpj_proponente = EXCLUDED.cnpj_proponente, "
    "nome_proponente = EXCLUDED.nome_proponente, municipio_ibge = EXCLUDED.municipio_ibge, uf = EXCLUDED.uf, "
    "valor_global = EXCLUDED.valor_global, valor_repasse = EXCLUDED.valor_repasse, modalidade = EXCLUDED.modalidade, "
    "justificativa_resumo = EXCLUDED.justificativa_resumo, emenda_codigo_associada = EXCLUDED.emenda_codigo_associada, "
    "politico_id = EXCLUDED.politico_id, parlamentar_nome = EXCLUDED.parlamentar_nome, "
    "executor_cnpj = EXCLUDED.executor_cnpj, executor_nome = EXCLUDED.executor_nome, "
    "data_assinatura = EXCLUDED.data_assinatura, objeto = EXCLUDED.objeto, origem_fonte = EXCLUDED.origem_fonte"
)

CAMPOS = [
    "nr_convenio","ano","situacao","vigencia_inicio","vigencia_fim","orgao_concedente",
    "cnpj_proponente","nome_proponente","municipio_ibge","uf","valor_global","valor_repasse",
    "valor_contrapartida","modalidade","justificativa_resumo","emenda_codigo_associada",
    "politico_id","parlamentar_nome","origem_fonte","executor_cnpj","executor_nome",
    "data_assinatura","objeto",
]

def to_row(r):
    return {k: r.get(k) for k in CAMPOS}

def carregar_prata(prata_path, dry_run):
    print("[prata] " + prata_path.name)
    prata = json.loads(prata_path.read_text())
    records = prata.get("records", [])
    print("  " + str(len(records)) + " registros")
    rows = [to_row(r) for r in records]
    if dry_run:
        sem_chave = sum(1 for r in rows if not r["nr_convenio"])
        print("  [dry-run] " + str(len(rows)) + " prontos | sem_nr_convenio=" + str(sem_chave))
        return
    inicio = datetime.now(timezone.utc)
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    novos = 0; erros = 0
    BATCH = 500
    for i in range(0, len(rows), BATCH):
        lote = rows[i:i+BATCH]
        try:
            execute_batch(cur, UPSERT_SQL, lote, page_size=200)
            conn.commit(); novos += len(lote)
        except Exception as e:
            conn.rollback(); erros += len(lote)
            print("  [erro] lote " + str(i // BATCH + 1) + ": " + str(e)[:200])
    fim = datetime.now(timezone.utc); dur = (fim - inicio).total_seconds()
    try:
        cur.execute(
            "INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos, erro_mensagem, duracao_seg, iniciado_em, finalizado_em) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ("transferegov_convenios", "fase_2", "sucesso" if erros == 0 else "parcial", len(records), novos, None if erros == 0 else (str(erros) + " erros"), round(dur, 2), inicio, fim),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("  [warn] etl_log falhou: " + str(e)[:120])
    cur.close(); conn.close()
    print("  [ok] " + str(novos) + " upserts em " + str(round(dur, 1)) + "s | erros=" + str(erros))

def main():
    ap = argparse.ArgumentParser(description="Agent C - Loader TransfereGov Convenios")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prata")
    ap.add_argument("--todos", action="store_true")
    args = ap.parse_args()
    print("TransfereGov Convenios - Agent C (Loader)")
    if args.prata:
        p = Path(args.prata)
        if not p.is_absolute(): p = PRATA_DIR / p
        carregar_prata(p, args.dry_run)
    elif args.todos:
        for p in sorted(PRATA_DIR.glob("planos_acao_especial_*_prata.json")):
            carregar_prata(p, args.dry_run); print()
    else:
        ps = sorted(PRATA_DIR.glob("planos_acao_especial_*_prata.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not ps:
            print("[erro] nenhum prata encontrado"); return
        carregar_prata(ps[0], args.dry_run)
    print("[ok] Agent C concluido.")

if __name__ == "__main__":
    main()
