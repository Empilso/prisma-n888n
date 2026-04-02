#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-D v3.0 — LOADER SUPABASE (EMENDAS ESTADUAIS BA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler o JSON Ouro gerado pelo Pelé-C e fazer upsert no Supabase
         na tabela `emendas_estaduais` sem perder NENHUM registro.

ARMADURA: Batch 500 | Retry 3x | Idempotente via prisma_id (UNIQUE)
TABELA:   emendas_estaduais (schema PRISMA — emendas estaduais BA/SIGA-BA)
PK:       id (uuid gerado pelo DB)
UPSERT:   via prisma_id UNIQUE — Prefer: resolution=merge-duplicates

CAMPOS GERADOS PELO BANCO (NUNCA inserir):
  - percentual_empenhado  → CASE WHEN valor_orcado_atual > 0 THEN (valor_empenhado/valor_orcado_atual)*100
  - percentual_pago       → CASE WHEN valor_orcado_atual > 0 THEN (valor_pago/valor_orcado_atual)*100

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

VERSAO     = "v3.0-prisma-pele-loader-estadual"
TABELA     = "emendas_estaduais"
BATCH_SIZE  = 500
MAX_RETRIES = 3
RETRY_WAIT  = 2

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Injetor final de emendas estaduais BA (SIGA-BA) para Supabase",
        "especialidade": "Carga de Emendas Parlamentares Estaduais",
        "protocolo_tecnico": "Supabase REST API + Batch Insert + Retry Exponencial",
        "camada_dados": "Ouro",
        "seguranca": "Idempotência via prisma_id (UNIQUE) + on_conflict=merge-duplicates"
    },
    "diretrizes": [
        "1. Tabela alvo: emendas_estaduais (PK=id uuid, UNIQUE=prisma_id)",
        "2. Upsert via Prefer: resolution=merge-duplicates (on_conflict prisma_id)",
        "3. percentual_empenhado e percentual_pago são GERADAS pelo banco — NUNCA inserir",
        "4. id (uuid) é gerado pelo banco — NUNCA inserir",
        "5. Batch de 500 registros com retry 3x exponencial",
        "6. Órfãos (sem parlamentar_id) inseridos normalmente — logados separadamente"
    ],
    "apuracao": {
        "safras_suportadas": ["2022", "2023", "2024", "2025"],
        "entrada_esperada": "data/saida/pele/ouro/pele_estadual_{ano}_ouro.json",
        "saida_esperada": "Tabela emendas_estaduais (Supabase DADOS-PRISMA)"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Campos aceitos pela tabela emendas_estaduais
# ATENÇÃO: NÃO incluir colunas geradas: percentual_empenhado, percentual_pago
#          NÃO incluir: id (uuid — gerado pelo banco)
# ─────────────────────────────────────────────────────────────────────────────
CAMPOS_EMENDAS_ESTADUAIS = [
    # Identidade e origem
    "prisma_id",         # UNIQUE — chave de upsert
    "parlamentar_id",    # FK → parlamentares.prisma_id (NULL = órfão)
    "parlamentar_nome",
    "partido",
    "ano",
    # Classificação orçamentária
    "numero_emenda",
    "tipo_emenda",
    "orgao",
    "funcao",
    "subfuncao",
    "programa",
    "acao",
    # Valores financeiros (percentual_empenhado e percentual_pago são GERADOS)
    "valor_orcado_atual",
    "valor_empenhado",
    "valor_liquidado",
    "valor_pago",
    "valor_restos_pagar",
    # Localização
    "municipio",
    "uf",
    # Origem e qualidade
    "fonte_portal",
    "url_transparencia",
    "nivel_qualidade",
    "qualidade_score",
    # Enriquecimento Pelé-C
    "cruzado_zidane",
    "ranking_valor",
    "valor_total_dep",
    "qtd_emendas_dep",
    "media_emenda",
    "versao_agente",
    "enriquecido_em",
    # Auditoria
    "metadados",
    "coletado_em",
]

# ─────────────────────────────────────────────────────────────────────────────
# Mapeamento de campos do JSON Ouro → tabela emendas_estaduais
# ─────────────────────────────────────────────────────────────────────────────
MAPA_CAMPOS_OURO = {
    # JSON Ouro pode ter nomes legados — garantimos compatibilidade
    "numero_emenda": ["numero_emenda", "num_codigo", "num_emenda"],
    "tipo_emenda":   ["tipo_emenda", "origem"],
    "orgao":         ["orgao"],
    "funcao":        ["funcao", "acao_programa"],
    "subfuncao":     ["subfuncao"],
    "programa":      ["programa"],
    "acao":          ["acao", "acao_programa"],
    "municipio":     ["municipio", "orgao_executor"],
    "coletado_em":   ["coletado_em", "ingerido_em", "processado_em"],
}

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
    print(f"\n{C_PURPLE}╔════════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}  🇧🇷 PELÉ-D v3.0 | LOADER — OURO → emendas_estaduais (BA)  {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚════════════════════════════════════════════════════════════════════╝{C_END}")
    print(f"{C_WHITE}   Tabela   : emendas_estaduais (SIGA-BA)")
    print(f"   Esfera    : estadual | UF: BA | Fonte: siga_ba")
    print(f"   Upsert    : ON CONFLICT prisma_id → merge-duplicates")
    print(f"   Armadura  : Batch {BATCH_SIZE} | Retry {MAX_RETRIES}x | Idempotente | Zero Perda{C_END}\n")
    sys.stdout.flush()


def print_status(msg: str, status="info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '🔹')} {msg}{C_END}")
    sys.stdout.flush()


def resolver_campo(r: Dict, campo_destino: str) -> Any:
    """Resolve um campo do JSON Ouro para o nome esperado pela tabela."""
    # Tenta o nome direto primeiro
    val = r.get(campo_destino)
    if val is not None:
        return val
    # Tenta aliases mapeados
    aliases = MAPA_CAMPOS_OURO.get(campo_destino, [])
    for alias in aliases:
        val = r.get(alias)
        if val is not None:
            return val
    return None


def mapear_para_emendas_estaduais(r: Dict[str, Any]) -> Dict[str, Any]:
    """Mapeia um registro Ouro para os campos da tabela emendas_estaduais."""
    row: Dict[str, Any] = {}

    for campo in CAMPOS_EMENDAS_ESTADUAIS:
        row[campo] = resolver_campo(r, campo)

    # ── Defaults obrigatórios ──
    row["uf"]              = row.get("uf") or "BA"
    row["fonte_portal"]    = row.get("fonte_portal") or "siga_ba"
    row["nivel_qualidade"] = row.get("nivel_qualidade") or "prata"
    row["qualidade_score"] = row.get("qualidade_score") or 0.6
    row["cruzado_zidane"]  = bool(row.get("cruzado_zidane") or False)

    # Valores financeiros nunca null
    for campo_val in ["valor_orcado_atual", "valor_empenhado", "valor_liquidado",
                      "valor_pago", "valor_restos_pagar"]:
        row[campo_val] = row.get(campo_val) or 0

    # Campos de contagem nunca null
    row["qtd_emendas_dep"]  = row.get("qtd_emendas_dep") or 0
    row["valor_total_dep"]  = row.get("valor_total_dep") or 0
    row["media_emenda"]     = row.get("media_emenda") or 0

    # Timestamp de coleta
    if not row.get("coletado_em"):
        row["coletado_em"] = datetime.utcnow().isoformat() + "Z"

    return row


def upsert_batch(
    batch: List[Dict],
    endpoint: str,
    headers: Dict,
    dry_run: bool = False,
) -> tuple:
    """Envia batch para Supabase com upsert por prisma_id. Retorna (ok, erros)."""
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
                    # on_conflict=prisma_id → upsert idempotente pelo campo UNIQUE
                    "Prefer": "return=minimal,resolution=merge-duplicates",
                },
                params={"on_conflict": "prisma_id"},
                timeout=60,
            )
            if resp.status_code in (200, 201, 204):
                return len(batch), 0
            if resp.status_code == 409:
                # Conflito tratado pelo on_conflict — não é erro
                return len(batch), 0
            print(f"   {C_YELLOW}⚠️  Tentativa {tentativa}/{MAX_RETRIES} — HTTP {resp.status_code}: {resp.text[:400]}{C_END}")
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
        description="Pelé-D v3.0: Loader Ouro → emendas_estaduais (Estadual BA/SIGA-BA)"
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
        sys.exit(1)

    headers = {
        "apikey":        supa_key or "dry-run-key",
        "Authorization": f"Bearer {supa_key or 'dry-run-key'}",
        "Content-Type":  "application/json",
    }
    endpoint = f"{supa_url}/rest/v1/{TABELA}"

    print_status(f"Endpoint : {endpoint}", "info")
    print_status(f"Tabela   : {TABELA} | Upsert por: prisma_id (UNIQUE)", "info")
    if args.dry_run:
        print(f"{C_YELLOW}⚠️  MODO DRY-RUN — Nenhum dado será gravado no Supabase.{C_END}\n")

    # ── Localizar Ouro ────────────────────────────────────────────────────────
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

    # ── FASE 1: Validação ─────────────────────────────────────────────────────
    print(f"{C_CYAN}━━━ FASE 1 — Verificação ━━━{C_END}")
    print_status(f"Tabela alvo    : {TABELA} (esfera=estadual, uf=BA, fonte=siga_ba)", "info")
    print_status(f"Colunas geradas (excluídas): percentual_empenhado, percentual_pago, id", "warn")
    print_status(f"Upsert via     : prisma_id UNIQUE + on_conflict=merge-duplicates", "info")

    # ── FASE 2: Mapeamento ────────────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 2 — Mapeamento Ouro → {TABELA} ━━━{C_END}")
    rows   = []
    orfaos = []
    sem_prisma_id = 0

    for r in records:
        if not r.get("prisma_id"):
            sem_prisma_id += 1
            print_status(f"ATENÇÃO: registro sem prisma_id — parlamentar={r.get('parlamentar_nome')}, ano={r.get('ano')}", "warn")
            continue  # sem prisma_id não pode fazer upsert
        if not r.get("parlamentar_id"):
            orfaos.append({"parlamentar_nome": r.get("parlamentar_nome"), "ano": r.get("ano")})
        rows.append(mapear_para_emendas_estaduais(r))

    print_status(
        f"Registros mapeados: {len(rows)} | "
        f"Órfãos (sem parlamentar_id): {len(orfaos)} | "
        f"Descartados (sem prisma_id): {sem_prisma_id}",
        "info"
    )

    # ── FASE 3: Upload em batches ─────────────────────────────────────────────
    print(f"\n{C_CYAN}━━━ FASE 3 — Upload Supabase ({TABELA}) ━━━{C_END}")
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
    print(f"{C_GREEN}✅ PELÉ-D v3.0 FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Ano            : {args.ano}")
    print(f"   Total Ouro     : {total}")
    print(f"   Mapeados       : {len(rows)}")
    print(f"   Inseridos/Upd  : {inseridos}")
    print(f"   Erros          : {erros}")
    print(f"   Órfãos         : {len(orfaos)} (inseridos sem vínculo parlamentar_id)")
    print(f"   Sem prisma_id  : {sem_prisma_id} (descartados — sem chave de upsert)")
    print(f"   Tabela         : {TABELA}")
    print(f"   Endpoint       : {endpoint}{C_END}")
    if args.dry_run:
        print(f"   {C_YELLOW}[DRY-RUN] Nada gravado no Supabase.{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    print("[AGENT DONE] ✅ Pelé-D v3.0 encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
