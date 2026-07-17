#!/usr/bin/env python3
"""Agent A — Coletor SICONFI Universal: API → Bronze JSON

Pipeline UNIVERSAL de execução fiscal cobrindo TODO o Brasil via SICONFI
(Sistema de Informações Contábeis e Fiscais do Setor Público Brasileiro —
Tesouro Nacional).

Endpoints API (base: https://apidatalake.tesouro.gov.br/ords/siconfi/tt/):
    RREO: /rreo?an_exercicio=YYYY&nr_periodo=N&co_tipo_demonstrativo=...&id_ente=IBGE
    RGF : /rgf?an_exercicio=YYYY&nr_periodo=N&co_tipo_demonstrativo=...&id_ente=IBGE
    DCA : /dca/anexo-{N}?an_exercicio=YYYY&id_ente=IBGE

Cobertura ALVO v1:
    - RREO 2018-2025 bimestral, 27 UFs + 27 capitais
    - DCA 2018-2024 anual, 27 UFs + 5.570 municípios
    - RGF 2018-2025 quadrimestral, 27 UFs (poder executivo)

Estratégia anti-429:
    - ThreadPoolExecutor(max_workers=3) — paralelismo controlado
    - time.sleep(2) entre requests por thread
    - tenacity: 5 tentativas, backoff exponencial 2-60s, retry em 429/5xx

Execução:
    python agent_a_coletor.py --documento RREO --ano 2024 --entes-tipo uf
    python agent_a_coletor.py --documento RREO --ano 2024 --capitais-only
    python agent_a_coletor.py --documento DCA  --ano 2023 --ufs SP,RJ --entes-tipo todos
    python agent_a_coletor.py --documento RGF  --ano 2024 --entes-tipo uf

Saída:
    data/siconfi_universal/bronze/{documento}/{ano}/{documento}_{ano}_{periodo}_{ente}_bronze.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data" / "siconfi_universal"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── API config ──────────────────────────────────────────────────────────────
API_BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"

# Tipos de demonstrativo padrão (texto literal aceito pelo endpoint)
TIPO_DEMONSTRATIVO = {
    "RREO_UF":         "RREO",
    "RREO_MUN":        "RREO Simplificado",
    "RGF_UF":          "RGF",
    "RGF_MUN":         "RGF Simplificado",
}

# Anexos default (modo "completo" coleta todos)
ANEXOS_RREO_PADRAO = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
ANEXOS_RGF_PADRAO  = [1, 2, 3, 4, 5, 6]
# DCA tem letras: I, I-C, I-D, I-E, II, III, etc. — começamos pelo I-C (receitas/despesas)
ANEXOS_DCA_PADRAO  = ["I-C", "I-D", "I-E"]

# ── Capitais (cod IBGE 7 dígitos) ───────────────────────────────────────────
CAPITAIS_IBGE = {
    "AC": "1200401", "AL": "2704302", "AM": "1302603", "AP": "1600303",
    "BA": "2927408", "CE": "2304400", "DF": "5300108", "ES": "3205309",
    "GO": "5208707", "MA": "2111300", "MG": "3106200", "MS": "5002704",
    "MT": "5103403", "PA": "1501402", "PB": "2507507", "PE": "2611606",
    "PI": "2211001", "PR": "4106902", "RJ": "3304557", "RN": "2408102",
    "RO": "1100205", "RR": "1400100", "RS": "4314902", "SC": "4205407",
    "SE": "2800308", "SP": "3550308", "TO": "1721000",
}

# Códigos de UF (2 dígitos IBGE — sigla → cod)
UF_CODIGOS = {
    "AC": "12", "AL": "27", "AM": "13", "AP": "16", "BA": "29", "CE": "23",
    "DF": "53", "ES": "32", "GO": "52", "MA": "21", "MG": "31", "MS": "50",
    "MT": "51", "PA": "15", "PB": "25", "PE": "26", "PI": "22", "PR": "41",
    "RJ": "33", "RN": "24", "RO": "11", "RR": "14", "RS": "43", "SC": "42",
    "SE": "28", "SP": "35", "TO": "17",
}

UFS_ALL = list(UF_CODIGOS.keys())

# Rate-limit
SLEEP_ENTRE_REQUESTS = 2.0  # segundos por thread
MAX_WORKERS = 3
REQUEST_TIMEOUT = 60

# Lock para print thread-safe
_print_lock = Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# ── Carregamento da lista de entes ──────────────────────────────────────────
def carregar_ufs(ufs_filtro: list[str] | None = None) -> list[dict]:
    """Retorna lista de entes UF (27 estados + DF)."""
    ufs = ufs_filtro or UFS_ALL
    return [
        {"id_ente": UF_CODIGOS[uf], "uf": uf, "ente_tipo": "UF", "ente_nome": uf}
        for uf in ufs
        if uf in UF_CODIGOS
    ]


def carregar_municipios(
    ufs_filtro: list[str] | None = None,
    capitais_only: bool = False,
) -> list[dict]:
    """Carrega municípios de prisma_data.ibge_municipios (ou capitais hardcoded como fallback)."""
    ufs = ufs_filtro or UFS_ALL

    if capitais_only:
        return [
            {"id_ente": CAPITAIS_IBGE[uf], "uf": uf, "ente_tipo": "MUNICIPIO", "ente_nome": f"Capital-{uf}"}
            for uf in ufs
            if uf in CAPITAIS_IBGE
        ]

    if not HAS_PSYCOPG2:
        log("⚠️  psycopg2 ausente — caindo para capitais como fallback")
        return carregar_municipios(ufs_filtro, capitais_only=True)

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            dbname=os.getenv("DB_NAME", "prisma_data"),
            user=os.getenv("DB_USER", "postgres"),
            password=DB_PASSWORD,
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id_ibge, nome, uf
              FROM municipios
             WHERE uf = ANY(%s)
             ORDER BY uf, nome
            """,
            (ufs,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        log(f"📍 {len(rows):,} municípios carregados de prisma_data.municipios")
        return [
            {"id_ente": str(r[0]), "uf": r[2], "ente_tipo": "MUNICIPIO", "ente_nome": r[1]}
            for r in rows
        ]
    except Exception as e:
        log(f"⚠️  Erro ao carregar municípios do banco ({e}) — usando capitais como fallback")
        return carregar_municipios(ufs_filtro, capitais_only=True)


def carregar_entes(
    tipo: str,
    ufs_filtro: list[str] | None = None,
    capitais_only: bool = False,
) -> list[dict]:
    if tipo == "uf":
        return carregar_ufs(ufs_filtro)
    if tipo == "municipio":
        return carregar_municipios(ufs_filtro, capitais_only=capitais_only)
    # todos
    return carregar_ufs(ufs_filtro) + carregar_municipios(ufs_filtro, capitais_only=capitais_only)


# ── HTTP ────────────────────────────────────────────────────────────────────
class RateLimit429(Exception):
    pass


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type((requests.exceptions.RequestException, RateLimit429)),
    reraise=True,
)
def get_api(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT,
                        headers={"User-Agent": "PRISMA888-SICONFI/1.0"})
    if resp.status_code == 429:
        raise RateLimit429(f"429 em {url}")
    if resp.status_code >= 500:
        raise requests.exceptions.HTTPError(f"{resp.status_code} em {url}")
    resp.raise_for_status()
    return resp.json()


# ── Bronze writer ───────────────────────────────────────────────────────────
def caminho_bronze(documento: str, ano: int, periodo: int | str,
                   anexo: str, ente: dict) -> Path:
    sub = BRONZE_DIR / documento.lower() / str(ano)
    sub.mkdir(parents=True, exist_ok=True)
    sufixo = (
        f"uf-{ente['uf']}" if ente["ente_tipo"] == "UF"
        else f"mun-{ente['id_ente']}"
    )
    return sub / (
        f"{documento.lower()}_{ano}_p{periodo}_anexo{str(anexo).replace('-', '')}_"
        f"{sufixo}_bronze.json"
    )


def salvar_bronze(path: Path, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False)
    sha = hashlib.sha256(body.encode()).hexdigest()
    payload["meta"]["sha256"] = sha
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


# ── Coletores por documento ─────────────────────────────────────────────────
def coletar_rreo(ente: dict, ano: int, periodo: int, anexo: int,
                 force: bool) -> tuple[str, int]:
    """Retorna (status, n_registros) — status ∈ {'ok','skip','erro','vazio'}."""
    path = caminho_bronze("RREO", ano, periodo, str(anexo), ente)
    if path.exists() and not force:
        return ("skip", 0)

    # Municípios grandes (capitais, > 50k pop) arquivam RREO completo; pequenos usam Simplificado
    # Tenta RREO completo primeiro; se vazio, cai no Simplificado
    tipos_tentar = (
        [TIPO_DEMONSTRATIVO["RREO_UF"]]
        if ente["ente_tipo"] == "UF"
        else [TIPO_DEMONSTRATIVO["RREO_UF"], TIPO_DEMONSTRATIVO["RREO_MUN"]]
    )
    items = []
    tipo = tipos_tentar[0]
    for tipo in tipos_tentar:
        params = {
            "an_exercicio":          ano,
            "nr_periodo":            periodo,
            "co_tipo_demonstrativo": tipo,
            "id_ente":               ente["id_ente"],
            "no_anexo":              f"RREO-Anexo {anexo:02d}",
        }
        try:
            data = get_api(f"{API_BASE}/rreo", params)
            items = data.get("items", []) if isinstance(data, dict) else []
            if items:
                break
        except Exception as e:
            log(f"  ❌ RREO {ano}/p{periodo}/anexo{anexo} ente={ente['id_ente']} tipo={tipo}: {e}")
            return ("erro", 0)
        finally:
            time.sleep(SLEEP_ENTRE_REQUESTS)

    if not items:
        return ("vazio", 0)

    payload = {
        "meta": {
            "documento":        "RREO",
            "ano":              ano,
            "periodo":          periodo,
            "anexo":            f"RREO_Anexo_{anexo}",
            "id_ente":          ente["id_ente"],
            "ente_tipo":        ente["ente_tipo"],
            "ente_uf":          ente["uf"],
            "ente_nome":        ente["ente_nome"],
            "tipo_demonstrativo": tipo,
            "data_extracao":    datetime.now(timezone.utc).isoformat(),
            "total_registros":  len(items),
            "endpoint":         f"{API_BASE}/rreo",
            "params":           params,
        },
        "records": items,
    }
    salvar_bronze(path, payload)
    return ("ok", len(items))


def coletar_rgf(ente: dict, ano: int, periodo: int, anexo: int,
                force: bool) -> tuple[str, int]:
    path = caminho_bronze("RGF", ano, periodo, str(anexo), ente)
    if path.exists() and not force:
        return ("skip", 0)

    tipo = TIPO_DEMONSTRATIVO["RGF_UF" if ente["ente_tipo"] == "UF" else "RGF_MUN"]
    params = {
        "an_exercicio":          ano,
        "nr_periodo":            periodo,
        "co_tipo_demonstrativo": tipo,
        "id_ente":               ente["id_ente"],
        "co_poder":              "E",  # Executivo (poder padrão)
        "no_anexo":              f"RGF-Anexo {anexo:02d}",
    }
    try:
        data = get_api(f"{API_BASE}/rgf", params)
    except Exception as e:
        log(f"  ❌ RGF {ano}/p{periodo}/anexo{anexo} ente={ente['id_ente']}: {e}")
        return ("erro", 0)
    finally:
        time.sleep(SLEEP_ENTRE_REQUESTS)

    items = data.get("items", []) if isinstance(data, dict) else []
    if not items:
        return ("vazio", 0)

    payload = {
        "meta": {
            "documento":        "RGF",
            "ano":              ano,
            "periodo":          periodo,
            "anexo":            f"RGF_Anexo_{anexo}",
            "id_ente":          ente["id_ente"],
            "ente_tipo":        ente["ente_tipo"],
            "ente_uf":          ente["uf"],
            "ente_nome":        ente["ente_nome"],
            "tipo_demonstrativo": tipo,
            "data_extracao":    datetime.now(timezone.utc).isoformat(),
            "total_registros":  len(items),
            "endpoint":         f"{API_BASE}/rgf",
            "params":           params,
        },
        "records": items,
    }
    salvar_bronze(path, payload)
    return ("ok", len(items))


def coletar_dca(ente: dict, ano: int, anexo: str,
                force: bool) -> tuple[str, int]:
    """DCA é anual (sem período). O endpoint /dca retorna TODOS os anexos de
    uma vez (não existe /dca/anexo-{N} — validado manualmente em 2026-07-07,
    a rota antiga dava 404 em 100% das chamadas). O parâmetro `anexo` só é
    usado pro nome do arquivo Bronze (mantido como "TODOS")."""
    path = caminho_bronze("DCA", ano, 0, "TODOS", ente)
    if path.exists() and not force:
        return ("skip", 0)

    endpoint = f"{API_BASE}/dca"
    params = {
        "an_exercicio": ano,
        "id_ente":      ente["id_ente"],
    }
    try:
        data = get_api(endpoint, params)
    except Exception as e:
        log(f"  ❌ DCA {ano} ente={ente['id_ente']}: {e}")
        return ("erro", 0)
    finally:
        time.sleep(SLEEP_ENTRE_REQUESTS)

    items = data.get("items", []) if isinstance(data, dict) else []
    if not items:
        return ("vazio", 0)

    payload = {
        "meta": {
            "documento":        "DCA",
            "ano":              ano,
            "periodo":          0,
            "anexo":            "DCA_TODOS",
            "id_ente":          ente["id_ente"],
            "ente_tipo":        ente["ente_tipo"],
            "ente_uf":          ente["uf"],
            "ente_nome":        ente["ente_nome"],
            "data_extracao":    datetime.now(timezone.utc).isoformat(),
            "total_registros":  len(items),
            "endpoint":         endpoint,
            "params":           params,
        },
        "records": items,
    }
    salvar_bronze(path, payload)
    return ("ok", len(items))


# ── Planejamento de tarefas ─────────────────────────────────────────────────
def planejar_tarefas(documento: str, ano: int, entes: list[dict],
                     anexos: list, periodos: list[int]) -> list[tuple]:
    """Gera lista de tarefas (callable, *args) para o ThreadPoolExecutor."""
    tarefas = []
    if documento == "RREO":
        for ente in entes:
            for p in periodos:
                for a in anexos:
                    tarefas.append(("RREO", ente, ano, p, a))
    elif documento == "RGF":
        for ente in entes:
            for p in periodos:
                for a in anexos:
                    tarefas.append(("RGF", ente, ano, p, a))
    elif documento == "DCA":
        # /dca retorna todos os anexos numa chamada só — 1 tarefa por ente.
        for ente in entes:
            tarefas.append(("DCA", ente, ano, 0, "TODOS"))
    return tarefas


def executar_tarefa(t: tuple, force: bool) -> tuple[str, int]:
    documento = t[0]
    if documento == "RREO":
        _, ente, ano, periodo, anexo = t
        return coletar_rreo(ente, ano, periodo, anexo, force)
    if documento == "RGF":
        _, ente, ano, periodo, anexo = t
        return coletar_rgf(ente, ano, periodo, anexo, force)
    if documento == "DCA":
        _, ente, ano, _, anexo = t
        return coletar_dca(ente, ano, anexo, force)
    return ("erro", 0)


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Agent A — Coletor SICONFI Universal")
    parser.add_argument("--documento", choices=["RREO", "RGF", "DCA"], required=True)
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--ufs", type=str, default=None,
                        help="UFs separadas por vírgula (ex.: SP,RJ,MG). Default: todas 27")
    parser.add_argument("--entes-tipo", choices=["uf", "municipio", "todos"],
                        default="uf")
    parser.add_argument("--capitais-only", action="store_true",
                        help="Quando entes-tipo inclui municípios, restringe a capitais")
    parser.add_argument("--ibge", type=str, default=None,
                        help="Códigos IBGE específicos separados por vírgula (ex.: 3557006). "
                             "Filtra a lista de entes após a montagem.")
    parser.add_argument("--anexo", type=str, default=None,
                        help="Anexo específico (ex.: 1, 2, I-C). Default: todos do documento")
    parser.add_argument("--periodo", type=int, default=None,
                        help="Bimestre/quadrimestre específico. Default: todos")
    parser.add_argument("--force", action="store_true",
                        help="Re-baixa mesmo se Bronze já existir")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS,
                        help=f"Threads concorrentes (default {MAX_WORKERS})")
    args = parser.parse_args()

    documento = args.documento
    ano = args.ano

    ufs_filtro = [u.strip().upper() for u in args.ufs.split(",")] if args.ufs else None
    entes = carregar_entes(args.entes_tipo, ufs_filtro,
                           capitais_only=args.capitais_only)

    if args.ibge:
        alvo = {c.strip() for c in args.ibge.split(",") if c.strip()}
        entes = [e for e in entes if str(e["id_ente"]).strip() in alvo]
        if not entes:
            log(f"❌ Nenhum ente casou com --ibge {sorted(alvo)} — confira os códigos")
            raise SystemExit(1)

    # Anexos
    if args.anexo:
        anexos = [args.anexo]
    else:
        anexos = {
            "RREO": ANEXOS_RREO_PADRAO,
            "RGF":  ANEXOS_RGF_PADRAO,
            "DCA":  ANEXOS_DCA_PADRAO,
        }[documento]

    # Períodos
    if documento == "DCA":
        periodos = [0]
    elif args.periodo:
        periodos = [args.periodo]
    elif documento == "RREO":
        periodos = [1, 2, 3, 4, 5, 6]  # 6 bimestres
    else:  # RGF
        periodos = [1, 2, 3]            # 3 quadrimestres

    log(f"📅 Documento: {documento} | Ano: {ano}")
    log(f"📍 Entes: {len(entes)} ({args.entes_tipo}{'/capitais' if args.capitais_only else ''})")
    log(f"📑 Anexos: {anexos}")
    log(f"📊 Períodos: {periodos}")
    log(f"⚙️  Workers: {args.workers} | sleep/thread: {SLEEP_ENTRE_REQUESTS}s")

    tarefas = planejar_tarefas(documento, ano, entes, anexos, periodos)
    log(f"🎯 Total de requests planejados: {len(tarefas):,}")

    stats = {"ok": 0, "skip": 0, "vazio": 0, "erro": 0, "registros": 0}

    pbar = tqdm(total=len(tarefas), desc="SICONFI") if HAS_TQDM else None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(executar_tarefa, t, args.force): t for t in tarefas}
        for fut in as_completed(futs):
            try:
                status, n = fut.result()
            except Exception as e:
                log(f"  ❌ Exceção não tratada: {e}")
                status, n = "erro", 0
            stats[status] = stats.get(status, 0) + 1
            stats["registros"] += n
            if pbar:
                pbar.update(1)
                pbar.set_postfix(stats)

    if pbar:
        pbar.close()

    log("\n📊 Resumo:")
    log(f"   ✅ ok     : {stats['ok']:,}")
    log(f"   ♻️  skip   : {stats['skip']:,}")
    log(f"   📭 vazio  : {stats['vazio']:,}")
    log(f"   ❌ erro   : {stats['erro']:,}")
    log(f"   📦 registros bronze: {stats['registros']:,}")
    log("\n✅ Agent A concluído.")


if __name__ == "__main__":
    main()
