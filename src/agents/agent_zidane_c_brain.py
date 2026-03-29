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

SIGLA_PARTIDO_NORMALIZER = {
    "UNIO": "UNIÃO",
    "UNIÃO BRASIL": "UNIÃO",
    "UNION": "UNIÃO",
    "DEMOCRATAS": "DEM",
    "PARTIDO DOS TRABALHADORES": "PT",
    "PARTIDO LIBERAL": "PL",
    "PROGRESSISTAS": "PP",
    "PARTIDO PROGRESSISTA": "PP",
    "PARTIDO PROGRESSISTA BRASILEIRO": "PPB",
}

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
        "safras_suportadas": ["17", "18", "19", "20 (Atual)"],
        "entrada_esperada": "data/saida/parlamentares/raw/parlamentar_{id}_oficial.json",
        "saida_esperada": "data/saida/parlamentares/enriquecidos/leg_{X}/parlamentar_{id}_enriquecido.json"
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
# Usando gemini-flash-lite-latest (novo equivalente ao 1.5-flash-lite)
MODEL_NAME = "gemini-flash-lite-latest"
BATCH_SIZE = 10        # Lote máximo para Paid Tier
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

def validar_dados_premium(original: dict, dados_premium: dict) -> tuple[dict, list, float]:
    """
    Confronta cada item gerado pelo LLM com a biografia original.
    Retorna (dados_validados, flags_lista, score_final).
    """
    bio = (original.get("biografia_completa") or "").lower()
    flags = []

    def item_confirmado(item: dict, campo: str) -> bool:
        """
        Verifica se pelo menos 2 palavras-chave do item existem na biografia.
        Palavras com menos de 4 chars são ignoradas (artigos, preposições).
        """
        texto = f"{item.get('label', '')} {item.get('sub', '')}".lower()
        palavras = [p for p in texto.split() if len(p) >= 4]
        if not palavras:
            return True  # sem palavras suficientes → não punir
        encontradas = sum(1 for p in palavras if p in bio)
        return encontradas >= 2  # pelo menos 2 palavras confirmadas

    # Validar carreira_politica
    carreira_original = dados_premium.get("carreira_politica", [])
    carreira_valida = []
    for i, item in enumerate(carreira_original):
        if item_confirmado(item, "carreira_politica"):
            carreira_valida.append(item)
        else:
            flags.append(f"carreira_politica[{i}]_nao_confirmado: {item.get('label')}")

    # Validar formacao_academica
    formacao_original = dados_premium.get("formacao_academica", [])
    formacao_valida = []
    for i, item in enumerate(formacao_original):
        if item_confirmado(item, "formacao_academica"):
            formacao_valida.append(item)
        else:
            flags.append(f"formacao_academica[{i}]_nao_confirmado: {item.get('label')}")

    # Validar lideranca_e_comissoes
    lideranca_original = dados_premium.get("lideranca_e_comissoes", [])
    lideranca_valida = []
    for i, item in enumerate(lideranca_original):
        if item_confirmado(item, "lideranca_e_comissoes"):
            lideranca_valida.append(item)
        else:
            flags.append(f"lideranca[{i}]_nao_confirmado: {item.get('label')}")

    # Normalizar sigla_partido no registro original
    sigla = original.get("sigla_partido", "")
    original["sigla_partido"] = SIGLA_PARTIDO_NORMALIZER.get(sigla.upper(), sigla)

    # Calcular qualidade_score final
    base_score = float(original.get("qualidade_score") or 1.0)
    desconto = len(flags) * 0.05
    score_final = round(max(0.5, base_score - desconto), 2)

    dados_validados = {
        **dados_premium,
        "carreira_politica": carreira_valida,
        "formacao_academica": formacao_valida,
        "lideranca_e_comissoes": lideranca_valida,
    }

    return dados_validados, flags, score_final

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
    enriquecido_dir = base_dir / "data" / "saida" / "parlamentares" / "enriquecidos"
    enriquecido_dir.mkdir(parents=True, exist_ok=True)
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
    
    # Carregar Mapeamento Global de Legislaturas por ID
    leg_map = {}
    for ids_f in glob.glob(str(raw_dir / "parlamentares_ids_leg_*.json")):
        m = re.search(r"leg_(\d+)\.json", ids_f)
        if m:
            lg = m.group(1)
            with open(ids_f, "r", encoding="utf-8") as f_ids:
                dados_ids = json.load(f_ids).get("records", [])
                for rec in dados_ids:
                    pid = rec.get("parlamentar_id")
                    if pid:
                        if pid not in leg_map: leg_map[pid] = []
                        if lg not in leg_map[pid]: leg_map[pid].append(lg)

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
                    dados_premium = extraido.get("dados_premium", {})
                    
                    # ← NOVO: validar antes de salvar
                    dados_validados, flags, score_final = validar_dados_premium(original, dados_premium)

                    original["carreira_politica"]      = dados_validados.get("carreira_politica", [])
                    original["formacao_academica"]     = dados_validados.get("formacao_academica", [])
                    original["lideranca_e_comissoes"]  = dados_validados.get("lideranca_e_comissoes", [])
                    original["condecoracoes"]          = dados_validados.get("condecoracoes", [])
                    original["tags_estrategicas"]      = dados_validados.get("tags_estrategicas", [])
                    original["biografia_resumo"]       = dados_validados.get("biografia_resumo", "")
                    original["versao_enricher"]        = f"v6.1-validated-{MODEL_NAME}"
                    original["qualidade_score"]        = score_final
                    original["flags_validacao"]        = flags  # ← novo campo para auditoria

                    if flags:
                        print(f"  ⚠️ {original['nome_limpo']}: {len(flags)} flag(s) → {flags}")

                    # Atualiza o mapa global
                    hub_map[original["nome_limpo"]] = original
                    
                    parl_id_api = original.get("parlamentar_id")
                    legislaturas_ativas = leg_map.get(parl_id_api, ["20"])
                    
                    # Salva o JSON enriquecido na pasta temporária isolada por safra
                    for leg in legislaturas_ativas:
                        leg_dir = enriquecido_dir / f"leg_{leg}"
                        leg_dir.mkdir(parents=True, exist_ok=True)
                        
                        copy_data = dict(original)
                        copy_data["legislatura_alvo"] = str(leg)
                        copy_data["historico_legislaturas"] = sorted([int(x) for x in legislaturas_ativas])
                        
                        out_path = leg_dir / f"parlamentar_{pid}_enriquecido.json"
                        with open(out_path, "w", encoding="utf-8") as f_out:
                            json.dump(copy_data, f_out, ensure_ascii=False, indent=2)
                    
            print(f"          🏷️  Lote Salvo na Memória e Arquivos Criados separados por Legislatura.")
            
            # SAVING PARCIAL
            hub_data["parlamentares"] = list(hub_map.values())
            hub_data["gerado_em"] = datetime.utcnow().isoformat() + "Z"
            with open(hub_file, "w", encoding="utf-8") as f:
                json.dump(hub_data, f, ensure_ascii=False, indent=2)
                
        else:
            print(f" {C_RED}❌ Lote ignorado após falhas múltiplas.{C_END}")
        

    print(f"\n{C_GREEN}✅ BULK ENGINE FINALIZADA! Arquivo Hub atualizado.{C_END}\n")

if __name__ == "__main__":
    main()
