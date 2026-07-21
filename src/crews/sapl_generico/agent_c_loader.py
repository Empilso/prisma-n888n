#!/usr/bin/env python3
"""SAPL Genérico — Agent C (Loader)

Prata → PostgreSQL. Tabelas novas (DDL idempotente, `CREATE TABLE IF NOT
EXISTS` — nunca TRUNCATE, carga é sempre incremental por UPSERT):

  sapl_parlamentares — cadastro do vereador na câmara + politico_id resolvido
                       (chave única: dominio + id_sapl)
  sapl_materias      — projetos de lei e afins + autores (chave única:
                       dominio + id_sapl)

Re-rodar a crew nunca duplica linha (`ON CONFLICT ... DO UPDATE`) e nunca
piora um match já resolvido: `politico_id` só é sobrescrito se o novo valor
não for nulo (mesmo espírito COALESCE-safe usado em cgu_emendas_federais).
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

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "prisma_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/sapl_generico/prata"

DDL = """
CREATE TABLE IF NOT EXISTS sapl_parlamentares (
    id                    bigserial PRIMARY KEY,
    dominio               text NOT NULL,
    id_sapl               integer NOT NULL,
    municipio_ibge        char(7) REFERENCES municipios(id_ibge),
    nome_completo         text,
    nome_parlamentar      text,
    ativo                 boolean,
    email                 text,
    legislatura           integer,
    data_inicio_mandato   date,
    data_fim_mandato      date,
    partido_sigla         text,
    politico_id           text,
    match_metodo          text,
    atualizado_em         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dominio, id_sapl)
);
CREATE INDEX IF NOT EXISTS idx_sapl_parlamentares_politico ON sapl_parlamentares (politico_id);
CREATE INDEX IF NOT EXISTS idx_sapl_parlamentares_municipio ON sapl_parlamentares (municipio_ibge);

CREATE TABLE IF NOT EXISTS sapl_materias (
    id                  bigserial PRIMARY KEY,
    dominio             text NOT NULL,
    id_sapl             integer NOT NULL,
    municipio_ibge      char(7) REFERENCES municipios(id_ibge),
    numero              integer,
    ano                 integer,
    tipo                integer,
    ementa              text,
    data_apresentacao   date,
    em_tramitacao       boolean,
    autores_id_sapl     integer[],
    autores_politico_id text[],
    atualizado_em       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dominio, id_sapl)
);
CREATE INDEX IF NOT EXISTS idx_sapl_materias_municipio ON sapl_materias (municipio_ibge);
CREATE INDEX IF NOT EXISTS idx_sapl_materias_autores ON sapl_materias USING gin (autores_politico_id);
"""


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _data(v):
    return v or None


def carregar_parlamentares(cur, rows: list[dict]) -> None:
    linhas = [(
        r["dominio"], r["id_sapl"], r["municipio_ibge"], r["nome_completo"], r["nome_parlamentar"],
        r["ativo"], r["email"], r["legislatura"], _data(r["data_inicio_mandato"]), _data(r["data_fim_mandato"]),
        r["partido_sigla"], r["politico_id"], r["match_metodo"],
    ) for r in rows]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO sapl_parlamentares (
            dominio, id_sapl, municipio_ibge, nome_completo, nome_parlamentar,
            ativo, email, legislatura, data_inicio_mandato, data_fim_mandato,
            partido_sigla, politico_id, match_metodo
        ) VALUES %s
        ON CONFLICT (dominio, id_sapl) DO UPDATE SET
            municipio_ibge = EXCLUDED.municipio_ibge,
            nome_completo = EXCLUDED.nome_completo,
            nome_parlamentar = EXCLUDED.nome_parlamentar,
            ativo = EXCLUDED.ativo,
            email = EXCLUDED.email,
            legislatura = EXCLUDED.legislatura,
            data_inicio_mandato = EXCLUDED.data_inicio_mandato,
            data_fim_mandato = EXCLUDED.data_fim_mandato,
            partido_sigla = EXCLUDED.partido_sigla,
            politico_id = COALESCE(EXCLUDED.politico_id, sapl_parlamentares.politico_id),
            match_metodo = CASE WHEN EXCLUDED.politico_id IS NOT NULL THEN EXCLUDED.match_metodo
                                ELSE sapl_parlamentares.match_metodo END,
            atualizado_em = now()
    """, linhas, page_size=500)


def carregar_materias(cur, rows: list[dict]) -> None:
    linhas = [(
        r["dominio"], r["id_sapl"], r["municipio_ibge"], r["numero"], r["ano"], r["tipo"],
        r["ementa"], _data(r["data_apresentacao"]), r["em_tramitacao"],
        r["autores_id_sapl"] or [], r["autores_politico_id"] or [],
    ) for r in rows]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO sapl_materias (
            dominio, id_sapl, municipio_ibge, numero, ano, tipo,
            ementa, data_apresentacao, em_tramitacao, autores_id_sapl, autores_politico_id
        ) VALUES %s
        ON CONFLICT (dominio, id_sapl) DO UPDATE SET
            numero = EXCLUDED.numero, ano = EXCLUDED.ano, tipo = EXCLUDED.tipo,
            ementa = EXCLUDED.ementa, data_apresentacao = EXCLUDED.data_apresentacao,
            em_tramitacao = EXCLUDED.em_tramitacao,
            autores_id_sapl = EXCLUDED.autores_id_sapl,
            autores_politico_id = EXCLUDED.autores_politico_id,
            atualizado_em = now()
    """, linhas, page_size=1000)


def main() -> None:
    ap = argparse.ArgumentParser(description="SAPL Genérico — Agent C (Loader)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    log("DDL ok (sapl_parlamentares + sapl_materias)")

    arquivos = sorted(PRATA_DIR.glob("*.json"))
    total_parlamentares = total_materias = 0
    for arq in arquivos:
        prata = json.loads(arq.read_text(encoding="utf-8"))
        total_parlamentares += len(prata["parlamentares"])
        total_materias += len(prata["materias"])
        if args.dry_run:
            continue
        carregar_parlamentares(cur, prata["parlamentares"])
        carregar_materias(cur, prata["materias"])
        conn.commit()

    log(f"{len(arquivos)} domínio(s) prata | {total_parlamentares:,} parlamentares | {total_materias:,} matérias")
    if args.dry_run:
        log("dry-run — nada gravado")
        conn.close()
        return

    cur.execute("SELECT count(*) FROM sapl_parlamentares")
    n_parl = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM sapl_materias")
    n_mat = cur.fetchone()[0]
    log(f"✅ banco: {n_parl:,} linhas em sapl_parlamentares | {n_mat:,} linhas em sapl_materias")
    conn.close()


if __name__ == "__main__":
    main()
