#!/usr/bin/env python3
"""
🇧🇷 PELÉ-B v3.0 — PARSER & NORMALIZADOR (ESTADUAL + FEDERAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENTRADA: data/saida/pele/bronze/pele_{tipo}_{ano}_bronze.json
SAÍDA:   data/saida/pele/prata/pele_{tipo}_{ano}_prata.json

USO:
    python3 agent_pele_b_parser.py --tipo estadual --ano 2024
    python3 agent_pele_b_parser.py --tipo federal  --ano 2024 --dry-run
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

VERSAO = "pele_b_v1"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Normalização Bronze → Prata para Emendas Estaduais e Transferências Federais BA",
        "especialidade": "Parser dual (estadual + federal)",
        "protocolo_tecnico": "Pure Python (re + json)",
        "camada_dados": "Prata (Normalizado)",
    },
    "diretrizes": [
        "1. Lê Bronze como lista direta (array JSON no root)",
        "2. Detecta tipo via argumento --tipo (estadual|federal)",
        "3. Reutiliza prisma_id do Bronze — NÃO regera",
        "4. Normaliza nomes (Title Case), partidos (sigla), valores (float)",
        "5. Calcula qualidade_score e nivel_qualidade",
        "6. Salva Prata com meta + records"
    ]
}

PARTIDOS_MAPA = {
    "pt": "PT", "partido dos trabalhadores": "PT",
    "psdb": "PSDB", "mdb": "MDB", "pmdb": "MDB",
    "pp": "PP", "progressistas": "PP",
    "pl": "PL", "partido liberal": "PL",
    "psd": "PSD", "união brasil": "UNIÃO", "uniao brasil": "UNIÃO", "união": "UNIÃO",
    "republicanos": "REPUBLICANOS", "avante": "AVANTE", "solidariedade": "SOLIDARIEDADE",
    "psb": "PSB", "pdt": "PDT", "pv": "PV", "rede": "REDE", "psol": "PSOL",
    "pc do b": "PCdoB", "pcdob": "PCdoB", "dem": "DEM", "democratas": "DEM",
    "novo": "NOVO", "podemos": "PODEMOS", "cidadania": "CIDADANIA",
    "patriota": "PATRIOTA", "pros": "PROS", "dc": "DC", "agir": "AGIR",
}

CAMPOS_OBRIGATORIOS = {
    "estadual": ["prisma_id", "parlamentar_nome", "ano", "orgao", "valor_empenhado"],
    "federal":  ["prisma_id", "parlamentar_nome", "ano_exercicio", "orgao", "valor_empenhado", "ministerio_origem"],
}

def title(s):
    if not s:
        return None
    return " ".join(str(s).strip().title().split()) or None

def partido(s):
    if not s:
        return None
    chave = str(s).strip().lower()
    if chave in PARTIDOS_MAPA:
        return PARTIDOS_MAPA[chave]
    up = re.sub(r'[-/](BA|RN|SP|RJ)$', '', str(s).strip().upper()).strip()
    return up or None

def fval(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(".", "").replace(",", "."))
    except Exception:
        return 0.0

def qualidade(record, tipo):
    campos = CAMPOS_OBRIGATORIOS.get(tipo, [])
    score = 1.0
    for c in campos:
        v = record.get(c)
        if not v or (isinstance(v, float) and v == 0.0):
            score -= 0.1
    score = round(max(0.1, score), 2)
    nivel = "ouro" if score >= 0.85 else ("prata" if score >= 0.60 else "bronze")
    return score, nivel

def cor(txt, c): return f"\033[{c}m{txt}\033[0m"
def ok(t): print(cor(f"✅ {t}", "92"))
def info(t): print(cor(f"🔹 {t}", "96"))
def warn(t): print(cor(f"⚠️  {t}", "93"))
def erro(t): print(cor(f"❌ {t}", "91"))

def normalizar_estadual(r, ano):
    rec = {
        "prisma_id":            r.get("prisma_id"),
        "esfera":               "estadual",
        "origem":               r.get("origem", "estadual"),
        "sufixo_origem":        r.get("sufixo_origem", ".5"),
        "uf":                   "BA",
        "fonte_portal":         "siga_ba",
        "ano":                  int(r.get("ano_exercicio") or ano),
        "ano_exercicio":        str(r.get("ano_exercicio") or ano),
        "num_codigo":           r.get("num_codigo"),
        "parlamentar_nome":     title(r.get("deputado_nome") or r.get("parlamentar_nome")),
        "parlamentar_nome_raw": r.get("deputado_nome") or r.get("parlamentar_nome"),
        "deputado_cod":         r.get("deputado_cod"),
        "partido":              partido(r.get("partido")),
        "parlamentar_id":       None,
        "orgao":                title(r.get("orgao")),
        "sgl_orgao":            r.get("sgl_orgao"),
        "unidade_orcamentaria": title(r.get("unidade_orcamentaria")),
        "nom_res_unidade":      r.get("nom_res_unidade"),
        "acao_programa":        title(r.get("acao_programa")),
        "cod_subfonte_recurso": r.get("cod_subfonte_recurso"),
        "orgao_executor":       title(r.get("orgao_executor")),
        "valor_orcado_inicial": fval(r.get("valor_orcado_inicial")),
        "valor_orcado_atual":   fval(r.get("valor_orcado_atual")),
        "valor_empenhado":      fval(r.get("valor_empenhado")),
        "valor_liquidado":      fval(r.get("valor_liquidado")),
        "valor_pago":           fval(r.get("valor_pago")),
        "taxa_execucao":        fval(r.get("taxa_execucao")),
        "pagamentos":           r.get("pagamentos", []),
        "liquidacoes":          r.get("liquidacoes", []),
        "processos_sei":        r.get("processos_sei", []),
        "tem_processo_sei":     r.get("tem_processo_sei", False),
        "ministerio_origem":    None,
        "num_emenda_federal":   None,
        "ano_emenda_federal":   None,
        "instrumento_captacao": None,
        "ingerido_em":          r.get("ingerido_em"),
        "ingestor_versao":      r.get("versao_agente"),
        "parser_versao":        VERSAO,
        "processado_em":        datetime.now(timezone.utc).isoformat(),
    }
    score, nivel = qualidade(rec, "estadual")
    rec["qualidade_score"] = score
    rec["nivel_qualidade"] = nivel
    return rec

def normalizar_federal(r, ano):
    rec = {
        "prisma_id":            r.get("prisma_id"),
        "esfera":               "federal_transferencia",
        "origem":               r.get("origem", "federal"),
        "sufixo_origem":        r.get("sufixo_origem", ".6"),
        "uf":                   "BA",
        "fonte_portal":         "dados_ba_gov_br_transf_especial",
        "ano_exercicio":        int(r.get("ano_exercicio") or ano),
        "num_codigo":           r.get("num_codigo"),
        "parlamentar_nome":     title(r.get("deputado_cod")),
        "parlamentar_nome_raw": r.get("deputado_cod"),
        "deputado_cod":         r.get("deputado_cod"),
        "partido":              partido(r.get("partido")),
        "parlamentar_id":       None,
        "ministerio_origem":    title(r.get("ministerio_origem")),
        "num_emenda_federal":   r.get("num_emenda_federal"),
        "ano_emenda_federal":   r.get("ano_emenda_federal"),
        "orgao":                title(r.get("orgao")),
        "sgl_orgao":            r.get("sgl_orgao"),
        "unidade_orcamentaria": title(r.get("unidade_orcamentaria")),
        "nom_res_unidade":      r.get("nom_res_unidade"),
        "acao_programa":        title(r.get("acao_programa")),
        "cod_subfonte_recurso": r.get("cod_subfonte_recurso"),
        "orgao_executor":       title(r.get("orgao_executor")),
        "valor_orcado_inicial": fval(r.get("valor_orcado_inicial")),
        "valor_orcado_atual":   fval(r.get("valor_orcado_atual")),
        "valor_empenhado":      fval(r.get("valor_empenhado")),
        "valor_liquidado":      fval(r.get("valor_liquidado")),
        "valor_pago":           fval(r.get("valor_pago")),
        "taxa_execucao":        fval(r.get("taxa_execucao")),
        "pagamentos":           r.get("pagamentos", []),
        "liquidacoes":          r.get("liquidacoes", []),
        "instrumento_captacao": r.get("instrumento_captacao"),
        "processos_sei":        [],
        "tem_processo_sei":     False,
        "ingerido_em":          r.get("ingerido_em"),
        "ingestor_versao":      r.get("versao_agente"),
        "parser_versao":        VERSAO,
        "processado_em":        datetime.now(timezone.utc).isoformat(),
    }
    score, nivel = qualidade(rec, "federal")
    rec["qualidade_score"] = score
    rec["nivel_qualidade"] = nivel
    return rec

def processar(tipo, ano, dry_run):
    print(cor(f"\n╔══════════════════════════════════════════════════════╗", "95"))
    print(cor(f"║  PELÉ-B {VERSAO} | {tipo.upper()} {ano}  ║", "95"))
    print(cor(f"╚══════════════════════════════════════════════════════╝\n", "95"))

    base = Path(__file__).resolve().parent.parent.parent
    bronze_path = base / "data/saida/pele/bronze" / f"pele_{tipo}_{ano}_bronze.json"

    if not bronze_path.exists():
        erro(f"Bronze não encontrado: {bronze_path.name}")
        return None

    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    records_raw = bronze if isinstance(bronze, list) else bronze.get("records", [])
    info(f"Bronze carregado: {len(records_raw)} records")

    fn = normalizar_estadual if tipo == "estadual" else normalizar_federal
    records = [fn(r, ano) for r in records_raw]

    stats = {"ouro": 0, "prata": 0, "bronze": 0}
    for r in records:
        stats[r["nivel_qualidade"]] += 1
    score_medio = round(sum(r["qualidade_score"] for r in records) / len(records), 2) if records else 0

    ok(f"Records: {len(records)} | Score médio: {score_medio} | 🥇{stats['ouro']} 🥈{stats['prata']} 🥉{stats['bronze']}")

    if dry_run:
        warn(f"DRY-RUN: {len(records)} records NÃO salvos.")
        print(json.dumps(records[0], ensure_ascii=False, indent=2))
        return stats

    out_dir = base / "data/saida/pele/prata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pele_{tipo}_{ano}_prata.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "tipo": tipo, "ano": int(ano),
                "total_records": len(records),
                "parser_versao": VERSAO,
                "gerado_em": datetime.now(timezone.utc).isoformat(),
                "stats": stats, "score_medio": score_medio,
            },
            "records": records,
        }, f, ensure_ascii=False, indent=2)

    ok(f"Prata salvo: {out_path.name}")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tipo", required=True, choices=["estadual", "federal"])
    parser.add_argument("--ano",  required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    processar(args.tipo, args.ano, args.dry_run)
