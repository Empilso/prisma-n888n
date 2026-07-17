#!/usr/bin/env python3
"""Agent A — extrai despesas contratadas dos ZIPs TSE para Bronze CSV.GZ.

Os mesmos ZIPs nacionais já usados por `tse_receitas_campanha` contêm as
despesas. O Bronze preserva o CSV original, apenas recomprimido por UF.
"""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
SOURCE_RAW_DIR = BASE_DIR / "data/tse_receitas_campanha/raw"
DATA_DIR = BASE_DIR / "data/tse_despesas_campanha"
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

ANOS = (2014, 2016, 2018, 2020, 2022, 2024)
UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG",
       "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR",
       "RS", "SC", "SE", "SP", "TO")


def _uf_do_membro(ano: int, nome: str) -> str | None:
    patterns = {
        2014: r"despesas_candidatos_2014_([A-Z]{2})\.txt$",
        2016: r"despesas_candidatos_prestacao_contas_final_2016_([A-Z]{2})\.txt$",
    }
    pattern = patterns.get(ano, rf"despesas_contratadas_candidatos_{ano}_([A-Z]{{2}})\.csv$")
    match = re.search(pattern, nome, re.IGNORECASE)
    return match.group(1).upper() if match else None


def extrair_ano(ano: int, ufs: set[str]) -> None:
    zip_path = SOURCE_RAW_DIR / f"receitas_{ano}.zip"
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP compartilhado não encontrado: {zip_path}")

    with zipfile.ZipFile(zip_path) as zf:
        membros = [(nome, _uf_do_membro(ano, nome)) for nome in zf.namelist()]
        membros = [(nome, uf) for nome, uf in membros if uf and uf in ufs]
        encontrados = {uf for _, uf in membros}
        faltantes = sorted(ufs - encontrados)
        if faltantes:
            print(f"⚠️ {ano}: UFs sem arquivo de despesas: {', '.join(faltantes)}")

        for nome, uf in sorted(membros, key=lambda item: item[1]):
            destino = BRONZE_DIR / f"despesas_{ano}_{uf}_bronze.csv.gz"
            meta_path = destino.with_suffix(".meta.json")
            if destino.exists() and meta_path.exists():
                print(f"♻️ {destino.name}")
                continue

            digest = hashlib.sha256()
            total_bytes = 0
            with zf.open(nome) as origem, gzip.open(destino, "wb", compresslevel=6) as saida:
                while chunk := origem.read(1024 * 1024):
                    digest.update(chunk)
                    total_bytes += len(chunk)
                    saida.write(chunk)

            meta = {
                "portal": "TSE — Prestação de Contas Eleitorais",
                "entidade": "despesas_campanha",
                "tipo": "despesas contratadas de candidatos",
                "ano_eleicao": ano,
                "uf": uf,
                "camada": "bronze",
                "arquivo_origem": nome,
                "zip_origem": zip_path.name,
                "bytes_origem": total_bytes,
                "hash_sha256": digest.hexdigest(),
                "data_extracao": datetime.now(timezone.utc).isoformat(),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✅ {ano}/{uf}: {total_bytes / 1024 / 1024:.1f} MiB → {destino.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent A — TSE despesas de campanha")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ano", type=int, choices=ANOS)
    group.add_argument("--todos", action="store_true")
    parser.add_argument("--ufs", nargs="+", choices=UFS)
    args = parser.parse_args()

    anos = ANOS if args.todos else (args.ano,)
    ufs = set(args.ufs or UFS)
    for ano in anos:
        extrair_ano(ano, ufs)


if __name__ == "__main__":
    main()
