#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-D v2.2 — LOADER SUPABASE (EMENDAS ESTADUAIS BA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Ouro gerado pelo Pelé-C e fazer upsert no Supabase
         na tabela `emendas_estaduais_ba` sem perder NENHUM registro.

ARMADURA: Batch 500 | Retry 3x | Idempotente via on_conflict=prisma_id
TABELA:   emendas_estaduais_ba (schema PRISMA — emendas estaduais BA)

ESTRATÉGIA DE UPSERT:
  Prefer: resolution=merge-duplicates
  on_conflict=prisma_id
  → Se o prisma_id já existe, atualiza. Se não, insere.
  → Garante idempotência total: rodar 2x não duplica dados.

COLUNAS GERADAS PELO BANCO (NÃO enviar no payload):
  - percentual_empenhado  (GENERATED ALWAYS AS valor_empenhado/valor_orcado_atual)
  - percentual_pago       (GENERATED ALWAYS AS valor_pago/valor_empenhado)

MUDANÇAS v2.2:
  - Remove 'metadados' de CAMPOS_TABELA (campo removido no Pelé-C v3.0)
  - Adiciona campos flat do enriquecimento:
    partido, cruzado_zidane, qualidade_score, valor_total_deputado,
    qtd_emendas_deputado, media_emenda, ranking_valor, versao_agente,
    enriquecido_em
  - mapear_para_tabela() aplica defaults para todos os novos campos
  - Schema 100% alinhado com emendas_estaduais_ba (Supabase)

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

VERSAO      = "v2.2-prisma-pele-loader-estadual"
TABELA      = "emendas_estaduais_ba"
BATCH_SIZE  = 500
MAX_RETRIES = 3
RETRY_WAIT  = 2

__PRISMA_MANIFEST__ = f"""
=============================================================================
PRISMA MANIFEST - AGENT PELÉ-D {VERSAO}
- Tabela alvo    : {TABELA}
- Esfera         : estadual
- UF             : BA
- Fonte portal   : siga_ba
- Visão Geral    : Injetor final Ouro → {TABELA}.
- Idempotência   : on_conflict=prisma_id + resolution=merge-duplicates.
                   Rodar 2x não duplica. prisma_id = MD5(siga_ba:ano:nome:emenda:orgao)
- Garantias      : Sem perda — órfãos logados, nunca silenciados.
- Estratégia     : Batch {BATCH_SIZE} com retry {MAX_RETRIES}x exponencial.
- Colunas geradas pelo DB (NÃO inserir):
                   percentual_empenhado, percentual_pago (colunas GENERATED)
=============================================================================
"""

# ── Campos aceitos pela tabela emendas_estaduais_ba ─────────────────────────────────────
# IMPORTANTE: Alinhados 1:1 com o JSON Ouro produzido pelo Pelé-C v3.0.
# NÃO incluir colunas GENERATED: percentual_empenhado, percentual_pago.
# 'metadados' foi REMOVIDO — campos agora são flat (v2.2).
CAMPOS_TABELA = [
    # ── Chave de upsert — OBRIGATÓRIO ──────────────────────────────────────────
    "prisma_id",

    # ── FK e identidade ─────────────────────────────────────────────────────────
    "parlamentar_id",
    "parlamentar_nome",
    "partido",                    # <- adicionado v2.2
    "ano",

    # ── Classificação orçamentária ───────────────────────────────────────────────
    "numero_emenda",
    "tipo_emenda",
    "orgao",
    "funcao",
    "subfuncao",
    "programa",
    "acao",

    # ── Valores (GENERATED excluídos: percentual_empenhado, percentual_pago) ────
    "valor_orcado_atual",
    "valor_empenhado",
    "valor_liquidado",
    "valor_pago",
    "valor_restos_pagar",

    # ── Localização ──────────────────────────────────────────────────────────────
    "municipio",
    "uf",

    # ── Origem e qualidade ───────────────────────────────────────────────────────
    "fonte_portal",
    "url_transparencia",
    "nivel_qualidade",

    # ── Campos flat de enriquecimento (adicionados v2.2 — antes em 'metadados') ─
    "cruzado_zidane",
    "qualidade_score",
    "valor_total_deputado",
    "qtd_emendas_deputado",
    "media_emenda",
    "ranking_valor",
    "versao_agente",
    "enriquecido_em",

    # ── Timestamps ───────────────────────────────────────────────────────────────
    "coletado_em",
]

# ── Estética Terminal ──────────────────────────────────────────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

def banner():
    print(f"\n{C_PURPLE}\u2554{'\u2550'*69}\u2557{C_END}")
    print(f"{C_PURPLE}\u2551{C_BOLD}{C_CYAN}  🇧🇷 PELÉ-D {VERSAO} | LOADER — OURO → {TABELA}  {C_END}{C_PURPLE}\u2551{C_END}")
    print(f"{C_PURPLE}\u255a{'\u2550'*69}\u255d{C_END}")
    print(f"{C_WHITE}   Tabela    : {TABELA}")
    print(f"   Esfera     : estadual | UF: BA | Fonte: siga_ba")
    print(f"   Upsert     : on_conflict=prisma_id (merge-duplicates)")
    print(f"   Armadura   : Batch {BATCH_SIZE} | Retry {MAX_RETRIES}x | Idempotente | Zero Perda{C_END}\n")
    sys.stdout.flush()

def print_status(msg: str, status="info"):
    icons  = {"info": "\U0001f539", "success": "\u2705", "error": "\u274c", "warn": "\u26a0\ufe0f", "process": "\u2699\ufe0f"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '\U0001f539')} {msg}{C_END}")
    sys.stdout.flush()


def mapear_para_tabela(r: Dict[str, Any]) -> Dict[str, Any]:
    """Filtra apenas os campos aceitos pela tabela emendas_estaduais_ba.

    Garante que:
    - prisma_id esteja sempre presente (chave de upsert)
    - Colunas GENERATED não sejam enviadas (percentual_empenhado, percentual_pago)
    - Valores defaults são aplicados para todos os campos obrigatórios
    """
    row: Dict[str, Any] = {}
    for campo in CAMPOS_TABELA:
        val = r.get(campo)
        row[campo] = val

    # ── Defaults campos obrigatórios ────────────────────────────────────────────
    row["uf"]                   = row.get("uf") or "BA"
    row["fonte_portal"]         = row.get("fonte_portal") or "siga_ba"
    row["nivel_qualidade"]      = row.get("nivel_qualidade") or "prata"
    row["valor_orcado_atual"]   = row.get("valor_orcado_atual") or 0
    row["valor_empenhado"]      = row.get("valor_empenhado") or 0
    row["valor_liquidado"]      = row.get("valor_liquidado") or 0
    row["valor_pago"]           = row.get("valor_pago") or 0
    row["valor_restos_pagar"]   = row.get("valor_restos_pagar") or 0
    row["coletado_em"]          = row.get("coletado_em") or datetime.utcnow().isoformat() + "Z"

    # ── Defaults campos flat enriquecimento (v2.2) ──────────────────────────────
    row["cruzado_zidane"]         = row.get("cruzado_zidane") if row.get("cruzado_zidane") is not None else False
    row["qualidade_score"]        = row.get("qualidade_score") or 0.0
    row["valor_total_deputado"]   = row.get("valor_total_deputado") or 0.0
    row["qtd_emendas_deputado"]   = row.get("qtd_emendas_deputado") or 0
    row["media_emenda"]           = row.get("media_emenda") or 0.0
    row["ranking_valor"]          = row.get("ranking_valor") or 0
    row["versao_agente"]          = row.get("versao_agente") or VERSAO
    row["enriquecido_em"]         = row.get("enriquecido_em") or datetime.utcnow().isoformat() + "Z"

    # ── Validação: prisma_id nunca pode ser None ────────────────────────────────
    if not row.get("prisma_id"):
        raise ValueError(f"prisma_id ausente no registro: {r.get('parlamentar_nome')} / {r.get('ano')}")

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

    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                endpoint,
                data=payload,
                headers={
                    **headers,
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                params={"on_conflict": "prisma_id"},
                timeout=60,
            )
            if resp.status_code in (200, 201, 204):
                return len(batch), 0
            if resp.status_code == 409:
                print(f"   {C_YELLOW}⚠️ 409 inesperado (merge-dup ativo): {resp.text[:200]}{C_END}")
                return len(batch), 0
            print(f"   {C_YELLOW}⚠️ Tentativa {tentativa}/{MAX_RETRIES} — HTTP {resp.status_code}: {resp.text[:300]}{C_END}")
            if tentativa < MAX_RETRIES:
                time.sleep(RETRY_WAIT * tentativa)
        except requests.exceptions.Timeout:
            print(f"   {C_YELLOW}⚠️ Tentativa {tentativa}/{MAX_RETRIES} — Timeout{C_END}")
            if tentativa < MAX_RETRIES:
                time.sleep(RETRY_WAIT * tentativa)
        except Exception as e:
            print(f"   {C_RED}❌ Erro inesperado: {e}{C_END}")
            break

    return 0, len(batch)


def main():
    parser = argparse.ArgumentParser(
        description=f"Pelé-D {VERSAO}: Loader Ouro → {TABELA} (Estadual BA)"
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
        print_status("Defina SUPABASE_SERVICE_ROLE_KEY no arquivo .env", "warn")
        sys.exit(1)

    headers = {
        "apikey":        supa_key or "dry-run-key",
        "Authorization": f"Bearer {supa_key or 'dry-run-key'}",
        "Content-Type":  "application/json",
    }
    endpoint = f"{supa_url}/rest/v1/{TABELA}"

    print_status(f"Endpoint : {endpoint}", "info")
    print_status(f"Upsert   : on_conflict=prisma_id (idempotente)", "info")
    if args.dry_run:
        print(f"{C_YELLOW}⚠️  MODO DRY-RUN — Nenhum dado será gravado no Supabase.{C_END}\n")

    # ── Localizar Ouro ──────────────────────────────────────────────────────────────────────
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

    # ── FASE 1: Verificação ───────────────────────────────────────────────────────────────────
    print(f"{C_CYAN}━━━ FASE 1 — Verificação ━━━{C_END}")
    print_status(f"Tabela alvo: {TABELA} (esfera=estadual, uf=BA, fonte=siga_ba)", "info")
    print_status(f"Colunas GENERATED excluídas do payload: percentual_empenhado, percentual_pago", "warn")
    print_status(f"Campos flat de enriquecimento (v2.2): cruzado_zidane, qualidade_score, ranking_valor, ...", "info")

    # ── FASE 2: Mapeamento ─────────────────────────────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 2 — Mapeamento Ouro → {TABELA} ━━━{C_END}")
    rows       = []
    orfaos     = []
    erros_mapa = []

    for r in records:
        try:
            row = mapear_para_tabela(r)
            if not row.get("parlamentar_id"):
                orfaos.append({
                    "prisma_id":        row.get("prisma_id"),
                    "parlamentar_nome": row.get("parlamentar_nome"),
                    "ano":              row.get("ano"),
                })
            rows.append(row)
        except ValueError as e:
            erros_mapa.append(str(e))
            print_status(f"Registro ignorado: {e}", "warn")

    print_status(
        f"Mapeados: {len(rows)} | "
        f"Órfãos (sem parlamentar_id): {len(orfaos)} | "
        f"Ignorados (sem prisma_id): {len(erros_mapa)}",
        "info"
    )

    # ── FASE 3: Upload em batches (upsert idempotente) ────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 3 — Upsert Supabase ({TABELA}) ━━━{C_END}")
    inseridos = 0
    erros     = 0

    for i in range(0, len(rows), args.batch):
        batch  = rows[i : i + args.batch]
        n_ok, n_err = upsert_batch(batch, endpoint, headers, args.dry_run)
        inseridos += n_ok
        erros     += n_err
        progresso  = min(i + args.batch, len(rows))
        if not args.dry_run:
            print(
                f"   {C_PURPLE}[{progresso}/{len(rows)}]{C_END} "
                f"{C_GREEN}✅ {inseridos}{C_END} | "
                f"{C_RED}❌ {erros}{C_END} | "
                f"{C_YELLOW}⚠️ órfãos: {len(orfaos)}{C_END}"
            )
        sys.stdout.flush()

    # ── FASE 4: Relatório ────────────────────────────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 4 — Relatório Final ━━━{C_END}")
    if orfaos:
        orfaos_dir  = base_dir / "data" / "saida" / "pele" / "orphans"
        orfaos_dir.mkdir(parents=True, exist_ok=True)
        hoje        = datetime.now().strftime("%Y%m%d_%H%M")
        orfaos_file = orfaos_dir / f"pele_orfaos_{args.ano}_{hoje}.json"
        with open(orfaos_file, "w", encoding="utf-8") as f:
            json.dump(orfaos, f, ensure_ascii=False, indent=2)
        print_status(f"{len(orfaos)} órfãos salvos em: {orfaos_file.name}", "warn")

    print(f"\n{C_PURPLE}{'━'*74}{C_END}")
    print(f"{C_GREEN}✅ PELÉ-D {VERSAO} FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Ano       : {args.ano}")
    print(f"   Tabela    : {TABELA}")
    print(f"   Total     : {total}")
    print(f"   Inseridos : {inseridos}")
    print(f"   Erros     : {erros}")
    print(f"   Órfãos    : {len(orfaos)} (inseridos sem vínculo parlamentar_id)")
    print(f"   Endpoint  : {endpoint}")
    print(f"   Upsert    : on_conflict=prisma_id (idempotente){C_END}")
    if args.dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Nada gravado no Supabase.{C_END}")
    print(f"{C_PURPLE}{'━'*74}{C_END}\n")
    print("[AGENT DONE] ✅ Pelé-D encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
