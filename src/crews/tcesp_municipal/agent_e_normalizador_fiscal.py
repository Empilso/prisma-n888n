#!/usr/bin/env python3
"""
🧪 AGENT-E: NORMALIZADOR FISCAL TCE-SP — Bronze → Prata
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT:  data/raw/tcesp/bronze/{tipo}_{slug}_{ano}_*_bronze.json
OUTPUT: data/raw/tcesp/prata/{tipo}_{slug}_{ano}_prata.json
FUNÇÃO: Normaliza valores BRL (aceita "1.234,56" E "1234,56"), valida o
        nome do mês contra o número, resolve id_ibge via tcesp_municipios
        (aborta se o município não estiver no cadastro da Fase 1),
        extrai CNPJ/CPF do fornecedor nas despesas.

USO:
    python agent_e_normalizador_fiscal.py --municipio votorantim --ano 2025
"""

import argparse
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

VERSAO = "v1.0"

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina no ambiente ou no .env da raiz do projeto")

DB_CONFIG = {"host": "localhost", "port": 5432, "dbname": "prisma_data",
             "user": "postgres", "password": DB_PASSWORD}

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/raw/tcesp/bronze"
PRATA_DIR = BASE_DIR / "data/raw/tcesp/prata"
REJEITADOS_DIR = BASE_DIR / "data/raw/tcesp/rejeitados"
PRATA_DIR.mkdir(parents=True, exist_ok=True)
REJEITADOS_DIR.mkdir(parents=True, exist_ok=True)

C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

def ok(t): print(f"{C_GREEN}✅ {t}{C_END}")
def info(t): print(f"{C_CYAN}🔹 {t}{C_END}")
def warn(t): print(f"{C_YELLOW}⚠️  {t}{C_END}")
def erro(t): print(f"{C_RED}❌ {t}{C_END}")

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def parse_brl(valor) -> float | None:
    """Aceita '1.234,56', '1234,56', '-123,45'. Retorna None se ilegível."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_data_br(valor) -> str | None:
    """'02/01/2025' → '2025-01-02'."""
    if not valor:
        return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", str(valor).strip())
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def extrair_fornecedor(id_fornecedor: str):
    """'CNPJ - PESSOA JURÍDICA - 00604122000197' → ('CNPJ', '00604122000197')."""
    if not id_fornecedor:
        return None, None
    doc = re.sub(r"\D", "", id_fornecedor)
    tipo = None
    up = id_fornecedor.upper()
    if "CNPJ" in up:
        tipo = "CNPJ"
    elif "CPF" in up:
        tipo = "CPF"
    return tipo, doc or None


def resolver_municipio(slug: str):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id_ibge, nome_ibge, match_status FROM tcesp_municipios
                       WHERE slug_tcesp = %s AND ativo""", (slug,))
        row = cur.fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        raise RuntimeError(
            f"Município '{slug}' não está no cadastro tcesp_municipios com id_ibge — "
            "rode a Fase 1 (agents A/B/C) antes. Regra: sem mapa IBGE, sem carga fiscal.")
    return row[0].strip(), row[1]


def bronze_mais_recente(tipo: str, slug: str, ano: int) -> Path:
    padrao = f"{tipo}_{slug}_{ano}_*_bronze.json"
    arqs = sorted(BRONZE_DIR.glob(padrao), key=lambda f: f.stat().st_mtime, reverse=True)
    if not arqs:
        raise FileNotFoundError(f"Nenhum Bronze {padrao} — rode agent_d_coletor_fiscal.py antes")
    return arqs[0]


def normalizar_tipo(tipo: str, slug: str, ano: int, id_ibge: str, nome_ibge: str):
    bronze_path = bronze_mais_recente(tipo, slug, ano)
    info(f"Bronze: {bronze_path.name}")
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    dt_extracao = bronze["meta"]["data_extracao"]
    prata, rejeitados = [], []

    for mes_str, registros in bronze["records_por_mes"].items():
        mes = int(mes_str)
        for rec in registros:
            nome_mes = (rec.get("mes") or "").strip().lower()
            if nome_mes and MESES_PT.get(nome_mes) not in (None, mes):
                rejeitados.append({**rec, "_mes_esperado": mes,
                                   "motivo_rejeicao": f"mês do payload ('{rec.get('mes')}') != mês da URL ({mes})"})
                continue

            if tipo == "receitas":
                valor = parse_brl(rec.get("vl_arrecadacao"))
                if valor is None:
                    rejeitados.append({**rec, "_mes_esperado": mes,
                                       "motivo_rejeicao": f"vl_arrecadacao ilegível: {rec.get('vl_arrecadacao')!r}"})
                    continue
                prata.append({
                    "slug_tcesp": slug, "id_ibge": id_ibge, "exercicio": ano, "mes": mes,
                    "orgao": rec.get("orgao"),
                    "fonte_recurso": rec.get("ds_fonte_recurso"),
                    "aplicacao": rec.get("ds_cd_aplicacao_fixo"),
                    "alinea": rec.get("ds_alinea"),
                    "subalinea": rec.get("ds_subalinea") or None,
                    "vl_arrecadacao": valor,
                    "dt_extracao": dt_extracao,
                })
            else:  # despesas
                valor = parse_brl(rec.get("vl_despesa"))
                if valor is None:
                    rejeitados.append({**rec, "_mes_esperado": mes,
                                       "motivo_rejeicao": f"vl_despesa ilegível: {rec.get('vl_despesa')!r}"})
                    continue
                forn_tipo, forn_doc = extrair_fornecedor(rec.get("id_fornecedor") or "")
                prata.append({
                    "slug_tcesp": slug, "id_ibge": id_ibge, "exercicio": ano, "mes": mes,
                    "orgao": rec.get("orgao"),
                    "evento": rec.get("evento"),
                    "nr_empenho": rec.get("nr_empenho"),
                    "fornecedor_tipo_doc": forn_tipo,
                    "fornecedor_doc": forn_doc,
                    "fornecedor_nome": rec.get("nm_fornecedor"),
                    "dt_emissao": parse_data_br(rec.get("dt_emissao_despesa")),
                    "vl_despesa": valor,
                    "dt_extracao": dt_extracao,
                })

    prata_file = PRATA_DIR / f"{tipo}_{slug}_{ano}_prata.json"
    with open(prata_file, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "bronze_origem": bronze_path.name,
                "tipo": tipo, "municipio_slug": slug, "id_ibge": id_ibge,
                "nome_ibge": nome_ibge, "exercicio": ano,
                "data_normalizacao": datetime.now(timezone.utc).isoformat(),
                "total_prata": len(prata),
                "rejeitados": len(rejeitados),
                "versao_agente": VERSAO,
            },
            "records": prata,
        }, f, ensure_ascii=False)

    if rejeitados:
        rej_file = REJEITADOS_DIR / f"{tipo}_{slug}_{ano}_rejeitados.json"
        with open(rej_file, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False, indent=2)
        warn(f"{tipo}: {len(rejeitados)} rejeitados → {rej_file.name}")

    campo_valor = "vl_arrecadacao" if tipo == "receitas" else "vl_despesa"
    total_valor = sum(r[campo_valor] for r in prata)
    ok(f"{tipo}: {len(prata)} registros válidos | soma {ano}: R$ {total_valor:,.2f}")
    return prata_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--municipio", required=True)
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--tipo", choices=["receitas", "despesas", "ambos"], default="ambos")
    args = parser.parse_args()

    tipos = ["receitas", "despesas"] if args.tipo == "ambos" else [args.tipo]
    print(f"\n{C_BOLD}AGENT-E {VERSAO} — NORMALIZADOR FISCAL "
          f"({args.municipio} {args.ano}, {'+'.join(tipos)}){C_END}")

    id_ibge, nome_ibge = resolver_municipio(args.municipio)
    info(f"Cadastro Fase 1: {args.municipio} → {nome_ibge} ({id_ibge})")

    for tipo in tipos:
        normalizar_tipo(tipo, args.municipio, args.ano, id_ibge, nome_ibge)

    print(f"\n{C_GREEN}{C_BOLD}[AGENT-E DONE] ✅{C_END}\n")


if __name__ == "__main__":
    main()
