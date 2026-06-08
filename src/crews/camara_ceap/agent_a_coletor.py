#!/usr/bin/env python3
"""Agent A — Coletor Câmara CEAP: Download ZIP → Bronze JSON por Ano

Portal:  https://www.camara.leg.br/transparencia/gastos-parlamentares
Formato: CSV nacional por ano (todos os 513 deputados), separador ';', encoding latin-1

URL padrão: https://www.camara.leg.br/cotas/Ano-{ANO}.csv.zip

Período coberto: 2015–2025 (10 anos de CEAP federal)
Volume estimado: 300K–800K linhas/ano → 3–8 M registros total

Execução:
    python agent_a_coletor.py --ano 2024
    python agent_a_coletor.py --todos
    python agent_a_coletor.py --todos --force   # re-baixa mesmo se ZIP existe

Saída:
    data/camara_ceap/bronze/ceap_{ANO}_bronze.json
"""
import csv, json, hashlib, zipfile, io, argparse
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
DATA_DIR   = BASE_DIR / "data/camara_ceap"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

ANOS = list(range(2015, 2026))  # 2015–2025

def url_para_ano(ano: int) -> str:
    return f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def baixar_zip(url: str, destino: Path) -> None:
    print(f"  ⬇️  Baixando {url.split('/')[-1]}...")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get('content-length', 0))
    bar = tqdm(total=total, unit='B', unit_scale=True) if HAS_TQDM and total else None
    with open(destino, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            if bar:
                bar.update(len(chunk))
    if bar:
        bar.close()
    print(f"  ✅ Salvo: {destino.name} ({destino.stat().st_size / 1_048_576:.1f} MB)")


def ler_csv_do_zip(zip_path: Path) -> list[dict]:
    """Lê o CSV dentro do ZIP (encoding latin-1, sep ;)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith('.csv')]
            if not csvs:
                print(f"  ⚠️  Nenhum CSV encontrado em {zip_path.name}")
                return []
            nome_csv = csvs[0]
            print(f"  📄 Lendo {nome_csv}...")
            data = zf.read(nome_csv)
            # Tenta UTF-8 primeiro, depois latin-1
            for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
                try:
                    texto = data.decode(enc)
                    reader = csv.DictReader(io.StringIO(texto), delimiter=';')
                    rows = list(reader)
                    print(f"  📊 {len(rows):,} linhas ({enc})")
                    return rows
                except (UnicodeDecodeError, csv.Error):
                    continue
            print(f"  ❌ Falha ao decodificar {nome_csv}")
            return []
    except zipfile.BadZipFile:
        print(f"  ❌ ZIP corrompido: {zip_path.name}")
        return []


def salvar_bronze(ano: int, rows: list[dict]) -> Path:
    out = BRONZE_DIR / f"ceap_{ano}_bronze.json"
    payload = json.dumps(rows, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    bronze  = {
        'meta': {
            'portal':          'Câmara Federal — Gastos Parlamentares (CEAP)',
            'entidade':        'camara_verbas_ceap',
            'ano':             ano,
            'camada':          'bronze',
            'data_extracao':   datetime.now(timezone.utc).isoformat(),
            'hash_sha256':     sha256,
            'total_registros': len(rows),
        },
        'records': rows,
    }
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(rows):>8,} registros → {out.name}")
    return out


def processar_ano(ano: int, force: bool = False) -> None:
    bronze_path = BRONZE_DIR / f"ceap_{ano}_bronze.json"
    if bronze_path.exists() and not force:
        print(f"  ♻️  Bronze já existe: {bronze_path.name} (use --force para re-baixar)")
        return

    zip_path = RAW_DIR / f"ceap_{ano}.zip"

    if zip_path.exists() and not force:
        try:
            zipfile.ZipFile(zip_path).close()
            print(f"  ♻️  ZIP já existe: {zip_path.name}")
        except zipfile.BadZipFile:
            print(f"  ⚠️  ZIP corrompido, re-baixando...")
            zip_path.unlink()

    if not zip_path.exists():
        try:
            baixar_zip(url_para_ano(ano), zip_path)
        except Exception as e:
            print(f"  ❌ Falha no download {ano}: {e}")
            return

    rows = ler_csv_do_zip(zip_path)
    if not rows:
        return

    salvar_bronze(ano, rows)


def main():
    parser = argparse.ArgumentParser(description='Agent A — Coletor Câmara CEAP')
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--ano',   type=int, choices=ANOS, help='Ano específico')
    grp.add_argument('--todos', action='store_true',    help='Todos os anos (2015–2025)')
    parser.add_argument('--force', action='store_true', help='Re-baixa mesmo se já existe')
    args = parser.parse_args()

    anos = ANOS if args.todos else [args.ano]
    print(f"📅 Anos: {anos[0]}–{anos[-1]} ({len(anos)} anos)")

    for ano in anos:
        print(f"\n📅 {ano}")
        processar_ano(ano, force=args.force)

    print("\n✅ Agent A concluído.")

if __name__ == '__main__':
    main()
