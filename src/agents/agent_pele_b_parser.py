#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-B v2.2 — PARSER & NORMALIZADOR (EMENDAS ESTADUAIS BA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Bronze gerado pelo Pelé-A1, normalizar campos,
         padronizar partidos, gerar prisma_id e produzir JSON Prata
         pronto para o Pelé-C enriquecer.

ENTRADA: data/saida/pele/bronze/pele_estadual_{ano}_bronze.json
OUTPUT:  data/saida/pele/prata/pele_estadual_{ano}_prata.json

ORIGEM:  SEMPRE estadual (SIGA-BA / dados.ba.gov.br)
TABELA DESTINO FINAL: emendas_estaduais_ba

USO:
    python agent_pele_b_parser.py --ano 2024
    python agent_pele_b_parser.py --ano 2024 --dry-run
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

VERSAO = "v2.2-prisma-pele-b-estadual"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Normalização Bronze → Prata para Emendas Estaduais BA (SIGA-BA).",
        "especialidade": "Parser estadual BA — tabela destino: emendas_estaduais_ba",
        "protocolo_tecnico": "Pure Python (unicodedata + re + hashlib)",
        "camada_dados": "Prata (Normalizado)",
        "esfera": "estadual",
        "uf": "BA",
        "fonte_portal": "siga_ba",
        "tabela_supabase": "emendas_estaduais_ba",
        "seguranca": "Sem acesso à internet. Processa apenas dados locais."
    },
    "diretrizes": [
        "1. Lê o JSON Bronze estadual (SIGA-BA).",
        "2. Normaliza nome do deputado (title case).",
        "3. Padroniza sigla do partido (uppercase).",
        "4. Normaliza valores monetários para float.",
        "5. Gera prisma_id MD5 único por registro.",
        "6. Detecta qualidade do registro (ouro/prata/bronze).",
        "7. Salva JSON Prata pronto para o Pelé-C."
    ]
}

# ── Normalização de Partidos ────────────────────────────────────────────────────────
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

# ── Estética Terminal ──────────────────────────────────────────────────────────────────────────────
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
    print(f"\n{C_PURPLE}\u2554" + "\u2550"*(width-2) + f"\u2557{C_END}")
    print(f"{C_PURPLE}\u2551{C_BOLD}{C_CYAN} {title.center(width-4)} {C_END}{C_PURPLE}\u2551{C_END}")
    print(f"{C_PURPLE}\u255a" + "\u2550"*(width-2) + f"\u255d{C_END}\n")

def print_status(msg: str, status="info"):
    icons  = {"info": "\U0001f539", "success": "\u2705", "error": "\u274c", "warn": "\u26a0\ufe0f", "process": "\u2699\ufe0f"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '\U0001f539')} {msg}{C_END}")


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
    if re.match(r'^[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00c7/\-]{1,12}$', up):
        return up.replace("-BA", "").replace("-RN", "").strip()
    return str(partido).strip().upper()


def gerar_prisma_id(ano: str, parlamentar_nome: str, numero_emenda: str, orgao: str) -> str:
    """Gera prisma_id MD5 único para emendas estaduais BA.
    
    Chave: siga_ba:{ano}:{nome_normalizado}:{numero_emenda}:{orgao}
    Garante idempotência no upsert do Pelé-D (on_conflict=prisma_id).
    """
    chave = f"siga_ba:{ano}:{normalizar_texto(parlamentar_nome) or ''}:{numero_emenda or ''}:{orgao or ''}"
    return hashlib.md5(chave.encode("utf-8")).hexdigest()


def calcular_qualidade(record: Dict) -> tuple:
    """Retorna (nivel_qualidade, score) de 0.0 a 1.0.
    
    Critérios:
      prisma_id(2) + parlamentar_nome(1) + numero_emenda(1) + ano(1)
      + valor_empenhado>0(1) + valor_pago>0(1) + orgao(1) + acao(1) + municipio(1)
    """
    pontos = 0
    total  = 10
    if record.get("prisma_id"):                         pontos += 2
    if record.get("parlamentar_nome"):                  pontos += 1
    if record.get("numero_emenda"):                     pontos += 1
    if record.get("ano"):                               pontos += 1
    if float(record.get("valor_empenhado") or 0) > 0:  pontos += 1
    if float(record.get("valor_pago") or 0) > 0:       pontos += 1
    if record.get("orgao"):                             pontos += 1
    if record.get("acao"):                              pontos += 1
    if record.get("municipio"):                         pontos += 1
    score = round(min(pontos, total) / total, 2)
    nivel = "ouro" if score >= 0.85 else ("prata" if score >= 0.60 else "bronze")
    return nivel, score


def main():
    parser = argparse.ArgumentParser(
        description="Pelé-B v2.2: Parser/Normalizador Emendas Estaduais BA → emendas_estaduais_ba"
    )
    parser.add_argument("--ano",     type=str, required=True, help="Ano dos dados (ex: 2024)")
    parser.add_argument("--dry-run", action="store_true",     help="Processa sem salvar")
    args = parser.parse_args()

    print_header(f"PEL\u00c9-B {VERSAO} | PARSER ESTADUAL BA — {args.ano}")

    base_dir    = Path(__file__).resolve().parent.parent.parent
    bronze_dir  = base_dir / "data" / "saida" / "pele" / "bronze"
    bronze_file = bronze_dir / f"pele_estadual_{args.ano}_bronze.json"

    if not bronze_file.exists():
        print_status(f"Bronze não encontrado: {bronze_file.name}", "error")
        print_status(
            f"Execute primeiro: python agent_pele_a1_estadual.py --pasta ./emendasparlamentares --ano {args.ano}",
            "warn"
        )
        sys.exit(1)

    print_status(f"Lendo Bronze: {bronze_file.name}", "process")
    with open(bronze_file, "r", encoding="utf-8") as f:
        bronze_data = json.load(f)

    records_bronze = bronze_data.get("records", [])
    total = len(records_bronze)
    print_status(f"Registros Bronze (estadual BA): {total}", "info")

    prata: List[Dict[str, Any]] = []
    stats = {"ouro": 0, "prata": 0, "bronze": 0, "sem_valor": 0}

    for r in records_bronze:
        parlamentar_nome = normalizar_texto(r.get("parlamentar_nome") or r.get("deputado_nome")) or ""
        partido          = normalizar_partido(r.get("partido"))
        ano_str          = str(r.get("ano") or args.ano).strip()
        numero_emenda    = str(r.get("numero_emenda") or r.get("num_codigo") or "").strip()
        orgao            = str(r.get("orgao") or "").strip()

        val_orcado_inicial = float(r.get("valor_orcado_inicial") or 0)
        val_orcado_atual   = float(r.get("valor_orcado_atual") or r.get("valor_orcado_inicial") or 0)
        val_empenhado      = float(r.get("valor_empenhado") or 0)
        val_liquidado      = float(r.get("valor_liquidado") or 0)
        val_pago           = float(r.get("valor_pago") or 0)
        val_restos         = float(r.get("valor_restos_pagar") or 0)

        if val_empenhado == 0:
            stats["sem_valor"] += 1

        # Gera ou reutiliza prisma_id (chave de upsert no Supabase)
        prisma_id = r.get("prisma_id") or gerar_prisma_id(ano_str, parlamentar_nome, numero_emenda, orgao)

        record_prata: Dict[str, Any] = {
            # ── Chave de upsert (on_conflict no Pelé-D) ───────────────────────────────────
            "prisma_id":          prisma_id,

            # ── Identidade / Origem ──────────────────────────────────────────────────
            "esfera":             "estadual",
            "uf":                 "BA",
            "fonte_portal":       "siga_ba",
            "ano":                int(ano_str) if ano_str.isdigit() else None,

            # ── Deputado normalizado ───────────────────────────────────────────────────
            "parlamentar_nome":   parlamentar_nome,
            "parlamentar_nome_raw": r.get("parlamentar_nome") or r.get("deputado_nome"),
            "partido":            partido,
            # Preenchido pelo Pelé-C via cruzamento Zidane:
            "parlamentar_id":     None,

            # ── Código / Emenda ───────────────────────────────────────────────────────
            "numero_emenda":      numero_emenda or None,
            "tipo_emenda":        r.get("tipo_emenda"),

            # ── Classificação orçamentária ───────────────────────────────────────────
            "orgao":              orgao or None,
            "funcao":             r.get("funcao"),
            "subfuncao":          r.get("subfuncao"),
            "programa":           r.get("programa"),
            "acao":               r.get("acao"),

            # ── Localização ───────────────────────────────────────────────────────────────
            "municipio":          r.get("municipio"),

            # ── Valores ────────────────────────────────────────────────────────────────────
            "valor_orcado_atual":  val_orcado_atual,
            "valor_empenhado":     val_empenhado,
            "valor_liquidado":     val_liquidado,
            "valor_pago":          val_pago,
            "valor_restos_pagar":  val_restos,
            # percentual_empenhado e percentual_pago são GERADOS pelo banco (colunas generated)

            # ── Metadados ──────────────────────────────────────────────────────────────────
            "url_transparencia":   r.get("url_transparencia"),
            "nivel_qualidade":     None,
            "qualidade_score":     None,
            "processado_em":       datetime.utcnow().isoformat() + "Z",
            "versao_agente":       VERSAO,
        }

        nivel, score = calcular_qualidade(record_prata)
        record_prata["nivel_qualidade"] = nivel
        record_prata["qualidade_score"] = score
        stats[nivel] = stats.get(nivel, 0) + 1

        prata.append(record_prata)

    print(f"\n{C_WHITE}\U0001f4ca Resultado da normalização (estadual BA):{C_END}")
    print(f"   \U0001f7e1 Total Bronze       : {total}")
    print(f"   \U0001f947 Nível Ouro         : {stats['ouro']}")
    print(f"   \U0001f948 Nível Prata        : {stats['prata']}")
    print(f"   \U0001f949 Nível Bronze       : {stats['bronze']}")
    print(f"   \u26a0\ufe0f  Sem valor empenh.  : {stats['sem_valor']}")

    if args.dry_run:
        print(f"\n{C_YELLOW}\u26a0\ufe0f  DRY-RUN: Nenhum arquivo salvo.{C_END}")
        if prata:
            print_status("Amostra do 1\u00ba registro Prata:", "info")
            print(json.dumps(prata[0], ensure_ascii=False, indent=2))
        sys.exit(0)

    prata_dir  = base_dir / "data" / "saida" / "pele" / "prata"
    prata_dir.mkdir(parents=True, exist_ok=True)
    out_file   = prata_dir / f"pele_estadual_{args.ano}_prata.json"

    output = {
        "total":          len(prata),
        "origem":         "estadual",
        "esfera":         "estadual",
        "uf":             "BA",
        "fonte_portal":   "siga_ba",
        "tabela_destino": "emendas_estaduais_ba",
        "ano":            args.ano,
        "gerado_em":      datetime.utcnow().isoformat() + "Z",
        "versao":         VERSAO,
        "stats":          stats,
        "records":        prata,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501{C_END}")
    print_status(f"PEL\u00c9-B CONCLU\u00cdDO! {C_BOLD}{len(prata)}{C_END} registros Prata (estadual BA) gerados.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END}", "info")
    print_status(f"Pr\u00f3ximo passo: python agent_pele_c_aguia.py --ano {args.ano}", "info")
    print(f"{C_PURPLE}\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501{C_END}\n")


if __name__ == "__main__":
    main()
