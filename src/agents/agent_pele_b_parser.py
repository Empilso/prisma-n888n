#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-B v2.0 — PARSER & NORMALIZADOR UNIFICADO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Bronze gerado pelo Pelé-A1 (estadual) OU Pelé-A2 (federal),
         normalizar campos comuns, tratar NULLs dos exclusivos de cada origem,
         padronizar partidos, gerar prisma_id e produzir JSON Prata unificado.

ENTRADA: data/saida/pele/bronze/pele_{origem}_{ano}_bronze.json
OUTPUT:  data/saida/pele/prata/pele_{origem}_{ano}_prata.json

CHAVE DE SEPARAÇÃO: campo 'origem' = 'estadual' | 'federal'
SUFIXO num_codigo:  *.5 = estadual | *.6 = federal

USO:
    python agent_pele_b_parser.py --origem estadual --ano 2024
    python agent_pele_b_parser.py --origem federal  --ano 2024
    python agent_pele_b_parser.py --origem estadual --ano 2024 --dry-run
"""

import os
import sys
import re
import json
import hashlib
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

VERSAO = "v2.0-prisma-pele-b-parser-unificado"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Normalização unificada de Bronze → Prata para Emendas Estaduais e Transferências Federais BA.",
        "especialidade": "Parser multi-origem: estadual (*.5) e federal (*.6)",
        "protocolo_tecnico": "Pure Python (unicodedata + re + hashlib)",
        "camada_dados": "Prata (Normalizado)",
        "seguranca": "Sem acesso à internet. Processa apenas dados locais."
    },
    "origens_suportadas": ["estadual", "federal"],
    "diretrizes": [
        "1. Lê o JSON Bronze da origem especificada.",
        "2. Normaliza nome do deputado (title case).",
        "3. Padroniza sigla do partido (uppercase).",
        "4. Normaliza valores monetários para float (já vêm normalizados do A1/A2).",
        "5. Trata campos exclusivos: NULL p/ campos que não existem na origem.",
        "6. Calcula taxa_execucao se não calculada.",
        "7. Detecta qualidade do registro (ouro/prata/bronze).",
        "8. Salva JSON Prata pronto para o Pelé-C."
    ]
}

# ── Normalização de Partidos ────────────────────────────────────────────────────
PARTIDOS_MAPA = {
    "pt dos trabalhadores": "PT", "partido dos trabalhadores": "PT",
    "psdb": "PSDB", "partido da social democracia brasileira": "PSDB",
    "mdb": "MDB", "pmdb": "MDB", "movimento democrático brasileiro": "MDB",
    "pp": "PP", "progressistas": "PP",
    "pl": "PL", "partido liberal": "PL", "pl/rn": "PL", "pl-ba": "PL",
    "psd": "PSD", "partido social democrático": "PSD",
    "união brasil": "UNIÃO", "uniao brasil": "UNIÃO", "união": "UNIÃO",
    "republicanos": "REPUBLICANOS",
    "avante": "AVANTE",
    "solidariedade": "SOLIDARIEDADE",
    "psb": "PSB", "partido socialista brasileiro": "PSB",
    "pdt": "PDT", "partido democrático trabalhista": "PDT",
    "pv": "PV", "partido verde": "PV",
    "rede": "REDE", "rede sustentabilidade": "REDE",
    "psol": "PSOL", "partido socialismo e liberdade": "PSOL",
    "pcdo b": "PCdoB", "pc do b": "PCdoB", "pcdob": "PCdoB",
    "dem": "DEM", "democratas": "DEM",
    "novo": "NOVO", "podemos": "PODEMOS",
    "cidadania": "CIDADANIA",
    "patriota": "PATRIOTA",
    "pros": "PROS",
    "dc": "DC", "democracia cristã": "DC",
    "prtb": "PRTB",
    "agir": "AGIR",
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
    width = 72
    print(f"\n{C_PURPLE}╔" + "═"*(width-2) + f"╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN} {title.center(width-4)} {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚" + "═"*(width-2) + f"╝{C_END}\n")

def print_status(msg: str, status="info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '🔹')} {msg}{C_END}")


def normalizar_texto(s) -> Optional[str]:
    if not s:
        return None
    return " ".join(str(s).strip().title().split())


def normalizar_partido(partido) -> Optional[str]:
    if not partido:
        return None
    chave = str(partido).strip().lower()
    if chave in PARTIDOS_MAPA:
        return PARTIDOS_MAPA[chave]
    up = str(partido).strip().upper()
    if re.match(r'^[A-ZÁÉÍÓÚÇ/\-]{1,12}$', up):
        return up.replace("-BA", "").replace("-RN", "").strip()
    return str(partido).strip().upper()


def calcular_qualidade(record: Dict) -> tuple:
    """Retorna (nivel_qualidade, score) de 0.0 a 1.0."""
    pontos = 0
    total  = 10
    if record.get("prisma_id"):                 pontos += 1
    if record.get("deputado_nome") or record.get("deputado_cod"): pontos += 1
    if record.get("num_codigo"):                pontos += 1
    if record.get("ano_exercicio"):             pontos += 1
    if record.get("valor_empenhado", 0) > 0:    pontos += 1
    if record.get("valor_pago", 0) > 0:         pontos += 1
    if record.get("orgao"):                     pontos += 1
    if record.get("acao_programa"):             pontos += 1
    if record.get("pagamentos"):                pontos += 1
    # Bônus por campos exclusivos preenchidos
    if record.get("origem") == "estadual" and record.get("tem_processo_sei"): pontos += 1
    if record.get("origem") == "federal"  and record.get("ministerio_origem"): pontos += 1
    score = round(min(pontos, total) / total, 2)
    nivel = "ouro" if score >= 0.85 else ("prata" if score >= 0.60 else "bronze")
    return nivel, score


def main():
    parser = argparse.ArgumentParser(
        description="Pelé-B v2.0: Parser/Normalizador Unificado (estadual + federal)"
    )
    parser.add_argument("--origem",  type=str, required=True,
                        choices=["estadual", "federal"],
                        help="Origem dos dados: estadual | federal")
    parser.add_argument("--ano",     type=str, required=True,
                        help="Ano dos dados (ex: 2024)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Processa sem salvar")
    args = parser.parse_args()

    print_header(f"PELÉ-B {VERSAO} | PARSER UNIFICADO — {args.origem.upper()} {args.ano}")

    base_dir    = Path(__file__).resolve().parent.parent.parent
    bronze_dir  = base_dir / "data" / "saida" / "pele" / "bronze"
    bronze_file = bronze_dir / f"pele_{args.origem}_{args.ano}_bronze.json"

    if not bronze_file.exists():
        print_status(f"Bronze não encontrado: {bronze_file.name}", "error")
        agente = "agent_pele_a1_estadual.py" if args.origem == "estadual" else "agent_pele_a2_federal.py"
        print_status(f"Execute primeiro: python {agente} --pasta ./... --ano {args.ano}", "warn")
        sys.exit(1)

    print_status(f"Lendo Bronze: {bronze_file.name}", "process")
    with open(bronze_file, "r", encoding="utf-8") as f:
        bronze_data = json.load(f)

    records_bronze = bronze_data.get("records", [])
    total = len(records_bronze)
    print_status(f"Registros Bronze ({args.origem}): {total}", "info")

    prata: List[Dict[str, Any]] = []
    stats = {"ouro": 0, "prata": 0, "bronze": 0, "sem_valor": 0,
             "com_sei": 0, "com_ministerio": 0}

    for r in records_bronze:
        deputado_nome = normalizar_texto(r.get("deputado_nome")) or ""
        deputado_cod  = str(r.get("deputado_cod") or "").strip()
        partido       = normalizar_partido(r.get("partido"))
        origem        = r.get("origem", args.origem)

        val_empenhado = float(r.get("valor_empenhado") or 0)
        val_pago      = float(r.get("valor_pago") or 0)
        taxa_exec     = float(r.get("taxa_execucao") or 0)
        if taxa_exec == 0 and val_empenhado > 0:
            taxa_exec = round(val_pago / val_empenhado, 4)

        if val_empenhado == 0:
            stats["sem_valor"] += 1

        # Campos exclusivos por origem
        ministerio   = r.get("ministerio_origem")    # None se estadual
        num_emenda_f = r.get("num_emenda_federal")   # None se estadual
        ano_emenda_f = r.get("ano_emenda_federal")   # None se estadual
        processos_sei = r.get("processos_sei", [])   # [] se federal
        tem_sei       = r.get("tem_processo_sei", False)

        if ministerio:   stats["com_ministerio"] += 1
        if tem_sei:       stats["com_sei"] += 1

        record_prata: Dict[str, Any] = {
            # ── Identidade ───────────────────────────────────────────────
            "prisma_id":             r.get("prisma_id"),
            "origem":                origem,
            "sufixo_origem":         r.get("sufixo_origem"),
            "esfera":                r.get("esfera"),
            "uf":                    "BA",
            "fonte_portal":          r.get("fonte_portal"),
            "ano_exercicio":         str(r.get("ano_exercicio") or args.ano).strip(),

            # ── Código ───────────────────────────────────────────────────
            "num_codigo":            r.get("num_codigo"),

            # ── Deputado normalizado ──────────────────────────────────────
            "deputado_cod":          deputado_cod,
            "deputado_nome":         deputado_nome,
            "deputado_nome_raw":     r.get("deputado_nome"),
            "partido":               partido,
            # Será preenchido pelo Pelé-C via cruzamento Zidane:
            "parlamentar_id":        None,
            "url_perfil":            None,

            # ── Campos exclusivos por origem ──────────────────────────────
            # Federal: ministerio, num_emenda, ano_emenda | NULL se estadual
            "ministerio_origem":     ministerio,
            "num_emenda_federal":    num_emenda_f,
            "ano_emenda_federal":    ano_emenda_f,
            # Estadual: processos SEI | [] se federal
            "processos_sei":         processos_sei,
            "tem_processo_sei":      tem_sei,

            # ── Órgão / Ação ──────────────────────────────────────────────
            "orgao":                 r.get("orgao"),
            "sgl_orgao":             r.get("sgl_orgao"),
            "unidade_orcamentaria": r.get("unidade_orcamentaria"),
            "nom_res_unidade":       r.get("nom_res_unidade"),
            "acao_programa":         r.get("acao_programa"),
            "cod_subfonte_recurso":  r.get("cod_subfonte_recurso"),
            "orgao_executor":        r.get("orgao_executor"),

            # ── Valores ──────────────────────────────────────────────────
            "valor_orcado_inicial":  float(r.get("valor_orcado_inicial") or 0),
            "valor_orcado_atual":    float(r.get("valor_orcado_atual") or 0),
            "valor_empenhado":       val_empenhado,
            "valor_liquidado":       float(r.get("valor_liquidado") or 0),
            "valor_pago":            val_pago,
            "taxa_execucao":         taxa_exec,

            # ── Instrumento de Captação (exclusivo federal) ───────────────
            "instrumento_captacao":  r.get("instrumento_captacao"),  # None se estadual

            # ── Pagamentos e liquidações ──────────────────────────────────
            "pagamentos":            r.get("pagamentos", []),
            "liquidacoes":           r.get("liquidacoes", []),
            "qtd_pagamentos":        len(r.get("pagamentos", [])),
            "qtd_liquidacoes":       len(r.get("liquidacoes", [])),

            # ── Qualidade ─────────────────────────────────────────────────
            "nivel_qualidade":       None,
            "qualidade_score":       None,

            # ── Metadados ─────────────────────────────────────────────────
            "processado_em":         datetime.utcnow().isoformat() + "Z",
            "versao_agente":         VERSAO,
        }

        nivel, score = calcular_qualidade(record_prata)
        record_prata["nivel_qualidade"] = nivel
        record_prata["qualidade_score"] = score
        stats[nivel] = stats.get(nivel, 0) + 1

        prata.append(record_prata)

    print(f"\n{C_WHITE}📊 Resultado da normalização ({args.origem}):{C_END}")
    print(f"   🟡 Total Bronze       : {total}")
    print(f"   🥇 Nível Ouro         : {stats['ouro']}")
    print(f"   🥈 Nível Prata        : {stats['prata']}")
    print(f"   🥉 Nível Bronze       : {stats['bronze']}")
    print(f"   ⚠️  Sem valor empenh.  : {stats['sem_valor']}")
    if args.origem == "estadual":
        print(f"   📋 Com processo SEI   : {stats['com_sei']}")
    if args.origem == "federal":
        print(f"   🏛️  Com ministério     : {stats['com_ministerio']}")

    if args.dry_run:
        print(f"\n{C_YELLOW}⚠️  DRY-RUN: Nenhum arquivo salvo.{C_END}")
        if prata:
            print_status("Amostra do 1º registro Prata:", "info")
            sample = {k: v for k, v in prata[0].items()
                      if k not in ["pagamentos", "liquidacoes"]}
            sample["pagamentos_count"] = prata[0]["qtd_pagamentos"]
            print(json.dumps(sample, ensure_ascii=False, indent=2))
        sys.exit(0)

    prata_dir  = base_dir / "data" / "saida" / "pele" / "prata"
    prata_dir.mkdir(parents=True, exist_ok=True)
    out_file   = prata_dir / f"pele_{args.origem}_{args.ano}_prata.json"

    output = {
        "total":        len(prata),
        "origem":       args.origem,
        "esfera":       bronze_data.get("esfera"),
        "uf":           "BA",
        "ano":          args.ano,
        "gerado_em":    datetime.utcnow().isoformat() + "Z",
        "versao":       VERSAO,
        "stats":        stats,
        "records":      prata,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"PELÉ-B CONCLUÍDO! {C_BOLD}{len(prata)}{C_END} registros Prata ({args.origem}) gerados.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END}", "info")
    print_status(f"Próximo passo: python agent_pele_c_aguia.py --origem {args.origem} --ano {args.ano}", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    main()
