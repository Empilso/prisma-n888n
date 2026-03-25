"""
@dev *aiox-agentic-extractor*
Crew: Orquestração Multi-Agente Oficial (CrewAI)
A evolução do Padrão Prisma. Agora, o fluxo é controlado por Agentes Autônomos Reais
com memória compartilhada e ferramentas injetáveis, usando o motor cognitivo da Groq limitando
alucinações via BaseModel/Pydantic Outputs.
"""

import os
import time
import json
import hashlib
import datetime
from textwrap import dedent

# Bibliotecas Core do CrewAI
from crewai import Agent, Task, Crew, Process
from pydantic import BaseModel, Field
from typing import List

# Setup do LLM Master (Llama 3.3-70b via LiteLLM nativo da CrewAI)
os.environ["GROQ_API_KEY"] = "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"
LLM_MODEL = "groq/llama-3.3-70b-versatile"

# =====================================================================
# CONFIGURAÇÃO DE DIRETÓRIOS (MEDALLION)
# =====================================================================
BASE_RIVER = "n888n/data/saida"
PATHS = {
    "bronze": os.path.join(BASE_RIVER, "bronze"),
    "prata": os.path.join(BASE_RIVER, "prata"),
    "ouro": os.path.join(BASE_RIVER, "ouro"), 
    "quarentena": os.path.join(BASE_RIVER, "quarentena")
}
for p in PATHS.values():
    os.makedirs(p, exist_ok=True)

def current_date_str(): return datetime.datetime.now().strftime("%Y%m%d")

# =====================================================================
# SCHEMA DE DADOS REQUERIDO (GUARDRAILS)
# =====================================================================
class DespesaAnalitica(BaseModel):
    id_origem: str = Field(description="Id/Nota Fiscal ou Processo")
    politico_nome: str = Field(description="Nome Parlamentar")
    fornecedor_cnpj: str = Field(description="CNPJ Limpo ou INVALIDO")
    valor_bruto: float = Field(description="Valor monetário formatado")
    categoria_origem: str = Field(description="Tipo de Despesa")
    data_emissao: str = Field(description="Data da despesa")
    link_documento: str = Field(description="URL link do pdf/html")
    ia_risco_nivel: str = Field(description="Avaliação de fraude (ALTO, MODERADO, BAIXO)")
    ia_comentario_revisor: str = Field(description="Veredito lógico do Revisor")

class PayloadCamadaOuro(BaseModel):
    extracao: List[DespesaAnalitica] = Field(description="O array final processado contendo os registros de despesa formatados pelo Revisor.")

# =====================================================================
# DEFINIÇÃO DOS AGENTES AUTÔNOMOS
# =====================================================================

agent_sourcing = Agent(
    role='Engenheiro de Sourcing de Dados Primitivo',
    goal='Extrair incondicionalmente a base de dados em formato de texto da ALBA e repassar aos especialistas.',
    backstory=dedent("""
    Você é a primeira linha da Orquestração. Um raspador de dados mestre.
    A você foi dada a tarefa de ingerir o arquivo HTML bruto ou TXT recebido do Sistema 
    Operacional e entregá-lo para os times de inteligência, sem tentar entendê-lo.
    Na fase atual, você vai ler o texto do arquivo bypass injetado.
    """),
    verbose=True,
    allow_delegation=False,
    llm=LLM_MODEL,
    max_iter=2,
    max_retry_limit=1
)

agent_organizer = Agent(
    role='Data Cleaner Sênior de Estrutura JSON',
    goal='Limpar erros de OCR / Digitação Severa, organizando o TXT bagunçado num JSON estrito Prisma Prata.',
    backstory=dedent("""
    Você é uma mente matemática focada em engenharia de dados. 
    Lê HTML rasgado e sabe inferir que "R$ 5OO" (letra O) na rubrica de Combustível 
    são 500 Reais exatos matematicos. Exige extrema ordem nas chaves "id_origem, politico_nome, etc"
    """),
    verbose=True,
    allow_delegation=False,
    llm=LLM_MODEL,
    max_iter=2,
    max_retry_limit=1
)

agent_compliance = Agent(
    role='Auditor-Chefe Federal Analítico (Compliance)',
    goal='Atuar nos Metadados sem abrir o PDF, identificando fraudes extremas pelo cruzamento Rubrica vs Valor.',
    backstory=dedent("""
    A burocracia humana foi extinta por você. 
    Se a Categoria for "Serviços Postais" e o Gasto for R$ 30.000 em uma nota só, 
    você levanta o risco ia_risco_nivel = ALTO. 
    Se a rubrica for ilegível, também levanta alerta ALTO. 
    Você escreve o laudo conciso no ia_comentario_revisor.
    """),
    verbose=True,
    allow_delegation=False,
    llm=LLM_MODEL,
    max_iter=2,
    max_retry_limit=1
)

agent_prisma_loader = Agent(
    role='Comandante Guardião do Data Lake Prisma',
    goal='Lacrar a esteira aplicando assinatura criptográfica MD5 em cada despesa da Camada Ouro para blindagem.',
    backstory=dedent("""
    A idoneidade e idempotência do banco de dados depende 100% de você. 
    O Agente Auditor gerou o laudo da nota. Sua função NÃO é revisar o laudo, 
    é apenas varrer a propriedade da nota, rodar um algorítmo MD5 e dar OK final 
    para inserir nos discos de alta performance.
    """),
    verbose=True,
    allow_delegation=False,
    llm=LLM_MODEL,
    max_iter=1,
    max_retry_limit=1
)

# =====================================================================
# TASKS E TRANSIÇÃO (WORKFLOW)
# =====================================================================

def run_alba_crew(payload_bypass_text: str):
    import time
    from langchain_groq import ChatGroq
    from utils.data_extractor import extract_table_only, count_tokens_estimate
    from utils.chunker import chunk_records
    from utils.model_router import get_available_model
    import json
    import os
    from textwrap import dedent
    from crewai import Task, Crew, Process
    import hashlib
    
    VERBOSE_MODE = os.getenv("AIOX_DEBUG", "false").lower() == "true"

    print("\n" + "="*80)
    print("🚀 INIT: AIOX CREW (ARQUITETURA 5 AGENTES HÍBRIDOS)")
    print("="*80)
    
    # =========================================================================
    # AGENTE 1: PYTHON NATIVO (Sourcing Raw HTML)
    # =========================================================================
    print("╭────────────────────────────── 🤖 Agent Started ──────────────────────────────╮")
    print("│                                                                              │")
    print("│  Agent 1: Engenheiro de Sourcing Primitivo (PYTHON NATIVO)                   │")
    print("│  Task: Ingerir HTML e Arrancar Tabela Custo $0                               │")
    print("│                                                                              │")
    print("╰──────────────────────────────────────────────────────────────────────────────╯")
    
    table_text = extract_table_only(payload_bypass_text)
    
    bronze_path = os.path.join(PATHS["bronze"], f"agent1_extract_{current_date_str()}.txt")
    with open(bronze_path, "w", encoding="utf-8") as f:
        f.write(table_text)
        
    records = [line for line in table_text.split('\n') if line.strip()]

    # =========================================================================
    # AGENTE 2: PYTHON NATIVO (Parser Básico & Chunker)
    # =========================================================================
    print("\n╭────────────────────────────── 🤖 Agent Started ──────────────────────────────╮")
    print("│                                                                              │")
    print("│  Agent 2: Parseador Sintático & Chunker (PYTHON NATIVO)                      │")
    print("│  Task: Quebrar strings | em propriedades DTO Dicionário e Fatiar.            │")
    print("│                                                                              │")
    print("╰──────────────────────────────────────────────────────────────────────────────╯")
    
    prata_records = []
    for line in records:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 6:
            try:
                v_str = parts[5].replace('R$', '').replace('.', '').replace(',', '.').strip()
                val = float(v_str)
            except: val = 0.0
            
            prata_records.append({
                "id_origem": parts[0],
                "fornecedor_cnpj": parts[1] if parts[1] else "INVALIDO",
                "data_emissao": parts[2],
                "politico_nome": parts[3],
                "categoria_origem": parts[4],
                "valor_bruto": val,
                "link_documento": "",
                "ia_risco_nivel": "PENDENTE",
                "ia_comentario_revisor": "Aguardando Avaliação Olhos de Águia"
            })
            
    prata_path = os.path.join(PATHS["prata"], f"agent2_clean_base_{current_date_str()}.json")
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump(prata_records, f, ensure_ascii=False, indent=4)

    # Chunker fatiando Strings JSON
    chunks_de_json = chunk_records([json.dumps(r, ensure_ascii=False) for r in prata_records], max_tokens_per_chunk=2500)
    print(f"\n[PIPELINE] Token Governor: Enviando a Prata JSON para as 2 IAs (Agent 3 e Agent 4) dividida em {len(chunks_de_json)} Chunks seguros.")

    all_results = []
    
    # Loop de Processamento (IAs)
    for i, chunk in enumerate(chunks_de_json):
        chunk_text = '\n'.join(chunk)
        
        model_escolhido, governor = get_available_model(chunk_text)
        governor.wait_if_needed(chunk_text)
        
        print(f"[PIPELINE] Processando Lote de Inteligência {i+1}/{len(chunks_de_json)} (Modelo: {model_escolhido})...")
        
        from crewai import LLM
        override_llm = LLM(model=model_escolhido, api_key=os.environ.get("GROQ_API_KEY"))
        agent_organizer.llm = override_llm
        agent_compliance.llm = override_llm
        
        # =========================================================================
        # AGENTE 3: CREW AI (Data Cleaner Sênior / Organizador Cognitivo)
        # =========================================================================
        task_clean_chunk = Task(
            description=dedent(f"""Receba os Objetos JSON iniciais purificados em lote:
{chunk_text}
Você deve enriquecer esses dados. Use sua inteligência para extrair provas, Links Visuais de NFs e URLS perdidas dentro dos nomes de despesa, e padronizar textos rasgados. Passe este pacote refinado para o próximo colega Auditor. Retorne um JSON com a mesma exata estrutura anterior mas enriquecido."""),
            expected_output="Os dados organizados e enriquecidos em formato JSON.",
            agent=agent_organizer
        )
        
        # =========================================================================
        # AGENTE 4: CREW AI (Compliance Auditor / Olhos de Águia)
        # =========================================================================
        task_compliance_chunk = Task(
            description="ATUE COMO AUDITOR FEDERAL. Você acabou de receber um pacote de despesas do Engenheiro Organizador. Cruze Categorias vs Valor vs Nome da Despesa em cada registro. Atribua o Risco (ALTO/MODERADO/BAIXO) para o campo 'ia_risco_nivel' de CADA despesa, justificando rapidamente no campo 'ia_comentario_revisor'. Retorne APENAS um Array Limpo de JSON com todos os registros embutidos dentro da chave 'extracao'.",
            expected_output="JSON List estrito com chave 'extracao' embalando OBRIGATORIAMENTE todas as despesas revisadas. Sem markdown residual.",
            agent=agent_compliance
        )
        
        crew_chunk = Crew(
            agents=[agent_organizer, agent_compliance],
            tasks=[task_clean_chunk, task_compliance_chunk],
            verbose=VERBOSE_MODE
        )
        
        resultado_chunk = crew_chunk.kickoff()
        all_results.append(resultado_chunk.raw if hasattr(resultado_chunk, 'raw') else str(resultado_chunk))

    print("\n🏁 CONSTRUÇÃO MULTI-CHUNK DAS 2 IAs (AGENTES 3 e 4) FINALIZADA. ATIVANDO AGENTE 5 DE DATALAKE")
    
    # =========================================================================
    # AGENTE 5: PYTHON NATIVO (Prisma Guardião / Consolidador)
    # =========================================================================
    print("╭────────────────────────────── 🤖 Agent Started ──────────────────────────────╮")
    print("│                                                                              │")
    print("│  Agent 5: Comandante Guardião do Data Lake Prisma (PYTHON NATIVO)            │")
    print("│  Task: Receber a Carga Cognitiva JSON, Gerar MD5 Hashes Isolados.            │")
    print("│                                                                              │")
    print("╰──────────────────────────────────────────────────────────────────────────────╯")

    all_evaluated_records = []
    for chunk_result in all_results:
        try:
            clean_res = chunk_result.strip()
            if clean_res.startswith("```json"): clean_res = clean_res[7:]
            if clean_res.startswith("```"): clean_res = clean_res[3:]
            if clean_res.endswith("```"): clean_res = clean_res[:-3]
            
            parsed = json.loads(clean_res.strip())
            
            if isinstance(parsed, dict) and "extracao" in parsed:
                all_evaluated_records.extend(parsed["extracao"])
            elif isinstance(parsed, list):
                all_evaluated_records.extend(parsed)
            elif isinstance(parsed, dict):
                all_evaluated_records.append(parsed)
        except Exception as e:
            print(f"[MERGE] ⚠️ Chunk de IA Cospido Inválido (Recuperação Automática Pulou os Corrompidos): {str(e)}")
            
    valid_records = []
    quarantine_records = []
    for reg in all_evaluated_records:
        cnpj = str(reg.get('fornecedor_cnpj', '')).upper()
        if reg.get('ia_risco_nivel') == "ALTO" and ("INVALID" in cnpj or not cnpj):
            quarantine_records.append(reg)
        else:
            chave = f"{reg.get('politico_nome','')}_{cnpj}_{reg.get('valor_bruto','')}"
            reg['hash_unico'] = hashlib.md5(chave.encode('utf-8')).hexdigest()
            valid_records.append(reg)
            
    run_date = current_date_str()
    
    try:
        if valid_records:
            ouro_path = os.path.join(PATHS["ouro"], f"alba_verbas_OURO_CREWAI_{run_date}.json")
            with open(ouro_path, 'w', encoding='utf-8') as f:
                json.dump(valid_records, f, ensure_ascii=False, indent=4)
            print(f"✔️💾 [A5] Controlador Prisma: Salvos {len(valid_records)} blocos OURO_CREWAI_{run_date}.json.")
            
        if quarantine_records:
            quar_path = os.path.join(PATHS["quarentena"], f"alba_quar_crewai_{run_date}.json")
            with open(quar_path, 'w', encoding='utf-8') as f:
                json.dump(quarantine_records, f, ensure_ascii=False, indent=4)
            print(f"⚠️💾 [A5] Controlador Prisma: Jogado {len(quarantine_records)} blocos na Quarentena Oficial.")
            
        print("\n🏆 Operação Datalake Enterprise Vencida com Sucesso Absoluto.")
            
    except Exception as em:
        print(f"\n❌ Falha no Serializador Final Prisma Datalake: {str(em)}")

if __name__ == '__main__':
    arquivo = '/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/organizar/alba_verbas_markdown.txt'
    try:
        with open(arquivo, 'r', encoding='utf-8') as fs:
            txt_in = fs.read()
        run_alba_crew(txt_in)
    except Exception as fl:
        print("Mestre, verifique o caminho do arquivo txt. Fuga executiva falhou.")
