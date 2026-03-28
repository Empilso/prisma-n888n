#!/usr/bin/env python3
"""
🏆 AGENT RONALDO GOLD v1.0 — O FINALIZADOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSÃO:  Transformar Camada Prata → Camada Ouro
ARMADURA: 12 Diretrizes Determinísticas (Zero IA)
AMARRA:   Vincula deputado (string) → parlamentar_id (hash 32 chars)
OUTPUT:   verbas_gabinete_gold.json → pronto para o Loader D / Upsert
"""

import os
import sys
import json
import hashlib
import re
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# --- Estética Premium (Padrão N888N) ────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"
C_END    = "\033[0m"

VERSION = "ronaldo_gold_v1.0"

# --- Mapeamento Global de Categorias (A Régua Mestre) ────────────────────────
CATEGORY_MAPPER: Dict[str, str] = {
    "divulga":       "divulgacao",
    "locomoc":       "locomocao",
    "combustivel":   "combustivel",
    "combust":       "combustivel",
    "telef":         "telefonia",
    "correio":       "correios",
    "consult":       "consultoria",
    "assessor":      "consultoria",
    "hosped":        "hospedagem",
    "aliment":       "alimentacao",
    "passag":        "passagens",
    "aluguel":       "aluguel",
    "imovel":        "aluguel",
    "locac":         "locacao_veiculos",
    "locaç":         "locacao_veiculos",
    "carro":         "locacao_veiculos",
    "veicu":         "locacao_veiculos",
    "material":      "material_escritorio",
    "aquisi":        "aquisicao",
    "tecnolog":      "tecnologia",
    "software":      "tecnologia",
    "impresso":      "impressos",
    "grafic":        "impressos",
    "sinaliz":       "sinalizacao",
    "segurança":     "seguranca",
    "seguranca":     "seguranca",
    "manutenc":      "manutencao",
}

def mapear_categoria_global(slug_prata: Optional[str], categoria_original: Optional[str]) -> str:
    """Diretriz 6: Converte categoria prata para slug global padronizado."""
    # Primeiro tenta usar o slug_prata já computado pelo Bebeto
    if slug_prata and slug_prata != "outros":
        return slug_prata
    
    # Fallback: tenta mapear a partir da categoria original
    if categoria_original:
        s = categoria_original.lower()
        for key, val in CATEGORY_MAPPER.items():
            if key in s:
                return val
    return "outros"


# ─── Busca de parlamentares no Supabase ────────────────────────────────────
def carregar_mapa_parlamentares(supa_url: str, supa_key: str) -> Dict[str, str]:
    """
    Carrega o cache de parlamentares do Supabase.
    Retorna dict: nome_normalizado (lower) → parlamentar_prisma_id
    """
    headers = {
        "apikey": supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{supa_url}/rest/v1/parlamentares"
    params = {"select": "prisma_id,nome_normalizado,nome_urna,nome_civil", "limit": 500}

    print(f"{C_CYAN}[RONALDO] 🗂️  Carregando mapa de parlamentares do Supabase...{C_END}")
    sys.stdout.flush()

    try:
        resp = requests.get(endpoint, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            rows = resp.json()
            mapa: Dict[str, str] = {}
            for row in rows:
                pid = row.get("prisma_id")
                if not pid:
                    continue
                # Vários índices para aumentar a taxa de match
                for campo in ["nome_normalizado", "nome_urna", "nome_civil"]:
                    nome = row.get(campo)
                    if nome:
                        mapa[nome.strip().lower()] = pid
            print(f"{C_GREEN}[RONALDO] ✅ {len(mapa)} nomes indexados em cache.{C_END}")
            return mapa
        else:
            print(f"{C_RED}[RONALDO] ❌ Supabase retornou {resp.status_code}: {resp.text[:120]}{C_END}")
            return {}
    except Exception as e:
        print(f"{C_RED}[RONALDO] ❌ Falha ao conectar Supabase: {e}{C_END}")
        return {}


def resolver_parlamentar_id(nome_deputado: Optional[str], mapa: Dict[str, str]) -> Optional[str]:
    """Resolve o nome string do deputado para o prisma_id do Supabase."""
    if not nome_deputado:
        return None
    busca = nome_deputado.strip().lower()
    
    # 1. Match exato
    if busca in mapa:
        return mapa[busca]
    
    # 2. Match parcial: se o nome da lista contem o nome do deputado ou vice-versa
    for nome_cache, pid in mapa.items():
        if busca in nome_cache or nome_cache in busca:
            return pid
    
    return None


# ─── Geração do Prisma ID Ouro ────────────────────────────────────────────
def gerar_prisma_id_ouro(parlamentar_id: Optional[str], num_nf: Optional[str],
                          valor: Optional[float], competencia_date: Optional[str]) -> str:
    """
    Diretriz 9 (Ouro): Hash MD5 imutável de:
    parlamentar_id + num_nf + valor + competencia_date
    """
    chave = f"{parlamentar_id}|{num_nf}|{valor}|{competencia_date}"
    return hashlib.md5(chave.encode("utf-8")).hexdigest()


# ─── Purificação para Gold ────────────────────────────────────────────────
def purificar_para_ouro(r: Dict[str, Any], mapa_parlamentares: Dict[str, str], erros_vinculo: List[str]) -> Optional[Dict[str, Any]]:
    """
    Orquestra as 12 diretrizes no nível Ouro.
    Retorna None se o registro não puder ser promovido por falta de dados críticos.
    """
    nome_deputado = r.get("deputado")

    # ── Amarra Relacional (Diretriz 1 do Ouro) ──────────────
    parlamentar_id = resolver_parlamentar_id(nome_deputado, mapa_parlamentares)
    if not parlamentar_id:
        erros_vinculo.append(nome_deputado or "DESCONHECIDO")

    # ── Categoria Global (Diretriz 2 do Ouro) ───────────────
    categoria_slug = mapear_categoria_global(
        r.get("categoria_slug"),
        r.get("categoria_original")
    )

    # ── Valores (Diretriz 3 do Ouro) ────────────────────────
    valor = r.get("valor")
    valor_glosado = r.get("valor_glosado")
    valor_liquido = None
    if isinstance(valor, (int, float)) and isinstance(valor_glosado, (int, float)):
        valor_liquido = round(valor - valor_glosado, 2)
    elif isinstance(valor, (int, float)):
        valor_liquido = valor

    # ── Prisma ID Ouro (Diretriz 9) ─────────────────────────
    prisma_id = gerar_prisma_id_ouro(
        parlamentar_id,
        r.get("num_nf_normalizado") or r.get("num_nf"),
        valor,
        r.get("competencia_date")
    )

    # ── Metadados JSONB (Diretriz 3 do Ouro: Empacotamento) ─
    metadados = {
        "nf_tipo":            r.get("nf_tipo"),
        "cnpj_valido":        r.get("cnpj_valido"),
        "link_pdf_valido":    r.get("link_pdf_valido"),
        "qualidade_score":    r.get("qualidade_score"),
        "flags":              r.get("flags", []),
        "cpf_fornecedor":     r.get("cpf_fornecedor"),
        "cpf_tipo_doc":       r.get("tipo_documento"),
        "num_processo":       r.get("num_processo"),
        "link_detalhe":       r.get("link_detalhe"),
        "link_pdf_nf_raw":    r.get("link_pdf_nf_raw"),
        "romario_coletado_em": r.get("romario_coletado_em"),
        "numero_nf_raw":      r.get("numero_nf_recibo_raw"),
        "bebeto_versao":      r.get("versao_bebeto"),
        "ronaldo_versao":     VERSION,
    }

    # ── Registro Ouro Final ──────────────────────────────────
    ouro = {
        "prisma_id":         prisma_id,
        "parlamentar_id":    parlamentar_id,
        "nome_deputado_raw": nome_deputado,           # preservado para auditoria
        "cnpj_fornecedor":   r.get("cnpj_fornecedor"),
        "nome_fornecedor":   r.get("nome_fornecedor"),
        "num_nf":            r.get("num_nf"),
        "num_nf_normalizado": r.get("num_nf_normalizado"),
        "categoria_slug":    categoria_slug,
        "categoria_original": r.get("categoria_original"),
        "url_pdf_nf":        r.get("url_pdf_nf"),
        "valor":             valor,
        "valor_glosado":     valor_glosado,
        "valor_liquido":     valor_liquido,
        "competencia_date":  r.get("competencia_date"),
        "competencia_ano":   r.get("competencia_ano"),
        "competencia_mes":   r.get("competencia_mes"),
        "ano":               r.get("ano"),
        "partido":           r.get("partido"),
        "fonte_portal":      r.get("fonte_portal", "ALBA"),
        "fonte_url":         r.get("fonte_url"),
        "metadados":         metadados,
        "nicel_qualidade":   "OURO",
        "processado_em":     datetime.utcnow().isoformat() + "Z",
    }

    return ouro


# ─── MAIN ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ronaldo Gold: O Finalizador")
    parser.add_argument("--year", type=str, default=None, help="Ano para processar (ex: 2022)")
    parser.add_argument("--file", type=str, default=None, help="Arquivo Prata específico")
    parser.add_argument("--all",  action="store_true", help="Processar todos os anos disponíveis")
    args = parser.parse_args()

    # --- Banner ──────────────────────────────────────────────────────────
    print(f"\n{C_PURPLE}╔════════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}       RONALDO GOLD v1.0 | O FINALIZADOR — PRATA → OURO      {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚════════════════════════════════════════════════════════════════════╝{C_END}")
    print(f"{C_WHITE}Armadura: 12 Diretrizes Determinísticas | Zero IA{C_END}\n")
    sys.stdout.flush()

    # --- Env ─────────────────────────────────────────────────────────────
    base_dir = Path(__file__).resolve().parent.parent.parent
    env_path = base_dir / ".env"
    load_dotenv(dotenv_path=env_path)

    project_id = os.getenv("DADOS_PRISMA_PROJECT", "hrrzwhkosgzungqxlcps")
    supa_url   = f"https://{project_id}.supabase.co"
    supa_key   = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_DADOS_PRISMA_KEY") or os.getenv("SUPABASE_KEY")

    if not supa_key:
        print(f"{C_RED}[RONALDO] ❌ Supabase key não encontrada no .env{C_END}")
        sys.exit(1)

    # --- Carrega Mapa de Parlamentares ───────────────────────────────────
    mapa_parl = carregar_mapa_parlamentares(supa_url, supa_key)

    # --- Resolve Arquivos Prata a Processar ──────────────────────────────
    prata_dir = base_dir / "data" / "saida" / "prata"
    ouro_dir  = base_dir / "data" / "saida" / "ouro"
    ouro_dir.mkdir(parents=True, exist_ok=True)

    arquivos_prata: List[Path] = []

    if args.file:
        p = Path(args.file)
        if not p.exists():
            p = prata_dir / args.file
        if not p.exists():
            print(f"{C_RED}[RONALDO] ❌ Arquivo não encontrado: {args.file}{C_END}")
            sys.exit(1)
        arquivos_prata = [p]
    elif args.year:
        p = prata_dir / f"alba_{args.year}_prata.json"
        if not p.exists():
            print(f"{C_RED}[RONALDO] ❌ Prata não encontrado para {args.year}: {p}{C_END}")
            sys.exit(1)
        arquivos_prata = [p]
    elif args.all:
        arquivos_prata = sorted(prata_dir.glob("alba_*_prata.json"))
    else:
        # Padrão: arquivo mais recente
        arquivos_prata = sorted(prata_dir.glob("alba_*_prata.json"),
                                key=lambda x: x.stat().st_mtime, reverse=True)[:1]

    if not arquivos_prata:
        print(f"{C_YELLOW}[RONALDO] ⚠️ Nenhum arquivo Prata encontrado em: {prata_dir}{C_END}")
        sys.exit(0)

    print(f"{C_WHITE}🎯 Arquivos na fila: {len(arquivos_prata)}{C_END}\n")

    # --- Processa cada arquivo ───────────────────────────────────────────
    total_ouro = 0
    total_sem_vinculo = 0

    for prata_path in arquivos_prata:
        print(f"{C_CYAN}━━━ Carregando: {prata_path.name} ━━━{C_END}")
        sys.stdout.flush()

        with open(prata_path, "r", encoding="utf-8") as f:
            registros = json.load(f)

        if isinstance(registros, dict):
            registros = registros.get("records", list(registros.values()))

        print(f"[RONALDO] 📂 {len(registros)} registros Prata carregados...")
        sys.stdout.flush()

        # Extrai ano do nome do arquivo para nomear o output
        match_ano = re.search(r"20\d{2}", prata_path.name)
        ano_str = match_ano.group(0) if match_ano else "undefined"

        registros_ouro: List[Dict[str, Any]] = []
        erros_vinculo: List[str] = []
        vistos: set = set()

        for i, r in enumerate(registros):
            nome_dep = r.get("deputado", "?")
            num_nf   = r.get("num_nf_normalizado") or r.get("num_nf", "?")

            ouro = purificar_para_ouro(r, mapa_parl, erros_vinculo)

            if ouro:
                if ouro["prisma_id"] not in vistos:
                    vistos.add(ouro["prisma_id"])
                    registros_ouro.append(ouro)
                    total_ouro += 1

            if (i + 1) % 1000 == 0:
                print(f"{C_PURPLE}[RONALDO GOLD] 🏆 {i+1}/{len(registros)} processados...{C_END}")
                sys.stdout.flush()

        # Log de erros de vínculo
        if erros_vinculo:
            erros_unicos = sorted(set(erros_vinculo))
            total_sem_vinculo += len(erros_vinculo)
            print(f"{C_YELLOW}[RONALDO] ⚠️  {len(erros_vinculo)} registros sem vínculo parlamentar.{C_END}")
            for nome in erros_unicos[:10]:
                print(f"   • {nome}")
            if len(erros_unicos) > 10:
                print(f"   ... e mais {len(erros_unicos) - 10}")
            sys.stdout.flush()

        # Salva o JSON Ouro
        output_path = ouro_dir / f"verbas_gabinete_{ano_str}_gold.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(registros_ouro, f, ensure_ascii=False, indent=2)

        print(f"{C_GREEN}[RONALDO] 💾 Arquivo salvo: {output_path.name}{C_END}")
        print(f"{C_GREEN}[RONALDO] 💎 Registros Ouro: {len(registros_ouro)}{C_END}")
        sys.stdout.flush()

    # --- Resumo Final ────────────────────────────────────────────────────
    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print(f"{C_GREEN}✅ RONALDO FINALIZADO!{C_END}")
    print(f"{C_WHITE}   Total Ouro gerados : {total_ouro}")
    print(f"   Sem vínculo parl.  : {total_sem_vinculo}")
    print(f"   Output dir         : {ouro_dir}{C_END}")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")
    print(f"[AGENT DONE] ✅ Ronaldo encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
