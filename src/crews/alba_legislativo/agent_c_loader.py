#!/usr/bin/env python3
"""
ALBA Legislativo — Agent C (Loader)

Prata → PostgreSQL (alba_proposicoes, alba_comissoes). DDL embutido (idempotente).
Espelha o schema de alesp_proposicoes/comissoes pra o frontend reusar o molde.
Data de apresentação vem "dd/mm/aaaa hh:mm:ss" da API → date.
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "alba_legislativo"
PRATA = DATA_DIR / "prata"

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido")
DB = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
          dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
          password=DB_PASSWORD)

DDL = """
CREATE TABLE IF NOT EXISTS alba_proposicoes (
    id_proposicao     bigint NOT NULL,
    politico_id       text NOT NULL DEFAULT '',  -- '' = não atribuída (fica p/ auditoria)
    autor_id          integer,
    autor_nome        text,
    sigla             text,
    tipo              text,
    numero            text,
    ano               integer,
    assunto           text,
    situacao          text,
    data_apresentacao date,
    processo          text,
    url_arquivo       text,
    eh_coautor        boolean DEFAULT false,
    created_at        timestamptz DEFAULT now(),
    PRIMARY KEY (id_proposicao, politico_id)
);
CREATE INDEX IF NOT EXISTS idx_alba_prop_politico ON alba_proposicoes (politico_id);
CREATE INDEX IF NOT EXISTS idx_alba_prop_tipo_ano ON alba_proposicoes (sigla, ano DESC);

CREATE TABLE IF NOT EXISTS alba_comissoes (
    comissao_id       text NOT NULL,
    comissao_nome     text,
    comissao_sigla    text,
    parlamentar_id    text NOT NULL,
    parlamentar_nome  text,
    politico_id       text,
    cargo             text,
    created_at        timestamptz DEFAULT now(),
    PRIMARY KEY (comissao_id, parlamentar_id)
);
CREATE INDEX IF NOT EXISTS idx_alba_com_politico ON alba_comissoes (politico_id);
"""


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _data(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v).split(" ")[0], "%d/%m/%Y").date()
    except ValueError:
        return None


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recurso", choices=["proposicoes", "comissoes", "todos"], default="todos")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    log("DDL ok")

    if args.recurso in ("proposicoes", "todos"):
        props = json.loads((PRATA / "proposicoes.json").read_text(encoding="utf-8"))
        # dedup por (id_proposicao, politico_id) — PK usa COALESCE, então
        # normalizamos NULL→'' na chave de deduplicação em memória
        vistos, linhas = set(), []
        for p in props:
            pid = p.get("politico_id") or ""
            chave = (p["id_proposicao"], pid)
            if chave in vistos:
                continue
            vistos.add(chave)
            linhas.append((p["id_proposicao"], pid, _int(p.get("autor_id")),
                           p.get("autor_nome"), p.get("sigla"), p.get("tipo"), p.get("numero"),
                           _int(p.get("ano")), p.get("assunto"), p.get("situacao"),
                           _data(p.get("data_apresentacao")), p.get("processo"),
                           p.get("url_arquivo"), bool(p.get("eh_coautor"))))
        log(f"proposições: {len(linhas):,} linhas únicas")
        if not args.dry_run:
            cur.execute("TRUNCATE alba_proposicoes")
            psycopg2.extras.execute_values(cur, """
                INSERT INTO alba_proposicoes (id_proposicao, politico_id, autor_id, autor_nome,
                    sigla, tipo, numero, ano, assunto, situacao, data_apresentacao, processo,
                    url_arquivo, eh_coautor) VALUES %s
                ON CONFLICT (id_proposicao, politico_id) DO NOTHING
            """, linhas, page_size=1000)
            conn.commit()
            log(f"✅ alba_proposicoes carregada")

    if args.recurso in ("comissoes", "todos"):
        coms = json.loads((PRATA / "comissoes.json").read_text(encoding="utf-8"))
        vistos, linhas = set(), []
        for c in coms:
            chave = (c["comissao_id"], c["parlamentar_id"])
            if chave in vistos:
                continue
            vistos.add(chave)
            linhas.append((c["comissao_id"], c.get("comissao_nome"), c.get("comissao_sigla"),
                           c["parlamentar_id"], c.get("parlamentar_nome"), c.get("politico_id"),
                           c.get("cargo")))
        log(f"comissões: {len(linhas)} vínculos únicos")
        if not args.dry_run:
            cur.execute("TRUNCATE alba_comissoes")
            psycopg2.extras.execute_values(cur, """
                INSERT INTO alba_comissoes (comissao_id, comissao_nome, comissao_sigla,
                    parlamentar_id, parlamentar_nome, politico_id, cargo) VALUES %s
                ON CONFLICT (comissao_id, parlamentar_id) DO NOTHING
            """, linhas, page_size=1000)
            conn.commit()
            log(f"✅ alba_comissoes carregada")
    conn.close()


if __name__ == "__main__":
    main()
