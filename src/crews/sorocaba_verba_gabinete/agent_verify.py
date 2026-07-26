#!/usr/bin/env python3
"""Agent Verify — Quality Gate Sorocaba Verba de Gabinete

Checks (limiares provisórios — calibrados por estimativa a partir da
amostra real de março/2025 e do sample de janeiro/2016, ambos inspecionados
manualmente antes de escrever este crew; recalibrar após a 1ª carga real se
o volume observado divergir muito do esperado):
  [1] Volume total (>= 2.000 registros — ~130 competências × ~25 vereadores
      × categorias parcialmente preenchidas)
  [2] Período (2016 até o ano atual)
  [3] Vereadores únicos (esperado 15–60, histórico multi-legislatura)
  [4] Valor total dentro de faixa plausível (R$500k–R$50M)
  [5] Zero valores <= 0 (célula vazia/"-" nunca devia ter virado linha)
  [6] Cobertura politico_id (aviso, não crítico)
  [7] Zero duplicatas de id
  [8] Exatamente 4 categorias (só as 4 de escopo do v1 — se aparecer uma
      5ª, é bug de mapeamento de coluna, não dado novo legítimo)
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

DB = dict(host="localhost", port=5432, dbname="prisma_data", user="postgres", password=DB_PASSWORD)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    print(f"🔍 Quality Gate — Sorocaba Verba de Gabinete | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    checks = []

    def check(nome, ok, detalhe, critico=False):
        s = "✅" if ok else ("❌" if critico else "⚠️ ")
        checks.append({"ok": ok, "critico": critico})
        print(f"  {s} {nome}: {detalhe}")

    cur.execute("SELECT COUNT(*) FROM sorocaba_verba_gabinete")
    total = cur.fetchone()[0]
    check("[1] Volume total", total >= 2_000, f"{total:,} registros (mínimo 2.000)", critico=True)

    cur.execute("SELECT MIN(ano), MAX(ano) FROM sorocaba_verba_gabinete")
    ano_min, ano_max = cur.fetchone()
    check("[2] Período", (ano_min or 9999) <= 2017 and (ano_max or 0) >= 2024,
          f"{ano_min} → {ano_max}", critico=True)

    cur.execute("SELECT COUNT(DISTINCT vereador_nome) FROM sorocaba_verba_gabinete")
    vereadores = cur.fetchone()[0]
    check("[3] Vereadores únicos", 15 <= vereadores <= 60,
          f"{vereadores} (esperado 15–60 — histórico multi-legislatura)", critico=True)

    cur.execute("SELECT SUM(valor::numeric) FROM sorocaba_verba_gabinete")
    soma = float(cur.fetchone()[0] or 0)
    check("[4] Valor total", 500_000 <= soma <= 50_000_000, f"R$ {soma:,.0f}", critico=True)

    cur.execute("SELECT COUNT(*) FROM sorocaba_verba_gabinete WHERE valor::numeric <= 0")
    neg = cur.fetchone()[0]
    check("[5] Valores inválidos (<=0)", neg == 0, f"{neg} registros", critico=True)

    cur.execute("SELECT COUNT(*) FROM sorocaba_verba_gabinete WHERE politico_id IS NOT NULL")
    com_pid = cur.fetchone()[0]
    pct = com_pid / max(total, 1) * 100
    check("[6] Cobertura politico_id", pct >= 40, f"{com_pid:,} ({pct:.1f}%) vinculados")

    cur.execute("SELECT COUNT(*) - COUNT(DISTINCT id) FROM sorocaba_verba_gabinete")
    dupes = cur.fetchone()[0]
    check("[7] Duplicatas", dupes == 0, f"{dupes}", critico=True)

    cur.execute("SELECT COUNT(DISTINCT categoria) FROM sorocaba_verba_gabinete")
    cats = cur.fetchone()[0]
    check("[8] Categorias", cats == 4, f"{cats} categorias distintas (esperado exatamente 4)")

    cur.close()
    conn.close()

    falhas = sum(1 for c in checks if not c["ok"] and c.get("critico"))
    avisos = sum(1 for c in checks if not c["ok"] and not c.get("critico"))
    print("=" * 60)
    if falhas == 0:
        print(f"  ✅ QUALITY GATE PASSOU" + (f" ({avisos} aviso(s))" if avisos else ""))
    else:
        print(f"  ❌ QUALITY GATE FALHOU — {falhas} check(s) crítico(s)")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
