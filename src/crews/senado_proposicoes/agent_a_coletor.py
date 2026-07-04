#!/usr/bin/env python3
"""Agent A — Coletor Senado Proposições: API REST → Bronze JSON por Ano

Portal:  https://legis.senado.leg.br/dadosabertos/docs/
Formato: XML nativo (forçamos JSON via Accept: application/json quando possível).
         Fallback automático: se servidor devolver XML, parse via xmltodict.

Endpoints usados:
    GET /materia/pesquisa/lista?ano={ANO}&sigla={SIGLA}   → lista materias do ano/sigla
    GET /materia/{CODIGO}                                 → detalhes completos
    GET /materia/{CODIGO}/autoria                         → autoria (senadores)

Período coberto: 2015–2026 (legislaturas 55, 56, 57)
Siglas cobertas: PLS, PL, PEC, PRS, PDS, MPV, PLP, PLN, PDL, PRN

Volume estimado: ~3.000–5.000 proposições/ano × 11 anos = ~40k–55k registros

Execução:
    python agent_a_coletor.py --ano 2024
    python agent_a_coletor.py --todos
    python agent_a_coletor.py --legislatura 57          # 2023+
    python agent_a_coletor.py --todos --force           # re-baixa mesmo se Bronze existe

Saída:
    data/senado_proposicoes/bronze/senado_prop_{ANO}_bronze.json
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
DATA_DIR   = BASE_DIR / "data/senado_proposicoes"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

API_BASE = "https://legis.senado.leg.br/dadosabertos"

ANOS = list(range(2015, 2027))  # 2015–2026

LEGISLATURAS = {
    55: list(range(2015, 2019)),   # 2015–2018
    56: list(range(2019, 2023)),   # 2019–2022
    57: list(range(2023, 2027)),   # 2023–2026
}

SIGLAS = ["PLS", "PL", "PEC", "PRS", "PDS", "MPV", "PLP", "PLN", "PDL", "PRN"]

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "PRISMA888/n888n senado_proposicoes/1.0 (+inteligencia.politica)",
}


def _parse_response(resp: requests.Response) -> dict:
    """API Senado: tenta JSON; se servidor mandou XML, converte via xmltodict."""
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
    """Navega aninhado tolerando dict/None/lista."""
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


def listar_proposicoes_ano_sigla(ano: int, sigla: str) -> list[dict]:
    """Lista proposições de um ano e sigla. Retorna lista de dicts brutos."""
    data = _get("/materia/pesquisa/lista", {"ano": ano, "sigla": sigla})
    if not data:
        return []

    # Estrutura JSON: {"PesquisaBasicaMateria": {"Materias": {"Materia": [...]}}}
    # Estrutura XML idem via xmltodict
    materias = _safe_get(data, "PesquisaBasicaMateria", "Materias", "Materia")
    if not materias:
        return []
    if isinstance(materias, dict):
        materias = [materias]
    return materias


def detalhe_materia(codigo: int) -> dict | None:
    try:
        data = _get(f"/materia/{codigo}")
    except requests.HTTPError as e:
        print(f"    ⚠️  HTTP detalhe {codigo}: {e}")
        return None
    if not data:
        return None
    return _safe_get(data, "DetalheMateria", "Materia") or data


def autoria_materia(codigo: int) -> list[dict]:
    try:
        data = _get(f"/materia/{codigo}/autoria")
    except requests.HTTPError as e:
        print(f"    ⚠️  HTTP autoria {codigo}: {e}")
        return []
    if not data:
        return []
    autores = _safe_get(data, "AutoriaMateria", "Materia", "Autoria", "Autor")
    if not autores:
        return []
    if isinstance(autores, dict):
        autores = [autores]
    return autores


def salvar_bronze(ano: int, registros: list[dict]) -> Path:
    out = BRONZE_DIR / f"senado_prop_{ano}_bronze.json"
    payload = json.dumps(registros, ensure_ascii=False)
    sha256 = hashlib.sha256(payload.encode()).hexdigest()
    bronze = {
        "meta": {
            "portal":          "Senado Federal — Dados Abertos",
            "entidade":        "senado_proposicoes",
            "ano":             ano,
            "camada":          "bronze",
            "data_extracao":   datetime.now(timezone.utc).isoformat(),
            "hash_sha256":     sha256,
            "total_registros": len(registros),
            "siglas_pesquisadas": SIGLAS,
        },
        "records": registros,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(registros):>5,} proposições → {out.name}")
    return out


def processar_ano(ano: int, force: bool = False) -> None:
    bronze_path = BRONZE_DIR / f"senado_prop_{ano}_bronze.json"
    if bronze_path.exists() and not force:
        print(f"  ♻️  Bronze já existe: {bronze_path.name} (use --force)")
        return

    todas = []
    siglas_iter = tqdm(SIGLAS, desc=f"siglas {ano}") if HAS_TQDM else SIGLAS
    for sigla in siglas_iter:
        try:
            lista = listar_proposicoes_ano_sigla(ano, sigla)
        except Exception as e:
            print(f"    ❌ Falha lista {sigla}/{ano}: {e}")
            continue
        if not lista:
            continue
        print(f"    📋 {sigla}/{ano}: {len(lista)} encontradas")

        for m in lista:
            codigo = _safe_get(m, "IdentificacaoMateria", "CodigoMateria")
            if not codigo:
                continue
            try:
                codigo = int(codigo)
            except (TypeError, ValueError):
                continue

            detalhe = detalhe_materia(codigo)
            autores = autoria_materia(codigo)
            time.sleep(0.05)  # gentileza com API

            todas.append({
                "_codigo":  codigo,
                "_sigla":   sigla,
                "_ano":     ano,
                "lista":    m,
                "detalhe":  detalhe,
                "autoria":  autores,
            })

    if not todas:
        print(f"  ⚠️  Nenhum registro coletado para {ano}")
        return

    salvar_bronze(ano, todas)


def main():
    parser = argparse.ArgumentParser(description="Agent A — Coletor Senado Proposições")
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

    print(f"📅 Anos: {anos[0]}–{anos[-1]} ({len(anos)} anos) | Siglas: {SIGLAS}")
    for ano in anos:
        print(f"\n📅 {ano}")
        processar_ano(ano, force=args.force)

    print("\n✅ Agent A concluído.")


if __name__ == "__main__":
    main()
