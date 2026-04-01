#!/usr/bin/env python3
"""
🇧🇷 CREW PELÉ v1.0 — ORQUESTRADOR DE EMENDAS FEDERAIS BA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Orquestrar toda a pipeline de Emendas Federais BA,
         encadeando Pelé-A → Pelé-B → Pelé-C → Pelé-D em sequência
         controlada, com checkpoints, dry-run e relatório final.

FLUXO:
  [CSV LOCAL]
      ↓ Pelé-A: Ingestor  → Bronze JSON
      ↓ Pelé-B: Parser    → Prata JSON  (normalizado)
      ↓ Pelé-C: Águia     → Ouro JSON   (enriquecido + validado)
      ↓ Pelé-D: Loader    → Supabase DB (tabela emendas_federais)

USO:
    # Pipeline completa
    python crew_pele.py --arquivo /path/emendas_ba_2024.csv --ano 2024

    # Dry-run (valida sem gravar no banco)
    python crew_pele.py --arquivo /path/emendas_ba_2024.csv --ano 2024 --dry-run

    # Rodar apenas a partir de uma fase (se Bronze já existe)
    python crew_pele.py --ano 2024 --from-fase B

    # Rodar só até uma fase (sem subir para o banco)
    python crew_pele.py --arquivo /path/emendas_ba_2024.csv --ano 2024 --ate-fase C

    # Forçar re-processamento mesmo que arquivos intermediários existam
    python crew_pele.py --arquivo /path/emendas_ba_2024.csv --ano 2024 --force

SAÍDA ESPERADA (modo normal):
    data/saida/emendas_federais/raw/emendas_federais_ba_{ano}_bronze.json
    data/saida/emendas_federais/prata/emendas_federais_ba_{ano}_prata.json
    data/saida/emendas_federais/ouro/emendas_federais_ba_{ano}_ouro.json
    → Supabase: tabela emendas_federais (upsert por prisma_id)
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

VERSAO = "v1.0-prisma-crew-pele"

# ── Caminhos ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent          # src/
AGENTS_DIR  = BASE_DIR / "agents"
DATA_DIR    = BASE_DIR.parent / "data" / "saida" / "emendas_federais"

FASES_ORDEM = ["A", "B", "C", "D"]
FASES_NOME  = {
    "A": "Pelé-A  │ Ingestor CSV → Bronze",
    "B": "Pelé-B  │ Parser       → Prata",
    "C": "Pelé-C  │ Águia        → Ouro",
    "D": "Pelé-D  │ Loader       → Supabase",
}
FASES_SCRIPT = {
    "A": AGENTS_DIR / "agent_pele_a_ingestor.py",
    "B": AGENTS_DIR / "agent_pele_b_parser.py",
    "C": AGENTS_DIR / "agent_pele_c_aguia.py",
    "D": AGENTS_DIR / "agent_pele_d_loader.py",
}
FASES_OUTPUT = {
    "A": lambda ano: DATA_DIR / "raw"   / f"emendas_federais_ba_{ano}_bronze.json",
    "B": lambda ano: DATA_DIR / "prata" / f"emendas_federais_ba_{ano}_prata.json",
    "C": lambda ano: DATA_DIR / "ouro"  / f"emendas_federais_ba_{ano}_ouro.json",
    "D": None,  # saída é o banco, não um arquivo
}

# ── Estética Terminal (padrão família Pelé/Zidane) ─────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_BLUE   = "\033[94m"
C_END    = "\033[0m"

def print_banner():
    width = 70
    titulo = f"CREW PELÉ {VERSAO}"
    subtitulo = "PIPELINE EMENDAS FEDERAIS BA — A→B→C→D"
    print(f"\n{C_PURPLE}╔{'═'*(width-2)}╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}{titulo.center(width-2)}{C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}║{C_WHITE}{subtitulo.center(width-2)}{C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚{'═'*(width-2)}╝{C_END}\n")

def print_fase_header(letra: str, dry_run: bool):
    nome = FASES_NOME[letra]
    modo = f"  {C_YELLOW}[DRY-RUN]{C_END}" if dry_run else ""
    print(f"\n{C_BLUE}{'─'*70}{C_END}")
    print(f"{C_BOLD}{C_WHITE}  FASE {letra} │ {nome}{C_END}{modo}")
    print(f"{C_BLUE}{'─'*70}{C_END}")

def print_status(msg: str, status="info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️",
               "process": "⚙️", "skip": "⏭️", "time": "⏱️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED,
               "warn": C_YELLOW, "process": C_PURPLE, "skip": C_BLUE, "time": C_WHITE}
    icon  = icons.get(status, "🔹")
    color = colors.get(status, C_CYAN)
    print(f"{color}{icon} {msg}{C_END}")

def print_relatorio(relatorio: dict):
    width = 70
    print(f"\n{C_GREEN}╔{'═'*(width-2)}╗{C_END}")
    print(f"{C_GREEN}║{C_BOLD}{C_WHITE}{'  RELATÓRIO FINAL — CREW PELÉ'.center(width-2)}{C_END}{C_GREEN}║{C_END}")
    print(f"{C_GREEN}╠{'═'*(width-2)}╣{C_END}")
    for k, v in relatorio.items():
        linha = f"  {k:<25} {v}"
        print(f"{C_GREEN}║{C_WHITE}{linha:<(width-2)}{C_END}{C_GREEN}║{C_END}")
    print(f"{C_GREEN}╚{'═'*(width-2)}╝{C_END}\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def arquivo_existe(fase: str, ano: str) -> bool:
    """Verifica se o arquivo de output da fase já existe."""
    getter = FASES_OUTPUT.get(fase)
    if getter is None:
        return False
    return getter(ano).exists()

def contar_registros(fase: str, ano: str) -> int:
    """Lê o JSON de output e retorna total de registros."""
    getter = FASES_OUTPUT.get(fase)
    if getter is None:
        return 0
    path = getter(ano)
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("total", len(data.get("records", [])))
    except Exception:
        return 0

def montar_cmd(fase: str, ano: str, arquivo: Optional[str], dry_run: bool) -> list:
    """Monta o comando de execução para cada fase."""
    script = str(FASES_SCRIPT[fase])
    cmd = [sys.executable, script]

    if fase == "A":
        if not arquivo:
            raise ValueError("Fase A requer --arquivo (caminho do CSV).")
        cmd += ["--arquivo", arquivo, "--ano", ano]
    else:
        cmd += ["--ano", ano]

    if dry_run:
        cmd.append("--dry-run")

    return cmd

def executar_fase(fase: str, ano: str, arquivo: Optional[str],
                  dry_run: bool, force: bool) -> dict:
    """
    Executa uma fase da pipeline.
    Retorna dict com: {ok, duracao_s, registros, pulada}
    """
    resultado = {"ok": False, "duracao_s": 0.0, "registros": 0, "pulada": False}

    # Verificar se pode pular (output já existe e não é force)
    if fase != "D" and not force and arquivo_existe(fase, ano):
        regs = contar_registros(fase, ano)
        print_status(
            f"Output já existe ({FASES_OUTPUT[fase](ano).name}, {regs} registros). "
            f"Use --force para re-processar.", "skip"
        )
        resultado["ok"]       = True
        resultado["pulada"]   = True
        resultado["registros"] = regs
        return resultado

    # Montar e executar comando
    try:
        cmd = montar_cmd(fase, ano, arquivo, dry_run)
    except ValueError as e:
        print_status(str(e), "error")
        return resultado

    print_status(f"Executando: {' '.join(cmd)}", "process")
    t0 = time.time()

    proc = subprocess.run(cmd, capture_output=False, text=True)

    duracao = round(time.time() - t0, 2)
    resultado["duracao_s"] = duracao

    if proc.returncode == 0:
        resultado["ok"] = True
        if fase != "D":
            resultado["registros"] = contar_registros(fase, ano)
        print_status(f"Fase {fase} concluída em {duracao}s.", "success")
    else:
        print_status(f"Fase {fase} falhou (exit code {proc.returncode}).", "error")

    return resultado


# ── Orquestrador principal ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Crew Pelé v1.0 — Orquestrador de Emendas Federais BA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--arquivo",   type=str,  default=None,
                        help="Caminho do CSV de emendas (obrigatório para Fase A)")
    parser.add_argument("--ano",       type=str,  required=True,
                        help="Ano dos dados (ex: 2024)")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Valida pipeline completa SEM gravar no banco")
    parser.add_argument("--force",     action="store_true",
                        help="Re-processa mesmo que arquivos intermediários existam")
    parser.add_argument("--from-fase", type=str,  default="A", choices=FASES_ORDEM,
                        help="Iniciar a partir desta fase (A/B/C/D)")
    parser.add_argument("--ate-fase",  type=str,  default="D", choices=FASES_ORDEM,
                        help="Parar após esta fase (A/B/C/D)")
    args = parser.parse_args()

    print_banner()

    ts_inicio = datetime.utcnow()
    print_status(f"Ano alvo       : {args.ano}", "info")
    print_status(f"Arquivo CSV    : {args.arquivo or '(não informado — iniciando de fase ' + args.from_fase + ')'}", "info")
    print_status(f"Fases          : {args.from_fase} → {args.ate_fase}", "info")
    print_status(f"Modo           : {'⚠️  DRY-RUN (nenhum dado será gravado no banco)' if args.dry_run else '🚀 PRODUÇÃO'}", "warn" if args.dry_run else "success")
    print_status(f"Force          : {'sim (re-processa tudo)' if args.force else 'não (pula fases prontas)'}", "info")

    # Validar range de fases
    idx_from = FASES_ORDEM.index(args.from_fase)
    idx_ate  = FASES_ORDEM.index(args.ate_fase)
    if idx_from > idx_ate:
        print_status("--from-fase não pode ser posterior a --ate-fase.", "error")
        sys.exit(1)

    fases_rodar = FASES_ORDEM[idx_from : idx_ate + 1]

    # Verificar se Fase A precisa do --arquivo
    if "A" in fases_rodar and not args.arquivo:
        print_status("Fase A requer --arquivo com o caminho do CSV.", "error")
        sys.exit(1)

    # Verificar se scripts existem
    for fase in fases_rodar:
        script = FASES_SCRIPT[fase]
        if not script.exists():
            print_status(f"Script da Fase {fase} não encontrado: {script}", "error")
            sys.exit(1)

    # ── Executar cada fase ────────────────────────────────────────────────────
    resultados = {}
    pipeline_ok = True

    for fase in fases_rodar:
        print_fase_header(fase, args.dry_run)
        res = executar_fase(
            fase=fase,
            ano=args.ano,
            arquivo=args.arquivo,
            dry_run=args.dry_run,
            force=args.force,
        )
        resultados[fase] = res

        if not res["ok"]:
            pipeline_ok = False
            print_status(f"Pipeline interrompida na Fase {fase}. Corrija o erro e re-execute.", "error")
            print_status(f"Dica: rode 'python crew_pele.py --ano {args.ano} --from-fase {fase} ...' para retomar.", "warn")
            break

    # ── Relatório final ───────────────────────────────────────────────────────
    ts_fim     = datetime.utcnow()
    duracao_total = round((ts_fim - ts_inicio).total_seconds(), 2)

    relatorio = {
        "Ano":             args.ano,
        "Modo":            "DRY-RUN" if args.dry_run else "PRODUÇÃO",
        "Fases executadas": " → ".join(fases_rodar),
        "Status pipeline": "✅ SUCESSO" if pipeline_ok else "❌ FALHOU",
        "Duração total":   f"{duracao_total}s",
    }
    for fase in fases_rodar:
        res = resultados.get(fase, {})
        estado = "PULADA" if res.get("pulada") else ("OK" if res.get("ok") else "ERRO")
        regs   = res.get("registros", 0)
        dur    = res.get("duracao_s", 0)
        label  = FASES_NOME[fase].split("│")[1].strip()
        relatorio[f"Fase {fase} ({label[:20]})"] = f"{estado} | {regs} registros | {dur}s"

    print_relatorio(relatorio)

    if not pipeline_ok:
        sys.exit(1)

    if args.dry_run:
        print_status("DRY-RUN finalizado. Nenhum dado foi gravado no Supabase.", "warn")
        print_status(f"Para rodar de verdade: python crew_pele.py --arquivo {args.arquivo or 'SEU_CSV.csv'} --ano {args.ano}", "info")
    else:
        print_status(f"Pipeline Pelé concluída! Emendas BA {args.ano} estão no banco. 🇧🇷⚽", "success")


if __name__ == "__main__":
    main()
