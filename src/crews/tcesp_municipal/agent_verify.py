#!/usr/bin/env python3
"""
🔍 AGENT-VERIFY — Reconciliação fiscal TCE-SP × CSV manual × SICONFI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Compara, mês a mês e no total do exercício:
  1. tcesp_receitas / tcesp_despesas (carregado da API pela crew)
  2. CSV manual exportado do TCE-SP (--csv-receitas), se fornecido
  3. SICONFI RREO local (siconfi_rreo), se o ente existir

NÃO altera nada. Saída é relatório. A regra do projeto: número só vai
pro Radar depois de saber QUAL conceito contábil ele representa.

USO:
    python agent_verify.py --municipio votorantim --ano 2025 \
        --csv-receitas /caminho/receitas-votorantim-2025.csv
"""

import argparse
import csv
import os
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido")

DB_CONFIG = {"host": "localhost", "port": 5432, "dbname": "prisma_data",
             "user": "postgres", "password": DB_PASSWORD}

C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BOLD = "\033[1m"
C_END = "\033[0m"


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_brl_csv(s):
    s = (s or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def somar_csv_receitas(path: Path):
    """CSV oficial TCE-SP: ; como separador, decimal vírgula, latin-1."""
    por_mes = {}
    ilegiveis = 0
    with open(path, encoding="latin-1") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            v = parse_brl_csv(row.get("vl_arrecadacao"))
            if v is None:
                ilegiveis += 1
                continue
            mes = int(row["mes_referencia"])
            por_mes[mes] = por_mes.get(mes, 0.0) + v
    return por_mes, ilegiveis


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--municipio", required=True)
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--csv-receitas", type=Path, default=None)
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT id_ibge, nome_ibge FROM tcesp_municipios WHERE slug_tcesp=%s",
                (args.municipio,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"❌ {args.municipio} não está em tcesp_municipios")
    id_ibge, nome = row[0].strip(), row[1]

    print(f"\n{C_BOLD}═══ RECONCILIAÇÃO FISCAL — {nome} ({id_ibge}) — {args.ano} ═══{C_END}")

    # ── 1. Receitas API (banco) ──────────────────────────────────────────────
    cur.execute("""SELECT mes, sum(vl_arrecadacao) FROM tcesp_receitas
                   WHERE slug_tcesp=%s AND exercicio=%s GROUP BY mes ORDER BY mes""",
                (args.municipio, args.ano))
    api_rec = dict(cur.fetchall())
    total_api = float(sum(api_rec.values()))

    # ── 2. CSV manual (se fornecido) ─────────────────────────────────────────
    csv_rec, csv_total, ilegiveis = {}, None, 0
    if args.csv_receitas and args.csv_receitas.exists():
        csv_rec, ilegiveis = somar_csv_receitas(args.csv_receitas)
        csv_total = sum(csv_rec.values())

    print(f"\n{C_CYAN}── RECEITAS: API TCE-SP × CSV manual ──{C_END}")
    print(f"{'mês':>4} | {'API (tcesp_receitas)':>22} | {'CSV manual':>22} | {'diferença':>15}")
    for mes in sorted(set(api_rec) | set(csv_rec)):
        a = float(api_rec.get(mes, 0))
        c = csv_rec.get(mes)
        diff = "" if c is None else brl(a - c)
        print(f"{mes:>4} | {brl(a):>22} | {(brl(c) if c is not None else '—'):>22} | {diff:>15}")
    print(f"{'ANO':>4} | {brl(total_api):>22} | "
          f"{(brl(csv_total) if csv_total is not None else '—'):>22} | "
          f"{(brl(total_api - csv_total) if csv_total is not None else ''):>15}")
    if ilegiveis:
        print(f"{C_YELLOW}⚠️  CSV: {ilegiveis} linhas com valor ilegível (não somadas){C_END}")

    if csv_total is not None:
        delta_pct = abs(total_api - csv_total) / csv_total * 100 if csv_total else 0
        cor = C_GREEN if delta_pct < 0.01 else C_YELLOW
        print(f"{cor}Δ anual API×CSV: {brl(total_api - csv_total)} ({delta_pct:.4f}%){C_END}")

    # ── 3. Despesas API por evento ───────────────────────────────────────────
    cur.execute("""SELECT evento, count(*), sum(vl_despesa) FROM tcesp_despesas
                   WHERE slug_tcesp=%s AND exercicio=%s GROUP BY evento ORDER BY 3 DESC""",
                (args.municipio, args.ano))
    rows = cur.fetchall()
    print(f"\n{C_CYAN}── DESPESAS: API TCE-SP por evento (conceitos distintos — NÃO somar entre si) ──{C_END}")
    for evento, n, total in rows:
        print(f"  {evento or '—':<12}: {n:>7} docs  {brl(float(total)):>22}")

    # ── 4. SICONFI local ─────────────────────────────────────────────────────
    cur.execute("""SELECT count(*) FROM siconfi_rreo WHERE id_ente=%s AND exercicio=%s""",
                (id_ibge, args.ano))
    n_siconfi = cur.fetchone()[0]
    print(f"\n{C_CYAN}── SICONFI RREO local ──{C_END}")
    if n_siconfi:
        cur.execute("""SELECT anexo, conta, coluna, valor FROM siconfi_rreo
                       WHERE id_ente=%s AND exercicio=%s
                         AND conta ILIKE '%%RECEITAS%%(III)%%' LIMIT 5""",
                    (id_ibge, args.ano))
        for r in cur.fetchall():
            print(f"  {r[0]} | {r[1][:60]} | {r[2]} | {brl(float(r[3] or 0))}")
    else:
        print(f"  {C_YELLOW}Sem registros de {nome} ({id_ibge}) em siconfi_rreo {args.ano} — "
              f"coleta SICONFI deste ente ainda não rodou (cobertura atual: capitais + UFs).{C_END}")

    conn.close()
    print(f"\n{C_BOLD}Conceitos: receita CSV/API = arrecadação bruta mensal; "
          f"despesa por evento: Empenhado ≠ Liquidado ≠ Pago.{C_END}\n")


if __name__ == "__main__":
    main()
