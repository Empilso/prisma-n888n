#!/usr/bin/env python3
"""Agent C — Loader CGU Lista Negra: Prata → tabela lista_negra_governo

Usa id_registro (UNIQUE) para idempotência — pode re-executar sem duplicar.

Schema real da tabela:
  id (bigint PK autoincrement), cnpj, razao_social, cpf_sancionado,
  nome_sancionado, tipo_punicao, data_inicio, data_fim, orgao_sancionador,
  fundamento_legal, origem (CEIS/CNEP/CEPIM), ativo (bool), id_registro (UNIQUE)

Execução:
    python agent_c_loader.py --dry-run
    python agent_c_loader.py --prata ceis_20260101_prata.json
    python agent_c_loader.py --todos
"""
import json, argparse, psycopg2
from pathlib import Path
from datetime import datetime, timezone, date
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
PRATA_DIR = BASE_DIR / "data/cgu_lista_negra/prata"

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

INSERT_SQL = """
INSERT INTO lista_negra_governo (
    cnpj, razao_social, cpf_sancionado, nome_sancionado,
    tipo_punicao, data_inicio, data_fim, orgao_sancionador,
    fundamento_legal, origem, ativo, id_registro
) VALUES (
    %(cnpj)s, %(razao_social)s, %(cpf_sancionado)s, %(nome_sancionado)s,
    %(tipo_punicao)s, %(data_inicio)s, %(data_fim)s, %(orgao_sancionador)s,
    %(fundamento_legal)s, %(origem)s, %(ativo)s, %(id_registro)s
)
ON CONFLICT (id_registro) DO NOTHING
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def is_ativo(data_fim_iso: str | None) -> bool:
    if not data_fim_iso:
        return True
    try:
        d = date.fromisoformat(data_fim_iso)
        return d >= date.today()
    except Exception:
        return True


def mapear_para_schema(r: dict) -> dict:
    """Converte do schema da prata para o schema real da tabela."""
    cnpj_cpf    = r.get('cnpj_cpf') or ''
    tipo_pessoa = r.get('tipo_pessoa') or ''
    nome        = r.get('nome_sancionado') or ''

    is_pj = tipo_pessoa == 'PJ' or (len(cnpj_cpf) == 14)
    is_pf = tipo_pessoa == 'PF' or (len(cnpj_cpf) == 11)

    return {
        'cnpj':             cnpj_cpf if is_pj else None,
        'razao_social':     nome if is_pj else None,
        'cpf_sancionado':   cnpj_cpf if is_pf else None,
        'nome_sancionado':  nome if is_pf else nome,
        'tipo_punicao':     r.get('tipo_sancao'),
        'data_inicio':      r.get('data_inicio'),
        'data_fim':         r.get('data_fim'),
        'orgao_sancionador':r.get('orgao_sancionador'),
        'fundamento_legal': r.get('fundamentacao_legal'),
        'origem':           r.get('fonte'),
        'ativo':            is_ativo(r.get('data_fim')),
        'id_registro':      r.get('id_registro'),
    }


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding='utf-8') as f:
        prata = json.load(f)

    records = prata.get('records', [])
    meta    = prata.get('meta', {})
    fonte   = meta.get('fonte', '?')
    print(f"📊 {len(records):,} registros | Fonte: {fonte}")

    rows = [mapear_para_schema(r) for r in records]

    if dry_run:
        erros = 0
        for r in rows[:200]:
            if not r.get('id_registro'):
                erros += 1
            if not r.get('cnpj') and not r.get('cpf_sancionado') and not r.get('nome_sancionado'):
                erros += 1
        print(f"🔍 DRY-RUN — {len(rows):,} prontos | Erros validação: {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    cur    = conn.cursor()
    novos = erros = 0

    for i in range(0, len(rows), 500):
        lote = rows[i:i+500]
        try:
            cur.executemany(INSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            if (i // 500 + 1) % 20 == 0:
                print(f"  ✅ {novos:,} inseridos...")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//500+1}: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    cur.execute(ETL_LOG, (
        f'cgu_lista_negra_{fonte}', 'fase_3',
        'sucesso' if erros == 0 else 'parcial',
        len(records), novos,
        None if erros == 0 else f'{erros} erros',
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ {fonte}: {novos:,} inseridos em {dur:.1f}s | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description='Agent C — Loader CGU Lista Negra')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--prata',   help='Arquivo prata específico')
    parser.add_argument('--todos',   action='store_true')
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("*_prata.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        carregar_prata(pratas[0], args.dry_run)

    print("\n✅ Agent C concluído.")

if __name__ == '__main__':
    main()
