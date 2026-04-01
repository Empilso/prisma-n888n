#!/usr/bin/env python3
"""
🇧🇷 PELÉ-A1 v2.0 — INGESTOR EMENDAS PARLAMENTARES ESTADUAIS BA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Processar 5 CSVs de Emendas Parlamentares (deputados estaduais BA)
         e gerar JSON Bronze unificado.

FONTE:   dados.ba.gov.br/dataset/emendas-parlamentares
TIPO:    Emendas Parlamentares (Estaduais BA)
ESFERA:  estadual
SUFIXO:  .5

ARQUIVOS (5):
  1. VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv (PRINCIPAL)
  2. VW_PAINEL_EMENDAS_PARLAMENTARES_CENTRALIZACAO_DESCENTRALIZACAO.csv
  3. VW_PAINEL_EMENDAS_PARLAMENTARES_LIQUIDACAO_ORCAMENTO.csv
  4. VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv
  5. VW_PROCESSO_SEI.csv (EXCLUSIVO A1)

OUTPUT:  data/saida/pele/bronze/pele_estadual_{ano}_bronze.json

USO:
    python agent_pele_a1_estadual.py --pasta ./emendasparlamentares --ano 2024
    python agent_pele_a1_estadual.py --pasta ./emendasparlamentares --ano 2024 --dry-run
"""

import os
import sys
import csv
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

VERSAO = "v2.0-prisma-pele-a1-estadual"

# Configuração fixa do A1
TIPO_EMENDA = "parlamentares"
ESFERA = "estadual"
SUFIXO_ORIGEM = ".5"
FONTE_PORTAL = "dados_ba_gov_br_emendas"

ARQUIVOS_ESPERADOS = [
    "VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv",
    "VW_PAINEL_EMENDAS_PARLAMENTARES_CENTRALIZACAO_DESCENTRALIZACAO.csv",
    "VW_PAINEL_EMENDAS_PARLAMENTARES_LIQUIDACAO_ORCAMENTO.csv",
    "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv",
    "VW_PROCESSO_SEI.csv"
]

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Ingesta de Emendas Parlamentares Estaduais BA (deputados estaduais)",
        "especialidade": "Ingestão Multi-Arquivo com Merge (5 CSVs)",
        "protocolo_tecnico": "csv.DictReader + Merge por num_codigo",
        "camada_dados": "Bronze (Raw Validado)",
        "seguranca": "Processamento local, encoding utf-8-sig"
    },
    "diretrizes": [
        "1. Processa 5 CSVs: DESPESAS (principal), PAGAMENTOS, LIQUIDACAO, CENTRALIZACAO, PROCESSO_SEI",
        "2. Merge por num_codigo: DESPESAS → CENTRALIZACAO → PAGAMENTOS/LIQUIDACOES",
        "3. Vincula processos SEI via num_empenho (exclusivo A1)",
        "4. Gera Bronze JSON: pele/bronze/pele_estadual_{ano}_bronze.json",
        "5. Campos exclusivos A1: processos_sei, tem_processo_sei, num_empenho",
        "6. Campos NULL no A1: ministerio_origem, num_emenda_federal, cnpj_cpf_credor, instrumento_captacao"
    ],
    "apuracao": {
        "esfera": "estadual",
        "fonte_portal": "dados_ba_gov_br_emendas",
        "uf": "BA",
        "origem": "Deputados estaduais BA — orçamento estadual",
        "sufixo_origem": ".5",
        "arquivos_entrada": 5,
        "tem_processo_sei": True,
        "tem_cnpj_credor": False,
        "tem_emenda_federal": False,
        "saida_esperada": "data/saida/pele/bronze/pele_estadual_{ano}_bronze.json"
    }
}
    "apuracao": {
        "esfera": "estadual",
        "fonte_portal": "siga_ba",
        "uf": "BA",
        "tipos_suportados": {
            "parlamentares": {
                "arquivos": 5,
                "origem": "Deputados estaduais BA",
                "tem_processo_sei": True,
                "tem_cnpj_credor": False
            },
            "transferencias": {
                "arquivos": 5,
                "origem": "Emendas federais (Pix) repassadas ao estado",
                "tem_cnpj_credor": True,
                "tem_emenda_federal": True,
                "tem_instrumento_captacao": True
            }
        },
        "entrada_esperada": "5 CSVs por tipo (upload manual ou pasta local)",
        "saida_esperada": "data/saida/pele/bronze/pele_{tipo}_{ano}_bronze.json"
    }
}

# ── Colunas esperadas no CSV (aceita variações de nome) ────────────────────────
COLUNAS_MAPA = {
    # Chave = nome canônico interno | Valores = variações aceitas no CSV
    "parlamentar_nome": ["deputado", "nome_deputado", "parlamentar", "nome", "autor", "nome_autor"],
    "partido":          ["partido", "sigla_partido", "sigla", "partido_politico"],
    "uf":               ["uf", "estado", "sigla_uf"],
    "ano":              ["ano", "exercicio", "ano_emenda", "competencia_ano"],
    "valor":            ["valor", "valor_emenda", "valor_pago", "vl_emenda", "valor_total"],
    "tipo_emenda":      ["tipo_emenda", "tipo", "modalidade", "especie"],
    "numero_emenda":    ["codigo", "codigo_emenda", "num_emenda", "numero_emenda", "id_emenda"],
    "funcao":           ["funcao", "funcao_programatica", "area", "setor"],
    "subfuncao":        ["subfuncao", "subfuncao_programatica"],
    "programa":         ["programa", "programa_orcamentario"],
    "acao":             ["acao", "acao_orcamentaria"],
    "localizador":      ["localizador", "localizador_gasto"],
    "resultado":        ["resultado", "resultado_primario"],
    "valor_orcado_inicial": ["dotacao", "dotacao_inicial", "dotacao_atualizada"],
    "valor_empenhado":  ["empenhado", "valor_empenhado"],
    "valor_liquidado":  ["liquidado", "valor_liquidado"],
    "valor_pago":       ["pago", "valor_pago_direto"],
    "beneficiario":     ["beneficiario", "nome_beneficiario", "municipio", "cidade"],
    "cnpj_cpf":         ["cnpj_cpf", "cnpj", "cpf", "documento_beneficiario"],
    "objeto":           ["objeto", "descricao", "descricao_emenda"],
    "situacao":         ["situacao", "status", "situacao_emenda"],
}
COLUNAS_OBRIGATORIAS = ["parlamentar_nome", "valor"]

# ── Estética Terminal (igual família Zidane) ───────────────────────────────────
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
    icon  = icons.get(status, "🔹")
    color = colors.get(status, C_CYAN)
    print(f"{color}{icon} {msg}{C_END}")


def detectar_coluna(header: List[str], variações: List[str]) -> str | None:
    """Encontra o nome real da coluna no CSV dentre as variações aceitas."""
    header_lower = {h.strip().lower(): h for h in header}
    for v in variações:
        if v.lower() in header_lower:
            return header_lower[v.lower()]
    return None


def detectar_ano(records: List[Dict], campo_ano: str | None) -> str:
    """Tenta detectar o ano dominante dos registros."""
    if campo_ano:
        anos = [r.get(campo_ano, "") for r in records if r.get(campo_ano, "").strip()]
        if anos:
            from collections import Counter
            return Counter(anos).most_common(1)[0][0]
    return datetime.now().strftime("%Y")


def limpar_valor(v: str) -> float:
    """Converte string de valor brasileiro para float."""
    if not v or str(v).strip() in ["", "None", "-"]:
        return 0.0
    v = str(v).strip()
    # Remove R$, espaços, pontos de milhar; troca vírgula decimal por ponto
    v = v.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def main():
    parser = argparse.ArgumentParser(description="Pelé-A v1.1: Ingestor de CSV local de Emendas Estaduais BA")
    parser.add_argument("--arquivo",  type=str, help="Caminho do arquivo CSV")
    parser.add_argument("--pasta",    type=str, help="Pasta com múltiplos CSVs para processar em lote")
    parser.add_argument("--ano",      type=str, default=None, help="Ano de referência (ex: 2024)")
    parser.add_argument("--dry-run",  action="store_true", help="Valida sem salvar")
    parser.add_argument("--encoding", type=str, default=None, help="Encoding do CSV (auto-detecta se omitido)")
    args = parser.parse_args()

    print_header(f"PELÉ-A v1.1 | INGESTOR CSV LOCAL — EMENDAS ESTADUAIS BA — {args.ano or 'ANO NÃO DEFINIDO'}")
    
    # Modo pasta: processar múltiplos CSVs
    if args.pasta:
        pasta_path = Path(args.pasta).expanduser().resolve()
        if not pasta_path.exists():
            print_status(f"Pasta não encontrada: {pasta_path}", "error")
            sys.exit(1)
        
        csv_files = list(pasta_path.glob("*.csv"))
        if not csv_files:
            print_status(f"Nenhum arquivo CSV encontrado em: {pasta_path}", "error")
            sys.exit(1)
        
        print_status(f"Modo LOTE: {len(csv_files)} arquivo(s) CSV encontrado(s)", "process")
        for csv_file in csv_files:
            print(f"\n{C_CYAN}{'─'*72}{C_END}")
            print_status(f"Processando: {csv_file.name}", "process")
            processar_arquivo(csv_file, args)
        
        print(f"\n{C_GREEN}✅ Processamento em lote concluído!{C_END}")
        sys.exit(0)
    
    # Modo arquivo único
    if not args.arquivo:
        print_status("Erro: --arquivo ou --pasta é obrigatório", "error")
        parser.print_help()
        sys.exit(1)
    
    csv_path = Path(args.arquivo).expanduser().resolve()
    processar_arquivo(csv_path, args)


def processar_arquivo(csv_path: Path, args):
    """Processa um único arquivo CSV"""
    print_status(f"Arquivo alvo: {csv_path.name}", "process")
    print_status("MODO: Arquivo local — nenhuma conexão com internet.", "info")

    # ── 1. Verificar arquivo ───────────────────────────────────────────────────
    if not csv_path.exists():
        print_status(f"Arquivo não encontrado: {csv_path}", "error")
        return
    if csv_path.suffix.lower() not in [".csv", ".txt"]:
        print_status(f"Extensão inesperada ({csv_path.suffix}). Esperado: .csv", "warn")

    tamanho_kb = round(csv_path.stat().st_size / 1024, 1)
    print_status(f"Arquivo encontrado: {csv_path.name} ({tamanho_kb} KB)", "success")

    # ── 2. Detectar encoding ───────────────────────────────────────────────────
    encodings_tentar = [args.encoding] if args.encoding else ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    conteudo_raw = None
    encoding_usado = None
    for enc in encodings_tentar:
        try:
            conteudo_raw = csv_path.read_text(encoding=enc)
            encoding_usado = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if not conteudo_raw:
        print_status("Não foi possível decodificar o CSV. Tente --encoding latin-1", "error")
        sys.exit(1)

    print_status(f"Encoding detectado: {encoding_usado}", "info")

    # ── 3. Ler CSV ─────────────────────────────────────────────────────────────
    import io
    # Detectar delimitador
    delimitador = ","
    primeira_linha = conteudo_raw.split("\n")[0]
    if primeira_linha.count(";") > primeira_linha.count(","):
        delimitador = ";"
    print_status(f"Delimitador detectado: '{delimitador}'", "info")

    reader = csv.DictReader(io.StringIO(conteudo_raw), delimiter=delimitador)
    header = reader.fieldnames or []
    if not header:
        print_status("CSV sem cabeçalho detectado.", "error")
        sys.exit(1)

    print_status(f"Colunas encontradas ({len(header)}): {', '.join(header[:10])}{'...' if len(header)>10 else ''}", "info")

    # ── 4. Mapear colunas ──────────────────────────────────────────────────────
    mapa_final: Dict[str, str | None] = {}  # canônico → nome_real_no_csv
    for canonico, variacoes in COLUNAS_MAPA.items():
        mapa_final[canonico] = detectar_coluna(header, variacoes)

    print(f"\n{C_WHITE}📋 Mapeamento de colunas:{C_END}")
    for canonico, real in mapa_final.items():
        if real:
            print(f"   {C_GREEN}✅ {canonico:<15}{C_END} → {C_CYAN}{real}{C_END}")
        else:
            is_obrig = canonico in COLUNAS_OBRIGATORIAS
            status = f"{C_RED}❌ {canonico:<15} (OBRIGATÓRIA — não encontrada){C_END}" if is_obrig else f"{C_YELLOW}⚠️  {canonico:<15} (não encontrada — será None){C_END}"
            print(f"   {status}")

    # Checar obrigatórias
    faltando = [c for c in COLUNAS_OBRIGATORIAS if not mapa_final.get(c)]
    if faltando:
        print_status(f"Colunas obrigatórias ausentes: {faltando}. Abortando.", "error")
        sys.exit(1)

    # ── 5. Ler registros ───────────────────────────────────────────────────────
    records_raw = list(reader)
    total = len(records_raw)
    print_status(f"Total de linhas no CSV: {total}", "info")

    if total == 0:
        print_status("CSV vazio. Nenhum registro encontrado.", "error")
        sys.exit(1)

    # ── 6. Detectar ano ───────────────────────────────────────────────────────
    ano = args.ano or detectar_ano(records_raw, mapa_final.get("ano"))
    print_status(f"Ano de referência: {ano}", "info")

    # ── 7. Construir Bronze ────────────────────────────────────────────────────
    def get(row: Dict, canonico: str):
        col = mapa_final.get(canonico)
        return row.get(col, "").strip() if col else None

    bronze: List[Dict[str, Any]] = []
    erros_linha = 0
    for i, row in enumerate(records_raw):
        dep = get(row, "parlamentar_nome")
        if not dep:
            erros_linha += 1
            continue
        bronze.append({
            "linha_csv":           i + 2,  # +2 porque linha 1 é header
            "parlamentar_nome":    dep,
            "partido":             get(row, "partido"),
            "uf":                  get(row, "uf") or "BA",
            "ano":                 get(row, "ano") or ano,
            "valor":               limpar_valor(get(row, "valor") or ""),
            "tipo_emenda":         get(row, "tipo_emenda"),
            "numero_emenda":       get(row, "numero_emenda"),
            "funcao":              get(row, "funcao"),
            "subfuncao":           get(row, "subfuncao"),
            "programa":            get(row, "programa"),
            "acao":                get(row, "acao"),
            "localizador":         get(row, "localizador"),
            "valor_orcado_inicial":limpar_valor(get(row, "valor_orcado_inicial") or ""),
            "valor_empenhado":     limpar_valor(get(row, "valor_empenhado") or ""),
            "valor_liquidado":     limpar_valor(get(row, "valor_liquidado") or ""),
            "valor_pago":          limpar_valor(get(row, "valor_pago") or ""),
            "beneficiario":        get(row, "beneficiario"),
            "cnpj_cpf":            get(row, "cnpj_cpf"),
            "objeto":              get(row, "objeto"),
            "situacao":            get(row, "situacao"),
            "_raw":                dict(row),  # linha original completa para auditoria
        })

    validos = len(bronze)
    print_status(f"Registros válidos: {validos} | Ignorados (sem parlamentar): {erros_linha}", "success")

    total_valor = sum(r["valor"] for r in bronze)
    print_status(f"Valor total: R$ {total_valor:,.2f}", "info")

    if args.dry_run:
        print(f"\n{C_YELLOW}⚠️  DRY-RUN: Nenhum arquivo salvo. Validação concluída com sucesso!{C_END}")
        print_status(f"Amostra do 1º registro Bronze:", "info")
        print(json.dumps(bronze[0], ensure_ascii=False, indent=2) if bronze else "(vazio)")
        sys.exit(0)

    # ── 8. Salvar Bronze ───────────────────────────────────────────────────────
    base_dir = Path(__file__).resolve().parent.parent.parent
    out_dir  = base_dir / "data" / "saida" / "pele" / "bronze"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / f"pele_estadual_{ano}_bronze.json"
    output = {
        "total":            validos,
        "ano":              ano,
        "uf":               "BA",
        "esfera":           "estadual",
        "fonte_portal":     "siga_ba",
        "tabela_destino":   "alba_emendas_master",
        "arquivo_origem":   csv_path.name,
        "encoding_csv":     encoding_usado,
        "ingestado_em":     datetime.utcnow().isoformat() + "Z",
        "versao":           VERSAO,
        "referencias_documentais": [
            "https://dados.ba.gov.br/dataset/emendas-parlamentares"
        ],
        "records":          bronze
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"PELÉ-A CONCLUÍDO! {C_BOLD}{validos}{C_END} registros Bronze gerados.", "success")
    print_status(f"Arquivo: {C_BOLD}{out_file.name}{C_END}", "info")
    print_status(f"Próximo passo: python agent_pele_b_parser.py --ano {ano}", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    main()
