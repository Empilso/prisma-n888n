#!/usr/bin/env python3
"""
🐘 AGENT ZIDANE-D — THE LOADER v3.3 | SYNC ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ESTRATÉGIA:
  1. Lê todos os enriquecidos/**/*.json (1 por leg por parlamentar)
  2. Agrupa por id_alba (parlamentar_id do ALBA — chave real entre legislaturas)
  3. Para cada parlamentar, pega o arquivo da leg mais recente como base
  4. Faz MERGE de todas as legislaturas_ativas de TODOS os arquivos do mesmo parlamentar
  5. Envia 1 único upsert por parlamentar para o Supabase

RESULTADO ESPERADO:
  - Todos os parlamentares únicos de TODAS as 4 legislaturas no banco
  - Cada um com legislaturas[] correto e completo
  - Sem duplicatas, sem perdas
  - Número de upserts = Número de parlamentares únicos reais

FIX v3.3: Consolida por id_alba em vez de prisma_id
          (prisma_id pode mudar entre versões mas id_alba é o ID real do portal ALBA)
"""

import os
import re
import sys
import json
import glob
import requests
from pathlib import Path
from dotenv import load_dotenv

__PRISMA_MANIFEST__ = {
    "versao": "v3.3",
    "fix": "Consolida por id_alba + merge legislaturas de todas as legs",
    "resultado_esperado": "1 upsert por parlamentar unico (todas as 4 legislaturas)",
}

C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_END    = "\033[0m"


def gerar_slug(nome: str, esfera: str, uf: str, casa: str) -> str:
    nome_slug = (
        nome.lower().strip()
        .encode("ascii", "ignore").decode()
        .replace(" ", "-")
    )
    nome_slug = re.sub(r"[^\w-]", "", nome_slug)
    sufixo_map = {
        "estadual":  f"deputado-{uf.lower()}",
        "federal":   "deputado-federal",
        "municipal": f"vereador-{uf.lower()}",
        "senado":    "senador",
    }
    sufixo = sufixo_map.get(esfera, f"parlamentar-{uf.lower()}")
    return f"{nome_slug}-{sufixo}"


def consolidar_por_id_alba(records: list) -> list:
    """
    LOGICA CORRETA v3.3:

    O Brain salva 1 arquivo por legislatura por parlamentar:
      enriquecidos/leg_17/parlamentar_123_enriquecido.json  <- Joao na leg 17
      enriquecidos/leg_18/parlamentar_123_enriquecido.json  <- Joao na leg 18
      enriquecidos/leg_19/parlamentar_123_enriquecido.json  <- Joao na leg 19
      enriquecidos/leg_20/parlamentar_123_enriquecido.json  <- Joao na leg 20

    E tambem pode ter:
      enriquecidos/leg_17/parlamentar_456_enriquecido.json  <- Maria SOMENTE na leg 17

    Precisamos de:
      -> 1 registro no banco para Joao com legislaturas=[17,18,19,20]
      -> 1 registro no banco para Maria com legislaturas=[17]

    Chave de agrupamento = parlamentar_id (id_alba) pois e o mesmo entre legislaturas.
    """
    grupos = {}  # id_alba -> lista de records

    for r in records:
        id_alba = str(r.get("parlamentar_id", "")).strip()
        if not id_alba:
            # fallback: usa prisma_id se nao tem id_alba
            id_alba = r.get("prisma_id", "")
        if not id_alba:
            continue
        if id_alba not in grupos:
            grupos[id_alba] = []
        grupos[id_alba].append(r)

    resultado = []
    for id_alba, lista in grupos.items():
        # Ordena por legislatura_alvo descrescente — a mais recente e a base
        lista_ord = sorted(
            lista,
            key=lambda x: int(x.get("legislatura_alvo") or 0),
            reverse=True
        )
        base = dict(lista_ord[0])  # copia do mais recente

        # Merge de TODAS as legislaturas de TODOS os arquivos desse id_alba
        legs_merged = set()
        for item in lista:
            # historico_legislaturas ja calculado pelo Brain
            hist = item.get("historico_legislaturas") or []
            for l in hist:
                legs_merged.add(int(l))
            # legislatura_alvo de cada arquivo
            leg_alvo = item.get("legislatura_alvo")
            if leg_alvo and str(leg_alvo).isdigit():
                legs_merged.add(int(leg_alvo))

        base["historico_legislaturas"] = sorted(legs_merged)
        base["legislaturas_merged_count"] = len(legs_merged)
        resultado.append(base)

    return resultado


def calcular_mandatos_count(r: dict) -> int:
    mandatos = r.get("mandatos")
    if mandatos and isinstance(mandatos, list) and len(mandatos) > 0:
        return len(mandatos)
    legs = r.get("historico_legislaturas") or []
    return len(legs) if legs else (r.get("mandatos_count") or 0)


def main():
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)
    base_dir = Path(__file__).resolve().parent.parent.parent

    project_id = os.getenv("DADOS_PRISMA_PROJECT", "hrrzwhkosgzungqxlcps")
    supa_url   = f"https://{project_id}.supabase.co"
    supa_key   = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_DADOS_PRISMA_KEY")
        or os.getenv("SUPABASE_KEY")
    )

    if not supa_key:
        print(f"{C_RED}❌ ERRO: Chave do Supabase nao encontrada no .env{C_END}")
        sys.exit(1)

    enriquecidos_dir = base_dir / "data" / "saida" / "parlamentares" / "enriquecidos"
    json_files = glob.glob(str(enriquecidos_dir / "**" / "*.json"), recursive=True)

    if not json_files:
        print(f"{C_YELLOW}⚠️ Nenhum enriquecido encontrado em {enriquecidos_dir}.{C_END}")
        sys.exit(0)

    # Carrega todos os arquivos
    records_brutos = []
    for fp in json_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                records_brutos.append(json.load(f))
        except Exception as e:
            print(f"{C_YELLOW}⚠️ Erro ao ler {fp}: {e}{C_END}")

    # ====================================================
    # v3.3 FIX PRINCIPAL: Consolida por id_alba
    # ====================================================
    records = consolidar_por_id_alba(records_brutos)

    print(f"\n{C_PURPLE}╔" + "═"*68 + f"╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}   ZIDANE-D THE LOADER v3.3 | SYNC ENGINE   {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚" + "═"*68 + f"╝{C_END}\n")
    print(f"{C_CYAN}📦 Arquivos lidos    : {C_BOLD}{len(records_brutos)}{C_END}{C_CYAN} (1 por leg por parlamentar){C_END}")
    print(f"{C_CYAN}🧙 Apos consolidação : {C_BOLD}{C_GREEN}{len(records)} parlamentares unicos{C_END}")
    print(f"{C_CYAN}🎯 Alvo              : {supa_url}/rest/v1/parlamentares{C_END}\n")
    sys.stdout.flush()

    headers = {
        "apikey":        supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal,resolution=merge-duplicates",
    }
    endpoint = f"{supa_url}/rest/v1/parlamentares"

    sucesso = 0
    erros   = 0

    for r in records:
        nome_urna  = r.get("nome_eleitoral") or r.get("nome_limpo") or r.get("nome_civil") or "Desconhecido"
        nome_civil = r.get("nome_civil")     or r.get("nome_limpo") or r.get("nome_eleitoral") or "Parlamentar"

        prisma_id = r.get("prisma_id")
        if not prisma_id:
            print(f"{C_YELLOW}[ZIDANE-D] ⚠️ Ignorado {nome_urna} (sem prisma_id){C_END}")
            erros += 1
            continue

        esfera = r.get("esfera", "estadual")
        uf     = r.get("uf",     "BA")
        casa   = r.get("casa",   "ALBA")
        slug   = gerar_slug(nome_urna, esfera, uf, casa)

        legislaturas_final = sorted(r.get("historico_legislaturas") or [])
        mandatos_list      = r.get("mandatos", [])
        mandatos_count     = calcular_mandatos_count(r)
        sexo_bruto         = r.get("sexo", "")
        sexo_tratado       = sexo_bruto[0].upper() if isinstance(sexo_bruto, str) and sexo_bruto else None
        tags               = r.get("tags_estrategicas", [])
        tags_count         = len(tags) if tags else 0
        contatos           = r.get("contatos", {}) or {}

        payload = {
            "prisma_id":             prisma_id,
            "id_alba":               str(r.get("parlamentar_id")) if r.get("parlamentar_id") else None,
            "nome_civil":            nome_civil,
            "nome_normalizado":      r.get("nome_limpo"),
            "nome_urna":             r.get("nome_eleitoral"),
            "url_oficial":           r.get("url_oficial"),
            "foto_url":              r.get("foto_url"),
            "slug":                  slug,
            "esfera":                esfera,
            "uf":                    uf,
            "casa":                  casa,
            "sexo":                  sexo_tratado,
            "data_nascimento":       r.get("data_nascimento"),
            "municipio_nascimento":  r.get("municipio_nascimento"),
            "uf_nascimento":         r.get("uf_nascimento"),
            "profissao":             r.get("profissao"),
            "estado_civil":          r.get("estado_civil"),
            "conjuge":               r.get("conjuge"),
            "filhos":                r.get("filhos"),
            "filiacao_mae_pai":      r.get("filiacao_mae_pai"),
            "sigla_partido":         r.get("sigla_partido"),
            "partido_nome":          r.get("partido"),
            "biografia_completa":    r.get("biografia_completa"),
            "biografia_resumo":      r.get("biografia_resumo"),
            "mandatos":              mandatos_list,
            "mandatos_count":        mandatos_count,
            "legislaturas":          legislaturas_final,
            "email":                 contatos.get("email") if isinstance(contatos, dict) else None,
            "telefones":             [f"(71) {t}" for t in contatos.get("telefones", []) if t] if isinstance(contatos, dict) else [],
            "gabinete_endereco":     r.get("gabinete_endereco"),
            "carreira_politica":     r.get("carreira_politica", []),
            "formacao_academica":    r.get("formacao_academica", []),
            "tags_estrategicas":     tags,
            "lideranca_e_comissoes": r.get("lideranca_e_comissoes", []),
            "condecoracoes":         r.get("condecoracoes", []),
            "versao_zidane":         r.get("versao_zidane"),
            "versao_enricher":       r.get("versao_enricher"),
            "qualidade_score":       r.get("qualidade_score"),
            "fonte_portal":          r.get("fonte_portal"),
            "processado_em":         r.get("processado_em"),
        }

        params = {"on_conflict": "prisma_id"}

        try:
            resp = requests.post(endpoint, headers=headers, params=params, json=payload, timeout=15)
            if resp.status_code in [200, 201, 204]:
                print(
                    f"{C_GREEN}[ZIDANE-D] 🐘 {C_BOLD}{nome_urna:<30}{C_END}{C_GREEN} "
                    f"| {casa:<6} | {uf} "
                    f"| Legs: {legislaturas_final} "
                    f"| Mandatos: {mandatos_count} "
                    f"| Tags: {tags_count} | ✅{C_END}"
                )
                sucesso += 1
            else:
                print(f"{C_RED}[ZIDANE-D] ❌ ERRO {nome_urna}: {resp.status_code} — {resp.text[:200]}{C_END}")
                erros += 1
        except Exception as e:
            print(f"{C_RED}[ZIDANE-D] ❌ EXCEÇÃO {nome_urna}: {e}{C_END}")
            erros += 1

        sys.stdout.flush()

    print(f"\n{C_PURPLE}{'=' * 70}{C_END}")
    print(f"{C_BOLD}{C_GREEN}  ✅ CARGA FINALIZADA — Sucesso: {sucesso} | Erros: {erros} | Total: {sucesso + erros}{C_END}")
    print(f"{C_BOLD}{C_CYAN}  📦 Lidos: {len(records_brutos)} arquivos → Consolidados: {len(records)} parlamentares unicos{C_END}")
    print(f"{C_PURPLE}{'=' * 70}{C_END}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
