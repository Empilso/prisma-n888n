#!/usr/bin/env python3
"""
💰 AGENT-D: COLETOR FISCAL TCE-SP — Receitas + Despesas mensais
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FONTE:  https://transparencia.tce.sp.gov.br/api/json/receitas/{slug}/{ano}/{mes}
        https://transparencia.tce.sp.gov.br/api/json/despesas/{slug}/{ano}/{mes}
OUTPUT: data/raw/tcesp/bronze/{tipo}_{slug}_{ano}_{YYYY-MM-DD}_bronze.json
FUNÇÃO: Coleta os 12 meses de um exercício para um município e salva
        Bronze imutável (payload por mês + SHA256 do conjunto).

USO:
    python agent_d_coletor_fiscal.py --municipio votorantim --ano 2025
    python agent_d_coletor_fiscal.py --municipio votorantim --ano 2025 --tipo receitas
"""

import argparse
import json
import hashlib
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

VERSAO = "v1.0"
BASE_URL = "https://transparencia.tce.sp.gov.br/api/json"
TIMEOUT = 120
TENTATIVAS = 3
PAUSA_ENTRE_MESES = 0.5  # cortesia com o portal

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/raw/tcesp/bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

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


def get_mes(tipo: str, slug: str, ano: int, mes: int):
    url = f"{BASE_URL}/{tipo}/{slug}/{ano}/{mes}"
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT,
                                headers={"User-Agent": "prisma-n888n-etl/1.0"})
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError(f"payload não é lista: {type(data)}")
            return data
        except Exception as e:
            ultimo_erro = e
            if tentativa < TENTATIVAS:
                time.sleep(2 ** tentativa)
    raise RuntimeError(f"{url} falhou após {TENTATIVAS} tentativas: {ultimo_erro}")


def coletar_tipo(tipo: str, slug: str, ano: int, meses: list[int], data_exec: str):
    bronze_file = BRONZE_DIR / f"{tipo}_{slug}_{ano}_{data_exec}_bronze.json"
    if bronze_file.exists():
        warn(f"Bronze já existe: {bronze_file.name} (pulando coleta de {tipo})")
        return bronze_file

    por_mes = {}
    total = 0
    for mes in meses:
        registros = get_mes(tipo, slug, ano, mes)
        por_mes[str(mes)] = registros
        total += len(registros)
        info(f"{tipo} {ano}/{mes:02d}: {len(registros)} registros")
        time.sleep(PAUSA_ENTRE_MESES)

    payload_str = json.dumps(por_mes, sort_keys=True, ensure_ascii=False)
    sha256 = hashlib.sha256(payload_str.encode()).hexdigest()

    with open(bronze_file, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "fonte": f"{BASE_URL}/{tipo}/{slug}/{ano}/{{mes}}",
                "portal": "TCE-SP — Transparência Municipal",
                "tipo": tipo,
                "municipio_slug": slug,
                "exercicio": ano,
                "meses_coletados": meses,
                "data_extracao": datetime.now(timezone.utc).isoformat(),
                "total_registros": total,
                "registros_por_mes": {m: len(v) for m, v in por_mes.items()},
                "sha256": sha256,
                "versao_agente": VERSAO,
            },
            "records_por_mes": por_mes,
        }, f, ensure_ascii=False)

    ok(f"{tipo}: {total} registros → {bronze_file.name} (sha256: {sha256[:8]}…)")
    return bronze_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--municipio", required=True, help="slug TCE-SP (ex: votorantim)")
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--tipo", choices=["receitas", "despesas", "ambos"], default="ambos")
    parser.add_argument("--meses", default="1-12", help="ex: 1-12 ou 1,2,3")
    args = parser.parse_args()

    if "-" in args.meses:
        ini, fim = args.meses.split("-")
        meses = list(range(int(ini), int(fim) + 1))
    else:
        meses = [int(m) for m in args.meses.split(",")]

    tipos = ["receitas", "despesas"] if args.tipo == "ambos" else [args.tipo]

    print(f"\n{C_BOLD}AGENT-D {VERSAO} — COLETOR FISCAL TCE-SP "
          f"({args.municipio} {args.ano}, {'+'.join(tipos)}){C_END}")
    inicio = datetime.now()
    data_exec = inicio.strftime("%Y-%m-%d")

    try:
        for tipo in tipos:
            coletar_tipo(tipo, args.municipio, args.ano, meses, data_exec)
        ok(f"Concluído em {(datetime.now() - inicio).total_seconds():.1f}s")
        print(f"\n{C_GREEN}{C_BOLD}[AGENT-D DONE] ✅{C_END}\n")
    except Exception as e:
        erro(f"Erro fatal: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
