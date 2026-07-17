#!/usr/bin/env python3
"""Agent C — carrega Prata no PostgreSQL e enriquece identidade/sanções."""
import argparse
import gzip
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

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
DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "prisma_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)

COLUNAS = (
    "linha_hash", "sq_candidato", "ano_eleicao", "uf", "cargo", "sigla_partido",
    "fornecedor_cnpj_cpf", "fornecedor_nome", "fornecedor_nome_rfb", "tipo_fornecedor",
    "tipo_despesa", "descricao", "valor", "data_despesa", "documento_tipo",
    "documento_numero", "tse_despesa_id", "linha_origem", "origem_arquivo",
)

UPSERT = f"""
INSERT INTO despesas_campanha ({', '.join(COLUNAS)}) VALUES %s
ON CONFLICT (linha_hash) DO UPDATE SET
    fornecedor_nome = EXCLUDED.fornecedor_nome,
    fornecedor_nome_rfb = EXCLUDED.fornecedor_nome_rfb,
    tipo_fornecedor = EXCLUDED.tipo_fornecedor,
    tipo_despesa = EXCLUDED.tipo_despesa,
    descricao = EXCLUDED.descricao,
    valor = EXCLUDED.valor,
    data_despesa = EXCLUDED.data_despesa,
    documento_tipo = EXCLUDED.documento_tipo,
    documento_numero = EXCLUDED.documento_numero,
    tse_despesa_id = EXCLUDED.tse_despesa_id,
    linha_origem = EXCLUDED.linha_origem,
    origem_arquivo = EXCLUDED.origem_arquivo,
    verificacao_status = 'PENDENTE',
    verificado_em = NULL,
    updated_at = now()
"""


def lotes(arquivo: Path, tamanho: int = 2000):
    lote = []
    with gzip.open(arquivo, "rt", encoding="utf-8") as entrada:
        for linha in entrada:
            registro = json.loads(linha)
            lote.append(tuple(registro.get(coluna) for coluna in COLUNAS))
            if len(lote) >= tamanho:
                yield lote
                lote = []
    if lote:
        yield lote


def enriquecer(conn, ano: int, uf: str) -> tuple[int, int]:
    cur = conn.cursor()
    cur.execute("""
        UPDATE despesas_campanha d
        SET politico_id = p.politico_id, pessoa_id = p.pessoa_id, updated_at = now()
        FROM (
            SELECT DISTINCT ON (sq_candidato, ano_eleicao)
                   sq_candidato, ano_eleicao, politico_id, pessoa_id
            FROM politicos
            WHERE sq_candidato IS NOT NULL AND politico_id IS NOT NULL
              AND ano_eleicao = %s AND uf = %s
            ORDER BY sq_candidato, ano_eleicao, updated_at DESC NULLS LAST, id_tse DESC
        ) p
        WHERE d.sq_candidato = p.sq_candidato
          AND d.ano_eleicao = p.ano_eleicao
          AND d.ano_eleicao = %s AND d.uf = %s
          AND (d.politico_id IS DISTINCT FROM p.politico_id
               OR d.pessoa_id IS DISTINCT FROM p.pessoa_id)
    """, (ano, uf, ano, uf))
    identidades = cur.rowcount

    cur.execute("""
        UPDATE despesas_campanha
        SET status_lneg = 'OK', updated_at = now()
        WHERE ano_eleicao = %s AND uf = %s
    """, (ano, uf))
    sancoes_avaliadas = cur.rowcount
    cur.execute("""
        WITH sancoes AS (
            SELECT DISTINCT
                COALESCE(
                    NULLIF(TRANSLATE(COALESCE(cnpj, ''), './-', ''), ''),
                    NULLIF(TRANSLATE(COALESCE(cpf_sancionado, ''), './-', ''), '')
                ) AS documento,
                COALESCE(data_inicio, DATE '1900-01-01') AS data_inicio,
                COALESCE(data_fim, DATE '9999-12-31') AS data_fim
            FROM lista_negra_vigencia
        )
        UPDATE despesas_campanha d
        SET status_lneg = 'MATCH', updated_at = now()
        FROM sancoes s
        WHERE d.ano_eleicao = %s AND d.uf = %s
          AND s.documento = d.fornecedor_cnpj_cpf
          AND d.data_despesa BETWEEN s.data_inicio AND s.data_fim
    """, (ano, uf))
    conn.commit()
    return identidades, sancoes_avaliadas


def carregar(arquivo: Path, dry_run: bool = False, enriquecer_only: bool = False) -> None:
    match = re.match(r"despesas_(\d{4})_([A-Z]{2})_prata\.jsonl\.gz", arquivo.name)
    if not match:
        raise ValueError(f"Nome Prata inválido: {arquivo.name}")
    ano, uf = int(match.group(1)), match.group(2)
    if dry_run:
        total = sum(len(lote) for lote in lotes(arquivo))
        print(f"🔍 DRY-RUN {ano}/{uf}: {total:,} registros válidos")
        return

    inicio = datetime.now(timezone.utc)
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    processados = 0
    try:
        if enriquecer_only:
            cur.execute("SELECT count(*) FROM despesas_campanha WHERE ano_eleicao=%s AND uf=%s", (ano, uf))
            processados = cur.fetchone()[0]
        else:
            for numero, lote in enumerate(lotes(arquivo), start=1):
                execute_values(cur, UPSERT, lote, page_size=2000)
                conn.commit()
                processados += len(lote)
                if numero % 10 == 0:
                    print(f"  {ano}/{uf}: {processados:,} registros")
        identidades, sancoes = enriquecer(conn, ano, uf)
        fim = datetime.now(timezone.utc)
        registros_novos = 0 if enriquecer_only else processados
        cur.execute("""
            INSERT INTO etl_log (
                portal, fase, status, total_registros, registros_novos,
                registros_atualizados, duracao_seg, iniciado_em, finalizado_em
            ) VALUES (%s, 'fase_0', 'sucesso', %s, %s, %s, %s, %s, %s)
        """, (
            f"tse_despesas_campanha_{ano}_{uf}", processados, registros_novos,
            identidades, round((fim - inicio).total_seconds(), 2), inicio, fim,
        ))
        conn.commit()
        print(f"✅ {ano}/{uf}: {processados:,} carregados · {identidades:,} identidades atualizadas · {sancoes:,} sanções avaliadas")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent C — TSE despesas de campanha")
    parser.add_argument("--prata")
    parser.add_argument("--todos", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--enriquecer-only", action="store_true", help="não repete upsert; resolve identidade e sanções do lote existente")
    args = parser.parse_args()
    arquivos = [Path(args.prata)] if args.prata else sorted(PRATA_DIR.glob("*_prata.jsonl.gz"))
    if not arquivos:
        raise SystemExit("Nenhum Prata encontrado")
    for arquivo in arquivos:
        carregar(arquivo, args.dry_run, args.enriquecer_only)


if __name__ == "__main__":
    main()
