#!/usr/bin/env python3
"""Agent B — Normalizador TSE Receitas: Bronze → Prata"""
import json, re, argparse, hashlib, psycopg2
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
    from pydantic import BaseModel, field_validator
    from typing import Optional
    from datetime import date as Date
except ImportError:
    print("❌ Instale pydantic: pip install pydantic"); raise

try:
    from rapidfuzz import process, fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/tse_receitas_campanha"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)


class ReceitaCampanha(BaseModel):
    prisma_id:       str
    politico_id:     Optional[str] = None
    sq_candidato:    str
    doador_cnpj_cpf: Optional[str] = None
    doador_nome:     Optional[str] = None
    doador_nome_rfb: Optional[str] = None
    valor:           Decimal
    data_receita:    Date
    fonte_recurso:   Optional[str] = None
    especie_recurso: Optional[str] = None
    ano_eleicao:     int
    uf:              str
    cargo:           Optional[str] = None
    sigla_partido:   Optional[str] = None

    @field_validator('valor')
    @classmethod
    def valor_valido(cls, v):
        if v < 0:
            raise ValueError('valor não pode ser negativo')
        return v

    @field_validator('ano_eleicao')
    @classmethod
    def ano_valido(cls, v):
        if not (2006 <= v <= 2026):
            raise ValueError(f'ano_eleicao inválido: {v}')
        return v


def carregar_indice_politicos(ano: int, uf: str) -> dict:
    """Carrega índice cpf→politico_id e sq_candidato→politico_id do banco.
    Busca por UF sem filtrar por ano — candidatos podem estar em anos diferentes.
    UF='BR' (arquivo nacional) busca sem filtro de UF, pois sq_candidato é único por eleição."""
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    if uf == 'BR':
        # Candidatos do arquivo nacional: sem filtro de UF
        cur.execute("""
            SELECT DISTINCT ON (sq_candidato) cpf, sq_candidato, politico_id, nome_urna
            FROM politicos
            WHERE politico_id IS NOT NULL
            ORDER BY sq_candidato, ABS(ano_eleicao - %s)
        """, (ano,))
    else:
        # Prioriza o registro do mesmo ano, mas aceita qualquer ano da mesma UF
        cur.execute("""
            SELECT DISTINCT ON (sq_candidato) cpf, sq_candidato, politico_id, nome_urna
            FROM politicos
            WHERE uf = %s AND politico_id IS NOT NULL
            ORDER BY sq_candidato, ABS(ano_eleicao - %s)
        """, (uf, ano))
    rows = cur.fetchall()
    conn.close()
    idx_cpf  = {r[0]: r[2] for r in rows if r[0]}
    idx_sq   = {r[1]: r[2] for r in rows if r[1]}
    idx_nome = {r[3].upper(): r[2] for r in rows if r[3]}
    return idx_cpf, idx_sq, idx_nome


def resolver_politico_id(cpf_cand: str, sq_cand: str, nome_cand: str,
                          idx_cpf: dict, idx_sq: dict, idx_nome: dict) -> tuple[str | None, str]:
    if cpf_cand and cpf_cand in idx_cpf:
        return idx_cpf[cpf_cand], 'cpf'
    if sq_cand and sq_cand in idx_sq:
        return idx_sq[sq_cand], 'sq_candidato'
    if HAS_FUZZ and nome_cand and idx_nome:
        match = process.extractOne(nome_cand.upper(), list(idx_nome.keys()),
                                   scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 85:
            return idx_nome[match[0]], f'fuzzy:{match[1]}'
    return None, 'sem_match'


def limpar(v) -> str | None:
    if not v: return None
    s = str(v).strip()
    return None if s in ('#NULO', '#NE', '-1', '-3', '-4', '', '#NULL!') else s


def parse_valor(v) -> Decimal | None:
    v = limpar(v)
    if not v: return None
    try:
        val = Decimal(v.replace('.', '').replace(',', '.'))
        return val if val >= 0 else None  # aceita zero, rejeita negativos
    except InvalidOperation:
        return None


def parse_date(v) -> Date | None:
    v = limpar(v)
    if not v: return None
    try:
        # 2014: "16/09/201400:00:00" (timestamp colado)
        # 2024: "27/09/2024"
        v = v.split()[0] if ' ' in v else v  # remove hora se separada
        v = v[:10] if len(v) > 10 else v     # corta timestamp colado
        d, m, a = v.split('/')
        d, m, a = int(d), int(m), int(a)
        if not (1 <= m <= 12 and 1 <= d <= 31 and 1900 <= a <= 2100):
            return None
        return Date(a, m, d)
    except Exception:
        return None


def normalizar_doc(v) -> str | None:
    v = limpar(v)
    if not v: return None
    digits = re.sub(r'\D', '', v)
    if len(digits) in (11, 14):
        return digits
    return None


def col(row: dict, *nomes) -> str:
    for n in nomes:
        if n in row and str(row[n]).strip():
            return str(row[n]).strip()
    return ''


def processar_bronze(bronze_path: Path) -> None:
    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding='utf-8') as f:
        bronze = json.load(f)

    meta    = bronze.get('meta', {})
    ano     = int(meta.get('ano_eleicao', 0))
    uf      = meta.get('uf', '')
    records = bronze.get('records', [])
    print(f"📊 Total bruto: {len(records)}")

    print(f"🔗 Carregando índice politicos ({ano}/{uf})...")
    try:
        idx_cpf, idx_sq, idx_nome = carregar_indice_politicos(ano, uf)
        print(f"   {len(idx_cpf)} por CPF | {len(idx_sq)} por SQ | {len(idx_nome)} por nome")
    except Exception as e:
        print(f"  ⚠️  Banco indisponível, politico_id será None: {e}")
        idx_cpf, idx_sq, idx_nome = {}, {}, {}

    validos, rejeitados = [], []
    for r in records:
        # Mapeamento 2014-2024: colunas modernas primeiro, depois antigas
        sq_cand    = col(r, 'SQ_CANDIDATO', 'Sequencial Candidato')
        cpf_cand   = re.sub(r'\D', '', col(r, 'NR_CPF_CANDIDATO', 'CPF do candidato'))
        cpf_cand   = cpf_cand if len(cpf_cand) == 11 else None
        nome_cand  = col(r, 'NM_CANDIDATO', 'Nome candidato')
        valor      = parse_valor(col(r, 'VR_RECEITA', 'Valor receita'))
        data_rec   = parse_date(col(r, 'DT_RECEITA', 'Data da receita'))
        ano_el_raw = col(r, 'AA_ELEICAO', 'ANO_ELEICAO')
        ano_el     = int(ano_el_raw) if ano_el_raw.isdigit() else ano

        if not data_rec or not sq_cand:
            motivo = ('data_receita inválida' if not data_rec else 'sq_candidato vazio')
            rejeitados.append({**r, 'motivo_rejeicao': motivo})
            continue
        
        # Aceita valor None (será 0) ou valor >= 0
        if valor is None:
            valor = Decimal('0')

        politico_id, metodo = resolver_politico_id(
            cpf_cand, sq_cand, nome_cand, idx_cpf, idx_sq, idx_nome)

        doador_doc = normalizar_doc(col(r, 'NR_CPF_CNPJ_DOADOR', 'CPF/CNPJ do doador'))
        fonte = limpar(col(r, 'DS_FONTE_RECEITA', 'Fonte recurso')) or ''
        especie = limpar(col(r, 'DS_ESPECIE_RECEITA', 'Especie recurso')) or ''

        # prisma_id determinístico — inclui fonte e espécie para diferenciar receitas múltiplas
        prisma_id = hashlib.md5(
            f"{sq_cand}_{doador_doc}_{valor}_{data_rec}_{fonte}_{especie}".encode()
        ).hexdigest()

        norm = {
            'prisma_id':       prisma_id,
            'politico_id':     politico_id,
            'sq_candidato':    sq_cand,
            'doador_cnpj_cpf': doador_doc,
            'doador_nome':     limpar(col(r, 'NM_DOADOR', 'Nome do doador')),
            'doador_nome_rfb': limpar(col(r, 'NM_DOADOR_RFB', 'Nome do doador (Receita Federal)')),
            'valor':           str(valor),
            'data_receita':    str(data_rec),
            'fonte_recurso':   limpar(col(r, 'DS_FONTE_RECEITA', 'Fonte recurso')),
            'especie_recurso': limpar(col(r, 'DS_ESPECIE_RECEITA', 'Especie recurso')),
            'ano_eleicao':     ano_el,
            'uf':              uf,
            'cargo':           limpar(col(r, 'DS_CARGO', 'Cargo')),
            'sigla_partido':   limpar(col(r, 'SG_PARTIDO', 'Sigla  Partido')),
            '_match_metodo':   metodo,
        }

        try:
            ReceitaCampanha(**{k: v for k, v in norm.items() if not k.startswith('_')})
            validos.append(norm)
        except Exception as e:
            rejeitados.append({**norm, 'motivo_rejeicao': str(e)})

    stem = bronze_path.stem.replace('_bronze', '')
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'data_processamento': datetime.now(timezone.utc).isoformat(),
                'fonte_bronze':       bronze_path.name,
                'ano_eleicao':        ano,
                'uf':                 uf,
                'total_validos':      len(validos),
                'total_rejeitados':   len(rejeitados),
                'sem_politico_id':    sum(1 for v in validos if not v['politico_id']),
            },
            'records': validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, 'w', encoding='utf-8') as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    sem_pid = sum(1 for v in validos if not v['politico_id'])
    print(f"✅ Prata: {len(validos)} válidos → {prata_path.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados)}")
    print(f"🔗 Sem politico_id: {sem_pid} ({sem_pid/max(len(validos),1)*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description='Agent B — Normalizador TSE Receitas')
    parser.add_argument('--bronze', help='Arquivo bronze específico (opcional)')
    parser.add_argument('--todos',  action='store_true', help='Processar todos os bronzes')
    args = parser.parse_args()

    if args.bronze:
        processar_bronze(Path(args.bronze))
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("*_bronze.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0])

    print("\n✅ Agent B concluído.")

if __name__ == '__main__':
    main()
