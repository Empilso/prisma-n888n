#!/usr/bin/env python3
"""Agent C — Loader SIGA-BA Emendas: Prata → tabela emendas_estaduais

Schema real:
  numero_emenda (PK text), politico_id, municipio_ibge (char7 FK),
  objeto, funcao, valor_empenhado, valor_liquidado, valor_pago,
  valor_autorizado, parlamentar_nome, pct_execucao,
  ano_orcamento (smallint), cnpj_favorecido, status_execucao (enum), origem_fonte

Execução:
    python agent_c_loader.py --dry-run
    python agent_c_loader.py --prata emendas_ba_2024_prata.json
    python agent_c_loader.py --todos
"""
import json, argparse, psycopg2
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
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
PRATA_DIR = BASE_DIR / "data/siga_ba_emendas/prata"

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

UPSERT_SQL = """
INSERT INTO emendas_estaduais (
    numero_emenda, politico_id, municipio_ibge, objeto, funcao,
    valor_autorizado, valor_empenhado, valor_liquidado, valor_pago,
    pct_execucao, parlamentar_nome,
    ano_orcamento, cnpj_favorecido, status_execucao, origem_fonte
) VALUES (
    %(numero_emenda)s, %(politico_id)s, %(municipio_ibge)s, %(objeto)s, %(funcao)s,
    %(valor_autorizado)s, %(valor_empenhado)s, %(valor_liquidado)s, %(valor_pago)s,
    %(pct_execucao)s, %(parlamentar_nome)s,
    %(ano_orcamento)s, %(cnpj_favorecido)s, %(status_execucao)s, %(origem_fonte)s
)
ON CONFLICT (numero_emenda) DO UPDATE SET
    valor_pago       = EXCLUDED.valor_pago,
    valor_liquidado  = EXCLUDED.valor_liquidado,
    pct_execucao     = EXCLUDED.pct_execucao,
    status_execucao  = EXCLUDED.status_execucao
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

STATUS_MAP = {
    'executado':   'executado',
    'aprovado':    'executado',
    'pago':        'executado',
    'parcial':     'parcial',
    'em execução': 'parcial',
    'em andamento':'parcial',
    'bloqueado':   'bloqueado',
    'suspenso':    'bloqueado',
    'cancelado':   'cancelado',
    'cancelada':   'cancelado',
}

def mapear_status(s: str | None) -> str | None:
    if not s:
        return None
    return STATUS_MAP.get(s.lower().strip())


def mapear_para_schema(r: dict) -> dict:
    ibge = r.get('cod_ibge_municipio') or ''
    ibge_7 = ibge[:7].zfill(7) if ibge else None

    # objeto = junta funcao + acao como descrição resumida
    partes = [p for p in [r.get('programa'), r.get('acao')] if p]
    objeto = ' | '.join(partes) if partes else r.get('funcao')

    return {
        'numero_emenda':   r.get('num_emenda') or r.get('id_emenda', '')[:50],
        'politico_id':     r.get('politico_id'),
        'municipio_ibge':  ibge_7,
        'objeto':          objeto,
        'funcao':          r.get('funcao'),
        'valor_autorizado':r.get('valor_autorizado'),
        'valor_empenhado': r.get('valor_empenhado'),
        'valor_liquidado': r.get('valor_liquidado'),
        'valor_pago':      r.get('valor_pago'),
        'pct_execucao':    r.get('pct_execucao'),
        'parlamentar_nome':r.get('parlamentar_nome'),
        'ano_orcamento':   r.get('ano_loa'),
        'cnpj_favorecido': None,
        'status_execucao': mapear_status(r.get('situacao')),
        'origem_fonte':    'SIGA-BA',
    }


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding='utf-8') as f:
        prata = json.load(f)

    records = prata.get('records', [])
    meta    = prata.get('meta', {})
    ano     = meta.get('ano', '?')
    print(f"📊 {len(records):,} registros | Ano: {ano}")

    rows = [mapear_para_schema(r) for r in records]

    if dry_run:
        erros = sum(1 for r in rows if not r.get('numero_emenda') or not r.get('ano_orcamento'))
        print(f"🔍 DRY-RUN — {len(rows):,} prontos | Erros: {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    cur    = conn.cursor()
    novos = erros = 0

    for i in range(0, len(rows), 500):
        lote = rows[i:i+500]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            if (i // 500 + 1) % 10 == 0:
                print(f"  ✅ {novos:,} upserts...")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//500+1}: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    cur.execute(ETL_LOG, (
        f'siga_ba_emendas_{ano}', 'fase_2',
        'sucesso' if erros == 0 else 'parcial',
        len(records), novos,
        None if erros == 0 else f'{erros} erros',
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {ano}: {novos:,} upserts em {dur:.1f}s | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description='Agent C — Loader SIGA-BA Emendas')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--prata',   help='Arquivo prata específico')
    parser.add_argument('--todos',   action='store_true')
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("emendas_ba_*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("emendas_ba_*_prata.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        carregar_prata(pratas[0], args.dry_run)

    print("\n✅ Agent C concluído.")

if __name__ == '__main__':
    main()
