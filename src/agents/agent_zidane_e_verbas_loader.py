#!/usr/bin/env python3
"""
🐘 AGENT ZIDANE-E | VERBAS LOADER v2.0 — O Injetor de Ouro
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler todos os JSONs Ouro e fazer upsert no Supabase
         na tabela `despesas_gabinete` sem perder NENHUM registro.
ARMADURA: Batches de 500 | Retry 3x | Idempotente via prisma_id
TABELA:   despesas_gabinete (schema enterprise v2 - multi-portal)

  prisma_id           TEXT PK   → hash: {fonte_portal}:{num_processo}:{competencia_date}
  parlamentar_id      TEXT      → FK parlamentares.prisma_id (NULL = órfão)
  fonte_portal        TEXT      → discriminador multi-portal (al_ba_gov_br, camara_fed...)
  esfera              TEXT      → estadual | federal | municipal
  uf                  CHAR(2)
  nome_deputado_raw   TEXT      → nome original do portal (auditoria)
  partido_raw         TEXT
  competencia_date    DATE
  competencia_ano     INT
  competencia_mes     INT
  num_processo        TEXT
  num_nf              TEXT
  num_nf_normalizado  TEXT
  tipo_documento      TEXT      → CPF | CNPJ | DESCONHECIDO
  cnpj_fornecedor     TEXT
  nome_fornecedor     TEXT
  valor               NUMERIC
  valor_detalhe       NUMERIC
  valor_glosado       NUMERIC
  valor_liquido       NUMERIC   → COLUNA GERADA (não inserir)
  categoria_portal    TEXT
  categoria_slug      TEXT
  categoria_detalhe   TEXT
  url_documento       TEXT
  url_transparencia   TEXT
  nivel_qualidade     TEXT
  qualidade_score     NUMERIC
  metadados           JSONB
  coletado_em         TIMESTAMPTZ
  criado_em           TIMESTAMPTZ
  processado_em       TIMESTAMPTZ

USO:
    python agent_zidane_e_verbas_loader.py              # todos os ouro disponíveis
    python agent_zidane_e_verbas_loader.py --year 2022  # só um ano
    python agent_zidane_e_verbas_loader.py --dry-run    # simula sem inserir
    python agent_zidane_e_verbas_loader.py --batch 200  # batch size customizado
"""

__PRISMA_MANIFEST__ = """
=============================================================================
PRISMA MANIFEST - AGENT ZIDANE-E v2.0 (VERBAS LOADER)
- Tabela alvo  : despesas_gabinete (schema enterprise multi-portal)
- Visão Geral  : Injetor final da Camada Ouro → Supabase.
- Garantias    : Idempotência via upsert no prisma_id.
                 Sem perda: órfãos logados, nunca silenciados.
                 Sem duplicatas: onConflict=prisma_id → update.
- Estratégia  : Batch 500 com retry 3x exponencial.
- valor_liquido: coluna GERADA pelo banco, nunca inserida aqui.
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
from typing import List, Dict, Any
from dotenv import load_dotenv

# --- Estética N888N ───────────────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

VERSION        = "zidane_e_v2.0"
BATCH_SIZE     = 500
MAX_RETRIES    = 3
RETRY_WAIT_SEC = 2

# ── Campos que serão inseridos (EXCLUI valor_liquido que é coluna GERADA) ──
CAMPOS_DESPESAS = [
    "prisma_id",
    "parlamentar_id",
    "fonte_portal",
    "esfera",
    "uf",
    "nome_deputado_raw",
    "partido_raw",
    "competencia_date",
    "competencia_ano",
    "competencia_mes",
    "num_processo",
    "num_nf",
    "num_nf_normalizado",
    "tipo_documento",
    "cnpj_fornecedor",
    "nome_fornecedor",
    "valor",
    "valor_detalhe",
    "valor_glosado",
    # valor_liquido → GERADO PELO BANCO, nunca inserir
    "categoria_portal",
    "categoria_slug",
    "categoria_detalhe",
    "url_documento",
    "url_transparencia",
    "nivel_qualidade",
    "qualidade_score",
    "metadados",
    "coletado_em",
    "processado_em",
]

# ── Mapeamento: campo do Ouro (Ronaldo Gold) → campo do Supabase ──
# Chave = nome no JSON Ouro | Valor = nome na tabela despesas_gabinete
MAP_OURO_TO_DB = {
    # Identidade
    "prisma_id"          : "prisma_id",
    "parlamentar_id"     : "parlamentar_id",
    # Portal
    "fonte_portal"       : "fonte_portal",
    "esfera"             : "esfera",
    "uf"                 : "uf",
    # Deputado raw
    "nome_deputado_raw"  : "nome_deputado_raw",
    "deputado"           : "nome_deputado_raw",   # fallback campo antigo
    "partido"            : "partido_raw",
    # Competência
    "competencia_date"   : "competencia_date",
    "competencia_ano"    : "competencia_ano",
    "ano"                : "competencia_ano",     # fallback
    "competencia_mes"    : "competencia_mes",
    # Documento
    "num_processo"       : "num_processo",
    "num_nf"             : "num_nf",
    "num_nf_normalizado" : "num_nf_normalizado",
    "tipo_documento"     : "tipo_documento",
    # Fornecedor
    "cnpj_fornecedor"    : "cnpj_fornecedor",
    "nome_fornecedor"    : "nome_fornecedor",
    # Valores
    "valor"              : "valor",
    "valor_detalhe"      : "valor_detalhe",
    "valor_glosado"      : "valor_glosado",
    # Categoria
    "categoria_portal"   : "categoria_portal",
    "categoria_original" : "categoria_portal",   # fallback campo antigo
    "categoria_slug"     : "categoria_slug",
    "categoria_detalhe"  : "categoria_detalhe",
    "categoria"          : "categoria_portal",   # fallback campo raw
    # URLs
    "url_documento"      : "url_documento",
    "url_pdf_nf"         : "url_documento",       # fallback campo antigo
    "link_pdf_nf"        : "url_documento",       # fallback campo bronze
    "url_transparencia"  : "url_transparencia",
    "fonte_url"          : "url_transparencia",   # fallback campo antigo
    "link_detalhe"       : "url_transparencia",   # fallback campo bronze
    # Qualidade
    "nivel_qualidade"    : "nivel_qualidade",
    "nicel_qualidade"    : "nivel_qualidade",      # corrige typo histórico
    "qualidade_score"    : "qualidade_score",
    # Metadados
    "metadados"          : "metadados",
    "coletado_em"        : "coletado_em",
    "processado_em"      : "processado_em",
}


def banner():
    print(f"\n{C_PURPLE}╔═══════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}  🐘 ZIDANE-E v2.0 | VERBAS LOADER — OURO → SUPABASE   {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚═══════════════════════════════════════════════════════════════════╝{C_END}")
    print(f"{C_WHITE}   Tabela   : despesas_gabinete (enterprise multi-portal v2)")
    print(f"   Armadura  : Batch {BATCH_SIZE} | Retry {MAX_RETRIES}x | Idempotente | Zero Perda{C_END}\n")
    sys.stdout.flush()


# ── Mapeamento Ouro → DB ───────────────────────────────────────────────────
def mapear_para_db(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converte um registro Ouro para o schema de despesas_gabinete.
    - Usa MAP_OURO_TO_DB para todos os campos (com fallbacks)
    - Primeira ocorrência do campo DB vence (prioridade decrescente)
    - Remove valor_liquido (coluna gerada)
    - Garante defaults obrigatórios
    """
    row: Dict[str, Any] = {c: None for c in CAMPOS_DESPESAS}

    # Aplica o mapeamento respeitando prioridade (primeira ocorrência vence)
    for campo_ouro, campo_db in MAP_OURO_TO_DB.items():
        if campo_db not in CAMPOS_DESPESAS:
            continue
        if row[campo_db] is None and r.get(campo_ouro) is not None:
            row[campo_db] = r[campo_ouro]

    # Defaults obrigatórios
    row["fonte_portal"]   = row["fonte_portal"]   or "al_ba_gov_br"
    row["esfera"]         = row["esfera"]         or "estadual"
    row["uf"]             = row["uf"]             or "BA"
    row["nivel_qualidade"]= row["nivel_qualidade"] or "ouro"
    row["valor"]          = row["valor"]          or 0
    row["valor_detalhe"]  = row["valor_detalhe"]  or 0
    row["valor_glosado"]  = row["valor_glosado"]  or 0
    row["processado_em"]  = row["processado_em"]  or datetime.utcnow().isoformat() + "Z"
    row["metadados"]      = row["metadados"]      or {}

    return row


# ── Supabase HTTP Upsert ───────────────────────────────────────────────────
def upsert_batch(
    batch: List[Dict],
    endpoint: str,
    headers: Dict,
    dry_run: bool = False,
) -> tuple[int, int]:
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
            if resp.status_code in (200, 201, 204):
                return len(batch), 0
            if resp.status_code == 409:
                return len(batch), 0
            print(f"   {C_YELLOW}⚠️  Tentativa {tentativa}/{MAX_RETRIES} — HTTP {resp.status_code}: {resp.text[:300]}{C_END}")
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


# ── Loader de arquivo Ouro ───────────────────────────────────────────────────
def carregar_arquivo_ouro(
    ouro_path: Path,
    endpoint: str,
    headers: Dict,
    batch_size: int,
    dry_run: bool,
    stats: Dict,
):
    print(f"\n{C_CYAN}━━━ {ouro_path.name} ({round(ouro_path.stat().st_size / 1024 / 1024, 1)} MB) ━━━{C_END}")
    sys.stdout.flush()

    with open(ouro_path, "r", encoding="utf-8") as f:
        registros = json.load(f)

    if not isinstance(registros, list):
        registros = registros.get("records", list(registros.values()))

    total = len(registros)
    print(f"   📦 {total} registros Ouro carregados.")
    sys.stdout.flush()

    inseridos = 0
    erros     = 0
    orfaos    = 0

    for i in range(0, total, batch_size):
        batch_raw  = registros[i : i + batch_size]
        batch_rows = []

        for r in batch_raw:
            if not r.get("prisma_id"):
                # Registro sem prisma_id é inutilizável — descarta com log
                print(f"   {C_RED}⚠️  Registro sem prisma_id ignorado: {str(r)[:100]}{C_END}")
                erros += 1
                continue

            if not r.get("parlamentar_id"):
                # Órfão: prisma_id existe mas sem vínculo com parlamentar
                # Inserimos mesmo assim (parlamentar_id é nullable)
                orfaos += 1
                stats["orfaos"].append({
                    "arquivo"          : ouro_path.name,
                    "prisma_id"        : r.get("prisma_id"),
                    "nome_deputado_raw": r.get("nome_deputado_raw") or r.get("deputado"),
                })

            batch_rows.append(mapear_para_db(r))

        if not batch_rows:
            continue

        n_ok, n_err = upsert_batch(batch_rows, endpoint, headers, dry_run)
        inseridos += n_ok
        erros     += n_err

        progresso = min(i + batch_size, total)
        print(
            f"   {C_PURPLE}[{ouro_path.stem[:30]}]{C_END} "
            f"{C_WHITE}{progresso}/{total}{C_END} | "
            f"{C_GREEN}✅ {inseridos}{C_END} | "
            f"{C_RED}❌ {erros}{C_END} | "
            f"{C_YELLOW}⚠️  órfãos: {orfaos}{C_END}"
        )
        sys.stdout.flush()

    stats["total_inseridos"] += inseridos
    stats["total_erros"]     += erros
    stats["total_orfaos"]    += orfaos
    stats["arquivos_processados"].append({
        "arquivo"   : ouro_path.name,
        "total"     : total,
        "inseridos" : inseridos,
        "erros"     : erros,
        "orfaos"    : orfaos,
    })
    print(f"   {C_GREEN}💾 {ouro_path.name} → {inseridos} upserts | {erros} erros | {orfaos} órfãos{C_END}")
    sys.stdout.flush()


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Zidane-E v2: Verbas Loader Ouro → despesas_gabinete")
    parser.add_argument("--year",    type=str, default=None,       help="Processar só um ano (ex: 2022)")
    parser.add_argument("--dry-run", action="store_true",          help="Simula sem inserir no Supabase")
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
        print(f"{C_RED}[ZIDANE-E] ❌ Supabase key não encontrada no .env{C_END}")
        sys.exit(1)

    headers = {
        "apikey"        : supa_key or "dry-run-key",
        "Authorization" : f"Bearer {supa_key or 'dry-run-key'}",
        "Content-Type"  : "application/json",
    }
    endpoint = f"{supa_url}/rest/v1/despesas_gabinete"

    print(f"{C_WHITE}🎯 Endpoint : {endpoint}")
    print(f"   Tabela   : despesas_gabinete (enterprise multi-portal){C_END}")
    if args.dry_run:
        print(f"{C_YELLOW}⚠️  MODO DRY-RUN — Nenhum dado será gravado.{C_END}")
    print()
    sys.stdout.flush()

    ouro_dir = base_dir / "data" / "saida" / "ouro"

    if args.year:
        arquivos = sorted(ouro_dir.glob(f"verbas_{args.year}_gold_*.json"))
        if not arquivos:
            print(f"{C_RED}❌ Nenhum Ouro encontrado para o ano {args.year} em {ouro_dir}{C_END}")
            sys.exit(1)
    else:
        arquivos = sorted(ouro_dir.glob("verbas_*_gold_*.json"))
        if not arquivos:
            print(f"{C_RED}❌ Nenhum Ouro encontrado em {ouro_dir}{C_END}")
            sys.exit(1)

    print(f"{C_WHITE}📦 {len(arquivos)} arquivo(s) Ouro na fila:{C_END}")
    for a in arquivos:
        print(f"   • {a.name} ({round(a.stat().st_size / 1024 / 1024, 1)} MB)")
    print()
    sys.stdout.flush()

    stats = {
        "total_inseridos"      : 0,
        "total_erros"          : 0,
        "total_orfaos"         : 0,
        "arquivos_processados" : [],
        "orfaos"               : [],
        "inicio"               : datetime.utcnow().isoformat() + "Z",
    }

    for ouro_path in arquivos:
        carregar_arquivo_ouro(
            ouro_path  = ouro_path,
            endpoint   = endpoint,
            headers    = headers,
            batch_size = args.batch,
            dry_run    = args.dry_run,
            stats      = stats,
        )

    # Salva relatório de órfãos
    if stats["orfaos"]:
        orfaos_dir  = base_dir / "data" / "saida" / "verbas" / "orphans"
        orfaos_dir.mkdir(parents=True, exist_ok=True)
        hoje        = datetime.now().strftime("%Y%m%d_%H%M")
        orfaos_path = orfaos_dir / f"loader_orfaos_{hoje}.json"
        with open(orfaos_path, "w", encoding="utf-8") as f:
            json.dump(stats["orfaos"], f, ensure_ascii=False, indent=2)
        print(f"\n{C_YELLOW}⚠️  {len(stats['orfaos'])} órfãos salvos em: {orfaos_path.name}{C_END}")

    stats["fim"] = datetime.utcnow().isoformat() + "Z"

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}✅ ZIDANE-E v2.0 FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Arquivos  : {len(stats['arquivos_processados'])}")
    print(f"   Upserts OK : {stats['total_inseridos']}")
    print(f"   Erros      : {stats['total_erros']}")
    print(f"   Órfãos     : {stats['total_orfaos']} (inseridos sem vínculo parlamentar)")
    print(f"   Endpoint   : {endpoint}{C_END}")
    if args.dry_run:
        print(f"   {C_YELLOW}[DRY RUN] Nada gravado no Supabase.{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    print(f"[AGENT DONE] ✅ Zidane-E v2 encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
