import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Fix path para importar utils do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "https://albalegis.nopapercloud.com.br"

def fetch_parlamentar_detalhes(parlamentar_id: int) -> Dict:
    """Consulta detalhes profundos do parlamentar via API de Dados Abertos."""
    api_url = f"{BASE_URL}/api/publico/parlamentar/"
    params = {"parlamentarID": parlamentar_id}
    
    try:
        resp = requests.get(api_url, params=params, verify=False, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else {}
    except Exception as e:
        print(f"❌ [ZIDANE-B] Erro ao buscar detalhes ID {parlamentar_id}: {e}")
        return {}

def fetch_proposicoes(autor_id: int) -> List[Dict]:
    """Busca as produções legislativas via API oficial."""
    if not autor_id: return []
    api_url = f"{BASE_URL}/api/publico/proposicao/"
    params = {"autorID": autor_id, "qtd": 50, "pag": 1}
    
    try:
        resp = requests.get(api_url, params=params, verify=False, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ [ZIDANE-B] Erro ao buscar proposições Autor {autor_id}: {e}")
        return []

def process_deputado(deputado, output_dir):
    dep_id = deputado.get('parlamentar_id')
    autor_id = deputado.get('autor_id')
    nome = deputado.get('nome_parlamentar')
    
    print(f"⚙️ [ZIDANE-B] Processando {nome} (ID: {dep_id})...", flush=True)
    
    # Busca dados rincos via API
    detalhes = fetch_parlamentar_detalhes(dep_id)
    proposicoes = fetch_proposicoes(autor_id)
    
    raw_data = {
        "parlamentar_id": dep_id,
        "autor_id": autor_id,
        "nome_civil": detalhes.get("parlamentarNomeCivil", ""),
        "biografia_resumo": detalhes.get("parlamentarDescricao", ""),
        "profissao": detalhes.get("parlamentarProfissao", ""),
        "sexo": detalhes.get("parlamentarSexo", ""),
        "data_nascimento": detalhes.get("parlamentarDataNascimento", ""),
        "partido": detalhes.get("parlamentarSiglaPartido", ""),
        "email": detalhes.get("parlamentarEmail", ""),
        "telefone": detalhes.get("parlamentarTelefone", ""),
        "mandatos": detalhes.get("mandatos", []),
        "comissoes": detalhes.get("comissoes", []),
        "proposicoes": proposicoes,
        "coletado_em": datetime.utcnow().isoformat() + "Z"
    }
    
    # Save JSON
    out_path = os.path.join(output_dir, f"parlamentar_{dep_id}_api.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    return True

def run_agent_b():
    print("🚀 [AGENT zidane_b] INICIANDO OPERAÇÃO VIA DADOS ABERTOS (API B)...", flush=True)
    
    base_dir = Path(__file__).resolve().parent.parent.parent
    ids_file = base_dir / "data" / "parlamentares" / "parlamentares_ids.json"
    out_dir = base_dir / "data" / "parlamentares" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if not ids_file.exists():
        print("❌ [AGENT zidane_b] parlamentares_ids.json não encontrado.", flush=True)
        return
        
    with open(ids_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    deputados = data.get("records", [])
    print(f"[zidane_b] 🔍 Carregado {len(deputados)} parlamentares.", flush=True)
    
    success = 0
    # Processa todos os deputados agora que é API (é rápido!)
    for dep in deputados:
        try:
            if process_deputado(dep, out_dir):
                success += 1
        except Exception as e:
            print(f"❌ Erro no Dep {dep.get('nome_parlamentar')}: {e}")
            
    print(f"🏁 [AGENT zidane_b] ✅ Concluído! {success}/{len(deputados)} perfis salvos via API oficial.")

if __name__ == "__main__":
    run_agent_b()
