#!/usr/bin/env python3
"""Agent A — Coletor PNCP: API → Bronze JSON

Portal Nacional de Contratações Públicas (PNCP) — contratos de todos os entes
federados (União, estados, municípios). Endpoint público, sem autenticação.

Execução:
    python agent_a_coletor.py --data-inicio 20250101 --data-fim 20250131
    python agent_a_coletor.py --data-inicio 20240601 --data-fim 20240630 --uf BA
    python agent_a_coletor.py --ano 2024

API: https://pncp.gov.br/api/consulta/v1/contratos
Parâmetros:
    dataInicial / dataFinal  — YYYYMMDD (obrigatório)
    pagina                   — página (default 1)
    tamanhoPagina            — itens por página (max 500)
    NOTA: parâmetro 'uf' é ignorado pela API — filtragem por UF é client-side
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

API_BASE    = "https://pncp.gov.br/api/consulta/v1/contratos"
PAGE_SIZE   = 500
SLEEP_REQ   = 1.5   # segundos entre páginas
BRONZE_DIR  = Path(__file__).parent / "data" / "pncp_contratos" / "bronze"


@retry(
    retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    reraise=True,
)
def _fetch_page(session: requests.Session, data_ini: str, data_fim: str, pagina: int) -> dict:
    r = session.get(API_BASE, params={
        "dataInicial":  data_ini,
        "dataFinal":    data_fim,
        "pagina":       pagina,
        "tamanhoPagina": PAGE_SIZE,
    }, timeout=60)  # 30s era curto demais pra API do PNCP (achado 2026-08-19)
    if r.status_code == 429:
        time.sleep(30)
        raise requests.ConnectionError("rate-limit 429")
    r.raise_for_status()
    return r.json()


def _raw_hash(item: dict) -> str:
    key = item.get("numeroControlePNCP") or json.dumps(item, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(key.encode()).hexdigest()


def coletar(data_ini: str, data_fim: str, uf_filter: str | None = None) -> int:
    """Coleta contratos no intervalo e salva bronze JSON. Retorna total de registros."""
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["Accept"] = "application/json"

    # descobrir total de páginas na página 1
    try:
        first = _fetch_page(session, data_ini, data_fim, 1)
    except Exception as e:
        # ANTES: "return 0" fazia o crew inteiro reportar SUCESSO com zero
        # dado quando a pagina 1 falhava apos esgotar os 5 retries (achado
        # real em producao, 2026-08-19: timeout de leitura do PNCP e maior
        # que os 30s configurados). Falha na pagina 1, apos retry, e falha
        # de verdade -- nunca deve ser confundida com "periodo sem contrato".
        print(f"[ERRO] Falha na primeira página, apos retries: {e}", file=sys.stderr)
        raise RuntimeError(f"PNCP: falha ao buscar pagina 1 de {data_ini}-{data_fim}") from e

    total_elements = first.get("totalRegistros") or first.get("total") or 0
    items_p1 = first.get("data") or first.get("itens") or []
    if not items_p1:
        print(f"[VAZIO] {data_ini}→{data_fim}")
        return 0

    total_pages = max(1, -(-total_elements // PAGE_SIZE))  # ceil
    all_items: list[dict] = list(items_p1)

    bar = tqdm(range(2, total_pages + 1), desc="PNCP páginas") if HAS_TQDM else range(2, total_pages + 1)
    for pg in bar:
        try:
            resp = _fetch_page(session, data_ini, data_fim, pg)
            items = resp.get("data") or resp.get("itens") or []
            all_items.extend(items)
        except Exception as e:
            print(f"[WARN] Página {pg}: {e}", file=sys.stderr)
        time.sleep(SLEEP_REQ)

    # filtro client-side por UF
    if uf_filter:
        all_items = [
            i for i in all_items
            if (i.get("unidadeOrgao") or {}).get("ufSigla", "").upper() == uf_filter.upper()
        ]

    # salvar bronze particionado por data
    out_path = BRONZE_DIR / f"pncp_{data_ini}_{data_fim}.json"
    out_path.write_text(
        json.dumps({"data_ini": data_ini, "data_fim": data_fim, "uf_filter": uf_filter,
                    "total": len(all_items), "items": all_items},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] {len(all_items)} registros → {out_path.name}")
    return len(all_items)


def _date_windows(ano: int) -> list[tuple[str, str]]:
    """Divide o ano em janelas mensais YYYYMMDD."""
    windows = []
    d = date(ano, 1, 1)
    while d.year == ano:
        ultimo = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if ultimo.year > ano:
            ultimo = date(ano, 12, 31)
        windows.append((d.strftime("%Y%m%d"), ultimo.strftime("%Y%m%d")))
        d = ultimo + timedelta(days=1)
    return windows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-inicio", help="YYYYMMDD")
    parser.add_argument("--data-fim",    help="YYYYMMDD")
    parser.add_argument("--ano",         type=int, help="Coleta o ano inteiro em janelas mensais")
    parser.add_argument("--uf",          help="Filtra UF client-side (ex: BA, SP)")
    args = parser.parse_args()

    total = 0
    if args.ano:
        for ini, fim in _date_windows(args.ano):
            total += coletar(ini, fim, args.uf)
    elif args.data_inicio and args.data_fim:
        total += coletar(args.data_inicio, args.data_fim, args.uf)
    else:
        parser.error("Forneça --ano OU --data-inicio + --data-fim")

    print(f"\n📦 Total bronze: {total:,}")
    print("✅ Agent A concluído.")
