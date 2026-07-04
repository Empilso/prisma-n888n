#!/usr/bin/env python3
"""Agent C — Loader TSE Receitas: Prata → tabela receitas_campanha"""
import json, argparse, psycopg2
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
PRATA_DIR = BASE_DIR / "data/tse_receitas_campanha/prata"

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

UPSERT_SQL = """
INSERT INTO receitas_campanha (
    prisma_id, politico_id, sq_candidato,
    doador_cnpj_cpf, doador_nome, doador_nome_rfb,
    valor, data_receita, fonte_recurso, especie_recurso,
    ano_eleicao, uf, cargo, sigla_partido
) VALUES (
    %(prisma_id)s, %(politico_id)s, %(sq_candidato)s,
    %(doador_cnpj_cpf)s, %(doador_nome)s, %(doador_nome_rfb)s,
    %(valor)s, %(data_receita)s, %(fonte_recurso)s, %(especie_recurso)s,
    %(ano_eleicao)s, %(uf)s, %(cargo)s, %(sigla_partido)s
)
ON CONFLICT (prisma_id) DO NOTHING
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding='utf-8') as f:
        prata = json.load(f)

    records = prata.get('records', [])
    meta    = prata.get('meta', {})
    ano     = meta.get('ano_eleicao', '?')
    uf      = meta.get('uf', '?')
    print(f"📊 {len(records)} registros | Ano: {ano} | UF: {uf}")

    if dry_run:
        print("🔍 DRY-RUN — nenhum dado gravado")
        print(f"✅ Simulação OK: {len(records)} registros prontos")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    cur    = conn.cursor()
    novos  = erros = 0

    # Remove chave interna de debug antes de inserir
    rows = [{k: v for k, v in r.items() if not k.startswith('_')} for r in records]

    for i in range(0, len(rows), 500):
        lote = rows[i:i+500]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            print(f"  ✅ Lote {i//500+1}: {len(lote)} registros")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//500+1} falhou: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    cur.execute(ETL_LOG, (
        f'tse_receitas_campanha_{ano}_{uf}', 'fase_0',
        'sucesso' if erros == 0 else 'parcial',
        len(records), novos,
        None if erros == 0 else f'{erros} erros',
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Carga concluída em {dur:.1f}s | Inseridos: {novos} | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description='Agent C — Loader TSE Receitas')
    parser.add_argument('--dry-run', action='store_true', help='Valida sem gravar')
    parser.add_argument('--prata',   help='Arquivo prata específico (opcional)')
    parser.add_argument('--todos',   action='store_true', help='Processar todos os pratas')
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
