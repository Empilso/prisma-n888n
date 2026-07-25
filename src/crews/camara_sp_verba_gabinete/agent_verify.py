#!/usr/bin/env python3
"""Agent Verify — Quality Gate Câmara SP Verba de Gabinete

Checks:
  [1] Volume total (>= 5.000 registros — piloto, não é 12 anos de milhões)
  [2] Período (2015 até o ano atual)
  [3] Vereadores únicos (esperado 40–250, histórico multi-legislatura)
  [4] Valor total dentro de faixa plausível
  [5] Zero valores negativos ou zero
  [6] Cobertura politico_id (aviso, não crítico — nome de urna pode divergir)
  [7] Zero duplicatas de id
  [8] Categorias de despesa distintas (>= 5)
"""
import argparse
import psycopg2
import sys
from datetime import datetime, timezone
import os

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

    print(f"🔍 Quality Gate — Câmara SP Verba de Gabinete | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    checks = []

    def check(nome, ok, detalhe, critico=False):
        s = "✅" if ok else ("❌" if critico else "⚠️ ")
        checks.append({"ok": ok, "critico": critico})
        print(f"  {s} {nome}: {detalhe}")

    cur.execute("SELECT COUNT(*) FROM camara_sp_verba_gabinete")
    total = cur.fetchone()[0]
    check("[1] Volume total", total >= 5_000, f"{total:,} registros (mínimo 5.000)", critico=True)

    cur.execute("SELECT MIN(ano), MAX(ano) FROM camara_sp_verba_gabinete")
    ano_min, ano_max = cur.fetchone()
    check("[2] Período", (ano_min or 9999) <= 2016 and (ano_max or 0) >= 2024,
          f"{ano_min} → {ano_max}", critico=True)

    cur.execute("SELECT COUNT(DISTINCT vereador_nome) FROM camara_sp_verba_gabinete")
    vereadores = cur.fetchone()[0]
    check("[3] Vereadores únicos", 40 <= vereadores <= 250,
          f"{vereadores} (esperado 40–250 — histórico multi-legislatura)", critico=True)

    cur.execute("SELECT SUM(valor::numeric) FROM camara_sp_verba_gabinete")
    soma = float(cur.fetchone()[0] or 0)
    check("[4] Valor total", 5_000_000 <= soma <= 1_000_000_000, f"R$ {soma:,.0f}", critico=True)

    cur.execute("SELECT COUNT(*) FROM camara_sp_verba_gabinete WHERE valor::numeric <= 0")
    neg = cur.fetchone()[0]
    check("[5] Valores inválidos (<=0)", neg == 0, f"{neg} registros", critico=True)

    cur.execute("SELECT COUNT(*) FROM camara_sp_verba_gabinete WHERE politico_id IS NOT NULL")
    com_pid = cur.fetchone()[0]
    pct = com_pid / max(total, 1) * 100
    check("[6] Cobertura politico_id", pct >= 40, f"{com_pid:,} ({pct:.1f}%) vinculados")

    cur.execute("SELECT COUNT(*) - COUNT(DISTINCT id) FROM camara_sp_verba_gabinete")
    dupes = cur.fetchone()[0]
    check("[7] Duplicatas", dupes == 0, f"{dupes}", critico=True)

    cur.execute("SELECT COUNT(DISTINCT tipo_despesa) FROM camara_sp_verba_gabinete")
    cats = cur.fetchone()[0]
    check("[8] Categorias", cats >= 5, f"{cats} categorias distintas")

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
