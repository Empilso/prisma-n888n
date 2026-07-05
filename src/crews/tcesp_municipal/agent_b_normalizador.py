#!/usr/bin/env python3
"""
🧪 AGENT-B: NORMALIZADOR TCE-SP — Match slug TCE-SP × código IBGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT:  data/raw/tcesp/bronze/municipios_{YYYY-MM-DD}_bronze.json
OUTPUT: data/raw/tcesp/prata/municipios_{YYYY-MM-DD}_prata.json
        data/raw/tcesp/rejeitados/municipios_{YYYY-MM-DD}_rejeitados.json
FUNÇÃO: Normaliza nomes, cruza cada slug do TCE-SP com a tabela
        `municipios` (IBGE, uf=SP) e classifica o match:
          exato  — slugify(nome IBGE) == slug TCE-SP (confidence 1.0)
          fuzzy  — melhor similaridade >= 0.90 (confidence = ratio)
          sem_match — vai pra rejeitados com motivo

REGRA DE OURO: sem match confiável, o município NÃO segue pra carga.
Melhor faltar do que associar dado fiscal à cidade errada.

USO:
    python agent_b_normalizador.py
"""

import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime, timezone

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

VERSAO = "v1.0"
FUZZY_MIN = 0.90

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina no ambiente ou no .env da raiz do projeto")

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "prisma_data",
    "user": "postgres",
    "password": DB_PASSWORD,
}

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/raw/tcesp/bronze"
PRATA_DIR = BASE_DIR / "data/raw/tcesp/prata"
REJEITADOS_DIR = BASE_DIR / "data/raw/tcesp/rejeitados"
PRATA_DIR.mkdir(parents=True, exist_ok=True)
REJEITADOS_DIR.mkdir(parents=True, exist_ok=True)

C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

def ok(t): print(f"{C_GREEN}✅ {t}{C_END}")
def info(t): print(f"{C_CYAN}🔹 {t}{C_END}")
def warn(t): print(f"{C_YELLOW}⚠️  {t}{C_END}")
def erro(t): print(f"{C_RED}❌ {t}{C_END}")


def slugify(nome: str) -> str:
    """Mesma convenção de slug do TCE-SP: minúsculo, sem acento, hífens."""
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def carregar_ibge_sp():
    """Lê municípios SP da tabela `municipios` (base IBGE já carregada)."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id_ibge, nome FROM municipios WHERE uf = 'SP'")
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        raise RuntimeError("Tabela municipios não tem SP — rode a crew ibge_municipios antes")
    return [{"id_ibge": r[0].strip(), "nome": r[1], "slug": slugify(r[1])} for r in rows]


def main():
    print(f"\n{C_BOLD}AGENT-B {VERSAO} — NORMALIZADOR / MATCH TCE-SP × IBGE{C_END}")
    inicio = datetime.now()
    data_exec = inicio.strftime("%Y-%m-%d")

    bronzes = sorted(BRONZE_DIR.glob("municipios_*_bronze.json"),
                     key=lambda f: f.stat().st_mtime, reverse=True)
    if not bronzes:
        erro(f"Nenhum Bronze em {BRONZE_DIR} — rode agent_a_coletor.py antes")
        raise SystemExit(1)

    bronze_path = bronzes[0]
    info(f"Bronze: {bronze_path.name}")
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)
    records = bronze["records"]
    info(f"Municípios TCE-SP no Bronze: {len(records)}")

    ibge_sp = carregar_ibge_sp()
    info(f"Municípios SP na base IBGE: {len(ibge_sp)}")
    ibge_por_slug = {m["slug"]: m for m in ibge_sp}

    dt_extracao = bronze["meta"]["data_extracao"]
    prata, rejeitados = [], []
    n_exato = n_fuzzy = 0
    slugs_tcesp = set()

    for rec in records:
        slug = (rec.get("municipio") or "").strip().lower()
        nome_ext = (rec.get("municipio_extenso") or "").strip()
        if not slug:
            rejeitados.append({**rec, "motivo_rejeicao": "slug vazio no payload TCE-SP"})
            continue
        if slug in slugs_tcesp:
            rejeitados.append({**rec, "motivo_rejeicao": f"slug duplicado no payload: {slug}"})
            continue
        slugs_tcesp.add(slug)

        base = {
            "slug_tcesp": slug,
            "nome_tcesp": nome_ext or slug,
            "uf": "SP",
            "dt_extracao": dt_extracao,
            "raw_payload": rec,
        }

        # 1) match exato por slug (tenta o slug do TCE e o slug do nome extenso)
        candidato = ibge_por_slug.get(slug) or ibge_por_slug.get(slugify(nome_ext))
        if candidato:
            prata.append({**base, "id_ibge": candidato["id_ibge"],
                          "nome_ibge": candidato["nome"],
                          "match_status": "exato", "match_confidence": 1.0})
            n_exato += 1
            continue

        # 2) fuzzy: melhor similaridade de slug contra toda a base SP
        melhor, melhor_ratio = None, 0.0
        for m in ibge_sp:
            ratio = SequenceMatcher(None, slug, m["slug"]).ratio()
            if ratio > melhor_ratio:
                melhor, melhor_ratio = m, ratio
        if melhor and melhor_ratio >= FUZZY_MIN:
            prata.append({**base, "id_ibge": melhor["id_ibge"],
                          "nome_ibge": melhor["nome"],
                          "match_status": "fuzzy",
                          "match_confidence": round(melhor_ratio, 3)})
            n_fuzzy += 1
            warn(f"fuzzy: {slug} → {melhor['nome']} ({melhor['id_ibge']}) ratio={melhor_ratio:.3f}")
            continue

        rejeitados.append({**rec, "motivo_rejeicao":
                           f"sem match IBGE (melhor: {melhor['slug'] if melhor else '-'} ratio={melhor_ratio:.3f})"})

    # municípios IBGE-SP que não apareceram no TCE-SP (ex.: capital → TCM-SP)
    matched_ibge = {p["id_ibge"] for p in prata}
    ausentes = [m for m in ibge_sp if m["id_ibge"] not in matched_ibge]

    prata_file = PRATA_DIR / f"municipios_{data_exec}_prata.json"
    with open(prata_file, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "bronze_origem": bronze_path.name,
                "data_normalizacao": datetime.now(timezone.utc).isoformat(),
                "total_prata": len(prata),
                "match_exato": n_exato,
                "match_fuzzy": n_fuzzy,
                "rejeitados": len(rejeitados),
                "ibge_sp_ausentes_no_tcesp": [
                    {"id_ibge": m["id_ibge"], "nome": m["nome"]} for m in ausentes
                ],
                "versao_agente": VERSAO,
            },
            "records": prata,
        }, f, ensure_ascii=False, indent=2)

    if rejeitados:
        rej_file = REJEITADOS_DIR / f"municipios_{data_exec}_rejeitados.json"
        with open(rej_file, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False, indent=2)
        warn(f"{len(rejeitados)} rejeitados → {rej_file.name}")

    print(f"\n{C_BOLD}── RELATÓRIO DE MATCH ──{C_END}")
    ok(f"exato: {n_exato}  |  fuzzy: {n_fuzzy}  |  rejeitados: {len(rejeitados)}")
    if ausentes:
        warn(f"IBGE-SP sem par no TCE-SP ({len(ausentes)}): "
             + ", ".join(f"{m['nome']} ({m['id_ibge']})" for m in ausentes[:10]))
        info("Nota: a capital São Paulo é fiscalizada pelo TCM-SP — ausência esperada.")
    ok(f"Prata salvo: {prata_file.name}")
    print(f"\n{C_GREEN}{C_BOLD}[AGENT-B DONE] ✅{C_END}\n")


if __name__ == "__main__":
    main()
