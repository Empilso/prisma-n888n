import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import ScrapeWebsiteTool, FirecrawlScrapeWebsiteTool, SeleniumScrapingTool
from decimal import Decimal
from typing import List

# Import local modules
from models.prisma_schema import VerbaIndenizatoria
from utils.pdf_extractor import extract_pdf_native

load_dotenv()

# Configuração de API Keys (Devem estar no .env)
# EX: FIRECRAWL_API_KEY=xxxx
# EX: GROQ_API_KEY=xxxx

def create_prisma_crew(ano: int):
    """Cria a tripulação PRISMA para um ano específico."""
    
    # 1. TOOLS
    # Prioridade: Firecrawl (estruturado) > ScrapeWebsite (grátis) > Selenium (JS)
    firecrawl_tool = FirecrawlScrapeWebsiteTool() 
    scrape_tool = ScrapeWebsiteTool()
    
# 2. AGENTES
    # Usando modelos econômicos (DeepSeek-V3 ou Llama-3-70b via Groq)
    web_engineer = Agent(
        role='Web Data Engineer (ALBA specialist)',
        goal=f'Extrair a lista de verbas de {ano} (Bloco {ano}) de forma econômica.',
        backstory="""Especialista em scraping de baixo custo. Você prioriza ferramentas nativas antes de chamar APIs pagas. 
        Sua missão é extrair os dados de 2015-2026 em blocos controlados.""",
        tools=[firecrawl_tool, scrape_tool],
        verbose=True,
        allow_delegation=False,
        memory=True
    )
    
    compliance_analyst = Agent(
        role='Compliance Forensic Analyst',
        goal='Auditoria de integridade com foco em economia de tokens.',
        backstory="""Analista que utiliza DeepSeek para estruturação de dados. Você sabe que processar 11 anos 
        exige cautela financeira. Você valida os lotes de despesas um a um.""",
        verbose=True,
        allow_delegation=False
    )

    # 3. TASKS
    task_scraping = Task(
        description=f"""Acesse: https://www.al.ba.gov.br/transparencia/verbas-idenizatorias?ano={ano}
        1. Extraia a tabela de resultados da primeira página (Processo, NF, Deputado, Categoria, Valor).
        2. Para cada linha, clique/acesse os 'DETALHES' para pegar o link do comprovante (PDF) e o CNPJ do fornecedor.
        3. Retorne uma lista de dicionários Python prontos para validação.""",
        expected_output="Uma lista de dicionários JSON contendo todos os campos da VerbaIndenizatoria.",
        agent=web_engineer
    )
    
    task_audit = Task(
        description="""Analise os dados extraídos pelo Web Engineer. 
        Verifique se os valores batem e se as categorias fazem sentido para o cargo parlamentar.
        Atribua um 'risco_nivel' (BAIXO, MEDIO, ALTO).""",
        expected_output="A lista original enriquecida com campos de auditoria e risco.",
        agent=compliance_analyst,
        context=[task_scraping]
    )

    # 4. CREW
    prisma_crew = Crew(
        agents=[web_engineer, compliance_analyst],
        tasks=[task_scraping, task_audit],
        process=Process.sequential,
        verbose=True
    )
    
    return prisma_crew

if __name__ == "__main__":
    # Exemplo de execução para o ano 2015 conforme solicitado
    print("🚀 Iniciando Arqueologia Digital PRISMA (2015)...")
    crew = create_prisma_crew(ano=2015)
    result = crew.kickoff()
    print("\n✅ Resultado da Auditoria 2015:")
    print(result)
