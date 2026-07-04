#!/usr/bin/env python3
"""Agent A — Coletor Senado Votações: API REST → Bronze JSON por Ano

Portal:  https://legis.senado.leg.br/dadosabertos/docs/

Endpoints usados:
    GET /plenario/lista/votacao/{ANO}    → lista votações nominais do ano
    GET /votacao/{CODIGO}                → detalhes + votos por senador

Período coberto: 2015–2026 (legislaturas 55, 56, 57)

Volume estimado: ~800–1.500 votações nominais/ano × 12 anos = ~10k–14k votações
                 × ~81 senadores = ~800k–1.1M votos individuais

Execução:
    python agent_a_coletor.py --ano 2024
    python agent_a_coletor.py --todos
    python agent_a_coletor.py --legislatura 57
    python agent_a_coletor.py --todos --force

Saída:
    data/senado_votacoes/bronze/senado_vot_{ANO}_bronze.json
"""
import json, hashlib, argparse, time
from pathlib import Path
from datetime import datetime, timezone

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    import xmltodict
    HAS_XMLTODICT = True
except ImportError:
    HAS_XMLTODICT = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/senado_votacoes"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

API_BASE = "https://legis.senado.leg.br/dadosabertos"

ANOS = list(range(2015, 2027))

LEGISLATURAS = {
    55: list(range(2015, 2019)),
    56: list(range(2019, 2023)),
    57: list(range(2023, 2027)),
}

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "PRISMA888/n888n senado_votacoes/1.0 (+inteligencia.politica)",
}


def _parse_response(resp: requests.Response) -> dict:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "json" in ctype:
        return resp.json()
    if HAS_XMLTODICT:
        return xmltodict.parse(resp.text)
    raise RuntimeError("Resposta XML mas xmltodict não disponível. Instale: pip install xmltodict")


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get(path: str, params: dict | None = None) -> dict:
    url = f"{API_BASE}{path}"
    resp = requests.get(url, params=params or {}, headers=HEADERS, timeout=60)
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    return _parse_response(resp)


def _safe_get(d, *keys):
    cur = d
    for k in keys:
        if cur is None:
            return None
        if isinstance(cur, list):
            if not cur:
                return None
            cur = cur[0]
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def listar_votacoes_ano(ano: int) -> list[dict]:
    """Retorna lista de votações nominais do ano."""
    data = _get(f"/plenario/lista/votacao/{ano}")
    if not data:
        return []

    # Estrutura: ListaVotacoes -> Votacoes -> Votacao -> [...]
    votacoes = (_safe_get(data, "ListaVotacoes", "Votacoes", "Votacao")
                or _safe_get(data, "ListaVotacao", "Votacoes", "Votacao")
                or _safe_get(data, "Votacoes", "Votacao"))
    if not votacoes:
        return []
    if isinstance(votacoes, dict):
        votacoes = [votacoes]

    # Filtra apenas nominais (Secret == "N" e tem votos individuais)
    return votacoes


def detalhe_votacao(codigo: int) -> dict | None:
    try:
        data = _get(f"/votacao/{codigo}")
    except requests.HTTPError as e:
        print(f"    ⚠️  HTTP detalhe votacao {codigo}: {e}")
        return None
    if not data:
        return None
    return (_safe_get(data, "VotacaoMateria", "Votacao")
            or _safe_get(data, "DetalheVotacao", "Votacao")
            or data)


def salvar_bronze(ano: int, registros: list[dict]) -> Path:
    out = BRONZE_DIR / f"senado_vot_{ano}_bronze.json"
    payload = json.dumps(registros, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    bronze = {
        "meta": {
            "portal":          "Senado Federal — Dados Abertos",
            "entidade":        "senado_votacoes",
            "ano":             ano,
            "camada":          "bronze",
            "data_extracao":   datetime.now(timezone.utc).isoformat(),
            "hash_sha256":     sha256,
            "total_votacoes":  len(registros),
        },
        "records": registros,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(registros):>4,} votações → {out.name}")
    return out


def processar_ano(ano: int, force: bool = False) -> None:
    bronze_path = BRONZE_DIR / f"senado_vot_{ano}_bronze.json"
    if bronze_path.exists() and not force:
        print(f"  ♻️  Bronze já existe: {bronze_path.name} (use --force)")
        return

    try:
        lista = listar_votacoes_ano(ano)
    except Exception as e:
        print(f"  ❌ Falha lista {ano}: {e}")
        return

    print(f"  📋 {ano}: {len(lista)} votações listadas")
    if not lista:
        return

    enriquecidas = []
    it = tqdm(lista, desc=f"votações {ano}") if HAS_TQDM else lista
    for v in it:
        codigo = _safe_get(v, "CodigoSessaoVotacao") or v.get("CodigoVotacao") or v.get("Codigo")
        if not codigo:
            # Algumas variantes do schema: dentro de Sessao
            codigo = _safe_get(v, "Sessao", "CodigoSessao")
        if not codigo:
            continue
        try:
            codigo = int(codigo)
        except (TypeError, ValueError):
            continue

        det = detalhe_votacao(codigo)
        time.sleep(0.05)

        enriquecidas.append({
            "_codigo": codigo,
            "_ano":    ano,
            "lista":   v,
            "detalhe": det,
        })

    if not enriquecidas:
        print(f"  ⚠️  Nenhum detalhe coletado para {ano}")
        return

    salvar_bronze(ano, enriquecidas)


def main():
    parser = argparse.ArgumentParser(description="Agent A — Coletor Senado Votações")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--ano",         type=int, choices=ANOS, help="Ano específico")
    grp.add_argument("--todos",       action="store_true", help="Todos os anos (2015–2026)")
    grp.add_argument("--legislatura", type=int, choices=list(LEGISLATURAS.keys()),
                     help="Legislatura inteira (55, 56, 57)")
    parser.add_argument("--force", action="store_true", help="Re-baixa mesmo se Bronze existe")
    args = parser.parse_args()

    if args.todos:
        anos = ANOS
    elif args.legislatura:
        anos = LEGISLATURAS[args.legislatura]
    else:
        anos = [args.ano]

    print(f"📅 Anos: {anos[0]}–{anos[-1]} ({len(anos)} anos)")
    for ano in anos:
        print(f"\n📅 {ano}")
        processar_ano(ano, force=args.force)

    print("\n✅ Agent A concluído.")


if __name__ == "__main__":
    main()
