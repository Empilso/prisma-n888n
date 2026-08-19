#!/usr/bin/env python3
"""
🌎 AGENT-A: COLETOR IBGE — Municípios Brasileiros
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FONTE:  Arquivo local municipios.json (5.571 municípios)
OUTPUT: data/raw/ibge/municipios_{YYYY-MM-DD}_bronze.json
FUNÇÃO: Lê arquivo local, salva Bronze imutável com SHA256

USO:
    python agent_a_coletor.py
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# ── Configurações ─────────────────────────────────────────────────────────────
VERSAO = "v1.0"
# Caminho absoluto para o arquivo de origem
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Fonte unificada em 2026-08-19: era caminho absoluto da maquina local
# apontando pro projeto descontinuado PRISMA-DADOS2 (quebrava em qualquer
# outra maquina, inclusive o VPS). Copiado pra dentro da propria crew,
# seguindo a mesma convencao de BASE_DIR que o resto do arquivo ja usa.
ARQUIVO_ORIGEM = BASE_DIR / "data/ibge_municipios/dados_brutos/municipios.json"
BRONZE_DIR = BASE_DIR / "data/raw/ibge/bronze"
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

# ── Bronze: Leitura do arquivo local ─────────────────────────────────────────
def ler_arquivo_local():
    """Lê JSON do arquivo local. Retorna (data, sha256)"""
    if not ARQUIVO_ORIGEM.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {ARQUIVO_ORIGEM}")
    
    info(f"Lendo arquivo: {ARQUIVO_ORIGEM.name}")
    
    with open(ARQUIVO_ORIGEM, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    payload_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    sha256 = hashlib.sha256(payload_str.encode()).hexdigest()
    
    ok(f"{len(data)} municípios carregados")
    return data, sha256

def salvar_bronze(data, sha256, data_exec):
    """Salva raw JSON (imutável)"""
    bronze_file = BRONZE_DIR / f"municipios_{data_exec}_bronze.json"
    
    if bronze_file.exists():
        warn(f"Bronze já existe: {bronze_file.name} (pulando gravação)")
        return bronze_file
    
    with open(bronze_file, 'w', encoding='utf-8') as f:
        json.dump({
            "meta": {
                "fonte": str(ARQUIVO_ORIGEM),
                "portal": "IBGE — Malha Municipal",
                "data_extracao": datetime.now(timezone.utc).isoformat(),
                "total_registros": len(data),
                "sha256": sha256,
                "versao_agente": VERSAO
            },
            "records": data
        }, f, ensure_ascii=False, indent=2)
    
    info(f"Bronze salvo: {bronze_file.name} (sha256: {sha256[:8]}...)")
    return bronze_file

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print_header(f"AGENT-A {VERSAO} — COLETOR IBGE")
    
    inicio = datetime.now()
    data_exec = inicio.strftime("%Y-%m-%d")
    
    try:
        # Bronze
        raw_data, sha256 = ler_arquivo_local()
        bronze_file = salvar_bronze(raw_data, sha256, data_exec)
        
        duracao = (datetime.now() - inicio).total_seconds()
        ok(f"Concluído em {duracao:.1f}s")
        print(f"\n{C_GREEN}{C_BOLD}[AGENT-A DONE] ✅{C_END}\n")
        
    except Exception as e:
        erro(f"Erro fatal: {e}")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
