import os
import json
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv

load_dotenv()

# Configurando o ambiente com a chave (se não estiver exportada)
GROQ_KEY = os.getenv("GROQ_API_KEY", "")

# Registros de teste (MOCK)
teste_chunk = [
  {
    "num_processo": "9797", "deputado": "Zé Neto Lula", 
    "valor": 1200, "categoria": "Divulgação da atividade parlamentar",
    "cnpj_fornecedor": "74.193.731/0001-37", "competencia": "12/2015"
  },
  {
    "num_processo": "9768", "deputado": "Maria del Carmen", 
    "valor": 500, "categoria": "Divulgação da atividade parlamentar",
    "cnpj_fornecedor": "10.699.669/0001-77", "competencia": "12/2015"
  },
  {
    "num_processo": "9767", "deputado": "Maria del Carmen", 
    "valor": 2888, "categoria": "Divulgação da atividade parlamentar",
    "cnpj_fornecedor": "07.318.773/0001-60", "competencia": "12/2015"
  }
]

print("[TESTE AGENT 3] Iniciando LLM com LLaMA 3.3 70B...")
llm = LLM(model="groq/llama-3.3-70b-versatile", api_key=GROQ_KEY, temperature=0.0)

aguia = Agent(
    role="Compliance Forensic Analyst",
    goal="Detectar anomalias, superfaturamento e riscos em verbas parlamentares",
    backstory="Especialista em auditoria pública com 20 anos de experiência no TCU",
    llm=llm,
    verbose=False,
)

task = Task(
    description=f"""
Analise os registros abaixo de verbas indenizatórias parlamentares.
Para cada registro, adicione os campos:
- risco_nivel: "Baixo", "Médio" ou "Alto"
- comentario_aguia: análise de 1 frase sobre anomalias ou conformidade

Critérios de risco:
- Alto: valor > R$20.000 em categoria única, fornecedor repetido com valores altos, CNPJ suspeito
- Médio: valor entre R$10k-20k, categoria genérica como "Assessoria"
- Baixo: valores normais e categoria clara

Registros:
{json.dumps(teste_chunk, ensure_ascii=False, indent=2)}

Retorne APENAS um JSON array válido com todos os registros originais + campos risco_nivel e comentario_aguia.
""",
    expected_output="JSON array com campos risco_nivel e comentario_aguia adicionados",
    agent=aguia,
)

crew = Crew(agents=[aguia], tasks=[task], verbose=False)
result = crew.kickoff()

try:
    texto = result.raw if hasattr(result, 'raw') else str(result)
    inicio = texto.find('[')
    fim = texto.rfind(']') + 1
    if inicio == -1 or fim == 0:
        print("[ERRO PARSE] Não encontrou colchetes de array no output da LLM.")
        print(texto)
    else:
        chunk_analisado = json.loads(texto[inicio:fim])
        print("\n=== OUTPUT JSON FINAL (PARSED) ===\n")
        print(json.dumps(chunk_analisado, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"[AGENT 3 TESTE] ⚠️ Falhou no parse JSON: {e}")
    print("OUTPUT BRUTO DA LLM:")
    print(texto)
