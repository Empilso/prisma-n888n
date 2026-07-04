#!/usr/bin/env python3
"""Agent A — Coletor CGU Lista Negra: Download ZIP → Bronze JSON

Fontes:
  CEIS  — Cadastro de Empresas Inidôneas e Suspensas
  CNEP  — Cadastro Nacional de Empresas Punidas
  CEPIM — Cadastro de Entidades Privadas Sem Fins Lucrativos Impedidas

Portal: https://portaldatransparencia.gov.br/download-de-dados/
URL:    https://portaldatransparencia.gov.br/download-de-dados/{fonte}/{YYYYMMDD}

O agent tenta datas recentes automaticamente (últimos 60 dias úteis).

Execução:
    python agent_a_coletor.py --fonte CEIS
    python agent_a_coletor.py --fonte todos
    python agent_a_coletor.py --fonte CNEP --force
"""
import csv, json, hashlib, zipfile, io, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/cgu_lista_negra"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

FONTES = ['CEIS', 'CNEP', 'CEPIM']
BASE_URL = "https://portaldatransparencia.gov.br/download-de-dados/{fonte}/{data}"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; PRISMA888-ETL/1.0; dados publicos)',
    'Accept': 'application/zip,application/octet-stream,*/*',
}


def datas_recentes(dias: int = 90) -> list[str]:
    """Gera lista de datas recentes no formato YYYYMMDD (dias úteis aprox)."""
    hoje = datetime.now().date()
    datas = []
    d = hoje
    for _ in range(dias):
        datas.append(d.strftime('%Y%m%d'))
        d -= timedelta(days=1)
    return datas


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
def tentar_download(url: str, destino: Path) -> bool:
    """Baixa o ZIP se disponível. Retorna True se bem-sucedido."""
    resp = requests.get(url, headers=HEADERS, stream=True, timeout=120)
    if resp.status_code == 404:
        return False
    resp.raise_for_status()

    content_type = resp.headers.get('content-type', '')
    if 'html' in content_type.lower():
        return False

    total = int(resp.headers.get('content-length', 0))
    bar = tqdm(total=total, unit='B', unit_scale=True, desc=destino.name) if HAS_TQDM and total else None
    with open(destino, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            if bar:
                bar.update(len(chunk))
    if bar:
        bar.close()

    try:
        zipfile.ZipFile(destino).close()
        return True
    except zipfile.BadZipFile:
        destino.unlink(missing_ok=True)
        return False


def encontrar_e_baixar(fonte: str, force: bool = False) -> tuple[Path | None, str | None]:
    """Tenta datas recentes até encontrar arquivo disponível. Retorna (zip_path, data_ref)."""
    for data_str in datas_recentes(90):
        zip_path = RAW_DIR / f"{fonte.lower()}_{data_str}.zip"
        if zip_path.exists() and not force:
            try:
                zipfile.ZipFile(zip_path).close()
                print(f"  ♻️  ZIP já existe: {zip_path.name}")
                return zip_path, data_str
            except zipfile.BadZipFile:
                zip_path.unlink()

        url = BASE_URL.format(fonte=fonte.lower(), data=data_str)
        try:
            ok = tentar_download(url, zip_path)
            if ok:
                print(f"  ✅ Download {fonte} ({data_str}): {zip_path.stat().st_size / 1_048_576:.1f} MB")
                return zip_path, data_str
        except Exception:
            continue

    return None, None


def ler_csv_do_zip(zip_path: Path) -> list[dict]:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith('.csv')]
            if not csvs:
                print(f"  ⚠️  Nenhum CSV em {zip_path.name}")
                return []
            nome_csv = csvs[0]
            print(f"  📄 Lendo {nome_csv}...")
            data = zf.read(nome_csv)
            for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
                try:
                    texto = data.decode(enc)
                    reader = csv.DictReader(io.StringIO(texto), delimiter=';')
                    rows = list(reader)
                    if not rows:
                        reader = csv.DictReader(io.StringIO(texto), delimiter=',')
                        rows = list(reader)
                    print(f"  📊 {len(rows):,} linhas ({enc})")
                    return rows
                except (UnicodeDecodeError, csv.Error):
                    continue
            return []
    except zipfile.BadZipFile:
        print(f"  ❌ ZIP corrompido: {zip_path.name}")
        return []


def salvar_bronze(fonte: str, data_ref: str, rows: list[dict]) -> Path:
    out = BRONZE_DIR / f"{fonte.lower()}_{data_ref}_bronze.json"
    payload = json.dumps(rows, ensure_ascii=False)
    sha256 = hashlib.sha256(payload.encode()).hexdigest()
    bronze = {
        'meta': {
            'portal':          f'CGU — {fonte}',
            'entidade':        'lista_negra_governo',
            'fonte':           fonte,
            'data_referencia': data_ref,
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


def processar_fonte(fonte: str, force: bool = False) -> None:
    bronze_existente = sorted(BRONZE_DIR.glob(f"{fonte.lower()}_*_bronze.json"))
    if bronze_existente and not force:
        print(f"  ♻️  Bronze já existe: {bronze_existente[-1].name} (use --force para re-baixar)")
        return

    print(f"\n🔍 Buscando arquivo mais recente de {fonte}...")
    zip_path, data_ref = encontrar_e_baixar(fonte, force)
    if not zip_path:
        print(f"  ❌ Não foi possível baixar {fonte} nos últimos 90 dias")
        return

    rows = ler_csv_do_zip(zip_path)
    if not rows:
        return

    salvar_bronze(fonte, data_ref, rows)


def main():
    parser = argparse.ArgumentParser(description='Agent A — Coletor CGU Lista Negra')
    parser.add_argument('--fonte', choices=FONTES + ['todos'], required=True)
    parser.add_argument('--force', action='store_true', help='Re-baixa mesmo se já existe')
    args = parser.parse_args()

    fontes = FONTES if args.fonte == 'todos' else [args.fonte.upper()]
    print(f"🚫 CGU Lista Negra | Fontes: {fontes}")

    for fonte in fontes:
        print(f"\n📋 {fonte}")
        processar_fonte(fonte, force=args.force)

    print("\n✅ Agent A concluído.")

if __name__ == '__main__':
    main()
