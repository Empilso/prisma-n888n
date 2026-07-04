#!/usr/bin/env python3
"""Agent B — Normalizador PNCP: Bronze JSON → Prata JSON

Limpa e normaliza contratos brutos da API PNCP:
- Extrai campos canônicos do JSON nested
- Limpa CNPJ (só dígitos, valida 14 chars)
- Mapeia municipio_ibge pelo código já vindo da API
- Classifica esfera (U=União/Federal, E=Estadual, M=Municipal)
- Calcula raw_hash por numeroControlePNCP

Execução:
    python agent_b_normalizador.py --todos
    python agent_b_normalizador.py --arquivo pncp_20250101_20250131.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BRONZE_DIR  = Path(__file__).parent / "data" / "pncp_contratos" / "bronze"
PRATA_DIR   = Path(__file__).parent / "data" / "pncp_contratos" / "prata"
REJECT_DIR  = Path(__file__).parent / "data" / "pncp_contratos" / "rejeitados"


def _limpar_cnpj(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 14 else None


def _esfera(item: dict) -> str:
    """U = União | E = Estadual | M = Municipal."""
    poder_id = (item.get("orgaoEntidade") or {}).get("poderId", "")
    esfera_id = (item.get("orgaoEntidade") or {}).get("esferaId", "")
    if esfera_id == "F" or poder_id in ("L", "E", "J", "M"):
        return "U"
    ibge = (item.get("unidadeOrgao") or {}).get("codigoIbge", "")
    if ibge and len(str(ibge).strip()) == 7:
        return "M"
    if ibge and len(str(ibge).strip()) == 2:
        return "E"
    return "U"


def _raw_hash(controle: str | None, item: dict) -> str:
    key = controle or json.dumps(item, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(key.encode()).hexdigest()


def normalizar_item(raw: dict) -> dict | None:
    """Retorna dict normalizado ou None se inválido."""
    controle = raw.get("numeroControlePNCP") or raw.get("numero_controle_pncp")
    if not controle:
        return None  # sem chave única — descarta

    orgao      = raw.get("orgaoEntidade") or {}
    unidade    = raw.get("unidadeOrgao") or {}
    contratado = raw.get("niFornecedor") or raw.get("cnpjFornecedor")

    ibge_raw = str(unidade.get("codigoIbge") or "").strip()
    municipio_ibge = ibge_raw if ibge_raw and len(ibge_raw) == 7 else None

    return {
        "id":                     controle,
        "numero_controle_pncp":   controle,
        "numero_contrato":        raw.get("numeroContrato"),
        "ano_contrato":           raw.get("anoContrato") or raw.get("ano"),
        "cnpj_orgao":             _limpar_cnpj(orgao.get("cnpj")),
        "nome_orgao":             orgao.get("razaoSocial"),
        "esfera":                 _esfera(raw),
        "uf":                     unidade.get("ufSigla"),
        "municipio_ibge":         municipio_ibge,
        "municipio_nome":         unidade.get("municipioNome"),
        "cnpj_contratado":        _limpar_cnpj(contratado),
        "nome_contratado":        raw.get("nomeFornecedor"),
        "objeto":                 raw.get("objetoContrato") or raw.get("objeto"),
        "valor_global":           raw.get("valorGlobal") or raw.get("valor_global"),
        "data_assinatura":        raw.get("dataAssinatura"),
        "data_vigencia_inicio":   raw.get("dataVigenciaInicio"),
        "data_vigencia_fim":      raw.get("dataVigenciaFim") or raw.get("data_vigencia_fim"),
        "modalidade":             (raw.get("modalidadeNome") or
                                   (raw.get("modalidadeContratacao") or {}).get("descricao")),
        "categoria_processo":     (raw.get("categoriaProcesso") or {}).get("nome") if isinstance(raw.get("categoriaProcesso"), dict) else raw.get("categoriaProcesso"),
        "tipo_contrato":          (raw.get("tipoContratoNome") or
                                   (raw.get("tipoContrato") or {}).get("nome")),
        "situacao":               raw.get("situacaoContrato") or raw.get("situacao"),
        "orgao":                  orgao.get("razaoSocial"),  # alias compatibilidade
        "unidade_gestora":        unidade.get("descricao") or unidade.get("municipioNome"),
        "processo":               raw.get("processo"),
        "link_pncp":              (f"https://pncp.gov.br/app/contratos/{controle}"
                                   if controle else None),
        "raw_hash":               _raw_hash(controle, raw),
        "status_lneg":            "PENDENTE",
    }


def processar_arquivo(bronze_path: Path) -> tuple[int, int]:
    """Retorna (validos, rejeitados)."""
    raw = json.loads(bronze_path.read_text(encoding="utf-8"))
    items = raw.get("items", [])

    validos, rejeitados = [], []
    for item in items:
        norm = normalizar_item(item)
        if norm:
            validos.append(norm)
        else:
            rejeitados.append(item)

    PRATA_DIR.mkdir(parents=True, exist_ok=True)
    prata_path = PRATA_DIR / bronze_path.name
    prata_path.write_text(
        json.dumps({"total": len(validos), "items": validos}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if rejeitados:
        REJECT_DIR.mkdir(parents=True, exist_ok=True)
        (REJECT_DIR / bronze_path.name).write_text(
            json.dumps(rejeitados, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return len(validos), len(rejeitados)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--todos",   action="store_true")
    parser.add_argument("--arquivo", help="Nome do arquivo bronze (sem caminho)")
    args = parser.parse_args()

    if args.todos:
        files = sorted(BRONZE_DIR.glob("pncp_*.json"))
    elif args.arquivo:
        files = [BRONZE_DIR / args.arquivo]
    else:
        parser.error("Forneça --todos ou --arquivo")

    total_v, total_r = 0, 0
    for f in files:
        v, r = processar_arquivo(f)
        print(f"[{f.name}] {v} válidos | {r} rejeitados")
        total_v += v
        total_r += r

    print(f"\n📊 Resumo: {total_v:,} válidos | {total_r:,} rejeitados ({total_r/(total_v+total_r)*100:.1f}% rej)" if (total_v+total_r) > 0 else "Nenhum arquivo processado.")
    print("✅ Agent B concluído.")
