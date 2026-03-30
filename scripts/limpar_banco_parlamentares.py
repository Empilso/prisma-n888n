#!/usr/bin/env python3
"""
🧹 PRISMA — LIMPEZA DO BANCO DE PARLAMENTARES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USO: python scripts/limpar_banco_parlamentares.py

O QUE FAZ:
  1. Conta quantos registros existem na tabela 'parlamentares'
  2. Pede confirmação antes de apagar
  3. Apaga TODOS os registros da tabela
  4. Confirma que a tabela ficou limpa

APÓS RODAR ESTE SCRIPT, rode o pipeline completo:
  python src/agents/agent_zidane_c_enricher.py
  python src/agents/agent_zidane_c_brain.py
  python src/agents/agent_zidane_d_loader.py
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

C_RED    = "\033[91m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN   = "\033[96m"
C_BOLD   = "\033[1m"
C_END    = "\033[0m"

def main():
    env_path = Path(__file__).resolve().parent.parent / ".env"
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

    headers = {
        "apikey":        supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type":  "application/json",
        "Prefer":        "count=exact",
    }
    endpoint = f"{supa_url}/rest/v1/parlamentares"

    print(f"\n{C_BOLD}{C_YELLOW}{'='*60}{C_END}")
    print(f"{C_BOLD}{C_RED}  🧹 PRISMA — LIMPEZA DO BANCO DE PARLAMENTARES{C_END}")
    print(f"{C_BOLD}{C_YELLOW}{'='*60}{C_END}\n")

    # 1. Contar registros atuais
    try:
        resp = requests.get(f"{endpoint}?select=prisma_id", headers=headers, timeout=10)
        total = len(resp.json()) if resp.status_code == 200 else "?"
        print(f"{C_CYAN}📊 Registros atuais na tabela 'parlamentares': {C_BOLD}{total}{C_END}")
    except Exception as e:
        print(f"{C_RED}❌ Erro ao contar registros: {e}{C_END}")
        sys.exit(1)

    # 2. Pedir confirmacao
    print(f"\n{C_RED}{C_BOLD}⚠️  ATENCAO: Isso vai apagar TODOS os {total} registros!{C_END}")
    print(f"{C_YELLOW}   Apos limpar, rode o pipeline completo para recarregar.{C_END}\n")
    confirm = input(f"{C_BOLD}   Digite 'LIMPAR' para confirmar: {C_END}").strip()

    if confirm != "LIMPAR":
        print(f"\n{C_GREEN}✅ Operacao cancelada. Banco intacto.{C_END}\n")
        sys.exit(0)

    # 3. Apagar todos os registros
    # DELETE sem filtro apaga tudo (Supabase exige neq para deletar todos)
    print(f"\n{C_YELLOW}🔄 Apagando registros...{C_END}")
    try:
        del_headers = {**headers, "Prefer": "return=minimal"}
        # Deleta onde prisma_id nao eh nulo (ou seja, tudo)
        resp = requests.delete(
            f"{endpoint}?prisma_id=neq.ZZZZ_PLACEHOLDER_QUE_NAO_EXISTE",
            headers=del_headers,
            timeout=30
        )
        # Tenta deletar com filtro diferente caso o acima nao funcione
        if resp.status_code not in [200, 204]:
            resp = requests.delete(
                f"{endpoint}?id=gte.0",
                headers=del_headers,
                timeout=30
            )
        if resp.status_code in [200, 204]:
            print(f"{C_GREEN}{C_BOLD}✅ Todos os registros apagados com sucesso!{C_END}")
        else:
            print(f"{C_RED}❌ Erro ao apagar: {resp.status_code} — {resp.text[:300]}{C_END}")
            sys.exit(1)
    except Exception as e:
        print(f"{C_RED}❌ Excecao: {e}{C_END}")
        sys.exit(1)

    # 4. Confirmar que ficou vazio
    try:
        resp2 = requests.get(f"{endpoint}?select=prisma_id", headers=headers, timeout=10)
        restantes = len(resp2.json()) if resp2.status_code == 200 else "?"
        print(f"{C_CYAN}📊 Registros restantes: {C_BOLD}{restantes}{C_END}")
    except Exception:
        pass

    print(f"\n{C_GREEN}{C_BOLD}{'='*60}{C_END}")
    print(f"{C_GREEN}{C_BOLD}  ✅ BANCO LIMPO! Agora rode o pipeline:{C_END}")
    print(f"{C_CYAN}  1. python src/agents/agent_zidane_c_enricher.py{C_END}")
    print(f"{C_CYAN}  2. python src/agents/agent_zidane_c_brain.py{C_END}")
    print(f"{C_CYAN}  3. python src/agents/agent_zidane_d_loader.py{C_END}")
    print(f"{C_GREEN}{C_BOLD}{'='*60}{C_END}\n")


if __name__ == "__main__":
    main()
