#!/usr/bin/env python3
"""Agent A — Coletor ALESP Verbas Gabinete: Download XML → Bronze JSON

Portal:  https://www.al.sp.gov.br/repositorioDados/deputados/despesas_gabinetes.xml
Formato: XML único com todos os anos desde 2015 (um arquivo, atualizado continuamente)
Tamanho: ~14 MB XML (todos os 94 dep estaduais SP, todos os meses desde 2015)

Campos do XML:
  <Ano>, <Mes>, <Matricula>, <Deputado>, <Tipo>, <Fornecedor>, <CNPJ>, <Valor>

Execução:
    python agent_a_coletor.py            # baixa e converte para bronze
    python agent_a_coletor.py --force    # re-baixa mesmo se já existe

Saída:
    data/alesp_verbas_gabinete/bronze/alesp_verbas_bronze.json
"""
import json, hashlib, argparse
from pathlib import Path
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/alesp_verbas_gabinete"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

URL = "https://www.al.sp.gov.br/repositorioDados/deputados/despesas_gabinetes.xml"
RAW_PATH    = RAW_DIR    / "despesas_gabinetes.xml"
BRONZE_PATH = BRONZE_DIR / "alesp_verbas_bronze.json"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def baixar_xml() -> None:
    print(f"  ⬇️  Baixando despesas_gabinetes.xml...")
    resp = requests.get(URL, timeout=120)
    resp.raise_for_status()
    RAW_PATH.write_bytes(resp.content)
    print(f"  ✅ Salvo: {RAW_PATH.name} ({RAW_PATH.stat().st_size / 1_048_576:.1f} MB)")


def parse_xml() -> list[dict]:
    print(f"  📄 Parseando XML...")
    tree = ET.parse(RAW_PATH)
    root = tree.getroot()
    rows = []
    for despesa in root.findall('despesa'):
        row = {child.tag: (child.text or '').strip() for child in despesa}
        rows.append(row)
    print(f"  📊 {len(rows):,} registros extraídos")
    return rows


def salvar_bronze(rows: list[dict]) -> None:
    payload = json.dumps(rows, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    bronze  = {
        'meta': {
            'portal':          'ALESP — Verbas de Gabinete dos Deputados Estaduais SP',
            'entidade':        'alesp_verbas_gabinete',
            'camada':          'bronze',
            'data_extracao':   datetime.now(timezone.utc).isoformat(),
            'hash_sha256':     sha256,
            'total_registros': len(rows),
            'url_fonte':       URL,
        },
        'records': rows,
    }
    with open(BRONZE_PATH, 'w', encoding='utf-8') as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(rows):>7,} registros → {BRONZE_PATH.name}")


def main():
    parser = argparse.ArgumentParser(description='Agent A — Coletor ALESP Verbas Gabinete')
    parser.add_argument('--force', action='store_true', help='Re-baixa mesmo se já existe')
    args = parser.parse_args()

    if BRONZE_PATH.exists() and not args.force:
        print(f"  ♻️  Bronze já existe: {BRONZE_PATH.name} (use --force para atualizar)")
        return

    try:
        baixar_xml()
    except Exception as e:
        print(f"  ❌ Falha no download: {e}"); return

    rows = parse_xml()
    if not rows:
        print("  ❌ Nenhum registro encontrado no XML"); return

    salvar_bronze(rows)
    print("\n✅ Agent A concluído.")

if __name__ == '__main__':
    main()
