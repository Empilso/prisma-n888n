#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-D v2.0 — LOADER SUPABASE (EMENDAS ESTADUAIS BA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Ouro gerado pelo Pelé-C e fazer upsert no Supabase
         na tabela `alba_emendas_master` sem perder NENHUM registro.

ARMADURA: Batch 500 | Retry 3x | Idempotente via id (uuid)
TABELA:   alba_emendas_master (schema PRISMA — emendas estaduais BA)

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

VERSAO    = "v2.0-prisma-pele-loader-estadual"
BATCH_SIZE  = 500
MAX_RETRIES = 3
RETRY_WAIT  = 2

__PRISMA_MANIFEST__ = """
=============================================================================
PRISMA MANIFEST - AGENT PELÉ-D v2.0 (EMENDAS ESTADUAIS BA LOADER)
- Tabela alvo  : alba_emendas_master (emendas estaduais BA — SIGA-BA)
- Esfera       : estadual
- UF           : BA
- Fonte portal : siga_ba
- Visão Geral  : Injetor final Ouro → alba_emendas_master.
- Garantias    : Idempotência via INSERT sem on_conflict (tabela usa id uuid).
                 Sem perda: órfãos logados, nunca silenciados.
- Estratégia   : Batch 500 com retry 3x exponencial.
- Campos gerados pelo DB (NÃO inserir):
                 percentual_empenhado, percentual_pago (colunas generated)
=============================================================================
"""

# ── Campos da tabela alba_emendas_master (excluindo colunas geradas) ───────────
CAMPOS_ALBA = [
    "parlamentar_id",
    "parlamentar_nome",
    "ano",
    "numero_emenda",
    "tipo_emenda",
    "orgao",
    "funcao",
    "subfuncao",
    "programa",
    "acao",
    "valor_orcado_atual",
    "valor_empenhado",
    "valor_liquidado",
    "valor_pago",
    "valor_restos_pagar",
    # percentual_empenhado → GERADO pelo banco — NÃO incluir
    # percentual_pago      → GERADO pelo banco — NÃO incluir
    "municipio",
    "uf",
    "fonte_portal",
    "url_transparencia",
    "nivel_qualidade",
    "metadados",
    "coletado_em",
]

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
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}  🇧🇷 PELÉ-D v2.0 | LOADER — OURO → alba_emendas_master (BA)  {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚═══════════════════════════════════════════════════════════════════╝{C_END}")
    print(f"{C_WHITE}   Tabela   : alba_emendas_master (emendas estaduais BA — SIGA-BA)")
    print(f"   Esfera    : estadual | UF: BA | Fonte: siga_ba")
    print(f"   Armadura  : Batch {BATCH_SIZE} | Retry {MAX_RETRIES}x | Idempotente | Zero Perda{C_END}\n")
    sys.stdout.flush()

def print_status(msg: str, status="info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '🔹')} {msg}{C_END}")
    sys.stdout.flush()


def mapear_para_alba(r: Dict[str, Any]) -> Dict[str, Any]:
    """Filtra apenas os campos aceitos pela tabela alba_emendas_master."""
    row: Dict[str, Any] = {}
    for campo in CAMPOS_ALBA:
        val = r.get(campo)
        row[campo] = val

    # Defaults obrigatórios
    row["uf"]             = row.get("uf") or "BA"
    row["fonte_portal"]   = row.get("fonte_portal") or "siga_ba"
    row["nivel_qualidade"]= row.get("nivel_qualidade") or "prata"
    row["valor_orcado_atual"]  = row.get("valor_orcado_atual") or 0
    row["valor_empenhado"]     = row.get("valor_empenhado") or 0
    row["valor_liquidado"]     = row.get("valor_liquidado") or 0
    row["valor_pago"]          = row.get("valor_pago") or 0
    row["valor_restos_pagar"]  = row.get("valor_restos_pagar") or 0
    row["coletado_em"]  = row.get("coletado_em") or datetime.utcnow().isoformat() + "Z"

    return row


def upsert_batch(
    batch: List[Dict],
    endpoint: str,
    headers: Dict,
    dry_run: bool = False,
) -> tuple[int, int]:
    if dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Simulando insert de {len(batch)} registros...{C_END}")
        if batch:
            print(f"   {C_WHITE}Exemplo payload (1º registro):{C_END}")
            print(json.dumps(batch[0], ensure_ascii=False, indent=4, default=str))
        return len(batch), 0

    payload = json.dumps(batch, ensure_ascii=False, default=str)

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                endpoint,
                data=payload,
                headers={
                    **headers,
                    "Prefer": "return=minimal",
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
    parser = argparse.ArgumentParser(
        description="Pelé-D v2.0: Loader Ouro → alba_emendas_master (Estadual BA)"
    )
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
    endpoint = f"{supa_url}/rest/v1/alba_emendas_master"

    print_status(f"Endpoint : {endpoint}", "info")
    if args.dry_run:
        print(f"{C_YELLOW}⚠️  MODO DRY-RUN — Nenhum dado será gravado no Supabase.{C_END}\n")

    # ── Localizar Ouro ────────────────────────────────────────────────────────
    ouro_dir  = base_dir / "data" / "saida" / "pele" / "ouro"
    ouro_file = ouro_dir / f"pele_estadual_{args.ano}_ouro.json"

    if not ouro_file.exists():
        print_status(f"Ouro não encontrado: {ouro_file.name}", "error")
        print_status(f"Execute o Pelé-C primeiro: python agent_pele_c_aguia.py --ano {args.ano}", "warn")
        sys.exit(1)

    tamanho_mb = round(ouro_file.stat().st_size / 1024 / 1024, 2)
    print_status(f"Ouro: {ouro_file.name} ({tamanho_mb} MB)", "info")

    with open(ouro_file, "r", encoding="utf-8") as f:
        ouro_data = json.load(f)

    records = ouro_data.get("records", [])
    total   = len(records)
    print_status(f"Total de registros Ouro: {total}", "info")
    print()
    sys.stdout.flush()

    # ── FASE 1: Informativo ───────────────────────────────────────────────────
    print(f"{C_CYAN}━━━ FASE 1 — Verificação ━━━{C_END}")
    print_status(f"Tabela alvo: alba_emendas_master (esfera=estadual, uf=BA, fonte=siga_ba)", "info")
    print_status(f"Colunas geradas pelo DB (excluídas do payload): percentual_empenhado, percentual_pago", "warn")

    # ── FASE 2: Mapeamento ────────────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 2 — Mapeamento Ouro → alba_emendas_master ━━━{C_END}")
    rows = []
    orfaos = []
    for r in records:
        if not r.get("parlamentar_id"):
            orfaos.append({"parlamentar_nome": r.get("parlamentar_nome"), "ano": r.get("ano")})
        rows.append(mapear_para_alba(r))

    print_status(f"Registros mapeados: {len(rows)} | Órfãos (sem parlamentar_id): {len(orfaos)}", "info")

    # ── FASE 3: Upload em batches ─────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 3 — Upload Supabase (alba_emendas_master) ━━━{C_END}")
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
        orfaos_dir  = base_dir / "data" / "saida" / "pele" / "orphans"
        orfaos_dir.mkdir(parents=True, exist_ok=True)
        hoje        = datetime.now().strftime("%Y%m%d_%H%M")
        orfaos_file = orfaos_dir / f"pele_orfaos_{args.ano}_{hoje}.json"
        with open(orfaos_file, "w", encoding="utf-8") as f:
            json.dump(orfaos, f, ensure_ascii=False, indent=2)
        print_status(f"{len(orfaos)} órfãos salvos em: {orfaos_file.name}", "warn")

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}✅ PELÉ-D v2.0 FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Ano      : {args.ano}")
    print(f"   Total    : {total}")
    print(f"   Inseridos: {inseridos}")
    print(f"   Erros    : {erros}")
    print(f"   Órfãos   : {len(orfaos)} (inseridos sem vínculo parlamentar_id)")
    print(f"   Tabela   : alba_emendas_master")
    print(f"   Endpoint : {endpoint}{C_END}")
    if args.dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Nada gravado no Supabase.{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    print("[AGENT DONE] ✅ Pelé-D v2.0 encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
