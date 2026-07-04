#!/usr/bin/env python3
"""Agent A — Coletor TSE Locais de Votação

Fonte: cdn.tse.jus.br — eleitorado_local_votacao_ATUAL.zip (~42 MB)
Saída: data/tse_locais/raw/eleitorado_local_votacao_ATUAL.csv

Execução:
    python agent_a_coletor.py
    python agent_a_coletor.py --force    # re-baixa mesmo se já existe
"""
import argparse
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR  = BASE_DIR / "data/tse_locais/raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

URL      = "https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitorado/eleitorado_local_votacao_ATUAL.zip"
ZIP_PATH = RAW_DIR / "eleitorado_local_votacao_ATUAL.zip"
CSV_PATH = RAW_DIR / "eleitorado_local_votacao_ATUAL.csv"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def baixar_zip(force: bool = False) -> Path:
    if ZIP_PATH.exists() and not force:
        print(f"✅ ZIP já existe ({ZIP_PATH.stat().st_size / 1_048_576:.1f} MB) — use --force para re-baixar")
        return ZIP_PATH

    print(f"⬇️  Baixando {URL} ...")
    resp = requests.get(URL, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    bar = tqdm(total=total, unit="B", unit_scale=True) if HAS_TQDM and total else None

    with open(ZIP_PATH, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk)
            if bar:
                bar.update(len(chunk))
    if bar:
        bar.close()

    print(f"✅ ZIP salvo: {ZIP_PATH.stat().st_size / 1_048_576:.1f} MB")
    return ZIP_PATH


def extrair_csv(force: bool = False) -> Path:
    if CSV_PATH.exists() and not force:
        print(f"✅ CSV já extraído ({CSV_PATH.stat().st_size / 1_048_576:.1f} MB)")
        return CSV_PATH

    import zipfile
    print("📦 Extraindo CSV...")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        members = zf.namelist()
        csv_member = next((m for m in members if m.endswith(".csv")), members[0])
        zf.extract(csv_member, RAW_DIR)
        extracted = RAW_DIR / csv_member
        if extracted != CSV_PATH:
            extracted.rename(CSV_PATH)

    print(f"✅ CSV extraído: {CSV_PATH.stat().st_size / 1_048_576:.1f} MB")
    return CSV_PATH


def main(force: bool = False):
    print("=" * 60)
    print("TSE LOCAIS DE VOTAÇÃO — Agent A: Coletor")
    print("=" * 60)
    baixar_zip(force)
    extrair_csv(force)
    print("\n✅ Agent A concluído — CSV pronto em:", CSV_PATH)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Re-baixa mesmo se já existe")
    args = ap.parse_args()
    main(args.force)
