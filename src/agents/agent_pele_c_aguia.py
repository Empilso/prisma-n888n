#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-C v1.0 — ÁGUIA ENRIQUECEDOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Enriquecer os registros Prata com dados parlamentares
         (cruzando com base Zidane se disponível), calcular totais
         por deputado, classificar tipos de emenda e gerar JSON Ouro.

ENTRADA: data/saida/emendas_federais/prata/emendas_federais_ba_{ano}_prata.json
CROSS:   data/saida/parlamentares/raw/parlamentares_ids_leg_20.json (opcional, Zidane)
OUTPUT:  data/saida/emendas_federais/ouro/emendas_federais_ba_{ano}_ouro.json

USO:
    python agent_pele_c_aguia.py --ano 2024
    python agent_pele_c_aguia.py --ano 2024 --dry-run
    python agent_pele_c_aguia.py --ano 2024 --sem-cruzamento
"""

import os
import sys
import re
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict

VERSAO = "v1.0-prisma-pele-aguia"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Enriquecimento Ouro de Emendas Federais BA.",
        "especialidade": "Cruzamento com base Zidane + cálculo de totais + scoring",
        "protocolo_tecnico": "Pure Python (fuzzy match + aggregations)",
        "camada_dados": "Ouro (Enriquecido)",
        "seguranca": "Sem acesso à internet. Cruzamento local com base Zidane."
    },
    "diretrizes": [
        "1. Lê o JSON Prata gerado pelo Pelé-B.",
        "2. Tenta cruzar deputados com base Zidane (parlamentar_id + partido).",
        "3. Calcula totais por deputado: valor_total, qtd_emendas, media_emenda.",
        "4. Eleva qualidade_score para registros enriquecidos com cross-data.",
        "5. Adiciona ranking por valor dentro do período.",
        "6. Salva JSON Ouro pronto para o Pelé-D (upload Supabase)."
    ]
}

# ── Estética Terminal ──────────────────────────────────────────────────────────
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
    print(f"\n{C_PURPLE}╔" + "═"*(width-2) + f"╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN} {title.center(width-4)} {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚" + "═"*(width-2) + f"╝{C_END}\n")

def print_status(msg: str, status="info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '🔹')} {msg}{C_END}")


def normalizar_nome(nome: str | None) -> str:
    """Remove acentos e lowercase para comparação fuzzy."""
    if not nome:
        return ""
    nfkd = "".join(c for c in __import__('unicodedata').normalize('NFKD', nome)
                   if not __import__('unicodedata').combining(c))
    return re.sub(r'\s+', ' ', nfkd.strip().lower())


def carregar_base_zidane(base_dir: Path) -> Dict[str, Dict]:
    """
    Carrega a base de parlamentares do Zidane-A (todas as legislaturas disponíveis).
    Retorna dict: nome_normalizado → dados do parlamentar.
    """
    mapa: Dict[str, Dict] = {}
    parl_dir = base_dir / "data" / "saida" / "parlamentares" / "raw"

    for leg in ["20", "19", "18", "17"]:
        ids_file = parl_dir / f"parlamentares_ids_leg_{leg}.json"
        if ids_file.exists():
            with open(ids_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for p in data.get("records", []):
                nome_norm = normalizar_nome(p.get("nome_parlamentar"))
                if nome_norm and nome_norm not in mapa:
                    mapa[nome_norm] = {
                        "parlamentar_id":  p.get("parlamentar_id"),
                        "nome_parlamentar": p.get("nome_parlamentar"),
                        "partido":         p.get("partido_atual"),
                        "url_perfil":      p.get("url_perfil"),
                        "legislatura":     leg,
                    }
            print_status(f"Zidane leg {leg}: {len(data.get('records', []))} parlamentares carregados.", "info")

    if not mapa:
        print_status("Base Zidane não encontrada — cruzamento será pulado.", "warn")
    else:
        print_status(f"Base Zidane total: {len(mapa)} parlamentares únicos.", "success")

    return mapa


def cruzar_com_zidane(deputado: str, partido: str | None, mapa_zidane: Dict) -> Dict | None:
    """
    Tenta localizar o parlamentar na base Zidane.
    Estratégia: match exato → match por palavras-chave do sobrenome.
    """
    if not mapa_zidane:
        return None

    nome_norm = normalizar_nome(deputado)

    # Match exato
    if nome_norm in mapa_zidane:
        return mapa_zidane[nome_norm]

    # Match parcial: verifica se alguma palavra longa do nome está no nome Zidane
    palavras = [p for p in nome_norm.split() if len(p) > 4]
    for p in palavras:
        candidatos = [k for k in mapa_zidane if p in k]
        if len(candidatos) == 1:
            return mapa_zidane[candidatos[0]]
        elif len(candidatos) > 1 and partido:
            # Desempata por partido
            partido_norm = normalizar_nome(partido)
            for c in candidatos:
                zid = mapa_zidane[c]
                if partido_norm in normalizar_nome(zid.get("partido", "")):
                    return zid

    return None


def main():
    parser = argparse.ArgumentParser(description="Pelé-C v1.0: Águia Enriquecedor de Emendas Federais BA")
    parser.add_argument("--ano",             type=str, required=True, help="Ano dos dados (ex: 2024)")
    parser.add_argument("--dry-run",         action="store_true",     help="Processa sem salvar")
    parser.add_argument("--sem-cruzamento",  action="store_true",     help="Pula cruzamento com base Zidane")
    args = parser.parse_args()

    print_header(f"PELÉ-C {VERSAO} | ÁGUIA ENRIQUECEDOR — ANO {args.ano}")

    base_dir   = Path(__file__).resolve().parent.parent.parent
    prata_dir  = base_dir / "data" / "saida" / "emendas_federais" / "prata"
    prata_file = prata_dir / f"emendas_federais_ba_{args.ano}_prata.json"

    if not prata_file.exists():
        print_status(f"Prata não encontrado: {prata_file.name}", "error")
        print_status("Execute o Pelé-B primeiro: python agent_pele_b_parser.py --ano ...", "warn")
        sys.exit(1)

    print_status(f"Lendo Prata: {prata_file.name}", "process")
    with open(prata_file, "r", encoding="utf-8") as f:
        prata_data = json.load(f)

    records = prata_data.get("records", [])
    total   = len(records)
    print_status(f"Registros Prata: {total}", "info")

    # ── Carregar base Zidane ───────────────────────────────────────────────────
    mapa_zidane: Dict[str, Dict] = {}
    if not args.sem_cruzamento:
        mapa_zidane = carregar_base_zidane(base_dir)

    # ── Calcular totais por deputado ───────────────────────────────────────────
    totais: Dict[str, Dict] = defaultdict(lambda: {"valor_total": 0.0, "qtd": 0})
    for r in records:
        dep = r.get("deputado", "")
        totais[dep]["valor_total"] += float(r.get("valor") or 0)
        totais[dep]["qtd"] += 1

    # Ranking por valor total
    ranking = sorted(totais.items(), key=lambda x: x[1]["valor_total"], reverse=True)
    rank_map = {nome: i+1 for i, (nome, _) in enumerate(ranking)}

    print(f"\n{C_WHITE}🏆 Top 5 deputados por valor total:{C_END}")
    for nome, dados in ranking[:5]:
        print(f"   {rank_map[nome]:>3}. {C_BOLD}{nome:<40}{C_END} R$ {dados['valor_total']:>14,.2f} ({dados['qtd']} emendas)")

    # ── Enriquecer registros ───────────────────────────────────────────────────
    ouro: List[Dict[str, Any]] = []
    stats = {"cruzados_zidane": 0, "sem_cruzamento": 0, "ouro": 0, "prata": 0, "bronze": 0}

    for r in records:
        dep     = r.get("deputado", "")
        partido = r.get("partido")
        t_dep   = totais.get(dep, {})

        # Cruzamento com Zidane
        zid = cruzar_com_zidane(dep, partido, mapa_zidane)

        # Herda parlamentar_id do Zidane se disponível
        parlamentar_id = None
        url_perfil     = None
        if zid:
            parlamentar_id = zid.get("parlamentar_id")
            url_perfil     = zid.get("url_perfil")
            stats["cruzados_zidane"] += 1
        else:
            stats["sem_cruzamento"] += 1

        # Eleva score se cruzado
        score_base = float(r.get("qualidade_score") or 0.6)
        score_final = min(1.0, score_base + (0.10 if zid else 0))
        nivel_final = "ouro" if score_final >= 0.85 else ("prata" if score_final >= 0.60 else "bronze")
        stats[nivel_final] = stats.get(nivel_final, 0) + 1

        record_ouro = {
            **r,  # herda tudo do Prata
            "parlamentar_id":      parlamentar_id,
            "url_perfil_alba":     url_perfil,
            "cruzado_zidane":      zid is not None,
            "valor_total_deputado": t_dep.get("valor_total", 0.0),
            "qtd_emendas_deputado": t_dep.get("qtd", 0),
            "media_emenda_deputado": round(
                t_dep["valor_total"] / t_dep["qtd"], 2
            ) if t_dep.get("qtd", 0) > 0 else 0.0,
            "ranking_valor": rank_map.get(dep, 0),
            "nivel_qualidade":  nivel_final,
            "qualidade_score":  score_final,
            "enriquecido_em":   datetime.utcnow().isoformat() + "Z",
        }
        ouro.append(record_ouro)

    print(f"\n{C_WHITE}📊 Resultado do enriquecimento:{C_END}")
    print(f"   🔗 Cruzados Zidane : {stats['cruzados_zidane']}")
    print(f"   ⚠️  Sem cruzamento : {stats['sem_cruzamento']}")
    print(f"   🥇 Ouro            : {stats['ouro']}")
    print(f"   🥈 Prata           : {stats['prata']}")
    print(f"   🥉 Bronze          : {stats['bronze']}")

    if args.dry_run:
        print(f"\n{C_YELLOW}⚠️  DRY-RUN: Nenhum arquivo salvo.{C_END}")
        if ouro:
            print_status("Amostra do 1º registro Ouro:", "info")
            print(json.dumps(ouro[0], ensure_ascii=False, indent=2))
        sys.exit(0)

    ouro_dir = base_dir / "data" / "saida" / "emendas_federais" / "ouro"
    ouro_dir.mkdir(parents=True, exist_ok=True)
    out_file = ouro_dir / f"emendas_federais_ba_{args.ano}_ouro.json"
    output = {
        "total":      len(ouro),
        "ano":        args.ano,
        "uf":         "BA",
        "esfera":     "federal",
        "gerado_em":  datetime.utcnow().isoformat() + "Z",
        "versao":     VERSAO,
        "stats":      stats,
        "records":    ouro
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"PELÉ-C CONCLUÍDO! {C_BOLD}{len(ouro)}{C_END} registros Ouro gerados.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END}", "info")
    print_status(f"Próximo passo: python agent_pele_d_loader.py --ano {args.ano} --dry-run", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    main()
