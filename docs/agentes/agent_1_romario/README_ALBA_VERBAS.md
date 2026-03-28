# Agent 1 – Romário (ALBA Verbas Indenizatórias)

**Objetivo Geral**
O **Agent 1 (Romário)** é o scraper de escopo central da arquitetura N888N. Seu objetivo é navegar pelo portal de transparência da Assembleia Legislativa da Bahia (ALBA), extrair linha a linha as verbas indenizatórias dos deputados e consumir as páginas de detalhe para capturar metadados das notas fiscais, gerando o dado bruto inicial (Camada Bronze).

---

## 📥 Entradas (Inputs)

Este agente não consome arquivos ou diretórios prévios. Ele é o marco zero da ingestão (`Ingestion Layer`). 

- **Fonte de Dados (URL):** `https://www.al.ba.gov.br/transparencia/verbas-idenizatorias`
- **Parâmetros de Execução:** 
  - `--ano`: Ano alvo da extração (Padrão: variável de ambiente `ANO_ALVO` ou `2015`).
  - `--max_pages`: Limite de páginas (Útil para testes, `0` = sem limite).
  - `--resume`: Reinicia do último checkpoint disponível.

---

## 📤 Saídas (Outputs)

Gera a fundação de dados do **DataLake** na sua forma mais bruta e inalterada.

- **Arquivo Principal:** `data/saida/bronze/alba_YYYY_bronze.json`
- **Checkpoint de Resiliência:** `data/saida/bronze/alba_YYYY_checkpoint.json`
  - *O checkpoint salva o estado da paginação (a cada 5 páginas) para evitar perda de dados em quedas de rede.*

---

## 🛠️ Tecnologias e Bibliotecas

- **Requests & requests.Session():** Para chamadas HTTP e manutenção de conexão na travessia das páginas.
- **BeautifulSoup (bs4):** Para parsing semântico do DOM (HTML) e navegação nas tags das tabelas.
- **Regex (`re`):** Para detecção do formato de CNPJ e extração do ID da ALBA dentro da URL de detalhes.
- **JSON:** Formato de serialização nativa para o Datalake.
- **Argparse & Sys/OS:** Gerenciamento dos comandos de terminal.

---

## ⚙️ Fluxo de Processamento (Passo a Passo)

1. **Inicialização e Parâmetros:**
   O agente é executado via `agent_1_wrapper.py` (uma safra) ou `agent_1_batch.py` (várias safras de uma vez). O script define o ano alvo e verifica a existência de um checkpoint (`alba_YYYY_checkpoint.json`).

2. **Navegação pela Paginação Mestre:**
   Entra em um loop contínuo acessando o endpoint via GET, passando `?ano=YYYY&page=N`. Utiliza headers customizados (simulando um navegador real Chrome) para evitar bloqueios triviais de *User-Agent*.

3. **Extração da Tabela Resumo (Parsing HTML):**
   Com o `BeautifulSoup`, localiza e isola todas as linhas (`<tr>`) que contenham pelo menos 6 colunas (`<td>`). Extrai dados preliminares:
   - Nº Processo, Nº NF, Competência (Mês/Ano), Nome do Deputado, Categoria e Valor.
   - Extrai o `href` do botão de detalhes que aponta para a página da NF específica (ex: `/transparencia/verbas-idenizatorias/73907/`).

4. **Coleta de Detalhes Profundos (Aprofundamento na NF):**
   Para cada linha encontrada na tabela resumo, o Agente 1 aciona a função auxiliar `scrape_detalhes(id_alba)`. Ele visita a página específica daquela nota fiscal contendo os metadados ricos:
   - **Fornecedor:** Nome e CNPJ.
   - **Metadados Financeiros:** Valor detalhe, Valor glosado.
   - **URL do PDF:** Captura o link para o comprovante da nota fiscal escaneado/anexado pelo parlamentar.

5. **Engenharia de "Enterprise Logs":**
   Em formato reativo, exibe no terminal um painel de instrumentação detalhado a cada registro processado (Ano, Página atual, Indicativo de "Possui PDF", Valor Bruto e Nome do Deputado), permitindo auditoria visual humana em tempo real do job em andamento.

6. **Checkpoint e Finalização:**
   A cada 5 páginas (cerca de 50 a 100 registros iterados), um dump em JSON salva o progresso atual. Ao alcançar o status HTTP 404 (fim dos dados) ou o limite do scraper, o arquivo final (`alba_YYYY_bronze.json`) é gerado no DataLake.

---

## 🛡️ Regras de Negócio e Boas Práticas (Camada Bronze)

- **Extração Passiva (Fidelidade do Dado Bruto):** O Agente 1 age como "espelho" do portal. Modificações de dados no Agente 1 são PROIBIDAS (com exceção a parsing de float no valor). Nomes não são normalizados e strings são mantidas "como estão".
- **Resiliência de Rede:** Em caso de interações não-404 fora do 200 OK (ex: 500, 502), aplica um leve *sleep* e realiza *retry* automatizado. 
- **Limpeza Pós-Extração:** Todo tratamento pesado (limpar nomes em maiúsculas, sanitização de CNPJ) é empurrado **obrigatoriamente** para a camada Prata (Agente 2).
- **Sem Modificação Destrutiva:** Scrapers nunca excluem JSONs do ano sem explícita confirmação, eles fazem sobrescrita total ou usam checkpoints de continuação (`--resume`).

---

## 🔗 Integrações na Esteira

O Agent 1 (Romário) atua de forma isolada do restante, mas é a espinha dorsal para os Agentes seguintes:

- **➡️ Agent 2 (Bebeto):** 
  É o consumidor natural da Camada Bronze. Bebeto lê os dados recém-raspados pelo Romário, limpa ruídos, gera chaves primárias autônomas (`prisma_id`) por MD5 e corrige links relativos do PDF. Bebeto expele a Camada Prata.

- **➡️ Kaká v4.1 Enterprise:**
  Recebe o JSON refinado do Bebeto, usa o campo "url_pdf_nf" rastreado originariamente pelo Romário e faz download forense do comprovante físico da nota (via PDF). Extrai, de dentro da folha faturada do papel, a comprovação do "Valor" extraído pelo Romário, aplicando um *Score de Confiança* triplo (Triple-Check).

- **➡️ Agent 5 (PDF Forensic) & Agent 6 (Merge Final):**
  Arquiteturas de fluxo alternativo para a extração passiva. O Agent 5 consome offline um repositório preenchido indiretamente com URLs da Camada Prata para decodificar PDFs maciçamente, e o Agent 6 cruza o JSON validado pelo banco Prática (Camada Ouro) com os laudos do Agent 5.

---

**[AGENT 1 DONE]** Operação de raspagem contínua projetada para 1M+ requisições com altíssima redundância.
