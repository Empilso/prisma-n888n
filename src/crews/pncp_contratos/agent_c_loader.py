#!/usr/bin/env python3
"""Agent C — Loader PNCP: Prata JSON → PostgreSQL (prisma_data.contratos_pncp)

UPSERT por numero_controle_pncp. Preserva registros existentes sem deletar.
Atualiza status_lneg se cnpj_contratado bater com lista_negra_governo.

Execução:
    python agent_c_loader.py --todos
    python agent_c_loader.py --arquivo pncp_20250101_20250131.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timezone, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

PRATA_DIR = Path(__file__).parent / "data" / "pncp_contratos" / "prata"

COLS = [
    "id", "numero_controle_pncp", "numero_contrato", "ano_contrato",
    "cnpj_orgao", "nome_orgao", "esfera", "uf", "municipio_ibge", "municipio_nome",
    "cnpj_contratado", "nome_contratado", "objeto", "valor_global",
    "data_assinatura", "data_vigencia_inicio", "data_vigencia_fim",
    "modalidade", "categoria_processo", "tipo_contrato", "situacao",
    "orgao", "unidade_gestora", "processo", "link_pncp", "raw_hash", "status_lneg",
]

UPSERT_SQL = f"""
INSERT INTO contratos_pncp ({",".join(COLS)}, dt_carga)
VALUES ({",".join(["%s"] * len(COLS))}, NOW())
ON CONFLICT (numero_controle_pncp) WHERE numero_controle_pncp IS NOT NULL
DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in COLS if c not in ("id","raw_hash"))},
    dt_carga = NOW()
WHERE contratos_pncp.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
"""


def _get_db():
    pw = os.getenv("DB_PASSWORD")
    if not pw:
        raise RuntimeError("DB_PASSWORD não definido")
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "prisma_data"),
        user=os.getenv("DB_USER", "postgres"),
        password=pw,
    )


def _verificar_lneg(conn, cnpjs: list[str]) -> set[str]:
    if not cnpjs:
        return set()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT cnpj FROM lista_negra_governo WHERE cnpj = ANY(%s)",
        [cnpjs],
    )
    return {r[0] for r in cur.fetchall()}


def carregar_arquivo(prata_path: Path, conn) -> tuple[int, int]:
    data = json.loads(prata_path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not items:
        return 0, 0

    # cross-check lista negra
    cnpjs_contratados = list({i["cnpj_contratado"] for i in items if i.get("cnpj_contratado")})
    lneg_set = _verificar_lneg(conn, cnpjs_contratados)

    rows = []
    for item in items:
        if item.get("cnpj_contratado") in lneg_set:
            item["status_lneg"] = "MATCH"
        elif item.get("cnpj_contratado"):
            item["status_lneg"] = "OK"
        rows.append(tuple(item.get(c) for c in COLS))

    cur = conn.cursor()
    try:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, rows, page_size=500)
        conn.commit()
        return len(rows), 0
    except Exception as e:
        conn.rollback()
        print(f"[ERRO] {prata_path.name}: {e}", file=sys.stderr)
        return 0, len(rows)
    finally:
        cur.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--todos",   action="store_true")
    parser.add_argument("--arquivo", help="Nome do arquivo prata")
    args = parser.parse_args()

    if args.todos:
        files = sorted(PRATA_DIR.glob("pncp_*.json"))
    elif args.arquivo:
        files = [PRATA_DIR / args.arquivo]
    else:
        parser.error("Forneça --todos ou --arquivo")

    conn = _get_db()
    total_ok, total_err = 0, 0
    for f in files:
        ok, err = carregar_arquivo(f, conn)
        print(f"[{f.name}] {ok} upserts | {err} erros")
        total_ok += ok
        total_err += err

    conn.close()

    # ETL log
    try:
        log_conn = _get_db()
        log_conn.cursor().execute("""
            INSERT INTO etl_log (crew_id, tabela, registros_novos, registros_erro, dt_run, status)
            VALUES ('pncp_contratos', 'contratos_pncp', %s, %s, NOW(), %s)
        """, [total_ok, total_err, "OK" if total_err == 0 else "PARCIAL"])
        log_conn.commit()
        log_conn.close()
    except Exception:
        pass

    print(f"\n📊 Total: {total_ok:,} upserts | {total_err:,} erros")
    print("✅ Agent C concluído.")
