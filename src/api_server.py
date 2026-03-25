import sys
import queue
import json
import asyncio
import os
import glob
import multiprocessing
import threading
import subprocess
from fastapi import FastAPI
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
    allow_methods=["*"],
    allow_headers=["*"]
)

# Filas de distribuição para os Navegadores conectados via SSE
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
        if layer not in ["bronze", "prata", "ouro", "quarentena"]:
            return {"status": "error", "message": "Camada Medallion inválida."}
            
        target_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "saida", layer)
        files = glob.glob(os.path.join(target_dir, "*.*"))
        
        if not files:
            return {"status": "none", "data": "Nenhum arquivo processado nesta camada ainda.", "type": "text"}
            
        latest_file = max(files, key=os.path.getctime)
        with open(latest_file, 'r', encoding='utf-8') as f:
            if latest_file.endswith('.json'):
                data = json.load(f)
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
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    
    try:
        from utils.terminal_sanitizer import strip_ansi
        import time
        start_time = time.time()
        
        for raw_line in process.stdout:
            clean = strip_ansi(raw_line).strip()
            if clean:
                # IMPORTANT: Injeta na fila global do terminal para o <TerminalPanel /> ver
                mp_queue.put(f"[{agent_id if agent_id else 'SYS'}] {clean}") 
                yield f"data: {json.dumps({'msg': clean})}\n\n"
        
        process.wait()
        duration = time.time() - start_time
        
        if process.returncode == 0:
            status = f"✅ Extração 100% Concluída! ⏱️ Tempo total: {duration:.2f}s"
        else:
            status = f"❌ Erro na extração (código {process.returncode}) | Parado em {duration:.2f}s"
            
        final_msg = f"[AGENT {agent_id if agent_id else 'SYS'} DONE] {status}"
        mp_queue.put(final_msg)
        yield f"data: {json.dumps({'msg': final_msg})}\n\n"
    
    except GeneratorExit:
        process.terminate()

# ─── AGENT 2 ENDPOINTS ─────────────────────────────────────
@app.get("/api/agent/{agent_id}/bronze-files")
async def get_agent_2_bronze_files():
    """Retorna lista de arquivos na pasta bronze para o seletor do Bebeto."""
    base_dir = Path(__file__).resolve().parent.parent
    bronze_dir = base_dir / "data" / "saida" / "bronze"
    
    if not bronze_dir.exists():
        return {"files": []}
    
    files = []
    for f in bronze_dir.glob("*.json"):
        stat = f.stat()
        files.append({
            "name": f.name,
            "size": f"{stat.st_size / 1024:.1f} KB",
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        })
    
    return {"files": sorted(files, key=lambda x: x["name"], reverse=True)}

@app.get("/api/datalake/stats/{agent_id}")
async def get_datalake_file_stats(agent_id: str, filename: str):
    """Retorna estatísticas reais e auditoria de um arquivo específico."""
    try:
        layer_map = {
            "1": "bronze", "2": "prata", "3": "ouro", 
            "4": "ouro", "5": "quarentena", "6": "ouro"
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

# ─── AGENT 3 SSE (LLM) ──────────────────────────────────────
@app.get("/api/agent/3/stream")
async def stream_agent_3(max_tokens: int = 2000, retries: int = 3, provider: str = "groq", model: str = None):
    env_vars = {
        "MAX_TOKENS": max_tokens,
        "MAX_RETRIES": retries,
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model or ""
    }
    return StreamingResponse(
        stream_agent_subprocess(["agents/agent_3_aguia.py"], agent_id="3", env_vars=env_vars),
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
    
    # Redireciona o stdout/stderr deste subprocesso para a fila mp_queue
    class QueueWriter:
        def __init__(self, target_queue):
            self.queue = target_queue
        def write(self, text):
            if text.strip():
                self.queue.put(text)
        def flush(self):
            pass
            
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

BRONZE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "saida", "bronze")
PRATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "saida", "prata")

@app.get("/api/status")
async def get_system_status():
    """Retorna o estado de todos os agentes e prontidão de dados detalhada."""
    global active_agent1_process
    
    # 🔍 Datalake Scan Granular
    def get_anos(directory, pattern="*.json"):
        import re
        files = glob.glob(os.path.join(directory, pattern))
        anos_finais = set()
        anos_checkpoint = set()
        for f in files:
            fname = os.path.basename(f)
            m = re.search(r"(20\d{2})", fname)
            if m:
                ano = m.group(1)
                if "checkpoint" in fname.lower():
                    anos_checkpoint.add(ano)
                else:
                    anos_finais.add(ano)
        return sorted(list(anos_finais)), sorted(list(anos_checkpoint))

    bronze_finais, bronze_checkpoint = get_anos(BRONZE_DIR)
    prata_finais, prata_checkpoint = get_anos(PRATA_DIR)
    ouro_finais, ouro_checkpoint = get_anos(os.path.join(os.path.dirname(PRATA_DIR), "ouro"))
    
    # Lógica Master: Um ano está 'extraído' se tiver bronze_final OU prata (qualquer camada refinada)
    # Isso garante que 2016 (tem prata mas não bronze_final) apareça como verde.
    anos_pipeline_completos = sorted(list(set(bronze_finais) | set(prata_finais)))
    # Um ano está 'em andamento' se tiver checkpoint mas ainda não entrou no pipeline
    anos_pipeline_checkpoint = sorted(list(set(bronze_checkpoint) - set(anos_pipeline_completos)))
    
    data_presence = {
        "bronze": len(bronze_finais) > 0 or len(bronze_checkpoint) > 0,
        "prata": len(prata_finais) > 0,
        "ouro": len(ouro_finais) > 0,
        "pdf": len(glob.glob(os.path.join(os.path.dirname(os.path.dirname(PRATA_DIR)), "anexos", "*.pdf"))) > 0,
        "bronze_anos": bronze_finais,
        "prata_anos": prata_finais,
        "ouro_anos": ouro_finais
    }

    # Status Dinâmico por Agente
    status = {
        "1": {
            "status": "idle", 
            "input_ready": True, 
            "detail": "Pronto para Sourcing",
            "completed_years": anos_pipeline_completos,
            "checkpoint_years": anos_pipeline_checkpoint,
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
            "detail": f"{len(prata_finais)} anos em Prata" if prata_finais else "Aguardando Refinamento",
            "completed_years": ouro_finais,
            "checkpoint_years": ouro_checkpoint,
            "available_input_years": [y for y in prata_finais if y not in ouro_finais],
            "usage": {"input": 45600, "output": 12800}
        },
        "4": {
            "status": "idle", 
            "input_ready": data_presence["prata"],
            "detail": "Pronto para Validação" if prata_finais else "Sem dados Prata",
            "completed_years": ouro_finais,
            "checkpoint_years": ouro_checkpoint,
            "available_input_years": prata_finais,
            "usage": {"input": 8900, "output": 450}
        },
        "5": {
            "status": "idle", 
            "input_ready": data_presence["pdf"],
            "detail": "Pronto para OCR" if data_presence["pdf"] else "Sem PDFs anexos",
            "completed_years": [],
            "checkpoint_years": [],
            "available_input_years": [],
            "usage": {"input": 0, "output": 0}
        },
        "6": {
            "status": "idle", 
            "input_ready": data_presence["ouro"],
            "detail": "Pronto para Consolidação" if ouro_finais else "Aguardando Ouro",
            "completed_years": ouro_finais,
            "checkpoint_years": ouro_checkpoint,
            "available_input_years": ouro_finais,
            "usage": {"input": 0, "output": 0}
        }
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
            cwd=os.path.dirname(os.path.abspath(__file__))
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
    max_pages: int = 0
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
        "1": ["agents/agent_1_wrapper.py"], # scraper_alba
        "kaka": ["agents/agent_kaka_pdf.py"], # arquivista forense
        "2": ["agents/agent_2_chunker.py"],   # Bebeto Xylos Purificador
        "3": ["agents/agent_3_aguia.py"],
        "4": ["agents/agent_4_prisma_db.py"],
        "5": ["agents/agent_5_pdf_forensic.py"],
        "6": ["agents/agent_6_merge.py"],
        "zidane_a": ["agents/agent_zidane_a_ids.py"],       # Zidane ID Collector
        "zidane_b": ["agents/agent_zidane_b_scraper.py"],   # Zidane Profile Scraper
        "zidane_c": ["agents/agent_zidane_c_enricher.py"],  # Zidane LLM Enricher
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
        if agent_id in ["1", "2", "kaka"]:
            extra_args = ["--ano", str(ano)] if agent_id in ["1", "kaka"] else ["--year", str(ano)]
            if agent_id == "1" and max_pages > 0:
                extra_args += ["--max_pages", str(max_pages)]
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
            os.path.join(base_dir, "saida", "gold", "**", "*.*"),
            os.path.join(base_dir, "saida", "checkpoints", "**", "*.*"),
            os.path.join(base_dir, "parlamentares", "**", "*.*")
        ]
        
        all_files = []
        for p in patterns:
            for fpath in glob.glob(p, recursive=True):
                if os.path.isfile(fpath):
                    stat = os.stat(fpath)
                    
                    rel_path = os.path.relpath(fpath, base_dir)
                    parts = rel_path.split(os.sep)
                    
                    if parts[0] == "saida" and len(parts) >= 3:
                        layer = parts[1] # bronze, prata, etc
                        name = "/".join(parts[2:]) # alba/alba_2015.json
                    elif parts[0] == "parlamentares":
                        # Compatibilidade Zidane original
                        layer = "parlamentares"
                        name = "/".join(parts[1:])
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
        
        if layer in ["bronze", "prata", "ouro", "checkpoints", "quarentena"]:
            fpath = os.path.join(base_dir, "data", "saida", layer, filename)
        elif layer == "parlamentares":
            fpath = os.path.join(base_dir, "data", "parlamentares", filename)
        else:
             return {"status": "error", "message": f"Camada inválida: {layer}."}
             
        if not os.path.exists(fpath):
             return {"status": "error", "message": "Arquivo não encontrado."}
             
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f) if filename.endswith('.json') else f.read()
        return {"status": "ok", "data": data, "type": "json" if filename.endswith('.json') else "text"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/api/datalake/files/{layer}/{filename:path}")
async def delete_datalake_file(layer: str, filename: str):
    """Deleta um arquivo específico de uma camada."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if layer in ["bronze", "prata", "ouro", "checkpoints", "quarentena"]:
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
    uvicorn.run("api_server:app", host="0.0.0.0", port=8001)
