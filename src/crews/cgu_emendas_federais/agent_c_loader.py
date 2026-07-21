#!/usr/bin/env python3
"""Agent C — Loader: Prata → tabela emendas_federais

UPSERT por codigo_emenda (PK natural da tabela) — idempotente.

Regra de conflito: nunca regredir dado já bom.
  - politico_id / cnpj_favorecido / municipio_ibge: COALESCE(existente, novo) —
    o processo ad-hoc que carregou 2015-2026 bate ~93% de match de politico_id;
    o matcher desta crew (nome+UF, fuzzy≥88) sozinho bate ~77% (medido 2026-07-20,
    nome CGU costuma ser nome civil completo, TSE usa apelido de urna). Por isso
    o valor JÁ GRAVADO tem prioridade — este loader só preenche o que ainda é NULL,
    nunca substitui um match existente por um novo (mesmo que diferente).
  - status_lneg: NUNCA tocado no UPDATE — é resolvido por um matcher separado
    (contra lista_negra_vigencia) que roda depois; sobrescrever aqui apagaria
    o trabalho de 'OK'/'MATCH' já feito. Só é setado 'PENDENTE' no INSERT quando
    há cnpj_favorecido, senão fica NULL.
  - demais campos (valores monetários, funcao, etc.): sempre atualizados —
    são dado bruto do CSV, não há por que preferir o antigo.

Execução:
    python agent_c_loader.py --dry-run
    python agent_c_loader.py --ano 2014
    python agent_c_loader.py --todos
"""
import json, argparse, psycopg2, psycopg2.extras
from pathlib import Path
from datetime import datetime, timezone
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/cgu_emendas_federais/prata"

DB = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 5432)),
    dbname   = os.getenv("DB_NAME", "prisma_data"),
    user     = os.getenv("DB_USER", "postgres"),
    password = DB_PASSWORD,
)

UPSERT_SQL = """
INSERT INTO emendas_federais (
    codigo_emenda, politico_id, municipio_ibge, funcao, subfuncao,
    valor_empenhado, valor_liquidado, valor_pago, cnpj_favorecido,
    ano_orcamento, status_lneg, tipo_emenda, nome_autor, numero_emenda,
    localidade_raw, valor_resto_pago
) VALUES (
    %(codigo_emenda)s, %(politico_id)s, %(municipio_ibge)s, %(funcao)s, %(subfuncao)s,
    %(valor_empenhado)s, %(valor_liquidado)s, %(valor_pago)s, %(cnpj_favorecido)s,
    %(ano_orcamento)s, %(status_lneg_inicial)s, %(tipo_emenda)s, %(nome_autor)s, %(numero_emenda)s,
    %(localidade_raw)s, %(valor_resto_pago)s
)
ON CONFLICT (codigo_emenda) DO UPDATE SET
    politico_id      = COALESCE(emendas_federais.politico_id, EXCLUDED.politico_id),
    municipio_ibge   = COALESCE(emendas_federais.municipio_ibge, EXCLUDED.municipio_ibge),
    cnpj_favorecido  = COALESCE(emendas_federais.cnpj_favorecido, EXCLUDED.cnpj_favorecido),
    funcao           = EXCLUDED.funcao,
    subfuncao        = EXCLUDED.subfuncao,
    valor_empenhado  = EXCLUDED.valor_empenhado,
    valor_liquidado  = EXCLUDED.valor_liquidado,
    valor_pago       = EXCLUDED.valor_pago,
    ano_orcamento    = EXCLUDED.ano_orcamento,
    tipo_emenda      = EXCLUDED.tipo_emenda,
    nome_autor       = EXCLUDED.nome_autor,
    numero_emenda    = EXCLUDED.numero_emenda,
    localidade_raw   = EXCLUDED.localidade_raw,
    valor_resto_pago = EXCLUDED.valor_resto_pago
"""

ETL_LOG_SQL = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""

LOTE = 500


def carregar_prata(prata_path: Path, dry_run: bool) -> None:
    print(f"📂 {prata_path.name}")
    with open(prata_path, encoding="utf-8") as f:
        prata = json.load(f)

    records = prata.get("records", [])
    meta    = prata.get("meta", {})
    print(f"  📊 {len(records):,} registros | politico_id {meta.get('pct_politico_id', '?')}% | "
          f"cnpj {meta.get('pct_cnpj', '?')}% | ibge {meta.get('pct_municipio_ibge', '?')}%")

    for r in records:
        r["status_lneg_inicial"] = "PENDENTE" if r.get("cnpj_favorecido") else None

    if dry_run:
        sem_cod = sum(1 for r in records if not r.get("codigo_emenda"))
        print(f"  🔍 DRY-RUN: {len(records):,} prontos | sem codigo_emenda: {sem_cod}")
        return

    inicio = datetime.now(timezone.utc)
    conn   = psycopg2.connect(**DB)
    cur    = conn.cursor()
    processados = erros = 0

    for i in range(0, len(records), LOTE):
        lote = records[i:i + LOTE]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            processados += len(lote)
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i // LOTE + 1}: {e}")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    ano = meta.get("ano", "?")
    cur.execute(ETL_LOG_SQL, (
        f"cgu_emendas_federais_{ano}", "fase_2",
        "sucesso" if erros == 0 else "parcial",
        len(records), processados,
        None if erros == 0 else f"{erros} erros",
        round(dur, 2), inicio, fim,
    ))
    conn.commit()
    cur.close()
    conn.close()

    print(f"  ✅ {processados:,} upserts em {dur:.1f}s | Erros: {erros}")


def main():
    parser = argparse.ArgumentParser(description="Agent C — Loader CGU Emendas Federais")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ano",     type=int, help="Ano específico")
    parser.add_argument("--todos",   action="store_true")
    args = parser.parse_args()

    if args.ano:
        p = PRATA_DIR / f"emendas_federais_{args.ano}_prata.json"
        if not p.exists():
            print(f"❌ Prata não encontrado: {p.name} — rode Agent B primeiro.")
            return
        carregar_prata(p, args.dry_run)
    elif args.todos:
        pratas = sorted(PRATA_DIR.glob("emendas_federais_*_prata.json"))
        if not pratas:
            print("❌ Nenhum Prata encontrado. Execute Agent A+B primeiro.")
            return
        for p in pratas:
            carregar_prata(p, args.dry_run)
            print()
    else:
        parser.print_help()
        return

    print("\n✅ Agent C concluído.")


if __name__ == "__main__":
    main()
