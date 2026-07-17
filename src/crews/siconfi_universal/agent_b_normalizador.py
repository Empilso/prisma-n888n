#!/usr/bin/env python3
"""Agent B — Normalizador SICONFI Universal: Bronze → Prata

Lê Bronzes gerados por Agent A e produz Prata padronizado para as tabelas
siconfi_rreo / siconfi_rgf / siconfi_dca em prisma_data.

Campos canônicos (saída Prata):
    id_ente, ente_tipo, ente_nome, uf, exercicio, periodo, anexo,
    conta, coluna, valor, raw_hash

Regras:
    - valor: aceita float, int, string com vírgula BR (1.234,56) ou notação US.
      Strings vazias / nulas / 'NaN' → None
    - raw_hash = SHA256 de (id_ente|exercicio|periodo|anexo|conta|coluna|valor_raw)
      — garante idempotência no Loader (ON CONFLICT raw_hash)
    - Rejeita: sem conta OR sem valor numérico

Saída:
    data/siconfi_universal/prata/{documento}/{ano}/{stem}_prata.json
    data/siconfi_universal/rejeitados/{documento}/{ano}/{stem}_rejeitados.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR    = BASE_DIR / "data" / "siconfi_universal"
BRONZE_DIR  = DATA_DIR / "bronze"
PRATA_DIR   = DATA_DIR / "prata"
REJEIT_DIR  = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Campos possíveis no payload SICONFI ─────────────────────────────────────
# A API SICONFI retorna em 'items' uma lista de dicts. As chaves variam por
# documento/anexo, mas o padrão mais comum nos retornos JSON ORDS é:
#   instituicao, cod_ibge, populacao, uf, exercicio, periodo, periodicidade,
#   conta, coluna, cod_conta, valor, anexo
COL_CONTA  = ["conta",  "Conta",  "rotulo", "descricao_conta"]
COL_COLUNA = ["coluna", "Coluna", "rotulo_coluna", "nome_coluna"]
COL_VALOR  = ["valor",  "Valor",  "vl_valor"]
COL_ENTE   = ["cod_ibge", "id_ente", "codigo_ibge", "co_ente"]
COL_NOME   = ["instituicao", "ente", "nome_ente", "no_ente"]
COL_UF     = ["uf", "UF", "sigla_uf"]
COL_EXERC  = ["exercicio", "an_exercicio", "ano"]
COL_PERIOD = ["periodo", "nr_periodo", "bimestre", "quadrimestre"]
COL_ANEXO  = ["anexo", "no_anexo"]


def get_col(row: dict, candidatos: list[str]) -> str | None:
    for c in candidatos:
        if c in row and row[c] not in (None, "", "null"):
            return row[c]
    return None


def parse_valor(v) -> Decimal | None:
    """Aceita float/int/str BR (1.234,56) ou US (1234.56)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "null", "none", "-"):
        return None
    # Detecta separador decimal: o que vier por último
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def computar_raw_hash(id_ente: str, exercicio: int, periodo: int,
                      anexo: str, conta: str, coluna: str | None,
                      valor_raw) -> str:
    chave = f"{id_ente}|{exercicio}|{periodo}|{anexo}|{conta}|{coluna or ''}|{valor_raw}"
    return sha256(chave)


def normalizar_registro(r: dict, meta: dict) -> dict | None:
    conta  = get_col(r, COL_CONTA)
    coluna = get_col(r, COL_COLUNA)
    valor_raw = get_col(r, COL_VALOR)
    valor = parse_valor(valor_raw)

    if not conta:
        return {"_motivo": "conta_ausente", **r}
    if valor is None:
        return {"_motivo": "valor_invalido", **r, "_conta": conta, "_coluna": coluna}

    id_ente = str(meta["id_ente"])
    exerc   = int(meta["ano"])
    periodo = int(meta.get("periodo", 0) or 0)
    anexo   = str(meta["anexo"])
    # DCA: o endpoint /dca retorna todos os anexos numa chamada só, então o meta
    # traz o placeholder "DCA_TODOS" — o anexo real (ex. "DCA-Anexo I-AB") vem em
    # cada registro. RREO/RGF mantêm o anexo do meta (formato "RREO_Anexo_N" já
    # consolidado em 3,9M linhas de siconfi_rreo — não mudar retroativamente).
    if (meta.get("documento") or "").upper() == "DCA":
        anexo_rec = get_col(r, COL_ANEXO)
        if anexo_rec:
            anexo = str(anexo_rec).strip()

    return {
        "id_ente":   id_ente,
        "ente_tipo": meta["ente_tipo"],
        "ente_nome": meta.get("ente_nome") or get_col(r, COL_NOME),
        "uf":        meta["ente_uf"],
        "exercicio": exerc,
        "periodo":   periodo,
        "anexo":     anexo,
        "conta":     str(conta).strip(),
        "coluna":    str(coluna).strip() if coluna else None,
        "valor":     str(valor),
        "raw_hash":  computar_raw_hash(id_ente, exerc, periodo, anexo,
                                       str(conta).strip(),
                                       str(coluna).strip() if coluna else None,
                                       valor_raw),
    }


def documento_de_bronze(meta: dict) -> str:
    doc = (meta.get("documento") or "").upper()
    if doc in ("RREO", "RGF", "DCA"):
        return doc
    # fallback: tenta inferir do anexo
    anexo = (meta.get("anexo") or "").upper()
    if anexo.startswith("RREO"): return "RREO"
    if anexo.startswith("RGF"):  return "RGF"
    if anexo.startswith("DCA"):  return "DCA"
    return "RREO"


def caminho_prata(documento: str, ano: int, stem: str) -> Path:
    out_dir = PRATA_DIR / documento.lower() / str(ano)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{stem}_prata.json"


def caminho_rejeitados(documento: str, ano: int, stem: str) -> Path:
    out_dir = REJEIT_DIR / documento.lower() / str(ano)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{stem}_rejeitados.json"


def processar_bronze(bronze_path: Path) -> tuple[int, int]:
    """Retorna (n_validos, n_rejeitados)."""
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    meta = bronze.get("meta", {})
    records = bronze.get("records", [])
    documento = documento_de_bronze(meta)
    ano = int(meta.get("ano", 0))

    validos, rejeitados = [], []
    for r in records:
        norm = normalizar_registro(r, meta)
        if norm is None:
            continue
        if "_motivo" in norm:
            rejeitados.append(norm)
        else:
            validos.append(norm)

    stem = bronze_path.stem.replace("_bronze", "")

    prata_path = caminho_prata(documento, ano, stem)
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "data_processamento": datetime.now(timezone.utc).isoformat(),
                "fonte_bronze":       bronze_path.name,
                "documento":          documento,
                "ano":                ano,
                "id_ente":            meta.get("id_ente"),
                "ente_tipo":          meta.get("ente_tipo"),
                "ente_uf":            meta.get("ente_uf"),
                "total_validos":      len(validos),
                "total_rejeitados":   len(rejeitados),
            },
            "records": validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        rej_path = caminho_rejeitados(documento, ano, stem)
        with open(rej_path, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    return len(validos), len(rejeitados)


def iterar_bronzes(documento: str | None) -> list[Path]:
    if documento:
        base = BRONZE_DIR / documento.lower()
        if not base.exists():
            return []
        return sorted(base.rglob("*_bronze.json"))
    return sorted(BRONZE_DIR.rglob("*_bronze.json"))


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador SICONFI Universal")
    parser.add_argument("--documento", choices=["RREO", "RGF", "DCA"], default=None)
    parser.add_argument("--bronze", help="Bronze específico")
    parser.add_argument("--todos", action="store_true", help="Processa todos os bronzes")
    args = parser.parse_args()

    if args.bronze:
        bronzes = [Path(args.bronze)]
    elif args.todos:
        bronzes = iterar_bronzes(args.documento)
    else:
        bronzes = iterar_bronzes(args.documento)
        if bronzes:
            bronzes = sorted(bronzes, key=lambda p: p.stat().st_mtime, reverse=True)[:1]

    if not bronzes:
        print("❌ Nenhum Bronze encontrado.")
        return

    print(f"📂 {len(bronzes):,} bronze(s) a processar")
    tot_val = tot_rej = 0
    for b in bronzes:
        try:
            v, r = processar_bronze(b)
        except Exception as e:
            print(f"  ❌ Falha em {b.name}: {e}")
            continue
        tot_val += v
        tot_rej += r
        if len(bronzes) <= 30:
            print(f"  ✅ {b.name}: {v:,} válidos | {r:,} rejeitados")

    print(f"\n📊 Resumo: {tot_val:,} válidos | {tot_rej:,} rejeitados "
          f"({(tot_rej / max(tot_val + tot_rej, 1) * 100):.1f}%)")
    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()
