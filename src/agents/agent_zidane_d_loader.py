#!/usr/bin/env python3
"""
🐘 AGENT ZIDANE-D — THE LOADER v2.0 | SYNC ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRATÉGIA: UPSERT de Elite — Identidade + Inteligência → Supabase
MOTOR:      REST API Supabase (DADOS-PRISMA)
SAÍDA:      Tabela 'parlamentares' (63 registros enriquecidos)
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Sincronizar a Identidade Suprema dos 63 parlamentares da ALBA para o banco de dados PRISMA DADOS (Supabase), unificando dados biográficos brutos com a inteligência IA do Cérebro Zidane-C.",
        "especialidade": "Loader de Elite | REST UPSERT com mapeamento premium de todos os campos de IA",
        "protocolo_tecnico": "Python + Supabase REST API (DADOS-PRISMA)",
        "camada_dados": "Ouro (Carga Final — Identidade + Inteligência)",
    },
    "diretrizes": [
        "1. Upsert por prisma_id (chave mestra de conflito).",
        "2. Mapeamento Premium de IA: carreira_politica, formacao_academica, tags_estrategicas, lideranca_e_comissoes, condecoracoes mapeados como colunas reais.",
        "3. Fallback de nomes nulos: nome_civil usa nome_limpo → nome_eleitoral para não violar constraint NOT NULL.",
        "4. Integridade Referencial: Nenhum registro sem prisma_id é enviado.",
    ],
    "apuracao": {
        "safras_suportadas": ["17", "18", "19", "20 (Atual)"],
        "entrada_esperada": "data/saida/parlamentares/parlamentares_hub_normalized.json",
        "saida_esperada": "Supabase PRISMA DADOS (Tabela parlamentares)"
    }
}

# --- Cockpit Visual ---
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_BOLD   = "\033[1m"
C_END    = "\033[0m"

def main():
    # ─── BOOT ──────────────────────────────────────────────────────────────
    print(f"\n{C_PURPLE}╔════════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}       ZIDANE-D THE LOADER v2.0 | SYNC ENGINE (63 PARLAMENTARES)  {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚════════════════════════════════════════════════════════════════════╝{C_END}\n")

    # 1. Variáveis de ambiente
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

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

    import glob
    enriquecidos_dir = base_dir / "data" / "saida" / "parlamentares" / "enriquecidos"
    
    json_files = glob.glob(str(enriquecidos_dir / "**" / "*.json"), recursive=True)
    if not json_files:
        print(f"{C_YELLOW}⚠️ Nenhum parlamentar encontrado em {enriquecidos_dir}.{C_END}")
        sys.exit(0)

    records = []
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            records.append(json.load(f))

    print(f"{C_CYAN}📦 {len(records)} biografias carregadas de {enriquecidos_dir}.{C_END}")
    print(f"{C_CYAN}🎯 Alvo: {supa_url}/rest/v1/parlamentares{C_END}\n")
    sys.stdout.flush()

    # 3. Headers REST
    headers = {
        "apikey":        supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal,resolution=merge-duplicates",
    }
    endpoint = f"{supa_url}/rest/v1/parlamentares"

    sucesso = 0
    erros   = 0

    # 4. UPSERT loop
    for r in records:
        nome_urna  = r.get("nome_eleitoral") or r.get("nome_limpo") or r.get("nome_civil") or "Desconhecido"
        nome_civil = r.get("nome_civil") or r.get("nome_limpo") or r.get("nome_eleitoral") or "Parlamentar ALBA"
        
        prisma_id  = r.get("prisma_id")

        if not prisma_id:
            print(f"{C_YELLOW}[ZIDANE-D] ⚠️ Ignorado {nome_urna} (sem prisma_id_base){C_END}")
            erros += 1
            continue

        telefone = r.get("contatos", {}) or {}
        # ---- GOLDEN RECORD: PRE-CHECK IDENTIDADE NO BANDO ----
        q_nome = r.get("nome_limpo")
        db_legislaturas = []
        if q_nome:
            try:
                # Busca exata pelo nome normalizado
                check_url = f"{endpoint}?nome_normalizado=eq.{requests.utils.quote(q_nome)}&select=prisma_id,legislaturas"
                check_resp = requests.get(check_url, headers=headers, timeout=10)
                if check_resp.status_code == 200:
                    matches = check_resp.json()
                    if matches and len(matches) > 0:
                        # Achou! Vamos herdar o ID existente em vez de criar duplicata
                        old_id = prisma_id
                        prisma_id = matches[0]["prisma_id"]
                        db_legislaturas = matches[0].get("legislaturas") or []
                        if old_id != prisma_id:
                            print(f"{C_CYAN}[ZIDANE-D] 🔗 Golden Record (Match): {q_nome} ➔ Herdado ID: {prisma_id[:8]}{C_END}")
            except Exception as e:
                print(f"{C_YELLOW}[ZIDANE-D] ⚠️ Erro no Pre-Check de Identidade: {e}{C_END}")
        sexo_bruto = r.get("sexo", "")
        sexo_tratado = (
            sexo_bruto[0].upper()
            if isinstance(sexo_bruto, str) and len(sexo_bruto) > 0
            else None
        )

        tags = r.get("tags_estrategicas", [])
        tags_count = len(tags) if tags else 0

        # ─── PAYLOAD OURO ESTRUTURADO ──────────────────────────────────────
        payload = {
            # Identidade
            "prisma_id":            prisma_id,
            "id_alba":              str(r.get("parlamentar_id")) if r.get("parlamentar_id") else None,
            "nome_civil":           nome_civil,
            "nome_normalizado":     r.get("nome_limpo"),
            "nome_urna":            r.get("nome_eleitoral"),
            "url_oficial":          r.get("url_oficial"),
            "foto_url":             r.get("foto_url"),

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

            # Mandatos e Legislaturas
            "mandatos":             r.get("mandatos", []),
            "mandatos_count":       r.get("mandatos_count", 0),
            "legislaturas":         list(set(db_legislaturas + ([str(r.get("legislatura"))] if r.get("legislatura") else []))),

            # Contato
            "email":                contatos.get("email") if isinstance(contatos, dict) else None,
            "telefones":            contatos.get("telefones", []) if isinstance(contatos, dict) else [],
            "gabinete_endereco":    r.get("gabinete_endereco"),

            # ── Inteligência IA (Campos Ouro do Zidane-C) ──
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
                    f"{C_GREEN}[ZIDANE-D] 🐘 Sincronizando Inteligência: "
                    f"{C_BOLD}{nome_urna}{C_END}{C_GREEN} | "
                    f"Tags: {tags_count} | Status: OURO ✅{C_END}"
                )
                sucesso += 1
            else:
                print(f"{C_RED}[ZIDANE-D] ❌ ERRO {nome_urna}: {resp.status_code} — {resp.text[:200]}{C_END}")
                erros += 1
        except Exception as e:
            print(f"{C_RED}[ZIDANE-D] ❌ EXCEÇÃO {nome_urna}: {e}{C_END}")
            erros += 1

        sys.stdout.flush()

    # 5. Relatório Final
    print(f"\n{C_PURPLE}{'═' * 70}{C_END}")
    print(f"{C_BOLD}{C_GREEN}  ✅ CARGA FINALIZADA — Sucesso: {sucesso} | Erros: {erros} | Total: {sucesso + erros}{C_END}")
    print(f"{C_PURPLE}{'═' * 70}{C_END}\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
