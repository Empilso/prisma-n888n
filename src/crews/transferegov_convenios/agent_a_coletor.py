#!/usr/bin/env python3
"""Agent A - Coletor TransfereGov Convenios: API REST -> Bronze JSON

Fonte: https://api.transferegov.dth.api.gov.br/transferenciasespeciais/

Endpoints consumidos (PostgREST-style):
  - /plano_acao_especial        : 1 linha por plano (equivalente a 'convenio')
  - /programa_especial          : metadados do programa (orgao concedente)

Estrategia:
  1. Pagina o endpoint plano_acao_especial com filtro por ano
  2. Salva em Bronze JSON (1 arquivo por ano)
  3. Coleta programa_especial inteiro para enriquecer Bronze de orgao

Execucao:
    python agent_a_coletor.py --ano 2024
    python agent_a_coletor.py --ano 2024 --limit 50    # smoke test
    python agent_a_coletor.py --todos
    python agent_a_coletor.py --ano 2024 --force
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / 'data/transferegov_convenios'
RAW_DIR    = DATA_DIR / 'raw'
BRONZE_DIR = DATA_DIR / 'bronze'
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

API_BASE = 'https://api.transferegov.dth.api.gov.br/transferenciasespeciais'
ANOS = list(range(2020, 2027))
PAGE_SIZE = 1000

HEADERS = {
    'User-Agent': 'PRISMA888-ETL/1.0 (dados publicos - convenios federais)',
    'Accept': 'application/json',
}


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get(path: str, params: dict) -> list[dict]:
    url = f'{API_BASE}/{path}'
    resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
    if resp.status_code in (502, 503, 504):
        raise RuntimeError(f'HTTP {resp.status_code} em {url}')
    resp.raise_for_status()
    return resp.json()


def paginar(path: str, base_params: dict, limit_total: int | None = None) -> Iterator[dict]:
    offset = 0
    while True:
        if limit_total is not None and offset >= limit_total:
            return
        page_size = PAGE_SIZE
        if limit_total is not None:
            page_size = min(PAGE_SIZE, limit_total - offset)
        params = {**base_params, 'limit': page_size, 'offset': offset}
        rows = _get(path, params)
        if not rows:
            return
        for r in rows:
            yield r
        if len(rows) < page_size:
            return
        offset += len(rows)


def baixar_planos_por_ano(ano: int, force: bool, limit: int | None) -> Path | None:
    out_name = f'planos_acao_especial_{ano}_bronze.json'
    if limit is not None:
        out_name = f'planos_acao_especial_{ano}_smoke{limit}_bronze.json'
    out = BRONZE_DIR / out_name
    if out.exists() and not force:
        print(f'  [skip] bronze ja existe: {out.name}')
        return out

    print(f'  >> baixando plano_acao_especial ano={ano} limit={limit or "all"}')
    params = {'ano_plano_acao': f'eq.{ano}'}
    rows = list(paginar('plano_acao_especial', params, limit_total=limit))
    if not rows:
        print(f'  [warn] nenhum registro para ano={ano}')
        return None

    payload = json.dumps(rows, ensure_ascii=False)
    bronze = {
        'meta': {
            'portal':          'TransfereGov - transferencias especiais',
            'entidade':        'plano_acao_especial',
            'fonte_url':       f'{API_BASE}/plano_acao_especial?ano_plano_acao=eq.{ano}',
            'ano':             ano,
            'camada':          'bronze',
            'data_extracao':   datetime.now(timezone.utc).isoformat(),
            'hash_sha256':     hashlib.sha256(payload.encode()).hexdigest(),
            'total_registros': len(rows),
        },
        'records': rows,
    }
    out.write_text(json.dumps(bronze, ensure_ascii=False))
    print(f'  [ok] bronze: {len(rows):,} registros -> {out.name}')
    return out


def baixar_programas(force: bool) -> Path | None:
    out = BRONZE_DIR / 'programas_especial_bronze.json'
    if out.exists() and not force:
        print(f'  [skip] bronze programas ja existe: {out.name}')
        return out
    print('  >> baixando programa_especial (catalogo completo)')
    rows = list(paginar('programa_especial', {}))
    if not rows:
        print('  [warn] nenhum programa retornado')
        return None
    payload = json.dumps(rows, ensure_ascii=False)
    bronze = {
        'meta': {
            'portal':          'TransfereGov - transferencias especiais',
            'entidade':        'programa_especial',
            'fonte_url':       f'{API_BASE}/programa_especial',
            'camada':          'bronze',
            'data_extracao':   datetime.now(timezone.utc).isoformat(),
            'hash_sha256':     hashlib.sha256(payload.encode()).hexdigest(),
            'total_registros': len(rows),
        },
        'records': rows,
    }
    out.write_text(json.dumps(bronze, ensure_ascii=False))
    print(f'  [ok] bronze programas: {len(rows):,} registros -> {out.name}')
    return out


def main():
    ap = argparse.ArgumentParser(description='Agent A - Coletor TransfereGov Convenios')
    ap.add_argument('--ano',   type=int)
    ap.add_argument('--todos', action='store_true')
    ap.add_argument('--limit', type=int, help='limite global de registros (smoke test)')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--skip-programas', action='store_true')
    args = ap.parse_args()

    print('TransfereGov Convenios - Agent A (Coletor)')
    print(f'  API: {API_BASE}')

    if not args.skip_programas:
        baixar_programas(args.force)

    anos = ANOS if args.todos else [args.ano or 2024]
    for ano in anos:
        baixar_planos_por_ano(ano, args.force, args.limit)
        print()

    print('[ok] Agent A concluido.')


if __name__ == '__main__':
    main()
