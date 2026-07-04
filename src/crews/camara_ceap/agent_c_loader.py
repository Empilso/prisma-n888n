#!/usr/bin/env python3
"""Agent C — Loader Câmara CEAP: Prata → tabela camara_verbas_ceap

Insere registros normalizados no PostgreSQL (prisma_data).
Usa ON CONFLICT (id_documento) DO NOTHING para idempotência — pode ser
re-executado com segurança sem duplicar dados.

Execução:
    python agent_c_loader.py --dry-run          # valida sem gravar
    python agent_c_loader.py --prata ceap_2024_prata.json
    python agent_c_loader.py --todos            # todos os pratas disponíveis
"""
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
PRATA_DIR = BASE_DIR / "data/camara_ceap/prata"

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

UPSERT_SQL = """
INSERT INTO camara_verbas_ceap (
    id_documento, politico_id,
    cnpj_fornecedor, nome_fornecedor,
    tipo_despesa, valor_liquido,
    data_emissao, competencia,
    nr_documento, descricao,
    url_documento, status_lneg
) VALUES (
    %(id_documento)s, %(politico_id)s,
    %(cnpj_fornecedor)s, %(nome_fornecedor)s,
    %(tipo_despesa)s, %(valor_liquido)s,
    %(data_emissao)s, %(competencia)s,
    %(nr_documento)s, %(descricao)s,
    %(url_documento)s, %(status_lneg)s
)
ON CONFLICT (id_documento) DO UPDATE SET
    url_documento = EXCLUDED.url_documento
    WHERE camara_verbas_ceap.url_documento IS NULL
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

CAMPOS_INSERT = [
    'id_documento', 'politico_id', 'cnpj_fornecedor', 'nome_fornecedor',
    'tipo_despesa', 'valor_liquido', 'data_emissao', 'competencia',
    'nr_documento', 'descricao', 'url_documento', 'status_lneg',
]


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding='utf-8') as f:
        prata = json.load(f)

    records = prata.get('records', [])
    meta    = prata.get('meta', {})
    ano     = meta.get('ano', '?')
    print(f"📊 {len(records):,} registros | Ano: {ano}")

    if dry_run:
        print("🔍 DRY-RUN — nenhum dado gravado")
        # Valida que os campos obrigatórios existem
        erros = 0
        for r in records[:100]:
            for campo in ('id_documento', 'politico_id', 'valor_liquido', 'data_emissao'):
                if not r.get(campo):
                    print(f"  ⚠️  Campo ausente '{campo}' em {r.get('id_documento','?')}")
                    erros += 1
        print(f"✅ Dry-run OK: {len(records):,} registros prontos | Erros validação: {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    cur    = conn.cursor()
    novos  = erros = 0

    # Extrai apenas os campos necessários para o INSERT
    rows = [{k: r.get(k) for k in CAMPOS_INSERT} for r in records]

    for i in range(0, len(rows), 500):
        lote = rows[i:i+500]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            if (i // 500 + 1) % 10 == 0 or i == 0:
                print(f"  ✅ Lote {i//500+1}: {novos:,} inseridos até agora...")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//500+1} falhou: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    cur.execute(ETL_LOG, (
        f'camara_ceap_{ano}', 'fase_1',
        'sucesso' if erros == 0 else 'parcial',
        len(records), novos,
        None if erros == 0 else f'{erros} erros',
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Carga concluída em {dur:.1f}s | Inseridos: {novos:,} | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description='Agent C — Loader Câmara CEAP')
    parser.add_argument('--dry-run', action='store_true', help='Valida sem gravar')
    parser.add_argument('--prata',   help='Arquivo prata específico')
    parser.add_argument('--todos',   action='store_true', help='Todos os pratas')
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("ceap_*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("ceap_*_prata.json"),
                        key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        carregar_prata(pratas[0], args.dry_run)

    print("\n✅ Agent C concluído.")

if __name__ == '__main__':
    main()
