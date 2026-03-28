import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

def main():
    # Carrega variáveis de ambiente
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)
    
    # 1. Configurar credenciais do Supabase
    # Prioriza o DADOS_PRISMA, com fallback para o principal
    project_id = os.getenv("DADOS_PRISMA_PROJECT", "hrrzwhkosgzungqxlcps")
    supa_url = f"https://{project_id}.supabase.co"
    
    supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_DADOS_PRISMA_KEY") or os.getenv("SUPABASE_KEY")
    
    if not supa_key:
        print("[AGENT ZIDANE-D] ❌ Erro: Chaves do Supabase não encontradas no .env")
        sys.exit(1)
        
    # 2. Carregar o Hub Normalizado (Entrada)
    base_dir = Path(__file__).resolve().parent.parent.parent
    hub_path = base_dir / "data" / "saida" / "parlamentares" / "parlamentares_hub_normalized.json"
    
    if not hub_path.exists():
        print(f"[AGENT ZIDANE-D] ❌ Erro: Arquivo {hub_path.name} não encontrado.")
        sys.exit(1)
        
    try:
        with open(hub_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[AGENT ZIDANE-D] ❌ Erro ao ler JSON: {e}")
        sys.exit(1)
        
    records = data.get("parlamentares", [])
    if not records:
        print("[AGENT ZIDANE-D] ⚠️ Nenhum parlamentar encontrado no arquivo.")
        sys.exit(0)
        
    print(f"[AGENT ZIDANE-D] 🐘 Iniciando Carga Supabase ({len(records)} registros)...")
    sys.stdout.flush()
    
    # 3. Preparar requisição REST para UPSERT
    headers = {
        "apikey": supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal,resolution=merge-duplicates"
    }
    
    endpoint = f"{supa_url}/rest/v1/parlamentares"
    
    sucesso = 0
    erros = 0
    
    # 4. Inserção iterativa (Upsert)
    for r in records:
        nome_urna = r.get("nome_eleitoral") or r.get("nome_civil") or r.get("prisma_id", "Desconhecido")
        prisma_id = r.get("prisma_id")
        
        if not prisma_id:
            print(f"[AGENT ZIDANE-D] ⚠️ Ignorado {nome_urna} (Sem prisma_id)")
            erros += 1
            continue
            
        contatos = r.get("contatos", {})
        sexo_bruto = r.get("sexo")
        sexo_tratado = sexo_bruto[0].upper() if (sexo_bruto and isinstance(sexo_bruto, str) and len(sexo_bruto) > 0) else None

        payload = {
            "prisma_id": prisma_id,
            "id_alba": str(r.get("parlamentar_id")) if r.get("parlamentar_id") else None,
            "nome_civil": r.get("nome_civil") or r.get("nome_limpo") or r.get("nome_eleitoral") or "Parlamentar ALBA",
            "nome_normalizado": r.get("nome_limpo"),
            "nome_urna": r.get("nome_eleitoral"),
            "sigla_partido": r.get("sigla_partido"),
            "partido_nome": r.get("partido"),
            "profissao": r.get("profissao"),
            "data_nascimento": r.get("data_nascimento"),
            "sexo": sexo_tratado,
            "conjuge": r.get("conjuge"),
            "filhos": r.get("filhos"),
            "foto_url": r.get("foto_url"),
            "biografia_completa": r.get("biografia_completa"),
            "biografia_resumo": r.get("biografia_resumo"),
            "mandatos": r.get("mandatos", []),
            "mandatos_count": r.get("mandatos_count", 0),
            "email": contatos.get("email") if isinstance(contatos, dict) else None,
            "telefones": contatos.get("telefones", []) if isinstance(contatos, dict) else [],
            "gabinete_endereco": r.get("gabinete_endereco"),
            "fonte_portal": r.get("fonte_portal"),
            "versao_zidane": r.get("versao_zidane"),
            "qualidade_score": r.get("qualidade_score"),
            "processado_em": r.get("processado_em"),
            "metadados": {
                "formacao_academica": r.get("formacao_academica", []),
                "lideranca_e_comissoes": r.get("lideranca_e_comissoes", []),
                "condecoracoes": r.get("condecoracoes", []),
                "tags_estrategicas": r.get("tags_estrategicas", [])
            }
        }
        
        params = {"on_conflict": "prisma_id"}
        
        try:
            resp = requests.post(endpoint, headers=headers, params=params, json=payload)
            if resp.status_code in [200, 201, 204]:
                print(f"[ZIDANE-D] 🎯 Sincronizando: {nome_urna}... OK")
                sucesso += 1
            else:
                print(f"[ZIDANE-D] ❌ ERROR {nome_urna}: {resp.status_code} - {resp.text}")
                erros += 1
        except Exception as e:
            print(f"[ZIDANE-D] ❌ ERROR CATCH {nome_urna}: {e}")
            erros += 1
            
        sys.stdout.flush()
        
    print(f"\n[AGENT ZIDANE-D] 🎯 Carga Finalizada: Sucesso: {sucesso} | Erros: {erros}")
    print("[AGENT ZIDANE-D] [AGENT DONE] Operação concluída.")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
