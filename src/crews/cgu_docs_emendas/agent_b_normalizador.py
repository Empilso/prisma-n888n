#!/usr/bin/env python3
"""Agent B — Normalizador: Bronze → Prata

Processa os registros de execução orçamentária de emendas:
  - Normaliza valores monetários (vírgula → ponto)
  - Classifica tipo de emenda (Individual / Bancada / Comissão / Relator)
  - Resolve município → municipio_ibge via tabela municipios (PostgreSQL)
  - Computa id_registro = SHA256(codigo_emenda|ano_mes|cod_orgao|cod_acao|uf|municipio)
  - Rejeita registros sem codigo_emenda válido

Execução:
    python agent_b_normalizador.py --bronze despesas_emendas_202501_bronze.json
    python agent_b_normalizador.py --todos
"""
import json, re, hashlib, argparse, unicodedata
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/cgu_docs_emendas/bronze"
PRATA_DIR  = BASE_DIR / "data/cgu_docs_emendas/prata"
REJEIT_DIR = BASE_DIR / "data/cgu_docs_emendas/rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB = dict(host="localhost", port=5432, dbname="prisma_data",
          user="postgres", password=DB_PASSWORD)

SEM_EMENDA = {"SEM EMENDA", "INFORMAÇÃO DO AUTOR NÃO DISPONÍVEL",
               "INFORMACAO DO AUTOR NAO DISPONIVEL", ""}


def norm(s: str) -> str:
    """Remove acentos e converte para uppercase para comparação."""
    nfd = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").upper().strip()


def parse_valor(v: str) -> float | None:
    """'1.234.567,89' → 1234567.89"""
    if not v or v.strip() in ("", "-1"):
        return None
    try:
        return float(v.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def tipo_emenda(codigo: str, nome: str) -> str:
    nome_up = nome.upper()
    if "BANCADA" in nome_up:
        return "BANCADA"
    if "COM." in nome_up or "COMISSAO" in nome_up or "COMISSÃO" in nome_up:
        return "COMISSAO"
    if "RELATOR" in nome_up:
        return "RELATOR"
    # código de emenda individual tem 12 dígitos (aaaa + cpf_parl + seq)
    if re.match(r"^\d{12}$", codigo.strip()):
        return "INDIVIDUAL"
    return "OUTRO"


def carregar_cache_municipios() -> dict:
    """Carrega dict (norm_nome, uf) → id_ibge do banco."""
    cache = {}
    try:
        conn = psycopg2.connect(**DB)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id_ibge, nome, uf FROM municipios")
        for r in cur.fetchall():
            key = (norm(r["nome"]), r["uf"].upper().strip())
            cache[key] = r["id_ibge"]
        conn.close()
        print(f"  🏙️  Cache municípios: {len(cache):,} entradas")
    except Exception as e:
        print(f"  ⚠️  Não foi possível carregar cache de municípios: {e}")
    return cache


def resolver_municipio(nome: str, uf: str, cache: dict) -> str | None:
    if not nome or not uf:
        return None
    key = (norm(nome), uf.upper().strip())
    return cache.get(key)


def id_registro(r: dict) -> str:
    partes = "|".join([
        r.get("codigo_emenda") or "",
        r.get("ano_mes") or "",
        r.get("cod_orgao_superior") or "",
        r.get("cod_acao") or "",
        r.get("uf") or "",
        r.get("municipio") or "",
    ])
    return hashlib.sha256(partes.encode()).hexdigest()


def normalizar_registro(raw: dict, cache_muni: dict) -> dict | None:
    codigo = raw.get("codigo_autor_emenda", "").strip()
    nome   = raw.get("nome_autor_emenda", "").strip()

    if not codigo or codigo.upper() in SEM_EMENDA:
        return None

    municipio_ibge = resolver_municipio(raw.get("municipio", ""), raw.get("uf", ""), cache_muni)

    r = {
        "codigo_emenda":        codigo,
        "nome_autor_emenda":    nome,
        "tipo_emenda":          tipo_emenda(codigo, nome),
        "ano_mes":              raw.get("ano_mes", ""),
        "uf":                   raw.get("uf", "") or None,
        "municipio":            raw.get("municipio", "") or None,
        "municipio_ibge":       municipio_ibge,
        "cod_orgao_superior":   raw.get("cod_orgao_superior", "") or None,
        "orgao_superior":       raw.get("orgao_superior", "") or None,
        "orgao_subordinado":    raw.get("orgao_subordinado", "") or None,
        "unidade_gestora":      raw.get("unidade_gestora", "") or None,
        "funcao":               raw.get("funcao", "") or None,
        "subfuncao":            raw.get("subfuncao", "") or None,
        "programa":             raw.get("programa", "") or None,
        "cod_acao":             raw.get("cod_acao", "") or None,
        "acao":                 raw.get("acao", "") or None,
        "plano_orcamentario":   raw.get("plano_orcamentario", "") or None,
        "categoria_economica":  raw.get("categoria_economica", "") or None,
        "grupo_despesa":        raw.get("grupo_despesa", "") or None,
        "elemento_despesa":     raw.get("elemento_despesa", "") or None,
        "modalidade_despesa":   raw.get("modalidade_despesa", "") or None,
        "valor_empenhado":      parse_valor(raw.get("valor_empenhado", "")),
        "valor_liquidado":      parse_valor(raw.get("valor_liquidado", "")),
        "valor_pago":           parse_valor(raw.get("valor_pago", "")),
        "valor_resto_inscrito": parse_valor(raw.get("valor_resto_inscrito", "")),
        "valor_resto_cancelado":parse_valor(raw.get("valor_resto_cancelado", "")),
        "valor_resto_pago":     parse_valor(raw.get("valor_resto_pago", "")),
        "id_registro":          None,
    }
    r["id_registro"] = id_registro(r)
    return r


def processar_bronze(bronze_path: Path, cache_muni: dict, force: bool = False) -> Path | None:
    ano_mes = bronze_path.stem.replace("despesas_emendas_", "").replace("_bronze", "")
    prata_path = PRATA_DIR / f"despesas_emendas_{ano_mes}_prata.json"

    if prata_path.exists() and not force:
        print(f"  ♻️  Prata já existe: {prata_path.name}")
        return prata_path

    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    meta    = bronze.get("meta", {})
    records = bronze.get("records", [])
    print(f"  📂 {bronze_path.name}: {len(records):,} registros bronze")

    ok = rejeitados_list = []
    ok_list = []
    for raw in records:
        r = normalizar_registro(raw, cache_muni)
        if r:
            ok_list.append(r)
        else:
            rejeitados_list.append(raw)

    # salva rejeitados
    if rejeitados_list:
        rej_path = REJEIT_DIR / f"despesas_emendas_{ano_mes}_rejeitados.json"
        with open(rej_path, "w", encoding="utf-8") as f:
            json.dump(rejeitados_list, f, ensure_ascii=False)

    # prata
    prata = {
        "meta": {
            **meta,
            "camada":              "prata",
            "data_normalizacao":   datetime.now(timezone.utc).isoformat(),
            "total_ok":            len(ok_list),
            "total_rejeitados":    len(rejeitados_list),
            "pct_municipio_ibge":  round(
                sum(1 for r in ok_list if r["municipio_ibge"]) / max(len(ok_list), 1) * 100, 1
            ),
        },
        "records": ok_list,
    }
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump(prata, f, ensure_ascii=False)

    print(f"  ✅ Prata: {len(ok_list):,} ok | {len(rejeitados_list):,} rejeitados | "
          f"{prata['meta']['pct_municipio_ibge']}% com IBGE → {prata_path.name}")
    return prata_path


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador Despesas de Emendas")
    parser.add_argument("--bronze", help="Arquivo bronze específico")
    parser.add_argument("--todos",  action="store_true")
    parser.add_argument("--force",  action="store_true")
    args = parser.parse_args()

    print("🔄 Agent B — Normalizador")
    cache_muni = carregar_cache_municipios()

    if args.bronze:
        processar_bronze(Path(args.bronze), cache_muni, force=args.force)
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("despesas_emendas_*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado. Execute Agent A primeiro.")
            return
        for b in bronzes:
            processar_bronze(b, cache_muni, force=args.force)
            print()
    else:
        parser.print_help()
        return

    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()
