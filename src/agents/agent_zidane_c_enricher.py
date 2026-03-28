#!/usr/bin/env python3
"""
⚽ AGENT ZIDANE-C v4.0 — HUB ENRICHER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT:  data/saida/parlamentares/raw/parlamentar_*_oficial.json
OUTPUT: data/saida/parlamentares/parlamentares_hub.json
FUNÇÃO: Fase 3 — Consolida todos os perfis em um Hub unificado com estatísticas
"""

import os, sys, json, glob, argparse
import urllib3
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Dict, List

# Silencia avisos de SSL (InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Estética Premium Terminal ─────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_WHITE = "\033[97m"
C_END = "\033[0m"

def print_header(title: str):
    width = 70
    print(f"\n{C_PURPLE}╔" + "═"*(width-2) + f"╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN} {title.center(width-4)} {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚" + "═"*(width-2) + f"╝{C_END}\n")

def print_status(msg: str, status="info"):
    icons = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️", "user": "👤"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE, "user": C_BOLD}
    icon = icons.get(status, "🔹")
    color = colors.get(status, C_CYAN)
    print(f"{color}{icon} {msg}{C_END}")

import re

VERSAO = "v4.0-prisma-hub"

def normalizar_registro(data: dict) -> dict:
    dp = data.get("dados_pessoais", {})

    # 1. NASCIMENTO → data + município + UF
    nasc_raw = dp.get("Nascimento", "")
    data["data_nascimento"] = None
    data["municipio_nascimento"] = None
    data["uf_nascimento"] = None
    if nasc_raw:
        # Ex: "15/03/1970, Salvador-BA"
        match = re.match(r'(\d{2}/\d{2}/\d{4}),?\s*([\w\s]+)-([A-Z]{2})', nasc_raw)
        if match:
            d, m, y = match.group(1).split("/")
            data["data_nascimento"]     = f"{y}-{m}-{d}"
            data["municipio_nascimento"] = match.group(2).strip()
            data["uf_nascimento"]        = match.group(3).strip()

    # 2. PROMOÇÃO de dados_pessoais para raiz
    data["nome_civil"]    = dp.get("Nome")
    data["profissao"]     = dp.get("Profissão")
    data["sexo"]          = dp.get("Sexo")
    data["estado_civil"]  = dp.get("Estado Civil")
    data["conjuge"]       = dp.get("Cônjuge")
    data["filhos"]        = dp.get("Filhos")
    data["filiacao_mae_pai"] = dp.get("Filiação")

    # 3. SEPARAR filiacao_partidaria[] do array mandatos[]
    mandatos_raw = data.get("mandatos", [])
    filiacao = []
    mandatos_limpos = []
    capturando_filiacao = False

    LABELS_SKIP = {
        "Filiação Partidária", "Atividade Partidária", "Atividade Parlamentar"
    }

    for item in mandatos_raw:
        item_strip = item.strip()
        if item_strip == "Filiação Partidária":
            capturando_filiacao = True
            continue
        if item_strip in ("Atividade Partidária", "Atividade Parlamentar"):
            capturando_filiacao = False
            continue
        if capturando_filiacao:
            # Ex: "PP, 2018 - ;" ou "PTB, 1997 - 2001;"
            m = re.match(r'([A-ZÁÉÍÓÚÃÕ\w/]+),\s*(\d{4})\s*[-–]\s*(\d{4}|)\s*;?', item_strip)
            if m:
                filiacao.append({
                    "partido": m.group(1).strip(),
                    "ano_inicio": int(m.group(2)),
                    "ano_fim": int(m.group(3)) if m.group(3) else None
                })
        else:
            if item_strip and item_strip not in LABELS_SKIP:
                mandatos_limpos.append(item_strip)

    data["filiacao_partidaria"] = filiacao
    data["mandatos"] = mandatos_limpos

    return data


def main():
    print_header(f"ZIDANE-C {VERSAO} | HUB ENRICHER & CONSOLIDADOR")
    print_status("Iniciando consolidação de perfis e cálculo de estatísticas...", "process")

    base_dir = Path("/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n")
    raw_dir = base_dir / "data" / "saida" / "parlamentares" / "raw"
    out_dir = base_dir / "data" / "saida" / "parlamentares"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Lê todos os JSONs individuais ──────────────────────────────
    json_files = sorted(glob.glob(str(raw_dir / "parlamentar_*_oficial.json")))
    if not json_files:
        print("💀 Nenhum perfil encontrado em raw/. Execute o Zidane-B primeiro!")
        return

    print(f"📂 {len(json_files)} perfis encontrados em {raw_dir.name}/\n")

    registros = []
    partidos = Counter()
    com_bio = 0
    com_foto = 0
    com_dados = 0
    com_mandatos = 0
    com_observacao = 0
    scores = []

    for i, fp in enumerate(json_files):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        data = normalizar_registro(data)

        nome = data.get("nome_limpo", "?")
        partido = data.get("sigla_partido", data.get("partido", "N/D"))
        score = data.get("qualidade_score", 0)

        partidos[partido] += 1
        scores.append(score)

        if data.get("biografia_completa"):
            com_bio += 1
        if data.get("foto_url"):
            com_foto += 1
        if data.get("dados_pessoais") and len(data["dados_pessoais"]) > 0:
            com_dados += 1
        if data.get("mandatos") and len(data["mandatos"]) > 0:
            com_mandatos += 1
        if data.get("observacao_mandato"):
            com_observacao += 1

        # Enriquecimento: Resumo executivo simples (sem LLM)
        resumo_partes = []
        dp = data.get("dados_pessoais", {})
        if dp.get("Profissão"):
            resumo_partes.append(f"Profissão: {dp['Profissão']}")
        if dp.get("Nascimento"):
            resumo_partes.append(f"Nascimento: {dp['Nascimento']}")
        if data.get("mandatos"):
            resumo_partes.append(f"{len(data['mandatos'])} registros de mandato/atividade")
        if data.get("formacao"):
            resumo_partes.append(f"Formação: {data['formacao'][:80]}...")

        data["resumo_executivo"] = " | ".join(resumo_partes) if resumo_partes else None
        data["enriquecido_em"] = datetime.utcnow().isoformat() + "Z"
        data["versao_enricher"] = VERSAO

        registros.append(data)
        status_icon = "✅" if score >= 0.9 else "⚠️" if score >= 0.6 else "❌"
        line_color = C_GREEN if score >= 0.9 else C_YELLOW if score >= 0.6 else C_RED
        print(f"   {status_icon} [{i+1:02d}/{len(json_files)}] {C_BOLD}{nome:<35}{C_END} | {C_CYAN}{partido:<12}{C_END} | {line_color}Score: {score}{C_END}")

    # ── Estatísticas do Hub ────────────────────────────────────────
    media_score = sum(scores) / len(scores) if scores else 0
    stats = {
        "total_parlamentares": len(registros),
        "com_biografia": com_bio,
        "com_foto": com_foto,
        "com_dados_pessoais": com_dados,
        "com_mandatos": com_mandatos,
        "com_observacao_mandato": com_observacao,
        "media_qualidade_score": round(media_score, 3),
        "por_partido": dict(partidos.most_common()),
        "completude_geral": round((com_bio / len(registros) * 100) if registros else 0, 1)
    }

    print(f"\n{C_PURPLE}📊 estatísticas do hub ───────────────────────────────────────────────{C_END}")
    print(f"   {C_CYAN}Total:{C_END} {C_BOLD}{stats['total_parlamentares']}{C_END} parlamentares")
    print(f"   {C_CYAN}Com biografia:{C_END} {com_bio}/{len(registros)} ({C_GREEN}{stats['completude_geral']}%{C_END})")
    print(f"   {C_CYAN}Com foto:{C_END} {com_foto} | {C_CYAN}Com dados pessoais:{C_END} {com_dados}")
    print(f"   {C_CYAN}Com mandatos:{C_END} {com_mandatos} | {C_CYAN}Com observações:{C_END} {com_observacao}")
    print(f"   {C_CYAN}Score médio:{C_END} {C_YELLOW}{media_score:.3f}{C_END}")
    print(f"   {C_CYAN}Partidos:{C_END} {C_WHITE}{dict(partidos.most_common(5))}{C_END}")
    print(f"{C_PURPLE}──────────────────────────────────────────────────────────────────────{C_END}")

    # ── Salva Hub consolidado ──────────────────────────────────────
    hub = {
        "versao": VERSAO,
        "gerado_em": datetime.utcnow().isoformat() + "Z",
        "fonte": "al.ba.gov.br",
        "estatisticas": stats,
        "parlamentares": registros
    }

    out_file = out_dir / "parlamentares_hub_normalized.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(hub, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"ZIDANE-C CONCLUÍDO! Hub com {C_BOLD}{len(registros)}{C_END} parlamentares consolidado.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END} ({out_file.stat().st_size / 1024:.1f} KB)", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    main()
