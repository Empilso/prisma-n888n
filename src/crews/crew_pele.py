#!/usr/bin/env python3
"""
⚽ CREW PELÉ v2.0 — ORQUESTRADOR DE EMENDAS PARLAMENTARES BA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Orquestrar a pipeline completa de Emendas Parlamentares BA.
         Suporta ESTADUAL (A1), FEDERAL (A2), ou AMBOS em sequência:

         ESTADUAL:  Pelé-A1 → Pelé-B → Pelé-C → Pelé-D
         FEDERAL:   Pelé-A2 → Pelé-B → Pelé-C → Pelé-D
         AMBOS:     A1 → A2 → B(estadual) → B(federal) → C(est) → C(fed) → D(est) → D(fed)

PATHS DE SAÍDA:
    data/saida/pele/bronze/pele_{origem}_{ano}_bronze.json
    data/saida/pele/prata/pele_{origem}_{ano}_prata.json
    data/saida/pele/ouro/pele_{origem}_{ano}_ouro.json
    → Supabase: tabelas emendas_estaduais_ba | emendas_federais_ba

USO:
    # Pipeline estadual completa
    python crew_pele.py --pasta ./emendasparlamentares --ano 2024 --origem estadual

    # Pipeline federal completa
    python crew_pele.py --pasta-federal ./transferenciasfederais --ano 2024 --origem federal

    # Pipeline AMBAS as origens
    python crew_pele.py \\
        --pasta ./emendasparlamentares \\
        --pasta-federal ./transferenciasfederais \\
        --ano 2024 --origem ambos

    # Dry-run (valida sem gravar no banco)
    python crew_pele.py --pasta ./emendasparlamentares --ano 2024 --origem estadual --dry-run

    # Rodar a partir de uma fase já processada
    python crew_pele.py --ano 2024 --origem estadual --from-fase B

    # Rodar até certa fase (sem subir ao banco)
    python crew_pele.py --pasta ./emendasparlamentares --ano 2024 --origem estadual --ate-fase C

    # Forçar reprocessamento mesmo com arquivos existentes
    python crew_pele.py --pasta ./emendasparlamentares --ano 2024 --origem estadual --force
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

VERSAO = "v2.0-prisma-crew-pele"

# ── Caminhos ─────────────────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent          # src/
AGENTS_DIR = BASE_DIR / "agents"
DATA_DIR   = BASE_DIR.parent / "data" / "saida" / "pele"    # data/saida/pele/

ORIGENS_VALIDAS = ["estadual", "federal", "ambos"]

FASES_NOME = {
    "A1": "Pelé-A1 │ Ingestor CSV Estadual   → Bronze",
    "A2": "Pelé-A2 │ Ingestor CSV Federal    → Bronze",
    "B":  "Pelé-B  │ Parser & Normalizador   → Prata",
    "C":  "Pelé-C  │ Águia Zidane Matcher    → Ouro",
    "D":  "Pelé-D  │ Loader Supabase         → DB",
}

FASES_SCRIPT = {
    "A1": AGENTS_DIR / "agent_pele_a1_estadual.py",
    "A2": AGENTS_DIR / "agent_pele_a2_federal.py",
    "B":  AGENTS_DIR / "agent_pele_b_parser.py",
    "C":  AGENTS_DIR / "agent_pele_c_aguia.py",
    "D":  AGENTS_DIR / "agent_pele_d_loader.py",
}

# Output esperado por fase/origem
def fase_output(fase: str, origem: str, ano: str) -> Optional[Path]:
    if fase == "A1":
        return DATA_DIR / "bronze" / f"pele_estadual_{ano}_bronze.json"
    if fase == "A2":
        return DATA_DIR / "bronze" / f"pele_federal_{ano}_bronze.json"
    if fase == "B":
        return DATA_DIR / "prata" / f"pele_{origem}_{ano}_prata.json"
    if fase == "C":
        return DATA_DIR / "ouro"  / f"pele_{origem}_{ano}_ouro.json"
    return None  # D = banco


# ── Estética Terminal ────────────────────────────────────────────────────────────────────
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
    width = 72
    linhas = [
        f"CREW PELÉ {VERSAO}",
        "PIPELINE EMENDAS PARLAMENTARES BA",
        "ESTADUAL (A1) + FEDERAL (A2) → B → C → D",
    ]
    print(f"\n{C_PURPLE}\u256d" + "─"*(width-2) + f"\u256e{C_END}")
    for linha in linhas:
        print(f"{C_PURPLE}│{C_BOLD}{C_CYAN}{linha.center(width-2)}{C_END}{C_PURPLE}│{C_END}")
    print(f"{C_PURPLE}\u2570" + "─"*(width-2) + f"\u256f{C_END}\n")

def print_fase_header(fase: str, origem: str, dry_run: bool):
    nome = FASES_NOME.get(fase, fase)
    modo = f"  {C_YELLOW}[DRY-RUN]{C_END}" if dry_run else ""
    orig_tag = f" [{origem.upper()}]" if origem else ""
    print(f"\n{C_BLUE}{'\u2500'*72}{C_END}")
    print(f"{C_BOLD}{C_WHITE}  FASE {fase}{orig_tag} │ {nome}{C_END}{modo}")
    print(f"{C_BLUE}{'\u2500'*72}{C_END}")

def print_status(msg: str, status="info"):
    icons  = {"info": "\U0001f539", "success": "\u2705", "error": "\u274c",
               "warn": "\u26a0\ufe0f", "process": "\u2699\ufe0f", "skip": "\u23ed\ufe0f", "time": "\u23f1\ufe0f"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED,
               "warn": C_YELLOW, "process": C_PURPLE, "skip": C_BLUE, "time": C_WHITE}
    icon  = icons.get(status, "\U0001f539")
    color = colors.get(status, C_CYAN)
    print(f"{color}{icon} {msg}{C_END}")

def print_relatorio(relatorio: dict):
    width = 72
    print(f"\n{C_GREEN}\u256d" + "─"*(width-2) + f"\u256e{C_END}")
    print(f"{C_GREEN}│{C_BOLD}{C_WHITE}{'  RELATÓRIO FINAL — CREW PELÉ'.center(width-2)}{C_END}{C_GREEN}│{C_END}")
    print(f"{C_GREEN}├" + "─"*(width-2) + f"\u2524{C_END}")
    for k, v in relatorio.items():
        linha = f"  {k:<28} {v}"
        print(f"{C_GREEN}│{C_WHITE}{linha:<(width-2)}{C_END}{C_GREEN}│{C_END}")
    print(f"{C_GREEN}\u2570" + "─"*(width-2) + f"\u256f{C_END}\n")


# ── Runner ────────────────────────────────────────────────────────────────────────────────────
def rodar_fase(script: Path, args_extra: List[str], fase: str, dry_run: bool) -> bool:
    """Executa um agente como subprocess e retorna True se OK."""
    if not script.exists():
        print_status(f"Script não encontrado: {script}", "error")
        return False

    cmd = [sys.executable, str(script)] + args_extra
    if dry_run:
        cmd.append("--dry-run")

    print_status(f"Executando: {' '.join(cmd)}", "process")
    t0 = time.time()
    result = subprocess.run(cmd, text=True, capture_output=False)
    elapsed = round(time.time() - t0, 1)

    if result.returncode == 0:
        print_status(f"Fase {fase} concluída em {elapsed}s", "time")
        return True
    else:
        print_status(f"Fase {fase} FALHOU (código {result.returncode})", "error")
        return False


def arquivo_existe(fase: str, origem: str, ano: str) -> bool:
    p = fase_output(fase, origem, ano)
    return p is not None and p.exists()


def contar_registros(fase: str, origem: str, ano: str) -> int:
    p = fase_output(fase, origem, ano)
    if p is None or not p.exists():
        return 0
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("total", len(data.get("records", [])))
    except:
        return 0


# ── Pipeline por Origem ─────────────────────────────────────────────────────────────────────────
def pipeline_origem(
    origem: str,
    ano: str,
    pasta: Optional[str],
    pasta_federal: Optional[str],
    dry_run: bool,
    force: bool,
    from_fase: str,
    ate_fase: str,
) -> Dict:
    """Executa pipeline A → B → C → D para uma origem e retorna stats."""
    fases_ordem_origem = ["A1" if origem == "estadual" else "A2", "B", "C", "D"]

    # Ordem de fases para navegação
    ordem_geral = ["A1", "A2", "B", "C", "D"]
    idx_from = ordem_geral.index(from_fase) if from_fase in ordem_geral else 0
    idx_ate  = ordem_geral.index(ate_fase)  if ate_fase  in ordem_geral else len(ordem_geral) - 1

    resultados = {}
    falhou = False

    for fase in fases_ordem_origem:
        idx_fase = ordem_geral.index(fase)
        if idx_fase < idx_from:
            print_status(f"Pulando fase {fase} (--from-fase {from_fase})", "skip")
            continue
        if idx_fase > idx_ate:
            print_status(f"Parando após fase {ate_fase} (--ate-fase {ate_fase})", "skip")
            break

        print_fase_header(fase, origem, dry_run)

        # Verificar se pode pular (output já existe e não é force)
        if fase != "D" and not force and arquivo_existe(fase, origem, ano):
            n = contar_registros(fase, origem, ano)
            print_status(f"Output já existe ({n} registros). Use --force para re-processar.", "skip")
            resultados[fase] = {"status": "skip", "registros": n}
            continue

        # Montar args por fase
        script = FASES_SCRIPT[fase]
        args_extra = []

        if fase == "A1":
            if not pasta:
                print_status("--pasta é obrigatório para origem estadual", "error")
                falhou = True
                break
            args_extra = ["--pasta", pasta, "--ano", ano]

        elif fase == "A2":
            p = pasta_federal or pasta
            if not p:
                print_status("--pasta-federal é obrigatório para origem federal", "error")
                falhou = True
                break
            args_extra = ["--pasta", p, "--ano", ano]

        elif fase in ("B", "C", "D"):
            args_extra = ["--origem", origem, "--ano", ano]

        ok = rodar_fase(script, args_extra, fase, dry_run)
        if not ok:
            falhou = True
            resultados[fase] = {"status": "erro"}
            break

        n = contar_registros(fase, origem, ano) if fase != "D" else "(banco)"
        resultados[fase] = {"status": "ok", "registros": n}

    return {"origem": origem, "falhou": falhou, "fases": resultados}


# ── Main ────────────────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=f"Crew Pelé {VERSAO}: Orquestrador Emendas Parlamentares BA"
    )
    ap.add_argument("--ano",          type=str, required=True,
                    help="Ano de exercício (ex: 2024)")
    ap.add_argument("--origem",       type=str, default="estadual",
                    choices=ORIGENS_VALIDAS,
                    help="estadual | federal | ambos (default: estadual)")
    ap.add_argument("--pasta",        type=str, default=None,
                    help="Pasta com CSVs estaduais (emendasparlamentares/)")
    ap.add_argument("--pasta-federal",type=str, default=None, dest="pasta_federal",
                    help="Pasta com CSVs federais (transferenciasfederais/)")
    ap.add_argument("--dry-run",      action="store_true",
                    help="Processa sem gravar arquivos/banco")
    ap.add_argument("--force",        action="store_true",
                    help="Re-processa mesmo que arquivos intermediários já existam")
    ap.add_argument("--from-fase",    type=str, default="A1",
                    choices=["A1", "A2", "B", "C", "D"],
                    help="Iniciar a partir desta fase (default: A1)")
    ap.add_argument("--ate-fase",     type=str, default="D",
                    choices=["A1", "A2", "B", "C", "D"],
                    help="Parar nesta fase (default: D)")
    args = ap.parse_args()

    print_banner()

    t_inicio = time.time()
    origens_rodar = ["estadual", "federal"] if args.origem == "ambos" else [args.origem]

    todos_resultados = []
    algum_falhou = False

    for origem in origens_rodar:
        print(f"\n{C_PURPLE}{'='*72}{C_END}")
        print(f"{C_BOLD}{C_CYAN}  INICIANDO PIPELINE: {origem.upper()}{C_END}")
        print(f"{C_PURPLE}{'='*72}{C_END}")

        res = pipeline_origem(
            origem=origem,
            ano=args.ano,
            pasta=args.pasta,
            pasta_federal=args.pasta_federal,
            dry_run=args.dry_run,
            force=args.force,
            from_fase=args.from_fase,
            ate_fase=args.ate_fase,
        )
        todos_resultados.append(res)
        if res["falhou"]:
            algum_falhou = True
            print_status(f"Pipeline {origem.upper()} FALHOU. Abortando.", "error")
            if args.origem != "ambos":
                break

    # ─ Relatório Final
    elapsed_total = round(time.time() - t_inicio, 1)
    relatorio = {
        "Versão":              VERSAO,
        "Timestamp":           datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "Ano processado":      args.ano,
        "Origens":             " + ".join(origens_rodar).upper(),
        "Dry-run":             "SIM" if args.dry_run else "NÃO",
        "Fases executadas":    f"{args.from_fase} → {args.ate_fase}",
        "Tempo total":         f"{elapsed_total}s",
    }

    for res in todos_resultados:
        origem = res["origem"]
        for fase, info in res["fases"].items():
            st = info.get("status", "?")
            recs = info.get("registros", "")
            label = f"{origem[:3].upper()} | Fase {fase}"
            relatorio[label] = f"{st.upper()} {'(' + str(recs) + ' reg)' if recs else ''}"

    relatorio["Status Final"] = "FALHA \u274c" if algum_falhou else "SUCESSO \u2705"
    print_relatorio(relatorio)

    sys.exit(1 if algum_falhou else 0)


if __name__ == "__main__":
    main()
