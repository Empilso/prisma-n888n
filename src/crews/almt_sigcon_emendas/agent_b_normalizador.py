#!/usr/bin/env python3
"""Agent B — Normalizador ALMT/SIGCON Emendas MT: Bronze → Prata (2 camadas)

Gera dois arquivos prata por ano, espelhando o par
emendas_federais / emendas_federais_pagamentos:

  - aplicacoes: 1 linha por (emenda, convênio) — granularidade real da fonte.
    Uma emenda pode financiar N convênios (medido: emenda 303 de "Lideranças
    Partidárias" financiou 29 projetos distintos em 2024) — perder isso
    seria fabricar um agregado que a fonte não garante ser 1:1.
  - agregado: 1 linha por (emenda, ano) — soma valor_utilizado de todas as
    aplicações, pra caber na tabela emendas_estaduais existente (mesmo
    schema usado pela BA). municipio_ibge/objeto ficam NULL quando a emenda
    tem mais de 1 aplicação (não fabricar um município "representante").

Resolução de politico_id: nome do parlamentar (texto livre do SIGCON, ex.
"Júlio Campos") → politico_id, por match exato/fuzzy contra `politicos`
filtrado por uf='MT' AND cargo='DEPUTADO ESTADUAL' (pool de ~1.270
candidaturas distintas, todas as legislaturas). Sem match → None, nunca
fabricar (mesma regra do sapl_generico).

Resolução de municipio_ibge: proponente costuma ser "PREFEITURA MUNICIPAL
DE X" — extrai o nome e casa contra `municipios` (uf='MT'). Proponentes que
não são prefeitura (associações, fundações, secretarias) ficam sem
município — correto, não são de um único município.
"""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from rapidfuzz import fuzz, process
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

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
BRONZE_DIR = BASE_DIR / "data/almt_sigcon_emendas/bronze"
PRATA_DIR = BASE_DIR / "data/almt_sigcon_emendas/prata"
PRATA_DIR.mkdir(parents=True, exist_ok=True)

UF = "MT"


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _slug_parlamentar(nome: str) -> str:
    """Identificador estável do parlamentar pra compor a chave da emenda.
    Usa o nome (não politico_id) — precisa ficar igual mesmo se o match de
    politico_id mudar numa recarga futura, senão a mesma emenda vira uma
    linha nova em vez de atualizar a existente."""
    s = _norm(nome)
    s = re.sub(r"[^A-Z0-9]+", "-", s).strip("-")
    return s


def chave_emenda(numero_emenda_origem: str, parlamentar_nome: str) -> str:
    """Nm.Emenda do SIGCON é numerado POR PARLAMENTAR, não globalmente —
    dois deputados podem ter "emenda 46" no mesmo ano (medido no piloto:
    25 colisões reais). numero_emenda (chave em emendas_estaduais) precisa
    ser único por (uf, ano) sozinho, então compõe com o parlamentar."""
    return f"{numero_emenda_origem}/{_slug_parlamentar(parlamentar_nome)}"


def _carregar_indice_deputados() -> list[tuple[str, str]]:
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT politico_id, nome_urna
        FROM politicos
        WHERE uf = %s AND cargo = 'DEPUTADO ESTADUAL' AND politico_id IS NOT NULL
    """, (UF,))
    idx = [(_norm(nome), pid) for pid, nome in cur.fetchall()]
    cur.close()
    conn.close()
    log(f"  índice deputados estaduais MT: {len(idx)} candidaturas distintas")
    return idx


def resolver_politico_id(idx: list[tuple[str, str]], nome: str) -> tuple[str | None, str]:
    nome_n = _norm(nome)
    if not nome_n or nome_n in ("LIDERANÇAS PARTIDÁRIAS", "COMISSÃO DE FISCALIZAÇÃO"):
        return None, "nao_individual"

    for candidato_nome, pid in idx:
        if candidato_nome == nome_n:
            return pid, "exato"

    if HAS_FUZZ:
        nomes = [c[0] for c in idx]
        match = process.extractOne(nome_n, nomes, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 90:
            return idx[match[2]][1], "fuzzy"

    return None, "none"


def _carregar_indice_municipios() -> dict[str, str]:
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT id_ibge, nome FROM municipios WHERE uf = %s", (UF,))
    idx = {_norm(nome): ibge for ibge, nome in cur.fetchall()}
    cur.close()
    conn.close()
    log(f"  índice municípios MT: {len(idx)}")
    return idx


PREFEITURA_RE = re.compile(r"PREFEITURA\s+MUNICIPAL\s+DE\s+(.+)", re.IGNORECASE)


def resolver_municipio(proponente: str, idx_mun: dict[str, str]) -> str | None:
    m = PREFEITURA_RE.match((proponente or "").strip())
    if not m:
        return None
    nome_n = _norm(m.group(1))
    if nome_n in idx_mun:
        return idx_mun[nome_n]
    if HAS_FUZZ:
        match = process.extractOne(nome_n, list(idx_mun.keys()), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 92:
            return idx_mun[match[0]]
    return None


def _parse_data(s: str | None) -> str | None:
    if not s:
        return None
    try:
        d, m, y = s.split("/")
        return f"{y}-{m}-{d}"
    except ValueError:
        return None


def processar_ano(bronze_path: Path, idx_dep: list[tuple[str, str]], idx_mun: dict[str, str], stats: dict) -> dict:
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    ano = bronze["meta"]["ano_ass"]
    aplicacoes = []
    for c in bronze["records"]:
        municipio_ibge = resolver_municipio(c.get("proponente"), idx_mun)
        vig_inicio = vig_fim = None
        if c.get("vigencia"):
            partes = c["vigencia"].split(" a ")
            if len(partes) == 2:
                vig_inicio = _parse_data(partes[0].strip())
                vig_fim = _parse_data(partes[1].strip())

        for e in c.get("emendas", []):
            politico_id, metodo = resolver_politico_id(idx_dep, e["parlamentar_nome"])
            stats["match"][metodo] = stats["match"].get(metodo, 0) + 1
            aplicacoes.append({
                "uf": UF,
                "ano_orcamento": ano,
                "numero_emenda": chave_emenda(e["numero_emenda"], e["parlamentar_nome"]),
                "numero_emenda_origem": e["numero_emenda"],
                "politico_id": politico_id,
                "parlamentar_nome": e["parlamentar_nome"],
                "conv_id": c["conv_id"],
                "numero_convenio": c.get("numero_convenio"),
                "concedente": c.get("concedente"),
                "proponente": c.get("proponente"),
                "municipio_ibge": municipio_ibge,
                "objeto": c.get("objeto"),
                "processo": c.get("processo"),
                "valor_utilizado": e.get("valor_utilizado"),
                "valor_convenio": c.get("valor_convenio"),
                "vigencia_inicio": vig_inicio,
                "vigencia_fim": vig_fim,
                "origem_fonte": "SIGCON-MT",
            })

    # agregado: soma valor_utilizado por (parlamentar, numero_emenda, ano).
    # município/objeto só sobrevivem quando a emenda tem 1 única aplicação —
    # com N aplicações não existe 1 valor honesto pra esses campos.
    agregados: dict[tuple, dict] = {}
    contagem: dict[tuple, int] = {}
    for a in aplicacoes:
        chave = (a["parlamentar_nome"], a["numero_emenda_origem"])
        contagem[chave] = contagem.get(chave, 0) + 1
    for a in aplicacoes:
        chave = (a["parlamentar_nome"], a["numero_emenda_origem"])
        if chave not in agregados:
            agregados[chave] = {
                "uf": UF,
                "ano_orcamento": ano,
                "numero_emenda": a["numero_emenda"],
                "numero_emenda_origem": a["numero_emenda_origem"],
                "politico_id": a["politico_id"],
                "parlamentar_nome": a["parlamentar_nome"],
                "valor_pago": 0.0,
                "municipio_ibge": a["municipio_ibge"] if contagem[chave] == 1 else None,
                "objeto": a["objeto"] if contagem[chave] == 1 else None,
                "n_aplicacoes": contagem[chave],
                "origem_fonte": "SIGCON-MT",
            }
        agregados[chave]["valor_pago"] += float(a["valor_utilizado"] or 0)

    return {"aplicacoes": aplicacoes, "agregado": list(agregados.values())}


def main() -> None:
    ap = argparse.ArgumentParser(description="Agent B — Normalizador ALMT/SIGCON Emendas MT")
    ap.add_argument("--ano", type=int)
    ap.add_argument("--todos", action="store_true")
    args = ap.parse_args()

    if not args.ano and not args.todos:
        ap.error("passe --ano AAAA (teste) ou --todos")

    log("carregando índices de referência (deputados MT, municípios MT)...")
    idx_dep = _carregar_indice_deputados()
    idx_mun = _carregar_indice_municipios()

    if args.ano:
        bronzes = [BRONZE_DIR / f"almt_sigcon_{args.ano}_bronze.json"]
    else:
        bronzes = sorted(BRONZE_DIR.glob("almt_sigcon_*_bronze.json"))

    stats = {"match": {}}
    total_apl = total_agr = 0
    for bp in bronzes:
        if not bp.exists():
            log(f"⚠️  {bp.name} não encontrado — rode Agent A primeiro")
            continue
        resultado = processar_ano(bp, idx_dep, idx_mun, stats)
        stem = bp.stem.replace("_bronze", "")
        with open(PRATA_DIR / f"{stem}_prata.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False)
        total_apl += len(resultado["aplicacoes"])
        total_agr += len(resultado["agregado"])
        log(f"  ✅ {stem}: {len(resultado['aplicacoes'])} aplicações, {len(resultado['agregado'])} emendas agregadas")

    pct_match = round(
        100 * (stats["match"].get("exato", 0) + stats["match"].get("fuzzy", 0))
        / max(sum(stats["match"].values()), 1), 1
    )
    log(f"\n✅ Agent B concluído: {total_apl:,} aplicações, {total_agr:,} emendas agregadas | "
        f"match politico_id: {stats['match']} ({pct_match}%)")


if __name__ == "__main__":
    main()
