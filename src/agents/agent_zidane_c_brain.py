#!/usr/bin/env python3
"""
🧠 AGENT ZIDANE-C THE BRAIN v6.0 — BULK ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRATÉGIA: Processamento em Lote (Bulk Processing)
MOTOR:      gemini-1.5-pro
CHUNKING:   Lotes de 5 para vencer limites de RPM e Cotas de Request
"""

import os
import sys
import json
import glob
import re
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Normalizar dados em massa usando Inteligência Artificial (Lote de 5).",
        "especialidade": "Especialista em Transformação de Biografias Brutas em Inteligência Política via Gemini 1.5 Flash",
        "protocolo_tecnico": "Python + Gemini API (Bulk Processing)",
        "camada_dados": "Ouro (Inteligência Enriquecida)",
        "seguranca": "Batch Size = 5, Sleep = 15s para evitar HTTP 429 Quota Exceeded"
    },
    "diretrizes": [
        "1. Lê todos os JSONs da pasta raw gerados pelo Minerador (Zidane-B).",
        "2. Identifica registros já processados via Cache (parlamentares_hub_normalized.json).",
        "3. Pega blocos (lotes) de 5 biografias para processamento simultâneo via IA.",
        "4. Envia o bloco para o LLM pedindo estruturação estrita em esquema JSON (Pydantic style).",
        "5. Extrai formação, carreira política, lideranças, condecorações e gera tags estratégicas.",
        "6. Faz sleep de 15 segundos entre lotes para respeitar Rate Limits do Google."
    ],
    "apuracao": {
        "safras_suportadas": ["Atual (Tempo Real)"],
        "saida_esperada": "data/saida/parlamentares/parlamentares_hub_normalized.json"
    }
}


# --- Estética ---
C_PURPLE = "\033[95m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_WHITE = "\033[97m"
C_END = "\033[0m"

# --- Configurações de Orquestração ---
# Usando gemini-2.0-flash-001 para ter acesso a uma nova cota diária de requisições.
MODEL_NAME = "gemini-flash-lite-latest"
BATCH_SIZE = 11        # Lote máximo para Paid Tier
SLEEP_BETWEEN_BATCHES = 2 # Alta velocidade (sem rate limit no Paid Tier)

SYSTEM_PROMPT = """Você é um Analista de Inteligência Política Sênior do sistema PRISMA.
Você receberá biografias parlamentares. Para CADA UMA, gere o objeto de inteligência no formato abaixo.

Retorne um ÚNICO JSON OBRIGATORIAMENTE neste formato exato:
{
  "respostas": [
    {
      "prisma_id": "...",
      "dados_premium": {
        "formacao_academica": [
          {"label": "Nome do Curso", "sub": "Instituição — Ano de Conclusão"}
        ],
        "carreira_politica": [
          {"label": "Cargo ou Mandato", "sub": "Partido — Período (ex: PP — 2019-2023)"}
        ],
        "lideranca_e_comissoes": [
          {"label": "Cargo na Mesa ou Comissão", "sub": "Órgão — Período"}
        ],
        "condecoracoes": ["Medalha X (Órgão, Ano)"],
        "tags_estrategicas": ["Tag1", "Tag2", "Tag3", "Tag4", "Tag5"],
        "biografia_resumo": "Resumo de 2-3 linhas focado em poder, alianças e trajetória política."
      }
    }
  ]
}

REGRAS OBRIGATÓRIAS:
1. "formacao_academica": Cada item DEVE ter {"label": "...", "sub": "..."}. label = nome do curso, sub = instituição + ano.
2. "carreira_politica": Cada item DEVE ter {"label": "...", "sub": "..."}. label = cargo, sub = partido + período.
3. "lideranca_e_comissoes": Cada item DEVE ter {"label": "...", "sub": "..."}. label = cargo, sub = órgão + período.
4. "condecoracoes": Lista de strings simples.
5. "tags_estrategicas": EXATAMENTE 5 tags curtas de perfil político (ex: "Agronegócio", "Base do Governo").
6. "biografia_resumo": Texto puro, 2-3 linhas, focado em poder e alianças. NÃO copie a bio bruta.
7. Não use marcação markdown (```json). Retorne APENAS o JSON puro.
"""

def init_brain():
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(f"{C_RED}❌ ERRO: GEMINI_API_KEY não encontrada.{C_END}")
        sys.exit(1)
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=SYSTEM_PROMPT)

def normalizar_basico(data: dict) -> dict:
    dp = data.get("dados_pessoais", {})
    nasc_raw = dp.get("Nascimento", "")
    data["data_nascimento"] = None
    data["municipio_nascimento"] = None
    data["uf_nascimento"] = None
    
    if nasc_raw:
        match = re.search(r'(\d{2}/\d{2}/\d{4}),?\s*([\w\s]+)-([A-Z]{2})', nasc_raw)
        if match:
            d, m, y = match.group(1).split("/")
            data["data_nascimento"] = f"{y}-{m}-{d}"
            data["municipio_nascimento"] = match.group(2).strip()
            data["uf_nascimento"] = match.group(3).strip()

    data["nome_civil"] = dp.get("Nome") or data.get("nome_civil")
    data["profissao"] = dp.get("Profissão")
    data["sexo"] = dp.get("Sexo")
    return data

def processar_lote_bulk(model, lote_bruto: list, retries=3) -> list:
    if not lote_bruto: return []
    
    prompt_dinamico = "Analise os seguintes perfis:\n\n"
    for item in lote_bruto:
        prompt_dinamico += f"--- PRISMA_ID: {item['prisma_id']} | NOME: {item['nome_limpo']} ---\n"
        prompt_dinamico += f"BIOGRAFIA: {item.get('biografia_completa', '')}\n\n"
        
    for attempt in range(retries + 1):
        try:
            response = model.generate_content(
                prompt_dinamico,
                generation_config=genai.GenerationConfig(response_mime_type="application/json", temperature=0.1),
            )
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            parsed = json.loads(raw)
            if "respostas" in parsed:
                return parsed["respostas"]
            else:
                raise Exception("JSON sem a chave 'respostas'.")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                print(f" {C_YELLOW}[RATE LIMIT! Esperando 60s...]{C_END}", end="", flush=True)
                time.sleep(60)
            elif "404" in err_str:
                print(f" {C_RED}[ERRO DE MODELO! 404]{C_END} {err_str}", end="", flush=True)
                return []
            else:
                print(f" {C_YELLOW}[Erro de parsing! Tentando novamente...]{C_END}", end="", flush=True)
                time.sleep(5)
            
            if attempt == retries:
                print(f" {C_RED}❌ Falha Lote após {retries} tentativas: {err_str[:40]}...{C_END}")
                return []
    return []

def chunk_list(lista, n):
    for i in range(0, len(lista), n):
        yield lista[i:i + n]

def main():
    print(f"\n{C_PURPLE}╔════════════════════════════════════════════════════════════════════╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN}       ZIDANE-C THE BRAIN v6.0 | BULK ENGINE (LOTE DE 5)     {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚════════════════════════════════════════════════════════════════════╝{C_END}")
    
    brain = init_brain()
    base_dir = Path(__file__).resolve().parent.parent.parent
    raw_dir = base_dir / "data" / "saida" / "parlamentares" / "raw"
    out_dir = base_dir / "data" / "saida" / "parlamentares"
    hub_file = out_dir / "parlamentares_hub_normalized.json"

    # --- Carregar Estado ---
    hub_data = {"parlamentares": []}
    if hub_file.exists():
        with open(hub_file, "r", encoding="utf-8") as f:
            hub_data = json.load(f)

    # Mapa rápido
    hub_map = {p.get("nome_limpo"): p for p in hub_data.get("parlamentares", [])}
    
    json_files = sorted(glob.glob(str(raw_dir / "parlamentar_*_oficial.json")))
    
    # Processa os JSONs brutos da pasta
    todos_dados = []
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            data = normalizar_basico(data)
            # Verifica se já está ouro
            nome = data.get("nome_limpo", "?")
            if nome in hub_map and hub_map[nome].get("tags_estrategicas") and len(hub_map[nome].get("tags_estrategicas", [])) > 0:
                continue # Já Processado
            
            # Assegura id caso falte
            if not data.get("prisma_id"):
                data["prisma_id"] = Path(fp).stem.replace("parlamentar_", "").replace("_oficial", "")
            
            # O nome limpo deve ser consistente
            data["nome_limpo"] = nome
            todos_dados.append(data)

    print(f"📦 Total na Fila Pendente: {len(todos_dados)}")
    print(f"📥 Já Minerados OK: {C_GREEN}{len(json_files) - len(todos_dados)}{C_END}\n")

    if not todos_dados:
        print(f"{C_GREEN}✅ Tudo preenchido! O hub tem {len(hub_map)} parlamentares enriquecidos.{C_END}")
        return

    # CHUNKING
    lotes = list(chunk_list(todos_dados, BATCH_SIZE))
    total_lotes = len(lotes)
    
    print(f"🚀 Iniciando processo em {total_lotes} lotes de {BATCH_SIZE}...")
    
    for i, lote in enumerate(lotes):
        nomes_lote = [p['nome_limpo'] for p in lote]
        print(f"\n{C_CYAN}[LOTE {i+1:02d}/{total_lotes:02d}] 🔄 Enviando 5 perfis para o Cérebro...{C_END}")
        
        resultado_lote = processar_lote_bulk(brain, lote)
        
        if resultado_lote:
            print(f" {C_GREEN}✅ Processados: {', '.join(nomes_lote[:5])}{C_END}")
            for extraido in resultado_lote:
                pid = extraido.get("prisma_id")
                dados_premium = extraido.get("dados_premium", {})
                
                # Busca registro original no lote pelo prisma_id
                original = next((item for item in lote if item.get("prisma_id") == pid), None)
                
                if original:
                    original["tags_estrategicas"] = dados_premium.get("tags_estrategicas", [])
                    original["formacao_academica"] = dados_premium.get("formacao_academica", [])
                    original["carreira_politica"] = dados_premium.get("carreira_politica", [])
                    original["lideranca_e_comissoes"] = dados_premium.get("lideranca_e_comissoes", [])
                    original["condecoracoes"] = dados_premium.get("condecoracoes", [])
                    if dados_premium.get("biografia_resumo"):
                        original["biografia_resumo"] = dados_premium["biografia_resumo"]
                    original["versao_enricher"] = f"v6.0-{MODEL_NAME}"
                    
                    # Atualiza o mapa global
                    hub_map[original["nome_limpo"]] = original
                    
            print(f"          🏷️  Lote Salvo na Memória.")
            
            # SAVING PARCIAL
            hub_data["parlamentares"] = list(hub_map.values())
            hub_data["gerado_em"] = datetime.utcnow().isoformat() + "Z"
            with open(hub_file, "w", encoding="utf-8") as f:
                json.dump(hub_data, f, ensure_ascii=False, indent=2)
                
        else:
            print(f" {C_RED}❌ Lote ignorado após falhas múltiplas.{C_END}")
        
        if i < total_lotes - 1:
            print(f"   [COOLDOWN] ⏳ Aguardando {SLEEP_BETWEEN_BATCHES}s para a próxima leva...")
            time.sleep(SLEEP_BETWEEN_BATCHES)

    # FINAL SAVING
    hub_data["parlamentares"] = list(hub_map.values())
    hub_data["gerado_em"] = datetime.utcnow().isoformat() + "Z"
    with open(hub_file, "w", encoding="utf-8") as f:
        json.dump(hub_data, f, ensure_ascii=False, indent=2)

    print(f"\n{C_GREEN}✅ BULK ENGINE FINALIZADA! Arquivo Hub atualizado.{C_END}\n")

if __name__ == "__main__":
    main()
