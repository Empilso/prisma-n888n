#!/usr/bin/env python3
"""
🐘 AGENT ZIDANE-D — THE LOADER v3.1 | SYNC ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRATÉGIA: UPSERT de Elite — Identidade + Inteligência → Supabase
MOTOR:      REST API Supabase (DADOS-PRISMA)
SAÍDA:      Tabela 'parlamentares' (dinâmico)
NEW v3.1:   FIX legislaturas — usa historico_legislaturas + legislatura_alvo (Zidane-C v6)
            FIX mandatos_count — calculado via len(mandatos)
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
    "visao_geral": {
        "missao": "Sincronizar a Identidade Suprema dos parlamentares para o banco PRISMA DADOS (Supabase).",
        "especialidade": "Loader de Elite | REST UPSERT com mapeamento premium de todos os campos de IA",
        "protocolo_tecnico": "Python + Supabase REST API (DADOS-PRISMA)",
        "camada_dados": "Ouro (Carga Final — Identidade + Inteligência)",
    },
    "diretrizes": [
        "1. Upsert por prisma_id (chave mestra de conflito).",
        "2. Mapeamento Premium de IA: carreira_politica, formacao_academica, tags_estrategicas, lideranca_e_comissoes, condecoracoes.",
        "3. Fallback de nomes nulos: nome_civil usa nome_limpo → nome_eleitoral.",
        "4. Integridade Referencial: Nenhum registro sem prisma_id é enviado.",
        "5. DDD 71 aplicado em todos os telefones de gabinete (Salvador-BA).",
        "6. v3.1: FIX legislaturas usando historico_legislaturas do Zidane-C + mandatos_count correto.",
    ],
}

C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_END    = "\033[0m"


def gerar_slug(nome: str, esfera: str, uf: str, casa: str) -> str:
    """Gera slug dinâmico baseado em nome + contexto geográfico."""
    nome_slug = (
        nome.lower()
        .strip()
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


def extrair_legislaturas(r: dict, db_legislaturas: list) -> list:
    """
    v3.1 FIX — Monta a lista final de legislaturas corretamente.
    Fontes (em ordem de prioridade):
      1. historico_legislaturas (int[]) — campo gerado pelo Zidane-C v6
      2. legislatura_alvo (str) — campo gerado pelo Zidane-C v6
      3. legislatura (str) — campo legado (Zidane-C v5 e anteriores)
      4. db_legislaturas — o que já existe no banco (merge)
    Retorna lista de strings (ex: ["17", "18", "19", "20"]).
    """
    legs = set(str(x) for x in (db_legislaturas or []))

    # Fonte 1: historico_legislaturas (lista de ints do Zidane-C v6)
    historico = r.get("historico_legislaturas")
    if historico and isinstance(historico, list):
        for leg in historico:
            legs.add(str(leg))

    # Fonte 2: legislatura_alvo (string do Zidane-C v6)
    leg_alvo = r.get("legislatura_alvo")
    if leg_alvo:
        legs.add(str(leg_alvo))

    # Fonte 3: legislatura (campo legado)
    leg_legado = r.get("legislatura")
    if leg_legado:
        legs.add(str(leg_legado))

    return sorted(legs)


def calcular_mandatos_count(r: dict) -> int:
    """
    v3.1 FIX — Calcula mandatos_count de forma confiável.
    Usa len(mandatos) se disponível, senão len(legislaturas).
    """
    mandatos = r.get("mandatos")
    if mandatos and isinstance(mandatos, list) and len(mandatos) > 0:
        return len(mandatos)
    # fallback: 1 mandato por legislatura detectada
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
        print(f"{C_RED}❌ ERRO: Chave do Supabase não encontrada no .env{C_END}")
        sys.exit(1)

    enriquecidos_dir = base_dir / "data" / "saida" / "parlamentares" / "enriquecidos"
    json_files = glob.glob(str(enriquecidos_dir / "**" / "*.json"), recursive=True)
    if not json_files:
        print(f"{C_YELLOW}⚠️ Nenhum parlamentar encontrado em {enriquecidos_dir}.{C_END}")
        sys.exit(0)

    records = []
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            records.append(json.load(f))

    print(f"\n{C_PURPLE}╔════════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}   ZIDANE-D THE LOADER v3.1 | SYNC ENGINE ({len(records)} PARLAMENTARES)   {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚════════════════════════════════════════════════════════════════════╝{C_END}\n")
    print(f"{C_CYAN}📦 {len(records)} biografias carregadas de {enriquecidos_dir}.{C_END}")
    print(f"{C_CYAN}🎯 Alvo: {supa_url}/rest/v1/parlamentares{C_END}\n")
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

        # ─── Contexto geográfico ─────────────────────────────────────────
        esfera = r.get("esfera", "estadual")
        uf     = r.get("uf",     "BA")
        casa   = r.get("casa",   "ALBA")

        # ─── Slug dinâmico ───────────────────────────────────────────────
        slug = gerar_slug(nome_urna, esfera, uf, casa)

        # ─── GOLDEN RECORD: PRE-CHECK IDENTIDADE NO BANCO ───────────────
        db_legislaturas = []
        q_nome = r.get("nome_limpo")
        if q_nome:
            try:
                check_url = f"{endpoint}?nome_normalizado=eq.{requests.utils.quote(q_nome)}&select=prisma_id,legislaturas"
                check_resp = requests.get(check_url, headers=headers, timeout=10)
                if check_resp.status_code == 200:
                    matches = check_resp.json()
                    if matches:
                        old_id = prisma_id
                        prisma_id       = matches[0]["prisma_id"]
                        db_legislaturas = matches[0].get("legislaturas") or []
                        if old_id != prisma_id:
                            print(f"{C_CYAN}[ZIDANE-D] 🔗 Golden Record: {q_nome} ➞ ID herdado: {prisma_id[:8]}{C_END}")
            except Exception as e:
                print(f"{C_YELLOW}[ZIDANE-D] ⚠️ Erro no Pre-Check: {e}{C_END}")

        # ─── v3.1 FIX: Legislaturas completas via função dedicada ────────
        legislaturas_final = extrair_legislaturas(r, db_legislaturas)

        # ─── v3.1 FIX: mandatos_count confiável ─────────────────────────
        mandatos_list  = r.get("mandatos", [])
        mandatos_count = calcular_mandatos_count(r)

        sexo_bruto   = r.get("sexo", "")
        sexo_tratado = sexo_bruto[0].upper() if isinstance(sexo_bruto, str) and sexo_bruto else None

        tags       = r.get("tags_estrategicas", [])
        tags_count = len(tags) if tags else 0
        contatos   = r.get("contatos", {}) or {}

        # ─── PAYLOAD OURO v3.1 ──────────────────────────────────────────
        payload = {
            # Identidade
            "prisma_id":            prisma_id,
            "id_alba":              str(r.get("parlamentar_id")) if r.get("parlamentar_id") else None,
            "nome_civil":           nome_civil,
            "nome_normalizado":     r.get("nome_limpo"),
            "nome_urna":            r.get("nome_eleitoral"),
            "url_oficial":          r.get("url_oficial"),
            "foto_url":             r.get("foto_url"),
            "slug":                 slug,

            # Contexto geográfico
            "esfera":               esfera,
            "uf":                   uf,
            "casa":                 casa,

            # Dados pessoais
            "sexo":                 sexo_tratado,
            "data_nascimento":      r.get("data_nascimento"),
            "municipio_nascimento": r.get("municipio_nascimento"),
            "uf_nascimento":        r.get("uf_nascimento"),
            "profissao":            r.get("profissao"),
            "estado_civil":         r.get("estado_civil"),
            "conjuge":              r.get("conjuge"),
            "filhos":               r.get("filhos"),
            "filiacao_mae_pai":     r.get("filiacao_mae_pai"),

            # Partido
            "sigla_partido":        r.get("sigla_partido"),
            "partido_nome":         r.get("partido"),

            # Bios
            "biografia_completa":   r.get("biografia_completa"),
            "biografia_resumo":     r.get("biografia_resumo"),

            # Mandatos e Legislaturas — v3.1 CORRIGIDO
            "mandatos":             mandatos_list,
            "mandatos_count":       mandatos_count,
            "legislaturas":         legislaturas_final,

            # Contato
            "email":                contatos.get("email") if isinstance(contatos, dict) else None,
            "telefones":            [f"(71) {t}" for t in contatos.get("telefones", []) if t] if isinstance(contatos, dict) else [],
            "gabinete_endereco":    r.get("gabinete_endereco"),

            # Inteligência IA (Zidane-C)
            "carreira_politica":    r.get("carreira_politica", []),
            "formacao_academica":   r.get("formacao_academica", []),
            "tags_estrategicas":    tags,
            "lideranca_e_comissoes": r.get("lideranca_e_comissoes", []),
            "condecoracoes":        r.get("condecoracoes", []),

            # Qualidade e versionamento
            "versao_zidane":        r.get("versao_zidane"),
            "versao_enricher":      r.get("versao_enricher"),
            "qualidade_score":      r.get("qualidade_score"),
            "fonte_portal":         r.get("fonte_portal"),
            "processado_em":        r.get("processado_em"),
        }

        params = {"on_conflict": "prisma_id"}

        try:
            resp = requests.post(endpoint, headers=headers, params=params, json=payload, timeout=15)
            if resp.status_code in [200, 201, 204]:
                print(
                    f"{C_GREEN}[ZIDANE-D] 🐘 {C_BOLD}{nome_urna:<30}{C_END}{C_GREEN} "
                    f"| {casa:<8} | {esfera:<10} | {uf} "
                    f"| Legs: {legislaturas_final} "
                    f"| Mandatos: {mandatos_count} "
                    f"| Tags: {tags_count} | ✅ OURO{C_END}"
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
    print(f"{C_PURPLE}{'=' * 70}{C_END}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
