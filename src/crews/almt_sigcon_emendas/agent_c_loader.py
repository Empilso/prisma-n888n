#!/usr/bin/env python3
"""Agent C — Loader ALMT/SIGCON Emendas MT: Prata → Postgres

Carrega as duas camadas prata:
  - emendas_estaduais            (agregado por emenda, uf='MT')
  - emendas_estaduais_aplicacoes (granular, 1 linha por emenda×convênio)

Execução:
    python agent_c_loader.py --ano 2024 --dry-run
    python agent_c_loader.py --todos
"""
import argparse
import json
import os
from datetime import datetime, timezone
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
PRATA_DIR = BASE_DIR / "data/almt_sigcon_emendas/prata"

UPSERT_AGREGADO = """
INSERT INTO emendas_estaduais (
    uf, numero_emenda, numero_emenda_origem, ano_orcamento, politico_id, parlamentar_nome,
    municipio_ibge, objeto, valor_pago, origem_fonte
) VALUES (
    %(uf)s, %(numero_emenda)s, %(numero_emenda_origem)s, %(ano_orcamento)s, %(politico_id)s, %(parlamentar_nome)s,
    %(municipio_ibge)s, %(objeto)s, %(valor_pago)s, %(origem_fonte)s
)
ON CONFLICT (uf, numero_emenda, ano_orcamento) DO UPDATE SET
    numero_emenda_origem = EXCLUDED.numero_emenda_origem,
    politico_id      = EXCLUDED.politico_id,
    parlamentar_nome = EXCLUDED.parlamentar_nome,
    municipio_ibge   = EXCLUDED.municipio_ibge,
    objeto           = EXCLUDED.objeto,
    valor_pago       = EXCLUDED.valor_pago
"""

UPSERT_APLICACAO = """
INSERT INTO emendas_estaduais_aplicacoes (
    uf, ano_orcamento, numero_emenda, numero_emenda_origem, politico_id, parlamentar_nome,
    conv_id, numero_convenio, concedente, proponente, municipio_ibge,
    objeto, processo, valor_utilizado, valor_convenio,
    vigencia_inicio, vigencia_fim, origem_fonte
) VALUES (
    %(uf)s, %(ano_orcamento)s, %(numero_emenda)s, %(numero_emenda_origem)s, %(politico_id)s, %(parlamentar_nome)s,
    %(conv_id)s, %(numero_convenio)s, %(concedente)s, %(proponente)s, %(municipio_ibge)s,
    %(objeto)s, %(processo)s, %(valor_utilizado)s, %(valor_convenio)s,
    %(vigencia_inicio)s, %(vigencia_fim)s, %(origem_fonte)s
)
ON CONFLICT (uf, ano_orcamento, numero_emenda, conv_id) DO UPDATE SET
    politico_id      = EXCLUDED.politico_id,
    valor_utilizado  = EXCLUDED.valor_utilizado,
    valor_convenio   = EXCLUDED.valor_convenio,
    objeto           = EXCLUDED.objeto
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def carregar_ano(prata_path: Path, dry_run: bool) -> None:
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    aplicacoes = prata["aplicacoes"]
    agregado = prata["agregado"]
    ano = aplicacoes[0]["ano_orcamento"] if aplicacoes else (agregado[0]["ano_orcamento"] if agregado else "?")
    print(f"📂 {prata_path.name} | ano {ano} | {len(agregado)} emendas agregadas, {len(aplicacoes)} aplicações")

    if dry_run:
        sem_pid_agr = sum(1 for a in agregado if not a.get("politico_id"))
        print(f"🔍 DRY-RUN — {len(agregado)} emendas prontas ({sem_pid_agr} sem politico_id)")
        return

    inicio = datetime.now(timezone.utc)
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    novos_agr = novos_apl = erros = 0
    try:
        for a in agregado:
            row = {k: a.get(k) for k in (
                "uf", "numero_emenda", "numero_emenda_origem", "ano_orcamento", "politico_id", "parlamentar_nome",
                "municipio_ibge", "objeto", "valor_pago", "origem_fonte")}
            cur.execute(UPSERT_AGREGADO, row)
        novos_agr = len(agregado)
        conn.commit()
    except Exception as e:
        conn.rollback()
        erros += len(agregado)
        print(f"  ❌ agregado: {e}")

    try:
        for i in range(0, len(aplicacoes), 500):
            lote = aplicacoes[i:i + 500]
            cur.executemany(UPSERT_APLICACAO, lote)
            conn.commit()
            novos_apl += len(lote)
    except Exception as e:
        conn.rollback()
        erros += len(aplicacoes) - novos_apl
        print(f"  ❌ aplicações: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()
    cur.execute(ETL_LOG, (
        "almt_sigcon_emendas", f"ano_{ano}",
        "sucesso" if erros == 0 else "parcial",
        len(agregado) + len(aplicacoes), novos_agr + novos_apl,
        None if erros == 0 else f"{erros} erros",
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {novos_agr} emendas + {novos_apl} aplicações upserted em {dur:.1f}s | Erros: {erros}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Agent C — Loader ALMT/SIGCON Emendas MT")
    ap.add_argument("--ano", type=int)
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.ano and not args.todos:
        ap.error("passe --ano AAAA (teste) ou --todos")

    if args.ano:
        pratas = [PRATA_DIR / f"almt_sigcon_{args.ano}_prata.json"]
    else:
        pratas = sorted(PRATA_DIR.glob("almt_sigcon_*_prata.json"))

    for p in pratas:
        if not p.exists():
            print(f"⚠️  {p.name} não encontrado — rode Agent B primeiro")
            continue
        carregar_ano(p, args.dry_run)
        print()

    print("✅ Agent C concluído.")


if __name__ == "__main__":
    main()
