#!/usr/bin/env python3
"""SAPL Genérico — Agent A (Extrator)

Para cada instância confirmada `ativa` em `sapl_instancias` (Agent 0), pagina
4 endpoints da API pública REST (DRF, sem login) de cada câmara:

    /api/parlamentares/parlamentar/   — cadastro do vereador
    /api/parlamentares/mandato/       — datas de início/fim de mandato + legislatura
    /api/parlamentares/filiacao/      — partido (FK) + data de filiação/desfiliação
    /api/parlamentares/partido/       — id -> sigla do partido
    /api/materia/materialegislativa/  — projetos de lei e afins (autores por ID)

Paginação real confirmada (Santarém-PA, 2026-07-21): objeto "pagination" com
"links.next" (URL completa) e "total_entries"; aceita "?page_size=100" (reduz
~10x o nº de requisições vs. o default de 10/página). "results" é a lista.

Cada câmara é tratada de forma isolada: falha numa não derruba as demais
(sequencial, nunca paralelo agressivo — são sites de terceiros, câmaras
pequenas, sem CDN robusta). Bronze por domínio, permite retomar depois de
interrupção sem re-baixar o que já foi salvo (a menos que --force).

Bronze: data/sapl_generico/bronze/{dominio}/{endpoint}.json
"""
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2
import psycopg2.extras

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "prisma_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/sapl_generico/bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PRISMA888/1.0 (dados abertos SAPL/Interlegis)"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}
TIMEOUT = 25
SLEEP = 0.4
MAX_RETRY = 4

ENDPOINTS = {
    "parlamentar": "parlamentares/parlamentar",
    "mandato": "parlamentares/mandato",
    "filiacao": "parlamentares/filiacao",
    "partido": "parlamentares/partido",
    "materialegislativa": "materia/materialegislativa",
}


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _get(url: str, params: dict) -> dict | None:
    for tentativa in range(1, MAX_RETRY + 1):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if tentativa == MAX_RETRY:
                log(f"    ⚠️ falha definitiva em {url}: {str(e)[:80]}")
                return None
            time.sleep(min(2 ** tentativa, 15))
    return None


def paginar(dominio: str, caminho: str, max_paginas: int | None) -> list[dict]:
    url = f"https://{dominio}/api/{caminho}/"
    registros: list[dict] = []
    params = {"page": 1, "page_size": 100}
    pagina = 1
    while True:
        data = _get(url, params)
        if data is None or not isinstance(data, dict):
            break
        results = data.get("results")
        if results is None:
            break
        registros.extend(results)
        nxt = (data.get("pagination") or {}).get("links", {}).get("next")
        if not nxt or (max_paginas and pagina >= max_paginas):
            break
        pagina += 1
        params = {"page": pagina, "page_size": 100}
        time.sleep(SLEEP)
    return registros


def coletar_instancia(dominio: str, municipio_ibge: str, force: bool, max_paginas: int | None) -> dict:
    destino_dir = BRONZE_DIR / dominio
    destino_dir.mkdir(parents=True, exist_ok=True)
    resumo = {"dominio": dominio, "municipio_ibge": municipio_ibge}

    for nome_curto, caminho in ENDPOINTS.items():
        arq = destino_dir / f"{nome_curto}.json"
        if arq.exists() and not force:
            resumo[nome_curto] = "cache"
            continue
        limite = max_paginas if nome_curto == "materialegislativa" else None
        registros = paginar(dominio, caminho, limite)
        arq.write_text(json.dumps({
            "meta": {"dominio": dominio, "endpoint": caminho, "coletado_em": datetime.now().isoformat(),
                      "total": len(registros)},
            "records": registros,
        }, ensure_ascii=False), encoding="utf-8")
        resumo[nome_curto] = len(registros)
        time.sleep(SLEEP)

    return resumo


def main() -> None:
    ap = argparse.ArgumentParser(description="SAPL Genérico — Agent A (Extrator)")
    ap.add_argument("--force", action="store_true", help="rebaixa mesmo se bronze já existir")
    ap.add_argument("--limit", type=int, default=None, help="limita nº de câmaras processadas (piloto)")
    ap.add_argument("--max-paginas-materia", type=int, default=None,
                     help="limita páginas de materialegislativa por câmara (teste rápido)")
    ap.add_argument("--todos", action="store_true", help="processa todas as instâncias 'ativa' (rodar na VPS)")
    args = ap.parse_args()

    if not args.todos and not args.limit:
        ap.error("passe --limit N (piloto) ou --todos (carga completa)")

    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sql = "SELECT municipio_ibge, dominio FROM sapl_instancias WHERE status = 'ativo' ORDER BY dominio"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    cur.execute(sql)
    instancias = cur.fetchall()
    conn.close()

    log(f"coletando {len(instancias)} câmara(s) SAPL confirmada(s)")
    falhas = []
    for i, inst in enumerate(instancias, 1):
        log(f"  [{i}/{len(instancias)}] {inst['dominio']}")
        try:
            resumo = coletar_instancia(inst["dominio"], inst["municipio_ibge"], args.force, args.max_paginas_materia)
            log(f"    {resumo}")
        except Exception as e:
            falhas.append(inst["dominio"])
            log(f"    ❌ falhou por completo: {str(e)[:100]} — seguindo pra próxima câmara")

    if falhas:
        log(f"⚠️ {len(falhas)} câmara(s) com falha total: {falhas}")
    log(f"✅ Agent A concluído: {len(instancias) - len(falhas)}/{len(instancias)} câmara(s) coletadas")


if __name__ == "__main__":
    main()
