#!/usr/bin/env python3
"""Agent P — publica somente lotes aprovados e assinados pelo Agent V."""
import argparse
import hashlib
import json
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

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/tse_despesas_campanha/prata"
REPORT_DIR = BASE_DIR / "data/tse_despesas_campanha/verificacoes"
DB = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "5432")),
          dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
          password=DB_PASSWORD)


def sha256(arquivo: Path) -> str:
    digest = hashlib.sha256()
    with arquivo.open("rb") as entrada:
        while chunk := entrada.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def publicar(relatorio_path: Path) -> None:
    relatorio = json.loads(relatorio_path.read_text(encoding="utf-8"))
    if relatorio.get("status") != "APROVADO" or not relatorio.get("todos_gates_passaram"):
        raise RuntimeError(f"Relatório não aprovado: {relatorio_path}")
    prata = PRATA_DIR / relatorio["arquivo_prata"]
    if not prata.exists() or sha256(prata) != relatorio.get("sha256_prata"):
        raise RuntimeError(f"Hash da Prata diverge do relatório: {prata}")

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("""
        UPDATE despesas_campanha
        SET verificacao_status = 'APROVADO', verificado_em = now(), updated_at = now()
        WHERE ano_eleicao = %s AND uf = %s AND origem_arquivo = %s
          AND verificacao_status IS DISTINCT FROM 'APROVADO'
    """, (relatorio["ano_eleicao"], relatorio["uf"], relatorio["arquivo_bronze"]))
    alterados = cur.rowcount
    cur.execute("""
        SELECT count(*), COALESCE(sum(valor), 0),
               count(*) FILTER (WHERE verificacao_status = 'APROVADO')
        FROM despesas_campanha
        WHERE ano_eleicao = %s AND uf = %s AND origem_arquivo = %s
    """, (relatorio["ano_eleicao"], relatorio["uf"], relatorio["arquivo_bronze"]))
    total_db, soma_db, aprovados_db = cur.fetchone()
    total_esperado = int(relatorio["total_registros"])
    soma_esperada = str(relatorio["soma_valores"])
    if total_db != total_esperado or aprovados_db != total_esperado or str(soma_db) != soma_esperada:
        conn.rollback()
        raise RuntimeError(
            f"Publicação abortada: DB={total_db}/{soma_db}/{aprovados_db} · "
            f"relatório={total_esperado}/{soma_esperada}"
        )
    conn.commit(); cur.close(); conn.close()
    print(
        f"✅ PUBLICADO {relatorio['ano_eleicao']}/{relatorio['uf']}: "
        f"{total_db:,} registros ({alterados:,} alterados nesta execução)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Publicador de lotes verificados")
    parser.add_argument("--relatorio")
    parser.add_argument("--todos", action="store_true")
    args = parser.parse_args()
    relatorios = [Path(args.relatorio)] if args.relatorio else sorted(REPORT_DIR.glob("despesas_*_verificado.json"))
    if not relatorios:
        raise SystemExit("Nenhum relatório do Agent V encontrado")
    for relatorio in relatorios:
        publicar(relatorio)


if __name__ == "__main__":
    main()
