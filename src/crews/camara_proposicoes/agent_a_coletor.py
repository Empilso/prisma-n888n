#!/usr/bin/env python3
"""Agent A — Coletor Câmara Proposições: API REST → Bronze JSON por Legislatura

Portal:  https://dadosabertos.camara.leg.br/swagger/api.html
Endpoint principal: GET /proposicoes (paginação, filtros por ano, tipo, autor)
Endpoint detalhe:   GET /proposicoes/{id}            — ementa, situação, keywords
Endpoint autores:   GET /proposicoes/{id}/autores    — id_camara do deputado autor

Estratégia:
    Itera tipo × ano dentro de uma legislatura. Para cada combinação tipo/ano,
    pagina /proposicoes?siglaTipo=...&ano=... (itens=100). Para cada proposição,
    busca detalhes (situação, keywords, ementa detalhada) e autores em batch.

Tipos cobertos por padrão: PL, PEC, MP, PLP, PRC
Legislaturas suportadas:   55 (2015-2018), 56 (2019-2022), 57 (2023-2026)

Rate-limit: respeita 429 com backoff exponencial. Connection pool reusa sessão.

Execução:
    python agent_a_coletor.py --legislatura 57
    python agent_a_coletor.py --todos
    python agent_a_coletor.py --todos --force        # re-baixa mesmo se Bronze existe
    python agent_a_coletor.py --legislatura 57 --tipos PL,PEC

Saída:
    data/camara_proposicoes/bronze/proposicoes_{LEG}_bronze.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/camara_proposicoes"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

API_BASE = "https://dadosabertos.camara.leg.br/api/v2"

# Mapa de legislatura → anos cobertos
LEGISLATURAS: dict[int, list[int]] = {
    55: list(range(2015, 2019)),  # 2015–2018
    56: list(range(2019, 2023)),  # 2019–2022
    57: list(range(2023, 2027)),  # 2023–2026
}

TIPOS_DEFAULT = ["PL", "PEC", "MP", "PLP", "PRC"]

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "PRISMA888/camara_proposicoes_coletor (contato: prisma888@local)",
}


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
def _get(session: requests.Session, url: str, params: dict | None = None) -> dict:
    resp = session.get(url, params=params, timeout=60)
    if resp.status_code == 429:
        # Respeita Retry-After se presente
        wait = int(resp.headers.get("Retry-After", "10"))
        print(f"    ⏳ 429 rate-limit; aguardando {wait}s...")
        time.sleep(wait)
        resp.raise_for_status()
    resp.raise_for_status()
    return resp.json()


def listar_proposicoes(session: requests.Session, ano: int, tipo: str) -> list[dict]:
    """Lista proposições paginadas (tipo × ano). Retorna lista de dicts resumidos."""
    todos: list[dict] = []
    pagina = 1
    itens = 100
    while True:
        try:
            data = _get(session, f"{API_BASE}/proposicoes", params={
                "siglaTipo":  tipo,
                "ano":        ano,
                "ordem":      "ASC",
                "ordenarPor": "id",
                "itens":      itens,
                "pagina":     pagina,
            })
        except Exception as e:
            print(f"    ❌ Falha ao listar {tipo}/{ano} pag {pagina}: {e}")
            break
        registros = data.get("dados", []) or []
        if not registros:
            break
        todos.extend(registros)
        if len(registros) < itens:
            break
        pagina += 1
        # Cortesia: 60ms entre páginas
        time.sleep(0.06)
    return todos


def buscar_detalhe(session: requests.Session, prop_id: int) -> dict | None:
    """GET /proposicoes/{id} → detalhe (situação atual, ementa detalhada, keywords)."""
    try:
        data = _get(session, f"{API_BASE}/proposicoes/{prop_id}")
        return data.get("dados")
    except Exception as e:
        print(f"      ⚠️  detalhe {prop_id} falhou: {e}")
        return None


def buscar_autores(session: requests.Session, prop_id: int) -> list[dict]:
    """GET /proposicoes/{id}/autores → autores (deputado_id Câmara + nome)."""
    try:
        data = _get(session, f"{API_BASE}/proposicoes/{prop_id}/autores")
        return data.get("dados", []) or []
    except Exception as e:
        print(f"      ⚠️  autores {prop_id} falhou: {e}")
        return []


def processar_legislatura(leg: int, tipos: list[str], force: bool) -> None:
    bronze_path = BRONZE_DIR / f"proposicoes_{leg}_bronze.json"
    if bronze_path.exists() and not force:
        print(f"  ♻️  Bronze já existe: {bronze_path.name} (use --force para re-baixar)")
        return

    anos = LEGISLATURAS[leg]
    print(f"  📅 Legislatura {leg} → anos {anos[0]}–{anos[-1]} | tipos: {','.join(tipos)}")
    session = _make_session()

    todas_props: list[dict] = []

    for tipo in tipos:
        for ano in anos:
            print(f"    🔎 {tipo} {ano}...")
            lista = listar_proposicoes(session, ano, tipo)
            print(f"      📋 {len(lista):,} proposições encontradas")
            iterador = tqdm(lista, desc=f"      {tipo}/{ano}", unit="prop") if HAS_TQDM else lista
            for resumo in iterador:
                prop_id = resumo.get("id")
                if not prop_id:
                    continue
                detalhe = buscar_detalhe(session, prop_id) or {}
                autores = buscar_autores(session, prop_id)
                todas_props.append({
                    "_resumo":  resumo,
                    "_detalhe": detalhe,
                    "_autores": autores,
                })
                # Cortesia inter-request — evita 429
                time.sleep(0.04)

    salvar_bronze(leg, tipos, anos, todas_props)


def salvar_bronze(leg: int, tipos: list[str], anos: list[int], rows: list[dict]) -> Path:
    out = BRONZE_DIR / f"proposicoes_{leg}_bronze.json"
    payload = json.dumps(rows, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    bronze  = {
        "meta": {
            "portal":          "Câmara Federal — Dados Abertos / Proposições",
            "entidade":        "camara_proposicoes",
            "legislatura":     leg,
            "anos":            anos,
            "tipos":           tipos,
            "camada":          "bronze",
            "data_extracao":   datetime.now(timezone.utc).isoformat(),
            "hash_sha256":     sha256,
            "total_registros": len(rows),
        },
        "records": rows,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(rows):>8,} proposições → {out.name}")
    return out


def main():
    parser = argparse.ArgumentParser(description="Agent A — Coletor Câmara Proposições")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--legislatura", type=int, choices=list(LEGISLATURAS.keys()),
                     help="Legislatura específica (55, 56 ou 57)")
    grp.add_argument("--todos", action="store_true",
                     help="Todas as legislaturas (55, 56, 57)")
    parser.add_argument("--tipos", default=",".join(TIPOS_DEFAULT),
                        help=f"Tipos separados por vírgula (default: {','.join(TIPOS_DEFAULT)})")
    parser.add_argument("--force", action="store_true",
                        help="Re-baixa mesmo se o Bronze já existe")
    args = parser.parse_args()

    tipos = [t.strip().upper() for t in args.tipos.split(",") if t.strip()]
    legs  = list(LEGISLATURAS.keys()) if args.todos else [args.legislatura]
    print(f"🏛️  Legislaturas: {legs} | tipos: {tipos}")

    for leg in legs:
        print(f"\n🏛️  Legislatura {leg}")
        processar_legislatura(leg, tipos, force=args.force)

    print("\n✅ Agent A concluído.")


if __name__ == "__main__":
    main()
