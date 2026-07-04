#!/usr/bin/env python3
"""Agent C — Loader Senado Proposições: Prata → tabela senado_proposicoes

Insere/atualiza no PostgreSQL (prisma_data).
ON CONFLICT (codigo) DO UPDATE — re-execução é segura e refresca campos voláteis
(situação_atual, autoria resolvida, ementa).

Schema esperado (cria se não existir):
    CREATE TABLE IF NOT EXISTS senado_proposicoes (
        codigo BIGINT PRIMARY KEY,
        tipo TEXT NOT NULL,
        numero INT,
        ano INT NOT NULL,
        ementa TEXT,
        data_apresentacao DATE,
        autoria TEXT,
        autores_politico_ids TEXT[],
        autores_detalhes JSONB,
        situacao_atual TEXT,
        casa TEXT DEFAULT 'SF',
        raw_hash TEXT UNIQUE,
        dt_carga TIMESTAMPTZ DEFAULT now()
    );

Execução:
    python agent_c_loader.py --dry-run
    python agent_c_loader.py --prata senado_prop_2024_prata.json
    python agent_c_loader.py --todos
"""
import json, argparse, os
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import Json

BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/senado_proposicoes/prata"


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "prisma_data"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
    )


DDL = """
CREATE TABLE IF NOT EXISTS senado_proposicoes (
    codigo BIGINT PRIMARY KEY,
    tipo TEXT NOT NULL,
    numero INT,
    ano INT NOT NULL,
    ementa TEXT,
    data_apresentacao DATE,
    autoria TEXT,
    autores_politico_ids TEXT[],
    autores_detalhes JSONB,
    situacao_atual TEXT,
    casa TEXT DEFAULT 'SF',
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_senado_prop_ano     ON senado_proposicoes(ano);
CREATE INDEX IF NOT EXISTS idx_senado_prop_autores ON senado_proposicoes USING gin(autores_politico_ids);
"""

UPSERT_SQL = """
INSERT INTO senado_proposicoes (
    codigo, tipo, numero, ano, ementa,
    data_apresentacao, autoria, autores_politico_ids,
    autores_detalhes, situacao_atual, casa, raw_hash
) VALUES (
    %(codigo)s, %(tipo)s, %(numero)s, %(ano)s, %(ementa)s,
    %(data_apresentacao)s, %(autoria)s, %(autores_politico_ids)s,
    %(autores_detalhes)s, %(situacao_atual)s, %(casa)s, %(raw_hash)s
)
ON CONFLICT (codigo) DO UPDATE SET
    ementa               = EXCLUDED.ementa,
    autoria              = EXCLUDED.autoria,
    autores_politico_ids = EXCLUDED.autores_politico_ids,
    autores_detalhes     = EXCLUDED.autores_detalhes,
    situacao_atual       = EXCLUDED.situacao_atual,
    raw_hash             = EXCLUDED.raw_hash,
    dt_carga             = now()
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _prep(r: dict) -> dict:
    return {
        "codigo":               r.get("codigo"),
        "tipo":                 r.get("tipo") or "DESCONHECIDO",
        "numero":               r.get("numero"),
        "ano":                  r.get("ano"),
        "ementa":               r.get("ementa"),
        "data_apresentacao":    r.get("data_apresentacao"),
        "autoria":              r.get("autoria"),
        "autores_politico_ids": r.get("autores_politico_ids") or [],
        "autores_detalhes":     Json(r.get("autores_detalhes") or []),
        "situacao_atual":       r.get("situacao_atual"),
        "casa":                 r.get("casa") or "SF",
        "raw_hash":             r.get("raw_hash"),
    }


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    records = prata.get("records", [])
    meta    = prata.get("meta", {})
    ano     = meta.get("ano", "?")
    print(f"📊 {len(records):,} registros | Ano: {ano} | Com politico_id: "
          f"{meta.get('com_politico_id', '?')}")

    if dry_run:
        print("🔍 DRY-RUN — nada gravado")
        erros = 0
        for r in records[:200]:
            for campo in ("codigo", "tipo", "ano", "raw_hash"):
                if r.get(campo) in (None, ""):
                    print(f"  ⚠️  Campo ausente '{campo}' em codigo={r.get('codigo')}")
                    erros += 1
        print(f"✅ Dry-run OK | Erros validação (200 primeiros): {erros}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = get_conn()
    cur    = conn.cursor()
    cur.execute(DDL)
    conn.commit()

    novos = erros = 0
    for i in range(0, len(records), 500):
        lote = [_prep(r) for r in records[i:i+500]]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            if (i // 500 + 1) % 10 == 0 or i == 0:
                print(f"  ✅ Lote {i//500+1}: {novos:,} processados...")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//500+1} falhou: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    try:
        cur.execute(ETL_LOG, (
            f"senado_proposicoes_{ano}", "fase_2",
            "sucesso" if erros == 0 else "parcial",
            len(records), novos,
            None if erros == 0 else f"{erros} erros",
            round(dur, 2), inicio, fim,
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"  ⚠️  etl_log indisponível: {e}")

    cur.close()
    conn.close()
    print(f"✅ Carga em {dur:.1f}s | Processados: {novos:,} | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader Senado Proposições")
    parser.add_argument("--dry-run", action="store_true", help="Valida sem gravar")
    parser.add_argument("--prata",   help="Arquivo prata específico")
    parser.add_argument("--todos",   action="store_true", help="Todos os pratas")
    args = parser.parse_args()

    if args.prata:
        carregar_prata(Path(args.prata), args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("senado_prop_*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        pratas = sorted(PRATA_DIR.glob("senado_prop_*_prata.json"),
                        key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        carregar_prata(pratas[0], args.dry_run)

    print("\n✅ Agent C concluído.")


if __name__ == "__main__":
    main()
