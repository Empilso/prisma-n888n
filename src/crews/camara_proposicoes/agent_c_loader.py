#!/usr/bin/env python3
"""Agent C — Loader Câmara Proposições: Prata → tabela camara_proposicoes

Idempotência: ON CONFLICT (id) DO UPDATE — re-execução segura.

Schema-evolução:
    O banco prisma_data já possui uma tabela `camara_proposicoes` legada com schema
    mínimo (id, politico_id, camara_id, tipo, numero, ano, ementa, descricao,
    dt_apresentacao, url_inteiro_teor, status_atual, tema; PK (id, politico_id)).
    Este Loader detecta esse cenário, faz ALTER TABLE ADD COLUMN IF NOT EXISTS
    para as colunas novas e cria uma tabela "wide" complementar
    `camara_proposicoes_wide` com PK = id (não por autor), que é o destino canônico.

    Para manter compat com consumidores antigos da tabela legada, populamos AMBAS:
      - `camara_proposicoes_wide` (1 linha por proposição, com autores em JSONB)
      - `camara_proposicoes` legada (1 linha por (proposicao, autor) — explode autores).

    Em banco limpo (sem tabela legada), cria só a wide com nome `camara_proposicoes`.

Cruzamento autor → politico_id PRISMA:
    A tabela `politicos` não tem `id_legislativo_camara`. Estratégia:
      1. Match exato (nome_urna, uf, sigla_partido).
      2. Fallback fuzzy via pg_trgm: similarity(nome_completo, autor.nome) ≥ 0.85
         filtrado por UF do autor.
    Os IDs resolvidos vão para o array `autores_politico_ids` e dentro de
    `autores` (chave `politico_id_prisma` por autor).

Execução:
    python agent_c_loader.py --dry-run            # valida + simula resolução de autores
    python agent_c_loader.py --prata proposicoes_57_prata.json
    python agent_c_loader.py --todos              # carrega todos os pratas disponíveis
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/camara_proposicoes/prata"


def db_config() -> dict:
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "prisma_data"),
        user=os.getenv("DB_USER", "postgres"),
        password=DB_PASSWORD,
    )


DDL_WIDE = """
CREATE TABLE IF NOT EXISTS camara_proposicoes_wide (
    id                          BIGINT PRIMARY KEY,
    tipo                        TEXT NOT NULL,
    numero                      INTEGER NOT NULL,
    ano                         INTEGER NOT NULL,
    ementa                      TEXT,
    ementa_detalhada            TEXT,
    data_apresentacao           DATE,
    status_situacao             TEXT,
    status_descricao_tramitacao TEXT,
    status_data                 TIMESTAMPTZ,
    uri_orgao_atual             TEXT,
    sigla_orgao_atual           TEXT,
    keywords                    TEXT[],
    autores                     JSONB,
    autores_politico_ids        TEXT[],
    raw_hash                    TEXT UNIQUE,
    dt_carga                    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cprop_wide_ano        ON camara_proposicoes_wide(ano);
CREATE INDEX IF NOT EXISTS idx_cprop_wide_tipo       ON camara_proposicoes_wide(tipo);
CREATE INDEX IF NOT EXISTS idx_cprop_wide_autores_pol
    ON camara_proposicoes_wide USING gin(autores_politico_ids);
CREATE INDEX IF NOT EXISTS idx_cprop_wide_keywords
    ON camara_proposicoes_wide USING gin(keywords);
"""

DDL_LEGADO_PATCH = """
-- Acrescenta colunas faltantes à camara_proposicoes legada (idempotente)
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS ementa_detalhada            TEXT;
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS status_situacao             TEXT;
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS status_descricao_tramitacao TEXT;
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS status_data                 TIMESTAMPTZ;
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS uri_orgao_atual             TEXT;
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS sigla_orgao_atual           TEXT;
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS keywords                    TEXT[];
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS raw_hash                    TEXT;
ALTER TABLE camara_proposicoes ADD COLUMN IF NOT EXISTS dt_carga                    TIMESTAMPTZ DEFAULT now();
"""

UPSERT_WIDE = """
INSERT INTO camara_proposicoes_wide (
    id, tipo, numero, ano, ementa, ementa_detalhada,
    data_apresentacao, status_situacao, status_descricao_tramitacao, status_data,
    uri_orgao_atual, sigla_orgao_atual, keywords, autores, autores_politico_ids,
    raw_hash
) VALUES (
    %(id)s, %(tipo)s, %(numero)s, %(ano)s, %(ementa)s, %(ementa_detalhada)s,
    %(data_apresentacao)s, %(status_situacao)s, %(status_descricao_tramitacao)s, %(status_data)s,
    %(uri_orgao_atual)s, %(sigla_orgao_atual)s, %(keywords)s, %(autores)s, %(autores_politico_ids)s,
    %(raw_hash)s
)
ON CONFLICT (id) DO UPDATE SET
    ementa                       = EXCLUDED.ementa,
    ementa_detalhada             = EXCLUDED.ementa_detalhada,
    status_situacao              = EXCLUDED.status_situacao,
    status_descricao_tramitacao  = EXCLUDED.status_descricao_tramitacao,
    status_data                  = EXCLUDED.status_data,
    uri_orgao_atual              = EXCLUDED.uri_orgao_atual,
    sigla_orgao_atual            = EXCLUDED.sigla_orgao_atual,
    keywords                     = EXCLUDED.keywords,
    autores                      = EXCLUDED.autores,
    autores_politico_ids         = EXCLUDED.autores_politico_ids,
    raw_hash                     = EXCLUDED.raw_hash,
    dt_carga                     = now()
"""

# Tabela legada — uma linha por (proposicao, autor). PK (id, politico_id).
UPSERT_LEGADO = """
INSERT INTO camara_proposicoes (
    id, politico_id, camara_id, tipo, numero, ano, ementa, descricao,
    dt_apresentacao, status_atual,
    ementa_detalhada, status_situacao, status_descricao_tramitacao, status_data,
    uri_orgao_atual, sigla_orgao_atual, keywords, raw_hash
) VALUES (
    %(id)s, %(politico_id)s, %(camara_id)s, %(tipo)s, %(numero)s, %(ano)s, %(ementa)s, %(descricao)s,
    %(dt_apresentacao)s, %(status_atual)s,
    %(ementa_detalhada)s, %(status_situacao)s, %(status_descricao_tramitacao)s, %(status_data)s,
    %(uri_orgao_atual)s, %(sigla_orgao_atual)s, %(keywords)s, %(raw_hash)s
)
ON CONFLICT (id, politico_id) DO UPDATE SET
    ementa                       = EXCLUDED.ementa,
    descricao                    = EXCLUDED.descricao,
    status_atual                 = EXCLUDED.status_atual,
    ementa_detalhada             = EXCLUDED.ementa_detalhada,
    status_situacao              = EXCLUDED.status_situacao,
    status_descricao_tramitacao  = EXCLUDED.status_descricao_tramitacao,
    status_data                  = EXCLUDED.status_data,
    uri_orgao_atual              = EXCLUDED.uri_orgao_atual,
    sigla_orgao_atual            = EXCLUDED.sigla_orgao_atual,
    keywords                     = EXCLUDED.keywords,
    raw_hash                     = EXCLUDED.raw_hash,
    dt_carga                     = now()
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def tabela_legada_existe(cur) -> bool:
    cur.execute("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema='public' AND table_name='camara_proposicoes'
        )
    """)
    return cur.fetchone()[0]


def garantir_schema(cur) -> None:
    cur.execute(DDL_WIDE)
    if tabela_legada_existe(cur):
        cur.execute(DDL_LEGADO_PATCH)


# ── Resolução autor → politico_id PRISMA ──────────────────────────────────────
RESOLVE_EXATO = """
SELECT politico_id FROM politicos
 WHERE LOWER(nome_urna) = LOWER(%s)
   AND uf = %s
   AND COALESCE(sigla_partido,'') = COALESCE(%s,'')
 LIMIT 1
"""

RESOLVE_FUZZY = """
SELECT politico_id, similarity(LOWER(nome_completo), LOWER(%s)) AS sim
  FROM politicos
 WHERE uf = %s
   AND similarity(LOWER(nome_completo), LOWER(%s)) >= 0.85
 ORDER BY sim DESC
 LIMIT 1
"""


def resolver_politico_id(cur, autor: dict, cache: dict) -> str | None:
    nome = autor.get("nome")
    uf   = autor.get("uf")
    par  = autor.get("partido")
    if not nome or not uf:
        return None
    key = (nome.lower(), uf, (par or "").upper())
    if key in cache:
        return cache[key]
    pid = None
    try:
        cur.execute(RESOLVE_EXATO, (nome, uf, par))
        row = cur.fetchone()
        if row:
            pid = row[0]
        else:
            try:
                cur.execute(RESOLVE_FUZZY, (nome, uf, nome))
                row2 = cur.fetchone()
                if row2:
                    pid = row2[0]
            except psycopg2.Error:
                # pg_trgm pode não estar instalado — não derruba o lote
                pass
    except psycopg2.Error:
        pid = None
    cache[key] = pid
    return pid


# ── Pipeline ──────────────────────────────────────────────────────────────────
def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    records = prata.get("records", [])
    meta    = prata.get("meta", {})
    leg     = meta.get("legislatura", "?")
    print(f"📊 {len(records):,} proposições | Legislatura: {leg}")

    if dry_run:
        print("🔍 DRY-RUN — nenhum dado gravado")
        ok, faltas = 0, 0
        for r in records[:200]:
            if r.get("id") and r.get("tipo") and r.get("ano"):
                ok += 1
            else:
                faltas += 1
        print(f"✅ Dry-run: {ok}/{ok+faltas} amostra com campos essenciais")
        print(f"   {sum(1 for r in records if r.get('autores'))}/{len(records)} têm autores")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**db_config())
    cur    = conn.cursor()

    print("  🛠️  Garantindo schema (DDL idempotente)...")
    garantir_schema(cur)
    conn.commit()
    tem_legado = tabela_legada_existe(cur)

    # Resolve autores → politico_id PRISMA
    print("  🔗 Resolvendo autores contra politicos...")
    cache: dict = {}
    autores_resolvidos = 0
    autores_total = 0
    for r in records:
        ids_resolvidos: list[str] = []
        for autor in r.get("autores", []) or []:
            autores_total += 1
            pid = resolver_politico_id(cur, autor, cache)
            autor["politico_id_prisma"] = pid
            if pid:
                ids_resolvidos.append(pid)
                autores_resolvidos += 1
        r["autores_politico_ids"] = sorted(set(ids_resolvidos))
    pct = autores_resolvidos / max(autores_total, 1) * 100
    print(f"  🔗 Resolvidos {autores_resolvidos:,}/{autores_total:,} autores ({pct:.1f}%)")

    # Carga WIDE (1 linha por proposição)
    novos_wide = erros_wide = 0
    rows_wide = [
        {
            "id":                          r["id"],
            "tipo":                        r["tipo"],
            "numero":                      r["numero"],
            "ano":                         r["ano"],
            "ementa":                      r.get("ementa"),
            "ementa_detalhada":            r.get("ementa_detalhada"),
            "data_apresentacao":           r.get("data_apresentacao"),
            "status_situacao":             r.get("status_situacao"),
            "status_descricao_tramitacao": r.get("status_descricao_tramitacao"),
            "status_data":                 r.get("status_data"),
            "uri_orgao_atual":             r.get("uri_orgao_atual"),
            "sigla_orgao_atual":           r.get("sigla_orgao_atual"),
            "keywords":                    r.get("keywords") or [],
            "autores":                     Json(r.get("autores") or []),
            "autores_politico_ids":        r.get("autores_politico_ids") or [],
            "raw_hash":                    r.get("raw_hash"),
        }
        for r in records
    ]

    for i in range(0, len(rows_wide), 500):
        lote = rows_wide[i:i+500]
        try:
            cur.executemany(UPSERT_WIDE, lote)
            conn.commit()
            novos_wide += len(lote)
            if (i // 500 + 1) % 10 == 0 or i == 0:
                print(f"  ✅ Wide lote {i//500+1}: {novos_wide:,} processados...")
        except Exception as e:
            conn.rollback()
            erros_wide += len(lote)
            print(f"  ❌ Wide lote {i//500+1} falhou: {e}")

    # Carga LEGADO (1 linha por (proposicao, autor)) — só se a tabela existe
    novos_leg = erros_leg = 0
    if tem_legado:
        rows_legado = []
        for r in records:
            autores = r.get("autores") or []
            if not autores:
                continue
            for a in autores:
                pid = a.get("politico_id_prisma")
                if not pid:
                    continue   # legada exige politico_id NOT NULL
                rows_legado.append({
                    "id":                          r["id"],
                    "politico_id":                 pid,
                    "camara_id":                   a.get("id_camara"),
                    "tipo":                        r["tipo"],
                    "numero":                      str(r["numero"]) if r["numero"] is not None else None,
                    "ano":                         r["ano"],
                    "ementa":                      r.get("ementa"),
                    "descricao":                   r.get("ementa_detalhada"),
                    "dt_apresentacao":             r.get("data_apresentacao"),
                    "status_atual":                r.get("status_situacao"),
                    "ementa_detalhada":            r.get("ementa_detalhada"),
                    "status_situacao":             r.get("status_situacao"),
                    "status_descricao_tramitacao": r.get("status_descricao_tramitacao"),
                    "status_data":                 r.get("status_data"),
                    "uri_orgao_atual":             r.get("uri_orgao_atual"),
                    "sigla_orgao_atual":           r.get("sigla_orgao_atual"),
                    "keywords":                    r.get("keywords") or [],
                    "raw_hash":                    r.get("raw_hash"),
                })

        for i in range(0, len(rows_legado), 500):
            lote = rows_legado[i:i+500]
            try:
                cur.executemany(UPSERT_LEGADO, lote)
                conn.commit()
                novos_leg += len(lote)
                if (i // 500 + 1) % 10 == 0 or i == 0:
                    print(f"  ✅ Legado lote {i//500+1}: {novos_leg:,} processados...")
            except Exception as e:
                conn.rollback()
                erros_leg += len(lote)
                print(f"  ❌ Legado lote {i//500+1} falhou: {e}")
    else:
        print("  ℹ️  Tabela legada `camara_proposicoes` não existe — só wide foi populada")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    try:
        cur.execute(ETL_LOG, (
            f"camara_proposicoes_leg{leg}", "fase_1",
            "sucesso" if (erros_wide + erros_leg) == 0 else "parcial",
            len(records), novos_wide,
            None if (erros_wide + erros_leg) == 0
                 else f"wide:{erros_wide} legado:{erros_leg}",
            round(dur, 2), inicio, fim,
        ))
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        print(f"  ⚠️  etl_log indisponível ({e}) — seguindo")

    cur.close()
    conn.close()

    print(f"✅ Carga concluída em {dur:.1f}s")
    print(f"   Wide:   {novos_wide:,} processados | erros: {erros_wide}")
    print(f"   Legado: {novos_leg:,} processados | erros: {erros_leg}")


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader Câmara Proposições")
    parser.add_argument("--dry-run", action="store_true", help="Valida sem gravar")
    parser.add_argument("--prata",   help="Arquivo prata específico")
    parser.add_argument("--todos",   action="store_true", help="Todos os pratas")
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("proposicoes_*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("proposicoes_*_prata.json"),
                        key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        carregar_prata(pratas[0], args.dry_run)

    print("\n✅ Agent C concluído.")


if __name__ == "__main__":
    main()
