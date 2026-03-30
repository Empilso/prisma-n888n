#!/usr/bin/env python3
"""
⚽ AGENT ZIDANE-C v5.1 — HUB ENRICHER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT:  data/saida/parlamentares/raw/parlamentar_*_oficial.json
OUTPUT: data/saida/parlamentares/parlamentares_hub.json
FUNÇÃO: Fase 3 — Consolida todos os perfis em um Hub unificado com estatísticas
NEW v5.0: detectar_legislatura() + campos esfera, uf, casa populados
FIX v5.1: mandatos_count salvo no JSON + historico_legislaturas (int[]) populado
"""

import os, sys, json, glob, argparse
import urllib3, re
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Dict, List

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

def print_header(title: str):
    width = 70
    print(f"\n{C_PURPLE}\u2554" + "\u2550"*(width-2) + f"\u2557{C_END}")
    print(f"{C_PURPLE}\u2551{C_BOLD}{C_CYAN} {title.center(width-4)} {C_END}{C_PURPLE}\u2551{C_END}")
    print(f"{C_PURPLE}\u255a" + "\u2550"*(width-2) + f"\u255d{C_END}\n")

def print_status(msg: str, status="info"):
    icons  = {"info": "\U0001f539", "success": "\u2705", "error": "\u274c", "warn": "\u26a0\ufe0f", "process": "\u2699\ufe0f", "user": "\U0001f464"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE, "user": C_BOLD}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '\U0001f539')} {msg}{C_END}")

VERSAO = "v5.1-prisma-hub"

# ─── MAPA DE CASAS LEGISLATIVAS ──────────────────────────────────────────────────────
# Chave: fonte_portal  →  (esfera, uf, casa, legislatura_num_atual, legislatura_label)
CASAS_MAP = {
    "al_ba_gov_br":   ("estadual",  "BA", "ALBA",   20, "20ª Legislatura"),
    "al_sp_gov_br":   ("estadual",  "SP", "ALESP",  19, "19\u00aa Legislatura"),
    "al_rj_gov_br":   ("estadual",  "RJ", "ALERJ",  11, "11\u00aa Legislatura"),
    "camara_gov_br":  ("federal",   "BR", "C\u00c2MARA", 57, "57\u00aa Legislatura"),
    "senado_gov_br":  ("federal",   "BR", "SENADO",  57, "57\u00aa Legislatura"),
    "cmsp_sp_gov_br": ("municipal", "SP", "CMSP",   19, "19\u00aa Legislatura"),
}
DEFAULT_CASA = ("estadual", "BA", "ALBA", 20, "20\u00aa Legislatura")

# Anos de início de cada legislatura ALBA para calcular histórico
ALBA_LEG_ANOS = {
    17: range(2007, 2011),
    18: range(2011, 2015),
    19: range(2015, 2019),
    20: range(2019, 2023),
    21: range(2023, 2027),
}

def ano_para_legislatura_alba(ano: int) -> int | None:
    """Converte um ano para o número da legislatura ALBA correspondente."""
    for leg_num, anos in ALBA_LEG_ANOS.items():
        if ano in anos:
            return leg_num
    return None


def detectar_historico_legislaturas(mandatos: list, fonte_portal: str = "") -> list:
    """
    v5.1 FIX: Extrai TODOS os anos/períodos dos mandatos e converte para
    números de legislatura, retornando lista de ints únicos ordenados.
    Ex: ['Deputado 2007-2011', 'Deputado 2011-2015'] -> [17, 18]
    """
    legs = set()
    for m in mandatos:
        # Detecta legislatura direta: "19ª Legislatura", "20ª Legislatura"
        match_leg = re.search(r'(\d{1,2})[\u00aa\u00baa\u00b0]?\s*[Ll]egislatura', m)
        if match_leg:
            legs.add(int(match_leg.group(1)))
            continue
        # Detecta anos isolados: 2007, 2011, 2015, 2019, 2023
        anos_encontrados = re.findall(r'\b(20\d{2})\b', m)
        for ano_str in anos_encontrados:
            leg = ano_para_legislatura_alba(int(ano_str))
            if leg:
                legs.add(leg)
    # Se não encontrou nada, usa padrão da casa
    if not legs:
        casa_info = CASAS_MAP.get(fonte_portal, DEFAULT_CASA)
        legs.add(casa_info[3])  # legislatura_num_atual
    return sorted(legs)


def detectar_legislatura(mandatos: list, fonte_portal: str = "") -> str:
    """
    Retorna a legislatura atual (label) para exibição.
    """
    for m in mandatos:
        match = re.search(r'(\d{1,2})[\u00aa\u00baa\u00b0]?\s*[Ll]egislatura', m)
        if match:
            return f"{match.group(1)}\u00aa Legislatura"
        match2 = re.search(r'[Ll]egislatura\s*(\d{1,2})', m)
        if match2:
            return f"{match2.group(1)}\u00aa Legislatura"
    casa_info = CASAS_MAP.get(fonte_portal, DEFAULT_CASA)
    return casa_info[4]


def normalizar_registro(data: dict) -> dict:
    dp = data.get("dados_pessoais", {})
    fonte_portal = data.get("fonte_portal", "al_ba_gov_br")
    casa_info = CASAS_MAP.get(fonte_portal, DEFAULT_CASA)

    # 1. NASCIMENTO
    nasc_raw = dp.get("Nascimento", "")
    data["data_nascimento"]      = None
    data["municipio_nascimento"] = None
    data["uf_nascimento"]        = None
    if nasc_raw:
        match = re.match(r'(\d{2}/\d{2}/\d{4}),?\s*([\w\s]+)-([A-Z]{2})', nasc_raw)
        if match:
            d, m, y = match.group(1).split("/")
            data["data_nascimento"]      = f"{y}-{m}-{d}"
            data["municipio_nascimento"] = match.group(2).strip()
            data["uf_nascimento"]        = match.group(3).strip()

    # 2. PROMOÇÃO de dados_pessoais para raiz
    data["nome_civil"]       = dp.get("Nome")
    data["profissao"]        = dp.get("Profiss\u00e3o")
    data["sexo"]             = dp.get("Sexo")
    data["estado_civil"]     = dp.get("Estado Civil")
    data["conjuge"]          = dp.get("C\u00f4njuge")
    data["filhos"]           = dp.get("Filhos")
    data["filiacao_mae_pai"] = dp.get("Filia\u00e7\u00e3o")

    # 3. SEPARAR filiacao_partidaria[] do array mandatos[]
    mandatos_raw = data.get("mandatos", [])
    filiacao        = []
    mandatos_limpos = []
    capturando_filiacao = False

    LABELS_SKIP = {"Filia\u00e7\u00e3o Partid\u00e1ria", "Atividade Partid\u00e1ria", "Atividade Parlamentar"}

    for item in mandatos_raw:
        item_strip = item.strip()
        if item_strip == "Filia\u00e7\u00e3o Partid\u00e1ria":
            capturando_filiacao = True
            continue
        if item_strip in ("Atividade Partid\u00e1ria", "Atividade Parlamentar"):
            capturando_filiacao = False
            continue
        if capturando_filiacao:
            m = re.match(r'([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00c3\u00d5\w/]+),\s*(\d{4})\s*[-\u2013]\s*(\d{4}|)\s*;?', item_strip)
            if m:
                filiacao.append({
                    "partido":    m.group(1).strip(),
                    "ano_inicio": int(m.group(2)),
                    "ano_fim":    int(m.group(3)) if m.group(3) else None
                })
        else:
            if item_strip and item_strip not in LABELS_SKIP:
                mandatos_limpos.append(item_strip)

    data["filiacao_partidaria"] = filiacao
    data["mandatos"]            = mandatos_limpos

    # 4. v5.0: legislatura + contexto geográfico
    data["legislatura"] = detectar_legislatura(mandatos_limpos, fonte_portal)
    data["esfera"]      = data.get("esfera") or casa_info[0]
    data["uf"]          = data.get("uf")     or casa_info[1]
    data["casa"]        = data.get("casa")   or casa_info[2]

    # 5. v5.1 FIX: mandatos_count + historico_legislaturas
    data["mandatos_count"]         = len(mandatos_limpos)
    data["historico_legislaturas"] = detectar_historico_legislaturas(mandatos_limpos, fonte_portal)

    return data


def main():
    print_header(f"ZIDANE-C {VERSAO} | HUB ENRICHER & CONSOLIDADOR")
    print_status("Iniciando consolida\u00e7\u00e3o de perfis e c\u00e1lculo de estat\u00edsticas...", "process")

    base_dir = Path(__file__).resolve().parent.parent.parent
    raw_dir  = base_dir / "data" / "saida" / "parlamentares" / "raw"
    out_dir  = base_dir / "data" / "saida" / "parlamentares"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(glob.glob(str(raw_dir / "parlamentar_*_oficial.json")))
    if not json_files:
        print("\U0001f480 Nenhum perfil encontrado em raw/. Execute o Zidane-B primeiro!")
        return

    print(f"\U0001f4c2 {len(json_files)} perfis encontrados em {raw_dir.name}/\n")

    registros      = []
    partidos       = Counter()
    legislaturas   = Counter()
    com_bio        = 0
    com_foto       = 0
    com_dados      = 0
    com_mandatos   = 0
    com_observacao = 0
    scores         = []

    for i, fp in enumerate(json_files):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        data = normalizar_registro(data)

        nome     = data.get("nome_limpo", "?")
        partido  = data.get("sigla_partido", data.get("partido", "N/D"))
        score    = data.get("qualidade_score", 0)
        leg      = data.get("legislatura", "?")
        hist_leg = data.get("historico_legislaturas", [])
        m_count  = data.get("mandatos_count", 0)

        partidos[partido]     += 1
        legislaturas[leg]     += 1
        scores.append(score)

        if data.get("biografia_completa"):                       com_bio       += 1
        if data.get("foto_url"):                                 com_foto      += 1
        if data.get("dados_pessoais") and data["dados_pessoais"]: com_dados     += 1
        if data.get("mandatos")       and data["mandatos"]:       com_mandatos  += 1
        if data.get("observacao_mandato"):                        com_observacao += 1

        resumo_partes = []
        if dp := data.get("dados_pessoais", {}):
            if dp.get("Profiss\u00e3o"):  resumo_partes.append(f"Profiss\u00e3o: {dp['Profiss\u00e3o']}")
            if dp.get("Nascimento"): resumo_partes.append(f"Nascimento: {dp['Nascimento']}")
        if data.get("mandatos"):
            resumo_partes.append(f"{m_count} registros de mandato/atividade")
        if data.get("formacao"):
            resumo_partes.append(f"Forma\u00e7\u00e3o: {data['formacao'][:80]}...")

        data["resumo_executivo"] = " | ".join(resumo_partes) if resumo_partes else None
        data["enriquecido_em"]   = datetime.utcnow().isoformat() + "Z"
        data["versao_enricher"]  = VERSAO

        registros.append(data)

        # Salva o JSON individual de volta com os campos novos
        with open(fp, "w", encoding="utf-8") as f_out:
            json.dump(data, f_out, ensure_ascii=False, indent=2)

        status_icon = "\u2705" if score >= 0.9 else "\u26a0\ufe0f" if score >= 0.6 else "\u274c"
        line_color  = C_GREEN  if score >= 0.9 else C_YELLOW if score >= 0.6 else C_RED
        print(
            f"   {status_icon} [{i+1:02d}/{len(json_files)}] {C_BOLD}{nome:<35}{C_END} "
            f"| {C_CYAN}{partido:<12}{C_END} | {C_PURPLE}{leg:<20}{C_END} "
            f"| Hist: {hist_leg} | Mandatos: {m_count} "
            f"| {line_color}Score: {score}{C_END}"
        )

    media_score = sum(scores) / len(scores) if scores else 0
    stats = {
        "total_parlamentares":  len(registros),
        "com_biografia":        com_bio,
        "com_foto":             com_foto,
        "com_dados_pessoais":   com_dados,
        "com_mandatos":         com_mandatos,
        "com_observacao_mandato": com_observacao,
        "media_qualidade_score": round(media_score, 3),
        "por_partido":          dict(partidos.most_common()),
        "por_legislatura":      dict(legislaturas.most_common()),
        "completude_geral":     round((com_bio / len(registros) * 100) if registros else 0, 1)
    }

    print(f"\n{C_PURPLE}\U0001f4ca estat\u00edsticas do hub {'-'*50}{C_END}")
    print(f"   {C_CYAN}Total:{C_END}          {C_BOLD}{stats['total_parlamentares']}{C_END} parlamentares")
    print(f"   {C_CYAN}Com biografia:{C_END}  {com_bio}/{len(registros)} ({C_GREEN}{stats['completude_geral']}%{C_END})")
    print(f"   {C_CYAN}Com foto:{C_END}       {com_foto} | {C_CYAN}Com dados pessoais:{C_END} {com_dados}")
    print(f"   {C_CYAN}Com mandatos:{C_END}   {com_mandatos} | {C_CYAN}Com observa\u00e7\u00f5es:{C_END} {com_observacao}")
    print(f"   {C_CYAN}Score m\u00e9dio:{C_END}    {C_YELLOW}{media_score:.3f}{C_END}")
    print(f"   {C_CYAN}Partidos:{C_END}       {C_WHITE}{dict(partidos.most_common(5))}{C_END}")
    print(f"   {C_CYAN}Legislaturas:{C_END}   {C_WHITE}{dict(legislaturas.most_common())}{C_END}")
    print(f"{C_PURPLE}{'='*70}{C_END}")

    hub = {
        "versao":       VERSAO,
        "gerado_em":    datetime.utcnow().isoformat() + "Z",
        "fonte":        "al.ba.gov.br",
        "estatisticas": stats,
        "parlamentares": registros
    }

    out_file = out_dir / "parlamentares_hub_normalized.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(hub, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}{'='*70}{C_END}")
    print_status(f"ZIDANE-C CONCLU\u00cdDO! Hub com {C_BOLD}{len(registros)}{C_END} parlamentares consolidado.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END} ({out_file.stat().st_size / 1024:.1f} KB)", "info")
    print(f"{C_PURPLE}{'='*70}{C_END}\n")


if __name__ == "__main__":
    main()
