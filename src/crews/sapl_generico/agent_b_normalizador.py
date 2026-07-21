#!/usr/bin/env python3
"""SAPL Genérico — Agent B (Normalizador): Bronze → Prata

Resolução de politico_id (parlamentar do SAPL → politico_id PRISMA):
  1) Índice em memória de `politicos` filtrado por cargo=VEREADOR, agrupado
     por município (o câmara↔município é 1:1 — pool bem menor e mais preciso
     que o cruzamento por UF usado em cgu_emendas_federais).
  2) Match exato por (nome_parlamentar normalizado, municipio_ibge).
  3) Fallback fuzzy (rapidfuzz token_sort_ratio ≥ 88) dentro do mesmo município.
  4) Sem match → politico_id = None — nunca fabricar (mesma regra de sempre).

`nome_parlamentar` do SAPL costuma já ser o nome de urna/apelido usado no
dia a dia (ex. "ADRIANA ALMEIDA"), diferente do nome civil completo usado
pelo CGU nas emendas federais — espera-se taxa de match mais alta, mas isso
só se confirma medindo (Agent Verify), nunca assumindo.

Partido: resolvido via filiação mais recente (sem data_desfiliacao, ou a de
maior `data` entre as filiações) + tabela de partidos da própria instância
(id -> sigla). Mandato: usa o de maior `legislatura`/`data_inicio_mandato`.

Proposições (materialegislativa): agregadas por parlamentar autor. Um projeto
pode ter múltiplos autores (array `autores` de IDs SAPL) — cada autor listado
recebe crédito pela proposição (mesmo item pode contar pra mais de 1 vereador,
isso é correto, é coautoria real, não duplicação de dado).

Saída: data/sapl_generico/prata/{dominio}.json
"""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from rapidfuzz import fuzz, process
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "prisma_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BRONZE_DIR = BASE_DIR / "data/sapl_generico/bronze"
PRATA_DIR = BASE_DIR / "data/sapl_generico/prata"
PRATA_DIR.mkdir(parents=True, exist_ok=True)


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _norm_nome(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.upper().strip())


def _carregar_indice_vereadores() -> dict[str, list[tuple[str, str]]]:
    """{municipio_ibge: [(nome_urna_norm, politico_id), ...]} só cargo=VEREADOR."""
    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DISTINCT politico_id, nome_urna, municipio_ibge
        FROM politicos
        WHERE cargo = 'VEREADOR' AND municipio_ibge IS NOT NULL AND politico_id IS NOT NULL
    """)
    idx: dict[str, list[tuple[str, str]]] = {}
    for r in cur.fetchall():
        idx.setdefault(r["municipio_ibge"], []).append((_norm_nome(r["nome_urna"]), r["politico_id"]))
    cur.close()
    conn.close()
    total = sum(len(v) for v in idx.values())
    log(f"  índice de vereadores: {len(idx)} município(s), {total:,} candidaturas distintas")
    return idx


def resolver_politico_id(idx: dict, nome: str, municipio_ibge: str) -> tuple[str | None, str]:
    """Retorna (politico_id, metodo). metodo ∈ {'exato','fuzzy','none'}"""
    nome_n = _norm_nome(nome)
    pool = idx.get(municipio_ibge) or []
    if not nome_n or not pool:
        return None, "none"

    for candidato_nome, pid in pool:
        if candidato_nome == nome_n:
            return pid, "exato"

    if HAS_FUZZ:
        nomes = [p[0] for p in pool]
        match = process.extractOne(nome_n, nomes, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 88:
            return pool[match[2]][1], "fuzzy"

    return None, "none"


def _ler_bronze(dominio_dir: Path, nome: str) -> list[dict]:
    arq = dominio_dir / f"{nome}.json"
    if not arq.exists():
        return []
    return json.loads(arq.read_text(encoding="utf-8")).get("records", [])


def _resolver_partidos(partidos_raw: list[dict]) -> dict[int, str]:
    return {p["id"]: p.get("sigla") for p in partidos_raw if p.get("id") is not None}


def _resolver_filiacoes(filiacoes_raw: list[dict], partidos: dict[int, str]) -> dict[int, str]:
    """parlamentar_id -> sigla do partido da filiação mais recente (sem desfiliação, senão maior data)."""
    melhor: dict[int, tuple[str, bool]] = {}
    for f in filiacoes_raw:
        pid_parlamentar = f.get("parlamentar")
        if pid_parlamentar is None:
            continue
        data = f.get("data") or ""
        ativa = not f.get("data_desfiliacao")
        atual = melhor.get(pid_parlamentar)
        if atual is None or (ativa and not atual[1]) or (ativa == atual[1] and data > atual[0]):
            melhor[pid_parlamentar] = (data, ativa)
    # segunda passada pra pegar o partido_id da filiação escolhida
    escolhidas: dict[int, int] = {}
    for f in filiacoes_raw:
        pid_parlamentar = f.get("parlamentar")
        if pid_parlamentar is None:
            continue
        data = f.get("data") or ""
        ativa = not f.get("data_desfiliacao")
        alvo = melhor.get(pid_parlamentar)
        if alvo and alvo == (data, ativa):
            escolhidas[pid_parlamentar] = f.get("partido")
    return {pid: partidos.get(partido_id) for pid, partido_id in escolhidas.items()}


def _resolver_mandatos(mandatos_raw: list[dict]) -> dict[int, dict]:
    """parlamentar_id -> {legislatura, data_inicio, data_fim} do mandato mais recente."""
    melhor: dict[int, dict] = {}
    for m in mandatos_raw:
        pid = m.get("parlamentar")
        if pid is None:
            continue
        atual = melhor.get(pid)
        if atual is None or (m.get("legislatura") or 0) >= (atual.get("legislatura") or 0):
            melhor[pid] = {
                "legislatura": m.get("legislatura"),
                "data_inicio_mandato": m.get("data_inicio_mandato"),
                "data_fim_mandato": m.get("data_fim_mandato"),
            }
    return melhor


def processar_dominio(dominio: str, municipio_ibge: str, idx_vereadores: dict, stats: dict) -> dict | None:
    d = BRONZE_DIR / dominio
    if not d.is_dir():
        return None

    parlamentares_raw = _ler_bronze(d, "parlamentar")
    if not parlamentares_raw:
        return None
    mandatos = _resolver_mandatos(_ler_bronze(d, "mandato"))
    partidos = _resolver_partidos(_ler_bronze(d, "partido"))
    filiacoes = _resolver_filiacoes(_ler_bronze(d, "filiacao"), partidos)
    materias_raw = _ler_bronze(d, "materialegislativa")

    parlamentares_prata = []
    id_sapl_para_politico: dict[int, str | None] = {}
    for p in parlamentares_raw:
        id_sapl = p.get("id")
        nome_parlamentar = p.get("nome_parlamentar") or p.get("nome_completo")
        politico_id, metodo = resolver_politico_id(idx_vereadores, nome_parlamentar, municipio_ibge)
        stats["match"][metodo] = stats["match"].get(metodo, 0) + 1
        id_sapl_para_politico[id_sapl] = politico_id
        mandato = mandatos.get(id_sapl, {})
        parlamentares_prata.append({
            "dominio": dominio, "id_sapl": id_sapl, "municipio_ibge": municipio_ibge,
            "nome_completo": p.get("nome_completo"), "nome_parlamentar": nome_parlamentar,
            "ativo": bool(p.get("ativo")), "email": p.get("email"),
            "legislatura": mandato.get("legislatura"),
            "data_inicio_mandato": mandato.get("data_inicio_mandato"),
            "data_fim_mandato": mandato.get("data_fim_mandato"),
            "partido_sigla": filiacoes.get(id_sapl),
            "politico_id": politico_id, "match_metodo": metodo,
        })

    materias_prata = []
    for m in materias_raw:
        autores_sapl = m.get("autores") or []
        autores_politico_id = [id_sapl_para_politico[a] for a in autores_sapl
                                if a in id_sapl_para_politico and id_sapl_para_politico[a]]
        materias_prata.append({
            "dominio": dominio, "id_sapl": m.get("id"), "municipio_ibge": municipio_ibge,
            "numero": m.get("numero"), "ano": m.get("ano"), "tipo": m.get("tipo"),
            "ementa": m.get("ementa"), "data_apresentacao": m.get("data_apresentacao"),
            "em_tramitacao": m.get("em_tramitacao"),
            "autores_id_sapl": autores_sapl, "autores_politico_id": autores_politico_id,
        })

    return {"parlamentares": parlamentares_prata, "materias": materias_prata}


def main() -> None:
    ap = argparse.ArgumentParser(description="SAPL Genérico — Agent B (Normalizador)")
    ap.add_argument("--todos", action="store_true", help="processa todos os bronzes disponíveis")
    ap.add_argument("--dominio", type=str, default=None, help="processa só 1 domínio (teste)")
    args = ap.parse_args()

    if not args.todos and not args.dominio:
        ap.error("passe --dominio X (teste) ou --todos")

    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.dominio:
        cur.execute("SELECT municipio_ibge, dominio FROM sapl_instancias WHERE dominio = %s", (args.dominio,))
    else:
        cur.execute("SELECT municipio_ibge, dominio FROM sapl_instancias WHERE status = 'ativo'")
    instancias = cur.fetchall()
    conn.close()

    log("carregando índice de vereadores (cargo=VEREADOR por município)...")
    idx_vereadores = _carregar_indice_vereadores()

    stats = {"match": {}}
    total_parlamentares = total_materias = 0
    for inst in instancias:
        resultado = processar_dominio(inst["dominio"], inst["municipio_ibge"], idx_vereadores, stats)
        if resultado is None:
            log(f"  ⚠️ sem bronze pra {inst['dominio']} — rode Agent A primeiro")
            continue
        (PRATA_DIR / f"{inst['dominio']}.json").write_text(
            json.dumps(resultado, ensure_ascii=False), encoding="utf-8"
        )
        total_parlamentares += len(resultado["parlamentares"])
        total_materias += len(resultado["materias"])
        log(f"  ✅ {inst['dominio']}: {len(resultado['parlamentares'])} parlamentar(es), "
            f"{len(resultado['materias'])} matéria(s)")

    pct_match = round(100 * (stats["match"].get("exato", 0) + stats["match"].get("fuzzy", 0))
                       / max(sum(stats["match"].values()), 1), 1)
    log(f"\n✅ Agent B concluído: {total_parlamentares:,} parlamentares, {total_materias:,} matérias | "
        f"match politico_id: {stats['match']} ({pct_match}%)")


if __name__ == "__main__":
    main()
