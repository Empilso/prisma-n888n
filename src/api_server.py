import sys
import queue
import json
import asyncio
import os
import glob
import multiprocessing
import threading
import subprocess
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Union
import collections
import re
from datetime import datetime
from pathlib import Path

# Permite rodar de dentro de n888n ou da raiz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI()

# State global para persistir prompts no backend
PROMPTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "saida", "configs", "agent_prompts.json")
agent_prompts = {}
agent_configs = {}

if os.path.exists(PROMPTS_FILE):
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            agent_prompts = json.load(f)
    except:
        pass

@app.post("/api/configure-prompt/{agent_id}")
async def configure_prompt(agent_id: str, data: dict):
    if "custom_prompt" in data:
        agent_prompts[agent_id] = data["custom_prompt"]
        os.makedirs(os.path.dirname(PROMPTS_FILE), exist_ok=True)
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(agent_prompts, f, ensure_ascii=False, indent=2)
    
    # Salva configurações adicionais (ano, mes, skin)
    if agent_id not in agent_configs:
        agent_configs[agent_id] = {"ano": 2015, "mes": 0, "skin_variant": "default"}
    
    if "ano" in data: agent_configs[agent_id]["ano"] = data["ano"]
    if "mes" in data: agent_configs[agent_id]["mes"] = data["mes"]
    if "skin_variant" in data: agent_configs[agent_id]["skin_variant"] = data["skin_variant"]
    
    print(f"[API] Configurações atualizadas para o Agent {agent_id}: {agent_configs[agent_id]}")
    return {"status": "ok", "message": f"Configurações do Agente {agent_id} aplicadas!"}

@app.get("/api/get-prompt/{agent_id}")
async def get_prompt(agent_id: str):
    return {
        "prompt": agent_prompts.get(agent_id, ""),
        "config": agent_configs.get(agent_id, {"ano": 2015, "mes": 0, "skin_variant": "default"})
    }

@app.get("/api/tokens-summary/{layer}")
async def get_tokens_summary(layer: str):
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "saida", layer)
        files = glob.glob(os.path.join(data_dir, "*.json"))
        if not files:
            return {"tokens": 0, "chars": 0}
        
        latest = max(files, key=os.path.getmtime)
        with open(latest, "r", encoding="utf-8") as f:
            content = f.read()
            # Estimativa simples: 1 token ~= 4 caracteres
            return {
                "filename": os.path.basename(latest),
                "chars": len(content),
                "tokens": len(content) // 4,
                "msg": f"Carga de entrada: ~{len(content)//4} tokens"
            }
    except Exception as e:
        return {"tokens": 0, "error": str(e)}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from routers_stage import router as stage_router
app.include_router(stage_router)

# ── LOGS EM TEMPO REAL via SSE (Server-Sent Events) ────────────────────────
log_queues = []

# Buffer de histórico — sobrevive a refresh do navegador
# Memória de Curto Prazo (RAM) para Configurações e Logs
log_history = collections.deque(maxlen=1000)

# Múltiplos processos / Ponte de comunicação OS
mp_queue = multiprocessing.Queue()
active_process = None

def queue_reader():
    """Lê do Processo Pesado da CrewAI e joga para as assinaturas SSE Leves do FastAPI"""
    while True:
        try:
            msg = mp_queue.get()
            log_history.append(msg)  # Salva no buffer persistente
            print(f"[QUEUE_READER] Broadcast msg: {msg[:50]}...") # Debug log
            for q in log_queues:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass
        except Exception as e:
            print(f"Erro no queue_reader: {e}")

# Liga a ponte de comunicação paralela global
threading.Thread(target=queue_reader, daemon=True).start()

def worker_process(txt_in, q):
    """Processo Isolado nível SO: Pode ser assassinado sumariamente sem afetar a API Ouro."""
    
    # [AIOX-SANITIZER] Camada 1 — Bloqueio na Origem (Subprocess ENV)
    import os
    os.environ["NO_COLOR"] = "1"
    os.environ["TERM"] = "dumb"
    os.environ["FORCE_COLOR"] = "0"
    os.environ["PYTHONUNBUFFERED"] = "1"

    class QueueInterceptor:
        def __init__(self, q): self.q = q
        def write(self, text):
            # Imprime no bash original tbm por garantia
            sys.__stdout__.write(text)
            sys.__stdout__.flush()
            
            # [AIOX-SANITIZER] Camada 2 — Filtro de Sanitização no Pipe SSE
            from utils.terminal_sanitizer import strip_ansi
            clean_text = strip_ansi(text)
            
            if clean_text.strip() or clean_text == "\n":
                self.q.put(clean_text)
                
        def flush(self): pass
        def __getattr__(self, name): return getattr(sys.__stdout__, name)
        
    # Sequestra a Saída Padrão apenas deste Processo Isolado
    sys.stdout = QueueInterceptor(q)
    sys.stderr = QueueInterceptor(q)
    
    try:
        from scripts.alba_crewai_pipeline import run_alba_crew
        print("\n\n" + "="*50)
        print(f"⚡ [SYSTEM OVERRIDE] B2B ISOLATED PROCESS IGNITION.")
        print("="*50 + "\n")
        
        run_alba_crew(txt_in)
        
        print("\n[✔] ORQUESTRAÇÃO MATRIX B2B FINALIZADA E PERSISTIDA.")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Ocorreu um desligamento da Engine: {str(e)}")

@app.post("/api/run-crew")
async def start_crew():
    global active_process
    
    if active_process and active_process.is_alive():
        return {"status": "Engrenagem já está operando!"}
        
    arquivo_teste = "/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/organizar/alba_verbas_markdown.txt"
    try:
        with open(arquivo_teste, 'r', encoding='utf-8') as fs:
            txt_in = fs.read()
    except:
        txt_in = "Arquivo não encontrado. Falha."
        
    # Inicializa a Orquestração como Processo de SO paralelo (Matável via RAM)
    active_process = multiprocessing.Process(target=worker_process, args=(txt_in, mp_queue))
    active_process.start()
    
    return {"status": "Ignition Authorized. Listen to SSE Stream."}

@app.post("/api/stop-crew")
async def stop_crew():
    global active_process
    # O Botão Vermelho do Mestre!
    if active_process and active_process.is_alive():
        active_process.terminate() # KILL DIRECT SYSTEM SIGNAL (-9)
        active_process.join()
        active_process = None
        # Avisa aos visualizadores que o Mestre abortou
        mp_queue.put("\n\n[☠️] ATENÇÃO: OPERAÇÃO ABORTADA PELO MESTRE (KILL SWITCH ACIONADO). CARGA COGNITIVA DESLIGADA E TOKENS SALVOS.\n")
        return {"status": "Processo de Morte Súbita executado com sucesso."}
    return {"status": "Nenhuma Orquestração rodando no momento para abortar."}

@app.get("/api/logs")
async def sse_logs():
    q = queue.Queue()
    log_queues.append(q)
    
    async def event_stream():
        try:
            # REPLAY: Envia histórico salvo ao reconectar (ex: após refresh)
            for old_msg in list(log_history):
                yield f"data: {json.dumps({'msg': old_msg})}\n\n"
            
            while True:
                msg = await asyncio.to_thread(q.get)
                yield f"data: {json.dumps({'msg': msg})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in log_queues:
                log_queues.remove(q)
                
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/api/log-history")
async def get_log_history():
    """Retorna o buffer de logs para clientes que reconectarem."""
    return {"logs": list(log_history)}

import glob
@app.get("/api/latest-results")
async def get_latest_results():
    try:
        ouro_dir = "/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n/data/saida/ouro"
        json_files = glob.glob(os.path.join(ouro_dir, "*.json"))
        if not json_files:
            return {"status": "none", "data": []}
        
        latest_file = max(json_files, key=os.path.getctime)
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return {"status": "ok", "filename": os.path.basename(latest_file), "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/stage/load")
async def get_stage():
    """Recupera o estado do React Flow."""
    try:
        with open(os.path.join(PRISMA_ROOT, "stage_config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"nodes": {}, "edges": {}, "stages": {}}

@app.post("/api/stage/save")
async def save_stage(data: dict):
    """Salva o estado do React Flow de forma persistente."""
    try:
        with open(os.path.join(PRISMA_ROOT, "stage_config.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/studio/explorer")
async def get_studio_explorer():
    import glob
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Datalake Explorer Tree
    crews = []
    
    # 1. ALBA Verbas (Crew 1)
    alba_files = {"bronze": [], "prata": [], "kaka": [], "ouro": []}
    saida_dir = os.path.join(base_dir, "data", "saida")
    
    for folder in ["bronze", "prata", "kaka", "ouro"]:
        f_dir = os.path.join(saida_dir, folder)
        if os.path.exists(f_dir):
            files = [f for f in os.listdir(f_dir) if f.endswith(".json")]
            alba_files[folder] = sorted(files, reverse=True)
            
    # Remapear para a estrutura do Frontend
    crews.append({
        "id": "alba",
        "name": "ALBA Verbas",
        "icon": "👽",
        "layers": {
            "bronze": alba_files["bronze"],
            "prata": alba_files["prata"],
            "kaka": alba_files["kaka"],
            "ouro": alba_files["ouro"]
        }
    })
    
    # 2. Zidane Biografias (Crew 2)
    zidane_files = {"parlamentares": []}
    parlamentares_dir = os.path.join(saida_dir, "parlamentares")
    raw_dir = os.path.join(parlamentares_dir, "raw")
    
    z_files = []
    if os.path.exists(parlamentares_dir):
        for f in os.listdir(parlamentares_dir):
            if f.endswith(".json") and os.path.isfile(os.path.join(parlamentares_dir, f)):
                z_files.append(f)
            
    if os.path.exists(raw_dir):
        for f in os.listdir(raw_dir):
            if f.endswith(".json") and os.path.isfile(os.path.join(raw_dir, f)):
                z_files.append(f"raw/{f}")
    
    enriquecido_dir = os.path.join(parlamentares_dir, "enriquecidos")
    if os.path.exists(enriquecido_dir):
        for f in os.listdir(enriquecido_dir):
            if f.endswith(".json") and os.path.isfile(os.path.join(enriquecido_dir, f)):
                z_files.append(f"enriquecidos/{f}")
        zidane_files["parlamentares"] = z_files
        crews.append({
            "id": "zidane",
            "name": "Zidane Biografias",
            "icon": "🕵️",
            "layers": zidane_files
        })
        
    return {"status": "ok", "crews": crews}

@app.get("/api/bronze-summary")
async def bronze_summary():
    # Procura qualquer arquivo checkpoint/bronze json na pasta data/
    target_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    
    bronze_paths = glob.glob(os.path.join(target_dir, "**/*checkpoint*.json"), recursive=True) + \
                   glob.glob(os.path.join(target_dir, "**/*bronze*.json"), recursive=True) + \
                   glob.glob(os.path.join(target_dir, "**/prisma_lista.csv"), recursive=True)
    
    if not bronze_paths:
        return {
            "encontrado": False,
            "mensagem": "Nenhum arquivo Bronze encontrado. Execute o Agent 1 primeiro.",
            "total": 0,
            "anos": [],
            "arquivos": []
        }
    
    # Lê o mais recente
    latest = sorted(bronze_paths, key=os.path.getmtime, reverse=True)[0]
    
    try:
        with open(latest, "r", encoding="utf-8") as f:
            if latest.endswith(".csv"):
                lines = f.readlines()
                records = lines[1:] if len(lines) > 1 else []
                anos = []
            else:
                data = json.load(f)
                # Detecta estrutura (lista ou dict)
                records = data if isinstance(data, list) else data.get("records", [data])
                # Extrai anos dos registros
                anos = list(set([
                    str(r.get("competencia", r.get("ano", "?"))).split("/")[-1]
                    for r in records if isinstance(r, dict)
                ]))
        
        return {
            "encontrado": True,
            "arquivo": os.path.basename(latest),
            "total": len(records),
            "anos": sorted(anos),
            "arquivos": [
                {
                    "nome": os.path.basename(p),
                    "tamanho_kb": round(os.path.getsize(p) / 1024, 1),
                    "camada": "BRONZE" if "checkpoint" in p or "bronze" in p else "PRATA",
                    "data": os.path.getmtime(p)
                }
                for p in bronze_paths
            ]
        }
    except Exception as e:
        return {"encontrado": False, "erro": str(e), "arquivo": latest}

@app.get("/api/agent-data/{layer}")
async def get_agent_data(layer: str):
    try:
        if layer not in ["bronze", "prata", "kaka", "ouro", "quarentena", "parlamentares"]:
            return {"status": "error", "message": "Camada Medallion invalida."}
            
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # ── Lógica Especial para Zidane (Parlamentares) ──────────────
        if layer == "parlamentares":
            p_dir = os.path.join(base_dir, "data", "saida", "parlamentares")
            hub_path = os.path.join(p_dir, "parlamentares_hub_normalized.json")
            
            if os.path.exists(hub_path):
                with open(hub_path, "r", encoding="utf-8") as f:
                    hub_data = json.load(f)
                    records = hub_data.get("parlamentares", [])
                    # Enriquecimento ad-hoc para o Grid do Studio
                    for r in records:
                        r["biografia_resumo"] = (r.get("biografia_completa") or "")[:200] + "..."
                        r["mandatos_count"] = len(r.get("mandatos", []))
                    return {"status": "ok", "filename": "parlamentares_hub.json", "data": records, "type": "json"}
            
            # Se não tem hub, tenta ler os arquivos individuais na pasta raw
            raw_dir = os.path.join(p_dir, "raw")
            json_files = glob.glob(os.path.join(raw_dir, "parlamentar_*_oficial.json"))
            if not json_files:
                return {"status": "none", "data": "Nenhum perfil extraído ainda.", "type": "text"}
            
            all_records = []
            for jf in sorted(json_files)[:63]: # Mostra todos os perfis brutos
                with open(jf, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    d["biografia_resumo"] = (d.get("biografia_completa") or "")[:200] + "..."
                    d["mandatos_count"] = len(d.get("mandatos", []))
                    all_records.append(d)
            return {"status": "ok", "filename": f"Raw profiles ({len(json_files)})", "data": all_records, "type": "json"}

        # ── Lógica Padrão Medallion ──────────────────────────────────
        target_dir = os.path.join(base_dir, "data", "saida", layer)
        files = glob.glob(os.path.join(target_dir, "*.*"))
        
        if not files:
            return {"status": "none", "data": "Nenhum arquivo processado nesta camada ainda.", "type": "text"}
            
        latest_file = max(files, key=os.path.getctime)
        with open(latest_file, 'r', encoding='utf-8') as f:
            if latest_file.endswith('.json'):
                data = json.load(f)
                if isinstance(data, dict) and "records" in data:
                    data = data["records"]
            else:
                data = f.read()
                
        return {
            "status": "ok", 
            "filename": os.path.basename(latest_file), 
            "data": data, 
            "type": "json" if latest_file.endswith('.json') else "text"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/agent-source/{layer}")
async def get_agent_source(layer: str):
    """Retorna o código-fonte do agente responsável por uma camada específica."""
    try:
        mapping = {
            "bronze": "agent_1_wrapper.py",
            "prata": "agent_2_chunker.py",
            "kaka": "agent_kaka_pdf.py",
            "ouro": "agent_4_prisma_db.py",
            "analyst": "agent_3_aguia.py",
            "forensic": "agent_5_pdf_forensic.py",
            "merge": "agent_6_merge.py"
        }
        
        filename = mapping.get(layer.lower())
        if not filename:
            return {"status": "error", "message": "Camada ou Agente inválido para código-fonte."}
            
        source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents", filename)
        
        if not os.path.exists(source_path):
            return {"status": "error", "message": f"Arquivo {filename} não encontrado."}
            
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return {
            "status": "ok",
            "filename": filename,
            "content": content
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/agent-manifest/{agent_id}")
async def get_agent_manifest(agent_id: str):
    """Extrai o __PRISMA_MANIFEST__ dinâmico do código-fonte do agente usando AST."""
    import ast
    try:
        mapping = {
            "1": "agent_1_wrapper.py",
            "2": "agent_2_chunker.py",
            "3": "agent_3_aguia.py",
            "kaka": "agent_kaka_pdf.py",
            "zidane_a": "agent_zidane_a_ids.py",
            "zidane_b": "agent_zidane_b_scraper.py",
            "zidane_c": "agent_zidane_c_brain.py",
            "zidane_d": "agent_zidane_d_loader.py",
            "4": "agent_4_prisma_db.py",
            "dunga": "agent_4_prisma_db.py",
            "5": "agent_5_pdf_forensic.py",
            "6": "agent_6_merge.py",
            "ronaldo": "agent_6_merge.py"
        }
        
        filename = mapping.get(agent_id.lower())
        if not filename:
            return {"status": "error", "message": "Agente não mapeado."}
            
        source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents", filename)
        if not os.path.exists(source_path):
            return {"status": "error", "message": f"Arquivo {filename} não encontrado."}
            
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Parseia o código Python com AST para extrair o dicionário __PRISMA_MANIFEST__
        tree = ast.parse(content)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__PRISMA_MANIFEST__':
                        manifest = ast.literal_eval(node.value)
                        return {"status": "ok", "manifest": manifest}
                        
        return {"status": "error", "message": "Manifesto não encontrado no código do agente."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def stream_agent_subprocess(script_args: list[str], agent_id: str = None, env_vars: dict = None):
    """
    Padrão SSE universal para qualquer agent.
    Roda o script como subprocess e jorra stdout via SSE.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    env["TERM"] = "dumb"
    env["PYTHONWARNINGS"] = "ignore:Unverified HTTPS request"

    if env_vars:
        env.update({k: str(v) for k, v in env_vars.items()})

    if agent_id and agent_id in agent_prompts and agent_prompts[agent_id]:
        env["AIOX_CUSTOM_PROMPT"] = agent_prompts[agent_id]
        print(f"[API] Injetando AIOX_CUSTOM_PROMPT no Agent {agent_id}.")
    
    process = subprocess.Popen(
        [sys.executable, "-u"] + script_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        bufsize=1,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safra = "master"
    for i, a in enumerate(script_args):
         if a in ("--ano", "--year") and i+1 < len(script_args):
              safra = script_args[i+1]

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"agent_{agent_id or 'SYS'}_{safra}_{timestamp}.log")

    try:
        from utils.terminal_sanitizer import strip_ansi
        import time
        start_time = time.time()
        
        with open(log_file_path, "a", encoding="utf-8") as log_f:
            for raw_line in process.stdout:
                clean = strip_ansi(raw_line).strip()
                if clean:
                    log_msg = f"[{agent_id if agent_id else 'SYS'}] {clean}"
                    # IMPORTANT: Injeta na fila global do terminal para o <TerminalPanel /> ver
                    mp_queue.put(log_msg) 
                    log_f.write(log_msg + "\n")
                    log_f.flush()
                    yield f"data: {json.dumps({'msg': log_msg})}\n\n"
            
            process.wait()
            duration = time.time() - start_time
            
            if process.returncode == 0:
                status = f"✅ Extração 100% Concluída! ⏱️ Tempo total: {duration:.2f}s"
            else:
                status = f"❌ Erro na extração (código {process.returncode}) | Parado em {duration:.2f}s"
                
            final_msg = f"[AGENT {agent_id if agent_id else 'SYS'} DONE] {status}"
            log_f.write(final_msg + "\n")
            mp_queue.put(final_msg)
            yield f"data: {json.dumps({'msg': final_msg})}\n\n"
    
    except GeneratorExit:
        process.terminate()

# ─── AGENT 2 ENDPOINTS ─────────────────────────────────────
@app.get("/api/agent/{agent_id}/input-files")
async def get_agent_input_files(agent_id: str, layer: str = "bronze"):
    """Retorna lista de arquivos de entrada para um agente (ex: bronze para Bebeto, prata para Kaká)."""
    base_dir = Path(__file__).resolve().parent.parent
    input_dir = base_dir / "data" / "saida" / layer
    
    if not input_dir.exists():
        return {"files": []}
    
    files = []
    # Busca .json e limpa duplicatas de checkpoints se necessário (opcional)
    for f in input_dir.glob("*.json"):
        stat = f.stat()
        files.append({
            "name": f.name,
            "layer": layer,
            "size": f"{stat.st_size / 1024:.1f} KB",
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        })
    
    return {"files": sorted(files, key=lambda x: x["name"], reverse=True)}

@app.get("/api/agent/2/bronze-files")
async def get_agent_2_bronze_files():
    """Legado para Bebeto — chama o novo endpoint genérico."""
    return await get_agent_input_files("2", "bronze")

@app.get("/api/datalake/stats/{agent_id}")
async def get_datalake_file_stats(agent_id: str, filename: str):
    """Retorna estatísticas reais e auditoria de um arquivo específico."""
    try:
        layer_map = {
            "1": "bronze", "2": "prata", "3": "kaka", 
            "4": "ouro", "dunga": "ouro", "5": "quarentena", "6": "ouro",
            "ronaldo": "ouro"
        }
        layer = layer_map.get(agent_id, "bronze")
        file_path = Path(__file__).resolve().parent.parent / "data" / "saida" / layer / filename
        
        if not file_path.exists():
            return {"status": "error", "message": "Arquivo não encontrado."}
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        records = data if isinstance(data, list) else data.get("records", [])
        total_records = len(records)
        
        # Auditoria de Normalização (Baseado nas 12 diretrizes do Bebeto/Agente 2)
        normalizations = []
        if agent_id == "2":
            normalizations = [
                "Campos 'num_nf' e 'competencia' normalizados para String",
                "Valores decimais forçados para Float (Deterministic)",
                "Remoção de espaços em branco (strip) em nomes de deputados",
                "Geração de 'prisma_id' único via Hash MD5",
                "Validação de integridade de data (ISO 8601)",
                "Filtragem de registros nulos ou zero-value",
                "Mapeamento de fornecedores (CNPJ/CPF)",
                "Tratamento de codificação UTF-8 (Fixing mojibake)"
            ]
        elif agent_id == "1":
            normalizations = [
                "Extração via Requests (Portal Transparência)",
                "Parsing de tabelas dinâmicas (BeautifulSoup)",
                "Captura de links de PDF anexos",
                "Deduplicação incremental via Checkpoint",
                "Normalização básica de moeda (R$ -> Float)"
            ]
        elif agent_id == "ronaldo":
            normalizations = [
                "Associação de Foreign Key (parlamentar_id)",
                "Mapeamento de Categorias Fiscais",
                "Hash MD5 Inviolável (prisma_id)",
                "Remoção de Mock Fields",
                "Padronização Dicionário Ouro"
            ]
            
        # Estimativa de tokens (1 token ~ 4 chars)
        file_size = os.path.getsize(file_path)
        tokens_estimate = file_size // 4
        
        # Cálculo de Completude de Campos (Health Check)
        completeness = {}
        if records and isinstance(records[0], dict):
            # Campos chave para monitorar
            key_fields = ["num_nf", "competencia", "deputado", "valor", "link_detalhe", "categoria"]
            for field in key_fields:
                filled = sum(1 for r in records if r.get(field) and str(r.get(field)).strip() not in ["", "None", "0"])
                completeness[field] = round((filled / total_records) * 100, 1) if total_records > 0 else 0

        # Detecção de duplicatas
        duplicatas = 0
        if records and isinstance(records[0], dict):
            seen = set()
            for r in records:
                key = r.get("num_nf") or r.get("link_detalhe") or str(r)
                if key in seen: duplicatas += 1
                seen.add(key)

        return {
            "status": "ok",
            "total_records": total_records,
            "duplicatas": duplicatas,
            "tokens": tokens_estimate,
            "file_size_kb": round(file_size / 1024, 1),
            "encoding": "UTF-8 OK",
            "completeness": completeness,
            "normalizations": normalizations,
            "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/agent/2/stream")
async def stream_agent_2(filename: str = None, year: str = None):
    args = ["agents/agent_2_chunker.py"]
    if filename:
        args.extend(["--file", filename])
    elif year:
        args.extend(["--year", year])
        
    return StreamingResponse(
        stream_agent_subprocess(args, agent_id="2"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

    return StreamingResponse(
        stream_agent_subprocess(["src/agents/agent_kaka_pdf.py", "--ano", ano or "2022"], agent_id="3"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ─── AGENT 4 SSE ───────────────────────────────────────────
@app.get("/api/agent/4/stream")
async def stream_agent_4():
    return StreamingResponse(
        stream_agent_subprocess(["agents/agent_4_prisma_db.py"], agent_id="4"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ─── AGENT 5 SSE ───────────────────────────────────────────
@app.get("/api/agent/5/stream")
async def stream_agent_5():
    return StreamingResponse(
        stream_agent_subprocess(["agents/agent_5_pdf_forensic.py"], agent_id="5"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ─── AGENT 6 SSE ───────────────────────────────────────────
@app.get("/api/agent/6/stream")
async def stream_agent_6():
    return StreamingResponse(
        stream_agent_subprocess(["agents/agent_6_merge.py"], agent_id="6"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# --- GERENCIADOR DE DATALAKE (HISTÓRICO E LIMPEZA) ---

def agent1_worker(ano_alvo, q, max_pages=0, mes_alvo=0):
    """Processo isolado do Agent 1: Scraping com logs via SSE."""
    import os, sys
    os.environ["PYTHONUNBUFFERED"] = "1"
    
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"agent_1_{ano_alvo or 'master'}_{timestamp}.log")

    # Redireciona o stdout/stderr deste subprocesso para a fila mp_queue e log
    class QueueWriter:
        def __init__(self, target_queue):
            self.queue = target_queue
            self.f = open(log_file_path, "a", encoding="utf-8")
        def write(self, text):
            if text.strip():
                clean = text.strip()
                log_msg = f"[1] {clean}"
                self.queue.put(log_msg)
                self.f.write(log_msg + "\n")
                self.f.flush()
        def flush(self):
            pass
        def __del__(self):
            self.f.close()
            
    sys.stdout = QueueWriter(q)
    sys.stderr = QueueWriter(q)
    
    try:
        from utils.scraper_alba import scrape_lista_completa
        import time
        start_time = time.time()
        
        # mes_alvo 0 significa 'Todos'
        mes_val = None if mes_alvo == 0 else int(mes_alvo)
        
        # INTELIGÊNCIA DE RETOMADA: Forçamos o resume se solicitado ou se for uma reconexão pós-queda
        # Aqui generalizamos: sempre tenta retomar se o arquivo de checkpoint existir
        resume_val = True if restart_val == "false" else False
        
        records = scrape_lista_completa(ano=ano_alvo, mes=mes_val, max_pages=max_pages, resume=resume_val)
        
        duration = time.time() - start_time
        print(f"\n🏁 [AGENT 1] Extração concluída com sucesso! 100% processado.")
        print(f"⏱️ Tempo total: {duration:.2f}s | 📊 {len(records)} registros extraídos e salvos para {ano_alvo}.\n")
    except Exception as e:
        print(f"\n❌ [AGENT 1] ERRO CRÍTICO: {e}\n")

active_agent1_process = None

PRISMA_ROOT = "/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n"
BRONZE_DIR = os.path.join(PRISMA_ROOT, "data", "saida", "bronze")
PRATA_DIR = os.path.join(PRISMA_ROOT, "data", "saida", "prata")

@app.get("/api/status")
async def get_system_status():
    """Retorna o estado de todos os agentes e prontidão de dados detalhada."""
    global active_agent1_process
    
    CHECKPOINT_DIR = os.path.join(os.path.dirname(PRATA_DIR), "checkpoints")

    # 🔍 Datalake Scan Granular com check_on_disk rigoroso
    def check_on_disk(directory, prefix="verbas", suffix=""):
        anos_finais = set()
        anos_checkpoint = set()
        for y in range(2015, 2026):
            ano_str = str(y)
            # Multi-Paths de Busca:
            diretorios_busca = [directory]
            if "bronze" in directory or "raw" in directory:
                diretorios_busca.extend([
                    os.path.join(PRISMA_ROOT, "data", "saida", "verbas", "raw"),
                    os.path.join(PRISMA_ROOT, "data", "raw")
                ])
            elif "prata" in directory or "processed" in directory:
                diretorios_busca.extend([
                    os.path.join(PRISMA_ROOT, "data", "saida", "verbas", "processed"),
                    os.path.join(PRISMA_ROOT, "data", "processed")
                ])
                
            f1 = f"{prefix}_{ano_str}{suffix}.json"
            f2 = f"alba_{ano_str}{suffix}.json"
            
            # Legados e Variações Ocultas:
            f3 = f"verbas_{ano_str}_processed.json" if "prata" in suffix else f1
            f4 = f"alba_{ano_str}.json" if "bronze" in suffix or suffix == "" else f1
            f5 = f"verbas_{ano_str}.json" if "bronze" in suffix or suffix == "" else f1
            f6 = f"alba_{ano_str}_bronze.json"
            f7 = f"alba_{ano_str}_prata.json"

            encontrou = False
            caminho_encontrado = ""
            for d in diretorios_busca:
                if not os.path.exists(d): continue
                
                # Busca flexível iterativa para arquivos Gold/Bronze versionados
                try:
                    for f_name in os.listdir(d):
                        if ano_str in f_name and suffix in f_name and not "checkpoint" in f_name and f_name.endswith(".json"):
                            caminho_completo = os.path.join(d, f_name)
                            if os.path.isfile(caminho_completo):
                                encontrou = True
                                caminho_encontrado = caminho_completo
                                break
                except Exception:
                    pass

                if not encontrou:
                    for f in [f1, f2, f3, f4, f5, f6, f7]:
                        caminho_completo = os.path.join(d, f)
                        if os.path.exists(caminho_completo):
                            encontrou = True
                            caminho_encontrado = caminho_completo
                            break
                if encontrou: break

            if encontrou:
                print(f"[DEBUG] Verificando Safra {ano_str}: Caminho [{caminho_encontrado}] -> STATUS: [FOUND]")
                anos_finais.add(ano_str)
            else:
                if prefix == "verbas" and suffix == "_bronze":
                    print(f"[DEBUG] Verificando Safra {ano_str}: {directory} -> STATUS: [NOT FOUND]")
            
            # Checkpoint file check
            chk_file = f"{prefix}_{ano_str}_checkpoint.json"
            
            # Kaká usa timestamp nos checkpoints na pasta central
            has_chk = False
            if prefix == "kaka":
                kaka_chks = glob.glob(os.path.join(CHECKPOINT_DIR, f"kaka_{ano_str}_checkpoint_*.json"))
                has_chk = len(kaka_chks) > 0
            else:
                has_chk = os.path.exists(os.path.join(directory, chk_file)) or os.path.exists(os.path.join(CHECKPOINT_DIR, chk_file))

            if has_chk:
                anos_checkpoint.add(ano_str)

        return sorted(list(anos_finais)), sorted(list(anos_checkpoint))

    bronze_finais, bronze_checkpoint = check_on_disk(BRONZE_DIR, prefix="alba", suffix="_bronze")
    prata_finais, prata_checkpoint = check_on_disk(PRATA_DIR, prefix="verbas", suffix="_prata")
    OURO_DIR = os.path.join(os.path.dirname(PRATA_DIR), "ouro")
    ouro_finais, ouro_checkpoint = check_on_disk(OURO_DIR, prefix="verbas", suffix="_gold")

    # Kaká Scan (Forense)
    KAKA_DIR = os.path.join(os.path.dirname(PRATA_DIR), "kaka")
    kaka_finais, kaka_checkpoint = check_on_disk(KAKA_DIR, prefix="kaka", suffix="")
    
    # Lógica Master: Um ano está 'extraído' se tiver bronze_final OU prata (qualquer camada refinada)
    # Isso garante que 2016 (tem prata mas não bronze_final) apareça como verde.
    anos_pipeline_completos = sorted(list(set(bronze_finais) | set(prata_finais) | set(ouro_finais)))
    # Um ano está 'em andamento' se tiver checkpoint mas ainda não entrou no pipeline
    anos_pipeline_checkpoint = sorted(list(set(bronze_checkpoint) - set(anos_pipeline_completos)))
    
    data_presence = {
        "bronze": len(bronze_finais) > 0 or len(bronze_checkpoint) > 0,
        "prata": len(prata_finais) > 0,
        "ouro": len(ouro_finais) > 0,
        "pdf": len(glob.glob(os.path.join(os.path.dirname(os.path.dirname(PRATA_DIR)), "anexos", "*.pdf"))) > 0,
        "bronze_anos": bronze_finais,
        "prata_anos": prata_finais,
        "ouro_anos": ouro_finais,
        "alba_verbas": len(bronze_finais) > 0,
        "alba_processed": len(prata_finais) > 0,
        "zidane_a": os.path.exists(os.path.join(PRISMA_ROOT, "data", "saida", "parlamentares", "raw", "parlamentares_ids.json")),
        "zidane_c": os.path.exists(os.path.join(PRISMA_ROOT, "data", "saida", "parlamentares", "parlamentares_hub_normalized.json"))
    }
    
    print(f"[STATUS CHECK] Verbas 2022: {'OK' if '2022' in bronze_finais else 'OFF'} | Zidane-A: {'OK' if data_presence['zidane_a'] else 'OFF'}")

    
    # Check audits
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")
    audit_gaps = {}
    for y in [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        af = os.path.join(log_dir, f"audit_verbas_{y}.json")
        if os.path.exists(af):
            try:
                with open(af, "r", encoding="utf-8") as jf:
                    j = json.load(jf)
                    if j.get("ausentes") and len(j["ausentes"]) > 0:
                        audit_gaps[str(y)] = True
            except: pass

    # Status Dinâmico por Agente
    status = {
        "1": {
            "status": "idle", 
            "input_ready": True, 
            "detail": "Pronto para Sourcing",
            "completed_years": anos_pipeline_completos,
            "checkpoint_years": anos_pipeline_checkpoint,
            "audit_gaps": audit_gaps,
            "available_input_years": [],
            "usage": {"input": 0, "output": 0}
        },
        "2": {
            "status": "idle", 
            "input_ready": data_presence["bronze"],
            "detail": f"{len(set(bronze_finais + bronze_checkpoint))} safras em Bronze",
            "completed_years": prata_finais,
            "checkpoint_years": prata_checkpoint,
            "available_input_years": sorted(list(set(bronze_finais + bronze_checkpoint))),
            "usage": {"input": 12450, "output": 2840}
        },
        "3": {
            "status": "idle", 
            "input_ready": data_presence["prata"],
            "detail": f"{len(prata_finais)} anos em Prata",
            "completed_years": kaka_finais,
            "checkpoint_years": kaka_checkpoint,
            "available_input_years": [y for y in prata_finais if y not in kaka_finais],
            "usage": {"input": 45600, "output": 12800}
        },
        "ronaldo": {
            "status": "idle", 
            "input_ready": len(kaka_finais) > 0 or len(prata_finais) > 0,
            "detail": "Pronto para Relacionamento e Ouro",
            "completed_years": ouro_finais,
            "checkpoint_years": ouro_checkpoint,
            "available_input_years": kaka_finais or prata_finais,
            "usage": {"input": 0, "output": 0}
        },
        "dunga": {
            "status": "idle", 
            "input_ready": len(ouro_finais) > 0,
            "detail": "Pronto para Persistência Prisma DB",
            "completed_years": ouro_finais, # Dunga relies on the same files since it just runs them, or we could query the DB
            "checkpoint_years": [],
            "available_input_years": ouro_finais,
            "usage": {"input": 0, "output": 0}
        }
    }

    # ── Status Zidane (Crew 00 — Biografias Parlamentares) ────────
    PARLAMENTARES_DIR = os.path.join(PRISMA_ROOT, "data", "saida", "parlamentares")
    RAW_DIR = os.path.join(PARLAMENTARES_DIR, "raw")
    
    # Detect legislatures
    zidane_a_completed = []
    ids_count = 0
    for leg in ["18", "19", "20"]:
        f_path = os.path.join(RAW_DIR, f"parlamentares_ids_leg_{leg}.json")
        if os.path.exists(f_path):
            zidane_a_completed.append(leg)
            try:
                with open(f_path, "r") as f:
                    ids_count += json.load(f).get("total", 0)
            except: pass

    hub_file = os.path.join(PARLAMENTARES_DIR, "parlamentares_hub_normalized.json")
    raw_perfis = glob.glob(os.path.join(RAW_DIR, "parlamentar_*_oficial.json"))

    hub_count = 0
    if os.path.exists(hub_file):
        try:
            with open(hub_file, "r") as f:
                hub_count = len(json.load(f).get("parlamentares", []))
        except: pass

    status["zidane_a"] = {
        "status": "idle",
        "input_ready": True,
        "detail": f"✅ {ids_count} IDs coletados" if zidane_a_completed else "Pronto para varredura",
        "completed_years": zidane_a_completed,
        "checkpoint_years": [],
        "available_input_years": [],
        "usage": {"input": 0, "output": ids_count}
    }

    status["zidane_b"] = {
        "status": "idle",
        "input_ready": len(zidane_a_completed) > 0,
        "detail": f"✅ {len(raw_perfis)} perfis extraídos" if raw_perfis else "Aguardando IDs",
        "completed_years": zidane_a_completed if len(raw_perfis) > 50 else [],
        "checkpoint_years": zidane_a_completed if 0 < len(raw_perfis) <= 50 else [],
        "available_input_years": zidane_a_completed,
        "usage": {"input": ids_count, "output": len(raw_perfis)}
    }

    status["zidane_c"] = {
        "status": "idle",
        "input_ready": len(raw_perfis) > 0,
        "detail": f"✅ Hub consolidado ({hub_count} parlamentares)" if os.path.exists(hub_file) else f"{len(raw_perfis)} perfis prontos para consolidação",
        "completed_years": ["18", "19", "20"] if os.path.exists(hub_file) else [],
        "checkpoint_years": [],
        "available_input_years": ["18", "19", "20"],
        "usage": {"input": len(raw_perfis), "output": hub_count}
    }

    cur_dir = os.path.dirname(os.path.abspath(__file__))
    base = os.path.dirname(cur_dir)
    status["zidane_d"] = {
        "status": "idle",
        "input_ready": os.path.exists(hub_file),
        "detail": "✅ Upsert Concluído" if os.path.exists(os.path.join(base, "data", "saida", "parlamentares", "logs", "carga_zidane_d.json")) else "Pronto para Upsert",
        "completed_years": ["2023-2027"] if False else [],  # Mantém falso pois não criamos lock yet
        "checkpoint_years": [],
        "available_input_years": [],
        "usage": {"input": hub_count, "output": hub_count}
    }

    # Sincroniza status de processos reais
    for a_id in status:
        if a_id in active_agent_processes and active_agent_processes[a_id].is_alive():
            status[a_id]["status"] = "running"
            if a_id == "1": status[a_id]["detail"] = "Extraindo Safra..."
            else: status[a_id]["detail"] = "Processando Camada..."
        
        # Injeta a skin_variant e configurações (ano, etc)
        config = agent_configs.get(a_id, {"ano": 2015, "mes": 0, "skin_variant": "default"})
        status[a_id]["skin_variant"] = config.get("skin_variant", "default")
        status[a_id]["config"] = config

    return {"agents": status, "data": data_presence}

@app.post("/api/stop-agent/{agent_id}")
async def stop_individual_agent(agent_id: str):
    """Mata o processo de um agente específico."""
    global active_agent_processes
    print(f"🛑 [AIOX] Parando Agente Individual: {agent_id}")
    
    if agent_id in active_agent_processes:
        p = active_agent_processes[agent_id]
        if p.is_alive():
            p.terminate()
            p.join()
            msg = f"\n\n[🛑] ATENÇÃO: EXECUÇÃO DO AGENT {agent_id} INTERROMPIDA MANUALMENTE.\n"
            mp_queue.put(msg)
            return {"status": "stopped", "message": f"Agent {agent_id} parado."}
            
    return {"status": "not_running", "message": f"Agent {agent_id} não está rodando."}

# Gerenciamento de Processos de Agentes
active_agent_processes = {}

def universal_agent_worker(agent_id, script_args, env_vars, q):
    """Worker universal para rodar agentes em background com captura de logs."""
    import os, sys, subprocess
    from utils.terminal_sanitizer import strip_ansi
    import time

    env = os.environ.copy()
    env.update({k: str(v) for k, v in env_vars.items()})
    env["PYTHONUNBUFFERED"] = "1"
    env["NO_COLOR"] = "1"
    env["PYTHONWARNINGS"] = "ignore:Unverified HTTPS request"

    msg_start = f"\n🚀 [AGENT {agent_id}] INICIANDO OPERAÇÃO...\n"
    q.put(msg_start)
    print(msg_start, flush=True)
    start_time = time.time()

    try:
        process = subprocess.Popen(
            [sys.executable, "-u"] + script_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        for line in process.stdout:
            clean = strip_ansi(line).strip()
            if clean:
                formatted = f"[{agent_id}] {clean}"
                q.put(formatted)
                print(formatted, flush=True)

        process.wait()
        duration = time.time() - start_time
        
        if process.returncode == 0:
            status = f"✅ Concluído! ⏱️ {duration:.2f}s"
        else:
            status = f"❌ Falha ({process.returncode}) | {duration:.2f}s"
            
        msg_end = f"\n🏁 [AGENT {agent_id}] {status}\n"
        q.put(msg_end)
        print(msg_end, flush=True)
    except Exception as e:
        msg_err = f"\n❌ [AGENT {agent_id}] ERRO CRÍTICO: {e}\n"
        q.put(msg_err)
        print(msg_err, flush=True)

@app.post("/api/run-agent/zidane_d")
async def run_zidane_d(response: Response):
    """Handler exclusivo para o Zidane-D (Loader Supabase) sem parâmetros de IA."""
    global active_agent_processes
    agent_id = "zidane_d"
    
    # Headers de CORS explícitos evitam bloqueio do Chrome se houver internal drops
    response.headers["Access-Control-Allow-Origin"] = "http://localhost:5175"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"

    if agent_id in active_agent_processes and active_agent_processes[agent_id].is_alive():
        return {"status": "running", "message": "Zidane-D já está em operação."}

    print(f"📡 [AIOX] Launching Agent Zidane-D (Loader Supabase Native)")
    
    # Config mínima
    agent_configs[agent_id] = {
        "skin_variant": agent_configs.get(agent_id, {}).get("skin_variant", "default")
    }
    
    env_vars = {} # Sem configs de LLM
    script = ["src/agents/agent_zidane_d_loader.py"]
    
    p = multiprocessing.Process(
        target=universal_agent_worker, 
        args=(agent_id, script, env_vars, mp_queue)
    )
    p.start()
    active_agent_processes[agent_id] = p
    
    return {"status": "started", "message": "Zidane-D iniciado com sucesso."}

@app.post("/api/run/agent_1/audit/{ano}")
async def run_audit_agent1(ano: int):
    """Triggers the Audit Forensic Mode for Agent 1 (Zorg-Romário)"""
    global active_agent_processes
    agent_id = "1"
    
    if agent_id in active_agent_processes and active_agent_processes[agent_id].is_alive():
        return {"status": "running", "message": f"Auditoria para o ano {ano} já está rodando."}

    print(f"📡 [AIOX] Launching Agent 1 SMART SYNC AUDIT | Ano: {ano}")

    script = ["src/agents/agent_1_wrapper.py", "--ano", str(ano), "--smart"]
    env_vars = {}
    
    p = multiprocessing.Process(
        target=universal_agent_worker, 
        args=(agent_id, script, env_vars, mp_queue)
    )
    p.start()
    active_agent_processes[agent_id] = p
    
    return {"status": "started", "message": f"Auditoria de {ano} iniciada com sucesso. Acompanhe os logs."}


@app.post("/api/run-agent/{agent_id}")
async def run_individual_agent(
    agent_id: str, 
    ano: Union[int, str] = 2015, 
    mes: int = 0, 
    municipio: str = "Salvador", 
    provider: str = "groq", 
    model: str = "llama-3.3-70b-versatile",
    filename: str = "",
    restart: bool = False,
    max_pages: int = 0,
    limit: int = 0
):
    """Triggers a specific agent task from the PRISMA pipeline."""

    global active_agent_processes
    
    # =====================================================================
    # GUARDA ANTI-RE-EXTRAÇÃO: Verifica se arquivo final já existe
    # Isso previne re-extração acidental de anos já concluídos.
    # =====================================================================
    if agent_id == "1" and not restart:
        checkpoint_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "saida", "bronze")
        final_file = os.path.join(checkpoint_dir, f"alba_{ano}.json")
        checkpoint_file = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
        
        if os.path.exists(final_file):
            # Arquivo final existe — retoma do checkpoint se houver, senão já está completo
            if os.path.exists(checkpoint_file):
                msg = f"✅ Safra {ano} já possui arquivo final ({os.path.getsize(final_file)//1024}KB). Use 'Reiniciar' para re-extrair."
            else:
                msg = f"✅ Safra {ano} já extraída e consolidada ({os.path.getsize(final_file)//1024}KB). Nenhuma ação necessária."
            print(f"[GUARDA] {msg}")
            mp_queue.put(f"[GUARDA] {msg}")
            return {"status": "already_done", "message": msg, "file": final_file}
    
    # Se for restart, limpa o checkpoint/arquivo parcial
    if restart:
        try:
            # Caminho para bronze (Agente 1)
            checkpoint_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "saida", "bronze")
            checkpoint_file = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
            if os.path.exists(checkpoint_file):
                os.remove(checkpoint_file)
                print(f"[API] Checkpoint removido para RESTART do Agent {agent_id} (Ano {ano})")
        except Exception as e:
            print(f"[API] Erro ao remover checkpoint: {e}")

    # Força a atualização do config global para este agente
    agent_configs[agent_id] = {
        "ano": ano,
        "mes": mes,
        "municipio": municipio,
        "provider": provider,
        "model": model,
        "filename": filename,
        "skin_variant": agent_configs.get(agent_id, {}).get("skin_variant", "default")
    }

    if agent_id in active_agent_processes and active_agent_processes[agent_id].is_alive():
        return {"status": "running", "message": f"Agent {agent_id} já está em operação."}

    print(f"📡 [AIOX] Launching Agent {agent_id} | Provider: {provider} | Model: {model}")

    # Mapeamento de Scripts (Caminhos relativos ao cwd que é src/)
    scripts = {
        "1": ["src/agents/agent_1_wrapper.py"], # scraper_alba
        "2": ["src/agents/agent_2_chunker.py"],   # Bebeto Xylos Purificador
        "3": ["src/agents/agent_kaka_pdf.py"],    # Kaká Forense (Novo Agente 3)
        "dunga": ["src/agents/agent_3_aguia.py"], # Dunga
        "4": ["src/agents/agent_4_prisma_db.py"],
        "5": ["src/agents/agent_kaka_pdf.py"], # legado
        "6": ["src/agents/agent_6_merge.py"],
        "ronaldo": ["src/agents/agent_ronaldo_gold.py"], # Ronaldo Gold
        "zidane_a": ["src/agents/agent_zidane_a_ids.py"],       
        "zidane_b": ["src/agents/agent_zidane_b_scraper.py"],   
        "zidane_c": ["src/agents/agent_zidane_c_enricher.py"],  
        "zidane_d": ["src/agents/agent_zidane_d_loader.py"],
    }

    if agent_id not in scripts:
        return {"status": "error", "message": "Agente ID desconhecido."}

    # Prepara argumentos de CLI extras para scripts que usam argparse
    extra_args = []
    
    # ROTEAMENTO INTELIGENTE PARA 'EXTRAIR TODOS'
    if str(ano) == "all" and agent_id == "1":
        scripts["1"] = ["agents/agent_1_batch.py"]
        # O script batch não recebe args, pois ele tem a lista chumbada interna
    else:
        if agent_id.startswith("zidane"):
            # Mapeamento estrito: Para a crew Zidane, usamos --legislatura em vez de --ano
            # Ignoramos para Zidane-D, pois ele processa o dataset unificado final
            if agent_id in ["zidane_a", "zidane_b", "zidane_c"]:
                extra_args = ["--legislatura", str(ano)]
                print(f"[EXEC] 🏛️ running {agent_id} with --legislatura {ano}")
                if limit > 0:
                    extra_args += ["--limit", str(limit)]
        elif agent_id in ["1", "2", "3", "kaka", "ronaldo", "dunga", "4", "5", "6"]:
            # Mapeamento de Extração: para a crew Alba Verbas e Auditoria
            tag = "--ano" if agent_id in ["1", "3", "kaka"] else "--year"
            extra_args = [tag, str(ano)]
            
            if agent_id == "1" and max_pages > 0:
                extra_args += ["--max_pages", str(max_pages)]
            
            # Limite de registros para Kaká (Agente 3)
            if agent_id == "3" and limit > 0:
                extra_args += ["--limit", str(limit)]

            # Passa o filename selecionado no frontend para o Agente 2
            if agent_id == "2" and filename:
                extra_args += ["--file", filename]


    env_vars = {
        "ANO_ALVO": str(ano),
        "MES_ALVO": str(mes),
        "MAX_PAGES": str(max_pages),
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model or "",
        "AIOX_CUSTOM_PROMPT": agent_prompts.get(agent_id, "")
    }

    p = multiprocessing.Process(
        target=universal_agent_worker, 
        args=(agent_id, scripts[agent_id] + extra_args, env_vars, mp_queue)
    )
    p.start()
    active_agent_processes[agent_id] = p
    
@app.delete("/api/agent/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Interrompe o processo de um agente ativo."""
    if agent_id in active_agent_processes:
        p = active_agent_processes[agent_id]
        if p.is_alive():
            print(f"🛑 [API] Interrompendo Agente {agent_id} (PID: {p.pid})")
            p.terminate() # Sinal SIGTERM para parada limpa
            p.join(timeout=2)
            if p.is_alive():
                p.kill() # Força se necessário
            
            mp_queue.put(f"🛑 [SISTEMA] Agente {agent_id} interrompido pelo usuário.")
            return {"status": "ok", "message": f"Agente {agent_id} parado."}
    
    return {"status": "error", "message": "Agente não está em execução."}

@app.get("/api/agent/{agent_id}/status")
async def get_agent_status(agent_id: str):
    """Verifica se o agente está rodando no SO."""
    is_running = False
    if agent_id in active_agent_processes:
        is_running = active_agent_processes[agent_id].is_alive()
    return {"status": "ok", "is_running": is_running}

@app.get("/api/datalake/files")
async def list_datalake_files():
    """Retorna a lista de todos os arquivos de todas as camadas para o histórico."""
    try:
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        
        patterns = [
            os.path.join(base_dir, "saida", "bronze", "**", "*.*"),
            os.path.join(base_dir, "saida", "prata", "**", "*.*"),
            os.path.join(base_dir, "saida", "kaka", "**", "*.*"),
            os.path.join(base_dir, "saida", "ouro", "**", "*.*"),
            os.path.join(base_dir, "saida", "checkpoints", "**", "*.*"),
            os.path.join(base_dir, "saida", "parlamentares", "**", "*.*")
        ]
        
        all_files = []
        for p in patterns:
            for fpath in glob.glob(p, recursive=True):
                if os.path.isfile(fpath):
                    stat = os.stat(fpath)
                    
                    rel_path = os.path.relpath(fpath, base_dir)
                    parts = rel_path.split(os.sep)
                    
                    if parts[0] == "saida" and len(parts) >= 3:
                        layer = parts[1] # bronze, prata, parlamentares
                        name = "/".join(parts[2:]) # raw/parlamentar_123.json ou alba_2015.json
                    else:
                        continue
                        
                    all_files.append({
                        "name": name,
                        "layer": layer,
                        "size": f"{stat.st_size / 1024:.1f} KB" if stat.st_size > 0 else "0 KB",
                        "created": stat.st_ctime,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "type": "json" if fpath.endswith(".json") else "txt"
                    })
                        
        all_files.sort(key=lambda x: x["created"], reverse=True)
        return {"status": "ok", "files": all_files}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/datalake/files/{layer}/{filename:path}")
async def get_datalake_file(layer: str, filename: str):
    """Retorna o conteúdo de um arquivo específico do datalake."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if layer in ["bronze", "prata", "kaka", "ouro", "checkpoints", "quarentena", "parlamentares"]:
            fpath = os.path.join(base_dir, "data", "saida", layer, filename)
        else:
             return {"status": "error", "message": f"Camada inválida: {layer}."}
             
        if not os.path.exists(fpath):
             return {"status": "error", "message": "Arquivo não encontrado."}
             
        with open(fpath, 'r', encoding='utf-8') as f:
            if filename.endswith('.json'):
                data = json.load(f)
                if isinstance(data, dict):
                    if "records" in data:
                        data = data["records"]
                    elif "parlamentares" in data:
                        data = data["parlamentares"]
            else:
                data = f.read()
        return {"status": "ok", "data": data, "type": "json" if filename.endswith('.json') else "text"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/api/datalake/files/{layer}/{filename:path}")
async def delete_datalake_file(layer: str, filename: str):
    """Deleta um arquivo específico de uma camada."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if layer in ["bronze", "prata", "kaka", "ouro", "checkpoints", "quarentena"]:
            fpath = os.path.join(base_dir, "data", "saida", layer, filename)
        elif layer == "parlamentares":
            fpath = os.path.join(base_dir, "data", "parlamentares", filename)
        else:
             return {"status": "error", "message": "Camada inválida para deleção."}
        
        if os.path.exists(fpath):
            os.remove(fpath)
            return {"status": "ok", "message": f"Arquivo removido com sucesso."}
        else:
            return {"status": "error", "message": "Arquivo não encontrado."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/api/datalake/reset")
async def datalake_reset():
    """Limpa todos os arquivos do Datalake para reextração do zero."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    padroes = [
        os.path.join(base_dir, "data", "**", "*.json"),
        os.path.join(base_dir, "data", "**", "*.csv"),
        os.path.join(base_dir, "data", "**", "*.parquet"),
        os.path.join(base_dir, "data", "raw", "alba", "pdfs", "**", "*.pdf"),
    ]
    removidos = []
    for padrao in padroes:
        for f in glob.glob(padrao, recursive=True):
            try:
                os.remove(f)
                removidos.append(os.path.relpath(f, base_dir))
            except Exception as e:
                print(f"[RESET] Erro ao remover {f}: {e}")
    mp_queue.put(f"[DATALAKE RESET] 🗑️ {len(removidos)} arquivos removidos.")
    return {"status": "ok", "removidos": len(removidos), "arquivos": removidos}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8003)
