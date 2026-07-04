#!/usr/bin/env python3
"""Agent A — Coletor TSE Candidatos: CSV → Bronze JSON"""
import csv, json, hashlib, chardet, argparse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
CAND_DIR   = BASE_DIR / "data/raw/tse/candidatos/dados_brutos"
BRONZE_DIR = BASE_DIR / "data/raw/tse/candidatos/bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

def ler_csv(path: Path) -> list[dict]:
    with open(path, 'rb') as f:
        enc = chardet.detect(f.read(50000))['encoding'] or 'latin-1'
    with open(path, encoding=enc, errors='replace') as f:
        return list(csv.DictReader(f, delimiter=';'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ano',  default='2024')
    parser.add_argument('--uf',   default='BA')
    parser.add_argument('--todos-ufs', action='store_true')
    args = parser.parse_args()

    ano_dir = CAND_DIR / f"consulta_cand_{args.ano}"
    if not ano_dir.exists():
        print(f"❌ Pasta não encontrada: {ano_dir}"); return

    if args.todos_ufs:
        arquivos = sorted(ano_dir.glob(f"consulta_cand_{args.ano}_*.csv"))
        arquivos = [f for f in arquivos if 'BRASIL' not in f.name and 'BR.csv' not in f.name]
    else:
        arquivos = [ano_dir / f"consulta_cand_{args.ano}_{args.uf}.csv"]

    todos_records = []
    for arq in arquivos:
        if not arq.exists():
            print(f"⚠️  Não encontrado: {arq.name}"); continue
        records = ler_csv(arq)
        todos_records.extend(records)
        print(f"  📄 {arq.name}: {len(records)} registros")

    payload = json.dumps(todos_records, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    hoje    = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    sufixo  = 'TODOS' if args.todos_ufs else args.uf

    out = BRONZE_DIR / f"candidatos_{args.ano}_{sufixo}_bronze.json"
    if out.exists():
        print(f"⚠️  Bronze já existe: {out.name}"); return

    bronze = {
        'meta': {
            'portal':          'TSE — Repositório de Dados Eleitorais',
            'ano_eleicao':     args.ano,
            'uf':              sufixo,
            'data_extracao':   datetime.now().astimezone().isoformat(),
            'hash_sha256':     sha256,
            'total_registros': len(todos_records),
            'versao_agente':   'v1.0',
        },
        'records': todos_records
    }

    with open(out, 'w', encoding='utf-8') as f:
        json.dump(bronze, f, ensure_ascii=False)

    print(f"✅ Bronze: {len(todos_records)} registros → {out.name}")
    print(f"   SHA256: {sha256[:16]}...")

if __name__ == '__main__':
    main()
