#!/usr/bin/env python3
"""Agent A — Extrator CGU Despesas de Emendas: ZIPs mensais → Bronze JSON

Lê os arquivos ZIP mensais de DESPESAS/{ANO}/{AAAAMM}_Despesas.zip,
filtra apenas as linhas vinculadas a emendas parlamentares reais
(descarta "SEM EMENDA" e "Informação do autor não disponível"),
e salva em Bronze JSON com metadados de rastreabilidade.

Estrutura dos ZIPs (47 colunas, latin-1, separador ;):
  Col 32: "Código Autor Emenda"  = codigoEmenda (ex: 202339280004)
  Col 33: "Nome Autor Emenda"    = "CARLA ZAMBELLI / EMENDA 4"
  Col 24: "UF"                   = "SP"
  Col 25: "Município"            = "SAO PAULO"
  Cols 42-47: valores R$

Execução:
    python agent_a_extrator.py --ano 2025
    python agent_a_extrator.py --ano 2026
    python agent_a_extrator.py --todos
    python agent_a_extrator.py --todos --force
"""
import csv, io, json, zipfile, hashlib, argparse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DESPESAS_DIR = BASE_DIR / "DESPESAS"
BRONZE_DIR   = BASE_DIR / "data/cgu_docs_emendas/bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

# Valores que indicam "sem emenda parlamentar"
SEM_EMENDA = {"SEM EMENDA", "INFORMAÇÃO DO AUTOR NÃO DISPONÍVEL",
               "INFORMACAO DO AUTOR NAO DISPONIVEL", ""}

# Mapeamento de índice → nome semântico (base-0)
COL_IDX = {
    "ano_mes":              0,
    "cod_orgao_superior":   1,
    "orgao_superior":       2,
    "cod_orgao_sub":        3,
    "orgao_subordinado":    4,
    "cod_ug":               5,
    "unidade_gestora":      6,
    "cod_gestao":           7,
    "gestao":               8,
    "cod_uo":               9,
    "unidade_orcamentaria": 10,
    "cod_funcao":           11,
    "funcao":               12,
    "cod_subfuncao":        13,
    "subfuncao":            14,
    "cod_programa":         15,
    "programa":             16,
    "cod_acao":             17,
    "acao":                 18,
    "cod_plano_orc":        19,
    "plano_orcamentario":   20,
    "cod_prog_gov":         21,
    "programa_governo":     22,
    "uf":                   23,
    "municipio":            24,
    "cod_subtitulo":        25,
    "subtitulo":            26,
    "cod_localizador":      27,
    "localizador":          28,
    "sigla_localizador":    29,
    "desc_localizador":     30,
    "codigo_autor_emenda":  31,
    "nome_autor_emenda":    32,
    "cod_cat_economica":    33,
    "categoria_economica":  34,
    "cod_grupo_despesa":    35,
    "grupo_despesa":        36,
    "cod_elemento":         37,
    "elemento_despesa":     38,
    "cod_modalidade":       39,
    "modalidade_despesa":   40,
    "valor_empenhado":      41,
    "valor_liquidado":      42,
    "valor_pago":           43,
    "valor_resto_inscrito": 44,
    "valor_resto_cancelado":45,
    "valor_resto_pago":     46,
}


def limpar(v: str) -> str:
    return v.strip().strip('"') if v else ""


def ler_zip(zip_path: Path) -> list[dict]:
    """Lê o ZIP mensal e retorna apenas linhas com emenda parlamentar real."""
    rows_emenda = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csvs:
                print(f"  ⚠️  Nenhum CSV em {zip_path.name}")
                return []
            nome_csv = csvs[0]
            raw = zf.read(nome_csv)

        # detecta encoding
        texto = None
        for enc in ("latin-1", "cp1252", "utf-8-sig", "utf-8"):
            try:
                texto = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not texto:
            print(f"  ❌ Encoding não detectado: {zip_path.name}")
            return []

        reader = csv.reader(io.StringIO(texto), delimiter=";")
        header = next(reader, None)
        if not header:
            return []

        total = sem_emenda = 0
        for row in reader:
            total += 1
            if len(row) < 47:
                continue
            codigo = limpar(row[31])
            nome   = limpar(row[32]).upper()
            if not codigo or codigo.upper() in SEM_EMENDA or nome in SEM_EMENDA:
                sem_emenda += 1
                continue

            record = {k: limpar(row[i]) for k, i in COL_IDX.items() if i < len(row)}
            rows_emenda.append(record)

        print(f"  📊 {zip_path.name}: {total:,} total | {len(rows_emenda):,} com emenda | {sem_emenda:,} sem emenda")
        return rows_emenda

    except zipfile.BadZipFile:
        print(f"  ❌ ZIP corrompido: {zip_path.name}")
        return []


def processar_zip(zip_path: Path, force: bool = False) -> Path | None:
    ano_mes = zip_path.stem.replace("_Despesas", "").replace("_despesas", "")
    bronze_path = BRONZE_DIR / f"despesas_emendas_{ano_mes}_bronze.json"

    if bronze_path.exists() and not force:
        print(f"  ♻️  Bronze já existe: {bronze_path.name} (use --force para re-extrair)")
        return bronze_path

    rows = ler_zip(zip_path)
    if not rows:
        return None

    payload = json.dumps(rows, ensure_ascii=False)
    sha256  = hashlib.sha256(payload.encode()).hexdigest()
    bronze  = {
        "meta": {
            "portal":          "Portal da Transparência — CGU",
            "entidade":        "emendas_execucao_orcamentaria",
            "fonte":           "Despesas Execução Mensal",
            "ano_mes":         ano_mes,
            "camada":          "bronze",
            "data_extracao":   datetime.now(timezone.utc).isoformat(),
            "hash_sha256":     sha256,
            "total_registros": len(rows),
            "zip_origem":      zip_path.name,
        },
        "records": rows,
    }
    with open(bronze_path, "w", encoding="utf-8") as f:
        json.dump(bronze, f, ensure_ascii=False)
    print(f"  ✅ Bronze: {len(rows):,} registros → {bronze_path.name}")
    return bronze_path


def listar_zips(anos: list[int]) -> list[Path]:
    zips = []
    for ano in anos:
        pasta = DESPESAS_DIR / str(ano)
        if not pasta.exists():
            print(f"  ⚠️  Pasta não encontrada: {pasta}")
            continue
        found = sorted(pasta.glob("*.zip"))
        print(f"  📁 {pasta}: {len(found)} arquivo(s)")
        zips.extend(found)
    return zips


def main():
    parser = argparse.ArgumentParser(description="Agent A — Extrator Despesas de Emendas")
    parser.add_argument("--ano",   type=int, action="append", help="Ano(s) a processar (pode repetir: --ano 2025 --ano 2026)")
    parser.add_argument("--todos", action="store_true", help="Processa todos os anos disponíveis em DESPESAS/")
    parser.add_argument("--force", action="store_true", help="Re-extrai mesmo se Bronze já existe")
    args = parser.parse_args()

    if args.todos:
        anos = sorted(int(p.name) for p in DESPESAS_DIR.iterdir() if p.is_dir() and p.name.isdigit())
    elif args.ano:
        anos = sorted(set(args.ano))
    else:
        parser.print_help()
        return

    print(f"📊 CGU Despesas de Emendas | Anos: {anos}")
    print(f"📁 Fonte: {DESPESAS_DIR}")

    zips = listar_zips(anos)
    if not zips:
        print("❌ Nenhum ZIP encontrado.")
        return

    ok = erros = 0
    for zip_path in zips:
        result = processar_zip(zip_path, force=args.force)
        if result:
            ok += 1
        else:
            erros += 1

    print(f"\n✅ Agent A concluído: {ok} bronze(s) gerado(s) | {erros} falha(s)")


if __name__ == "__main__":
    main()
