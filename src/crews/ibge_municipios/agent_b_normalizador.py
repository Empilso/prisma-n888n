#!/usr/bin/env python3
"""
Agent B — Normalizador IBGE
Merge Bronze + lat/lng CSV → Prata
"""
import json
import csv
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/raw/ibge/bronze"
PRATA_DIR  = BASE_DIR / "data/raw/ibge/prata"
REJEIT_DIR = BASE_DIR / "data/raw/ibge/rejeitados"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)
PRATA_DIR.mkdir(parents=True, exist_ok=True)
REJEIT_DIR.mkdir(parents=True, exist_ok=True)
LATLONG_CSV = BASE_DIR / "data/raw/ibge/dados_brutos/municipios_latlong.csv"

def carregar_latlong() -> dict:
    """Carrega CSV de lat/lng indexado por codigo_ibge (7 dígitos)"""
    index = {}
    with open(LATLONG_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            codigo = str(row['codigo_ibge']).zfill(7)
            index[codigo] = {
                'lat':          float(row['latitude'])  if row['latitude']  else None,
                'lng':          float(row['longitude']) if row['longitude'] else None,
                'capital':      row['capital'] == '1',
                'ddd':          int(row['ddd'])          if row['ddd']       else None,
                'fuso_horario': row['fuso_horario']      or None,
            }
    return index

def normalizar(record: dict, latlong: dict) -> dict:
    """Normaliza um registro Bronze e enriquece com lat/lng"""
    id_ibge = str(record.get('id_ibge', '')).zfill(7)
    nome    = (record.get('nome') or '').strip()
    uf      = (record.get('uf_sigla') or record.get('uf') or '').upper().strip()

    geo = latlong.get(id_ibge, {})

    return {
        'id_ibge':           id_ibge,
        'nome':              nome,
        'uf':                uf,
        'uf_nome':           record.get('uf_nome'),
        'regiao_sigla':      record.get('regiao_sigla'),
        'regiao_nome':       record.get('regiao_nome'),
        'mesorregiao_id':    record.get('mesorregiao_id'),
        'mesorregiao_nome':  record.get('mesorregiao_nome'),
        'microrregiao_id':   record.get('microrregiao_id'),
        'microrregiao_nome': record.get('microrregiao_nome'),
        'lat':               geo.get('lat'),
        'lng':               geo.get('lng'),
        'capital':           geo.get('capital', False),
        'ddd':               geo.get('ddd'),
        'fuso_horario':      geo.get('fuso_horario'),
    }

def validar(record: dict) -> str | None:
    """Retorna motivo de rejeição ou None se válido"""
    if not record['id_ibge'] or len(record['id_ibge']) != 7:
        return 'id_ibge inválido'
    if not record['nome']:
        return 'nome vazio'
    if not record['uf'] or len(record['uf']) != 2:
        return 'uf inválida'
    return None

def main():
    # Pega o Prata mais recente (já normalizado pelo agent_b v1)
    pratas = sorted(BRONZE_DIR.glob("*_bronze.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not pratas:
        print("❌ Nenhum arquivo Bronze encontrado em", BRONZE_DIR)
        return

    prata_path = pratas[0]
    print(f"📂 Prata base: {prata_path.name}")

    with open(prata_path, encoding='utf-8') as f:
        prata_base = json.load(f)

    records_brutos = prata_base.get('records', prata_base) if isinstance(prata_base, dict) else prata_base
    print(f"📊 Total bruto: {len(records_brutos)}")

    latlong = carregar_latlong()
    print(f"🗺️  Lat/lng carregados: {len(latlong)} municípios")

    validos, rejeitados = [], []
    for r in records_brutos:
        norm = normalizar(r, latlong)
        motivo = validar(norm)
        if motivo:
            rejeitados.append({**norm, 'motivo_rejeicao': motivo})
        else:
            validos.append(norm)

    hoje = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Salvar Prata
    prata = {
        'meta': {
            'data_processamento': datetime.now().astimezone().isoformat(),
            'fonte_prata_base': prata_path.name,
            'fonte_latlong': LATLONG_CSV.name,
            'total_validos': len(validos),
            'total_rejeitados': len(rejeitados),
            'versao_agente': 'v2.0',
        },
        'records': validos
    }
    prata_path = PRATA_DIR / f"municipios_{hoje}_prata.json"
    with open(prata_path, 'w', encoding='utf-8') as f:
        json.dump(prata, f, ensure_ascii=False, indent=2)

    # Salvar Rejeitados
    if rejeitados:
        rejeit_path = REJEIT_DIR / f"municipios_{hoje}_rejeitados.json"
        with open(rejeit_path, 'w', encoding='utf-8') as f:
            json.dump(rejeitados, f, ensure_ascii=False, indent=2)

    print(f"✅ Prata: {len(validos)} válidos → {prata_path.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados)}")
    
    # Verificar cobertura de lat/lng
    if validos:
        com_geo = sum(1 for r in validos if r['lat'] is not None)
        print(f"🗺️  Com lat/lng: {com_geo}/{len(validos)} ({com_geo/len(validos)*100:.1f}%)")

if __name__ == '__main__':
    main()
