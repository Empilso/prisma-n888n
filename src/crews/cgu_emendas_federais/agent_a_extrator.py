#!/usr/bin/env python3
"""Agent A — Extrator CGU Emendas Federais: ZIP único CGU → Bronze JSON por ano

Fonte confirmada (sem token/API, histórico completo 2014-2026):
    https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares/EmendasParlamentares.zip

O ZIP contém 3 CSVs (latin-1, separador ;):
  - EmendasParlamentares.csv            → 1 linha por codigo_emenda (grão da tabela destino)
  - EmendasParlamentares_PorFavorecido.csv → 1 linha por (emenda, favorecido); usado só pra
    resolver cnpj_favorecido via agregação no Agent B (fora de escopo aqui)
  - EmendasParlamentares_Convenios.csv   → fora de escopo desta crew

O `Código da Emenda` embute o ano nos 4 primeiros dígitos (ex: "201534200006" → 2015),
mesmo quando a coluna "Ano da Emenda" existe — usamos a coluna oficial como fonte
de verdade e o prefixo só como fallback de particionamento do PorFavorecido.

Execução:
    python agent_a_extrator.py --ano 2014
    python agent_a_extrator.py --todos
    python agent_a_extrator.py --todos --force
"""
import csv, io, json, zipfile, hashlib, argparse, requests
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR    = BASE_DIR / "data/cgu_emendas_federais/raw"
BRONZE_DIR = BASE_DIR / "data/cgu_emendas_federais/bronze"
RAW_DIR.mkdir(parents=True, exist_ok=True)
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

URL_ZIP = ("https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/"
           "saida/emendas-parlamentares/EmendasParlamentares.zip")

ANO_MIN, ANO_MAX = 2014, 2026


def baixar_zip(force: bool = False) -> Path:
    hoje = datetime.now(timezone.utc).strftime("%Y%m%d")
    zip_path = RAW_DIR / f"EmendasParlamentares_{hoje}.zip"
    if zip_path.exists() and not force:
        print(f"  ♻️  ZIP já baixado hoje: {zip_path.name} (use --force para rebaixar)")
        return zip_path
    print(f"  ⬇️  Baixando {URL_ZIP} ...")
    r = requests.get(URL_ZIP, timeout=180)
    r.raise_for_status()
    zip_path.write_bytes(r.content)
    print(f"  ✅ {len(r.content)/1e6:.1f} MB → {zip_path.name}")
    return zip_path


def _ler_csv_do_zip(zip_path: Path, nome_arquivo: str) -> list[dict]:
    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.read(nome_arquivo)
    texto = None
    for enc in ("latin-1", "cp1252", "utf-8-sig", "utf-8"):
        try:
            texto = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not texto:
        raise RuntimeError(f"Encoding não detectado: {nome_arquivo}")
    reader = csv.DictReader(io.StringIO(texto), delimiter=";")
    return [dict(row) for row in reader]


def _bronze_meta(entidade: str, fonte_arquivo: str, ano: int, registros: list) -> dict:
    payload = json.dumps(registros, ensure_ascii=False)
    return {
        "portal":          "Portal da Transparência — CGU",
        "entidade":        entidade,
        "fonte":           fonte_arquivo,
        "ano":             ano,
        "camada":          "bronze",
        "data_extracao":   datetime.now(timezone.utc).isoformat(),
        "hash_sha256":     hashlib.sha256(payload.encode()).hexdigest(),
        "total_registros": len(registros),
    }


def processar(zip_path: Path, anos: list[int], force: bool) -> None:
    print("  📖 Lendo EmendasParlamentares.csv (principal)...")
    principal = _ler_csv_do_zip(zip_path, "EmendasParlamentares.csv")
    print(f"     {len(principal):,} linhas totais")

    print("  📖 Lendo EmendasParlamentares_PorFavorecido.csv...")
    favorecidos = _ler_csv_do_zip(zip_path, "EmendasParlamentares_PorFavorecido.csv")
    print(f"     {len(favorecidos):,} linhas totais")

    por_ano_principal: dict[int, list] = {}
    for row in principal:
        try:
            ano = int(row.get("Ano da Emenda", "").strip())
        except ValueError:
            continue
        por_ano_principal.setdefault(ano, []).append(row)

    por_ano_favorecido: dict[int, list] = {}
    for row in favorecidos:
        cod = (row.get("Código da Emenda") or "").strip()
        if len(cod) < 4 or not cod[:4].isdigit():
            continue
        ano = int(cod[:4])
        por_ano_favorecido.setdefault(ano, []).append(row)

    ok = 0
    for ano in anos:
        registros_p = por_ano_principal.get(ano, [])
        registros_f = por_ano_favorecido.get(ano, [])
        if not registros_p:
            print(f"  ⚠️  Ano {ano}: nenhum registro em EmendasParlamentares.csv")
            continue

        bronze_p = BRONZE_DIR / f"emendas_federais_{ano}_bronze.json"
        bronze_f = BRONZE_DIR / f"emendas_federais_favorecidos_{ano}_bronze.json"

        if bronze_p.exists() and bronze_f.exists() and not force:
            print(f"  ♻️  Bronze {ano} já existe (use --force para re-extrair)")
            ok += 1
            continue

        with open(bronze_p, "w", encoding="utf-8") as f:
            json.dump({
                "meta": _bronze_meta("emendas_federais", "EmendasParlamentares.csv", ano, registros_p),
                "records": registros_p,
            }, f, ensure_ascii=False)

        with open(bronze_f, "w", encoding="utf-8") as f:
            json.dump({
                "meta": _bronze_meta("emendas_federais", "EmendasParlamentares_PorFavorecido.csv", ano, registros_f),
                "records": registros_f,
            }, f, ensure_ascii=False)

        print(f"  ✅ {ano}: {len(registros_p):,} emendas | {len(registros_f):,} favorecidos → bronze")
        ok += 1

    print(f"\n✅ Agent A concluído: {ok}/{len(anos)} ano(s) processado(s)")


def main():
    parser = argparse.ArgumentParser(description="Agent A — Extrator CGU Emendas Federais")
    parser.add_argument("--ano",   type=int, action="append", help="Ano(s) a processar (pode repetir)")
    parser.add_argument("--todos", action="store_true", help=f"Processa {ANO_MIN}-{ANO_MAX}")
    parser.add_argument("--force", action="store_true", help="Rebaixa o ZIP e reprocessa mesmo se bronze já existe")
    args = parser.parse_args()

    if args.todos:
        anos = list(range(ANO_MIN, ANO_MAX + 1))
    elif args.ano:
        anos = sorted(set(args.ano))
    else:
        parser.print_help()
        return

    print(f"📊 CGU Emendas Federais | Anos: {anos}")
    zip_path = baixar_zip(force=args.force)
    processar(zip_path, anos, force=args.force)


if __name__ == "__main__":
    main()
