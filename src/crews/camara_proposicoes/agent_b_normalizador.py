#!/usr/bin/env python3
"""Agent B — Normalizador Câmara Proposições: Bronze → Prata

Cada item Bronze tem 3 partes (do Agent A):
  _resumo  → resumo do endpoint /proposicoes
  _detalhe → detalhe do endpoint /proposicoes/{id} (situação, ementa detalhada, keywords)
  _autores → lista do endpoint /proposicoes/{id}/autores (deputado_id Câmara + nome)

Saída por registro segue o schema da tabela camara_proposicoes (Postgres prisma_data):
    id, tipo, numero, ano, ementa, ementa_detalhada,
    data_apresentacao, status_situacao, status_descricao_tramitacao, status_data,
    uri_orgao_atual, sigla_orgao_atual, keywords (TEXT[]),
    autores (JSONB lista), autores_politico_ids (TEXT[]),
    raw_hash (TEXT UNIQUE)

Cruzamento autor → politico_id PRISMA
------------------------------------
A tabela `politicos` **não** possui campo `id_legislativo_camara`. A API da Câmara
retorna `idDeputadoAutor` (numérico Câmara), porém o ID interno PRISMA é `id_tse`
(também armazenado como `politico_id`). Estratégia adotada pelo Agent C:

  1. Tenta resolver por `nome_urna` + `uf` + `sigla_partido` da legislatura corrente.
  2. Cai em fuzzy match por `nome_completo` (similaridade ≥ 0.85 via pg_trgm) +
     UF do autor.
  3. Se não encontrar, o `politico_id_prisma` fica NULL no item autor mas o registro
     ainda é carregado (autoria fica registrada por nome).

Aqui, o Agent B apenas extrai os campos brutos do autor (id Câmara, nome, partido, UF, tipo).
O Agent C faz o lookup contra `politicos`.

Regras de rejeição:
  - id da proposição ausente
  - tipo / numero / ano ausentes (registro corrupto)
  - ementa ausente (proposição inválida sem texto)

Saída:
    data/camara_proposicoes/prata/proposicoes_{LEG}_prata.json
    data/camara_proposicoes/rejeitados/proposicoes_{LEG}_rejeitados.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, date, timezone
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/camara_proposicoes"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)


def limpar(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "None", "null", "#NULO", "-1") else s


def parse_date(v) -> date | None:
    v = limpar(v)
    if not v:
        return None
    try:
        v = v.split("T")[0].strip()[:10]
        if "/" in v:
            d, m, a = v.split("/")
            return date(int(a), int(m), int(d))
        if "-" in v:
            a, m, d = v[:4], v[5:7], v[8:10]
            return date(int(a), int(m), int(d))
    except Exception:
        return None
    return None


def parse_datetime(v) -> str | None:
    """Retorna ISO8601 com timezone (string) ou None."""
    v = limpar(v)
    if not v:
        return None
    try:
        # API costuma devolver "2024-03-15T10:30:00" (sem tz). Assumimos -03 (Brasília).
        if "T" in v and "+" not in v and "Z" not in v:
            return f"{v}-03:00"
        return v
    except Exception:
        return None


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def extrair_keywords(detalhe: dict) -> list[str]:
    """Keywords podem vir como string CSV em detalhe['keywords'] ou como lista."""
    raw = detalhe.get("keywords") if detalhe else None
    if raw is None:
        return []
    if isinstance(raw, list):
        out = [str(k).strip() for k in raw if str(k).strip()]
    else:
        partes = re.split(r"[;,\n]", str(raw))
        out = [p.strip() for p in partes if p.strip()]
    # Remove duplicatas mantendo ordem
    visto, dedup = set(), []
    for k in out:
        kl = k.lower()
        if kl not in visto:
            visto.add(kl)
            dedup.append(k)
    return dedup


def normalizar_autor(raw_autor: dict) -> dict | None:
    """Extrai (idDeputado da Câmara, nome, partido, uf, tipo). politico_id_prisma vem do Loader."""
    if not raw_autor:
        return None
    uri = raw_autor.get("uri") or ""
    id_camara = None
    if uri:
        m = re.search(r"/deputados/(\d+)", uri)
        if m:
            id_camara = int(m.group(1))
    # Fallback se vier idDeputadoAutor explícito
    id_camara = id_camara or raw_autor.get("idDeputadoAutor") or raw_autor.get("id")
    try:
        id_camara = int(id_camara) if id_camara is not None else None
    except (TypeError, ValueError):
        id_camara = None

    return {
        "id_camara":           id_camara,
        "nome":                limpar(raw_autor.get("nome")),
        "partido":             limpar(raw_autor.get("siglaPartido") or raw_autor.get("partido")),
        "uf":                  limpar(raw_autor.get("siglaUf") or raw_autor.get("uf")),
        "tipo":                limpar(raw_autor.get("tipo") or raw_autor.get("descricaoTipo")),
        "ordem_assinatura":    raw_autor.get("ordemAssinatura"),
        "proponente":          raw_autor.get("proponente"),
        "politico_id_prisma":  None,   # resolvido no Agent C
    }


def normalizar_registro(item: dict) -> dict | None:
    resumo  = item.get("_resumo")  or {}
    detalhe = item.get("_detalhe") or {}
    autores_raw = item.get("_autores") or []

    prop_id = resumo.get("id") or detalhe.get("id")
    tipo    = limpar(resumo.get("siglaTipo") or detalhe.get("siglaTipo"))
    numero  = resumo.get("numero") or detalhe.get("numero")
    ano     = resumo.get("ano") or detalhe.get("ano")

    if not prop_id:
        return {"_motivo": "id ausente", **item}
    if not tipo or not numero or not ano:
        return {"_motivo": "tipo/numero/ano ausentes", **item}

    ementa = limpar(resumo.get("ementa") or detalhe.get("ementa"))
    if not ementa:
        return {"_motivo": "ementa ausente", **item}

    status = detalhe.get("statusProposicao") or {}
    autores_norm = [a for a in (normalizar_autor(a) for a in autores_raw) if a is not None]

    chave_hash = f"{prop_id}|{tipo}|{numero}|{ano}|{ementa[:200]}"
    raw_hash   = sha256(chave_hash)

    return {
        "id":                          int(prop_id),
        "tipo":                        tipo,
        "numero":                      int(numero) if str(numero).isdigit() else numero,
        "ano":                         int(ano),
        "ementa":                      ementa,
        "ementa_detalhada":            limpar(detalhe.get("ementaDetalhada")),
        "data_apresentacao":           str(parse_date(resumo.get("dataApresentacao")
                                                     or detalhe.get("dataApresentacao")) or "") or None,
        "status_situacao":             limpar(status.get("descricaoSituacao")),
        "status_descricao_tramitacao": limpar(status.get("descricaoTramitacao")),
        "status_data":                 parse_datetime(status.get("dataHora")),
        "uri_orgao_atual":             limpar(status.get("uriOrgao")),
        "sigla_orgao_atual":           limpar(status.get("siglaOrgao")),
        "keywords":                    extrair_keywords(detalhe),
        "autores":                     autores_norm,
        "autores_politico_ids":        [],   # populado no Agent C após resolução
        "raw_hash":                    raw_hash,
    }


def processar_bronze(bronze_path: Path) -> None:
    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    meta    = bronze.get("meta", {})
    leg     = meta.get("legislatura")
    records = bronze.get("records", [])
    print(f"📊 Total bruto: {len(records):,}")

    validos, rejeitados = [], []
    for r in records:
        norm = normalizar_registro(r)
        if norm is None:
            continue
        if "_motivo" in norm:
            rejeitados.append(norm)
        else:
            validos.append(norm)

    # Deduplica por raw_hash mantendo o primeiro
    visto, dedup = set(), []
    for v in validos:
        h = v["raw_hash"]
        if h in visto:
            continue
        visto.add(h)
        dedup.append(v)

    stem = bronze_path.stem.replace("_bronze", "")
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "data_processamento": datetime.now(timezone.utc).isoformat(),
                "fonte_bronze":       bronze_path.name,
                "legislatura":        leg,
                "total_validos":      len(dedup),
                "total_rejeitados":   len(rejeitados),
                "dedup_removidas":    len(validos) - len(dedup),
            },
            "records": dedup,
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    taxa = len(rejeitados) / max(len(records), 1) * 100
    print(f"✅ Prata: {len(dedup):>8,} válidos → {prata_path.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados):,} ({taxa:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador Câmara Proposições")
    parser.add_argument("--bronze", help="Arquivo bronze específico")
    parser.add_argument("--todos",  action="store_true", help="Todos os bronzes disponíveis")
    args = parser.parse_args()

    if args.bronze:
        processar_bronze(Path(args.bronze))
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("proposicoes_*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("proposicoes_*_bronze.json"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0])

    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()
