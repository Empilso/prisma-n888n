#!/usr/bin/env python3
"""
🏛️ AGENT-A: COLETOR TCE-SP — Cadastro de Municípios
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FONTE:  https://transparencia.tce.sp.gov.br/api/json/municipios
OUTPUT: data/raw/tcesp/bronze/municipios_{YYYY-MM-DD}_bronze.json
FUNÇÃO: Coleta a lista oficial de municípios fiscalizados pelo TCE-SP
        (slug + nome extenso) e salva Bronze imutável com SHA256.

NOTA:   A capital São Paulo é fiscalizada pelo TCM-SP, não pelo TCE-SP —
        é esperado que ela NÃO apareça nesta lista (exceção documentada).

USO:
    python agent_a_coletor.py
"""

import json
import hashlib
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

# ── Configurações ─────────────────────────────────────────────────────────────
VERSAO = "v1.0"
URL_MUNICIPIOS = "https://transparencia.tce.sp.gov.br/api/json/municipios"
TIMEOUT = 30
TENTATIVAS = 3

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/raw/tcesp/bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

# ── Estética Terminal ─────────────────────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

def print_header(title: str):
    print(f"\n{C_PURPLE}╔{'═'*68}╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN} {title.center(66)} {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚{'═'*68}╝{C_END}")

def ok(t): print(f"{C_GREEN}✅ {t}{C_END}")
def info(t): print(f"{C_CYAN}🔹 {t}{C_END}")
def warn(t): print(f"{C_YELLOW}⚠️  {t}{C_END}")
def erro(t): print(f"{C_RED}❌ {t}{C_END}")

# ── Bronze: Coleta da API ─────────────────────────────────────────────────────
def coletar_municipios():
    """GET na API do TCE-SP com retry. Retorna (data, sha256)."""
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            info(f"GET {URL_MUNICIPIOS} (tentativa {tentativa}/{TENTATIVAS})")
            resp = requests.get(URL_MUNICIPIOS, timeout=TIMEOUT, headers={
                "User-Agent": "prisma-n888n-etl/1.0"
            })
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or not data:
                raise ValueError(f"Payload inesperado: {type(data)} len={len(data) if isinstance(data, list) else 'n/a'}")
            payload_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            sha256 = hashlib.sha256(payload_str.encode()).hexdigest()
            ok(f"{len(data)} municípios recebidos do TCE-SP")
            return data, sha256
        except Exception as e:
            ultimo_erro = e
            warn(f"Falha: {e}")
            if tentativa < TENTATIVAS:
                espera = 2 ** tentativa
                info(f"Aguardando {espera}s antes de tentar de novo…")
                time.sleep(espera)
    raise RuntimeError(f"Coleta falhou após {TENTATIVAS} tentativas: {ultimo_erro}")

def salvar_bronze(data, sha256, data_exec):
    """Salva raw JSON (imutável)."""
    bronze_file = BRONZE_DIR / f"municipios_{data_exec}_bronze.json"

    if bronze_file.exists():
        warn(f"Bronze já existe: {bronze_file.name} (pulando gravação)")
        return bronze_file

    with open(bronze_file, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "fonte": URL_MUNICIPIOS,
                "portal": "TCE-SP — Transparência Municipal",
                "data_extracao": datetime.now(timezone.utc).isoformat(),
                "total_registros": len(data),
                "sha256": sha256,
                "versao_agente": VERSAO,
            },
            "records": data,
        }, f, ensure_ascii=False, indent=2)

    info(f"Bronze salvo: {bronze_file.name} (sha256: {sha256[:8]}…)")
    return bronze_file

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print_header(f"AGENT-A {VERSAO} — COLETOR TCE-SP MUNICÍPIOS")

    inicio = datetime.now()
    data_exec = inicio.strftime("%Y-%m-%d")

    try:
        raw_data, sha256 = coletar_municipios()
        salvar_bronze(raw_data, sha256, data_exec)

        duracao = (datetime.now() - inicio).total_seconds()
        ok(f"Concluído em {duracao:.1f}s")
        print(f"\n{C_GREEN}{C_BOLD}[AGENT-A DONE] ✅{C_END}\n")

    except Exception as e:
        erro(f"Erro fatal: {e}")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
