#!/usr/bin/env python3
"""Agent B — Normalizador CGU Lista Negra: Bronze → Prata

Mapeia colunas de CEIS, CNEP e CEPIM para o schema de lista_negra_governo.
Suporta variações de nomes de colunas entre versões dos CSVs.
Computa id_registro = SHA256(fonte|cnpj_cpf|data_inicio_iso).

Regras de rejeição:
  - cnpj_cpf ausente E nome_sancionado ausente (sem identificação)

Execução:
    python agent_b_normalizador.py --bronze ceis_20260101_bronze.json
    python agent_b_normalizador.py --todos
"""
import json, re, argparse, hashlib
from pathlib import Path
from datetime import datetime, date, timezone
from decimal import Decimal, InvalidOperation

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/cgu_lista_negra"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Mapeamento defensivo: campo interno → variantes possíveis no CSV
# Colunas reais confirmadas (2026-06-08): maiúsculas com acentos
COL_MAP = {
    'cnpj_cpf':           ['CPF OU CNPJ DO SANCIONADO', 'CNPJ ENTIDADE', 'cpfCnpj', 'CNPJ/CPF'],
    'tipo_pessoa':        ['TIPO DE PESSOA', 'tipoPessoa'],
    'nome_sancionado':    ['NOME DO SANCIONADO', 'NOME ENTIDADE', 'RAZÃO SOCIAL - CADASTRO RECEITA', 'nomeRazaoSocial'],
    'tipo_sancao':        ['CATEGORIA DA SANÇÃO', 'MOTIVO DO IMPEDIMENTO', 'tipoSancao'],
    'data_inicio':        ['DATA INÍCIO SANÇÃO', 'dataInicioSancao'],
    'data_fim':           ['DATA FINAL SANÇÃO', 'dataFimSancao'],
    'orgao_sancionador':  ['ÓRGÃO SANCIONADOR', 'ÓRGÃO CONCEDENTE', 'orgaoSancionador'],
    'uf_orgao':           ['UF ÓRGÃO SANCIONADOR', 'ufOrgaoSancionador'],
    'esfera':             ['ESFERA DO ÓRGÃO SANCIONADOR', 'esferaOrgaoSancionador'],
    'fundamentacao_legal':['NÚMERO DO PROCESSO', 'fundamentacaoLegal'],
    'descricao_sancao':   ['DETALHAMENTO DO MEIO DE PUBLICAÇÃO', 'descricaoSancao'],
    'data_publicacao':    ['DATA PUBLICAÇÃO', 'dataPublicacaoDou'],
}


def col(row: dict, chave: str) -> str:
    for nome in COL_MAP.get(chave, []):
        if nome in row and str(row[nome]).strip() not in ('', '#NULO', '-1', '#NE', 'None'):
            return str(row[nome]).strip()
    return ''


def limpar(v: str) -> str | None:
    s = v.strip() if v else ''
    return None if s in ('', '#NULO', '#NE', '-1', 'nan', 'None') else s


def normalizar_doc(v: str) -> str | None:
    if not v:
        return None
    digits = re.sub(r'\D', '', v)
    if len(digits) in (11, 14):
        return digits
    return None


def parse_date(v: str) -> date | None:
    v = limpar(v)
    if not v:
        return None
    try:
        v = v.split('T')[0].strip()[:10]
        if '/' in v:
            partes = v.split('/')
            if len(partes) == 3:
                if len(partes[2]) == 4:
                    d, m, a = int(partes[0]), int(partes[1]), int(partes[2])
                else:
                    a, m, d = int(partes[0]), int(partes[1]), int(partes[2])
            else:
                return None
        elif '-' in v:
            a, m, d = int(v[:4]), int(v[5:7]), int(v[8:10])
        else:
            return None
        if 1 <= m <= 12 and 1 <= d <= 31 and 1900 <= a <= 2100:
            return date(a, m, d)
    except Exception:
        pass
    return None


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def normalizar_tipo_pessoa(v: str) -> str | None:
    v = (v or '').strip().upper()
    if v in ('J', 'PJ', 'JURÍDICA', 'JURIDICA'):
        return 'PJ'
    if v in ('F', 'PF', 'FÍSICA', 'FISICA'):
        return 'PF'
    return limpar(v)


def normalizar_registro(r: dict, fonte: str) -> dict | None:
    cnpj_raw     = col(r, 'cnpj_cpf')
    cnpj_cpf     = normalizar_doc(cnpj_raw)
    nome         = limpar(col(r, 'nome_sancionado'))
    data_inicio  = parse_date(col(r, 'data_inicio'))

    if not cnpj_cpf and not nome:
        return {'_motivo': 'sem_identificacao', **r}

    chave = f"{fonte}|{cnpj_cpf or nome or ''}|{data_inicio.isoformat() if data_inicio else ''}"
    id_registro = sha256(chave)

    return {
        'id_registro':         id_registro,
        'fonte':               fonte,
        'cnpj_cpf':            cnpj_cpf,
        'nome_sancionado':     nome,
        'tipo_pessoa':         normalizar_tipo_pessoa(col(r, 'tipo_pessoa')),
        'tipo_sancao':         limpar(col(r, 'tipo_sancao')),
        'data_inicio':         data_inicio.isoformat() if data_inicio else None,
        'data_fim':            parse_date(col(r, 'data_fim')).isoformat() if parse_date(col(r, 'data_fim')) else None,
        'orgao_sancionador':   limpar(col(r, 'orgao_sancionador')),
        'uf_orgao':            limpar(col(r, 'uf_orgao')),
        'esfera':              limpar(col(r, 'esfera')),
        'fundamentacao_legal': limpar(col(r, 'fundamentacao_legal')),
        'descricao_sancao':    limpar(col(r, 'descricao_sancao')),
        'data_publicacao':     parse_date(col(r, 'data_publicacao')).isoformat() if parse_date(col(r, 'data_publicacao')) else None,
    }


def processar_bronze(bronze_path: Path) -> None:
    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding='utf-8') as f:
        bronze = json.load(f)

    meta    = bronze.get('meta', {})
    fonte   = meta.get('fonte', 'DESCONHECIDA')
    records = bronze.get('records', [])
    print(f"📊 {len(records):,} registros brutos | Fonte: {fonte}")

    validos, rejeitados = [], []
    ids_vistos = set()

    for r in records:
        norm = normalizar_registro(r, fonte)
        if norm is None:
            continue
        if '_motivo' in norm:
            rejeitados.append(norm)
            continue
        # deduplicação na prata
        if norm['id_registro'] in ids_vistos:
            continue
        ids_vistos.add(norm['id_registro'])
        validos.append(norm)

    stem = bronze_path.stem.replace('_bronze', '')
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'data_processamento': datetime.now(timezone.utc).isoformat(),
                'fonte_bronze':       bronze_path.name,
                'fonte':              fonte,
                'total_validos':      len(validos),
                'total_rejeitados':   len(rejeitados),
                'total_deduplicados': len(records) - len(validos) - len(rejeitados),
            },
            'records': validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, 'w', encoding='utf-8') as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    taxa_rej = len(rejeitados) / max(len(records), 1) * 100
    print(f"✅ Prata: {len(validos):>7,} válidos | Rejeitados: {len(rejeitados):,} ({taxa_rej:.1f}%) → {prata_path.name}")


def main():
    parser = argparse.ArgumentParser(description='Agent B — Normalizador CGU Lista Negra')
    parser.add_argument('--bronze', help='Arquivo bronze específico')
    parser.add_argument('--todos',  action='store_true', help='Todos os bronzes')
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
