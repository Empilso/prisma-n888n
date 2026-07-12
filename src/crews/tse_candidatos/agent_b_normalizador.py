#!/usr/bin/env python3
"""Agent B — Normalizador TSE: Bronze → Prata"""
import json, re, argparse, psycopg2, hashlib
import logging
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

logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR  = BASE_DIR / "data/raw/tse/candidatos/bronze"
PRATA_DIR   = BASE_DIR / "data/raw/tse/candidatos/prata"
REJEIT_DIR  = BASE_DIR / "data/raw/tse/candidatos/rejeitados"
PRATA_DIR.mkdir(parents=True, exist_ok=True)
REJEIT_DIR.mkdir(parents=True, exist_ok=True)

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

def carregar_indice_politico_id() -> dict:
    """Carrega nome+nascimento+uf → politico_id de quem já tem CPF no banco"""
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT lower(coalesce(nome_completo,'') || coalesce(data_nascimento::text,'') || coalesce(uf_nascimento,'')),
               politico_id
        FROM politicos
        WHERE cpf IS NOT NULL AND politico_id IS NOT NULL
    """)
    idx = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return idx

def carregar_indice_cpf_identidade() -> dict:
    """cpf → set de identidades (nome+nascimento) já vistas no banco.

    Guarda anti-colisão (fix 2026-07-12): o TSE publica o MESMO CPF em pessoas
    diferentes (bug conhecido, sobretudo municipais 2008-2020). Se o CPF chegar
    com nome+nascimento divergente do que o banco já conhece, NÃO usar
    sha256(cpf) — senão duas pessoas fundem no mesmo politico_id (caso
    Colombo × Brandi, 56k grupos corrigidos na cirurgia de 2026-07-11/12).
    """
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT cpf, lower(coalesce(nome_completo,'') || coalesce(data_nascimento::text,''))
        FROM politicos
        WHERE cpf IS NOT NULL AND cpf_fonte = 'tse_candidatura'
    """)
    idx: dict = {}
    for cpf, ident in cur.fetchall():
        idx.setdefault(cpf, set()).add(ident)
    conn.close()
    return idx

def resolver_politico_id(cpf, nome_completo, data_nascimento, uf_nascimento, idx, idx_cpf=None) -> str:
    chave = ((nome_completo or '') + (data_nascimento or '') + (uf_nascimento or '')).lower()
    if cpf:
        if idx_cpf is not None:
            identidades = idx_cpf.get(cpf)
            ident_atual = ((nome_completo or '') + (data_nascimento or '')).lower()
            if identidades and ident_atual not in identidades:
                # CPF contestado: banco conhece esse CPF com OUTRA pessoa.
                # Id escopado por identidade em vez de fundir no hash do CPF.
                return hashlib.sha256(f"identidade:{chave}".encode()).hexdigest()
        return hashlib.sha256(cpf.encode()).hexdigest()
    if chave in idx:
        return idx[chave]  # reutiliza hash do CPF se encontrar match
    return hashlib.sha256(chave.encode()).hexdigest()

STATUS_MAP = {
    'ELEITO': 'eleito', 'ELEITO POR QP': 'eleito_qp',
    'ELEITO POR MÉDIA': 'eleito_media', 'ELEITO POR MEDIA': 'eleito_media',
    'SUPLENTE': 'suplente', 'NÃO ELEITO': 'nao_eleito', 'NAO ELEITO': 'nao_eleito',
    '2º TURNO': 'segundo_turno', '2O TURNO': 'segundo_turno',
    'CASSADO': 'cassado', 'RENUNCIOU': 'renunciou',
}

def carregar_municipios() -> dict:
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    cur.execute("SELECT id_ibge, nome, uf FROM municipios")
    idx = {(uf.strip(), nome.upper().strip()): id_ibge for id_ibge, nome, uf in cur.fetchall()}
    conn.close()
    return idx

def resolver_municipio(nm_ue: str, uf: str, idx: dict) -> str | None:
    chave = (uf.strip(), nm_ue.upper().strip())
    if chave in idx:
        return idx[chave]
    if HAS_FUZZ:
        candidatos = [k[1] for k in idx if k[0] == uf]
        match = process.extractOne(nm_ue.upper(), candidatos, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 80:
            return idx.get((uf, match[0]))
    return None

def limpar(v) -> str | None:
    if not v or str(v).strip() in ('#NULO', '#NE', '-1', '-3', '-4', ''):
        return None
    return str(v).strip()

def parse_date(v) -> str | None:
    v = limpar(v)
    if not v: return None
    try:
        d, m, a = v.split('/')
        d, m, a = int(d), int(m), int(a)
        # Validar ranges
        if not (1 <= m <= 12): return None
        if not (1 <= d <= 31): return None
        if not (1900 <= a <= 2100): return None
        return f"{a:04d}-{m:02d}-{d:02d}"
    except (ValueError, TypeError):
        logger.warning("parse_date: valor de data inválido, ignorando: %r", v)
        return None

def title(v) -> str | None:
    v = limpar(v)
    if not v: return None
    stop = {'de','da','do','das','dos','e','a','o','em','na','no','nas','nos','com','por','para'}
    return ' '.join(w.capitalize() if w.lower() not in stop else w.lower() for w in v.split())

def normalizar(r: dict, idx: dict, idx_politico_id: dict, idx_cpf: dict | None = None) -> dict:
    cpf = re.sub(r'\D', '', r.get('NR_CPF_CANDIDATO', '') or '')
    cpf = cpf if len(cpf) == 11 else None

    status_raw = (r.get('DS_SIT_TOT_TURNO') or '').strip().upper()
    status = STATUS_MAP.get(status_raw, 'nulo')

    uf    = (r.get('SG_UF') or '').strip().upper()
    nm_ue = (r.get('NM_UE') or '').strip()
    mun_ibge = resolver_municipio(nm_ue, uf, idx)

    email = limpar(r.get('DS_EMAIL'))
    if email and 'DIVULG' in email.upper(): email = None

    norm = {
        'id_tse':          limpar(r.get('SQ_CANDIDATO')),
        'cpf':             cpf,
        'nome_urna':       title(r.get('NM_URNA_CANDIDATO')),
        'nome_completo':   title(r.get('NM_CANDIDATO')),
        'partido':         limpar(r.get('NM_PARTIDO')),
        'sigla_partido':   limpar(r.get('SG_PARTIDO')),
        'uf':              uf or None,
        'cargo':           limpar(r.get('DS_CARGO')),
        'cd_cargo':        limpar(r.get('CD_CARGO')),
        'municipio_ibge':  mun_ibge,
        'nm_ue':           nm_ue or None,
        'status_eleicao':  status,
        'nr_candidato':    limpar(r.get('NR_CANDIDATO')),
        'sq_candidato':    limpar(r.get('SQ_CANDIDATO')),
        'ano_eleicao':     int(r['ANO_ELEICAO']) if r.get('ANO_ELEICAO','').isdigit() else None,
        'turno':           int(r['NR_TURNO']) if r.get('NR_TURNO','').isdigit() else None,
        'genero':          limpar(r.get('DS_GENERO')),
        'grau_instrucao':  limpar(r.get('DS_GRAU_INSTRUCAO')),
        'estado_civil':    limpar(r.get('DS_ESTADO_CIVIL')),
        'cor_raca':        limpar(r.get('DS_COR_RACA')),
        'ocupacao':        limpar(r.get('DS_OCUPACAO')),
        'data_nascimento': parse_date(r.get('DT_NASCIMENTO')),
        'uf_nascimento':   (limpar(r.get('SG_UF_NASCIMENTO')) or '')[:2] or None,
        'nr_titulo':       limpar(r.get('NR_TITULO_ELEITORAL_CANDIDATO')),
        'tipo_eleicao':    limpar(r.get('NM_TIPO_ELEICAO')),
        'ds_eleicao':      limpar(r.get('DS_ELEICAO')),
        'dt_eleicao':      parse_date(r.get('DT_ELEICAO')),
        'abrangencia':     limpar(r.get('TP_ABRANGENCIA')),
        'nr_federacao':    limpar(r.get('NR_FEDERACAO')),
        'nm_federacao':    limpar(r.get('NM_FEDERACAO')),
        'sg_federacao':    limpar(r.get('SG_FEDERACAO')),
        'nm_coligacao':    limpar(r.get('NM_COLIGACAO')),
        'tp_agremiacao':   limpar(r.get('TP_AGREMIACAO')),
        'email':           email,
    }
    
    norm['politico_id'] = resolver_politico_id(
        norm.get('cpf'), norm.get('nome_completo'),
        norm.get('data_nascimento'), norm.get('uf_nascimento'),
        idx_politico_id, idx_cpf
    )
    
    return norm

def validar(r: dict) -> str | None:
    if not r['id_tse']:      return 'id_tse vazio'
    if not r['nome_urna']:   return 'nome_urna vazio'
    if not r['uf']:          return 'uf vazia'
    if not r['ano_eleicao']: return 'ano_eleicao inválido'
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bronze', help='Arquivo bronze específico (opcional)')
    args = parser.parse_args()

    if args.bronze:
        bronze_path = Path(args.bronze)
    else:
        bronzes = sorted(BRONZE_DIR.glob("*_bronze.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        bronze_path = bronzes[0]

    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding='utf-8') as f:
        bronze = json.load(f)

    records_brutos = bronze.get('records', [])
    print(f"📊 Total bruto: {len(records_brutos)}")
    print("🔗 Carregando índice de municípios...")
    idx = carregar_municipios()
    print(f"   {len(idx)} municípios indexados")
    print("🔗 Carregando índice de politico_id...")
    idx_politico_id = carregar_indice_politico_id()
    print(f"   {len(idx_politico_id)} registros indexados")
    print("🔗 Carregando índice anti-colisão de CPF...")
    idx_cpf = carregar_indice_cpf_identidade()
    print(f"   {len(idx_cpf)} CPFs indexados")

    validos, rejeitados, sem_municipio = [], [], 0
    for r in records_brutos:
        norm = normalizar(r, idx, idx_politico_id, idx_cpf)
        motivo = validar(norm)
        if motivo:
            rejeitados.append({**norm, 'motivo_rejeicao': motivo})
        else:
            if not norm['municipio_ibge']:
                sem_municipio += 1
            validos.append(norm)

    sufixo = bronze_path.stem.replace('_bronze', '')
    prata_path = PRATA_DIR / f"{sufixo}_prata.json"

    with open(prata_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'data_processamento': datetime.now().astimezone().isoformat(),
                'fonte_bronze':       bronze_path.name,
                'total_validos':      len(validos),
                'total_rejeitados':   len(rejeitados),
                'sem_municipio_ibge': sem_municipio,
                'versao_agente':      'v1.0',
            },
            'records': validos
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{sufixo}_rejeitados.json"
        with open(rj, 'w', encoding='utf-8') as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    print(f"✅ Prata: {len(validos)} válidos → {prata_path.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados)}")
    print(f"🗺️  Sem municipio_ibge: {sem_municipio} (FK NULL — aceitável)")

if __name__ == '__main__':
    main()
