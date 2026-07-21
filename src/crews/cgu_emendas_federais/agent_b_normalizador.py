#!/usr/bin/env python3
"""Agent B — Normalizador CGU Emendas Federais: Bronze → Prata

Resolução de politico_id (nome do autor da emenda → politico_id PRISMA):
  1) Cache em memória, construído por consulta única à tabela `politicos`
     filtrando candidatos a Deputado Federal ou Senador (eleições 2014-2022).
  2) Match preferencial por (nome, UF da localidade de aplicação do recurso).
  3) Fallback fuzzy (rapidfuzz token_sort_ratio ≥ 88) por nome dentro da mesma UF.
  4) Sem match → politico_id = None (loader grava NULL) — nunca fabricar.

cnpj_favorecido: agregado a partir do bronze de favorecidos (EmendasParlamentares_
PorFavorecido.csv), escolhendo o favorecido de MAIOR "Valor Recebido" por
codigo_emenda — decisão explícita e documentada (mesmo espírito do siga_ba_emendas:
resumir com critério claro, nunca inventar). Emendas sem nenhum favorecido claro
ficam com cnpj_favorecido = NULL.

valor_resto_pago: mapeado direto de "Valor Restos A Pagar Pagos" (não é soma dos
3 campos de restos a pagar do CSV — inscrito/cancelado/pago são estados distintos
do mesmo saldo, somar duplicaria valor). Validar contra os registros já existentes
de 2015-2026 no primeiro dry-run antes de aplicar em massa.

Saída:
    data/cgu_emendas_federais/prata/emendas_federais_{ANO}_prata.json
    data/cgu_emendas_federais/rejeitados/emendas_federais_{ANO}_rejeitados.json
"""
import json
import re
import argparse
import os
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

try:
    from rapidfuzz import fuzz, process
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/cgu_emendas_federais"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 5432)),
    dbname   = os.getenv("DB_NAME", "prisma_data"),
    user     = os.getenv("DB_USER", "postgres"),
    password = DB_PASSWORD,
)


# ──────────────────────────────────────────────────────────────────
# Resolução politico_id
# ──────────────────────────────────────────────────────────────────

def _norm_nome(s: str | None) -> str:
    if not s:
        return ""
    s = s.upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s


# O CSV da CGU traz "UF" por extenso ("PARANÁ"), não a sigla — mesmo vocabulário
# oficial de nomes de estado usado em `municipios.uf_nome` (27 UFs fixas, sem risco
# de fabricar dado: é só normalização de nomenclatura já usada no próprio banco).
UF_NOME_PARA_SIGLA = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAZONAS": "AM", "AMAPÁ": "AP",
    "BAHIA": "BA", "CEARÁ": "CE", "DISTRITO FEDERAL": "DF",
    "ESPÍRITO SANTO": "ES", "GOIÁS": "GO", "MARANHÃO": "MA",
    "MINAS GERAIS": "MG", "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT",
    "PARÁ": "PA", "PARAÍBA": "PB", "PERNAMBUCO": "PE", "PIAUÍ": "PI",
    "PARANÁ": "PR", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RONDÔNIA": "RO", "RORAIMA": "RR", "RIO GRANDE DO SUL": "RS",
    "SANTA CATARINA": "SC", "SERGIPE": "SE", "SÃO PAULO": "SP",
    "TOCANTINS": "TO",
}


def _uf_para_sigla(uf_raw: str | None) -> str | None:
    if not uf_raw:
        return None
    uf_raw = uf_raw.upper().strip()
    if len(uf_raw) == 2:
        return uf_raw  # já é sigla
    return UF_NOME_PARA_SIGLA.get(uf_raw)


def _carregar_indice_politicos() -> dict:
    """Índice em memória:
        por_nome_uf: {(nome_norm, uf): politico_id}
        fuzzy_pool_por_uf: {uf: [(nome_norm, politico_id), ...]}
    Filtra Deputados Federais e Senadores nas eleições 2014-2022
    (emendas parlamentares federais são só desses dois cargos).
    """
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'politicos'
    """)
    cols = {r["column_name"] for r in cur.fetchall()}

    nome_col    = "nome_urna" if "nome_urna" in cols else (
                   "nome_candidato" if "nome_candidato" in cols else "nome")
    partido_col = "sigla_partido" if "sigla_partido" in cols else (
                   "partido" if "partido" in cols else None)
    cargo_col   = "cargo" if "cargo" in cols else None
    uf_col      = "uf" if "uf" in cols else ("sigla_uf" if "sigla_uf" in cols else None)

    select_extras = [f'"{nome_col}" AS nome']
    if partido_col: select_extras.append(f'"{partido_col}" AS partido')
    if uf_col:      select_extras.append(f'"{uf_col}" AS uf')

    # Sem filtro de ano_eleicao: nome+UF de um Deputado Federal/Senador não muda
    # entre eleições, e a tabela `politicos` tem gaps de candidatura em anos
    # específicos pra incumbentes de longa carreira (ex: Jair Bolsonaro só tem
    # registro de 2006/2010 — restringir a 2014/2018/2022 os excluiria do índice).
    where = ["politico_id IS NOT NULL"]
    if cargo_col:
        where.append(f"(UPPER({cargo_col}) LIKE 'DEPUTADO FEDERAL%%' OR UPPER({cargo_col}) LIKE 'SENADOR%%')")

    sql = f"""
        SELECT politico_id, {', '.join(select_extras)}
        FROM politicos
        WHERE {' AND '.join(where)}
    """
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except Exception as e:
        print(f"  ! Falha ao carregar índice de políticos: {e}")
        rows = []
    finally:
        cur.close()
        conn.close()

    idx = {"por_nome_uf": {}, "fuzzy_pool_por_uf": {}}
    for r in rows:
        pid  = r["politico_id"]
        nome = _norm_nome(r.get("nome"))
        uf   = (r.get("uf") or "").upper().strip()
        if nome and uf:
            idx["por_nome_uf"].setdefault((nome, uf), pid)
            idx["fuzzy_pool_por_uf"].setdefault(uf, []).append((nome, pid))

    print(f"  Indice políticos: {len(idx['por_nome_uf'])} por nome+uf | "
          f"{sum(len(v) for v in idx['fuzzy_pool_por_uf'].values())} no pool fuzzy")
    return idx


def resolver_politico_id(idx: dict, nome: str | None, uf: str | None) -> tuple[str | None, str]:
    """Retorna (politico_id, metodo). metodo ∈ {'exato','fuzzy','none'}"""
    nome_n = _norm_nome(nome)
    uf_n   = (uf or "").upper().strip()
    if not nome_n or not uf_n:
        return None, "none"

    hit = idx["por_nome_uf"].get((nome_n, uf_n))
    if hit:
        return hit, "exato"

    if HAS_FUZZ and uf_n in idx["fuzzy_pool_por_uf"]:
        pool = idx["fuzzy_pool_por_uf"][uf_n]
        nomes = [p[0] for p in pool]
        match = process.extractOne(nome_n, nomes, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 88:
            return pool[match[2]][1], "fuzzy"

    return None, "none"


# ──────────────────────────────────────────────────────────────────
# Helpers de parsing
# ──────────────────────────────────────────────────────────────────

def _parse_valor(v: str | None) -> float | None:
    if not v:
        return None
    v = v.strip().replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _limpar(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v if v and v.upper() != "SEM INFORMAÇÃO" else None


def _agregar_cnpj_favorecido(registros_favorecido: list[dict]) -> dict[str, str]:
    """codigo_emenda -> Código do Favorecido de maior Valor Recebido."""
    melhor: dict[str, tuple[float, str]] = {}
    for row in registros_favorecido:
        cod = _limpar(row.get("Código da Emenda"))
        fav = _limpar(row.get("Código do Favorecido"))
        if not cod or not fav:
            continue
        valor = _parse_valor(row.get("Valor Recebido")) or 0.0
        atual = melhor.get(cod)
        if atual is None or valor > atual[0]:
            melhor[cod] = (valor, fav)
    return {cod: fav for cod, (_, fav) in melhor.items()}


# ──────────────────────────────────────────────────────────────────
# Normalizador principal
# ──────────────────────────────────────────────────────────────────

def normalizar_registro(row: dict, cnpj_por_emenda: dict, idx: dict, stats: dict) -> dict | None:
    codigo = _limpar(row.get("Código da Emenda"))
    if not codigo:
        return {"_motivo": "codigo_emenda ausente", **row}

    ano = row.get("Ano da Emenda", "").strip()
    try:
        ano_orcamento = int(ano)
    except ValueError:
        return {"_motivo": "ano_orcamento inválido", **row}

    nome_autor = _limpar(row.get("Nome do Autor da Emenda"))
    uf         = _uf_para_sigla(_limpar(row.get("UF")))

    politico_id, metodo = resolver_politico_id(idx, nome_autor, uf)
    stats["match"][metodo] = stats["match"].get(metodo, 0) + 1

    municipio_ibge = _limpar(row.get("Código Município IBGE"))
    if municipio_ibge and len(municipio_ibge) != 7:
        municipio_ibge = None  # não fabricar padding — deixa NULL se formato inesperado

    cnpj_favorecido = cnpj_por_emenda.get(codigo)

    return {
        "codigo_emenda":    codigo,
        "politico_id":      politico_id,
        "nome_autor":       nome_autor,
        "municipio_ibge":   municipio_ibge,
        "funcao":           _limpar(row.get("Nome Função")),
        "subfuncao":        _limpar(row.get("Nome Subfunção")),
        "valor_empenhado":  _parse_valor(row.get("Valor Empenhado")),
        "valor_liquidado":  _parse_valor(row.get("Valor Liquidado")),
        "valor_pago":       _parse_valor(row.get("Valor Pago")),
        "valor_resto_pago": _parse_valor(row.get("Valor Restos A Pagar Pagos")),
        "cnpj_favorecido":  cnpj_favorecido,
        "ano_orcamento":    ano_orcamento,
        "tipo_emenda":      _limpar(row.get("Tipo de Emenda")),
        "numero_emenda":    _limpar(row.get("Número da emenda")),
        "localidade_raw":   _limpar(row.get("Localidade de aplicação do recurso")),
    }


def processar_bronze(bronze_p: Path, bronze_f: Path, idx: dict) -> None:
    print(f"Bronze: {bronze_p.name}")
    with open(bronze_p, encoding="utf-8") as f:
        bp = json.load(f)
    registros_raw = bp.get("records", [])
    ano = bp.get("meta", {}).get("ano")

    registros_favorecido = []
    if bronze_f.exists():
        with open(bronze_f, encoding="utf-8") as f:
            registros_favorecido = json.load(f).get("records", [])
    cnpj_por_emenda = _agregar_cnpj_favorecido(registros_favorecido)

    validos: list[dict] = []
    rejeitados: list[dict] = []
    stats = {"match": {}}

    for row in registros_raw:
        nr = normalizar_registro(row, cnpj_por_emenda, idx, stats)
        if "_motivo" in nr:
            rejeitados.append(nr)
            continue
        validos.append(nr)

    total = max(len(validos), 1)
    com_politico = sum(1 for r in validos if r["politico_id"])
    com_cnpj     = sum(1 for r in validos if r["cnpj_favorecido"])
    com_ibge     = sum(1 for r in validos if r["municipio_ibge"])

    prata_path = PRATA_DIR / f"emendas_federais_{ano}_prata.json"
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "data_processamento": datetime.now(timezone.utc).isoformat(),
                "ano":                ano,
                "total_registros":    len(validos),
                "rejeitados":         len(rejeitados),
                "pct_politico_id":    round(com_politico / total * 100, 1),
                "pct_cnpj":           round(com_cnpj / total * 100, 1),
                "pct_municipio_ibge": round(com_ibge / total * 100, 1),
                "match_politico":     stats["match"],
            },
            "records": validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        with open(REJEIT_DIR / f"emendas_federais_{ano}_rejeitados.json", "w", encoding="utf-8") as f:
            json.dump({"registros_rejeitados": rejeitados}, f, ensure_ascii=False)

    print(f"  Prata: {len(validos):>6,} registros | "
          f"politico_id {com_politico/total*100:.1f}% | "
          f"cnpj {com_cnpj/total*100:.1f}% | ibge {com_ibge/total*100:.1f}% → {prata_path.name}")
    print(f"  Match politico: {stats['match']}")


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador CGU Emendas Federais")
    parser.add_argument("--ano",   type=int, help="Ano específico do bronze a processar")
    parser.add_argument("--todos", action="store_true", help="Todos os bronzes disponíveis")
    args = parser.parse_args()

    print("Carregando índice de políticos...")
    idx = _carregar_indice_politicos()

    if args.ano:
        bronze_p = BRONZE_DIR / f"emendas_federais_{args.ano}_bronze.json"
        bronze_f = BRONZE_DIR / f"emendas_federais_favorecidos_{args.ano}_bronze.json"
        if not bronze_p.exists():
            print(f"❌ Bronze não encontrado: {bronze_p.name} — rode Agent A primeiro.")
            return
        processar_bronze(bronze_p, bronze_f, idx)
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("emendas_federais_*_bronze.json"))
        bronzes = [b for b in bronzes if "favorecidos" not in b.name]
        if not bronzes:
            print("Nenhum Bronze encontrado — rode Agent A primeiro."); return
        for bp in bronzes:
            ano = bp.stem.replace("emendas_federais_", "").replace("_bronze", "")
            bf = BRONZE_DIR / f"emendas_federais_favorecidos_{ano}_bronze.json"
            processar_bronze(bp, bf, idx)
            print()
    else:
        parser.print_help()
        return

    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()
