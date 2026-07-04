#!/usr/bin/env python3
"""Agent A — Coletor SIGA-BA Emendas Estaduais: Download CSV → Bronze JSON

Tenta múltiplas URLs do Portal da Transparência da Bahia e SIAFEB.
Período: 2015–2025.

URLs tentadas em ordem:
  1. https://www.transparencia.ba.gov.br/resource?type=emendas&ano={ANO}&output=csv
  2. https://www.transparencia.ba.gov.br/modules/transparencia/submodules/emendas/download?ano={ANO}
  3. https://siafeb.ba.gov.br/siafeb/public/emendas/download?ano={ANO}

Execução:
    python agent_a_coletor.py --ano 2024
    python agent_a_coletor.py --todos
    python agent_a_coletor.py --todos --force
"""
import csv, json, hashlib, io, argparse, warnings, zipfile
from pathlib import Path
from datetime import datetime, timezone

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/siga_ba_emendas"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

ANOS = list(range(2015, 2026))

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; PRISMA888-ETL/1.0; dados publicos)',
    'Accept': 'application/zip,text/csv,application/octet-stream,*/*',
}

# Portal de Dados Abertos BA — CKAN — dataset oficial
CKAN_API   = "https://dados.ba.gov.br/sv/api/3/action/package_show?id=emendas-parlamentares"
CKAN_PAGE  = "https://dados.ba.gov.br/sv/dataset/emendas-parlamentares"
ZIP_HINTS  = ["EmendasParlamentares", "emendas", "parlamentares"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
def baixar_bytes(url: str, timeout: int = 120) -> bytes | None:
    resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, verify=False)
    if resp.status_code != 200:
        return None
    content_type = resp.headers.get('content-type', '').lower()
    # Rejeita HTML puro pequeno (página de erro)
    if 'html' in content_type and len(resp.content) < 10_000:
        return None
    return resp.content


def descobrir_url_zip() -> str | None:
    """Consulta a API CKAN para encontrar a URL do ZIP mais recente."""
    print("  🔍 Consultando CKAN API...")
    try:
        resp = requests.get(CKAN_API, headers=HEADERS, timeout=30, verify=False)
        resp.raise_for_status()
        pkg = resp.json()
        resources = pkg.get('result', {}).get('resources', [])
        for r in resources:
            url = r.get('url', '')
            name = (r.get('name', '') + r.get('url', '')).lower()
            if any(h.lower() in name for h in ZIP_HINTS):
                print(f"  ✅ Recurso encontrado: {r.get('name')} → {url}")
                return url
        # Fallback: primeiro recurso disponível
        if resources:
            url = resources[0].get('url', '')
            print(f"  ⚠️  Usando primeiro recurso: {url}")
            return url
    except Exception as e:
        print(f"  ⚠️  CKAN API falhou: {e}")

    # Fallback: scrape da página HTML
    print("  🔍 Tentando scrape da página do dataset...")
    try:
        import re
        resp = requests.get(CKAN_PAGE, headers=HEADERS, timeout=30, verify=False)
        matches = re.findall(r'href=["\']([^"\']*(?:emendas|parlamentares)[^"\']*\.(?:zip|csv|xlsx))["\']',
                             resp.text, re.IGNORECASE)
        if matches:
            url = matches[0]
            if not url.startswith('http'):
                url = 'https://dados.ba.gov.br' + url
            print(f"  ✅ URL encontrada via scrape: {url}")
            return url
    except Exception as e:
        print(f"  ⚠️  Scrape falhou: {e}")

    return None


def ler_zip(data: bytes) -> tuple[list[dict], str]:
    """Extrai CSV(s) do ZIP. Retorna (rows, nome_arquivo)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(('.csv', '.txt'))]
            if not csvs:
                print(f"  ⚠️  ZIP sem CSV. Conteúdo: {zf.namelist()}")
                return [], ''
            # Pega o maior CSV (dataset principal)
            csvs.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
            nome = csvs[0]
            print(f"  📄 Extraindo: {nome} ({zf.getinfo(nome).file_size / 1024:.0f} KB)")
            raw = zf.read(nome)
            rows = ler_csv_bytes(raw)
            return rows, nome
    except zipfile.BadZipFile:
        # Pode ser CSV direto (não ZIP)
        rows = ler_csv_bytes(data)
        return rows, 'direto.csv'


def ler_csv_bytes(data: bytes) -> list[dict]:
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        for sep in (';', ',', '\t'):
            try:
                texto = data.decode(enc)
                reader = csv.DictReader(io.StringIO(texto), delimiter=sep)
                rows = list(reader)
                if len(rows) > 5 and len(reader.fieldnames or []) > 2:
                    print(f"  📊 {len(rows):,} linhas | enc={enc} sep='{sep}' | colunas: {list(reader.fieldnames or [])[:6]}")
                    return rows
            except Exception:
                continue
    return []


def salvar_bronze(rows: list[dict], fonte_url: str) -> Path:
    """Dataset único — sem separação por ano (o ZIP contém todos os anos)."""
    out = BRONZE_DIR / "emendas_ba_completo_bronze.json"
    payload = json.dumps(rows, ensure_ascii=False)
    sha256 = hashlib.sha256(payload.encode()).hexdigest()
    bronze = {
        'meta': {
            'portal':          'Portal de Dados Abertos BA — CKAN',
            'entidade':        'emendas_estaduais',
            'fonte_url':       fonte_url,
            'camada':          'bronze',
            'data_extracao':   datetime.now(timezone.utc).isoformat(),
            'hash_sha256':     sha256,
            'total_registros': len(rows),
        },
        'records': rows,
    }
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(rows):,} registros → {out.name}")
    return out


def main():
    parser = argparse.ArgumentParser(description='Agent A — Coletor Emendas BA (dados.ba.gov.br)')
    parser.add_argument('--force', action='store_true', help='Re-baixa mesmo se bronze existe')
    # mantém compatibilidade com --todos e --ano mas ignora (dataset é único)
    parser.add_argument('--todos', action='store_true')
    parser.add_argument('--ano',   type=int)
    args = parser.parse_args()

    bronze_path = BRONZE_DIR / "emendas_ba_completo_bronze.json"
    if bronze_path.exists() and not args.force:
        print(f"♻️  Bronze já existe: {bronze_path.name} (use --force para re-baixar)")
        return

    print("💵 Emendas Parlamentares Estaduais BA — Portal de Dados Abertos")

    url_zip = descobrir_url_zip()
    if not url_zip:
        print("❌ Não foi possível encontrar a URL do arquivo. Verifique manualmente:")
        print(f"   {CKAN_PAGE}")
        return

    print(f"\n⬇️  Baixando: {url_zip}")
    raw_path = RAW_DIR / "emendas_ba_completo.zip"
    try:
        data = baixar_bytes(url_zip)
        if not data:
            print("❌ Download falhou (sem conteúdo)"); return
        raw_path.write_bytes(data)
        print(f"  ✅ {len(data) / 1024:.0f} KB baixados")
    except Exception as e:
        print(f"❌ Download falhou: {e}"); return

    rows, nome_csv = ler_zip(data)
    if not rows:
        print(f"❌ Não foi possível extrair linhas do arquivo {nome_csv}"); return

    salvar_bronze(rows, url_zip)
    print("\n✅ Agent A concluído.")

if __name__ == '__main__':
    main()
