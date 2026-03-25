import os, sys, json, time
from pathlib import Path
import requests
import concurrent.futures
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv

load_dotenv()

def valida_link_nf(link: str, session: requests.Session) -> tuple[str, str]:
    if not link or "fserver/:anexo:" in link:
        return "MÁXIMO", "Link ausente/Lista errada"
    if not link.startswith("http"):
        return "ALTO", "Link inválido"
    try:
        r = session.head(link, timeout=3, allow_redirects=True)
        if r.status_code != 200:
            return "ALTO", f"Link HTTP Inacessível ({r.status_code})"
        return "BAIXO", "PDF acessível"
    except Exception:
        return "ALTO", "Falha validação link (Timeout/Erro)"

def calcular_score(registro: dict, contagem_mes: dict, contagem_fornecedor: dict, session: requests.Session) -> tuple[float, list]:
    score = 0.0
    motivos = []
    
    categoria = registro.get("categoria", "") or ""
    if "Divulgação da atividade parlamentar" in categoria:
        score += 3.0
        motivos.append("Divulgação genérica")
    
    deputado = registro.get("deputado", "") or ""
    mes = registro.get("competencia", "") or ""
    chave_mes = f"{deputado}|{categoria}|{mes}"
    if contagem_mes.get(chave_mes, 0) > 1:
        score += 4.0
        motivos.append(f"Repetição suspeita ({contagem_mes[chave_mes]}x no mês)")

    cnpj = str(registro.get("cnpj_fornecedor", "") or "").strip()
    if cnpj and contagem_fornecedor.get(cnpj, 0) > 2:
        score += 2.0
        motivos.append("Concentração de Fornecedor")

    nf = str(registro.get("num_nf", "") or "").strip()
    if nf in ["1", "0", ""] or len(nf) < 3:
        score += 3.5
        motivos.append("NF genérica (ausente ou len < 3)")
    
    try:
        valor = float(registro.get("valor", 0) or 0)
    except:
        valor = 0.0

    if valor > 2500 and "Divulgação" in categoria:
        score += 2.0
        motivos.append("Valor alto divulgação (> R$2500)")
    
    risco_link, msg_link = valida_link_nf(registro.get("link_pdf_nf", ""), session)
    if risco_link == "MÁXIMO": 
        score += 4.0
        motivos.append(msg_link)
    elif risco_link == "ALTO": 
        score += 2.5
        motivos.append(msg_link)
    
    if "/0001-" in cnpj and valor > 1000:
        score += 2.0
        motivos.append("CNPJ Matriz/Nova + Alto valor")
    
    return min(score, 10.0), motivos

def main():
    print("[AGENT 3] 🦅 ÁGUIA FORENSE v2.0 — Iniciando...")
    sys.stdout.flush()
    
    base_dir = Path(__file__).resolve().parent.parent.parent
    ano_alvo = os.environ.get("ANO_ALVO", "2015")
    prata_path = base_dir / "data" / "saida" / "prata" / f"alba_{ano_alvo}_prata.json"
    
    if not prata_path.exists():
        # Fallback para o mais recente se o específico não existir
        prata_files = sorted((base_dir / "data" / "saida" / "prata").glob("alba_*_prata.json"), key=os.path.getmtime, reverse=True)
        if not prata_files:
            print(f"[AGENT 3] Erro: Arquivo Prata não encontrado para o ano {ano_alvo}.")
            sys.exit(1)
        prata_path = prata_files[0]
    with open(prata_path, "r", encoding="utf-8") as f:
        registros = json.load(f)
    
    print(f"[AGENT 3] 🔍 {len(registros)} registros prata interceptados de {prata_path.name}")
    
    contagem_mes = {}
    contagem_fornecedor = {}
    for r in registros:
        chave_mes = f"{r.get('deputado','')}|\"{r.get('categoria','')}|\"{r.get('competencia','')}"
        contagem_mes[chave_mes] = contagem_mes.get(chave_mes, 0) + 1
        cnpj = str(r.get("cnpj_fornecedor", "") or "").strip()
        if cnpj:
            contagem_fornecedor[cnpj] = contagem_fornecedor.get(cnpj, 0) + 1

    session = requests.Session()
    print("[AGENT 3] ✅ Etapa 1: Atribuindo Score Heurístico (Regras de Negócio e HTTP Check)...")
    for i, r in enumerate(registros):
        if i % 200 == 0:
            print(f"  -> Scoreando {i}/{len(registros)}...")
            sys.stdout.flush()
            
        score, motivos = calcular_score(r, contagem_mes, contagem_fornecedor, session)
        r["score_risco"] = round(score, 1)
        r["motivos_risco"] = motivos
        
        if score >= 8: r["risco_nivel"] = "MÁXIMO"
        elif score >= 6: r["risco_nivel"] = "ALTO"  
        elif score >= 4: r["risco_nivel"] = "MÉDIO"
        else: r["risco_nivel"] = "BAIXO"
        
        r["comentario_aguia"] = f"Risco Autônomo ({score}/10): {'; '.join(motivos)}"

    print("\n[AGENT 3] ✅ Etapa 2: Acionando Ouro AI Engine (LLaMA) para refinamento em lote...")
    analisados = []
    CHUNK_SIZE = 35 # Aumentamos chunk levemente
    total_consumed_tokens = 0
    
    GROQ_KEY = os.getenv("GROQ_API_KEY", "")
    llm = LLM(model="groq/llama-3.3-70b-versatile", api_key=GROQ_KEY, temperature=0.0)
    
    aguia = Agent(
        role="Auditor TCU Forense",
        goal="Analisar profundamente a taxonomia de riscos de Verbas ALBA",
        backstory="Auditor Sênior anti-corrupção com 25 anos de TCU. Detecta fraudes sutis em verbas públicas baseando-se em scores heurísticos providos.",
        llm=llm,
        verbose=False
    )
    
    total_chunks = (len(registros) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for i in range(0, len(registros), CHUNK_SIZE):
        chunk = registros[i:i+CHUNK_SIZE]
        print(f"[AGENT 3 AI] Processando Chunk {i//CHUNK_SIZE + 1} de {total_chunks}...")
        sys.stdout.flush()
        
        custom_prompt = os.getenv("AIOX_CUSTOM_PROMPT", "").strip()
        default_prompt = f"""
Você é o Revisor Final (Camada Ouro). Os {len(chunk)} registros abaixo já receberam um "score_risco" matemático rigoroso e uma taxonomia em "risco_nivel" (MÁXIMO, ALTO, MÉDIO, BAIXO).
Seu trabalho é APENAS formatar e lapidar linguisticamente a chave `comentario_aguia` baseando-se nos `motivos_risco`, tornando-a uma conclusão oficial de auditoria coesa, e você NUNCA DEVE diminuir o `risco_nivel` se ele for ALTO ou MÁXIMO.

Dados processados heuristicamente:
{json.dumps(chunk, ensure_ascii=False, indent=2)}

Retorne APENAS um JSON Array perfeito com todos os registros mantendo a estrutura exata, alterando apenas a gramática do "comentario_aguia" para tom profissional investigativo.
"""
        task_desc = f"{custom_prompt}\n\nDados do Chunk:\n{json.dumps(chunk, ensure_ascii=False, indent=2)}\n\nRetorne APENAS um JSON Array perfeito mantendo a mesma estrutura de chaves e os registros." if custom_prompt else default_prompt

        task = Task(
            description=task_desc,
            expected_output="Valid JSON Array of objects.",
            agent=aguia
        )
        
        crew = Crew(agents=[aguia], tasks=[task], max_rpm=28, verbose=False)
        
        try:
            result = crew.kickoff()
            
            # Extração de Métricas de Uso de Tokens
            if hasattr(crew, 'usage_metrics') and crew.usage_metrics:
                try:
                    metrics = crew.usage_metrics
                    p_tok = getattr(metrics, 'prompt_tokens', 0)
                    c_tok = getattr(metrics, 'completion_tokens', 0)
                    tot_tok = getattr(metrics, 'total_tokens', p_tok + c_tok)
                    total_consumed_tokens += tot_tok
                    print(f"[AGENT 3 AI] 📊 Tokens do Chunk: {tot_tok} (Prompt: {p_tok} | Geração: {c_tok})")
                except:
                    pass

            texto = result.raw if hasattr(result, 'raw') else str(result)
            inicio = texto.find('[')
            fim = texto.rfind(']') + 1
            if inicio != -1 and fim > 0:
                refined = json.loads(texto[inicio:fim])
                if isinstance(refined, list) and len(refined) > 0:
                    analisados.extend(refined)
                    continue
        except Exception as e:
            print(f"[AGENT 3 AI] Falha na LLaMA no chunk {i//CHUNK_SIZE + 1}, injetando salvamento raw: {e}")
            
        analisados.extend(chunk)

    ano = registros[0].get("ano", "0000") if registros else "0000"
    output = prata_path.parent.parent / "ouro" / f"alba_{ano}_ouro_aguia_v2.json"
    os.makedirs(output.parent, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(analisados, f, ensure_ascii=False, indent=2)
    
    altos = sum(1 for r in analisados if r.get("risco_nivel") == "ALTO")
    maximos = sum(1 for r in analisados if r.get("risco_nivel") == "MÁXIMO")
    medios = sum(1 for r in analisados if r.get("risco_nivel") == "MÉDIO")
    
    print(f"\n============================================================")
    print(f"RELATÓRIO FINAL — AGENT 3 v2.0 (Camada Ouro)")
    print(f"============================================================")
    print(f"🔴 MÁXIMO: {maximos} | 🟠 ALTO: {altos} | 🟡 MÉDIO: {medios}")
    print(f"Total Validado: {len(analisados)}")
    print(f"💰 Custo Cognitivo Total: {total_consumed_tokens} tokens consumidos na API da Groq.")
    print("\n[TOP 5 ALERTAS EM MÁXIMO RISCO]")
    top_risks = sorted(analisados, key=lambda x: x.get("score_risco", 0), reverse=True)[:5]
    for idx, r in enumerate(top_risks, 1):
        print(f"  {idx}. Ref: {r.get('deputado','')} - Score {r.get('score_risco')} - Proc: {r.get('num_processo')}")
        print(f"      Motivos: {r.get('motivos_risco')}")
        print(f"      Águia: {r.get('comentario_aguia')}")
    
    print(f"\n[AGENT 3 v2.0] [DONE] ✅ Salvo em: {output}")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
