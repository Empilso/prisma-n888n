#!/usr/bin/env python3
"""
🐘 AGENT ZIDANE-E | VERBAS LOADER — O Injetor de Ouro
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler todos os JSONs Ouro e fazer upsert no Supabase
         na tabela `verbas_gabinete` sem perder NENHUM registro.
ARMADURA: Batches de 500 | Retry 3x | Idempotente via prisma_id
TABELA:   verbas_gabinete (schema abaixo)

  prisma_id         TEXT PK
  parlamentar_id    TEXT → FK parlamentares.prisma_id
  nome_deputado_raw TEXT
  cnpj_fornecedor   TEXT
  nome_fornecedor   TEXT
  num_nf            TEXT
  num_nf_normalizado TEXT
  categoria_slug    TEXT
  categoria_original TEXT
  url_pdf_nf        TEXT
  valor             NUMERIC
  valor_glosado     NUMERIC
  valor_liquido     NUMERIC
  competencia_date  DATE
  competencia_ano   INT
  competencia_mes   INT
  ano               INT
  partido           TEXT
  fonte_portal      TEXT
  fonte_url         TEXT
  metadados         JSONB
  nivel_qualidade   TEXT
  processado_em     TIMESTAMPTZ

USO:
    python agent_zidane_e_verbas_loader.py              # todos os ouro disponíveis
    python agent_zidane_e_verbas_loader.py --year 2022  # só um ano
    python agent_zidane_e_verbas_loader.py --dry-run    # simula sem inserir
    python agent_zidane_e_verbas_loader.py --batch 200  # batch size customizado
"""

__PRISMA_MANIFEST__ = """
=============================================================================
PRISMA MANIFEST - AGENT ZIDANE-E (VERBAS LOADER)
- Visão Geral: Injetor final da Camada Ouro → Supabase.
- Garantias: Idempotência via upsert no prisma_id.
             Sem perda: órfãos logados, nunca silenciados.
             Sem duplicatas: onConflict=prisma_id → update.
- Estratégia: Batch 500 com retry 3x exponencial.
=============================================================================
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# --- Estética N888N ─────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

VERSION        = "zidane_e_v1.0"
BATCH_SIZE     = 500
MAX_RETRIES    = 3
RETRY_WAIT_SEC = 2

# ─── Campos do Supabase (schema verbas_gabinete) ──────────────────────────
CAMPOS_VERBAS = [
    "prisma_id", "parlamentar_id", "nome_deputado_raw",
    "cnpj_fornecedor", "nome_fornecedor",
    "num_nf", "num_nf_normalizado",
    "categoria_slug", "categoria_original",
    "url_pdf_nf",
    "valor", "valor_glosado", "valor_liquido",
    "competencia_date", "competencia_ano", "competencia_mes",
    "ano", "partido",
    "fonte_portal", "fonte_url",
    "metadados",
    "nivel_qualidade",   # coluna correta (sem typo 'nicel')
    "processado_em",
]


def banner():
    print(f"\n{C_PURPLE}╔════════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}    🐘 ZIDANE-E | VERBAS LOADER v1.0 — OURO → SUPABASE       {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚════════════════════════════════════════════════════════════════════╝{C_END}")
    print(f"{C_WHITE}Armadura: Batch {BATCH_SIZE} | Retry {MAX_RETRIES}x | Idempotente | Zero Perda{C_END}\n")
    sys.stdout.flush()


# ─── Supabase HTTP Helper ────────────────────────────────────────────────
def upsert_batch(
    batch: List[Dict],
    endpoint: str,
    headers: Dict,
    dry_run: bool = False
) -> tuple[int, int]:
    """
    Faz upsert de um batch no Supabase via REST.
    Retorna (n_inseridos_ou_atualizados, n_erros).
    """
    if dry_run:
        print(f"   {C_YELLOW}[DRY RUN] Simulando upsert de {len(batch)} registros...{C_END}")
        return len(batch), 0

    payload = json.dumps(batch, ensure_ascii=False, default=str)

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                endpoint,
                data=payload,
                headers={
                    **headers,
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                timeout=60,
            )
            if resp.status_code in (200, 201):
                return len(batch), 0
            elif resp.status_code == 409:
                # Conflito tratado pelo Prefer merge-duplicates
                return len(batch), 0
            else:
                print(f"   {C_YELLOW}⚠️  Tentativa {tentativa}/{MAX_RETRIES} — HTTP {resp.status_code}: {resp.text[:200]}{C_END}")
                if tentativa < MAX_RETRIES:
                    time.sleep(RETRY_WAIT_SEC * tentativa)
        except requests.exceptions.Timeout:
            print(f"   {C_YELLOW}⚠️  Tentativa {tentativa}/{MAX_RETRIES} — Timeout{C_END}")
            if tentativa < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SEC * tentativa)
        except Exception as e:
            print(f"   {C_RED}❌ Erro inesperado: {e}{C_END}")
            break

    return 0, len(batch)


# ─── Mapeamento Ouro → Schema Supabase ──────────────────────────────────
def mapear_para_supabase(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Garante que o registro Ouro está alinhado com o schema do Supabase.
    Corrige typo 'nicel_qualidade' → 'nivel_qualidade'.
    Remove campos extras que não existem na tabela.
    """
    row = {}
    for campo in CAMPOS_VERBAS:
        # Corrige typo histórico do Ronaldo Gold
        if campo == "nivel_qualidade":
            row[campo] = r.get("nivel_qualidade") or r.get("nicel_qualidade", "OURO")
        else:
            row[campo] = r.get(campo)
    return row


# ─── Loader Principal ────────────────────────────────────────────────────
def carregar_arquivo_ouro(
    ouro_path: Path,
    endpoint: str,
    headers: Dict,
    batch_size: int,
    dry_run: bool,
    stats: Dict,
):
    """Carrega um arquivo JSON Ouro e faz upsert em batches."""
    print(f"\n{C_CYAN}━━━ Carregando: {ouro_path.name} ({round(ouro_path.stat().st_size / 1024 / 1024, 1)} MB) ━━━{C_END}")
    sys.stdout.flush()

    with open(ouro_path, "r", encoding="utf-8") as f:
        registros = json.load(f)

    if not isinstance(registros, list):
        registros = registros.get("records", list(registros.values()))

    total = len(registros)
    print(f"   📂 {total} registros Ouro carregados.")
    sys.stdout.flush()

    inseridos = 0
    erros     = 0
    sem_parlamentar = 0

    for i in range(0, total, batch_size):
        batch_raw  = registros[i : i + batch_size]
        batch_rows = []

        for r in batch_raw:
            # Sem parlamentar_id → Quarentena (nunca silencioso)
            if not r.get("parlamentar_id"):
                sem_parlamentar += 1
                stats["orfaos"].append({
                    "arquivo": ouro_path.name,
                    "nome_deputado_raw": r.get("nome_deputado_raw"),
                    "prisma_id": r.get("prisma_id"),
                })
                continue
            batch_rows.append(mapear_para_supabase(r))

        if not batch_rows:
            continue

        n_ok, n_err = upsert_batch(batch_rows, endpoint, headers, dry_run)
        inseridos += n_ok
        erros     += n_err

        progresso = min(i + batch_size, total)
        print(
            f"   {C_PURPLE}[{ouro_path.stem}]{C_END} "
            f"{C_WHITE}{progresso}/{total}{C_END} | "
            f"{C_GREEN}✅ {inseridos}{C_END} | "
            f"{C_RED}❌ {erros}{C_END} | "
            f"{C_YELLOW}⚠️ sem_parl: {sem_parlamentar}{C_END}"
        )
        sys.stdout.flush()

    stats["total_inseridos"]  += inseridos
    stats["total_erros"]      += erros
    stats["total_sem_parl"]   += sem_parlamentar
    stats["arquivos_processados"].append({
        "arquivo": ouro_path.name,
        "total": total,
        "inseridos": inseridos,
        "erros": erros,
        "sem_parlamentar": sem_parlamentar,
    })

    print(
        f"   {C_GREEN}💾 {ouro_path.name} → {inseridos} upserts OK "
        f"| {erros} erros "
        f"| {sem_parlamentar} órfãos{C_END}"
    )
    sys.stdout.flush()


# ─── MAIN ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Zidane-E: Verbas Loader Ouro → Supabase")
    parser.add_argument("--year",    type=str, default=None,         help="Processar só um ano (ex: 2022)")
    parser.add_argument("--dry-run", action="store_true",            help="Simula sem inserir no Supabase")
    parser.add_argument("--batch",   type=int, default=BATCH_SIZE,   help=f"Tamanho do batch (default: {BATCH_SIZE})")
    args = parser.parse_args()

    banner()

    # ── Env ───────────────────────────────────────────────────────────────
    base_dir = Path(__file__).resolve().parent.parent.parent
    load_dotenv(dotenv_path=base_dir / ".env")

    project_id = os.getenv("DADOS_PRISMA_PROJECT", "hrrzwhkosgzungqxlcps")
    supa_url   = f"https://{project_id}.supabase.co"
    supa_key   = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_DADOS_PRISMA_KEY")
        or os.getenv("SUPABASE_KEY")
    )

    if not supa_key and not args.dry_run:
        print(f"{C_RED}[ZIDANE-E] ❌ Supabase key não encontrada no .env{C_END}")
        sys.exit(1)

    headers = {
        "apikey":        supa_key or "dry-run-key",
        "Authorization": f"Bearer {supa_key or 'dry-run-key'}",
        "Content-Type":  "application/json",
    }
    endpoint = f"{supa_url}/rest/v1/verbas_gabinete"

    print(f"{C_WHITE}🎯 Endpoint: {endpoint}{C_END}")
    if args.dry_run:
        print(f"{C_YELLOW}⚠️  MODO DRY-RUN ATIVADO — Nenhum dado será gravado.{C_END}")
    print()
    sys.stdout.flush()

    # ── Resolve arquivos Ouro ─────────────────────────────────────────────
    ouro_dir = base_dir / "data" / "saida" / "ouro"

    if args.year:
        arquivos = sorted(ouro_dir.glob(f"verbas_{args.year}_gold_*.json"))
        if not arquivos:
            print(f"{C_RED}[ZIDANE-E] ❌ Nenhum arquivo Ouro encontrado para o ano {args.year} em {ouro_dir}{C_END}")
            sys.exit(1)
    else:
        arquivos = sorted(ouro_dir.glob("verbas_*_gold_*.json"))
        if not arquivos:
            print(f"{C_RED}[ZIDANE-E] ❌ Nenhum arquivo Ouro encontrado em {ouro_dir}{C_END}")
            sys.exit(1)

    print(f"{C_WHITE}📦 {len(arquivos)} arquivo(s) Ouro na fila:{C_END}")
    for a in arquivos:
        size_mb = round(a.stat().st_size / 1024 / 1024, 1)
        print(f"   • {a.name} ({size_mb} MB)")
    print()
    sys.stdout.flush()

    # ── Estatísticas globais ──────────────────────────────────────────────
    stats = {
        "total_inseridos": 0,
        "total_erros": 0,
        "total_sem_parl": 0,
        "arquivos_processados": [],
        "orfaos": [],
        "inicio": datetime.utcnow().isoformat() + "Z",
    }

    # ── Processa cada arquivo ─────────────────────────────────────────────
    for ouro_path in arquivos:
        carregar_arquivo_ouro(
            ouro_path=ouro_path,
            endpoint=endpoint,
            headers=headers,
            batch_size=args.batch,
            dry_run=args.dry_run,
            stats=stats,
        )

    # ── Salva relatório de órfãos ─────────────────────────────────────────
    if stats["orfaos"]:
        orfaos_dir = base_dir / "data" / "saida" / "verbas" / "orphans"
        orfaos_dir.mkdir(parents=True, exist_ok=True)
        hoje = datetime.now().strftime("%Y%m%d_%H%M")
        orfaos_path = orfaos_dir / f"loader_orfaos_{hoje}.json"
        with open(orfaos_path, "w", encoding="utf-8") as f:
            json.dump(stats["orfaos"], f, ensure_ascii=False, indent=2)
        print(f"\n{C_YELLOW}⚠️  {len(stats['orfaos'])} órfãos salvos em: {orfaos_path.name}{C_END}")

    # ── Resumo Final ──────────────────────────────────────────────────────
    stats["fim"] = datetime.utcnow().isoformat() + "Z"
    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}✅ ZIDANE-E FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Arquivos processados : {len(stats['arquivos_processados'])}")
    print(f"   Total upserts OK    : {stats['total_inseridos']}")
    print(f"   Total erros         : {stats['total_erros']}")
    print(f"   Total sem vínculo   : {stats['total_sem_parl']}")
    print(f"   Endpoint            : {endpoint}{C_END}")
    if args.dry_run:
        print(f"   {C_YELLOW}[DRY RUN] Nenhum dado foi gravado no Supabase.{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    print(f"[AGENT DONE] ✅ Zidane-E encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
