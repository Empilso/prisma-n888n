#!/usr/bin/env python3
"""Agent A — Coletor TSE Receitas: Download ZIP → Bronze JSON por UF

Suporta:
  - 2018-2024: ZIP único nacional, arquivos .csv, colunas modernas (SG_UF, VR_RECEITA)
  - 2014:      ZIP único nacional, arquivos .txt, colunas antigas (UF, Valor receita)
  - 2016:      27 ZIPs por UF (extrato_campanha_2016_{UF}.zip), arquivos .txt
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
DATA_DIR   = BASE_DIR / "data/tse_receitas_campanha"
RAW_DIR    = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
for d in (RAW_DIR, BRONZE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# URLs para anos com ZIP único nacional
URLS = {
    2024: "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2024.zip",
    2022: "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2022.zip",
    2020: "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2020.zip",
    2018: "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2018.zip",
    2014: "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_final_2014.zip",
}

# 2016: ZIPs separados por UF
UFS_BR = ['AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT',
          'PA','PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO']
URL_2016_UF = "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/extrato_campanha_2016_{uf}.zip"


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


def col(row: dict, *nomes) -> str:
    for n in nomes:
        if n in row and str(row[n]).strip():
            return str(row[n]).strip()
    return ''


def salvar_bronze(ano: int, uf: str, rows: list[dict]) -> None:
    out = BRONZE_DIR / f"receitas_{ano}_{uf}_bronze.json"
    if out.exists():
        print(f"  ♻️  Bronze já existe: {out.name}"); return
    payload = json.dumps(rows, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    bronze  = {
        'meta': {
            'portal':          'TSE — Prestação de Contas Eleitorais',
            'entidade':        'receitas_campanha',
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
    """Extrai Bronze de ZIP único nacional processando um CSV por vez (baixo uso de memória)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            arquivos = sorted([
                n for n in zf.namelist()
                if re.search(r'receitas?_candidatos', n, re.IGNORECASE)
                and (n.endswith('.csv') or n.endswith('.txt'))
                and 'doador_originario' not in n.lower()
                and 'brasil' not in n.lower()
            ])
            if not arquivos:
                print(f"  ⚠️  Nenhum arquivo de receitas de candidatos em {zip_path.name}")
                return

            for nome in arquivos:
                # Detecta UF pelo nome do arquivo (ex: receitas_candidatos_2024_BA.csv)
                m = re.search(r'_([A-Z]{2})\.(csv|txt)$', nome, re.IGNORECASE)
                uf_arquivo = m.group(1).upper() if m else None

                # Pula se filtro de UF ativo e UF não está na lista
                if ufs_filtro and uf_arquivo and uf_arquivo not in ufs_filtro:
                    continue

                # Pula se Bronze já existe para esta UF
                if uf_arquivo:
                    out = BRONZE_DIR / f"receitas_{ano}_{uf_arquivo}_bronze.json"
                    if out.exists():
                        print(f"  ♻️  Bronze já existe: {out.name}"); continue

                print(f"  📄 Processando {nome}...")

                # Lê e processa linha a linha — sem acumular tudo na memória
                por_uf: dict[str, list[dict]] = {}
                data = zf.read(nome)
                rows = ler_arquivo(data)
                del data  # libera memória imediatamente

                for r in rows:
                    uf = col(r, 'SG_UF', 'SG_UF_CANDIDATO', 'UF').upper()
                    if not uf or len(uf) != 2:
                        continue
                    if ufs_filtro and uf not in ufs_filtro:
                        continue
                    por_uf.setdefault(uf, []).append(r)
                del rows  # libera memória

                for uf, uf_rows in sorted(por_uf.items()):
                    salvar_bronze(ano, uf, uf_rows)
                del por_uf  # libera memória

    except zipfile.BadZipFile:
        print(f"  ❌ ZIP corrompido: {zip_path.name}")


def processar_2016(ufs_filtro: list[str] | None) -> None:
    """2016: baixa e extrai ZIP por UF."""
    ufs = ufs_filtro if ufs_filtro else UFS_BR
    for uf in ufs:
        zip_path = RAW_DIR / f"receitas_2016_{uf}.zip"
        url = URL_2016_UF.format(uf=uf)

        if not zip_path.exists():
            try:
                baixar_zip(url, zip_path)
                print(f"  ✅ ZIP salvo: {zip_path.name}")
            except Exception as e:
                print(f"  ❌ Falha {uf}: {e}"); continue
        else:
            print(f"  ♻️  ZIP já existe: {zip_path.name}")

        # Verifica integridade
        try:
            with zipfile.ZipFile(zip_path) as zf:
                arquivos = [
                    n for n in zf.namelist()
                    if re.search(r'receita', n, re.IGNORECASE)
                    and (n.endswith('.csv') or n.endswith('.txt'))
                    and 'partido' not in n.lower()
                ]
                if not arquivos:
                    print(f"  ⚠️  Sem receitas de candidatos em {zip_path.name}"); continue
                rows = []
                for nome in arquivos:
                    rows.extend(ler_arquivo(zf.read(nome)))
                salvar_bronze(2016, uf, rows)
        except zipfile.BadZipFile:
            print(f"  ❌ ZIP corrompido: {zip_path.name}")
            zip_path.unlink()  # Remove para re-baixar na próxima execução


def processar_ano(ano: int, ufs_filtro: list[str] | None) -> None:
    if ano == 2016:
        processar_2016(ufs_filtro)
        return

    url = URLS.get(ano)
    if not url:
        print(f"⚠️  Sem URL para {ano}"); return

    zip_path = RAW_DIR / f"receitas_{ano}.zip"

    # Verifica se ZIP existente está íntegro
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
    anos_disponiveis = sorted(list(URLS.keys()) + [2016])
    parser = argparse.ArgumentParser(description='Agent A — Coletor TSE Receitas')
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--ano',   type=int, choices=anos_disponiveis)
    grp.add_argument('--todos', action='store_true')
    parser.add_argument('--ufs', nargs='+', metavar='UF')
    args = parser.parse_args()

    anos = anos_disponiveis if args.todos else [args.ano]
    ufs  = [u.upper() for u in args.ufs] if args.ufs else None

    print("🌎 Todos os estados" if not ufs else f"🔍 UFs: {', '.join(ufs)}")

    for ano in anos:
        print(f"\n📅 Ano: {ano}")
        processar_ano(ano, ufs)

    print("\n✅ Agent A concluído.")

if __name__ == '__main__':
    main()
