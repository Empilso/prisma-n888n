#!/usr/bin/env python3
"""Agent C — Loader SICONFI Universal: Prata → PostgreSQL

Insere Prata em prisma_data.siconfi_rreo / siconfi_rgf / siconfi_dca via
INSERT ... ON CONFLICT (raw_hash) DO NOTHING — totalmente idempotente.

Cria as tabelas e índices se ainda não existirem (DDL no início).

Conexão (env vars):
    DB_HOST=localhost DB_PORT=5432 DB_NAME=prisma_data
    DB_USER=postgres DB_PASSWORD=...   (obrigatório)

Execução:
    python agent_c_loader.py --documento RREO --dry-run
    python agent_c_loader.py --documento RREO --prata <arquivo.json>
    python agent_c_loader.py --documento DCA  --todos
    python agent_c_loader.py --todos                 # carrega tudo que existir
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data" / "siconfi_universal" / "prata"

BATCH_SIZE = 500


def db_config() -> dict:
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "prisma_data"),
        user=os.getenv("DB_USER", "postgres"),
        password=DB_PASSWORD,
    )


# ── DDL ─────────────────────────────────────────────────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS siconfi_rreo (
    id BIGSERIAL PRIMARY KEY,
    id_ente TEXT NOT NULL,
    ente_tipo TEXT NOT NULL,
    ente_nome TEXT,
    uf TEXT NOT NULL,
    exercicio INT NOT NULL,
    periodo INT NOT NULL,
    anexo TEXT NOT NULL,
    conta TEXT NOT NULL,
    coluna TEXT,
    valor NUMERIC(20, 2),
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_siconfi_rreo_ente_ano ON siconfi_rreo(id_ente, exercicio, periodo);
CREATE INDEX IF NOT EXISTS idx_siconfi_rreo_uf ON siconfi_rreo(uf, exercicio);

CREATE TABLE IF NOT EXISTS siconfi_dca (
    id BIGSERIAL PRIMARY KEY,
    id_ente TEXT NOT NULL,
    ente_tipo TEXT NOT NULL,
    ente_nome TEXT,
    uf TEXT NOT NULL,
    exercicio INT NOT NULL,
    anexo TEXT NOT NULL,
    conta TEXT NOT NULL,
    coluna TEXT,
    valor NUMERIC(20, 2),
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_siconfi_dca_ente_ano ON siconfi_dca(id_ente, exercicio);
CREATE INDEX IF NOT EXISTS idx_siconfi_dca_uf ON siconfi_dca(uf, exercicio);

CREATE TABLE IF NOT EXISTS siconfi_rgf (
    id BIGSERIAL PRIMARY KEY,
    id_ente TEXT NOT NULL,
    ente_tipo TEXT NOT NULL,
    ente_nome TEXT,
    uf TEXT NOT NULL,
    exercicio INT NOT NULL,
    periodo INT NOT NULL,
    anexo TEXT NOT NULL,
    conta TEXT,
    coluna TEXT,
    valor NUMERIC(20, 2),
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_siconfi_rgf_ente_ano ON siconfi_rgf(id_ente, exercicio, periodo);
CREATE INDEX IF NOT EXISTS idx_siconfi_rgf_uf ON siconfi_rgf(uf, exercicio);
"""

# ── SQL por documento ────────────────────────────────────────────────────────
INSERT_RREO = """
INSERT INTO siconfi_rreo (
    id_ente, ente_tipo, ente_nome, uf,
    exercicio, periodo, anexo,
    conta, coluna, valor, raw_hash
) VALUES (
    %(id_ente)s, %(ente_tipo)s, %(ente_nome)s, %(uf)s,
    %(exercicio)s, %(periodo)s, %(anexo)s,
    %(conta)s, %(coluna)s, %(valor)s, %(raw_hash)s
)
ON CONFLICT (raw_hash) DO NOTHING
"""

INSERT_DCA = """
INSERT INTO siconfi_dca (
    id_ente, ente_tipo, ente_nome, uf,
    exercicio, anexo,
    conta, coluna, valor, raw_hash
) VALUES (
    %(id_ente)s, %(ente_tipo)s, %(ente_nome)s, %(uf)s,
    %(exercicio)s, %(anexo)s,
    %(conta)s, %(coluna)s, %(valor)s, %(raw_hash)s
)
ON CONFLICT (raw_hash) DO NOTHING
"""

INSERT_RGF = """
INSERT INTO siconfi_rgf (
    id_ente, ente_tipo, ente_nome, uf,
    exercicio, periodo, anexo,
    conta, coluna, valor, raw_hash
) VALUES (
    %(id_ente)s, %(ente_tipo)s, %(ente_nome)s, %(uf)s,
    %(exercicio)s, %(periodo)s, %(anexo)s,
    %(conta)s, %(coluna)s, %(valor)s, %(raw_hash)s
)
ON CONFLICT (raw_hash) DO NOTHING
"""

INSERT_SQL_BY_DOC = {
    "RREO": INSERT_RREO,
    "DCA":  INSERT_DCA,
    "RGF":  INSERT_RGF,
}

CAMPOS_RREO_RGF = [
    "id_ente", "ente_tipo", "ente_nome", "uf",
    "exercicio", "periodo", "anexo",
    "conta", "coluna", "valor", "raw_hash",
]
CAMPOS_DCA = [
    "id_ente", "ente_tipo", "ente_nome", "uf",
    "exercicio", "anexo",
    "conta", "coluna", "valor", "raw_hash",
]

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def garantir_schema(conn) -> None:
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    cur.close()


def documento_de_prata(meta: dict, hint: str | None) -> str:
    doc = (meta.get("documento") or "").upper()
    if doc in ("RREO", "RGF", "DCA"):
        return doc
    if hint and hint.upper() in ("RREO", "RGF", "DCA"):
        return hint.upper()
    anexo = (meta.get("anexo") or "").upper()
    if anexo.startswith("RREO"): return "RREO"
    if anexo.startswith("RGF"):  return "RGF"
    if anexo.startswith("DCA"):  return "DCA"
    return "RREO"


def carregar_prata(prata_path: Path, dry_run: bool,
                   documento_hint: str | None,
                   conn=None) -> tuple[str, int, int]:
    """Retorna (documento, n_novos, n_erros)."""
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    meta = prata.get("meta", {})
    records = prata.get("records", [])
    documento = documento_de_prata(meta, documento_hint)

    if dry_run:
        # Valida campos
        campos = CAMPOS_DCA if documento == "DCA" else CAMPOS_RREO_RGF
        erros = 0
        for r in records[:50]:
            for c in ("id_ente", "uf", "exercicio", "anexo", "conta", "raw_hash"):
                if not r.get(c) and r.get(c) != 0:
                    erros += 1
                    break
        print(f"  🔍 DRY-RUN {documento} | {prata_path.name}: {len(records):,} regs | val_amostra_erros={erros}")
        return documento, 0, 0

    assert conn is not None
    sql = INSERT_SQL_BY_DOC[documento]
    campos = CAMPOS_DCA if documento == "DCA" else CAMPOS_RREO_RGF

    rows = []
    for r in records:
        row = {k: r.get(k) for k in campos}
        # periodo é NOT NULL em RREO/RGF — força 0 se ausente
        if documento in ("RREO", "RGF") and row.get("periodo") is None:
            row["periodo"] = 0
        rows.append(row)

    cur = conn.cursor()
    novos = erros = 0
    for i in range(0, len(rows), BATCH_SIZE):
        lote = rows[i:i+BATCH_SIZE]
        try:
            cur.executemany(sql, lote)
            conn.commit()
            novos += len(lote)
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//BATCH_SIZE + 1} ({prata_path.name}): {e}")
    cur.close()
    return documento, novos, erros


def iterar_pratas(documento: str | None) -> list[Path]:
    if documento:
        base = PRATA_DIR / documento.lower()
        if not base.exists():
            return []
        return sorted(base.rglob("*_prata.json"))
    return sorted(PRATA_DIR.rglob("*_prata.json"))


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader SICONFI Universal")
    parser.add_argument("--documento", choices=["RREO", "RGF", "DCA"], default=None)
    parser.add_argument("--prata", help="Arquivo prata específico")
    parser.add_argument("--todos", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Seleciona pratas
    if args.prata:
        pratas = [Path(args.prata)]
    elif args.todos:
        pratas = iterar_pratas(args.documento)
    else:
        pratas = iterar_pratas(args.documento)
        if pratas:
            pratas = sorted(pratas, key=lambda p: p.stat().st_mtime, reverse=True)[:1]

    if not pratas:
        print("❌ Nenhum Prata encontrado.")
        return

    print(f"📂 {len(pratas):,} prata(s) a carregar")

    conn = None
    if not args.dry_run:
        try:
            conn = psycopg2.connect(**db_config())
        except Exception as e:
            print(f"❌ Falha ao conectar PostgreSQL: {e}")
            sys.exit(1)
        garantir_schema(conn)

    inicio = datetime.now(timezone.utc)
    stats_por_doc: dict[str, dict] = {}

    for p in pratas:
        try:
            doc, novos, erros = carregar_prata(p, args.dry_run, args.documento, conn)
        except Exception as e:
            print(f"  ❌ Falha total em {p.name}: {e}")
            continue
        s = stats_por_doc.setdefault(doc, {"arquivos": 0, "novos": 0, "erros": 0})
        s["arquivos"] += 1
        s["novos"]    += novos
        s["erros"]    += erros

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    if conn:
        try:
            cur = conn.cursor()
            for doc, s in stats_por_doc.items():
                cur.execute(ETL_LOG, (
                    f"siconfi_{doc.lower()}",
                    "fase_2",
                    "sucesso" if s["erros"] == 0 else "parcial",
                    s["arquivos"], s["novos"],
                    None if s["erros"] == 0 else f"{s['erros']} erros",
                    round(dur, 2), inicio, fim,
                ))
            conn.commit()
            cur.close()
        except Exception as e:
            print(f"⚠️  Falha ao registrar etl_log: {e}")
        finally:
            conn.close()

    print("\n📊 Resumo por documento:")
    for doc, s in stats_por_doc.items():
        print(f"  {doc}: arquivos={s['arquivos']:,} | novos={s['novos']:,} | erros={s['erros']:,}")
    print(f"\n✅ Agent C concluído em {dur:.1f}s")


if __name__ == "__main__":
    main()
