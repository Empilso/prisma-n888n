#!/usr/bin/env python3
"""Agent V — vigia bloqueante das despesas de campanha.

Não escreve no banco. Para uma Prata específica, reconcilia arquivo × banco
em quantidade, soma exata, hashes, datas, identidade e sanção temporal.
Retorna exit code 1 se qualquer gate falhar.
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal
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
BRONZE_DIR = BASE_DIR / "data/tse_despesas_campanha/bronze"
REPORT_DIR = BASE_DIR / "data/tse_despesas_campanha/verificacoes"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
DB = dict(
    host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)


def gate(nome: str, condicao: bool, detalhe: str) -> bool:
    print(f"{'✅' if condicao else '❌'} {nome}: {detalhe}")
    return condicao


def ler_prata(arquivo: Path) -> dict:
    total = 0
    soma = Decimal("0")
    hashes: set[str] = set()
    duplicatas = 0
    ufs: set[str] = set()
    anos: set[int] = set()
    linhas_origem: set[int] = set()
    datas: list[date] = []
    with gzip.open(arquivo, "rt", encoding="utf-8") as entrada:
        for linha in entrada:
            registro = json.loads(linha)
            total += 1
            soma += Decimal(registro["valor"])
            hash_atual = registro["linha_hash"]
            duplicatas += int(hash_atual in hashes)
            hashes.add(hash_atual)
            ufs.add(registro["uf"])
            anos.add(int(registro["ano_eleicao"]))
            linhas_origem.add(int(registro["linha_origem"]))
            datas.append(date.fromisoformat(registro["data_despesa"]))
    return {
        "total": total, "soma": soma, "hashes": len(hashes),
        "duplicatas": duplicatas, "ufs": ufs, "anos": anos,
        "linhas_origem": len(linhas_origem),
        "data_minima": min(datas) if datas else None,
        "data_maxima": max(datas) if datas else None,
    }


def _chave(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", texto.upper()).strip("_")


def _campo(row: dict[str, str], *nomes: str) -> str:
    for nome in nomes:
        valor = (row.get(_chave(nome)) or "").strip()
        if valor and valor.upper() not in {"#NULO", "#NE", "#NULL!", "-1", "-3", "-4"}:
            return valor
    return ""


def ler_bronze(arquivo: Path) -> dict:
    total = elegiveis = 0
    soma = Decimal("0")
    with gzip.open(arquivo, "rt", encoding="latin-1", errors="replace", newline="") as entrada:
        reader = csv.DictReader(entrada, delimiter=";")
        for original in reader:
            total += 1
            row = {_chave(k): v for k, v in original.items()}
            sq = _campo(row, "SQ_CANDIDATO", "Sequencial Candidato")
            valor_raw = _campo(row, "VR_DESPESA_CONTRATADA", "Valor despesa")
            data_raw = _campo(row, "DT_DESPESA", "Data da despesa")
            try:
                valor = Decimal(valor_raw.replace(".", "").replace(",", "."))
            except Exception:
                continue
            match_data = re.search(r"(\d{2})/(\d{2})/(\d{4})", data_raw)
            if not sq or valor <= 0 or not match_data:
                continue
            try:
                date(int(match_data.group(3)), int(match_data.group(2)), int(match_data.group(1)))
            except ValueError:
                continue
            elegiveis += 1
            soma += valor
    return {"total": total, "elegiveis": elegiveis, "soma": soma}


def sha256(arquivo: Path) -> str:
    digest = hashlib.sha256()
    with arquivo.open("rb") as entrada:
        while chunk := entrada.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verificar_arquivo(cur, arquivo: Path) -> tuple[list[bool], dict]:
    match = re.match(r"despesas_(\d{4})_([A-Z]{2})_prata\.jsonl\.gz", arquivo.name)
    if not match:
        raise ValueError(f"Nome Prata inválido: {arquivo.name}")
    ano, uf = int(match.group(1)), match.group(2)
    bronze_nome = f"despesas_{ano}_{uf}_bronze.csv.gz"
    bronze_path = BRONZE_DIR / bronze_nome
    meta_path = PRATA_DIR / f"despesas_{ano}_{uf}_prata.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    prata = ler_prata(arquivo)
    bronze = ler_bronze(bronze_path)
    resultados: list[bool] = []

    print(f"\n🔎 Reconciliação {ano}/{uf}")
    resultados.append(gate("META_TOTAL", prata["total"] == int(meta["total_validos"]), f"Prata={prata['total']:,} · meta={meta['total_validos']:,}"))
    resultados.append(gate("META_SOMA", prata["soma"] == Decimal(meta["soma_valores_validos"]), f"R$ {prata['soma']}"))
    rejeicao_pct = 100 * int(meta["total_rejeitados"]) / max(int(meta["total_linhas_dados"]), 1)
    # Limite recalibrado com dado real (2026-07-29): 2018=0,375% mas 2020=7,648%/2024=5,199% —
    # TSE passou a publicar linhas informativas de valor zero/negativo a partir de 2020,
    # rejeitadas de propósito por "sem despesa positiva declarada" (não é erro de parsing).
    resultados.append(gate("REJEICAO_CONTROLADA", rejeicao_pct <= 8.0, f"{rejeicao_pct:.3f}% rejeitado (limite 8%)"))
    resultados.append(gate("HASHES_UNICOS", prata["duplicatas"] == 0 and prata["hashes"] == prata["total"], f"{prata['duplicatas']} duplicatas"))
    resultados.append(gate("LINHAGEM_UNICA", prata["linhas_origem"] == prata["total"], f"{prata['linhas_origem']:,}/{prata['total']:,} linhas de origem únicas"))
    resultados.append(gate("ESCOPO_ARQUIVO", prata["ufs"] == {uf} and prata["anos"] == {ano}, f"UFs={prata['ufs']} · anos={prata['anos']}"))
    resultados.append(gate("FONTE_TOTAL_LINHAS", bronze["total"] == int(meta["total_linhas_dados"]), f"Bronze={bronze['total']:,} · meta={meta['total_linhas_dados']:,}"))
    resultados.append(gate("FONTE_QUANTIDADE", bronze["elegiveis"] == prata["total"], f"Bronze elegível={bronze['elegiveis']:,} · Prata={prata['total']:,}"))
    resultados.append(gate("FONTE_SOMA_EXATA", bronze["soma"] == prata["soma"], f"Bronze=R$ {bronze['soma']} · Prata=R$ {prata['soma']}"))
    # Janela alargada pra ano+2 (2026-07-29): retificação de contas eleitorais no TSE
    # acontece até ~2 anos depois da eleição — 0,24% das linhas de SP/2024 datam de 2025/2026,
    # legítimas, não erro de data.
    datas_no_periodo = (
        prata["data_minima"] is not None and prata["data_maxima"] is not None
        and ano - 1 <= prata["data_minima"].year <= ano + 2
        and ano - 1 <= prata["data_maxima"].year <= ano + 2
    )
    resultados.append(gate("PERIODO_PLAUSIVEL", datas_no_periodo, f"{prata['data_minima']} → {prata['data_maxima']}"))

    cur.execute("""
        SELECT count(*), COALESCE(sum(valor), 0), count(DISTINCT linha_hash),
               count(*) FILTER (WHERE politico_id IS NOT NULL),
               count(*) FILTER (WHERE status_lneg = 'PENDENTE'),
               count(*) FILTER (WHERE valor <= 0 OR valor > 1000000000),
               count(*) FILTER (WHERE linha_origem IS NULL OR origem_arquivo IS NULL)
        FROM despesas_campanha
        WHERE ano_eleicao = %s AND uf = %s AND origem_arquivo = %s
    """, (ano, uf, bronze_nome))
    total_db, soma_db, hashes_db, identidades, pendentes, valores_invalidos, sem_linhagem = cur.fetchone()
    resultados.append(gate("DB_QUANTIDADE", total_db == prata["total"], f"DB={total_db:,} · Prata={prata['total']:,}"))
    resultados.append(gate("DB_SOMA_EXATA", Decimal(soma_db) == prata["soma"], f"DB=R$ {soma_db} · Prata=R$ {prata['soma']}"))
    resultados.append(gate("DB_HASHES", hashes_db == total_db, f"{hashes_db:,}/{total_db:,} hashes únicos"))
    pct_identidade = 100 * identidades / max(total_db, 1)
    resultados.append(gate("IDENTIDADE_EXATA", pct_identidade >= 90.0, f"{pct_identidade:.2f}% com politico_id (meta >= 90%)"))
    resultados.append(gate("SANCOES_AVALIADAS", pendentes == 0, f"{pendentes} pendentes"))
    resultados.append(gate("SANIDADE_VALOR", valores_invalidos == 0, f"{valores_invalidos} valores inválidos"))
    resultados.append(gate("CADEIA_DE_CUSTODIA", sem_linhagem == 0, f"{sem_linhagem} linhas sem origem"))

    cur.execute("""
        SELECT count(*)
        FROM despesas_campanha d
        JOIN (
            SELECT DISTINCT ON (sq_candidato, ano_eleicao)
                   sq_candidato, ano_eleicao, politico_id, pessoa_id
            FROM politicos
            WHERE sq_candidato IS NOT NULL AND politico_id IS NOT NULL
              AND ano_eleicao = %s AND uf = %s
            ORDER BY sq_candidato, ano_eleicao, updated_at DESC NULLS LAST, id_tse DESC
        ) p ON p.sq_candidato = d.sq_candidato AND p.ano_eleicao = d.ano_eleicao
        WHERE d.ano_eleicao = %s AND d.uf = %s AND d.origem_arquivo = %s
          AND (d.politico_id IS DISTINCT FROM p.politico_id
               OR d.pessoa_id IS DISTINCT FROM p.pessoa_id)
    """, (ano, uf, ano, uf, bronze_nome))
    identidade_divergente = cur.fetchone()[0]
    resultados.append(gate("IDENTIDADE_NAO_DIVERGE", identidade_divergente == 0, f"{identidade_divergente} divergências sq_candidato+ano"))

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
        ), matches AS (
            SELECT DISTINCT d.linha_hash
            FROM despesas_campanha d
            JOIN sancoes s
              ON s.documento = d.fornecedor_cnpj_cpf
             AND d.data_despesa BETWEEN s.data_inicio AND s.data_fim
            WHERE d.ano_eleicao = %s AND d.uf = %s AND d.origem_arquivo = %s
        )
        SELECT count(*)
        FROM despesas_campanha d
        LEFT JOIN matches m ON m.linha_hash = d.linha_hash
        WHERE d.ano_eleicao = %s AND d.uf = %s AND d.origem_arquivo = %s
          AND d.status_lneg IS DISTINCT FROM
              CASE WHEN m.linha_hash IS NOT NULL THEN 'MATCH' ELSE 'OK' END
    """, (ano, uf, bronze_nome, ano, uf, bronze_nome))
    sancao_divergente = cur.fetchone()[0]
    resultados.append(gate("SANCAO_TEMPORAL_REPRODUZIVEL", sancao_divergente == 0, f"{sancao_divergente} divergências"))
    aprovado = all(resultados)
    relatorio = {
        "status": "APROVADO" if aprovado else "REPROVADO",
        "todos_gates_passaram": aprovado,
        "ano_eleicao": ano,
        "uf": uf,
        "arquivo_prata": arquivo.name,
        "arquivo_bronze": bronze_nome,
        "sha256_prata": sha256(arquivo),
        "total_registros": prata["total"],
        "soma_valores": str(prata["soma"]),
        "total_gates": len(resultados),
        "gates_aprovados": sum(resultados),
        "verificado_em": datetime.now(timezone.utc).isoformat(),
    }
    report_path = REPORT_DIR / f"despesas_{ano}_{uf}_verificado.json"
    report_path.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📄 Relatório: {report_path}")
    return resultados, relatorio


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent V bloqueante — TSE despesas")
    parser.add_argument("--prata")
    parser.add_argument("--todos", action="store_true")
    args = parser.parse_args()
    arquivos = [Path(args.prata)] if args.prata else sorted(PRATA_DIR.glob("*_prata.jsonl.gz"))
    if not arquivos:
        print("❌ Nenhuma Prata encontrada")
        return 1

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    resultados: list[bool] = []
    try:
        for arquivo in arquivos:
            gates, _ = verificar_arquivo(cur, arquivo)
            resultados.extend(gates)
    finally:
        cur.close(); conn.close()
    if all(resultados):
        print("\n✅ AGENT V: TODOS OS GATES PASSARAM — lote liberado")
        return 0
    print(f"\n❌ AGENT V: {sum(not item for item in resultados)} gate(s) falharam — lote BLOQUEADO")
    return 1


if __name__ == "__main__":
    sys.exit(main())
