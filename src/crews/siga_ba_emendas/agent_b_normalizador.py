#!/usr/bin/env python3
"""Agent B — Normalizador SIGA-BA Emendas: Bronze → Prata

Dataset real: VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS (dados.ba.gov.br)
Colunas reais: num_pagto_nob, Nº do Pagamento Formatado, RazaoSocialCredorPagamento,
               Data do Pagamento, val_pagto_nob, Pagamento_Efetivado, val_GCV,
               Objeto, num_empenho, num_codigo_exec

Chave: id_emenda = SHA256(num_empenho|ano_orcamento)
Ano extraído de num_codigo_exec (primeiro segmento: "2024.3.22...")

Execução:
    python agent_b_normalizador.py
    python agent_b_normalizador.py --bronze emendas_ba_completo_bronze.json
    python agent_b_normalizador.py --todos
"""
import json, re, argparse, hashlib
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/siga_ba_emendas"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)


def limpar(v) -> str | None:
    s = str(v).strip() if v is not None else ''
    return None if not s or s in ('#NULO', '#NE', '-1', 'nan', 'None', 'null') else s


def parse_valor(v) -> Decimal | None:
    s = limpar(v)
    if not s:
        return None
    try:
        s = re.sub(r'[R$\s]', '', s)
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        d = Decimal(s)
        return d if d > 0 else None
    except (InvalidOperation, ValueError):
        return None


def extrair_ano(num_codigo_exec: str, data_pagto: str) -> int | None:
    # num_codigo_exec formato: "2024.3.22.22201.406.3696.500044.5"
    if num_codigo_exec:
        m = re.match(r'^(\d{4})\.', num_codigo_exec.strip())
        if m:
            ano = int(m.group(1))
            if 2010 <= ano <= 2030:
                return ano
    # fallback: extrair do campo Data do Pagamento
    if data_pagto:
        m = re.search(r'\b(20\d{2})\b', data_pagto)
        if m:
            return int(m.group(1))
    return None


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def normalizar_registro(r: dict) -> dict | None:
    num_empenho  = limpar(r.get('num_empenho') or r.get('num_pagto_nob') or '')
    num_codigo   = limpar(r.get('num_codigo_exec') or '')
    data_pagto   = limpar(r.get('Data do Pagamento') or '')

    ano = extrair_ano(num_codigo or '', data_pagto or '')
    if ano is None:
        return {'_motivo': 'ano_nao_identificado', **r}

    val_pago = parse_valor(r.get('val_pagto_nob') or r.get('val_GCV') or '')
    if val_pago is None:
        return {'_motivo': 'valor_pago_nulo_ou_zero', **r}

    id_emenda = sha256(f"{num_empenho or ''}|{ano}")

    objeto = limpar(r.get('Objeto') or '')
    credor = limpar(r.get('RazaoSocialCredorPagamento') or '')
    pago_efetivado = (r.get('Pagamento_Efetivado') or '').strip().lower()
    situacao = 'executado' if pago_efetivado in ('sim', 's', '1', 'true') else 'parcial'

    return {
        'id_emenda':          id_emenda,
        'num_emenda':         num_empenho,
        'ano_loa':            ano,
        'parlamentar_nome':   None,
        'parlamentar_id_ba':  None,
        'politico_id':        None,
        'tipo_emenda':        None,
        'funcao':             None,
        'subfuncao':          None,
        'programa':           None,
        'acao':               objeto,
        'municipio_destino':  None,
        'cod_ibge_municipio': None,
        'valor_autorizado':   str(val_pago),
        'valor_empenhado':    str(val_pago),
        'valor_liquidado':    str(val_pago),
        'valor_pago':         str(val_pago),
        'pct_execucao':       '100.00' if situacao == 'executado' else None,
        'situacao':           situacao,
        'cnpj_favorecido':    None,
        'objeto':             objeto or credor,
        'credor_nome':        credor,
        'num_codigo_exec':    num_codigo,
    }


def processar_bronze(bronze_path: Path) -> None:
    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding='utf-8') as f:
        bronze = json.load(f)

    records = bronze.get('records', [])
    print(f"📊 {len(records):,} registros brutos")

    validos, rejeitados = [], []
    ids_vistos = set()

    for r in records:
        norm = normalizar_registro(r)
        if norm is None:
            continue
        if '_motivo' in norm:
            rejeitados.append(norm)
            continue
        if norm['id_emenda'] in ids_vistos:
            continue
        ids_vistos.add(norm['id_emenda'])
        validos.append(norm)

    stem = bronze_path.stem.replace('_bronze', '')
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'data_processamento': datetime.now(timezone.utc).isoformat(),
                'fonte_bronze':       bronze_path.name,
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

    taxa = len(rejeitados) / max(len(records), 1) * 100
    print(f"✅ Prata: {len(validos):>6,} válidos | Rejeitados: {len(rejeitados):,} ({taxa:.1f}%) → {prata_path.name}")


def main():
    parser = argparse.ArgumentParser(description='Agent B — Normalizador SIGA-BA Emendas')
    parser.add_argument('--bronze', help='Arquivo bronze específico')
    parser.add_argument('--todos',  action='store_true')
    args = parser.parse_args()

    if args.bronze:
        processar_bronze(Path(args.bronze))
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("emendas_ba_*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("emendas_ba_*_bronze.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0])

    print("\n✅ Agent B concluído.")

if __name__ == '__main__':
    main()
