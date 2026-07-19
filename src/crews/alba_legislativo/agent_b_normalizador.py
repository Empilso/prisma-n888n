#!/usr/bin/env python3
"""
ALBA Legislativo — Agent B (Normalizador + atribuição a politico_id)

Bronze (JSON da API) → Prata (registros normalizados com politico_id resolvido).

Atribuição (robusta, sem matching por nome):
  1. autorId da API → alba_parlamentares.autor_id → politico_id  (fonte primária)
  2. fallback por CPF: AutorRequerenteDados.cpf_cnpj → politicos.cpf
Proposição sem nenhum dos dois fica com politico_id=NULL (não some — o loader
grava mesmo assim, marcada como não-atribuída, pra auditoria).
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "alba_legislativo"
BRONZE = DATA_DIR / "bronze"
PRATA = DATA_DIR / "prata"
PRATA.mkdir(parents=True, exist_ok=True)

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido")
DB = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
          dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
          password=DB_PASSWORD)


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _so_digitos(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def carregar_mapas(cur):
    """autor_id→politico_id (alba_parlamentares); cpf→politico_id (politicos)."""
    cur.execute("SELECT autor_id, parlamentar_id, politico_id FROM alba_parlamentares WHERE politico_id IS NOT NULL")
    por_autor, por_parlamentar = {}, {}
    for r in cur.fetchall():
        if r["autor_id"] is not None:
            por_autor[str(r["autor_id"])] = r["politico_id"]
        if r["parlamentar_id"] is not None:
            por_parlamentar[str(r["parlamentar_id"])] = r["politico_id"]
    return por_autor, por_parlamentar


def resolver_por_cpf(cur, cpf: str) -> str | None:
    cpf = _so_digitos(cpf)
    if len(cpf) != 11:
        return None
    cur.execute("""
        SELECT politico_id FROM politicos
        WHERE cpf = %s AND COALESCE(cpf_contestado, false) = false
        ORDER BY ano_eleicao DESC LIMIT 1
    """, [cpf])
    row = cur.fetchone()
    return row["politico_id"] if row else None


def normalizar_proposicoes(cur, por_autor: dict) -> list[dict]:
    saida, cpf_cache = [], {}
    arquivos = sorted(BRONZE.glob("proposicoes_autor*.json"))
    log(f"proposições: {len(arquivos)} arquivos bronze (1 por autor)")
    for arq in arquivos:
        payload = json.loads(arq.read_text(encoding="utf-8"))
        for p in payload.get("proposicoes", []):
            autor = p.get("AutorRequerenteDados") or {}
            autor_id = autor.get("autorId")
            pid = por_autor.get(str(autor_id)) if autor_id is not None else None
            if not pid:
                cpf = _so_digitos(autor.get("cpf_cnpj"))
                if cpf and len(cpf) == 11:
                    if cpf not in cpf_cache:
                        cpf_cache[cpf] = resolver_por_cpf(cur, cpf)
                    pid = cpf_cache[cpf]
            saida.append({
                "id_proposicao": p.get("id"),
                "politico_id": pid,
                "autor_id": autor_id,
                "autor_nome": autor.get("nomeRazao"),
                "sigla": p.get("sigla"),
                "tipo": p.get("tipo"),
                "numero": p.get("numero"),
                "ano": p.get("ano"),
                "assunto": p.get("assunto"),
                "situacao": p.get("situacao"),
                "data_apresentacao": p.get("data"),
                "processo": p.get("processo"),
                "url_arquivo": p.get("arquivo"),
                "eh_coautor": False,
            })
            # coautores (quando a API traz)
            for co in (p.get("CoAutores") or []):
                co_id = (co or {}).get("autorId")
                co_pid = por_autor.get(str(co_id)) if co_id is not None else None
                if not co_pid:
                    continue  # coautor só entra se resolvido — evita ruído
                saida.append({**saida[-1], "politico_id": co_pid, "autor_id": co_id,
                              "autor_nome": (co or {}).get("nomeRazao"), "eh_coautor": True})
    return saida


def normalizar_comissoes(por_parlamentar: dict) -> list[dict]:
    arq = BRONZE / "comissoes.json"
    if not arq.exists():
        return []
    payload = json.loads(arq.read_text(encoding="utf-8"))
    saida = []
    for c in payload.get("comissoes", []):
        for m in (c.get("comissaoParlamentar") or []):
            parl_id = m.get("parlamentarID")
            saida.append({
                "comissao_id": c.get("comissaoID"),
                "comissao_nome": c.get("comissaoNome"),
                "comissao_sigla": c.get("comissaoSigla"),
                "parlamentar_id": parl_id,
                "parlamentar_nome": m.get("parlamentarRazaoSocial"),
                "politico_id": por_parlamentar.get(str(parl_id)),
                "cargo": m.get("comissaoCargo"),
            })
    return saida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recurso", choices=["proposicoes", "comissoes", "todos"], default="todos")
    args = ap.parse_args()

    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    por_autor, por_parlamentar = carregar_mapas(cur)
    log(f"mapas: {len(por_autor)} autor_id, {len(por_parlamentar)} parlamentar_id → politico_id")

    if args.recurso in ("proposicoes", "todos"):
        props = normalizar_proposicoes(cur, por_autor)
        atrib = sum(1 for p in props if p["politico_id"])
        (PRATA / "proposicoes.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        log(f"✅ proposições prata: {len(props):,} linhas ({atrib:,} atribuídas a politico_id, "
            f"{len(props) - atrib:,} sem atribuição)")
    if args.recurso in ("comissoes", "todos"):
        coms = normalizar_comissoes(por_parlamentar)
        (PRATA / "comissoes.json").write_text(json.dumps(coms, ensure_ascii=False), encoding="utf-8")
        log(f"✅ comissões prata: {len(coms)} vínculos parlamentar↔comissão")
    conn.close()


if __name__ == "__main__":
    main()
