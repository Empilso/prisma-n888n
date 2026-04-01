#!/usr/bin/env python3
"""
🇧🇷 AGENT PELÉ-A1 v2.0 — INGESTOR EMENDAS PARLAMENTARES (ESTADUAL BA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Ler os CSVs do portal de Emendas Parlamentares (deputados estaduais BA),
         consolidar as 5 tabelas em um JSON Bronze unificado com origem = 'estadual'.

ARQUIVOS DE ENTRADA (pasta emendasparlamentares/):
  - VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv          (principal)
  - VW_PAINEL_EMENDAS_PARLAMENTARES_CENTRALIZACAO_DESCENTRALIZACAO.csv
  - VW_PAINEL_EMENDAS_PARLAMENTARES_LIQUIDACAO_ORCAMENTO.csv
  - VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv
  - VW_PROCESSO_SEI.csv                                   (exclusivo estadual)

CHAVE DE JUNÇÃO:
  num_codigo → CENTRALIZACAO → num_codigo_exec → PAGAMENTO
                             → num_codigo_liqu → LIQUIDACAO
  num_empenho (PAGAMENTOS) → VW_PROCESSO_SEI

IDENTIFICADOR DE ORIGEM: sufixo *.5 no num_codigo

OUTPUT:
  data/saida/pele/bronze/pele_estadual_{ano}_bronze.json

USO:
    python agent_pele_a1_estadual.py --pasta ./emendasparlamentares --ano 2024
    python agent_pele_a1_estadual.py --pasta ./emendasparlamentares --ano 2024 --dry-run
"""

import os
import sys
import re
import csv
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

VERSAO = "v2.0-prisma-pele-a1-estadual"
ORIGEM = "estadual"
SUFIXO_ORIGEM = ".5"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Ingestão Bronze dos CSVs de Emendas Parlamentares Estaduais BA.",
        "especialidade": "Consolidação de 5 CSVs + junção por num_codigo + enriquecimento SEI",
        "protocolo_tecnico": "Pure Python (csv + json)",
        "camada_dados": "Bronze (Raw)",
        "origem": ORIGEM,
        "sufixo_num_codigo": SUFIXO_ORIGEM,
        "seguranca": "Sem acesso à internet. Processa apenas arquivos locais."
    },
    "arquivos_entrada": [
        "VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv",
        "VW_PAINEL_EMENDAS_PARLAMENTARES_CENTRALIZACAO_DESCENTRALIZACAO.csv",
        "VW_PAINEL_EMENDAS_PARLAMENTARES_LIQUIDACAO_ORCAMENTO.csv",
        "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv",
        "VW_PROCESSO_SEI.csv",
    ],
    "chave_juncao": "num_codigo → centralizacao → exec/liqu → pagamentos/liquidacoes",
    "exclusivo": "VW_PROCESSO_SEI vincula num_empenho → processo SEI (só estadual)"
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

def print_header(title: str):
    width = 72
    print(f"\n{C_PURPLE}╔" + "═"*(width-2) + f"╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN} {title.center(width-4)} {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚" + "═"*(width-2) + f"╝{C_END}\n")

def print_status(msg: str, status="info"):
    icons  = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE}
    print(f"{colors.get(status, C_CYAN)}{icons.get(status, '🔹')} {msg}{C_END}")


def normalizar_chave_coluna(col: str) -> str:
    """Normaliza nomes de colunas: lowercase, sem acentos, sem espaços."""
    import unicodedata
    nfkd = "".join(c for c in unicodedata.normalize('NFKD', col)
                   if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9_]', '_', nfkd.strip().lower()).strip('_')


def ler_csv(filepath: Path, encoding: str = "utf-8-sig") -> List[Dict[str, str]]:
    """Lê CSV e retorna lista de dicts com chaves normalizadas."""
    records = []
    try:
        with open(filepath, "r", encoding=encoding, errors="replace") as f:
            reader = csv.DictReader(f, delimiter=",")
            for row in reader:
                normalized = {normalizar_chave_coluna(k): (v.strip() if v else "") for k, v in row.items()}
                records.append(normalized)
        print_status(f"{filepath.name}: {len(records)} linhas lidas.", "success")
    except Exception as e:
        print_status(f"Erro ao ler {filepath.name}: {e}", "error")
    return records


def parse_valor(v: str) -> float:
    """Converte valor BR (ex: 1.234,56) para float."""
    if not v:
        return 0.0
    try:
        return float(v.replace(".", "").replace(",", ".").replace("R$", "").strip())
    except:
        return 0.0


def gerar_prisma_id(num_codigo: str, origem: str, ano: str) -> str:
    payload = f"{num_codigo.strip().lower()}{origem}{ano.strip()}"
    return hashlib.md5(payload.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Pelé-A1 v2.0: Ingestor Emendas Parlamentares Estaduais BA"
    )
    parser.add_argument("--pasta",   type=str, required=True,
                        help="Pasta contendo os CSVs de emendasparlamentares/")
    parser.add_argument("--ano",     type=str, required=True,
                        help="Ano de exercício (ex: 2024)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Processa sem salvar")
    args = parser.parse_args()

    print_header(f"PELÉ-A1 {VERSAO} | INGESTOR ESTADUAL — ANO {args.ano}")

    pasta = Path(args.pasta)
    if not pasta.exists():
        print_status(f"Pasta não encontrada: {pasta}", "error")
        sys.exit(1)

    # ── 1. Ler todos os CSVs ───────────────────────────────────────────────────
    print_status("Carregando CSVs...", "process")

    f_despesas       = pasta / "VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv"
    f_central        = pasta / "VW_PAINEL_EMENDAS_PARLAMENTARES_CENTRALIZACAO_DESCENTRALIZACAO.csv"
    f_liquidacao     = pasta / "VW_PAINEL_EMENDAS_PARLAMENTARES_LIQUIDACAO_ORCAMENTO.csv"
    f_pagamentos     = pasta / "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv"
    f_sei            = pasta / "VW_PROCESSO_SEI.csv"

    rows_despesas    = ler_csv(f_despesas)    if f_despesas.exists()    else []
    rows_central     = ler_csv(f_central)     if f_central.exists()     else []
    rows_liquidacao  = ler_csv(f_liquidacao)  if f_liquidacao.exists()  else []
    rows_pagamentos  = ler_csv(f_pagamentos)  if f_pagamentos.exists()  else []
    rows_sei         = ler_csv(f_sei)         if f_sei.exists()         else []

    # ── 2. Indexar tabelas auxiliares por chave ────────────────────────────────
    print_status("Indexando tabelas auxiliares...", "process")

    # Centralização: num_codigo → lista de exec/liqu
    idx_central: Dict[str, List[Dict]] = {}
    for r in rows_central:
        chave = r.get("num_codigo", "").strip()
        if chave:
            idx_central.setdefault(chave, []).append(r)

    # Liquidação: num_codigo_liqu → dados
    idx_liquidacao: Dict[str, Dict] = {}
    for r in rows_liquidacao:
        chave = r.get("num_codigo_liqu", "").strip()
        if chave:
            idx_liquidacao[chave] = r

    # Pagamentos: num_codigo_exec → lista de pagamentos
    idx_pagamentos: Dict[str, List[Dict]] = {}
    for r in rows_pagamentos:
        chave = r.get("num_codigo_exec", "").strip()
        if chave:
            idx_pagamentos.setdefault(chave, []).append(r)

    # SEI: num_empenho → processo SEI (exclusivo estadual)
    idx_sei: Dict[str, str] = {}
    for r in rows_sei:
        empenho = r.get("num_empenho_orcamento", "").strip()
        processo = r.get("num_processo_sist_elet_info", "").strip()
        if empenho and processo:
            idx_sei[empenho] = processo

    print_status(f"Centralização: {len(idx_central)} chaves", "info")
    print_status(f"Liquidações:   {len(idx_liquidacao)} registros", "info")
    print_status(f"Pagamentos:    {len(idx_pagamentos)} chaves", "info")
    print_status(f"SEI:           {len(idx_sei)} vínculos", "info")

    # ── 3. Montar registros Bronze ─────────────────────────────────────────────
    print_status("Montando registros Bronze...", "process")
    bronze: List[Dict[str, Any]] = []
    stats = {"com_central": 0, "com_pagamento": 0, "com_sei": 0, "sem_central": 0}

    for d in rows_despesas:
        num_codigo = d.get("num_codigo", "").strip()
        if not num_codigo:
            continue

        # Dados da centralização
        centrais = idx_central.get(num_codigo, [])
        if centrais:
            stats["com_central"] += 1
        else:
            stats["sem_central"] += 1

        # Agrupa pagamentos e liquidações de todos os exec/liqu deste num_codigo
        pagamentos_list: List[Dict] = []
        liquidacoes_list: List[Dict] = []
        orgao_exec = None

        for c in centrais:
            orgao_exec = c.get("nom_orgao_orcamento_exec") or orgao_exec
            exec_cod = c.get("num_codigo_exec", "").strip()
            liqu_cod = c.get("num_codigo_liqu", "").strip()

            if exec_cod and exec_cod in idx_pagamentos:
                pagamentos_list.extend(idx_pagamentos[exec_cod])
                stats["com_pagamento"] += 1

            if liqu_cod and liqu_cod in idx_liquidacao:
                liquidacoes_list.append(idx_liquidacao[liqu_cod])

        # Vínculos SEI — via num_empenho nos pagamentos
        processos_sei = []
        for pag in pagamentos_list:
            empenho = pag.get("num_empenho", "").strip()
            if empenho and empenho in idx_sei:
                proc = idx_sei[empenho]
                if proc not in processos_sei:
                    processos_sei.append(proc)
                    stats["com_sei"] += 1

        # Valores
        val_orcado_inicial = parse_valor(d.get("valor_orcado_inicial_", "") or d.get("valor_orcado_inicial", ""))
        val_orcado_atual   = parse_valor(d.get("valor_orcado_atual_", "") or d.get("valor_orcado_atual", ""))
        val_empenhado      = parse_valor(d.get("valor_empenhado_", "") or d.get("valor_empenhado", ""))
        val_liquidado      = parse_valor(d.get("valor_liquidado_", "") or d.get("valor_liquidado", ""))
        val_pago           = parse_valor(d.get("valor_pago_", "") or d.get("valor_pago", ""))

        # Taxa de execução
        taxa_execucao = round(val_pago / val_empenhado, 4) if val_empenhado > 0 else 0.0

        # prisma_id
        prisma_id = gerar_prisma_id(num_codigo, ORIGEM, args.ano)

        record: Dict[str, Any] = {
            # ── Identificadores ──────────────────────────────────────────
            "prisma_id":             prisma_id,
            "origem":                ORIGEM,
            "sufixo_origem":         SUFIXO_ORIGEM,
            "esfera":                "estadual",
            "uf":                    "BA",
            "fonte_portal":          "dados_ba_gov_br_emendas",
            "ano_exercicio":         d.get("ano_exercicio", "").strip() or args.ano,

            # ── Código único ─────────────────────────────────────────────
            "num_codigo":            num_codigo,

            # ── Deputado ─────────────────────────────────────────────────
            "deputado_cod":          d.get("deputado", "").strip(),
            "deputado_nome":         d.get("nome_do_deputado", "").strip(),
            # Campo exclusivo federal — NULL no estadual
            "ministerio_origem":     None,
            "num_emenda_federal":    None,
            "ano_emenda_federal":    None,

            # ── Órgão / Ação ──────────────────────────────────────────────
            "orgao":                 d.get("orgao", "").strip(),
            "sgl_orgao":             d.get("sgl_orgao_orcamento", "").strip(),
            "unidade_orcamentaria": d.get("unidade_orcamentaria", "").strip(),
            "nom_res_unidade":       d.get("nom_res_unidade_orcamentaria", "").strip(),
            "acao_programa":         d.get("acao_do_programa_de_governo", "").strip(),
            "cod_subfonte_recurso":  d.get("cod_subfonte_recurso", "").strip(),
            "orgao_executor":        orgao_exec,

            # ── Valores ──────────────────────────────────────────────────
            "valor_orcado_inicial":  val_orcado_inicial,
            "valor_orcado_atual":    val_orcado_atual,
            "valor_empenhado":       val_empenhado,
            "valor_liquidado":       val_liquidado,
            "valor_pago":            val_pago,
            "taxa_execucao":         taxa_execucao,

            # ── Pagamentos (lista) ─────────────────────────────────────────
            "pagamentos": [
                {
                    "num_pagto_nob":      p.get("num_pagto_nob", ""),
                    "num_pagto_fmt":      p.get("n_do_pagamento_formatado", ""),
                    "credor":             p.get("razaosocialcredorpagamento", ""),
                    "cnpj_cpf_credor":    None,  # exclusivo federal
                    "data_pagamento":     p.get("data_do_pagamento", ""),
                    "valor_pagto":        parse_valor(p.get("val_pagto_nob", "")),
                    "pagamento_efetivado":p.get("pagamento_efetivado", ""),
                    "valor_gcv":          parse_valor(p.get("val_gcv", "")),
                    "objeto":             p.get("objeto", ""),
                    "num_empenho":        p.get("num_empenho", ""),
                    "url_painel":         None,  # exclusivo federal
                    "ano_exercicio":      None,  # exclusivo federal
                }
                for p in pagamentos_list
            ],

            # ── Liquidações (lista) ────────────────────────────────────────
            "liquidacoes": [
                {
                    "val_liquidacao":          parse_valor(liq.get("val_liquidacao", "")),
                    "dtc_liquidacao":          liq.get("dtc_liquidacao", ""),
                    "dtc_cadastro":            liq.get("dtc_cadastro", ""),
                    "dtc_ultima_atualizacao":  liq.get("dtc_ultima_atualizacao", ""),
                    "num_codigo_liqu":         liq.get("num_codigo_liqu", ""),
                }
                for liq in liquidacoes_list
            ],

            # ── SEI (exclusivo estadual) ───────────────────────────────────
            "processos_sei":         processos_sei,
            "tem_processo_sei":      len(processos_sei) > 0,

            # ── Metadados ─────────────────────────────────────────────────
            "ingerido_em":           datetime.utcnow().isoformat() + "Z",
            "versao_agente":         VERSAO,
        }
        bronze.append(record)

    print(f"\n{C_WHITE}📊 Resultado da ingestão:{C_END}")
    print(f"   🔹 Total registros DESPESA  : {len(rows_despesas)}")
    print(f"   ✅ Com centralização         : {stats['com_central']}")
    print(f"   ⚠️  Sem centralização        : {stats['sem_central']}")
    print(f"   💰 Com pagamentos            : {stats['com_pagamento']}")
    print(f"   📋 Com processo SEI          : {stats['com_sei']}")
    print(f"   🟡 Bronze gerados            : {len(bronze)}")

    if args.dry_run:
        print(f"\n{C_YELLOW}⚠️  DRY-RUN: Nenhum arquivo salvo.{C_END}")
        if bronze:
            print_status("Amostra do 1º registro Bronze:", "info")
            sample = {k: v for k, v in bronze[0].items() if k not in ["pagamentos", "liquidacoes"]}
            sample["pagamentos_count"] = len(bronze[0]["pagamentos"])
            sample["liquidacoes_count"] = len(bronze[0]["liquidacoes"])
            print(json.dumps(sample, ensure_ascii=False, indent=2))
        sys.exit(0)

    # ── Salvar Bronze ─────────────────────────────────────────────────────────
    base_dir   = Path(__file__).resolve().parent.parent.parent
    out_dir    = base_dir / "data" / "saida" / "pele" / "bronze"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file   = out_dir / f"pele_estadual_{args.ano}_bronze.json"

    output = {
        "total":        len(bronze),
        "origem":       ORIGEM,
        "esfera":       "estadual",
        "uf":           "BA",
        "ano":          args.ano,
        "gerado_em":    datetime.utcnow().isoformat() + "Z",
        "versao":       VERSAO,
        "stats":        stats,
        "records":      bronze,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"PELÉ-A1 CONCLUÍDO! {C_BOLD}{len(bronze)}{C_END} registros Bronze (estadual) gerados.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END}", "info")
    print_status(f"Próximo passo: python agent_pele_b_parser.py --arquivo {out_file.name} --origem estadual", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    main()
