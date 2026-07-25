#!/usr/bin/env python3
"""Agent A — Coletor Câmara SP Verba de Gabinete: Web Service → Bronze JSON

Portal: SisGV Consulta — Câmara Municipal de São Paulo
        https://sisgvconsulta.saopaulo.sp.leg.br/
Web Service (ASMX, aceita HTTP POST simples além de SOAP):
        POST /ws/Servicos.asmx/ObterDebitoVereadorJSON
        body: ano=<int>&mes=<int>
        → array de despesas item a item (fornecedor, CNPJ, valor, categoria)

Cobertura confirmada por teste real: 2015-01 tem dado, 2013-01 retorna [].
Não há endpoint "tudo de uma vez" — precisa iterar competência por
competência (diferente do ALESP, que publica um XML único).

Execução:
    python agent_a_coletor.py                      # 2015 até o mês atual
    python agent_a_coletor.py --ano-inicio 2024     # só a partir de um ano
    python agent_a_coletor.py --force               # re-baixa mesmo se já existe

Saída:
    data/camara_sp_verba_gabinete/bronze/camara_sp_verba_bronze.json
"""
import json
import hashlib
import argparse
import time
from pathlib import Path
from datetime import datetime, timezone

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data/camara_sp_verba_gabinete"
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://sisgvconsulta.saopaulo.sp.leg.br/ws/Servicos.asmx/ObterDebitoVereadorJSON"
BRONZE_PATH = BRONZE_DIR / "camara_sp_verba_bronze.json"

ANO_INICIO_PADRAO = 2015


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def buscar_competencia(ano: int, mes: int) -> list[dict]:
    resp = requests.post(
        BASE_URL,
        data={"ano": ano, "mes": mes},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def main():
    parser = argparse.ArgumentParser(description="Agent A — Coletor Câmara SP Verba de Gabinete")
    parser.add_argument("--ano-inicio", type=int, default=ANO_INICIO_PADRAO)
    parser.add_argument("--ano-fim", type=int, default=datetime.now().year)
    parser.add_argument("--force", action="store_true", help="Re-baixa mesmo se já existe")
    args = parser.parse_args()

    if BRONZE_PATH.exists() and not args.force:
        print(f"  ♻️  Bronze já existe: {BRONZE_PATH.name} (use --force para atualizar)")
        return

    hoje = datetime.now()
    rows: list[dict] = []
    competencias_vazias = 0
    competencias_com_erro = 0

    for ano in range(args.ano_inicio, args.ano_fim + 1):
        mes_max = hoje.month if ano == hoje.year else 12
        for mes in range(1, mes_max + 1):
            try:
                registros = buscar_competencia(ano, mes)
            except Exception as e:
                print(f"  ❌ {ano}-{mes:02d}: falhou ({e})")
                competencias_com_erro += 1
                continue
            if not registros:
                competencias_vazias += 1
                continue
            rows.extend(registros)
            print(f"  ✅ {ano}-{mes:02d}: {len(registros)} registro(s)")
            time.sleep(0.3)  # gentil com o servidor da fonte

    if not rows:
        print("  ❌ Nenhum registro coletado")
        return

    payload = json.dumps(rows, ensure_ascii=False)
    sha256 = hashlib.sha256(payload.encode()).hexdigest()
    bronze = {
        "meta": {
            "portal": "SisGV Consulta — Câmara Municipal de São Paulo",
            "entidade": "camara_sp_verba_gabinete",
            "camada": "bronze",
            "data_extracao": datetime.now(timezone.utc).isoformat(),
            "hash_sha256": sha256,
            "total_registros": len(rows),
            "url_fonte": BASE_URL,
            "periodo": f"{args.ano_inicio}-01 a {args.ano_fim}-{hoje.month:02d}",
            "competencias_vazias": competencias_vazias,
            "competencias_com_erro": competencias_com_erro,
        },
        "records": rows,
    }
    with open(BRONZE_PATH, "w", encoding="utf-8") as f:
        json.dump(bronze, f, ensure_ascii=False)

    print(f"\n  ✅ Bronze: {len(rows):>7,} registros → {BRONZE_PATH.name}")
    print(f"  ℹ️  Competências vazias: {competencias_vazias} | com erro: {competencias_com_erro}")
    print("\n✅ Agent A concluído.")


if __name__ == "__main__":
    main()
