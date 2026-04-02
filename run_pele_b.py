#!/usr/bin/env python3
"""
run_pele_b.py — Processa TODOS os 17 Bronzes → Prata
USO:
    python3 run_pele_b.py
    python3 run_pele_b.py --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src/agents"))
from agent_pele_b_parser import processar

ESTADUAL_ANOS = ["2017","2018","2019","2020","2021","2022","2023","2024","2025","2026"]
FEDERAL_ANOS  = ["2020","2021","2022","2023","2024","2025","2026"]

def cor(txt, c): return f"\033[{c}m{txt}\033[0m"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total_records = 0
    total_ouro = total_prata = total_bronze = 0
    erros = []

    print(cor("\n🚀 RUN PELÉ-B — Processando 17 Bronzes\n", "95"))

    for ano in ESTADUAL_ANOS:
        stats = processar("estadual", ano, args.dry_run)
        if stats:
            total_ouro   += stats.get("ouro", 0)
            total_prata  += stats.get("prata", 0)
            total_bronze += stats.get("bronze", 0)
        else:
            erros.append(f"estadual/{ano}")

    for ano in FEDERAL_ANOS:
        stats = processar("federal", ano, args.dry_run)
        if stats:
            total_ouro   += stats.get("ouro", 0)
            total_prata  += stats.get("prata", 0)
            total_bronze += stats.get("bronze", 0)
        else:
            erros.append(f"federal/{ano}")

    total_records = total_ouro + total_prata + total_bronze
    print(cor(f"\n{'━'*60}", "95"))
    print(cor(f"✅ CONCLUÍDO: {total_records} records totais", "92"))
    print(cor(f"   🥇 Ouro:   {total_ouro}  ({round(total_ouro/total_records*100,1) if total_records else 0}%)", "93"))
    print(cor(f"   🥈 Prata:  {total_prata}  ({round(total_prata/total_records*100,1) if total_records else 0}%)", "96"))
    print(cor(f"   🥉 Bronze: {total_bronze}  ({round(total_bronze/total_records*100,1) if total_records else 0}%)", "97"))
    if erros:
        print(cor(f"   ❌ Erros: {erros}", "91"))
