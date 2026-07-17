#!/usr/bin/env python3
"""Agent B — normaliza Bronze TSE para Prata JSONL.GZ, em streaming."""
import argparse
import csv
import gzip
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data/tse_despesas_campanha"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for directory in (PRATA_DIR, REJEIT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def chave(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", texto.upper()).strip("_")


def limpar(valor: object) -> str | None:
    texto = str(valor or "").strip()
    return None if texto.upper() in {"", "#NULO", "#NE", "#NULL!", "-1", "-3", "-4"} else texto


def campo(row: dict[str, str], *nomes: str) -> str | None:
    for nome in nomes:
        valor = limpar(row.get(chave(nome)))
        if valor is not None:
            return valor
    return None


def documento(valor: str | None) -> str | None:
    digitos = re.sub(r"\D", "", valor or "")
    return digitos if len(digitos) in (11, 14) else None


def valor_decimal(valor: str | None) -> Decimal | None:
    texto = limpar(valor)
    if texto is None:
        return None
    try:
        numero = Decimal(texto.replace(".", "").replace(",", "."))
        return numero if numero >= 0 else None
    except InvalidOperation:
        return None


def data_br(valor: str | None) -> date | None:
    texto = limpar(valor)
    if texto is None:
        return None
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def normalizar(row: dict[str, str], ano: int, uf: str, origem: str, numero_linha: int) -> tuple[dict | None, str | None]:
    sq_candidato = campo(row, "SQ_CANDIDATO", "Sequencial Candidato")
    valor = valor_decimal(campo(row, "VR_DESPESA_CONTRATADA", "Valor despesa"))
    data_despesa = data_br(campo(row, "DT_DESPESA", "Data da despesa"))
    ano_raw = campo(row, "AA_ELEICAO", "ANO_ELEICAO")
    ano_eleicao = int(ano_raw) if ano_raw and ano_raw.isdigit() else ano

    if not sq_candidato:
        return None, "sq_candidato vazio"
    if valor is None or valor <= 0:
        return None, "registro sem despesa positiva declarada"
    if data_despesa is None:
        return None, "data da despesa inválida"
    if not 2006 <= ano_eleicao <= 2026:
        return None, "ano eleitoral inválido"

    registro = {
        "sq_candidato": sq_candidato,
        "ano_eleicao": ano_eleicao,
        "uf": (campo(row, "SG_UF", "UF") or uf).upper()[:2],
        "cargo": campo(row, "DS_CARGO", "Cargo"),
        "sigla_partido": campo(row, "SG_PARTIDO", "Sigla Partido"),
        "fornecedor_cnpj_cpf": documento(campo(row, "NR_CPF_CNPJ_FORNECEDOR", "CPF/CNPJ do fornecedor")),
        "fornecedor_nome": campo(row, "NM_FORNECEDOR", "Nome do fornecedor"),
        "fornecedor_nome_rfb": campo(row, "NM_FORNECEDOR_RFB", "Nome do fornecedor Receita Federal"),
        "tipo_fornecedor": campo(row, "DS_TIPO_FORNECEDOR"),
        "tipo_despesa": campo(row, "DS_ORIGEM_DESPESA", "Tipo despesa"),
        "descricao": campo(row, "DS_DESPESA", "Descricao da despesa"),
        "valor": str(valor),
        "data_despesa": data_despesa.isoformat(),
        "documento_tipo": campo(row, "DS_TIPO_DOCUMENTO", "Tipo do documento", "Tipo de documento"),
        "documento_numero": campo(row, "NR_DOCUMENTO", "Numero do documento"),
        "tse_despesa_id": campo(row, "SQ_DESPESA"),
        "linha_origem": numero_linha,
        "origem_arquivo": origem,
    }
    material_hash = json.dumps(registro, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    registro["linha_hash"] = hashlib.sha256(material_hash.encode("utf-8")).hexdigest()
    return registro, None


def processar(arquivo: Path) -> None:
    match = re.match(r"despesas_(\d{4})_([A-Z]{2})_bronze\.csv\.gz", arquivo.name)
    if not match:
        raise ValueError(f"Nome Bronze inválido: {arquivo.name}")
    ano, uf = int(match.group(1)), match.group(2)
    prata = PRATA_DIR / f"despesas_{ano}_{uf}_prata.jsonl.gz"
    rejeitados = REJEIT_DIR / f"despesas_{ano}_{uf}_rejeitados.jsonl.gz"
    meta_path = PRATA_DIR / f"despesas_{ano}_{uf}_prata.meta.json"

    validos = rejeitados_total = 0
    soma_valores = Decimal("0")
    data_minima: date | None = None
    data_maxima: date | None = None
    with gzip.open(arquivo, "rt", encoding="latin-1", errors="replace", newline="") as entrada, \
         gzip.open(prata, "wt", encoding="utf-8") as saida, \
         gzip.open(rejeitados, "wt", encoding="utf-8") as saida_rejeitados:
        reader = csv.DictReader(entrada, delimiter=";")
        for numero_linha, row_original in enumerate(reader, start=2):
            row = {chave(k): v for k, v in row_original.items()}
            registro, motivo = normalizar(row, ano, uf, arquivo.name, numero_linha)
            if registro:
                saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
                validos += 1
                soma_valores += Decimal(registro["valor"])
                data_atual = date.fromisoformat(registro["data_despesa"])
                data_minima = data_atual if data_minima is None else min(data_minima, data_atual)
                data_maxima = data_atual if data_maxima is None else max(data_maxima, data_atual)
            else:
                saida_rejeitados.write(json.dumps({
                    "linha": numero_linha,
                    "motivo": motivo,
                    "sq_candidato": campo(row, "SQ_CANDIDATO", "Sequencial Candidato"),
                    "tse_despesa_id": campo(row, "SQ_DESPESA"),
                    "data_original": campo(row, "DT_DESPESA", "Data da despesa"),
                    "valor_original": campo(row, "VR_DESPESA_CONTRATADA", "Valor despesa"),
                }, ensure_ascii=False) + "\n")
                rejeitados_total += 1

    meta_path.write_text(json.dumps({
        "fonte_bronze": arquivo.name,
        "ano_eleicao": ano,
        "uf": uf,
        "total_validos": validos,
        "total_rejeitados": rejeitados_total,
        "total_linhas_dados": validos + rejeitados_total,
        "soma_valores_validos": str(soma_valores),
        "data_minima": data_minima.isoformat() if data_minima else None,
        "data_maxima": data_maxima.isoformat() if data_maxima else None,
        "data_processamento": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {ano}/{uf}: {validos:,} válidos · {rejeitados_total:,} rejeitados")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent B — TSE despesas de campanha")
    parser.add_argument("--bronze")
    parser.add_argument("--todos", action="store_true")
    args = parser.parse_args()
    arquivos = [Path(args.bronze)] if args.bronze else sorted(BRONZE_DIR.glob("*_bronze.csv.gz"))
    if not arquivos:
        raise SystemExit("Nenhum Bronze encontrado")
    for arquivo in arquivos:
        processar(arquivo)


if __name__ == "__main__":
    main()
