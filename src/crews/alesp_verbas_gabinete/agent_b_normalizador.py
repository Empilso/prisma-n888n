#!/usr/bin/env python3
"""Agent B — Normalizador ALESP Verbas: Bronze → Prata

Mapeia os campos do XML da ALESP para o schema de alesp_verbas_gabinete.
Tenta vincular deputados ao politico_id via fuzzy match de nome contra
politicos.nome_urna (SP, DEPUTADO ESTADUAL) no banco.

id (PK) = SHA256(matricula + competencia + cnpj + valor)

Rejeições:
  - Valor ausente ou <= 0
  - Matrícula ausente
  - Ano/Mês inválido

Saída:
    data/alesp_verbas_gabinete/prata/alesp_verbas_prata.json
    data/alesp_verbas_gabinete/rejeitados/alesp_verbas_rejeitados.json
"""
import json, re, argparse, hashlib, psycopg2
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

try:
    from rapidfuzz import process, fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/alesp_verbas_gabinete"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

BRONZE_PATH = BRONZE_DIR / "alesp_verbas_bronze.json"
PRATA_PATH  = PRATA_DIR  / "alesp_verbas_prata.json"
REJEIT_PATH = REJEIT_DIR / "alesp_verbas_rejeitados.json"

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password='prisma2026')


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def limpar(v) -> str | None:
    s = str(v).strip() if v else ''
    return None if not s else s


def parse_valor(v: str) -> Decimal | None:
    v = limpar(v)
    if not v:
        return None
    try:
        # ALESP usa ponto como decimal (formato US): "200.0", "2850.0"
        if ',' in v and '.' in v:
            if v.rfind(',') > v.rfind('.'):
                v = v.replace('.', '').replace(',', '.')
            else:
                v = v.replace(',', '')
        elif ',' in v:
            v = v.replace(',', '.')
        d = Decimal(v)
        return d if d > 0 else None
    except InvalidOperation:
        return None


def carregar_indice_sp() -> dict:
    """Carrega nome_urna → politico_id para dep estaduais SP no banco."""
    try:
        conn = psycopg2.connect(**DB)
        cur  = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ON (nome_urna) nome_urna, politico_id
            FROM politicos
            WHERE uf = 'SP' AND cargo = 'DEPUTADO ESTADUAL'
              AND politico_id IS NOT NULL
            ORDER BY nome_urna, ano_eleicao DESC
        """)
        idx = {r[0].upper(): r[1] for r in cur.fetchall()}
        cur.close(); conn.close()
        print(f"  🔗 Índice SP Dep Estaduais: {len(idx)} nomes")
        return idx
    except Exception as e:
        print(f"  ⚠️  Banco indisponível, politico_id será None: {e}")
        return {}


def resolver_politico_id(nome_dep: str, idx: dict) -> tuple[str | None, str]:
    nome = nome_dep.upper().strip()
    if nome in idx:
        return idx[nome], 'exact'
    if HAS_FUZZ and idx:
        match = process.extractOne(nome, list(idx.keys()), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 80:
            return idx[match[0]], f'fuzzy:{match[1]}'
    return None, 'sem_match'


def normalizar(r: dict, idx: dict) -> dict | None:
    matricula = limpar(r.get('Matricula'))
    nome_dep  = limpar(r.get('Deputado'))
    ano_raw   = limpar(r.get('Ano'))
    mes_raw   = limpar(r.get('Mes'))
    valor     = parse_valor(r.get('Valor', ''))
    cnpj_raw  = limpar(r.get('CNPJ'))
    fornec    = limpar(r.get('Fornecedor'))
    tipo      = limpar(r.get('Tipo'))

    if not matricula:
        return {'_motivo': 'matricula ausente', **r}
    if valor is None:
        return {'_motivo': 'valor inválido ou zero', **r}
    try:
        ano = int(ano_raw)
        mes = int(mes_raw)
        if not (2000 <= ano <= 2030 and 1 <= mes <= 12):
            raise ValueError()
    except Exception:
        return {'_motivo': f'ano/mes inválido: {ano_raw}/{mes_raw}', **r}

    competencia = f"{ano:04d}-{mes:02d}"
    cnpj = re.sub(r'\D', '', cnpj_raw or '')
    cnpj = cnpj if len(cnpj) in (11, 14) else None

    # id determinístico
    chave = f"{matricula}|{competencia}|{cnpj or ''}|{valor}"
    id_doc = sha256(chave)[:32]

    politico_id, metodo = resolver_politico_id(nome_dep or '', idx)

    return {
        'id':              id_doc,
        'politico_id':     politico_id,
        'matricula':       matricula,
        'nome_deputado':   nome_dep,
        'cnpj_fornecedor': cnpj,
        'nome_fornecedor': fornec,
        'tipo_despesa':    tipo,
        'valor':           str(valor),
        'mes':             mes,
        'ano':             ano,
        'competencia':     competencia,
        'status_lneg':     None,
        '_match_metodo':   metodo,
    }


def main():
    parser = argparse.ArgumentParser(description='Agent B — Normalizador ALESP Verbas')
    parser.add_argument('--bronze', default=str(BRONZE_PATH), help='Arquivo bronze')
    args = parser.parse_args()

    bronze_path = Path(args.bronze)
    if not bronze_path.exists():
        print(f"❌ Bronze não encontrado: {bronze_path}"); return

    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding='utf-8') as f:
        bronze = json.load(f)

    records = bronze.get('records', [])
    print(f"📊 Total bruto: {len(records):,}")

    print("🔗 Carregando índice de deputados SP...")
    idx = carregar_indice_sp()

    validos, rejeitados = [], []
    sem_pid = 0
    for r in records:
        norm = normalizar(r, idx)
        if norm is None:
            continue
        if '_motivo' in norm:
            rejeitados.append(norm)
        else:
            if not norm['politico_id']:
                sem_pid += 1
            validos.append(norm)

    with open(PRATA_PATH, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'data_processamento': datetime.now(timezone.utc).isoformat(),
                'fonte_bronze':       bronze_path.name,
                'total_validos':      len(validos),
                'total_rejeitados':   len(rejeitados),
                'sem_politico_id':    sem_pid,
            },
            'records': validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        with open(REJEIT_PATH, 'w', encoding='utf-8') as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    pct_pid = (len(validos) - sem_pid) / max(len(validos), 1) * 100
    print(f"✅ Prata: {len(validos):>7,} válidos → {PRATA_PATH.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados):,}")
    print(f"🔗 Com politico_id: {len(validos)-sem_pid:,} ({pct_pid:.1f}%)")
    print("\n✅ Agent B concluído.")

if __name__ == '__main__':
    main()
