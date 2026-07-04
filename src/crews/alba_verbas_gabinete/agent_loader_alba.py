#!/usr/bin/env python3
"""
Agent Loader ALBA v2 — Prata → PostgreSQL
PK: prisma_id (hash MD5 único)
Fonte: data/alba/alba_{ano}_prata.json
"""
import json, glob, argparse, psycopg2, psycopg2.extras
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


try:
    from rapidfuzz import process, fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
ALBA_DIR  = BASE_DIR / "data/alba"

DB = dict(host='localhost', port=5432, dbname='prisma_data',
          user='postgres', password=DB_PASSWORD)

MAPA_NOMES_ALBA = {
    'BIRA CORÔA LULA':       'BIRA COROA',
    'GIKA LOPES LULA':       'GIKA',
    'JACÓ LULA DA SILVA':    'JACÓ',
    'ZÉ NETO LULA':          'ZÉ NETO',
    'MARCELL DOS ANIMAIS':   'MARCELL MORAES',
    'PASTOR ISIDÓRIO FILHO': 'PASTOR SARGENTO ISIDORIO',
    'TOM É MEU AMIGO':       'PASTOR TOM',
    'ÂNGELO CORONEL':        'ANGELO CORONEL FILHO',
    'HERZEM GUSMÃO':         None,        # não encontrado no TSE BA
    'LEUR LOMANTO JÚNIOR':   None,        # não encontrado no TSE BA
    'FABRÍCIO FALCÃO':       'FABRÍCIO',
    'HASSAN':                'HASSAN DE ZÉ COCÁ',
    # Novos mapeamentos identificados em 2026-04-08
    'VANDO':                 'LAERTE DO VANDO',
    'CARLOS UBALDINO':       'PASTOR UBALDINO',
}

MAPA_IDS_DIRETOS = {
    # Deputados que mudaram de cargo — politico_id resolvido diretamente
    'LEUR LOMANTO JÚNIOR': '21fe23073e46ce47508bb9c7e79b99e04d9f610d4999d24957bb2316b670e0da',
}

UPSERT_SQL = """
INSERT INTO alba_verbas_gabinete (
    prisma_id, num_processo, politico_id, nome_deputado_raw,
    cnpj_fornecedor, cpf_fornecedor, nome_fornecedor,
    categoria, valor_pago, data_emissao, competencia,
    url_pdf, url_detalhe_alba, qualidade_score, ano, uf
) VALUES (
    %(prisma_id)s, %(num_processo)s, %(politico_id)s, %(nome_deputado_raw)s,
    %(cnpj_fornecedor)s, %(cpf_fornecedor)s, %(nome_fornecedor)s,
    %(categoria)s, %(valor_pago)s, %(data_emissao)s, %(competencia)s,
    %(url_pdf)s, %(url_detalhe_alba)s, %(qualidade_score)s, %(ano)s, %(uf)s
)
ON CONFLICT (prisma_id) DO UPDATE SET
    politico_id        = EXCLUDED.politico_id,
    nome_deputado_raw  = EXCLUDED.nome_deputado_raw,
    nome_fornecedor    = EXCLUDED.nome_fornecedor,
    valor_pago         = EXCLUDED.valor_pago,
    url_detalhe_alba   = EXCLUDED.url_detalhe_alba,
    qualidade_score    = EXCLUDED.qualidade_score;
"""

def carregar_indice_politicos(conn) -> dict:
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (politico_id) upper(nome_urna), politico_id
        FROM politicos
        WHERE uf = 'BA' AND cargo = 'DEPUTADO ESTADUAL' AND politico_id IS NOT NULL
        ORDER BY politico_id, ano_eleicao DESC
    """)
    return {r[0]: r[1] for r in cur.fetchall()}

def resolver_politico_id(nome_raw: str, idx: dict) -> str | None:
    if not nome_raw: return None
    nome_upper = nome_raw.upper().strip()
    # 1. Mapa de IDs diretos (deputados que mudaram de cargo)
    if nome_upper in MAPA_IDS_DIRETOS:
        return MAPA_IDS_DIRETOS[nome_upper]
    # 2. Mapa de nomes alternativos
    if nome_upper in MAPA_NOMES_ALBA:
        mapeado = MAPA_NOMES_ALBA[nome_upper]
        if mapeado is None: return None
        nome_upper = mapeado.upper()
    # 3. Match exato no índice
    if nome_upper in idx: return idx[nome_upper]
    # 4. Fuzzy match
    if HAS_FUZZ:
        match = process.extractOne(nome_upper, list(idx.keys()), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 75: return idx[match[0]]
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--ano', type=int)
    args = parser.parse_args()

    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()

    print("🔗 Carregando índice de deputados BA...")
    idx = carregar_indice_politicos(conn)
    print(f"   {len(idx)} deputados indexados")

    # Selecionar arquivos Prata
    if args.ano:
        arquivos = list(ALBA_DIR.glob(f"alba_{args.ano}_prata.json"))
    else:
        arquivos = sorted(ALBA_DIR.glob("alba_*_prata.json"))

    if not arquivos:
        print("❌ Nenhum arquivo Prata encontrado"); return

    inicio = datetime.now(timezone.utc)
    total_ins = total_sem = total_err = 0

    for arq in arquivos:
        print(f"\n📂 {arq.name}")
        data = json.load(open(arq))
        if isinstance(data, dict):
            data = data.get('records', data.get('dados', []))

        lote = []
        sem = err = 0

        for r in data:
            pid = r.get('prisma_id','').strip()
            if not pid: err += 1; continue

            politico_id = resolver_politico_id(r.get('deputado'), idx)
            if not politico_id: sem += 1

            lote.append({
                'prisma_id':          pid,
                'num_processo':       str(r.get('num_processo') or ''),
                'politico_id':        politico_id,
                'nome_deputado_raw':  r.get('deputado'),
                'cnpj_fornecedor':    r.get('cnpj_fornecedor'),
                'cpf_fornecedor':  r.get('cpf_fornecedor'),
                'nome_fornecedor': r.get('nome_fornecedor_limpo') or r.get('nome_fornecedor'),
                'categoria':       r.get('categoria_slug') or r.get('categoria_original'),
                'valor_pago':      float(r.get('valor') or 0),
                'data_emissao':    r.get('competencia_date'),
                'competencia':     r.get('competencia_raw'),
                'url_pdf':         r.get('url_pdf_nf'),
                'url_detalhe_alba': r.get('link_detalhe'),
                'qualidade_score': r.get('qualidade_score'),
                'ano':             r.get('competencia_ano') or r.get('ano'),
                'uf':              r.get('uf', 'BA'),
            })

            if len(lote) >= 500:
                if not args.dry_run:
                    cur.executemany(UPSERT_SQL, lote)
                    conn.commit()
                total_ins += len(lote); lote = []

        if lote:
            if not args.dry_run:
                cur.executemany(UPSERT_SQL, lote)
                conn.commit()
            total_ins += len(lote)

        total_sem += sem; total_err += err
        print(f"   ✅ {len(data)-sem-err} inseridos | ⚠️  {sem} sem politico_id | ❌ {err} sem prisma_id")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    if not args.dry_run:
        cur.execute("""
            INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                                 erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, ('alba_verbas_gabinete', 'fase_1', 'sucesso',
              total_ins, total_ins,
              f'{total_sem} sem politico_id' if total_sem else None,
              round(dur,2), inicio, fim))
        conn.commit()

    conn.close()
    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}✅ {dur:.1f}s | {total_ins} inseridos | {total_sem} sem politico_id | {total_err} erros")

if __name__ == '__main__':
    main()
