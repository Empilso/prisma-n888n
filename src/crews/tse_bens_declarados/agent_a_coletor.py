#!/usr/bin/env python3
"""Agent A — Coletor TSE Bens Declarados: Download ZIP → Bronze JSON por UF

ZIP único nacional por ano, já vem separado em 1 CSV por UF (+ 1 CSV BRASIL
agregado, que é ignorado — processamos por UF pra bater com o padrão das
outras crews TSE). Formato latin-1, separador ';', estável 2008-2024
(só o nome da coluna de ordem muda entre anos antigos e modernos).
"""
import csv, json, hashlib, zipfile, io, argparse, re
from pathlib import Path
from datetime import datetime, timezone

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/tse_bens_declarados"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

ANOS_DISPONIVEIS = [2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024]
URL_TPL = "https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_{ano}.zip"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def baixar_zip(url: str, destino: Path) -> None:
    print(f"  ⬇️  Baixando {url.split('/')[-1]}...")
    resp = requests.get(url, stream=True, timeout=180)
    resp.raise_for_status()
    total = int(resp.headers.get('content-length', 0))
    bar = tqdm(total=total, unit='B', unit_scale=True) if HAS_TQDM and total else None
    with open(destino, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            if bar:
                bar.update(len(chunk))
    if bar:
        bar.close()


def ler_arquivo(data: bytes) -> list[dict]:
    texto = data.decode('latin-1', errors='replace')
    reader = csv.DictReader(io.StringIO(texto), delimiter=';')
    return list(reader)


def salvar_bronze(ano: int, uf: str, rows: list[dict]) -> None:
    out = BRONZE_DIR / f"bens_{ano}_{uf}_bronze.json"
    if out.exists():
        print(f"  ♻️  Bronze já existe: {out.name}"); return
    payload = json.dumps(rows, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    bronze  = {
        'meta': {
            'portal':          'TSE — Bens de Candidatos',
            'entidade':        'bens_declarados',
            'ano_eleicao':     ano,
            'uf':              uf,
            'camada':          'bronze',
            'data_extracao':   datetime.now(timezone.utc).isoformat(),
            'hash_sha256':     sha256,
            'total_registros': len(rows),
            'hash_algoritmo':  'SHA256',
        },
        'records': rows,
    }
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(rows):>6} registros → {out.name}")


def extrair_zip_nacional(ano: int, zip_path: Path, ufs_filtro: list[str] | None) -> None:
    """Extrai Bronze de ZIP único nacional, processando um CSV de UF por vez."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            arquivos = sorted([
                n for n in zf.namelist()
                if re.search(r'bem_candidato', n, re.IGNORECASE)
                and n.endswith('.csv')
                and 'brasil' not in n.lower()
            ])
            if not arquivos:
                print(f"  ⚠️  Nenhum arquivo de bens de candidatos em {zip_path.name}")
                return

            for nome in arquivos:
                m = re.search(r'_([A-Z]{2})\.csv$', nome, re.IGNORECASE)
                uf_arquivo = m.group(1).upper() if m else None

                if ufs_filtro and uf_arquivo and uf_arquivo not in ufs_filtro:
                    continue

                if uf_arquivo:
                    out = BRONZE_DIR / f"bens_{ano}_{uf_arquivo}_bronze.json"
                    if out.exists():
                        print(f"  ♻️  Bronze já existe: {out.name}"); continue

                print(f"  📄 Processando {nome}...")
                data = zf.read(nome)
                rows = ler_arquivo(data)
                del data

                uf = uf_arquivo or 'BR'
                salvar_bronze(ano, uf, rows)
                del rows

    except zipfile.BadZipFile:
        print(f"  ❌ ZIP corrompido: {zip_path.name}")


def processar_ano(ano: int, ufs_filtro: list[str] | None) -> None:
    url = URL_TPL.format(ano=ano)
    zip_path = RAW_DIR / f"bens_{ano}.zip"

    if zip_path.exists():
        try:
            zipfile.ZipFile(zip_path).close()
            print(f"  ♻️  ZIP já existe: {zip_path.name}")
        except zipfile.BadZipFile:
            print(f"  ⚠️  ZIP corrompido, re-baixando: {zip_path.name}")
            zip_path.unlink()

    if not zip_path.exists():
        try:
            baixar_zip(url, zip_path)
            print(f"  ✅ ZIP salvo: {zip_path.name}")
        except Exception as e:
            print(f"  ❌ Falha no download {ano}: {e}"); return

    extrair_zip_nacional(ano, zip_path, ufs_filtro)


def main():
    parser = argparse.ArgumentParser(description='Agent A — Coletor TSE Bens Declarados')
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--ano',   type=int, choices=ANOS_DISPONIVEIS)
    grp.add_argument('--todos', action='store_true')
    parser.add_argument('--ufs', nargs='+', metavar='UF')
    args = parser.parse_args()

    anos = ANOS_DISPONIVEIS if args.todos else [args.ano]
    ufs  = [u.upper() for u in args.ufs] if args.ufs else None

    print("🌎 Todos os estados" if not ufs else f"🔍 UFs: {', '.join(ufs)}")

    for ano in anos:
        print(f"\n📅 Ano: {ano}")
        processar_ano(ano, ufs)

    print("\n✅ Agent A concluído.")

if __name__ == '__main__':
    main()
