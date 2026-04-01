#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-D v3.0 — LOADER SUPABASE (EMENDAS ESTADUAIS BA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Ouro do Pelé-C e fazer upsert no Supabase
         na tabela `alba_emendas_master` sem perder NENHUM registro.

ARMADURA: Batch 500 | Retry 3x | Idempotente via on_conflict=prisma_id
TABELA:   alba_emendas_master (schema PRISMA — emendas estaduais BA SIGA)

ESTRATÉGIA DE UPSERT:
  Prefer: resolution=merge-duplicates
  on_conflict=prisma_id
  → Se o prisma_id já existe, atualiza. Se não, insere.
  → Garante idempotência total: rodar 2x não duplica dados.

COLUNAS NÃO ENVIADAS (geradas/gerenciadas pelo DB):
  - id                  (UUID gerado automaticamente pelo Supabase)
  - percentual_empenhado (GENERATED ALWAYS AS valor_empenhado/valor_orcado_atual)
  - percentual_pago      (GENERATED ALWAYS AS valor_pago/valor_orcado_atual)
  - criado_em           (DEFAULT now())
  - atualizado_em       (DEFAULT now())

USO:
    python agent_pele_d_loader.py --ano 2024 --dry-run   # SEMPRE testar primeiro!
    python agent_pele_d_loader.py --ano 2024              # upload real
    python agent_pele_d_loader.py --ano 2024 --batch 200  # batch customizado
    python agent_pele_d_loader.py --ano 2024 --origem estadual  # compatível com orquestrador
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

VERSAO      = "v3.0-prisma-pele-d-alba"
TABELA      = "alba_emendas_master"
BATCH_SIZE  = 500
MAX_RETRIES = 3
RETRY_WAIT  = 2

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao":        f"Injetor final Ouro → {TABELA} (Supabase).",
        "especialidade": "Loader estadual BA — tabela destino: alba_emendas_master",
        "tabela_supabase": TABELA,
        "esfera":        "estadual",
        "uf":            "BA",
        "fonte_portal":  "siga_ba",
        "upsert":        "on_conflict=prisma_id + resolution=merge-duplicates",
        "seguranca":     "Service Role Key via .env. Nunca exposta no código.",
    },
    "diretrizes": [
        "1. Lê o JSON Ouro gerado pelo Pelé-C.",
        "2. Mapeia apenas os campos aceitos pela tabela alba_emendas_master.",
        "3. Exclui colunas GENERATED: percentual_empenhado, percentual_pago.",
        "4. Exclui colunas auto-gerenciadas: id, criado_em, atualizado_em.",
        "5. Upsert idempotente em batches via on_conflict=prisma_id.",
        "6. Registra órfãos (sem parlamentar_id) em arquivo JSON separado.",
        "7. Zero silêncio: todos os erros são logados e reportados.",
    ]
}

# ── Campos aceitos pela tabela alba_emendas_master ─────────────────────────────────────
# NUNCA incluir: id, percentual_empenhado, percentual_pago, criado_em, atualizado_em
CAMPOS_TABELA = [
    # ── Chave de upsert ── OBRIGATÓRIO
    "prisma_id",

    # ── Relacionamentos ──
    "parlamentar_id",
    "parlamentar_nome",
    "partido",
    "ano",

    # ── Classificação orçamentária ──
    "numero_emenda",
    "tipo_emenda",
    "orgao",
    "funcao",
    "subfuncao",
    "programa",
    "acao",

    # ── Valores financeiros ──
    # (percentual_empenhado e percentual_pago são GENERATED — NÃO enviar)
    "valor_orcado_atual",
    "valor_empenhado",
    "valor_liquidado",
    "valor_pago",
    "valor_restos_pagar",

    # ── Localização ──
    "municipio",
    "uf",

    # ── Origem e rastreabilidade ──
    "fonte_portal",
    "url_transparencia",

    # ── Qualidade e enriquecimento (Pelé-C) ──
    "nivel_qualidade",
    "qualidade_score",
    "cruzado_zidane",
    "ranking_valor",
    "valor_total_dep",
    "qtd_emendas_dep",
    "media_emenda",
    "versao_agente",
    "enriquecido_em",

    # ── Auditoria ──
    "metadados",
    "coletado_em",
]

# ── Estética Terminal ──────────────────────────────────────────────────────────────────
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
    print(f"{C_PURPLE}\u2551{C_BOLD}{C_CYAN}  🇧🇷 PELÉ-D {VERSAO} | LOADER → {TABELA}  {C_END}{C_PURPLE}\u2551{C_END}")
    print(f"{C_PURPLE}\u255a{'\u2550'*69}\u255d{C_END}")
    print(f"{C_WHITE}   Tabela    : {TABELA}")
    print(f"   Esfera     : estadual | UF: BA | Fonte: siga_ba")
    print(f"   Upsert     : on_conflict=prisma_id (merge-duplicates)")
    print(f"   Armadura   : Batch {BATCH_SIZE} | Retry {MAX_RETRIES}x | Idempotente | Zero Perda{C_END}\n")
    sys.stdout.flush()


def print_status(msg: str, status: str = "info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '🔹')} {msg}{C_END}")
    sys.stdout.flush()


def mapear_para_tabela(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filtra e mapeia os campos do JSON Ouro (Pelé-C) para a tabela alba_emendas_master.

    Regras:
    - Apenas campos de CAMPOS_TABELA são enviados
    - Colunas GENERATED e auto-gerenciadas são excluídas
    - Defaults aplicados para campos obrigatórios
    - prisma_id obrigatório (chave de upsert) — ValueError se ausente
    """
    row: Dict[str, Any] = {}
    for campo in CAMPOS_TABELA:
        val = r.get(campo)
        row[campo] = val

    # ── Defaults obrigatórios ──────────────────────────────────────────────────
    row["uf"]             = row.get("uf") or "BA"
    row["fonte_portal"]   = row.get("fonte_portal") or "siga_ba"
    row["nivel_qualidade"]= row.get("nivel_qualidade") or "prata"
    row["cruzado_zidane"] = bool(row.get("cruzado_zidane") or False)
    row["qualidade_score"]= float(row.get("qualidade_score") or 0.6)

    # Valores financeiros — nunca None
    for campo_val in ["valor_orcado_atual", "valor_empenhado", "valor_liquidado",
                      "valor_pago", "valor_restos_pagar", "valor_total_dep",
                      "media_emenda"]:
        row[campo_val] = float(row.get(campo_val) or 0)

    row["qtd_emendas_dep"] = int(row.get("qtd_emendas_dep") or 0)
    row["ranking_valor"]   = int(row.get("ranking_valor") or 0)
    row["coletado_em"]     = row.get("coletado_em") or datetime.utcnow().isoformat() + "Z"
    row["enriquecido_em"]  = row.get("enriquecido_em") or datetime.utcnow().isoformat() + "Z"
    row["metadados"]       = row.get("metadados") or {}

    # ── Validação crítica ──────────────────────────────────────────────────────
    if not row.get("prisma_id"):
        raise ValueError(
            f"prisma_id ausente: {r.get('parlamentar_nome')} / ano={r.get('ano')} "
            f"/ emenda={r.get('numero_emenda')}"
        )

    return row


def upsert_batch(
    batch: List[Dict],
    endpoint: str,
    headers: Dict,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Envia um batch para o Supabase com upsert idempotente. Retorna (ok, erros)."""
    if dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Simulando upsert de {len(batch)} registros...{C_END}")
        if batch:
            print(f"   {C_WHITE}Exemplo payload (1º registro):{C_END}")
            amostra = {k: v for k, v in list(batch[0].items())[:12]}
            print(json.dumps(amostra, ensure_ascii=False, indent=4, default=str))
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
        description=f"Pelé-D {VERSAO}: Loader Ouro → {TABELA} (Estadual BA / SIGA-BA)"
    )
    parser.add_argument("--ano",     type=str, required=True,
                        help="Ano dos dados (ex: 2024)")
    parser.add_argument("--origem",  type=str, default="estadual",
                        choices=["estadual", "federal", "ambos"],
                        help="Origem dos dados (default: estadual)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simula sem inserir no Supabase")
    parser.add_argument("--batch",   type=int, default=BATCH_SIZE,
                        help=f"Tamanho do batch (default: {BATCH_SIZE})")
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

    print_status(f"Projeto   : {project_id} (DADOS-PRISMA)", "info")
    print_status(f"Endpoint  : {endpoint}", "info")
    print_status(f"Upsert    : on_conflict=prisma_id (idempotente)", "info")
    if args.dry_run:
        print(f"{C_YELLOW}⚠️  MODO DRY-RUN — Nenhum dado será gravado no Supabase.{C_END}\n")

    # ── Localizar JSON Ouro ────────────────────────────────────────────────────
    ouro_dir  = base_dir / "data" / "saida" / "pele" / "ouro"
    ouro_file = ouro_dir / f"pele_estadual_{args.ano}_ouro.json"

    if not ouro_file.exists():
        print_status(f"Ouro não encontrado: {ouro_file.name}", "error")
        print_status(
            f"Execute o Pelé-C primeiro: "
            f"python agent_pele_c_aguia.py --ano {args.ano} --origem {args.origem}",
            "warn"
        )
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

    # ── FASE 1: Verificação ────────────────────────────────────────────────────
    print(f"{C_CYAN}━━━ FASE 1 — Verificação ━━━{C_END}")
    print_status(f"Tabela alvo : {TABELA} (esfera=estadual, uf=BA, fonte=siga_ba)", "info")
    print_status("Colunas EXCLUÍDAS do payload (GENERATED/auto): "
                 "id, percentual_empenhado, percentual_pago, criado_em, atualizado_em", "warn")

    # ── FASE 2: Mapeamento ─────────────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 2 — Mapeamento Ouro → {TABELA} ━━━{C_END}")
    rows      = []
    orfaos    = []
    ignorados = []

    for r in records:
        try:
            row = mapear_para_tabela(r)
            if not row.get("parlamentar_id"):
                orfaos.append({
                    "prisma_id":        row.get("prisma_id"),
                    "parlamentar_nome": row.get("parlamentar_nome"),
                    "partido":          row.get("partido"),
                    "ano":              row.get("ano"),
                })
            rows.append(row)
        except ValueError as e:
            ignorados.append(str(e))
            print_status(f"Registro ignorado (sem prisma_id): {e}", "warn")

    print_status(
        f"Mapeados: {len(rows)} | "
        f"Órfãos (sem parlamentar_id): {len(orfaos)} | "
        f"Ignorados (sem prisma_id): {len(ignorados)}",
        "info"
    )

    # ── FASE 3: Upsert em batches ──────────────────────────────────────────────
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

    # ── FASE 4: Relatório Final ────────────────────────────────────────────────
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
    print(f"{C_WHITE}   Ano         : {args.ano}")
    print(f"   Tabela      : {TABELA}")
    print(f"   Total Ouro  : {total}")
    print(f"   Inseridos   : {inseridos}")
    print(f"   Erros       : {erros}")
    print(f"   Órfãos      : {len(orfaos)} (inseridos sem vínculo parlamentar_id)")
    print(f"   Ignorados   : {len(ignorados)} (sem prisma_id)")
    print(f"   Endpoint    : {endpoint}")
    print(f"   Upsert      : on_conflict=prisma_id (idempotente){C_END}")
    if args.dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Nada gravado no Supabase.{C_END}")
    print(f"{C_PURPLE}{'━'*74}{C_END}\n")
    print("[AGENT DONE] ✅ Pelé-D encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
