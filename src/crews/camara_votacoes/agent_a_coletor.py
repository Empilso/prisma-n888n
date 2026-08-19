#!/usr/bin/env python3
"""Agent A — Coletor Câmara Votações: API REST → Bronze JSON

Portal:  https://dadosabertos.camara.leg.br
Endpoints utilizados:
  GET /votacoes                    → lista paginada com filtros dataInicio/dataFim/idLegislatura
  GET /votacoes/{id}/votos         → votos nominais (1 registro por deputado por votação)
  GET /votacoes/{id}/orientacoes   → orientações de bancada

Cobertura: legislaturas 55, 56, 57 (2015–2026).

Como funciona a paginação:
  - itens=100 (máximo aceito pela API)
  - segue links rel="next" do header até esgotar
  - filtros por janela mensal (dataInicio/dataFim) para evitar truncamento
    em legislaturas inteiras (a API tem limite ~10k itens por query).

Execução:
    python agent_a_coletor.py --legislatura 57
    python agent_a_coletor.py --ano 2024
    python agent_a_coletor.py --todos
    python agent_a_coletor.py --legislatura 57 --force

Saída:
    data/camara_votacoes/bronze/votacoes_{LEG}_{ANO}_{MES}_bronze.json
    (cada arquivo contém metadados + lista de votações + votos nominais + orientações)
"""
import json
import hashlib
import argparse
import time
from pathlib import Path
from datetime import datetime, date, timezone
from calendar import monthrange

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/camara_votacoes"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

API_BASE = "https://dadosabertos.camara.leg.br/api/v2"

# Legislatura → (data_inicio, data_fim)  — referência oficial Câmara
LEGISLATURAS = {
    55: (date(2015, 2, 1),  date(2019, 1, 31)),
    56: (date(2019, 2, 1),  date(2023, 1, 31)),
    57: (date(2023, 2, 1),  date(2027, 1, 31)),
}

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "prisma888-etl/1.0 (https://github.com/empilso/prisma888)",
}

# Pequena pausa entre requests pra ser educado com a API
SLEEP_BETWEEN_VOTACOES = 0.15


class APIError(Exception):
    pass


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.RequestException, APIError)),
)
def _get(url: str, params: dict | None = None) -> dict:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=120)
    if resp.status_code == 429:
        # Rate limit — espera e tenta de novo
        time.sleep(5)
        raise APIError("rate limit (429)")
    if resp.status_code >= 500:
        raise APIError(f"server error ({resp.status_code})")
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        raise APIError(f"resposta não-JSON em {url}")


def listar_votacoes_janela(data_ini: date, data_fim: date,
                            id_legislatura: int) -> list[dict]:
    """Lista todas as votações em uma janela de datas (paginação seguida)."""
    out: list[dict] = []
    # `idLegislatura` combinado com dataInicio/dataFim quebra a API da Camara
    # com 400 "Parametro(s) invalido(s)" -- confirmado ao vivo em 2026-08-19.
    # O intervalo de datas ja escopa a consulta o suficiente (cada legislatura
    # corresponde a um periodo de anos conhecido), entao o parametro e
    # redundante e foi removido.
    params = {
        "dataInicio":     data_ini.isoformat(),
        "dataFim":        data_fim.isoformat(),
        "itens":          100,
        "ordem":          "ASC",
        "ordenarPor":     "dataHoraRegistro",
    }
    url = f"{API_BASE}/votacoes"
    while url:
        data = _get(url, params=params)
        dados = data.get("dados", []) or []
        out.extend(dados)
        # Próxima página via "links"
        next_url = None
        for link in data.get("links", []) or []:
            if link.get("rel") == "next":
                next_url = link.get("href")
                break
        if not next_url:
            break
        url = next_url
        params = None  # já vem nos query params do next_url
    return out


def coletar_votos(votacao_id: str) -> list[dict]:
    """Pega os votos nominais de uma votação. Pagina se necessário."""
    out: list[dict] = []
    url = f"{API_BASE}/votacoes/{votacao_id}/votos"
    params: dict | None = {"itens": 100}
    while url:
        try:
            data = _get(url, params=params)
        except requests.HTTPError as e:
            # 404 = votação sem votos nominais (votação simbólica)
            if getattr(e.response, "status_code", None) == 404:
                return []
            raise
        out.extend(data.get("dados", []) or [])
        next_url = None
        for link in data.get("links", []) or []:
            if link.get("rel") == "next":
                next_url = link.get("href")
                break
        if not next_url:
            break
        url = next_url
        params = None
    return out


def coletar_orientacoes(votacao_id: str) -> list[dict]:
    url = f"{API_BASE}/votacoes/{votacao_id}/orientacoes"
    try:
        data = _get(url, params={"itens": 100})
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 404:
            return []
        raise
    return data.get("dados", []) or []


def salvar_bronze(legislatura: int, ano: int, mes: int,
                   votacoes: list[dict],
                   votos_por_votacao: dict[str, list[dict]],
                   orientacoes_por_votacao: dict[str, list[dict]]) -> Path:
    out = BRONZE_DIR / f"votacoes_{legislatura}_{ano}_{mes:02d}_bronze.json"
    payload = {
        "votacoes": votacoes,
        "votos":    votos_por_votacao,
        "orientacoes": orientacoes_por_votacao,
    }
    blob   = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    sha256 = hashlib.sha256(blob.encode()).hexdigest()
    bronze = {
        "meta": {
            "portal":          "Câmara Federal — Dados Abertos (API REST v2)",
            "entidade":        "camara_votacoes",
            "legislatura":     legislatura,
            "ano":             ano,
            "mes":             mes,
            "camada":          "bronze",
            "data_extracao":   datetime.now(timezone.utc).isoformat(),
            "hash_sha256":     sha256,
            "total_votacoes":  len(votacoes),
            "total_votos":     sum(len(v) for v in votos_por_votacao.values()),
            "total_orientacoes": sum(len(v) for v in orientacoes_por_votacao.values()),
        },
        "votacoes":     votacoes,
        "votos":        votos_por_votacao,
        "orientacoes":  orientacoes_por_votacao,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  Bronze: {len(votacoes):>5,} votações | "
          f"{bronze['meta']['total_votos']:>7,} votos nominais -> {out.name}")
    return out


def processar_mes(legislatura: int, ano: int, mes: int, force: bool = False) -> None:
    bronze_path = BRONZE_DIR / f"votacoes_{legislatura}_{ano}_{mes:02d}_bronze.json"
    if bronze_path.exists() and not force:
        print(f"  Ja existe: {bronze_path.name} (use --force)")
        return

    data_ini = date(ano, mes, 1)
    data_fim = date(ano, mes, monthrange(ano, mes)[1])

    print(f"  Janela: {data_ini} -> {data_fim}")
    votacoes = listar_votacoes_janela(data_ini, data_fim, legislatura)
    print(f"  Votacoes listadas: {len(votacoes)}")

    votos_por_votacao: dict[str, list[dict]] = {}
    orientacoes_por_votacao: dict[str, list[dict]] = {}

    iterator = tqdm(votacoes, desc="  votos") if HAS_TQDM else votacoes
    for v in iterator:
        vid = v.get("id")
        if not vid:
            continue
        try:
            votos_por_votacao[vid]      = coletar_votos(vid)
            orientacoes_por_votacao[vid] = coletar_orientacoes(vid)
        except Exception as e:
            print(f"  ! Falha em {vid}: {e}")
            votos_por_votacao[vid]       = []
            orientacoes_por_votacao[vid] = []
        time.sleep(SLEEP_BETWEEN_VOTACOES)

    salvar_bronze(legislatura, ano, mes,
                  votacoes, votos_por_votacao, orientacoes_por_votacao)


def meses_da_legislatura(legislatura: int) -> list[tuple[int, int]]:
    ini, fim = LEGISLATURAS[legislatura]
    # Não passa do "hoje" pra não pedir dados que ainda não existem
    hoje = date.today()
    if fim > hoje:
        fim = hoje
    pares: list[tuple[int, int]] = []
    a, m = ini.year, ini.month
    while (a, m) <= (fim.year, fim.month):
        pares.append((a, m))
        m += 1
        if m == 13:
            m = 1
            a += 1
    return pares


def meses_de_ano(ano: int) -> list[tuple[int, int]]:
    hoje = date.today()
    ult_mes = hoje.month if ano == hoje.year else 12
    return [(ano, m) for m in range(1, ult_mes + 1)]


def descobrir_legislatura(ano: int) -> int:
    for leg, (ini, fim) in LEGISLATURAS.items():
        if ini.year <= ano <= fim.year:
            return leg
    raise ValueError(f"ano {ano} fora das legislaturas conhecidas")


def main():
    parser = argparse.ArgumentParser(description="Agent A — Coletor Câmara Votações")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--legislatura", type=int, choices=list(LEGISLATURAS),
                      help="Legislatura específica (55, 56, 57)")
    grp.add_argument("--ano",   type=int, help="Ano específico (mês a mês)")
    grp.add_argument("--todos", action="store_true",
                      help="Todas as legislaturas configuradas")
    parser.add_argument("--force", action="store_true",
                         help="Re-baixa mesmo se Bronze já existe")
    args = parser.parse_args()

    if args.todos:
        for leg in LEGISLATURAS:
            print(f"\n=== Legislatura {leg} ===")
            for ano, mes in meses_da_legislatura(leg):
                print(f"\n[{leg}] {ano}-{mes:02d}")
                processar_mes(leg, ano, mes, force=args.force)
    elif args.legislatura:
        leg = args.legislatura
        print(f"=== Legislatura {leg} ===")
        for ano, mes in meses_da_legislatura(leg):
            print(f"\n[{leg}] {ano}-{mes:02d}")
            processar_mes(leg, ano, mes, force=args.force)
    elif args.ano:
        leg = descobrir_legislatura(args.ano)
        print(f"=== Ano {args.ano} (legislatura {leg}) ===")
        for ano, mes in meses_de_ano(args.ano):
            print(f"\n[{leg}] {ano}-{mes:02d}")
            processar_mes(leg, ano, mes, force=args.force)

    print("\n✅ Agent A concluído.")


if __name__ == "__main__":
    main()
