#!/usr/bin/env python3
"""
🏆 AGENT RONALDO GOLD v2.0 — O FINALIZADOR ENTERPRISE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Prata → Ouro com vínculo garantido ao hub parlamentares
ARMADURA: Match exato + fuzzy (difflib) + token sort
           Todos os registros sobem ao banco:
             - MATCH → com parlamentar_id preenchido
             - SEM MATCH → parlamentar_id=None, flag ORFAO no metadados
OUTPUT:   verbas_{ano}_gold_{versao}_{data}.json (pronto para Zidane-E)

CHANGELOG v2.0:
  - Fuzzy match com difflib (threshold 0.82)
  - Token sort match ("joao silva" == "silva joao")
  - Sem match: registro vai para Ouro com flag ORFAO (não descarta mais)
  - Campos alinhados ao schema enterprise despesas_gabinete
  - nicel_qualidade → nivel_qualidade (typo corrigido)
  - valor_liquido removido do JSON (coluna gerada no banco)
  - fonte_portal normalizado: ALBA → al_ba_gov_br
  - prisma_id hash mais robusto: usa num_processo quando num_nf vazio
"""

__PRISMA_MANIFEST__ = """
=============================================================================
PRISMA MANIFEST - AGENT 3 (RONALDO GOLD v2.0)
- Visão Geral  : Finalizador da Camada Gold Financeira.
- Matching     : Exato > Fuzzy (0.82) > Token Sort > ORFAO (nunca descarta)
- Garantia     : 100% dos registros Prata chegam ao banco.
                 Com vínculo = parlamentar_id preenchido.
                 Sem vínculo = parlamentar_id NULL + metadados.orfao=True.
- Schema       : Alinhado com despesas_gabinete enterprise v2.
=============================================================================
"""

import os
import sys
import json
import hashlib
import re
import argparse
import requests
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

VERSION         = "ronaldo_gold_v2.0"
FUZZY_THRESHOLD = 0.82   # score mínimo para aceitar fuzzy match

# ── Mapeamento de Categorias (Régua Mestre) ──────────────────────────────────
CATEGORY_MAPPER: Dict[str, str] = {
    "divulga":    "divulgacao",
    "locomoc":    "locomocao",
    "combustivel":"combustivel",
    "combust":    "combustivel",
    "telef":      "telefonia",
    "correio":    "correios",
    "consult":    "consultoria",
    "assessor":   "consultoria",
    "hosped":     "hospedagem",
    "aliment":    "alimentacao",
    "passag":     "passagens",
    "aluguel":    "aluguel",
    "imovel":     "aluguel",
    "locac":      "locacao_veiculos",
    "locaç":      "locacao_veiculos",
    "carro":      "locacao_veiculos",
    "veicu":      "locacao_veiculos",
    "material":   "material_escritorio",
    "aquisi":     "aquisicao",
    "tecnolog":   "tecnologia",
    "software":   "tecnologia",
    "impresso":   "impressos",
    "grafic":     "impressos",
    "sinaliz":    "sinalizacao",
    "segurança":  "seguranca",
    "seguranca":  "seguranca",
    "manutenc":   "manutencao",
}

def mapear_categoria(slug_prata: Optional[str], cat_original: Optional[str]) -> str:
    if slug_prata and slug_prata != "outros":
        return slug_prata
    if cat_original:
        s = cat_original.lower()
        for key, val in CATEGORY_MAPPER.items():
            if key in s:
                return val
    return "outros"


# ── Normalização de Nomes ───────────────────────────────────────────────────────
RUIDOS = [
    " do pt", " do pl", " do psd", " do psb", " do pdt", " do psol",
    " do mdb", " do uniao", " do solidariedade", " do republicanos",
    " lula", " professor", " professora", " pastor", " pastora",
    " capitão", " capitao", " coronel", " sargento", " delegado",
    " dr.", " dr ", "deputado", "deputada", " neto", " filho",
]

def normalizar(nome: str) -> str:
    if not nome: return ""
    s = ''.join(
        c for c in unicodedata.normalize('NFD', nome)
        if unicodedata.category(c) != 'Mn'
    )
    s = s.lower()
    for r in RUIDOS:
        s = s.replace(r, "")
    return re.sub(r'\s+', ' ', s).strip()

def token_sort(nome: str) -> str:
    """'silva joao' e 'joao silva' viram a mesma chave."""
    return " ".join(sorted(nome.split()))


# ── Carrega Mapa de Parlamentares do Supabase ────────────────────────────────
def carregar_mapa(supa_url: str, supa_key: str) -> Dict[str, str]:
    """
    Retorna 3 dicionários para lookup multi-camada:
      mapa_exato     : nome_normalizado → prisma_id
      mapa_token     : token_sort(nome) → prisma_id
      lista_fuzzy    : [(nome_normalizado, prisma_id), ...] para difflib
    Empacotados em um dict único para transporte.
    """
    headers = {
        "apikey": supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{supa_url}/rest/v1/parlamentares"
    params   = {"select": "prisma_id,nome_normalizado,nome_urna,nome_civil", "limit": 1000}

    print(f"{C_CYAN}[RONALDO] 🗺️  Carregando mapa parlamentares do Supabase...{C_END}")
    sys.stdout.flush()

    mapa_exato: Dict[str, str] = {}
    mapa_token: Dict[str, str] = {}
    lista_fuzzy: List[Tuple[str, str]] = []

    try:
        resp = requests.get(endpoint, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
        for row in rows:
            pid = row.get("prisma_id")
            if not pid: continue
            for campo in ["nome_normalizado", "nome_urna", "nome_civil"]:
                nome = row.get(campo)
                if not nome: continue
                n = normalizar(nome)
                if not n: continue
                mapa_exato[n] = pid
                mapa_token[token_sort(n)] = pid
                lista_fuzzy.append((n, pid))

        print(f"{C_GREEN}[RONALDO] ✅ {len(rows)} parlamentares | {len(mapa_exato)} entradas indexadas.{C_END}")
    except Exception as e:
        print(f"{C_RED}[RONALDO] ❌ Falha ao carregar mapa: {e}{C_END}")

    return {"exato": mapa_exato, "token": mapa_token, "fuzzy": lista_fuzzy}


# ── Resolver parlamentar_id (3 camadas) ────────────────────────────────────────
def resolver_id(nome: Optional[str], mapa: Dict) -> Tuple[Optional[str], str, float]:
    """
    Retorna (prisma_id, metodo, score).
    metodo: 'exato' | 'token_sort' | 'fuzzy' | 'orfao'
    """
    if not nome:
        return None, "orfao", 0.0

    n = normalizar(nome)
    if not n:
        return None, "orfao", 0.0

    # Camada 1: Match exato
    if n in mapa["exato"]:
        return mapa["exato"][n], "exato", 1.0

    # Camada 2: Token sort ("joao silva" == "silva joao")
    ts = token_sort(n)
    if ts in mapa["token"]:
        return mapa["token"][ts], "token_sort", 0.95

    # Camada 3: Fuzzy (difflib SequenceMatcher)
    melhor_score = 0.0
    melhor_pid   = None
    for nome_ref, pid in mapa["fuzzy"]:
        score = SequenceMatcher(None, n, nome_ref).ratio()
        if score > melhor_score:
            melhor_score = score
            melhor_pid   = pid

    if melhor_score >= FUZZY_THRESHOLD:
        return melhor_pid, "fuzzy", melhor_score

    return None, "orfao", melhor_score


# ── Gera prisma_id Ouro ────────────────────────────────────────────────────────────
def gerar_prisma_id(
    fonte_portal: str,
    num_processo: Optional[str],
    num_nf: Optional[str],
    valor: Optional[float],
    competencia_date: Optional[str],
) -> str:
    """
    Hash MD5 robusto: usa num_processo como ancora principal.
    Se num_processo vazio, cai para num_nf. Garante unicidade multi-portal.
    """
    ancora = num_processo or num_nf or "SEM_NF"
    chave  = f"{fonte_portal}|{ancora}|{valor}|{competencia_date}"
    return hashlib.md5(chave.encode("utf-8")).hexdigest()


# ── Purificação Prata → Ouro ───────────────────━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def purificar(r: Dict[str, Any], mapa: Dict, stats: Dict) -> Dict[str, Any]:
    nome_dep    = r.get("deputado") or r.get("nome_deputado_raw", "")
    fonte_portal = "al_ba_gov_br"   # discriminador fixo para ALBA

    # ─ Resolve vínculo ─
    parlamentar_id, metodo, score = resolver_id(nome_dep, mapa)

    if metodo == "orfao":
        stats["orfaos"] += 1
        stats["orfaos_nomes"].add(nome_dep or "DESCONHECIDO")
        nivel_qualidade = "ORFAO"
        flag_orfao      = True
        print(f"   {C_YELLOW}⚠️  ORFAO: {nome_dep} (score={score:.2f}){C_END}")
    else:
        stats["matches"][metodo] = stats["matches"].get(metodo, 0) + 1
        nivel_qualidade = "OURO"
        flag_orfao      = False
        icone = "🎯" if metodo == "exato" else ("🔍" if metodo == "token_sort" else "🧠")
        print(f"   {C_GREEN}{icone} {metodo.upper()} [{score:.2f}]: {nome_dep} → {parlamentar_id}{C_END}")

    # ─ Categoria ─
    categoria_slug = mapear_categoria(r.get("categoria_slug"), r.get("categoria_original") or r.get("categoria"))

    # ─ Valores ─
    valor         = r.get("valor") or r.get("valor_detalhe") or 0
    valor_detalhe = r.get("valor_detalhe") or valor
    valor_glosado = r.get("valor_glosado") or 0
    # valor_liquido é coluna GERADA no banco → não incluir no JSON

    # ─ Prisma ID ─
    prisma_id = gerar_prisma_id(
        fonte_portal,
        r.get("num_processo"),
        r.get("num_nf_normalizado") or r.get("num_nf"),
        valor,
        r.get("competencia_date"),
    )

    # ─ Metadados JSONB ─
    metadados = {
        "nf_tipo"           : r.get("nf_tipo"),
        "cnpj_valido"       : r.get("cnpj_valido"),
        "link_pdf_valido"   : r.get("link_pdf_valido"),
        "qualidade_score"   : r.get("qualidade_score"),
        "flags"             : r.get("flags", []),
        "num_processo"      : r.get("num_processo"),
        "link_detalhe"      : r.get("link_detalhe"),
        "bebeto_versao"     : r.get("versao_bebeto"),
        "ronaldo_versao"    : VERSION,
        "match_metodo"      : metodo,
        "match_score"       : round(score, 4),
        "orfao"             : flag_orfao,
    }

    return {
        # PK + FK
        "prisma_id"          : prisma_id,
        "parlamentar_id"     : parlamentar_id,       # None se órfão
        # Portal
        "fonte_portal"       : fonte_portal,
        "esfera"             : "estadual",
        "uf"                 : "BA",
        # Deputado raw
        "nome_deputado_raw"  : nome_dep,
        "partido_raw"        : r.get("partido"),
        # Competência
        "competencia_date"   : r.get("competencia_date"),
        "competencia_ano"    : r.get("competencia_ano") or r.get("ano"),
        "competencia_mes"    : r.get("competencia_mes"),
        # Documento
        "num_processo"       : r.get("num_processo"),
        "num_nf"             : r.get("num_nf"),
        "num_nf_normalizado" : r.get("num_nf_normalizado"),
        "tipo_documento"     : r.get("tipo_documento"),
        # Fornecedor
        "cnpj_fornecedor"    : r.get("cnpj_fornecedor"),
        "nome_fornecedor"    : r.get("nome_fornecedor"),
        # Valores (valor_liquido é GERADO no banco)
        "valor"              : valor,
        "valor_detalhe"      : valor_detalhe,
        "valor_glosado"      : valor_glosado,
        # Categoria
        "categoria_portal"   : r.get("categoria_original") or r.get("categoria"),
        "categoria_slug"     : categoria_slug,
        "categoria_detalhe"  : r.get("categoria_detalhe"),
        # URLs
        "url_documento"      : r.get("url_pdf_nf") or r.get("link_pdf_nf"),
        "url_transparencia"  : r.get("fonte_url") or r.get("link_detalhe"),
        # Qualidade
        "nivel_qualidade"    : nivel_qualidade,
        "qualidade_score"    : r.get("qualidade_score") or (1.0 if not flag_orfao else 0.5),
        # Metadados + timestamps
        "metadados"          : metadados,
        "coletado_em"        : r.get("coletado_em") or r.get("romario_coletado_em"),
        "processado_em"      : datetime.utcnow().isoformat() + "Z",
    }


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ronaldo Gold v2: O Finalizador Enterprise")
    parser.add_argument("--year", type=str,        default=None,  help="Ano para processar (ex: 2022)")
    parser.add_argument("--file", type=str,        default=None,  help="Arquivo Prata específico")
    parser.add_argument("--all",  action="store_true",            help="Processar todos os anos")
    args = parser.parse_args()

    print(f"\n{C_PURPLE}╔═══════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}   🏆 RONALDO GOLD v2.0 | PRATA → OURO ENTERPRISE    {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚═══════════════════════════════════════════════════════════════════╝{C_END}")
    print(f"{C_WHITE}   Match   : Exato > Token Sort > Fuzzy ({FUZZY_THRESHOLD}) > ORFAO")
    print(f"   Garantia : 100% dos registros sobem ao banco{C_END}\n")
    sys.stdout.flush()

    base_dir = Path(__file__).resolve().parent.parent.parent
    load_dotenv(dotenv_path=base_dir / ".env")

    project_id = os.getenv("DADOS_PRISMA_PROJECT", "hrrzwhkosgzungqxlcps")
    supa_url   = f"https://{project_id}.supabase.co"
    supa_key   = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_DADOS_PRISMA_KEY")
        or os.getenv("SUPABASE_KEY")
    )

    if not supa_key:
        print(f"{C_RED}[RONALDO] ❌ Supabase key não encontrada no .env{C_END}")
        sys.exit(1)

    mapa = carregar_mapa(supa_url, supa_key)

    prata_dir = base_dir / "data" / "saida" / "prata"
    ouro_dir  = base_dir / "data" / "saida" / "ouro"
    ouro_dir.mkdir(parents=True, exist_ok=True)

    # Resolve arquivos Prata
    if args.file:
        p = Path(args.file)
        if not p.exists(): p = prata_dir / args.file
        if not p.exists():
            print(f"{C_RED}❌ Arquivo não encontrado: {args.file}{C_END}")
            sys.exit(1)
        arquivos = [p]
    elif args.year:
        p = prata_dir / f"alba_{args.year}_prata.json"
        if not p.exists():
            print(f"{C_RED}❌ Prata não encontrado: {p}{C_END}")
            sys.exit(1)
        arquivos = [p]
    elif args.all:
        arquivos = sorted(prata_dir.glob("alba_*_prata.json"))
    else:
        arquivos = sorted(prata_dir.glob("alba_*_prata.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]

    if not arquivos:
        print(f"{C_YELLOW}⚠️  Nenhum Prata encontrado em: {prata_dir}{C_END}")
        sys.exit(0)

    print(f"{C_WHITE}🎯 {len(arquivos)} arquivo(s) Prata na fila:{C_END}")
    for a in arquivos: print(f"   • {a.name}")
    print()
    sys.stdout.flush()

    # Stats globais
    stats_global = {"ouro": 0, "orfaos": 0, "matches": {}, "orfaos_nomes": set()}

    for prata_path in arquivos:
        print(f"\n{C_CYAN}━━━ {prata_path.name} ━━━{C_END}")
        sys.stdout.flush()

        with open(prata_path, "r", encoding="utf-8") as f:
            registros = json.load(f)
        if isinstance(registros, dict):
            registros = registros.get("records", list(registros.values()))

        print(f"   📦 {len(registros)} registros Prata.")
        sys.stdout.flush()

        match_ano  = re.search(r"20\d{2}", prata_path.name)
        ano_str    = match_ano.group(0) if match_ano else "undefined"
        stats_arq  = {"ouro": 0, "orfaos": 0, "matches": {}, "orfaos_nomes": set()}

        registros_ouro: List[Dict] = []
        vistos: set = set()

        for i, r in enumerate(registros):
            ouro = purificar(r, mapa, stats_arq)

            if ouro["prisma_id"] not in vistos:
                vistos.add(ouro["prisma_id"])
                registros_ouro.append(ouro)
                if ouro["parlamentar_id"]:
                    stats_arq["ouro"] += 1

            if (i + 1) % 2000 == 0:
                print(f"{C_PURPLE}   ⏳ {i+1}/{len(registros)} | ouro={stats_arq['ouro']} | orfaos={stats_arq['orfaos']}{C_END}")
                sys.stdout.flush()

        # Salva Ouro
        hoje       = datetime.now().strftime("%Y%m%d")
        versao_tag = VERSION.split('_')[-1]
        out_path   = ouro_dir / f"verbas_{ano_str}_gold_{versao_tag}_{hoje}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(registros_ouro, f, ensure_ascii=False, indent=2)

        # Report do arquivo
        matches_str = " | ".join(f"{k}={v}" for k, v in stats_arq["matches"].items())
        print(f"\n   {C_GREEN}💾 Salvo: {out_path.name}{C_END}")
        print(f"   {C_GREEN}💳 Total registros : {len(registros_ouro)}{C_END}")
        print(f"   {C_GREEN}✅ Com vínculo      : {stats_arq['ouro']} ({matches_str}){C_END}")
        print(f"   {C_YELLOW}⚠️  Órfãos (sem match): {stats_arq['orfaos']}{C_END}")
        if stats_arq["orfaos_nomes"]:
            for nome in sorted(stats_arq["orfaos_nomes"])[:10]:
                print(f"      • {nome}")
        sys.stdout.flush()

        stats_global["ouro"]   += stats_arq["ouro"]
        stats_global["orfaos"] += stats_arq["orfaos"]
        for k, v in stats_arq["matches"].items():
            stats_global["matches"][k] = stats_global["matches"].get(k, 0) + v

    # Resumo Final
    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}🏆 RONALDO GOLD v2.0 FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Com vínculo   : {stats_global['ouro']}")
    print(f"   Órfãos (banco) : {stats_global['orfaos']} (sobem com parlamentar_id=NULL)")
    total_matches = sum(stats_global["matches"].values())
    for k, v in stats_global["matches"].items():
        pct = round(v / total_matches * 100, 1) if total_matches else 0
        print(f"   Match {k:12}: {v} ({pct}%)")
    print(f"{C_END}{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    print(f"[AGENT DONE] ✅ Ronaldo Gold v2 encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
