# 📊 Orquestração N888N: Arquitetura 100% Nativa IA (Software 3.0)
**Padrão PRISMA Datalake | Versão Enterprise 2.0 (Cognitiva)**

A grande falha dos extratores tradicionais é a fragilidade. Para resolver isso, o Padrão PRISMA atua com IA Nativa (Groq Llama-3). O Python atua apenas como "Encanamento", enquanto o cébrebro é puro LLM. Abaixo, o detalhe exato e transparente da operação de cada nó da nossa orquestração.

---

### Módulo 1: Coletor de Rede (Crawl4AI)
* **Resumo:** A Força Bruta. Trabalha ignorando a formatação textual. Seu objetivo é bypassar bloqueios e extrair a matriz HTML / Tabela das despesas governamentais.
* **Paradigma:** Não usa LLM. É rápido, agressivo e cego. Foca em Meta-links.
* **Ferramentas Acopladas:** Crawl4AI (Web Scraper), Anti-Bot Bypass, File System (Upload TXT).
* **Como Ele Opera (Passo-a-Passo):**
  1. Inicia o navegador dinâmico escondido (Headless).
  2. Pula barreiras de anti-bot básicas do portal alvo.
  3. Captura o código HTML limpo da página de tabelas financeiras.
  4. Extrai e guarda a **URL primária (Link)** de cada Nota Fiscal.
  5. Salva todo o bloco em arquivo cru (Markdown/TXT) na pasta `bronze/`.

### Módulo 2: Organizador Cognitivo (Groq LLM)
* **Resumo:** O Início da Inteligência. Onde antes usávamos programadores para criar Expressões Regulares (Regex) falhas, agora usamos Inteligência Artificial pura para higidez.
* **Paradigma:** Substituição do código rígido pela interpretação humana. Tolerante a OCR quebrado ou HTML mal-feito.
* **Ferramentas Acopladas:** Groq Llama-3.3 API, LLM JSON Object Mode, Conversor Matemático.
* **Como Ele Opera (Passo-a-Passo):**
  1. Lê o arquivo Markdown textificado que estava perdido na Camada Bronze.
  2. Aciona o LLM Groq no Modo Restrito JSON (Garantindo que a saída seja perfeita).
  3. "Lê" as linhas e arruma falhas humanas de digitação na Categoria e no Preço. (Ex: "R$ 5OO" vira "500").
  4. Identifica se o documento possui links vazios ou se a rubrica está ilegível.
  5. Expele um Dicionário de Formato Perfeito contendo Nome, CNPJ, Valor e o Link do Comprovante na Camada Prata.

### Módulo 3: Revisor Analítico Sênior (Groq LLM)
* **Resumo:** A última barreira analítica antes do Banco de Dados Central. Um filtro rigoroso de corrupção.
* **Paradigma:** Dispensa revisores lógicos juniores. Lê metadados para emitir "Red Flags" de risco Eleitoral/Financeiro.
* **Ferramentas Acopladas:** Groq Llama-3.3 API, Compliance Cognitive Engine, Risco System.
* **Como Ele Opera (Passo-a-Passo):**
  1. Lê o JSON limpo deixado pelo Agente 2 na Camada Prata.
  2. Faz o cruzamento cognitivo na LLM: *Esta 'Categoria' justifica este 'Valor Bruto' num único evento temporal?*
  3. Identifica as anomalias lógicas e aciona a flag de sistema: `"ia_risco_nivel" = ALTO, MEDIO ou BAIXO`.
  4. Insere o campo textual `"ia_comentario_revisor"` com o laudo resumido da decisão.
  5. Libera a nota, validada e assinada pelo LLM, para o fechamento.

### Módulo 4: Controlador Prisma (Idempotência e Persistência)
* **Resumo:** O Arquivista Matemático. Ele não contesta ou tenta julgar a Inteligência Artificial; sua premissa é estrita conformidade de File System e Banco.
* **Paradigma:** Proteção Estrutural de Dados. Operação exclusiva em Hashes (Big-O = O(1)).
* **Ferramentas Acopladas:** Criptografia Hash MD5, OS File System I/O, Idempotency Gate.
* **Como Ele Opera (Passo-a-Passo):**
  1. Recebe a esteira de metadados prontos do Agente 3 e varre por chaves nulas de sistema.
  2. Gera a Criptografia Chave Única MD5 (Concatenando: Nome+CNPJ+Preço).
  3. Com o MD5 atuando como RG, zera a chance do Datalake aceitar cópias repetidas dessa nota.
  4. Separa os dados lógicos na pasta definitiva `/ouro/` e atira os refis rejeitados (Falta de Link, Risco Extremo) para a `/quarentena/`.
  5. Fecha a esteira e notifica o painel gerencial de "Conformação Finalizada".
