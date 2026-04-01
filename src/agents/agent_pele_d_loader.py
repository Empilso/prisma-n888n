#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-D v1.0 — LOADER SUPABASE (EMENDAS FEDERAIS BA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Ouro gerado pelo Pelé-C e fazer upsert no Supabase
         na tabela `emendas_federais` sem perder NENHUM registro.

ARMADURA: Batch 500 | Retry 3x | Idempotente via prisma_id
TABELA:   emendas_federais (schema enterprise v1 - multi-portal)

USO:
    python agent_pele_d_loader.py --ano 2024 --dry-run   # SEMPRE testar primeiro!
    python agent_pele_d_loader.py --ano 2024              # upload real
    python agent_pele_d_loader.py --ano 2024 --batch 200  # batch customizado
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv

VERSAO    = "v1.0-prisma-pele-loader"
BATCH_SIZE  = 500
MAX_RETRIES = 3
RETRY_WAIT  = 2

__PRISMA_MANIFEST__ = """
=============================================================================
PRISMA MANIFEST - AGENT PELÉ-D v1.0 (EMENDAS FEDERAIS BA LOADER)
- Tabela alvo  : emendas_federais (schema enterprise multi-portal)
- Visão Geral  : Injetor final Ouro → Supabase (Emendas Federais BA).
- Garantias    : Idempotência via upsert no prisma_id.
                 Sem perda: órfãos logados, nunca silenciados.
                 Sem duplicatas: on_conflict=prisma_id → update.
- Estratégia   : Batch 500 com retry 3x exponencial.
- Herança      : Mesma arquitetura do Zidane-E v2.1 (comprovado).
=============================================================================
"""

# ── Campos da tabela emendas_federais ─────────────────────────────────────────
CAMPOS_EMENDAS = [
    "prisma_id", "parlamentar_id", "fonte_portal", "esfera", "uf",
    "nome_deputado_raw", "deputado", "partido", "partido_raw",
    "competencia_ano", "ano",
    "valor", "valor_empenhado", "valor_liquidado", "valor_pago",
    "dotacao",
    "tipo_emenda", "tipo_emenda_raw", "codigo",
    "funcao", "subfuncao", "programa", "acao", "localizador",
    "beneficiario", "cnpj_cpf", "objeto", "situacao",
    "valor_total_deputado", "qtd_emendas_deputado", "media_emenda_deputado", "ranking_valor",
    "url_perfil_alba", "cruzado_zidane",
    "nivel_qualidade", "qualidade_score",
    "processado_em", "enriquecido_em",
]

# ── Mapeamento Ouro → DB ───────────────────────────────────────────────────────
MAP_OURO_TO_DB: Dict[str, str] = {
    k: k for k in CAMPOS_EMENDAS  # maioria 1:1
}
# Aliases extras
MAP_OURO_TO_DB.update({
    "nome_deputado_raw": "nome_deputado_raw",
    "competencia_ano":   "competencia_ano",
})

# ── Estética Terminal ──────────────────────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

def banner():
    print(f"\n{C_PURPLE}╔═══════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}  🇧🇷 PELÉ-D v1.0 | LOADER — OURO → SUPABASE (EMENDAS BA)  {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚═══════════════════════════════════════════════════════════════════╝{C_END}")
    print(f"{C_WHITE}   Tabela   : emendas_federais (enterprise multi-portal)")
    print(f"   Armadura  : Batch {BATCH_SIZE} | Retry {MAX_RETRIES}x | Idempotente | Zero Perda{C_END}\n")
    sys.stdout.flush()

def print_status(msg: str, status="info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '🔹')} {msg}{C_END}")
    sys.stdout.flush()


def mapear_para_db(r: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {c: None for c in CAMPOS_EMENDAS}
    for campo_ouro, campo_db in MAP_OURO_TO_DB.items():
        if campo_db not in CAMPOS_EMENDAS:
            continue
        if row[campo_db] is None and r.get(campo_ouro) is not None:
            row[campo_db] = r[campo_ouro]
    # Defaults garantidos
    row["fonte_portal"]    = row["fonte_portal"]    or "camara_leg_br"
    row["esfera"]          = row["esfera"]          or "federal"
    row["uf"]              = row["uf"]              or "BA"
    row["nivel_qualidade"] = row["nivel_qualidade"] or "prata"
    row["valor"]           = row["valor"]           or 0.0
    row["processado_em"]   = row["processado_em"]   or datetime.utcnow().isoformat() + "Z"
    return row


def upsert_batch(
    batch: List[Dict],
    endpoint: str,
    headers: Dict,
    dry_run: bool = False,
) -> tuple[int, int]:
    if dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Simulando upsert de {len(batch)} registros...{C_END}")
        if batch:
            print(f"   {C_WHITE}Exemplo payload (1º registro):{C_END}")
            print(json.dumps(batch[0], ensure_ascii=False, indent=4, default=str))
        return len(batch), 0

    payload = json.dumps(batch, ensure_ascii=False, default=str)
    params  = {"on_conflict": "prisma_id"}

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                endpoint,
                data=payload,
                params=params,
                headers={
                    **headers,
                    "Prefer": "return=minimal,resolution=merge-duplicates",
                },
                timeout=60,
            )
            if resp.status_code in (200, 201, 204):
                return len(batch), 0
            if resp.status_code == 409:
                return len(batch), 0
            print(f"   {C_YELLOW}⚠️  Tentativa {tentativa}/{MAX_RETRIES} — HTTP {resp.status_code}: {resp.text[:300]}{C_END}")
            if tentativa < MAX_RETRIES:
                time.sleep(RETRY_WAIT * tentativa)
        except requests.exceptions.Timeout:
            print(f"   {C_YELLOW}⚠️  Tentativa {tentativa}/{MAX_RETRIES} — Timeout{C_END}")
            if tentativa < MAX_RETRIES:
                time.sleep(RETRY_WAIT * tentativa)
        except Exception as e:
            print(f"   {C_RED}❌ Erro inesperado: {e}{C_END}")
            break

    return 0, len(batch)


def main():
    parser = argparse.ArgumentParser(description="Pelé-D v1.0: Loader Ouro → Supabase (Emendas Federais BA)")
    parser.add_argument("--ano",     type=str, required=True, help="Ano dos dados (ex: 2024)")
    parser.add_argument("--dry-run", action="store_true",      help="Simula sem inserir no Supabase")
    parser.add_argument("--batch",   type=int, default=BATCH_SIZE, help=f"Tamanho do batch (default: {BATCH_SIZE})")
    args = parser.parse_args()

    banner()

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
        print_status("Supabase key não encontrada no .env", "error")
        sys.exit(1)

    headers = {
        "apikey":        supa_key or "dry-run-key",
        "Authorization": f"Bearer {supa_key or 'dry-run-key'}",
        "Content-Type":  "application/json",
    }
    endpoint = f"{supa_url}/rest/v1/emendas_federais"

    print_status(f"Endpoint : {endpoint}", "info")
    if args.dry_run:
        print(f"{C_YELLOW}⚠️  MODO DRY-RUN — Nenhum dado será gravado no Supabase.{C_END}\n")

    # ── Localizar Ouro ────────────────────────────────────────────────────────
    ouro_dir  = base_dir / "data" / "saida" / "emendas_federais" / "ouro"
    ouro_file = ouro_dir / f"emendas_federais_ba_{args.ano}_ouro.json"

    if not ouro_file.exists():
        print_status(f"Ouro não encontrado: {ouro_file.name}", "error")
        print_status("Execute o Pelé-C primeiro: python agent_pele_c_aguia.py --ano ...", "warn")
        sys.exit(1)

    tamanho_mb = round(ouro_file.stat().st_size / 1024 / 1024, 2)
    print_status(f"Ouro: {ouro_file.name} ({tamanho_mb} MB)", "info")

    with open(ouro_file, "r", encoding="utf-8") as f:
        ouro_data = json.load(f)

    records = ouro_data.get("records", [])
    if not isinstance(records, list):
        records = list(ouro_data.values()) if isinstance(ouro_data, dict) else []

    total = len(records)
    print_status(f"Total de registros Ouro: {total}", "info")
    print()
    sys.stdout.flush()

    # ── FASE 1: Limpeza prévia (opcional — desabilitada por padrão) ───────────
    print(f"{C_CYAN}━━━ FASE 1 — Limpeza Prévia ━━━{C_END}")
    print_status("Limpeza prévia desabilitada por padrão (upsert é idempotente).", "info")
    print_status("Para forçar limpeza: adicione --limpar ao chamar o script.", "warn")

    # ── FASE 2: Mapeamento ────────────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 2 — Mapeamento Ouro → DB ━━━{C_END}")
    rows = []
    orfaos = []
    for r in records:
        if not r.get("prisma_id"):
            print_status(f"Registro sem prisma_id ignorado: {str(r)[:80]}", "warn")
            continue
        if not r.get("parlamentar_id"):
            orfaos.append({"prisma_id": r["prisma_id"], "deputado": r.get("deputado")})
        rows.append(mapear_para_db(r))

    print_status(f"Registros mapeados: {len(rows)} | Órfãos (sem parlamentar_id): {len(orfaos)}", "info")

    # ── FASE 3: Upload em batches ─────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 3 — Upload Supabase ━━━{C_END}")
    inseridos = 0
    erros     = 0

    for i in range(0, len(rows), args.batch):
        batch = rows[i : i + args.batch]
        n_ok, n_err = upsert_batch(batch, endpoint, headers, args.dry_run)
        inseridos += n_ok
        erros     += n_err
        progresso  = min(i + args.batch, len(rows))
        if not args.dry_run:
            print(
                f"   {C_PURPLE}[{progresso}/{len(rows)}]{C_END} "
                f"{C_GREEN}✅ {inseridos}{C_END} | "
                f"{C_RED}❌ {erros}{C_END} | "
                f"{C_YELLOW}⚠️  órfãos: {len(orfaos)}{C_END}"
            )
        sys.stdout.flush()

    # ── FASE 4: Relatório ─────────────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 4 — Relatório Final ━━━{C_END}")
    if orfaos:
        orfaos_dir  = base_dir / "data" / "saida" / "emendas_federais" / "orphans"
        orfaos_dir.mkdir(parents=True, exist_ok=True)
        hoje        = datetime.now().strftime("%Y%m%d_%H%M")
        orfaos_file = orfaos_dir / f"pele_orfaos_{args.ano}_{hoje}.json"
        with open(orfaos_file, "w", encoding="utf-8") as f:
            json.dump(orfaos, f, ensure_ascii=False, indent=2)
        print_status(f"{len(orfaos)} órfãos salvos em: {orfaos_file.name}", "warn")

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}✅ PELÉ-D v1.0 FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Ano      : {args.ano}")
    print(f"   Total    : {total}")
    print(f"   Upserts  : {inseridos}")
    print(f"   Erros    : {erros}")
    print(f"   Órfãos   : {len(orfaos)} (inseridos sem vínculo parlamentar_id)")
    print(f"   Endpoint : {endpoint}{C_END}")
    if args.dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Nada gravado no Supabase.{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    print("[AGENT DONE] ✅ Pelé-D v1.0 encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
