#!/usr/bin/env python3
"""Agent C — Loader TSE Bens Declarados: Prata → tabela bens_declarados

Resolve politico_id/pessoa_id em SQL puro, set-based, por sq_candidato+ano
(chave exata da candidatura — join determinístico, sem fuzzy). NUNCA cruza
CPFs em quarentena (cpf_contestado) porque o join nem passa por CPF."""
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
PRATA_DIR = BASE_DIR / "data/tse_bens_declarados/prata"

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

UPSERT_SQL = """
INSERT INTO bens_declarados (
    sq_candidato, ano_eleicao, uf, nr_ordem,
    tipo_bem_cod, tipo_bem, descricao, valor
) VALUES (
    %(sq_candidato)s, %(ano_eleicao)s, %(uf)s, %(nr_ordem)s,
    %(tipo_bem_cod)s, %(tipo_bem)s, %(descricao)s, %(valor)s
)
ON CONFLICT (sq_candidato, ano_eleicao, nr_ordem, uf)
DO UPDATE SET valor = EXCLUDED.valor, descricao = EXCLUDED.descricao,
              tipo_bem = EXCLUDED.tipo_bem, tipo_bem_cod = EXCLUDED.tipo_bem_cod
"""

RESOLVE_IDENTIDADE_SQL = """
UPDATE bens_declarados b SET politico_id = p.politico_id, pessoa_id = p.pessoa_id
FROM politicos p
WHERE p.sq_candidato = b.sq_candidato AND p.ano_eleicao = b.ano_eleicao
  AND p.uf = b.uf
  AND b.politico_id IS NULL
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def carregar_prata(prata_path: Path, dry_run: bool) -> int:
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
        return 0

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    cur    = conn.cursor()
    novos  = erros = 0

    rows = [{k: v for k, v in r.items() if k != 'prisma_id'} for r in records]

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
        f'tse_bens_declarados_{ano}_{uf}', 'fase_0',
        'sucesso' if erros == 0 else 'parcial',
        len(records), novos,
        None if erros == 0 else f'{erros} erros',
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Carga concluída em {dur:.1f}s | Inseridos/atualizados: {novos} | Erros: {erros}")
    return novos


def resolver_identidade(dry_run: bool) -> None:
    if dry_run:
        print("🔍 DRY-RUN — resolução de identidade não executada")
        return
    print("\n🔗 Resolvendo politico_id/pessoa_id (set-based, sq_candidato+ano)...")
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    cur.execute(RESOLVE_IDENTIDADE_SQL)
    afetados = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {afetados} linhas com politico_id/pessoa_id resolvidos")


def main():
    parser = argparse.ArgumentParser(description='Agent C — Loader TSE Bens Declarados')
    parser.add_argument('--dry-run', action='store_true', help='Valida sem gravar')
    parser.add_argument('--prata',   help='Arquivo prata específico (opcional)')
    parser.add_argument('--todos',   action='store_true', help='Processar todos os pratas')
    args = parser.parse_args()

    total_novos = 0
    if args.prata:
        total_novos += carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        for p in pratas:
            total_novos += carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("*_prata.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        total_novos += carregar_prata(pratas[0], args.dry_run)

    if total_novos > 0 or args.todos:
        resolver_identidade(args.dry_run)

    print("\n✅ Agent C concluído.")

if __name__ == '__main__':
    main()
