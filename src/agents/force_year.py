#!/usr/bin/env python3
"""
🔁 FORCE YEAR — Re-download forçado ou Smart Resume de um ano específico
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO: Gerenciar o pipeline Bronze → Prata → Ouro de um ano específico.

MODOS:
  --smart   (RECOMENDADO) Aproveita o Bronze existente, baixa SÓ o que falta.
            Não deleta nada. Usa o smart sync do scraper_alba (por ID único).

  (padrão)  Deleta Bronze + Prata + Ouro e refaz tudo do zero.

USO:
    python force_year.py --year 2022 --smart          # continua de onde parou ✅
    python force_year.py --year 2022                  # deleta tudo e refaz
    python force_year.py --year 2022 --skip-ouro      # para na Prata
    python force_year.py --year 2022 --only-clean     # só limpa, sem pipeline
    python force_year.py --year 2022 --dry-run        # simula sem executar nada
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# --- Estética N888N ─────────────────────────────────────────────────────────
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


def banner(year: str, smart: bool):
    modo = f"{C_GREEN}SMART RESUME (continua de onde parou)" if smart else f"{C_RED}FORCE RESET (deleta e refaz do zero)"
    print(f"\n{C_PURPLE}╔══════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}        🔁 FORCE YEAR {year} — PIPELINE ORQUESTRADOR        {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚══════════════════════════════════════════════════════════════╝{C_END}")
    print(f"   Modo: {modo}{C_END}\n")
    sys.stdout.flush()


# ── SMART: inspeciona o que já existe ────────────────────────────────────────
def inspecionar_bronze(year: str) -> dict:
    """Lê o checkpoint Bronze existente e retorna um resumo do estado atual."""
    checkpoint = BRONZE_DIR / f"alba_{year}_checkpoint.json"
    bronze     = BRONZE_DIR / f"alba_{year}_bronze.json"

    arquivo = bronze if bronze.exists() else (checkpoint if checkpoint.exists() else None)

    if not arquivo:
        return {"existe": False, "total": 0, "arquivo": None}

    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records", data) if isinstance(data, dict) else data
        last_page = data.get("last_page", "?") if isinstance(data, dict) else "?"
        return {
            "existe": True,
            "total": len(records),
            "last_page": last_page,
            "arquivo": arquivo.name,
            "size_kb": round(arquivo.stat().st_size / 1024, 1),
        }
    except Exception as e:
        return {"existe": False, "total": 0, "arquivo": None, "erro": str(e)}


# ── FORCE: deleta arquivos do ano ─────────────────────────────────────────────
def deletar_arquivos_ano(year: str, dry_run: bool = False) -> list:
    """Remove todos os arquivos Bronze, Prata e Ouro do ano especificado."""
    padroes = [
        BRONZE_DIR / f"alba_{year}_checkpoint.json",
        BRONZE_DIR / f"alba_{year}_bronze.json",
        PRATA_DIR  / f"alba_{year}_prata.json",
    ]
    padroes_ouro = list(OURO_DIR.glob(f"verbas_{year}_gold_*.json"))
    todos = [p for p in padroes if p.exists()] + padroes_ouro

    if not todos:
        print(f"{C_YELLOW}⚠️  Nenhum arquivo encontrado para o ano {year}. Pipeline rodará do zero.{C_END}")
        return []

    print(f"{C_CYAN}🗑️  Arquivos que serão deletados:{C_END}")
    for p in todos:
        print(f"   • {p.name} ({round(p.stat().st_size / 1024, 1)} KB)")

    if dry_run:
        print(f"\n{C_YELLOW}[DRY RUN] Nenhum arquivo foi deletado.{C_END}")
        return todos

    for p in todos:
        p.unlink()
        print(f"   {C_RED}✗ Deletado:{C_END} {p.name}")

    print(f"\n{C_GREEN}✅ Limpeza concluída! {len(todos)} arquivo(s) removido(s).{C_END}\n")
    sys.stdout.flush()
    return todos


# ── Executor de agentes ───────────────────────────────────────────────────────
def rodar_agente(script: str, args_extra: list, label: str, dry_run: bool = False) -> int:
    """Executa um agente Python como subprocess e retorna o exit code."""
    cmd = [sys.executable, str(AGENTS_DIR / script)] + args_extra
    print(f"\n{C_CYAN}━━━ [{label}] Iniciando...{C_END}")
    print(f"   CMD: {' '.join(cmd)}")
    sys.stdout.flush()

    if dry_run:
        print(f"   {C_YELLOW}[DRY RUN] Comando não executado.{C_END}")
        return 0

    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        print(f"{C_RED}❌ [{label}] FALHOU com exit code {result.returncode}{C_END}")
    else:
        print(f"{C_GREEN}✅ [{label}] Concluído com sucesso!{C_END}")
    sys.stdout.flush()
    return result.returncode


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Force Year: Orquestrador de pipeline por ano")
    parser.add_argument("--year",       type=str, required=True,  help="Ano alvo (ex: 2022)")
    parser.add_argument("--smart",      action="store_true",       help="Resume inteligente: aproveita Bronze existente e baixa só o que falta")
    parser.add_argument("--dry-run",    action="store_true",       help="Simula sem deletar ou executar nada")
    parser.add_argument("--skip-ouro",  action="store_true",       help="Pula etapa Ouro (Ronaldo Gold)")
    parser.add_argument("--only-clean", action="store_true",       help="Apenas limpa os arquivos, sem rodar pipeline")
    args = parser.parse_args()

    year = args.year
    banner(year, args.smart)

    # ────────────────────────────────────────────────────────────────────────
    # MODO SMART: inspeciona o que já existe, não deleta nada
    # ────────────────────────────────────────────────────────────────────────
    if args.smart:
        estado = inspecionar_bronze(year)
        if estado["existe"]:
            print(f"{C_WHITE}[SMART] 🧠 Bronze encontrado:{C_END}")
            print(f"   • Arquivo  : {estado['arquivo']} ({estado['size_kb']} KB)")
            print(f"   • Registros: {estado['total']}")
            print(f"   • Última pág: {estado.get('last_page', '?')}")
            print(f"\n{C_CYAN}   → O scraper vai carregar esses IDs e baixar APENAS os registros faltantes.{C_END}\n")
        else:
            print(f"{C_YELLOW}[SMART] ⚠️  Nenhum Bronze encontrado. Download completo será feito.{C_END}\n")
        sys.stdout.flush()

        if args.only_clean:
            print(f"{C_YELLOW}🛑 --only-clean ignorado em modo --smart (nada a deletar).{C_END}")
            sys.exit(0)

        # Bronze com --smart: passa --smart para o wrapper/batch
        # O scraper_alba.py usa smart=True para carregar IDs existentes e pular
        print(f"{C_WHITE}[PASSO 1/3] Bronze Smart Resume ({year})...{C_END}")

        # Tenta agent_1_wrapper.py com --smart, depois agent_1_batch.py
        # O agent_1_batch não aceita --smart por arg, então usamos o scraper diretamente
        scraper_path = BASE_DIR / "src" / "utils" / "scraper_alba.py"
        if scraper_path.exists():
            rc = rodar_agente(
                str(scraper_path.relative_to(AGENTS_DIR.parent)),  # relativo ao src/
                ["--ano", year, "--smart"],
                f"BRONZE SMART {year}",
                dry_run=args.dry_run,
            )
            # Ajuste: rodar via caminho absoluto se necessário
            if rc != 0:
                cmd_abs = [sys.executable, str(scraper_path), "--ano", year, "--smart"]
                print(f"\n{C_CYAN}↩ Tentando caminho absoluto...{C_END}")
                if not args.dry_run:
                    import subprocess as sp
                    r = sp.run(cmd_abs, cwd=str(BASE_DIR))
                    rc = r.returncode
        else:
            # Fallback: chama o scraper diretamente via import
            print(f"{C_CYAN}   Importando scraper_alba diretamente...{C_END}")
            if not args.dry_run:
                sys.path.insert(0, str(BASE_DIR / "src"))
                from utils.scraper_alba import scrape_lista_completa
                checkpoint_dir = str(BRONZE_DIR)
                records = scrape_lista_completa(
                    ano=int(year),
                    smart=True,
                    resume=False,
                    checkpoint_dir=checkpoint_dir,
                )
                print(f"{C_GREEN}✅ Bronze Smart: {len(records)} registros totais.{C_END}")
            rc = 0

        if rc != 0:
            print(f"{C_RED}❌ Falha no Bronze Smart. Pipeline interrompido.{C_END}")
            sys.exit(1)

    # ────────────────────────────────────────────────────────────────────────
    # MODO FORCE (padrão): deleta tudo e refaz do zero
    # ────────────────────────────────────────────────────────────────────────
    else:
        print(f"{C_WHITE}[PASSO 1/4] Limpando arquivos do ano {year}...{C_END}")
        deletar_arquivos_ano(year, dry_run=args.dry_run)

        if args.only_clean or args.dry_run:
            print(f"{C_YELLOW}🛑 Modo {'--dry-run' if args.dry_run else '--only-clean'}: Pipeline não foi executado.{C_END}")
            sys.exit(0)

        print(f"\n{C_WHITE}[PASSO 2/4] Coletando Bronze ({year}) via Agent 1 Batch...{C_END}")
        bronze_scripts = [
            ("agent_1_batch.py",   ["--year", year]),
            ("agent_1_wrapper.py", ["--year", year]),
        ]
        bronze_ok = False
        for script, extra in bronze_scripts:
            if (AGENTS_DIR / script).exists():
                rc = rodar_agente(script, extra, f"BRONZE {year}", dry_run=args.dry_run)
                if rc == 0:
                    bronze_ok = True
                    break

        if not bronze_ok:
            print(f"{C_RED}❌ Falha na etapa Bronze. Pipeline interrompido.{C_END}")
            sys.exit(1)

    # ── Prata (comum aos dois modos) ─────────────────────────────────────────
    passo_prata = "2" if args.smart else "3"
    print(f"\n{C_WHITE}[PASSO {passo_prata}/3] Purificando Prata ({year}) via Agent 2 Chunker...{C_END}")
    rc = rodar_agente("agent_2_chunker.py", ["--year", year], f"PRATA {year}", dry_run=args.dry_run)
    if rc != 0:
        print(f"{C_RED}❌ Falha na etapa Prata. Ouro cancelado.{C_END}")
        sys.exit(1)

    # ── Ouro (comum aos dois modos) ──────────────────────────────────────────
    passo_ouro = "3" if args.smart else "4"
    if args.skip_ouro:
        print(f"\n{C_YELLOW}[PASSO {passo_ouro}/3] Ouro ignorado (--skip-ouro).{C_END}")
    else:
        print(f"\n{C_WHITE}[PASSO {passo_ouro}/3] Gerando Ouro ({year}) via Ronaldo Gold...{C_END}")
        rc = rodar_agente("agent_ronaldo_gold.py", ["--year", year], f"OURO {year}", dry_run=args.dry_run)
        if rc != 0:
            print(f"{C_RED}❌ Falha na etapa Ouro.{C_END}")
            sys.exit(1)

    # ── Resumo ────────────────────────────────────────────────────────────────
    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}🏆 FORCE YEAR {year} CONCLUÍDO!{C_END}")
    print(f"{C_WHITE}   Modo       : {'SMART RESUME' if args.smart else 'FORCE RESET'}")
    print(f"   Finalizado : {datetime.now().strftime('%Y-%m-%d %H:%M')}{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
