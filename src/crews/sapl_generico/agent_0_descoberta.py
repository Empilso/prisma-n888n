#!/usr/bin/env python3
"""SAPL Genérico — Agent 0 (Descoberta de instâncias)

Não existe uma lista pronta e confiável de "quais câmaras usam SAPL" — o
diretório oficial do Interlegis (www12.senado.leg.br/interlegis/orgaosatendidos)
não respondeu de forma estável na pesquisa que originou esta crew (2026-07-21).
Alternativa validada manualmente: instâncias SAPL seguem o padrão de domínio

    https://sapl.{slug(nome_municipio)}.{uf}.leg.br

onde slug = nome do município sem acento, sem espaço, minúsculo. Confirmado
em 3 câmaras reais (Santarém-PA → sapl.santarem.pa.leg.br, Foz do Iguaçu-PR →
sapl.fozdoiguacu.pr.leg.br, Centenário do Sul-PR → sapl.centenariodosul.pr.leg.br).

Este agent testa o padrão contra TODOS os municípios de `municipios` (uma
requisição leve por município: GET .../api/parlamentares/parlamentar/?page=1
com timeout curto) e grava o resultado — nunca assume "não usa SAPL" sem
testar, e nunca assume "usa SAPL" sem uma resposta HTTP 200 com JSON válido
contendo "results".

Município sem resposta (timeout, DNS falho, 404, 500) fica marcado como
`sem_resposta` — pode ser: câmara sem SAPL, domínio fora do padrão, ou
instância temporariamente fora do ar. Não é erro, é um estado legítimo.

Saída: data/sapl_generico/bronze/instancias.json (lista completa testada,
idempotente — re-rodar não duplica, só atualiza `testado_em`).

Uso:
    python agent_0_descoberta.py --limit 50          # amostra (teste local)
    python agent_0_descoberta.py --uf PA             # só 1 UF
    python agent_0_descoberta.py --todos             # 5.570 municípios (RODAR NA VPS)
"""
import argparse
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2
import psycopg2.extras

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
DATA_DIR = BASE_DIR / "data/sapl_generico"
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PRISMA888/1.0 (dados abertos SAPL/Interlegis)"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}
TIMEOUT = 12
SLEEP = 0.3

DDL = """
CREATE TABLE IF NOT EXISTS sapl_instancias (
    municipio_ibge   char(7) PRIMARY KEY REFERENCES municipios(id_ibge),
    dominio          text NOT NULL,
    status           text NOT NULL,  -- ativo | sem_resposta | fora_do_padrao
    total_parlamentares_amostra integer,
    testado_em       timestamptz NOT NULL,
    UNIQUE (dominio)
);
CREATE INDEX IF NOT EXISTS idx_sapl_instancias_status ON sapl_instancias (status);
"""


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def slug(nome: str) -> str:
    """'Foz do Iguaçu' -> 'fozdoiguacu' (sem acento, sem espaço, minúsculo)."""
    nfkd = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def testar_dominio(dominio: str) -> tuple[str, int | None]:
    """Retorna (status, total_amostra). Nunca lança — falha vira 'sem_resposta'."""
    url = f"https://{dominio}/api/parlamentares/parlamentar/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, params={"page": 1})
        if r.status_code != 200:
            return "sem_resposta", None
        data = r.json()
        if not isinstance(data, dict) or "results" not in data:
            return "fora_do_padrao", None
        total = (data.get("pagination") or {}).get("total_entries")
        return "ativo", int(total) if total is not None else None
    except Exception:
        return "sem_resposta", None


def carregar_municipios(cur, uf: str | None, limit: int | None) -> list[dict]:
    sql = "SELECT id_ibge, nome, uf FROM municipios"
    params: list = []
    if uf:
        sql += " WHERE uf = %s"
        params.append(uf.upper())
    sql += " ORDER BY uf, nome"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    return cur.fetchall()


def main() -> None:
    ap = argparse.ArgumentParser(description="SAPL Genérico — Agent 0 (Descoberta de instâncias)")
    ap.add_argument("--uf", type=str, default=None, help="restringe a uma UF (ex.: PA)")
    ap.add_argument("--limit", type=int, default=None, help="limita nº de municípios testados (piloto)")
    ap.add_argument("--todos", action="store_true", help="testa todos os 5.570 municípios (rodar na VPS)")
    args = ap.parse_args()

    if not args.todos and not args.limit and not args.uf:
        ap.error("passe --limit N (piloto), --uf UF, ou --todos (carga completa)")

    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(DDL)
    conn.commit()

    municipios = carregar_municipios(cur, args.uf, args.limit)
    log(f"testando padrão de domínio SAPL em {len(municipios):,} município(s)")

    resultado, contagem = [], {"ativo": 0, "sem_resposta": 0, "fora_do_padrao": 0}
    for i, m in enumerate(municipios, 1):
        dominio = f"sapl.{slug(m['nome'])}.{m['uf'].lower()}.leg.br"
        status, total = testar_dominio(dominio)
        contagem[status] += 1
        agora = datetime.now(timezone.utc)
        registro = {
            "municipio_ibge": m["id_ibge"], "nome": m["nome"], "uf": m["uf"],
            "dominio": dominio, "status": status, "total_parlamentares_amostra": total,
            "testado_em": agora.isoformat(),
        }
        resultado.append(registro)
        cur.execute("""
            INSERT INTO sapl_instancias (municipio_ibge, dominio, status, total_parlamentares_amostra, testado_em)
            VALUES (%(municipio_ibge)s, %(dominio)s, %(status)s, %(total_parlamentares_amostra)s, %(testado_em)s)
            ON CONFLICT (municipio_ibge) DO UPDATE SET
                dominio = EXCLUDED.dominio, status = EXCLUDED.status,
                total_parlamentares_amostra = EXCLUDED.total_parlamentares_amostra,
                testado_em = EXCLUDED.testado_em
        """, registro)
        if status == "ativo":
            log(f"  ✅ {m['nome']}/{m['uf']} → {dominio} ({total or '?'} parlamentares)")
        if i % 100 == 0:
            conn.commit()
            log(f"  … {i}/{len(municipios)} testados | ativo={contagem['ativo']}")
        time.sleep(SLEEP)

    conn.commit()
    (BRONZE_DIR / "instancias.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ descoberta concluída: {contagem['ativo']} ativa(s) | "
        f"{contagem['sem_resposta']} sem resposta | {contagem['fora_do_padrao']} fora do padrão "
        f"(de {len(municipios):,} testados)")
    conn.close()


if __name__ == "__main__":
    main()
