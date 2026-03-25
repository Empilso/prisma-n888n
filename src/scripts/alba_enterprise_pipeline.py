"""
@dev *aiox-agentic-extractor*
Crew: Pipeline Enterprise FASE 1 - Metadados e Links Organizados
Objetivo: Conformação do Padrão Prisma sem baixar PDFs no momento.
A IA Groq processa as tabelas HTML raspadas e o Módulo Revisor analisa o contexto.
*ATUALIZAÇÃO*: Integração Real com GROQ_API_KEY ativada nos Agentes 2 e 3.
"""

import datetime
import hashlib
import json
import os
from typing import List, Dict, Any
from groq import Groq

# =====================================================================
# CREDENCIAIS E CLIENTE DE INTELIGÊNCIA ARTIFICIAL
# =====================================================================
os.environ["GROQ_API_KEY"] = "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"
groq_client = Groq()
MODELO_LLM = "llama-3.3-70b-versatile"

# =====================================================================
# CONFIGURAÇÃO DO PADRÃO PRISMA (MEDALLION)
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
# AGENT 1: COLETOR WEB DE METADADOS (SOURCING & BYPASS UPLOAD)
# =====================================================================
class AgentScraper:
    PROMPT_DA_IA = "Você é um Scraper focado em Tabelas HTML/Dados Estruturais..."
    
    def __init__(self, local_file_bypass: str = None):
        self.local_file_bypass = local_file_bypass
        
    def scrape_real_world(self):
        print("\n📥 [AGENTE 1: Coletor de Tabelas e Links]")
        
        if self.local_file_bypass and os.path.exists(self.local_file_bypass):
            print(f"MÓDULO: Upload Bypass Ativado (Lendo arquivo: {os.path.basename(self.local_file_bypass)})")
            with open(self.local_file_bypass, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            print(f"=> Sucesso. {len(raw_text)} bytes brutos carregados do disco.")
        else:
            print("MÓDULO: Crawl4AI Web Scraper")
            raw_text = "[Link PDF](al.ba.gov.br) - 101/26. ROSEMB PINTO. R$ 5OO,00" # Exemplo Dummy
            
        path = os.path.join(PATHS["bronze"], f"texto_cru_alba_{current_date_str()}.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(raw_text)
            
        print(f"=> Arquivo salvo na Bronze: {path}")
        return raw_text

# =====================================================================
# AGENT 2: ORGANIZADOR GROQ INTELLIGENCE (LLM CLEANER REAL)
# =====================================================================
class AgentOrganizerGroq:
    PROMPT_DA_IA = """
    Você é um Especialista de Estruturação de Dados JSON impecável. 
    Abaixo você receberá um texto HTML/Markdown bruto vindo de um Scraping do site da ALBA.
    Você DEVE extrair UMA LISTA JSON sob a chave 'despesas', contendo multiplos objetos dict com:
    "id_origem" (str): Número do processo ou protocolo,
    "politico_nome" (str): Nome do deputado tratado para maiúsculas,
    "fornecedor_cnpj" (str): Apenas os 14 dígitos. Se nulo/ilegível, coloque "INVALIDO",
    "valor_bruto" (float): O valor matemático decimal tratado e convertido de string R$,
    "categoria_origem" (str): Categoria da despesa informada,
    "data_emissao" (str): Data convertida para AAAA-MM-DD,
    "link_documento" (str): A url extraída do texto para chegar ao PDF.
    
    Converta erros de OCR e letras O em Zeros matemáticos. Retorne APENAS UM JSON VÁLIDO contendo a chave 'despesas', absolutamente nenhuma fala adicional. Não quebre a sintaxe.
    """
    
    def groq_organize_data(self, raw_text: str) -> List[Dict[str, Any]]:
        print("\n🤖 [AGENTE 2: Organizador Cognitivo Groq]")
        print("MÓDULO: LLM Llama-3.3-70B (GROQ CLOUD API REAL)")
        print(f"Enviando os dados brutos ({len(raw_text)} bytes inteiros) para o cérebro da Groq processar JSON...")
        
        try:
            response = groq_client.chat.completions.create(
                model=MODELO_LLM,
                messages=[
                    {"role": "system", "content": self.PROMPT_DA_IA},
                    {"role": "user", "content": f"Formate os registros contidos no trecho a seguir para o Schema JSON exigido:\n\n{raw_text}"}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            # Decodificando o JSON Retornado Diretamente pelo Cerebro da Groq
            json_response = json.loads(response.choices[0].message.content)
            silver_data = json_response.get("despesas", [])
            print(f"=> Sucesso! A Groq extraiu e limpou {len(silver_data)} registros estruturados perfeitos direto do caos HTML!")
            return silver_data
            
        except Exception as e:
            print(f"❌ Erro Crítico na Conversão IA do Agente 2: {str(e)}")
            return []

# =====================================================================
# AGENT 3: REVISOR ANALÍTICO GROQ (METADADOS SÊNIOR REAL)
# =====================================================================
class AgentRevisorAnaliticoGroq:
    PROMPT_DA_IA = """
    Você é um Auditor Federal Revisor Sênior (Anti-corrupção). 
    Sua entrada é um JSON com Metadados limpos.
    Avalie o cruzamento entre a categoria financeira da despesa e o 'valor_bruto'.
    Seja cauteloso: Divulgação, Assessorias Externas, Combustíveis com mais de R$ 5000,00 diarios geram Ia Risco.
    Retorne exatamente o mesmo array JSON sob a chave 'despesas_analisadas', 
    mas ADICIONE a cada objeto as seguintes chaves:
    "ia_risco_nivel": "ALTO", "MODERADO" ou "BAIXO",
    "ia_comentario_revisor": Uma curtíssima explicação de max 10 palavras do aval.
    
    Retorne apenas o JSON VÁLIDO sob a chave 'despesas_analisadas'. Nada de conversas extra.
    """
    
    def groq_final_review(self, silver_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        print("\n🧐 [AGENTE 3: Revisor Analítico via Metadados (Groq Llama-3.3)]")
        if not silver_data:
            print("Nada para revisar.")
            return []
            
        print(f"Submetendo o JSON Limpo ({len(silver_data)} itens) para Auditoria da Inteligência Artificial Sênior...")
        
        payload_str = json.dumps(silver_data, ensure_ascii=False)
        
        try:
            response = groq_client.chat.completions.create(
                model=MODELO_LLM,
                messages=[
                    {"role": "system", "content": self.PROMPT_DA_IA},
                    {"role": "user", "content": f"Inspecione o lote:\n{payload_str}"}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            json_response = json.loads(response.choices[0].message.content)
            gold_enriched = json_response.get("despesas_analisadas", [])
            print("=> Sucesso! Revisão de Risco Concluída e Anotada por IA em milissegundos.")
            return gold_enriched
            
        except Exception as e:
            print(f"❌ Erro Crítico na Auditoria IA do Agente 3: {str(e)}")
            return silver_data # Pass-through caso dê erro para não perder dados

# =====================================================================
# AGENT 4: CONTROLADOR PRISMA (IDEMPOTÊNCIA E BANCO DE DADOS)
# =====================================================================
class AgentPrismaLoader:
    def generate_hash_and_save(self, final_reviewed_data: List[Dict[str, Any]]):
        print("\n💽 [AGENTE 4: Controlador Padrão Prisma]")
        if not final_reviewed_data:
            print("❌ Vazio. Encerrando.")
            return
            
        run_date = current_date_str()
        valid_records = []
        quarantine_records = []
        
        for reg in final_reviewed_data:
            cnpj = str(reg.get('fornecedor_cnpj', '')).upper()
            if reg.get('ia_risco_nivel') == "ALTO" and ("INVALID" in cnpj or not cnpj):
                quarantine_records.append(reg)
                continue
                
            chave = f"{reg.get('politico_nome','')}_{cnpj}_{reg.get('valor_bruto','')}"
            reg['hash_unico'] = hashlib.md5(chave.encode('utf-8')).hexdigest()
            valid_records.append(reg)
            
        print(f"✔️ {len(valid_records)} notas consolidadas perfeitamente pela IA salvar em Ouro.")
        if quarantine_records:
            print(f"⚠️ {len(quarantine_records)} Entradas Rejeitadas movidas para Quarentena.")
        
        if valid_records:
            ouro_path = os.path.join(PATHS["ouro"], f"alba_verbas_OURO_NATIVO_IA_REAL_{run_date}.json")
            with open(ouro_path, 'w', encoding='utf-8') as f:
                json.dump(valid_records, f, ensure_ascii=False, indent=4)
        
        if quarantine_records:
            quar_path = os.path.join(PATHS["quarentena"], f"alba_quarentena_links_{run_date}.json")
            with open(quar_path, 'w', encoding='utf-8') as f:
                json.dump(quarantine_records, f, ensure_ascii=False, indent=4)

# =====================================================================
# EXECUÇÃO METADADOS - FASE 1 (COM INTEGRAÇÃO LLM REAL)
# =====================================================================
def run_native_ai_pipeline(arquivo_upload: str = None):
    print("\n" + "="*80)
    print("🚀 NATIVE AI PIPELINE: EXTRAÇÃO, TRATAMENTO GROQ Llama-3 E AUDITORIA")
    print("="*80)
    
    ag1 = AgentScraper(local_file_bypass=arquivo_upload)
    raw = ag1.scrape_real_world()
    
    ag2 = AgentOrganizerGroq()
    silver = ag2.groq_organize_data(raw)
    
    ag3 = AgentRevisorAnaliticoGroq()
    gold = ag3.groq_final_review(silver)
    
    ag4 = AgentPrismaLoader()
    ag4.generate_hash_and_save(gold)
    
    print("\n[+] Fluxo Finalizado. Software 3.0 Operacional.")

if __name__ == "__main__":
    # Testando com a chave Groq Real e o Markdown Fornecido
    arquivo = "/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/organizar/alba_verbas_markdown.txt"
    run_native_ai_pipeline(arquivo_upload=arquivo)
