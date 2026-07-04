#!/usr/bin/env python3
"""Agent B — Normalizador Câmara Votações: Bronze → Prata

Lê Bronze (API REST v2 da Câmara) e produz dois conjuntos de records
prontos para o Loader:

  records_votacoes        → linhas para camara_votacoes
  records_votos_nominais  → linhas para camara_votos_nominais

Resolução de politico_id (deputado_id_camara → politico_id PRISMA):
  1) Cache em memória, construído por consulta única à tabela `politicos`
     filtrando candidatos a Deputado Federal nas eleições (2014, 2018, 2022).
  2) Match preferencial por (nome_urna|nome_completo, UF, partido).
  3) Fallback fuzzy (rapidfuzz token_sort_ratio ≥ 88) por nome+UF.
  4) Sem match → politico_id = None (loader grava NULL).

Regras de rejeição (votação):
  - id ausente
  - dataHoraRegistro inválida

Regras de rejeição (voto nominal):
  - deputado.id ausente
  - tipoVoto vazio

Saída:
    data/camara_votacoes/prata/votacoes_{LEG}_{ANO}_{MES}_prata.json
    data/camara_votacoes/rejeitados/votacoes_{LEG}_{ANO}_{MES}_rejeitados.json
"""
import json
import re
import hashlib
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
DATA_DIR   = BASE_DIR / "data/camara_votacoes"
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


def _carregar_indice_politicos() -> dict:
    """Constrói índice em memória:
        {
          "por_id_legislativo": {id_camara: politico_id},
          "por_nome_uf":        {(nome_norm, uf): politico_id},
          "por_nome_uf_partido": {(nome_norm, uf, partido): politico_id},
          "fuzzy_pool_por_uf":  {uf: [(nome_norm, politico_id), ...]},
        }
    Filtra somente Deputados Federais nas eleições recentes.
    Robusto contra schema variável (id_legislativo_camara pode não existir).
    """
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Descobre quais colunas existem em politicos (schema varia)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'politicos'
    """)
    cols = {r["column_name"] for r in cur.fetchall()}

    nome_col   = "nome_urna" if "nome_urna" in cols else (
                  "nome_candidato" if "nome_candidato" in cols else "nome")
    partido_col = "sigla_partido" if "sigla_partido" in cols else (
                   "partido" if "partido" in cols else None)
    cargo_col  = "cargo" if "cargo" in cols else None
    uf_col     = "uf" if "uf" in cols else ("sigla_uf" if "sigla_uf" in cols else None)
    ano_col    = "ano_eleicao" if "ano_eleicao" in cols else None
    id_leg_col = next((c for c in (
        "id_legislativo_camara", "id_camara",
        "id_deputado_camara", "id_parlamentar_camara"
    ) if c in cols), None)

    select_extras = [f'"{nome_col}" AS nome']
    if partido_col: select_extras.append(f'"{partido_col}" AS partido')
    if uf_col:      select_extras.append(f'"{uf_col}" AS uf')
    if id_leg_col:  select_extras.append(f'"{id_leg_col}" AS id_legislativo')

    where = ["politico_id IS NOT NULL"]
    if cargo_col:
        where.append(f"UPPER({cargo_col}) LIKE 'DEPUTADO FEDERAL%%'")
    if ano_col:
        where.append(f"{ano_col} IN (2014, 2018, 2022, 2024)")

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

    idx = {
        "por_id_legislativo":   {},
        "por_nome_uf":          {},
        "por_nome_uf_partido":  {},
        "fuzzy_pool_por_uf":    {},
    }
    for r in rows:
        pid = r["politico_id"]
        nome = _norm_nome(r.get("nome"))
        uf   = (r.get("uf") or "").upper().strip()
        part = (r.get("partido") or "").upper().strip()
        id_leg = r.get("id_legislativo")

        if id_leg:
            try:
                idx["por_id_legislativo"][int(id_leg)] = pid
            except (TypeError, ValueError):
                pass
        if nome and uf:
            idx["por_nome_uf"].setdefault((nome, uf), pid)
            if part:
                idx["por_nome_uf_partido"].setdefault((nome, uf, part), pid)
            idx["fuzzy_pool_por_uf"].setdefault(uf, []).append((nome, pid))

    print(f"  Indice políticos: "
          f"{len(idx['por_id_legislativo'])} por id_legislativo | "
          f"{len(idx['por_nome_uf'])} por nome+uf | "
          f"{sum(len(v) for v in idx['fuzzy_pool_por_uf'].values())} no pool fuzzy")
    return idx


def resolver_politico_id(idx: dict, id_camara: int | None,
                          nome: str | None, uf: str | None,
                          partido: str | None) -> tuple[str | None, str]:
    """Retorna (politico_id, metodo). metodo ∈ {'id_legislativo','exato','fuzzy','none'}"""
    if id_camara and id_camara in idx["por_id_legislativo"]:
        return idx["por_id_legislativo"][id_camara], "id_legislativo"

    nome_n = _norm_nome(nome)
    uf_n   = (uf or "").upper().strip()
    part_n = (partido or "").upper().strip()

    if nome_n and uf_n and part_n:
        hit = idx["por_nome_uf_partido"].get((nome_n, uf_n, part_n))
        if hit:
            return hit, "exato"
    if nome_n and uf_n:
        hit = idx["por_nome_uf"].get((nome_n, uf_n))
        if hit:
            return hit, "exato"

    if HAS_FUZZ and nome_n and uf_n and uf_n in idx["fuzzy_pool_por_uf"]:
        pool = idx["fuzzy_pool_por_uf"][uf_n]
        nomes = [p[0] for p in pool]
        match = process.extractOne(nome_n, nomes, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 88:
            return pool[match[2]][1], "fuzzy"

    return None, "none"


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _parse_ts(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    # Aceita ISO com ou sem tz; devolve string para o loader
    try:
        # normaliza "Z" → "+00:00"
        ss = s.replace("Z", "+00:00")
        # valida
        datetime.fromisoformat(ss)
        return ss
    except ValueError:
        # tenta só data
        try:
            datetime.strptime(s[:10], "%Y-%m-%d")
            return s[:10]
        except ValueError:
            return None


def _parse_int(v) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _hash_votacao(vid: str, data: str | None, descricao: str | None) -> str:
    chave = f"{vid}|{data or ''}|{descricao or ''}"
    return hashlib.sha256(chave.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────
# Normalizador principal
# ──────────────────────────────────────────────────────────────────

def normalizar_votacao(v: dict) -> dict | None:
    vid = v.get("id")
    if not vid:
        return {"_motivo": "id ausente", **v}

    data_hora = _parse_ts(v.get("dataHoraRegistro"))
    if not data_hora:
        return {"_motivo": "dataHoraRegistro inválida", **v}

    data_iso = data_hora[:10] if data_hora else None

    descricao = (v.get("descricao") or v.get("ementa") or "").strip() or None
    sigla_orgao = v.get("siglaOrgao") or None

    # Proposição associada (pode ser lista)
    prop_id = None
    prop_obj = v.get("proposicaoObjeto") or {}
    if isinstance(prop_obj, dict):
        prop_id = _parse_int(prop_obj.get("id"))
    if not prop_id:
        props = v.get("proposicoesAfetadas") or []
        if props and isinstance(props, list):
            prop_id = _parse_int(props[0].get("id") if isinstance(props[0], dict) else None)

    aprov = v.get("aprovacao")
    aprovacao = None
    if isinstance(aprov, bool):
        aprovacao = 1 if aprov else 0
    elif isinstance(aprov, (int, float)):
        aprovacao = int(aprov)
    elif isinstance(aprov, str) and aprov.strip().isdigit():
        aprovacao = int(aprov.strip())

    return {
        "id":                   str(vid),
        "legislatura":          None,  # preenchido pelo caller (vem do meta)
        "data":                 data_iso,
        "data_hora_registro":   data_hora,
        "sigla_orgao":          sigla_orgao,
        "proposicao_id":        prop_id,
        "descricao":            descricao,
        "aprovacao":            aprovacao,
        "sim":                  None,  # preenchido na agregação dos votos
        "nao":                  None,
        "outros":               None,
        "abstencoes":           None,
        "raw_hash":             _hash_votacao(str(vid), data_iso, descricao),
    }


def normalizar_voto(voto: dict, votacao_id: str, idx: dict,
                     stats: dict) -> dict | None:
    dep = voto.get("deputado_") or voto.get("deputado") or {}
    id_camara = _parse_int(dep.get("id"))
    nome      = dep.get("nome") or voto.get("nome") or None
    uf        = dep.get("siglaUf") or voto.get("siglaUf") or None
    partido   = dep.get("siglaPartido") or voto.get("siglaPartido") or None
    tipo      = (voto.get("tipoVoto") or voto.get("voto") or "").strip() or None
    data_voto = _parse_ts(voto.get("dataRegistroVoto"))

    if not id_camara:
        return {"_motivo": "deputado.id ausente", **voto}
    if not tipo:
        return {"_motivo": "tipoVoto vazio", **voto}

    politico_id, metodo = resolver_politico_id(idx, id_camara, nome, uf, partido)
    stats["match"][metodo] = stats["match"].get(metodo, 0) + 1

    return {
        "votacao_id":         votacao_id,
        "deputado_id_camara": id_camara,
        "politico_id":        politico_id,
        "nome":               nome,
        "sigla_partido":      partido,
        "sigla_uf":           uf,
        "tipo_voto":          tipo,
        "data_hora_voto":     data_voto,
    }


def _agregar_contagens(votos_norm: list[dict]) -> dict:
    sim = nao = abst = outros = 0
    for v in votos_norm:
        t = (v.get("tipo_voto") or "").lower()
        if "sim" in t:
            sim += 1
        elif "não" in t or "nao" in t:
            nao += 1
        elif "absten" in t:
            abst += 1
        else:
            outros += 1
    return {"sim": sim, "nao": nao, "outros": outros, "abstencoes": abst}


# ──────────────────────────────────────────────────────────────────
# Processamento de bronze
# ──────────────────────────────────────────────────────────────────

def processar_bronze(bronze_path: Path, idx: dict) -> None:
    print(f"Bronze: {bronze_path.name}")
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    meta            = bronze.get("meta", {})
    legislatura     = meta.get("legislatura")
    votacoes_raw    = bronze.get("votacoes", []) or []
    votos_por_vid   = bronze.get("votos", {}) or {}
    print(f"  Total bruto: {len(votacoes_raw):,} votações")

    votacoes_validas: list[dict] = []
    votos_validos:    list[dict] = []
    rejeitados_vot:   list[dict] = []
    rejeitados_vts:   list[dict] = []

    stats = {"match": {}}

    for v in votacoes_raw:
        nv = normalizar_votacao(v)
        if nv is None:
            continue
        if "_motivo" in nv:
            rejeitados_vot.append(nv)
            continue
        nv["legislatura"] = legislatura

        vid = nv["id"]
        votos = votos_por_vid.get(vid, []) or []
        votos_norm: list[dict] = []
        for voto in votos:
            nvoto = normalizar_voto(voto, vid, idx, stats)
            if nvoto is None:
                continue
            if "_motivo" in nvoto:
                rejeitados_vts.append(nvoto)
                continue
            votos_norm.append(nvoto)

        cont = _agregar_contagens(votos_norm)
        nv.update(cont)

        votacoes_validas.append(nv)
        votos_validos.extend(votos_norm)

    stem = bronze_path.stem.replace("_bronze", "")
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "data_processamento":  datetime.now(timezone.utc).isoformat(),
                "fonte_bronze":        bronze_path.name,
                "legislatura":         legislatura,
                "ano":                 meta.get("ano"),
                "mes":                 meta.get("mes"),
                "total_votacoes":      len(votacoes_validas),
                "total_votos":         len(votos_validos),
                "rejeitados_votacoes": len(rejeitados_vot),
                "rejeitados_votos":    len(rejeitados_vts),
                "match_politico":      stats["match"],
            },
            "records_votacoes":       votacoes_validas,
            "records_votos_nominais": votos_validos,
        }, f, ensure_ascii=False)

    if rejeitados_vot or rejeitados_vts:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, "w", encoding="utf-8") as f:
            json.dump({
                "votacoes_rejeitadas": rejeitados_vot,
                "votos_rejeitados":    rejeitados_vts,
            }, f, ensure_ascii=False)

    print(f"  Prata: {len(votacoes_validas):>5,} votações | "
          f"{len(votos_validos):>7,} votos -> {prata_path.name}")
    print(f"  Match politico: {stats['match']}")


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador Câmara Votações")
    parser.add_argument("--bronze", help="Arquivo bronze específico")
    parser.add_argument("--todos",  action="store_true", help="Todos os bronzes")
    args = parser.parse_args()

    print("Carregando índice de políticos...")
    idx = _carregar_indice_politicos()

    if args.bronze:
        processar_bronze(Path(args.bronze), idx)
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("votacoes_*_bronze.json"))
        if not bronzes:
            print("Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b, idx)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("votacoes_*_bronze.json"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0], idx)

    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()
