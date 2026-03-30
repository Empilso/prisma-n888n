#!/usr/bin/env python3
"""
🐘 AGENT ZIDANE-D — THE LOADER v3.2 | SYNC ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRATÉGIA: UPSERT de Elite — Identidade + Inteligência → Supabase
MOTOR:      REST API Supabase (DADOS-PRISMA)
SAÍDA:      Tabela 'parlamentares' (dinâmico)
FIX v3.2:   Deduplica por prisma_id antes do upsert
            (evita 300+ requests redundantes por duplicatas de leg_XX/)
            Merge completo de historico_legislaturas de TODOS os arquivos
            antes de enviar 1 único upsert por parlamentar
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
        "2. Deduplicação: 1 único registro por parlamentar (merge de todas as legislaturas).",
        "3. Mapeamento Premium de IA: carreira_politica, formacao_academica, tags_estrategicas.",
        "4. Fallback de nomes nulos.",
        "5. Integridade Referencial: Nenhum registro sem prisma_id é enviado.",
        "6. v3.2: FIX deduplication + merge legislaturas antes do upsert.",
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


def extrair_legislaturas(r: dict, db_legislaturas: list) -> list:
    legs = set(str(x) for x in (db_legislaturas or []))
    historico = r.get("historico_legislaturas")
    if historico and isinstance(historico, list):
        for leg in historico:
            legs.add(str(leg))
    leg_alvo = r.get("legislatura_alvo")
    if leg_alvo:
        legs.add(str(leg_alvo))
    leg_legado = r.get("legislatura")
    if leg_legado:
        # Extrai apenas o numero da legislatura ex: "20ª Legislatura" -> "20"
        match = re.search(r'(\d+)', str(leg_legado))
        if match:
            legs.add(match.group(1))
    return sorted(legs)


def calcular_mandatos_count(r: dict) -> int:
    mandatos = r.get("mandatos")
    if mandatos and isinstance(mandatos, list) and len(mandatos) > 0:
        return len(mandatos)
    legs = r.get("historico_legislaturas") or []
    return len(legs) if legs else (r.get("mandatos_count") or 0)


def deduplicar_records(records: list) -> list:
    """
    v3.2 FIX PRINCIPAL:
    Agrupa todos os arquivos pelo prisma_id.
    Para cada parlamentar, pega o arquivo da legislatura mais recente
    como base e faz MERGE de todas as legislaturas encontradas.
    Resultado: 1 registro limpo por parlamentar.
    """
    grupos = {}
    for r in records:
        pid = r.get("prisma_id")
        if not pid:
            continue
        if pid not in grupos:
            grupos[pid] = []
        grupos[pid].append(r)

    resultado = []
    for pid, lista in grupos.items():
        # Ordena por legislatura_alvo desc para pegar a mais recente como base
        lista_ord = sorted(
            lista,
            key=lambda x: int(x.get("legislatura_alvo") or 0),
            reverse=True
        )
        base = lista_ord[0]  # registro mais recente = base

        # Merge de TODAS as legislaturas de todos os arquivos desse parlamentar
        legs_merged = set()
        for item in lista:
            hist = item.get("historico_legislaturas") or []
            for l in hist:
                legs_merged.add(str(l))
            leg_alvo = item.get("legislatura_alvo")
            if leg_alvo:
                legs_merged.add(str(leg_alvo))

        base["historico_legislaturas"] = sorted([int(x) for x in legs_merged if x.isdigit()])
        resultado.append(base)

    return resultado


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

    # Carrega todos os arquivos
    records_brutos = []
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            records_brutos.append(json.load(f))

    # ━━━ v3.2 FIX: Deduplica ANTES de qualquer coisa ━━━━━━━━━━━━━━━━━━━━━
    records = deduplicar_records(records_brutos)

    print(f"\n{C_PURPLE}╔" + "═"*68 + f"╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}   ZIDANE-D THE LOADER v3.2 | SYNC ENGINE   {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚" + "═"*68 + f"╝{C_END}\n")
    print(f"{C_CYAN}📦 Arquivos lidos: {len(records_brutos)} | Após deduplicação: {C_BOLD}{C_GREEN}{len(records)} parlamentares únicos{C_END}")
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

        esfera = r.get("esfera", "estadual")
        uf     = r.get("uf",     "BA")
        casa   = r.get("casa",   "ALBA")
        slug   = gerar_slug(nome_urna, esfera, uf, casa)

        # Golden Record: pre-check no banco
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

        legislaturas_final = extrair_legislaturas(r, db_legislaturas)
        mandatos_list      = r.get("mandatos", [])
        mandatos_count     = calcular_mandatos_count(r)
        sexo_bruto         = r.get("sexo", "")
        sexo_tratado       = sexo_bruto[0].upper() if isinstance(sexo_bruto, str) and sexo_bruto else None
        tags               = r.get("tags_estrategicas", [])
        tags_count         = len(tags) if tags else 0
        contatos           = r.get("contatos", {}) or {}

        payload = {
            "prisma_id":            prisma_id,
            "id_alba":              str(r.get("parlamentar_id")) if r.get("parlamentar_id") else None,
            "nome_civil":           nome_civil,
            "nome_normalizado":     r.get("nome_limpo"),
            "nome_urna":            r.get("nome_eleitoral"),
            "url_oficial":          r.get("url_oficial"),
            "foto_url":             r.get("foto_url"),
            "slug":                 slug,
            "esfera":               esfera,
            "uf":                   uf,
            "casa":                 casa,
            "sexo":                 sexo_tratado,
            "data_nascimento":      r.get("data_nascimento"),
            "municipio_nascimento": r.get("municipio_nascimento"),
            "uf_nascimento":        r.get("uf_nascimento"),
            "profissao":            r.get("profissao"),
            "estado_civil":         r.get("estado_civil"),
            "conjuge":              r.get("conjuge"),
            "filhos":               r.get("filhos"),
            "filiacao_mae_pai":     r.get("filiacao_mae_pai"),
            "sigla_partido":        r.get("sigla_partido"),
            "partido_nome":         r.get("partido"),
            "biografia_completa":   r.get("biografia_completa"),
            "biografia_resumo":     r.get("biografia_resumo"),
            "mandatos":             mandatos_list,
            "mandatos_count":       mandatos_count,
            "legislaturas":         legislaturas_final,
            "email":                contatos.get("email") if isinstance(contatos, dict) else None,
            "telefones":            [f"(71) {t}" for t in contatos.get("telefones", []) if t] if isinstance(contatos, dict) else [],
            "gabinete_endereco":    r.get("gabinete_endereco"),
            "carreira_politica":    r.get("carreira_politica", []),
            "formacao_academica":   r.get("formacao_academica", []),
            "tags_estrategicas":    tags,
            "lideranca_e_comissoes": r.get("lideranca_e_comissoes", []),
            "condecoracoes":        r.get("condecoracoes", []),
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
                    f"| {casa:<8} | {uf} "
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
    print(f"{C_BOLD}{C_CYAN}  🐘 Arquivos lidos: {len(records_brutos)} → Deduplicados: {len(records)} parlamentares únicos{C_END}")
    print(f"{C_PURPLE}{'=' * 70}{C_END}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
