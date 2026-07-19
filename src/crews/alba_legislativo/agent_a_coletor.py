#!/usr/bin/env python3
"""
ALBA Legislativo — Agent A (Coletor)

Fonte: API pública oficial da ALBA (sistema NoPaperCloud/SPL).
  - Proposições: GET /api/publico/proposicao/?pg=N&qtd=M   (74k+ registros, paginado)
  - Comissões:   GET /api/publico/comissoes/?pg=1&qtd=100  (14 comissões + membros)

Descoberto no recon 2026-07-19 (dados-abertos.aspx). API JSON limpa e oficial —
NÃO é scraping de HTML. Cada proposição traz AutorRequerenteDados.autorId + CPF,
o que permite atribuição robusta a politico_id (sem matching por nome).

Bronze: data/alba_legislativo/bronze/{proposicoes_pgNNNN.json, comissoes.json}
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

BASE = "https://albalegis.nopapercloud.com.br/api/publico"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PRISMA888/1.0 (dados abertos ALBA)"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "alba_legislativo"
BRONZE = DATA_DIR / "bronze"
BRONZE.mkdir(parents=True, exist_ok=True)

QTD_POR_PAGINA = 500
SLEEP = 0.8          # gentileza com o servidor da ALBA
MAX_RETRY = 5


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _get(url: str) -> dict:
    for tentativa in range(1, MAX_RETRY + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=40)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if tentativa == MAX_RETRY:
                raise
            espera = min(2 ** tentativa, 30)
            log(f"  ⚠️ {url} falhou ({e}); retry {tentativa}/{MAX_RETRY} em {espera}s")
            time.sleep(espera)
    return {}


def coletar_comissoes(force: bool) -> int:
    destino = BRONZE / "comissoes.json"
    if destino.exists() and not force:
        log("comissoes.json já existe (use --force pra rebaixar)")
        return 0
    data = _get(f"{BASE}/comissoes/?pg=1&qtd=100")
    total = int(data.get("total") or 0)
    payload = {
        "meta": {"fonte": "ALBA API /comissoes", "coletado_em": datetime.now(timezone.utc).isoformat(), "total": total},
        "comissoes": data.get("comissoes", []),
    }
    destino.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log(f"✅ comissões: {total} coletadas → {destino.name}")
    return total


def _autor_ids_da_alba() -> list[int]:
    """autor_ids dos deputados que temos em alba_parlamentares.

    A API SÓ pagina por filtro `?autorId=` (o `pg` é ignorado e `qtd` grande dá
    timeout — recon 2026-07-19). Coletar por autor é o caminho certo: targeted,
    rápido (~140 proposições/deputado) e já pré-atribuído a politico_id.
    """
    if psycopg2 is None:
        raise RuntimeError("psycopg2 ausente — necessário pra listar autor_ids da ALBA")
    db = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
              dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
              password=os.getenv("DB_PASSWORD"))
    conn = psycopg2.connect(**db)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT autor_id FROM alba_parlamentares WHERE autor_id IS NOT NULL ORDER BY autor_id")
    ids = [int(r[0]) for r in cur.fetchall()]
    conn.close()
    return ids


def coletar_proposicoes(force: bool, max_autores: int | None) -> int:
    autores = _autor_ids_da_alba()
    if max_autores:
        autores = autores[:max_autores]
    log(f"📊 proposições: coletando por {len(autores)} autor(es) da ALBA (filtro ?autorId)")

    coletadas = 0
    for i, autor_id in enumerate(autores, 1):
        destino = BRONZE / f"proposicoes_autor{autor_id}.json"
        if destino.exists() and not force:
            continue
        data = _get(f"{BASE}/proposicao/?autorId={autor_id}&qtd=3000")
        registros = data.get("Data", []) or []
        payload = {
            "meta": {"fonte": "ALBA API /proposicao?autorId", "autor_id": autor_id,
                     "total_autor": int(data.get("total") or 0),
                     "coletado_em": datetime.now(timezone.utc).isoformat()},
            "proposicoes": registros,
        }
        destino.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        coletadas += len(registros)
        if i % 10 == 0 or i == len(autores):
            log(f"  … {i}/{len(autores)} autores ({coletadas:,} proposições)")
        time.sleep(SLEEP)
    log(f"✅ proposições: {coletadas:,} coletadas de {len(autores)} autores")
    return coletadas


def main() -> None:
    ap = argparse.ArgumentParser(description="ALBA Legislativo — Coletor da API pública")
    ap.add_argument("--recurso", choices=["proposicoes", "comissoes", "todos"], default="todos")
    ap.add_argument("--force", action="store_true", help="rebaixa mesmo se bronze já existir")
    ap.add_argument("--max-autores", type=int, default=None, help="limita nº de autores (teste)")
    args = ap.parse_args()

    if args.recurso in ("comissoes", "todos"):
        coletar_comissoes(args.force)
    if args.recurso in ("proposicoes", "todos"):
        coletar_proposicoes(args.force, args.max_autores)


if __name__ == "__main__":
    main()
