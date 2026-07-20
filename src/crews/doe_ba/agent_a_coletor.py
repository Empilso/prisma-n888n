#!/usr/bin/env python3
"""
DOE-BA — Agent A (Coletor)

Fonte: motor de busca público do Diário Oficial (EGBA/IONEWS), subtema "alba"
  — é o Diário Oficial ELETRÔNICO DA ASSEMBLEIA LEGISLATIVA DA BAHIA, publicado
  no mesmo motor do DOE estadual mas com escopo próprio (só conteúdo da ALBA:
  ~1.000 edições com a seção "SRH" vs 122k+ no DOE geral do Executivo).

Recon 2026-07-20: o app Angular de busca (`/buscanova`) chama
  GET https://dool.egba.ba.gov.br/busca/busca/buscar/query/{pagina}/?1=1&q={termo}&subtheme=alba
Retorna JSON crua do Elasticsearch (`hits.hits[]._source.conteudo` = texto da
página do diário). Sem login, sem paywall nesse endpoint. Acervo dá pra buscar
por termo (não por data pura — `q=*` não funciona nesse motor).

Termo usado: "SRH" (cabeçalho fixo da seção "SUPERINTENDÊNCIA DE RECURSOS
HUMANOS — ATOS ADMINISTRATIVOS" em toda edição que publica nomeação/exoneração
de cargo comissionado). pageSize do motor = 10 resultados/página.

Bronze: data/doe_ba/bronze/page_NNNNN.json (1 arquivo por página de resultado).
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = "https://dool.egba.ba.gov.br/busca/busca/buscar/query"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PRISMA888/1.0 (dados abertos DOE-BA)"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "doe_ba"
BRONZE = DATA_DIR / "bronze"
BRONZE.mkdir(parents=True, exist_ok=True)

TERMO = "SRH"
SUBTEMA = "alba"
SLEEP = 0.6
MAX_RETRY = 5


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _get(pagina: int) -> dict:
    url = f"{BASE}/{pagina}/?1=1&q={TERMO}&subtheme={SUBTEMA}"
    for tentativa in range(1, MAX_RETRY + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=40, verify=False)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if tentativa == MAX_RETRY:
                raise
            espera = min(2 ** tentativa, 30)
            log(f"  ⚠️ pág {pagina} falhou ({e}); retry {tentativa}/{MAX_RETRY} em {espera}s")
            time.sleep(espera)
    return {}


def coletar(force: bool, max_paginas: int | None) -> int:
    primeira = _get(0)
    total = int((primeira.get("hits") or {}).get("total") or 0)
    total_paginas = (total + 9) // 10
    if max_paginas:
        total_paginas = min(total_paginas, max_paginas)
    log(f"📊 {total:,} páginas do diário ALBA com termo '{TERMO}' → {total_paginas} páginas de resultado (10/pág)")

    coletadas, falhas = 0, []
    for pagina in range(total_paginas):
        destino = BRONZE / f"page_{pagina:05d}.json"
        if destino.exists() and not force:
            coletadas += 1
            continue
        try:
            data = primeira if pagina == 0 else _get(pagina)
        except Exception as e:
            falhas.append(pagina)
            log(f"  ❌ página {pagina} falhou após retries ({str(e)[:60]}) — pulando")
            time.sleep(SLEEP)
            continue
        destino.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        coletadas += 1
        if (pagina + 1) % 20 == 0 or pagina == total_paginas - 1:
            log(f"  … {pagina + 1}/{total_paginas} páginas coletadas")
        time.sleep(SLEEP)

    if falhas:
        log(f"⚠️ {len(falhas)} página(s) falharam (re-run preenche): {falhas}")
    log(f"✅ coleta: {coletadas}/{total_paginas} páginas de resultado salvas em bronze")
    return coletadas


def main() -> None:
    ap = argparse.ArgumentParser(description="DOE-BA (subtema ALBA) — Coletor da busca pública EGBA/IONEWS")
    ap.add_argument("--force", action="store_true", help="rebaixa mesmo se bronze já existir")
    ap.add_argument("--max-paginas", type=int, default=None, help="limita nº de páginas de resultado (teste)")
    args = ap.parse_args()
    coletar(args.force, args.max_paginas)


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
