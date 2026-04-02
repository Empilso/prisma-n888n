#!/usr/bin/env python3
"""
🇧🇷 PELÉ-A2 v2.0 — INGESTOR TRANSFERÊNCIAS ESPECIAIS (EMENDAS PIX/FEDERAIS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FONTE:   dados.ba.gov.br/dataset/transferencias-especiais
ESFERA:  federal_transferencia | SUFIXO: .6

ARQUIVOS (5):
  1. VW_PAINEL_TRANSFERENCIA_ESPECIAL_DESPESA.csv (PRINCIPAL)
  2. VW_PAINEL_TRANSFERENCIA_ESPECIAL_CENTRALIZACAO_DESCENTRALIZACAO.csv
  3. VW_PAINEL_TRANSFERENCIA_ESPECIAL_LIQUIDACAO_ORCAMENTO.csv
  4. VW_PAINEL_TRANSFERENCIA_ESPECIAL_PAGAMENTO.csv
  5. VW_PAINEL_TRANSFERENCIA_ESPECIAL_INSTRUMENTO_CAPTACAO.csv

USO:
    python3 agent_pele_a2_federal.py --pasta ./transferencias --ano 2024
    python3 agent_pele_a2_federal.py --pasta ./transferencias --ano 2024 --dry-run
"""

import csv
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone

VERSAO = "v2.0-prisma-pele-a2-federal"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Ingesta de Transferências Especiais (emendas federais Pix repassadas ao estado BA)",
        "especialidade": "Ingestão Multi-Arquivo com Merge (5 CSVs)",
        "protocolo_tecnico": "csv.DictReader + Merge por num_codigo",
        "camada_dados": "Bronze (Raw Validado)",
        "seguranca": "Processamento local, encoding utf-8-sig"
    },
    "diretrizes": [
        "1. Processa 5 CSVs: DESPESA (principal), PAGAMENTO, LIQUIDACAO, CENTRALIZACAO, INSTRUMENTO_CAPTACAO",
        "2. Merge por num_codigo: DESPESA → CENTRALIZACAO → PAGAMENTO/LIQUIDACOES",
        "3. Extrai instrumento de captação (convênio/contrato) - exclusivo A2",
        "4. Gera Bronze JSON: pele/bronze/pele_federal_{ano}_bronze.json",
        "5. Campos exclusivos A2: ministerio_origem, num_emenda_federal, cnpj_cpf_credor, instrumento_captacao",
        "6. Campos NULL no A2: processos_sei (lista vazia), tem_processo_sei (false), num_empenho (null)"
    ],
    "apuracao": {
        "esfera": "federal_transferencia",
        "fonte_portal": "dados_ba_gov_br_transf_especial",
        "uf": "BA",
        "sufixo_origem": ".6",
        "saida_esperada": "data/saida/pele/bronze/pele_federal_{ano}_bronze.json"
    }
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def ler_csv(path: Path) -> list[dict]:
    rows = []
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = [r for r in reader]
            break
        except Exception:
            continue
    return rows

def parse_valor(v: str) -> float:
    if not v:
        return 0.0
    try:
        return float(v.strip().replace(".", "").replace(",", "."))
    except Exception:
        return 0.0

def prisma_id(num_codigo: str, ano: str) -> str:
    raw = f"{num_codigo.lower()}federal{ano}"
    return hashlib.md5(raw.encode()).hexdigest()

def cor(txt, c): return f"\033[{c}m{txt}\033[0m"
def ok(t): print(cor(f"✅ {t}", "92"))
def info(t): print(cor(f"🔹 {t}", "96"))
def warn(t): print(cor(f"⚠️  {t}", "93"))
def erro(t): print(cor(f"❌ {t}", "91"))

# ── Lógica principal ───────────────────────────────────────────────────────────

def processar(pasta: Path, ano: str, dry_run: bool):
    print(cor(f"\n╔══════════════════════════════════════════════════════╗", "95"))
    print(cor(f"║  PELÉ-A2 {VERSAO} | Transferências Especiais BA {ano}  ║", "95"))
    print(cor(f"╚══════════════════════════════════════════════════════╝\n", "95"))

    def csv_path(nome):
        p = pasta / nome
        if not p.exists():
            erro(f"Arquivo não encontrado: {nome}")
            return None
        return p

    p_despesa    = csv_path("VW_PAINEL_TRANSFERENCIA_ESPECIAL_DESPESA.csv")
    p_central    = csv_path("VW_PAINEL_TRANSFERENCIA_ESPECIAL_CENTRALIZACAO_DESCENTRALIZACAO.csv")
    p_liquidacao = csv_path("VW_PAINEL_TRANSFERENCIA_ESPECIAL_LIQUIDACAO_ORCAMENTO.csv")
    p_pagamento  = csv_path("VW_PAINEL_TRANSFERENCIA_ESPECIAL_PAGAMENTO.csv")
    p_instrumento= csv_path("VW_PAINEL_TRANSFERENCIA_ESPECIAL_INSTRUMENTO_CAPTACAO.csv")

    if not all([p_despesa, p_central, p_liquidacao, p_pagamento, p_instrumento]):
        erro("Arquivos faltando. Abortando.")
        return

    info("Carregando CSVs...")
    despesas     = ler_csv(p_despesa)
    central      = ler_csv(p_central)
    liquidacoes  = ler_csv(p_liquidacao)
    pagamentos   = ler_csv(p_pagamento)
    instrumentos = ler_csv(p_instrumento)

    ok(f"DESPESA: {len(despesas)} linhas")
    ok(f"CENTRALIZACAO: {len(central)} linhas")
    ok(f"LIQUIDACAO: {len(liquidacoes)} linhas")
    ok(f"PAGAMENTO: {len(pagamentos)} linhas")
    ok(f"INSTRUMENTO_CAPTACAO: {len(instrumentos)} linhas")

    # ── Indexar auxiliares ────────────────────────────────────────────────────
    idx_central: dict[str, list] = {}
    for r in central:
        k = (r.get("num_codigo") or "").strip()
        if k:
            idx_central.setdefault(k, []).append({
                "num_codigo_exec": (r.get("num_codigo_exec") or "").strip(),
                "num_codigo_liqu": (r.get("num_codigo_liqu") or "").strip(),
                "orgao_executor":  (r.get("nom_orgao_orcamento_exec") or "").strip() or None,
            })

    idx_pag: dict[str, list] = {}
    for r in pagamentos:
        k = (r.get("num_codigo_exec") or "").strip()
        if k:
            idx_pag.setdefault(k, []).append(r)

    idx_liqu: dict[str, list] = {}
    for r in liquidacoes:
        k = (r.get("num_codigo_liqu") or "").strip()
        if k:
            idx_liqu.setdefault(k, []).append(r)

    # INSTRUMENTO: indexado por posição (sem chave direta — usa seq)
    # Associamos ao num_codigo via ordem de aparição na DESPESA
    # (estrutura real: seq_inst_captacao_recurso sem FK explícita)
    instr_list = instrumentos  # usado abaixo por índice se necessário

    # ── Filtrar por ano ───────────────────────────────────────────────────────
    despesas_ano = [r for r in despesas if (r.get("Ano Exercício") or "").strip() == ano]
    info(f"Registros do ano {ano}: {len(despesas_ano)}")

    if not despesas_ano:
        warn(f"Nenhum registro para o ano {ano}.")
        anos = sorted(set((r.get("Ano Exercício") or "").strip() for r in despesas))
        warn(f"Anos disponíveis: {anos}")
        return

    # ── Montar records Bronze ─────────────────────────────────────────────────
    records = []
    for idx, row in enumerate(despesas_ano):
        num_codigo = (row.get("num_codigo") or "").strip()
        vinculos   = idx_central.get(num_codigo, [{}])

        pags_list  = []
        liqus_list = []

        for v in vinculos:
            exec_cod = v.get("num_codigo_exec", "")
            liqu_cod = v.get("num_codigo_liqu", "")

            for p in idx_pag.get(exec_cod, []):
                pags_list.append({
                    "num_pagto_nob":      (p.get("num_pagto_nob") or "").strip() or None,
                    "num_pagto_fmt":      (p.get("Nº do Pagamento Formatado") or "").strip() or None,
                    "credor":             (p.get("RazaoSocialCredorPagamento") or "").strip() or None,
                    "cnpj_cpf_credor":    (p.get("CNPJ_CPF_CREDOR_PAGAMENTO") or "").strip() or None,
                    "data_pagamento":     (p.get("Data do Pagamento") or "").strip() or None,
                    "valor_pagto":        parse_valor(p.get("Valor Pagamento Nob") or ""),
                    "pagamento_efetivado":(p.get("Pagamento_Efetivado") or "").strip() or None,
                    "valor_gcv":          parse_valor(p.get("Valor GCV") or ""),
                    "objeto":             (p.get("Objeto") or "").strip() or None,
                    "num_empenho":        None,  # exclusivo A1
                    "url_painel":         (p.get("URL Painel de Pagamentos") or "").strip() or None,
                    "ano_exercicio":      (p.get("ano_exercicio") or ano).strip(),
                })

            for l in idx_liqu.get(liqu_cod, []):
                liqus_list.append({
                    "val_liquidacao":         parse_valor(l.get("val_liquidacao") or ""),
                    "dtc_liquidacao":         (l.get("dtc_liquidacao") or "").strip() or None,
                    "dtc_cadastro":           (l.get("dtc_cadastro") or "").strip() or None,
                    "dtc_ultima_atualizacao": (l.get("dtc_ultima_atualizacao") or "").strip() or None,
                    "num_codigo_liqu":        liqu_cod or None,
                })

        # Instrumento de captação (por índice correspondente)
        instr = instr_list[idx] if idx < len(instr_list) else {}
        instrumento_captacao = {
            "tipo":     None,
            "numero":   (instr.get("seq_inst_captacao_recurso") or "").strip() or None,
            "convenio": None,
            "raw":      json.dumps(instr, ensure_ascii=False) if instr else None,
        }

        val_emp = parse_valor(row.get("Valor Empenhado Total") or "")
        val_orc = parse_valor(row.get("Valor Orçado Atual") or "") or parse_valor(row.get("Valor Orçado Inicial") or "")

        record = {
            "prisma_id":            prisma_id(num_codigo, ano),
            "origem":               "federal",
            "sufixo_origem":        ".6",
            "esfera":               "federal_transferencia",
            "uf":                   "BA",
            "fonte_portal":         "dados_ba_gov_br_transf_especial",
            "ano_exercicio":        ano,
            "num_codigo":           num_codigo,

            "deputado_cod":         (row.get("Deputado") or "").strip() or None,
            "deputado_nome":        None,  # resolvido pelo Pelé-C via Zidane
            "ministerio_origem":    (row.get("Ministério de Origem da Emenda") or "").strip() or None,
            "num_emenda_federal":   (row.get("Número da Emenda Parlamentar") or "").strip() or None,
            "ano_emenda_federal":   (row.get("Ano da Emenda") or "").strip() or None,

            "orgao":                (row.get("Órgão") or "").strip() or None,
            "sgl_orgao":            (row.get("sgl_orgao_orcamento") or "").strip() or None,
            "unidade_orcamentaria": (row.get("Unidade Orçamentária") or "").strip() or None,
            "nom_res_unidade":      (row.get("nom_res_unidade_orcamentaria") or "").strip() or None,
            "acao_programa":        (row.get("Ação do Programa de Governo") or "").strip() or None,
            "cod_subfonte_recurso": (row.get("COD_SUBFONTE_RECURSO") or "").strip() or None,
            "orgao_executor":       vinculos[0].get("orgao_executor") if vinculos else None,

            "valor_orcado_inicial": parse_valor(row.get("Valor Orçado Inicial") or ""),
            "valor_orcado_atual":   parse_valor(row.get("Valor Orçado Atual") or ""),
            "valor_empenhado":      val_emp,
            "valor_liquidado":      parse_valor(row.get("Valor Liquidado Total") or ""),
            "valor_pago":           parse_valor(row.get("Valor Pago") or ""),
            "taxa_execucao":        round(val_emp / val_orc, 4) if val_orc else 0.0,

            "instrumento_captacao": instrumento_captacao,
            "pagamentos":           pags_list,
            "liquidacoes":          liqus_list,

            "processos_sei":        [],
            "tem_processo_sei":     False,

            "ingerido_em":          datetime.now(timezone.utc).isoformat(),
            "versao_agente":        VERSAO,
        }
        records.append(record)

    ok(f"Records montados: {len(records)}")

    if dry_run:
        print(cor("\n🔍 DRY-RUN — Amostra do 1º record:\n", "95"))
        print(json.dumps(records[0], ensure_ascii=False, indent=2))
        warn(f"DRY-RUN: {len(records)} records NÃO salvos.")
        return

    out_dir = Path("data/saida/pele/bronze")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pele_federal_{ano}_bronze.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    ok(f"Bronze salvo: {out_path} ({len(records)} records)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pelé-A2: Ingestor Transferências Especiais BA")
    parser.add_argument("--pasta", required=True, help="Pasta com os 5 CSVs")
    parser.add_argument("--ano",   required=True, help="Ano de exercício (ex: 2024)")
    parser.add_argument("--dry-run", action="store_true", help="Processa sem salvar")
    args = parser.parse_args()

    processar(Path(args.pasta), args.ano, args.dry_run)
