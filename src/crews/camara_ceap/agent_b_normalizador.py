#!/usr/bin/env python3
"""Agent B — Normalizador Câmara CEAP: Bronze → Prata

Mapeia as colunas brutas do CSV da Câmara para o schema de camara_verbas_ceap.
Trata variações de nomes de colunas entre anos (2015-2016 vs 2017+).
Computa politico_id = SHA256(cpf) do parlamentar (igual ao padrão politicos).
Computa id_documento = ideDocumento ou SHA256 de campos-chave (deduplicação).

Regras de rejeição:
  - Valor líquido ausente ou negativo
  - Data de emissão inválida
  - CPF do parlamentar ausente (sem como vincular ao politico)

Saída:
    data/camara_ceap/prata/ceap_{ANO}_prata.json
    data/camara_ceap/rejeitados/ceap_{ANO}_rejeitados.json
"""
import json, re, argparse, hashlib
from pathlib import Path
from datetime import datetime, date, timezone
from decimal import Decimal, InvalidOperation

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/camara_ceap"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Mapeamento de colunas: nome_interno → [variantes_possíveis_no_csv]
# Cobre formato 2015-2016 (colunas em português) e 2017+ (camelCase)
COL_MAP = {
    'nome_parlamentar':    ['txNomeParlamentar', 'Parlamentar', 'Nome'],
    'cpf_parlamentar':     ['cpf', 'CPF'],
    'ide_cadastro':        ['ideCadastro', 'idCadastro'],
    'nu_legislatura':      ['nuLegislatura', 'Legislatura'],
    'sg_uf':               ['sgUF', 'UF', 'sgUf'],
    'sg_partido':          ['sgPartido', 'Partido'],
    'num_sub_cota':        ['numSubCota', 'Numero da Sub-cota'],
    'txt_descricao':       ['txtDescricao', 'Descricao', 'Descrição'],
    'txt_desc_especif':    ['txtDescricaoEspecificacao', 'Especificacao'],
    'txt_fornecedor':      ['txtFornecedor', 'Fornecedor', 'Nome do Fornecedor'],
    'txt_cnpj_cpf':        ['txtCNPJCPF', 'CNPJ/CPF do Fornecedor', 'CNPJ'],
    'txt_numero':          ['txtNumero', 'Numero do Documento', 'NF'],
    'ind_tipo_doc':        ['indTipoDocumento', 'Tipo do Documento'],
    'dat_emissao':         ['datEmissao', 'Data da Emissão', 'Data Emissão'],
    'vlr_documento':       ['vlrDocumento', 'Valor do Documento', 'Valor Documento'],
    'vlr_glosa':           ['vlrGlosa', 'Valor Glosa'],
    'vlr_liquido':         ['vlrLiquido', 'Valor Líquido', 'Valor'],
    'num_mes':             ['numMes', 'Mês', 'Mes'],
    'num_ano':             ['numAno', 'Ano'],
    'nu_deputado_id':      ['nuDeputadoId', 'idDeputado'],
    'ide_documento':       ['ideDocumento', 'idDocumento'],
    'url_documento':       ['urlDocumento', 'URL'],
}


def col(row: dict, chave_interna: str) -> str:
    """Extrai valor usando qualquer variante de nome de coluna."""
    for nome in COL_MAP.get(chave_interna, []):
        if nome in row and str(row[nome]).strip() not in ('', '#NULO', '-1', '#NE'):
            return str(row[nome]).strip()
    return ''


def limpar(v: str) -> str | None:
    s = v.strip() if v else ''
    return None if s in ('', '#NULO', '#NE', '-1', '-3', '-4', '#NULL!', 'nan') else s


def parse_valor(v: str) -> Decimal | None:
    """Detecta automaticamente formato BR (9.999,98) vs US (9999.98 ou 9,999.98)."""
    v = limpar(v)
    if not v:
        return None
    try:
        if ',' in v and '.' in v:
            # Ambos presentes: o que vier ÚLTIMO é o decimal
            if v.rfind(',') > v.rfind('.'):
                v = v.replace('.', '').replace(',', '.')   # BR: 9.999,98 → 9999.98
            else:
                v = v.replace(',', '')                      # US: 9,999.98 → 9999.98
        elif ',' in v:
            v = v.replace(',', '.')                        # Só vírgula: decimal BR
        # Só ponto ou sem separador: já é formato US/neutro válido
        return Decimal(v)
    except InvalidOperation:
        return None


def parse_date(v: str) -> date | None:
    v = limpar(v)
    if not v:
        return None
    try:
        # formatos: yyyy-mm-ddTHH:MM:SS, dd/mm/yyyy, yyyy-mm-dd
        v = v.split('T')[0].strip()[:10]  # remove parte de hora se presente
        if '/' in v:
            partes = v.split('/')
            if len(partes[2]) == 4:  # dd/mm/yyyy
                d, m, a = int(partes[0]), int(partes[1]), int(partes[2])
            else:                    # yyyy/mm/dd improvável mas trata
                a, m, d = int(partes[0]), int(partes[1]), int(partes[2])
        elif '-' in v:              # yyyy-mm-dd
            a, m, d = int(v[:4]), int(v[5:7]), int(v[8:10])
        else:
            return None
        if not (1 <= m <= 12 and 1 <= d <= 31 and 1900 <= a <= 2100):
            return None
        return date(a, m, d)
    except Exception:
        return None


def normalizar_doc(v: str) -> str | None:
    v = limpar(v)
    if not v:
        return None
    digits = re.sub(r'\D', '', v)
    return digits if len(digits) in (11, 14) else None


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def computar_id_documento(ide_doc: str, cpf: str, nr_doc: str,
                           dat_emissao: str, vlr_liquido: str) -> str:
    """Usa ideDocumento se disponível, senão SHA256 de campos-chave."""
    if ide_doc and ide_doc.isdigit():
        return f"cam_{ide_doc}"
    chave = f"{cpf}|{nr_doc}|{dat_emissao}|{vlr_liquido}"
    return f"h_{sha256(chave)[:32]}"


def normalizar_registro(r: dict, ano: int) -> dict | None:
    """Retorna registro normalizado ou None se deve ser rejeitado."""
    cpf_raw      = col(r, 'cpf_parlamentar')
    cpf_limpo    = re.sub(r'\D', '', cpf_raw)
    cpf          = cpf_limpo if len(cpf_limpo) == 11 else None

    vlr_liquido  = parse_valor(col(r, 'vlr_liquido'))
    dat_emissao  = parse_date(col(r, 'dat_emissao'))

    if not cpf:
        return {'_motivo': 'cpf_parlamentar ausente', **r}
    if vlr_liquido is None:
        return {'_motivo': 'valor_liquido inválido', **r}
    if dat_emissao is None:
        return {'_motivo': 'data_emissao inválida', **r}
    if vlr_liquido < 0:
        return {'_motivo': 'valor_liquido negativo', **r}

    ide_doc  = col(r, 'ide_documento')
    nr_doc   = col(r, 'txt_numero') or ''
    id_doc   = computar_id_documento(ide_doc, cpf, nr_doc, str(dat_emissao), str(vlr_liquido))

    num_mes  = col(r, 'num_mes')
    num_ano  = col(r, 'num_ano') or str(ano)
    try:
        competencia = f"{int(num_ano):04d}-{int(num_mes):02d}" if num_mes else f"{ano}-01"
    except ValueError:
        competencia = f"{ano}-01"

    politico_id = sha256(cpf)

    cnpj_forn = normalizar_doc(col(r, 'txt_cnpj_cpf'))

    return {
        'id_documento':   id_doc,
        'politico_id':    politico_id,
        'cpf_parlamentar': cpf,
        'nome_parlamentar': limpar(col(r, 'nome_parlamentar')),
        'sg_uf':          limpar(col(r, 'sg_uf')),
        'sg_partido':     limpar(col(r, 'sg_partido')),
        'cnpj_fornecedor': cnpj_forn,
        'nome_fornecedor': limpar(col(r, 'txt_fornecedor')),
        'tipo_despesa':   limpar(col(r, 'txt_descricao')),
        'descricao':      limpar(col(r, 'txt_desc_especif')),
        'valor_documento': str(parse_valor(col(r, 'vlr_documento')) or vlr_liquido),
        'valor_glosa':    str(parse_valor(col(r, 'vlr_glosa')) or Decimal('0')),
        'valor_liquido':  str(vlr_liquido),
        'data_emissao':   str(dat_emissao),
        'competencia':    competencia,
        'nr_documento':   limpar(nr_doc),
        'url_documento':  limpar(col(r, 'url_documento')),
        'status_lneg':    None,
    }


def processar_bronze(bronze_path: Path) -> None:
    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding='utf-8') as f:
        bronze = json.load(f)

    meta    = bronze.get('meta', {})
    ano     = int(meta.get('ano', 0))
    records = bronze.get('records', [])
    print(f"📊 Total bruto: {len(records):,}")

    validos, rejeitados = [], []
    for r in records:
        norm = normalizar_registro(r, ano)
        if norm is None:
            continue
        if '_motivo' in norm:
            rejeitados.append(norm)
        else:
            validos.append(norm)

    stem = bronze_path.stem.replace('_bronze', '')
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'data_processamento': datetime.now(timezone.utc).isoformat(),
                'fonte_bronze':       bronze_path.name,
                'ano':                ano,
                'total_validos':      len(validos),
                'total_rejeitados':   len(rejeitados),
            },
            'records': validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, 'w', encoding='utf-8') as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    taxa = len(rejeitados) / max(len(records), 1) * 100
    print(f"✅ Prata: {len(validos):>8,} válidos → {prata_path.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados):,} ({taxa:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description='Agent B — Normalizador Câmara CEAP')
    parser.add_argument('--bronze', help='Arquivo bronze específico')
    parser.add_argument('--todos',  action='store_true', help='Todos os bronzes')
    args = parser.parse_args()

    if args.bronze:
        processar_bronze(Path(args.bronze))
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("ceap_*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("ceap_*_bronze.json"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0])

    print("\n✅ Agent B concluído.")

if __name__ == '__main__':
    main()
