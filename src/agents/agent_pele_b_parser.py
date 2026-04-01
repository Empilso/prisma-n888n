#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-B v1.0 — PARSER & NORMALIZADOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Bronze gerado pelo Pelé-A, normalizar campos,
         limpar encoding BR, padronizar partidos e gerar JSON Prata.

ENTRADA: data/saida/emendas_federais/raw/emendas_federais_ba_{ano}_bronze.json
OUTPUT:  data/saida/emendas_federais/prata/emendas_federais_ba_{ano}_prata.json

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

VERSAO = "v1.0-prisma-pele-parser"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Normalização e limpeza dos dados Bronze de Emendas Federais BA.",
        "especialidade": "Normalização textual, partidos, valores monetários BR",
        "protocolo_tecnico": "Pure Python (unicodedata + re + hashlib)",
        "camada_dados": "Prata (Normalizado)",
        "seguranca": "Sem acesso à internet. Processa apenas dados locais."
    },
    "diretrizes": [
        "1. Lê o JSON Bronze gerado pelo Pelé-A.",
        "2. Normaliza nome do deputado (title case + remove acentos excessivos).",
        "3. Padroniza sigla do partido (uppercase, remove espaços).",
        "4. Gera prisma_id único via MD5 (codigo + deputado + ano).",
        "5. Normaliza valores monetários para float.",
        "6. Classifica tipo_emenda em categorias padronizadas.",
        "7. Detecta e registra qualidade do registro (ouro/prata/bronze).",
        "8. Salva JSON Prata pronto para o Pelé-C."
    ]
}

# ── Normalização de Partidos ────────────────────────────────────────────────────
PARTIDOS_MAPA = {
    "pt dos trabalhadores": "PT", "partido dos trabalhadores": "PT",
    "psdb": "PSDB", "partido da social democracia brasileira": "PSDB",
    "mdb": "MDB", "pmdb": "MDB", "movimento democrático brasileiro": "MDB",
    "pp": "PP", "progressistas": "PP",
    "pl": "PL", "partido liberal": "PL",
    "pl/rn": "PL", "pl-ba": "PL",
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

# ── Normalização de tipo_emenda ────────────────────────────────────────────────
TIPO_MAPA = {
    "individual": "Individual",
    "bancada": "Bancada",
    "comissao": "Comissão",
    "comissão": "Comissão",
    "impositiva": "Individual",
    "nao impositiva": "Individual Não-Impositiva",
    "não impositiva": "Individual Não-Impositiva",
    "emenda de relator": "Relator-Geral (RP9)",
    "rp9": "Relator-Geral (RP9)",
    "relator": "Relator-Geral (RP9)",
    "transferencia especial": "Transferência Especial (Pix)",
    "pix": "Transferência Especial (Pix)",
    "transferência especial": "Transferência Especial (Pix)",
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


def normalizar_texto(s: str | None) -> str | None:
    """Title case limpo, sem quebras duplas."""
    if not s:
        return None
    return " ".join(s.strip().title().split())


def normalizar_partido(partido: str | None) -> str | None:
    if not partido:
        return None
    chave = partido.strip().lower()
    # Tenta direto
    if chave in PARTIDOS_MAPA:
        return PARTIDOS_MAPA[chave]
    # Tenta uppercase
    up = partido.strip().upper()
    # Já é sigla curta (≤12 chars, tudo maiúsculo)
    if re.match(r'^[A-ZÁÉÍÓÚÇ/\-]{1,12}$', up):
        return up.replace("-BA", "").replace("-RN", "").strip()
    return partido.strip().upper()


def normalizar_tipo_emenda(tipo: str | None) -> str | None:
    if not tipo:
        return None
    chave = tipo.strip().lower()
    for k, v in TIPO_MAPA.items():
        if k in chave:
            return v
    return tipo.strip().title()


def gerar_prisma_id(codigo: str | None, deputado: str, ano: str) -> str:
    payload = f"{(codigo or '').strip().lower()}{deputado.strip().lower()}{ano.strip()}"
    return hashlib.md5(payload.encode()).hexdigest()


def calcular_qualidade(record: Dict) -> tuple[str, float]:
    """Retorna (nivel_qualidade, score) de 0.0 a 1.0."""
    pontos = 0
    total  = 8
    if record.get("prisma_id"):         pontos += 1
    if record.get("deputado"):          pontos += 1
    if record.get("partido"):           pontos += 1
    if record.get("ano"):               pontos += 1
    if record.get("valor", 0) > 0:      pontos += 1
    if record.get("tipo_emenda"):       pontos += 1
    if record.get("codigo"):            pontos += 1
    if record.get("beneficiario") or record.get("objeto"): pontos += 1
    score = round(pontos / total, 2)
    nivel = "ouro" if score >= 0.85 else ("prata" if score >= 0.60 else "bronze")
    return nivel, score


def main():
    parser = argparse.ArgumentParser(description="Pelé-B v1.0: Parser/Normalizador de Emendas Federais BA")
    parser.add_argument("--ano",     type=str, required=True, help="Ano dos dados (ex: 2024)")
    parser.add_argument("--dry-run", action="store_true",     help="Processa sem salvar")
    args = parser.parse_args()

    print_header(f"PELÉ-B {VERSAO} | PARSER & NORMALIZADOR — ANO {args.ano}")

    base_dir   = Path(__file__).resolve().parent.parent.parent
    bronze_dir = base_dir / "data" / "saida" / "emendas_federais" / "raw"
    bronze_file = bronze_dir / f"emendas_federais_ba_{args.ano}_bronze.json"

    if not bronze_file.exists():
        print_status(f"Bronze não encontrado: {bronze_file.name}", "error")
        print_status("Execute o Pelé-A primeiro: python agent_pele_a_ingestor.py --arquivo ...", "warn")
        sys.exit(1)

    print_status(f"Lendo Bronze: {bronze_file.name}", "process")
    with open(bronze_file, "r", encoding="utf-8") as f:
        bronze_data = json.load(f)

    records_bronze = bronze_data.get("records", [])
    total = len(records_bronze)
    print_status(f"Registros Bronze: {total}", "info")

    prata: List[Dict[str, Any]] = []
    stats = {"ouro": 0, "prata": 0, "bronze": 0, "sem_valor": 0}

    for i, r in enumerate(records_bronze):
        deputado   = normalizar_texto(r.get("deputado")) or ""
        partido    = normalizar_partido(r.get("partido"))
        ano_rec    = str(r.get("ano") or args.ano).strip()
        valor      = float(r.get("valor") or 0)
        codigo     = str(r.get("codigo") or "").strip()
        tipo_emen  = normalizar_tipo_emenda(r.get("tipo_emenda"))
        prisma_id  = gerar_prisma_id(codigo or None, deputado, ano_rec)
        processado_em = datetime.utcnow().isoformat() + "Z"

        if valor == 0:
            stats["sem_valor"] += 1

        record_prata: Dict[str, Any] = {
            "prisma_id":       prisma_id,
            "esfera":          "federal",
            "uf":              str(r.get("uf") or "BA").upper().strip(),
            "fonte_portal":    "camara_leg_br",
            "deputado":        deputado,
            "nome_deputado_raw": r.get("deputado", "").strip(),
            "partido":         partido,
            "partido_raw":     r.get("partido"),
            "ano":             ano_rec,
            "competencia_ano": ano_rec,
            "valor":           valor,
            "valor_empenhado": float(r.get("empenhado") or 0),
            "valor_liquidado": float(r.get("liquidado") or 0),
            "valor_pago":      float(r.get("pago") or 0),
            "tipo_emenda":     tipo_emen,
            "tipo_emenda_raw": r.get("tipo_emenda"),
            "codigo":          codigo or None,
            "funcao":          r.get("funcao"),
            "subfuncao":       r.get("subfuncao"),
            "programa":        r.get("programa"),
            "acao":            r.get("acao"),
            "localizador":     r.get("localizador"),
            "dotacao":         float(r.get("dotacao") or 0),
            "beneficiario":    r.get("beneficiario"),
            "cnpj_cpf":        r.get("cnpj_cpf"),
            "objeto":          r.get("objeto"),
            "situacao":        r.get("situacao"),
            "nivel_qualidade": None,  # será preenchido abaixo
            "qualidade_score": None,
            "processado_em":   processado_em,
            "linha_csv":       r.get("linha_csv"),
        }

        nivel, score = calcular_qualidade(record_prata)
        record_prata["nivel_qualidade"] = nivel
        record_prata["qualidade_score"] = score
        stats[nivel] = stats.get(nivel, 0) + 1
        prata.append(record_prata)

        if (i + 1) % 500 == 0:
            print_status(f"Processados: {i+1}/{total}...", "process")

    print(f"\n{C_WHITE}📊 Qualidade dos registros:{C_END}")
    print(f"   🥇 Ouro   : {stats['ouro']}")
    print(f"   🥈 Prata  : {stats['prata']}")
    print(f"   🥉 Bronze : {stats['bronze']}")
    print(f"   ⚠️  Sem valor: {stats['sem_valor']}")

    if args.dry_run:
        print(f"\n{C_YELLOW}⚠️  DRY-RUN: Nenhum arquivo salvo.{C_END}")
        print_status("Amostra do 1º registro Prata:", "info")
        if prata:
            print(json.dumps(prata[0], ensure_ascii=False, indent=2))
        sys.exit(0)

    prata_dir = base_dir / "data" / "saida" / "emendas_federais" / "prata"
    prata_dir.mkdir(parents=True, exist_ok=True)
    out_file = prata_dir / f"emendas_federais_ba_{args.ano}_prata.json"
    output = {
        "total":      len(prata),
        "ano":        args.ano,
        "uf":         "BA",
        "esfera":     "federal",
        "gerado_em":  datetime.utcnow().isoformat() + "Z",
        "versao":     VERSAO,
        "stats":      stats,
        "records":    prata
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"PELÉ-B CONCLUÍDO! {C_BOLD}{len(prata)}{C_END} registros Prata gerados.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END}", "info")
    print_status(f"Próximo passo: python agent_pele_c_aguia.py --ano {args.ano}", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    main()
