#!/usr/bin/env python3
"""
⚽ AGENT ZIDANE-A v4.0 — COLETOR DE IDs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FONTE:  https://www.al.ba.gov.br/deputados/deputados-estaduais
OUTPUT: data/saida/parlamentares/raw/parlamentares_ids.json
FUNÇÃO: Fase 1 — Identifica todos os deputados (nomes, IDs, partidos, observações)
"""

import os, sys, json, re, hashlib, argparse
import requests
import urllib3
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, List

# Silencia avisos de SSL (InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.al.ba.gov.br"
URL_LISTA = f"{BASE_URL}/deputados/deputados-estaduais"
VERSAO = "v4.0-prisma-ids"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Identificar todos os parlamentares ativos e listar IDs e páginas de perfil.",
        "especialidade": "Reconhecimento de Superfície",
        "protocolo_tecnico": "Requests + BeautifulSoup4 + LXML",
        "camada_dados": "Raw (Bronze Inicial)",
        "seguranca": "Timeout 30s + Ignora Erros de Certificado ALBA"
    },
    "diretrizes": [
        "1. Acessa a lista master de deputados estaduais da ALBA.",
        "2. Identifica o CARD de cada deputado (nó DOM .col-md-3).",
        "3. Extrai o parlamentar_id dinâmico da URL do perfil.",
        "4. Captura partido, nome parlamentar e foto.",
        "5. Verifica a sessão de observações para listar suplências."
    ],
    "apuracao": {
        "safras_suportadas": ["Atual (Tempo Real)"],
        "saida_esperada": "data/saida/parlamentares/raw/parlamentares_ids.json"
    }
}



def get_soup(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, "lxml")
    except Exception as e:
        print(f"    ❌ Erro ao acessar: {url} → {e}")
        return None

# ── Estética Premium Terminal ─────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
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


def main():
    print_header(f"ZIDANE-A {VERSAO} | COLETOR DE IDs")
    print_status("Iniciando reconhecimento de parlamentares no portal ALBA...", "process")

    base_dir = Path("/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n")
    out_dir = base_dir / "data" / "saida" / "parlamentares" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📡 Acessando lista: {URL_LISTA}")
    soup = get_soup(URL_LISTA)
    if not soup:
        print("💀 Falha crítica: não foi possível acessar o portal ALBA.")
        return

    # ── Extração de Cards ──────────────────────────────────────────
    cards = [c for c in soup.select(".col-md-3") if c.select_one(".campo-dados")]
    print(f"   ✅ Cards de deputados encontrados: {len(cards)}")

    deputados = []
    for card in cards:
        nome_tag = card.select_one(".deputado-nome a span")
        if not nome_tag:
            nome_tag = card.select_one(".deputado-nome a")
        if not nome_tag:
            continue
        nome = nome_tag.get_text(strip=True)

        link_tag = card.select_one(".deputado-nome a")
        if not link_tag:
            continue
        href = link_tag.get("href", "")
        url = BASE_URL + href if href.startswith("/") else href
        p_id = href.rstrip("/").split("/")[-1]

        partido_tag = card.select_one(".partido-nome")
        partido = partido_tag.get_text(strip=True) if partido_tag else "N/D"

        # Foto do card
        img_tag = card.select_one(".deputado-img")
        foto_url = None
        if img_tag and img_tag.get("src"):
            src = img_tag["src"].split("/static:")[0]
            foto_url = BASE_URL + src if src.startswith("/") else src

        if nome and p_id:
            deputados.append({
                "parlamentar_id": p_id,
                "nome_parlamentar": nome,
                "partido_atual": partido,
                "status": "ativo",
                "foto_url": foto_url,
                "url_perfil": url
            })
            print(f"   {C_BOLD}👤 {nome:<40}{C_END} | {C_CYAN}{partido:<12}{C_END} | {C_PURPLE}ID: {p_id}{C_END}")

    # ── Extração de Observações (suplentes/substituições) ──────────
    mapa_obs: Dict[str, str] = {}
    obs_header = soup.find(lambda t: t.name in ["h2","h3","h4","b","strong","p"]
                           and t.get_text(strip=True).lower() in ["observações", "observacoes"])
    if obs_header:
        bloco = obs_header.find_next_sibling()
        while bloco:
            txt = bloco.get_text(separator="\n", strip=True)
            linhas = [l.strip() for l in txt.split("\n") if l.strip()]
            if len(linhas) >= 2:
                mapa_obs[linhas[0].lower()] = " ".join(linhas[1:])
            bloco = bloco.find_next_sibling()
            if not bloco or bloco.get_text(strip=True).lower().startswith("atualização"):
                break

    for dep in deputados:
        dep["observacao_mandato"] = mapa_obs.get(dep["nome_parlamentar"].lower(), None)

    print(f"\n   📋 Total: {len(deputados)} parlamentares | Observações: {len(mapa_obs)}")

    # ── Salvar JSON ────────────────────────────────────────────────
    output = {
        "total": len(deputados),
        "coletado_em": datetime.utcnow().isoformat() + "Z",
        "fonte": "al.ba.gov.br",
        "metodo": "scraping_oficial",
        "versao": VERSAO,
        "records": deputados
    }

    out_file = out_dir / "parlamentares_ids.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"ZIDANE-A CONCLUÍDO! {C_BOLD}{len(deputados)}{C_END} IDs coletados.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END}", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    main()
