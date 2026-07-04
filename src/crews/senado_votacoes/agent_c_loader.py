#!/usr/bin/env python3
"""Agent C — Loader Senado Votações: Prata → senado_votacoes + senado_votos_nominais

Cria tabelas se não existirem e carrega em duas etapas por votação:
  1) UPSERT no cabeçalho (senado_votacoes)
  2) DELETE + INSERT (replace) dos votos individuais (senado_votos_nominais),
     dentro da mesma transação por votação — garante consistência se a lista
     de votos for re-publicada pela API.

Execução:
    python agent_c_loader.py --dry-run
    python agent_c_loader.py --prata senado_vot_2024_prata.json
    python agent_c_loader.py --todos
"""
import json, argparse, os
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/senado_votacoes/prata"


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "prisma_data"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
    )


DDL = """
CREATE TABLE IF NOT EXISTS senado_votacoes (
    codigo BIGINT PRIMARY KEY,
    data DATE,
    descricao TEXT,
    materia_codigo BIGINT,
    resultado TEXT,
    total_sim INT,
    total_nao INT,
    total_abstencao INT,
    sessao_codigo BIGINT,
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS senado_votos_nominais (
    votacao_codigo BIGINT NOT NULL REFERENCES senado_votacoes(codigo) ON DELETE CASCADE,
    senador_codigo INT NOT NULL,
    politico_id TEXT,
    nome TEXT,
    sigla_partido TEXT,
    sigla_uf TEXT,
    tipo_voto TEXT,
    PRIMARY KEY (votacao_codigo, senador_codigo)
);
CREATE INDEX IF NOT EXISTS idx_senado_votos_pol
    ON senado_votos_nominais(politico_id) WHERE politico_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_senado_votacoes_materia
    ON senado_votacoes(materia_codigo) WHERE materia_codigo IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_senado_votacoes_data
    ON senado_votacoes(data);
"""

UPSERT_VOTACAO = """
INSERT INTO senado_votacoes (
    codigo, data, descricao, materia_codigo, resultado,
    total_sim, total_nao, total_abstencao, sessao_codigo, raw_hash
) VALUES (
    %(codigo)s, %(data)s, %(descricao)s, %(materia_codigo)s, %(resultado)s,
    %(total_sim)s, %(total_nao)s, %(total_abstencao)s, %(sessao_codigo)s, %(raw_hash)s
)
ON CONFLICT (codigo) DO UPDATE SET
    data            = EXCLUDED.data,
    descricao       = EXCLUDED.descricao,
    materia_codigo  = EXCLUDED.materia_codigo,
    resultado       = EXCLUDED.resultado,
    total_sim       = EXCLUDED.total_sim,
    total_nao       = EXCLUDED.total_nao,
    total_abstencao = EXCLUDED.total_abstencao,
    sessao_codigo   = EXCLUDED.sessao_codigo,
    raw_hash        = EXCLUDED.raw_hash,
    dt_carga        = now()
"""

DELETE_VOTOS = "DELETE FROM senado_votos_nominais WHERE votacao_codigo = %s"

INSERT_VOTOS = """
INSERT INTO senado_votos_nominais (
    votacao_codigo, senador_codigo, politico_id, nome,
    sigla_partido, sigla_uf, tipo_voto
) VALUES %s
ON CONFLICT (votacao_codigo, senador_codigo) DO UPDATE SET
    politico_id   = EXCLUDED.politico_id,
    nome          = EXCLUDED.nome,
    sigla_partido = EXCLUDED.sigla_partido,
    sigla_uf      = EXCLUDED.sigla_uf,
    tipo_voto     = EXCLUDED.tipo_voto
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    records = prata.get("records", [])
    meta    = prata.get("meta", {})
    ano     = meta.get("ano", "?")
    total_votos = sum(len(r.get("votos", [])) for r in records)
    print(f"📊 {len(records):,} votações | {total_votos:,} votos | Ano: {ano}")

    if dry_run:
        print("🔍 DRY-RUN — nada gravado")
        erros = 0
        for r in records[:50]:
            v = r.get("votacao", {})
            for campo in ("codigo", "raw_hash"):
                if v.get(campo) in (None, ""):
                    print(f"  ⚠️  Campo ausente '{campo}' em codigo={v.get('codigo')}")
                    erros += 1
        print(f"✅ Dry-run OK | Erros validação (50 primeiros): {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = get_conn()
    cur    = conn.cursor()
    cur.execute(DDL)
    conn.commit()

    novas = erros = votos_inseridos = 0
    for idx, r in enumerate(records):
        v = r.get("votacao", {})
        votos = r.get("votos", [])
        try:
            cur.execute(UPSERT_VOTACAO, v)
            cur.execute(DELETE_VOTOS, (v["codigo"],))
            if votos:
                rows = [
                    (v["codigo"], vt["senador_codigo"], vt.get("politico_id"),
                     vt.get("nome"), vt.get("sigla_partido"), vt.get("sigla_uf"),
                     vt.get("tipo_voto"))
                    for vt in votos
                ]
                execute_values(cur, INSERT_VOTOS, rows)
                votos_inseridos += len(rows)
            conn.commit()
            novas += 1
            if (idx + 1) % 200 == 0:
                print(f"  ✅ {novas:,}/{len(records):,} votações processadas | "
                      f"{votos_inseridos:,} votos")
        except Exception as e:
            conn.rollback()
            erros += 1
            print(f"  ❌ Votação {v.get('codigo')}: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    try:
        cur.execute(ETL_LOG, (
            f"senado_votacoes_{ano}", "fase_2",
            "sucesso" if erros == 0 else "parcial",
            len(records), novas,
            None if erros == 0 else f"{erros} votações com erro",
            round(dur, 2), inicio, fim,
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"  ⚠️  etl_log indisponível: {e}")

    cur.close()
    conn.close()
    print(f"✅ Carga em {dur:.1f}s | Votações: {novas:,} | Votos: {votos_inseridos:,} | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader Senado Votações")
    parser.add_argument("--dry-run", action="store_true", help="Valida sem gravar")
    parser.add_argument("--prata",   help="Arquivo prata específico")
    parser.add_argument("--todos",   action="store_true", help="Todos os pratas")
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("senado_vot_*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("senado_vot_*_prata.json"),
                        key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        carregar_prata(pratas[0], args.dry_run)

    print("\n✅ Agent C concluído.")


if __name__ == "__main__":
    main()
