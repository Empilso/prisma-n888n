#!/usr/bin/env python3
"""
🔁 FORCE YEAR — Re-download forçado de um ano específico
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO: Limpa os arquivos Bronze e Prata de um ano e
        dispara o pipeline completo: Bronze → Prata → Ouro

USO:
    python force_year.py --year 2022
    python force_year.py --year 2022 --skip-ouro
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# --- Estética N888N ─────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

BASE_DIR   = Path(__file__).resolve().parent.parent.parent
BRONZE_DIR = BASE_DIR / "data" / "saida" / "bronze"
PRATA_DIR  = BASE_DIR / "data" / "saida" / "prata"
OURO_DIR   = BASE_DIR / "data" / "saida" / "ouro"
AGENTS_DIR = Path(__file__).resolve().parent


def banner(year: str):
    print(f"\n{C_PURPLE}╔══════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}   🔁 FORCE YEAR — RE-DOWNLOAD FORÇADO: {year}   {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚══════════════════════════════════════════════════════╝{C_END}\n")
    sys.stdout.flush()


def deletar_arquivos_ano(year: str, dry_run: bool = False) -> list:
    """Remove todos os arquivos Bronze, Prata e Ouro do ano especificado."""
    padroes = [
        BRONZE_DIR / f"alba_{year}_checkpoint.json",
        BRONZE_DIR / f"alba_{year}_bronze.json",
        PRATA_DIR  / f"alba_{year}_prata.json",
    ]
    # Ouro usa data no nome — glob dinâmico
    padroes_ouro = list(OURO_DIR.glob(f"verbas_{year}_gold_*.json"))

    todos = [p for p in padroes if p.exists()] + padroes_ouro

    if not todos:
        print(f"{C_YELLOW}⚠️  Nenhum arquivo encontrado para o ano {year}. Pipeline rodará do zero.{C_END}")
        return []

    print(f"{C_CYAN}🗑️  Arquivos que serão deletados:{C_END}")
    for p in todos:
        size_kb = round(p.stat().st_size / 1024, 1)
        print(f"   • {p.name} ({size_kb} KB)")

    if dry_run:
        print(f"\n{C_YELLOW}[DRY RUN] Nenhum arquivo foi deletado.{C_END}")
        return todos

    for p in todos:
        p.unlink()
        print(f"   {C_RED}✗ Deletado:{C_END} {p.name}")

    print(f"\n{C_GREEN}✅ Limpeza concluída! {len(todos)} arquivo(s) removido(s).{C_END}\n")
    sys.stdout.flush()
    return todos


def rodar_agente(script: str, args_extra: list, label: str) -> int:
    """Executa um agente Python como subprocess e retorna o exit code."""
    cmd = [sys.executable, str(AGENTS_DIR / script)] + args_extra
    print(f"\n{C_CYAN}━━━ [{label}] Iniciando...{C_END}")
    print(f"   CMD: {' '.join(cmd)}")
    sys.stdout.flush()

    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        print(f"{C_RED}❌ [{label}] FALHOU com exit code {result.returncode}{C_END}")
    else:
        print(f"{C_GREEN}✅ [{label}] Concluído com sucesso!{C_END}")
    sys.stdout.flush()
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Force Year: Re-download de um ano específico")
    parser.add_argument("--year",      type=str, required=True, help="Ano alvo (ex: 2022)")
    parser.add_argument("--dry-run",   action="store_true",    help="Simula sem deletar ou executar")
    parser.add_argument("--skip-ouro", action="store_true",    help="Pula etapa Ouro (Ronaldo Gold)")
    parser.add_argument("--only-clean",action="store_true",    help="Apenas limpa os arquivos, sem rodar pipeline")
    args = parser.parse_args()

    year = args.year
    banner(year)

    # ── 1. Limpa arquivos ────────────────────────────────────
    print(f"{C_WHITE}[PASSO 1/4] Limpando arquivos do ano {year}...{C_END}")
    deletar_arquivos_ano(year, dry_run=args.dry_run)

    if args.only_clean or args.dry_run:
        print(f"{C_YELLOW}🛑 Modo {'--dry-run' if args.dry_run else '--only-clean'}: Pipeline não foi executado.{C_END}")
        sys.exit(0)

    # ── 2. Bronze (Zorg-Romário / agent_1_batch) ─────────────
    # O agent_1_batch aceita ANO_ALVO via env ou --year
    print(f"\n{C_WHITE}[PASSO 2/4] Coletando Bronze ({year}) via Agent 1 Batch...{C_END}")
    # Tenta o batch wrapper, que aceita --year diretamente
    bronze_scripts = [
        ("agent_1_batch.py",   ["--year", year]),
        ("agent_1_wrapper.py", ["--year", year]),
    ]
    bronze_ok = False
    for script, extra in bronze_scripts:
        if (AGENTS_DIR / script).exists():
            rc = rodar_agente(script, extra, f"BRONZE {year}")
            if rc == 0:
                bronze_ok = True
                break

    if not bronze_ok:
        print(f"{C_RED}❌ Falha na etapa Bronze. Pipeline interrompido.{C_END}")
        sys.exit(1)

    # ── 3. Prata (Xylos-Bebeto / agent_2_chunker) ────────────
    print(f"\n{C_WHITE}[PASSO 3/4] Purificando Prata ({year}) via Agent 2 Chunker...{C_END}")
    rc = rodar_agente("agent_2_chunker.py", ["--year", year], f"PRATA {year}")
    if rc != 0:
        print(f"{C_RED}❌ Falha na etapa Prata. Ouro cancelado.{C_END}")
        sys.exit(1)

    # ── 4. Ouro (Ronaldo Gold) ───────────────────────────────
    if args.skip_ouro:
        print(f"\n{C_YELLOW}[PASSO 4/4] Ouro ignorado (--skip-ouro).{C_END}")
    else:
        print(f"\n{C_WHITE}[PASSO 4/4] Gerando Ouro ({year}) via Ronaldo Gold...{C_END}")
        rc = rodar_agente("agent_ronaldo_gold.py", ["--year", year], f"OURO {year}")
        if rc != 0:
            print(f"{C_RED}❌ Falha na etapa Ouro.{C_END}")
            sys.exit(1)

    # ── Resumo ───────────────────────────────────────────────
    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}🏆 FORCE YEAR {year} CONCLUÍDO!{C_END}")
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"{C_WHITE}   Finalizado em: {hoje}{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
