#!/usr/bin/env python3
"""Agent B — Normalizador Câmara SP Verba de Gabinete: Bronze → Prata

Mapeia os campos do JSON do SisGV Consulta para o schema de
camara_sp_verba_gabinete. Tenta vincular vereadores ao politico_id via
fuzzy match de nome contra politicos.nome_urna (município=São Paulo,
cargo=VEREADOR) no banco.

id (PK) = SHA256(centro_custos_id|competencia|cnpj|despesa|valor)[:32]

Rejeições:
  - Valor ausente ou <= 0
  - CENTROCUSTOSID ausente
  - Ano/Mês inválido

Saída:
    data/camara_sp_verba_gabinete/prata/camara_sp_verba_prata.json
    data/camara_sp_verba_gabinete/rejeitados/camara_sp_verba_rejeitados.json
"""
import json
import re
import argparse
import hashlib
import psycopg2
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

try:
    from rapidfuzz import process, fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data/camara_sp_verba_gabinete"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

BRONZE_PATH = BRONZE_DIR / "camara_sp_verba_bronze.json"
PRATA_PATH = PRATA_DIR / "camara_sp_verba_prata.json"
REJEIT_PATH = REJEIT_DIR / "camara_sp_verba_rejeitados.json"

DB = dict(host="localhost", port=5432, dbname="prisma_data", user="postgres", password=DB_PASSWORD)

MUNICIPIO_IBGE_SP_CAPITAL = "3550308"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def limpar(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return None if not s else s


def parse_valor(v) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
        return d if d > 0 else None
    except InvalidOperation:
        return None


def carregar_indice_vereadores_sp() -> dict:
    """Carrega nome_urna → politico_id para vereadores de São Paulo capital."""
    try:
        conn = psycopg2.connect(**DB)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT ON (nome_urna) nome_urna, politico_id
            FROM politicos
            WHERE municipio_ibge = %s AND cargo = 'VEREADOR'
              AND politico_id IS NOT NULL
            ORDER BY nome_urna, ano_eleicao DESC
            """,
            (MUNICIPIO_IBGE_SP_CAPITAL,),
        )
        idx = {r[0].upper(): r[1] for r in cur.fetchall()}
        cur.close()
        conn.close()
        print(f"  🔗 Índice vereadores SP capital: {len(idx)} nomes")
        return idx
    except Exception as e:
        print(f"  ⚠️  Banco indisponível, politico_id será None: {e}")
        return {}


def resolver_politico_id(nome_vereador: str, idx: dict) -> tuple[str | None, str]:
    nome = nome_vereador.upper().strip()
    if nome in idx:
        return idx[nome], "exact"
    if HAS_FUZZ and idx:
        match = process.extractOne(nome, list(idx.keys()), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 80:
            return idx[match[0]], f"fuzzy:{match[1]}"
    return None, "sem_match"


def normalizar(r: dict, idx: dict) -> dict | None:
    centro_custos = r.get("CENTROCUSTOSID")
    vereador = limpar(r.get("VEREADOR"))
    ano_raw = r.get("ANO")
    mes_raw = r.get("MES")
    valor = parse_valor(r.get("VALOR"))
    cnpj_raw = limpar(r.get("CNPJ"))
    fornec = limpar(r.get("FORNECEDOR"))
    tipo = limpar(r.get("DESPESA"))

    if centro_custos is None:
        return {"_motivo": "centro_custos_id ausente", **r}
    if valor is None:
        return {"_motivo": "valor inválido ou zero", **r}
    try:
        ano = int(ano_raw)
        mes = int(mes_raw)
        if not (2010 <= ano <= 2030 and 1 <= mes <= 12):
            raise ValueError()
    except Exception:
        return {"_motivo": f"ano/mes inválido: {ano_raw}/{mes_raw}", **r}

    competencia = f"{ano:04d}-{mes:02d}"
    cnpj = re.sub(r"\D", "", cnpj_raw or "")
    cnpj = cnpj if len(cnpj) in (11, 14) else None
    centro_custos_id = int(centro_custos)

    chave = f"{centro_custos_id}|{competencia}|{cnpj or ''}|{tipo or ''}|{valor}"
    id_doc = sha256(chave)[:32]

    politico_id, metodo = resolver_politico_id(vereador or "", idx)

    return {
        "id": id_doc,
        "politico_id": politico_id,
        "centro_custos_id": centro_custos_id,
        "vereador_nome": vereador,
        "cnpj_fornecedor": cnpj,
        "nome_fornecedor": fornec,
        "tipo_despesa": tipo,
        "valor": str(valor),
        "mes": mes,
        "ano": ano,
        "competencia": competencia,
        "status_lneg": None,
        "_match_metodo": metodo,
    }


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador Câmara SP Verba de Gabinete")
    parser.add_argument("--bronze", default=str(BRONZE_PATH), help="Arquivo bronze")
    args = parser.parse_args()

    bronze_path = Path(args.bronze)
    if not bronze_path.exists():
        print(f"❌ Bronze não encontrado: {bronze_path}")
        return

    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    records = bronze.get("records", [])
    print(f"📊 Total bruto: {len(records):,}")

    print("🔗 Carregando índice de vereadores SP capital...")
    idx = carregar_indice_vereadores_sp()

    validos, rejeitados = [], []
    sem_pid = 0
    for r in records:
        norm = normalizar(r, idx)
        if norm is None:
            continue
        if "_motivo" in norm:
            rejeitados.append(norm)
        else:
            if not norm["politico_id"]:
                sem_pid += 1
            validos.append(norm)

    with open(PRATA_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "data_processamento": datetime.now(timezone.utc).isoformat(),
                    "fonte_bronze": bronze_path.name,
                    "total_validos": len(validos),
                    "total_rejeitados": len(rejeitados),
                    "sem_politico_id": sem_pid,
                },
                "records": validos,
            },
            f,
            ensure_ascii=False,
        )

    if rejeitados:
        with open(REJEIT_PATH, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    pct_pid = (len(validos) - sem_pid) / max(len(validos), 1) * 100
    print(f"✅ Prata: {len(validos):>7,} válidos → {PRATA_PATH.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados):,}")
    print(f"🔗 Com politico_id: {len(validos)-sem_pid:,} ({pct_pid:.1f}%)")
    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()
