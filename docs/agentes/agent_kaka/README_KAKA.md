# Agent Kaká (v4.1 Enterprise)

**Objetivo Geral**
O **Kaká v4.1** é a "Arma de Destruição em Massa de Fraudes" da suíte N888N. Seu objetivo é cruzar a informação que o deputado declarou textualmente ao Portal (via Agent 1/Bebeto) contra o **físico escaneado (PDF/JPEG)** da Nota Fiscal em si. O agente baixa cada laudo, usa uma cascata de inteligências artificiais com templates cirúrgicos e emite o veredito final sobre a emissão legítima do recurso.

---

## 📥 Entradas (Inputs)

O Kaká é acionado independentemente, mas exige a Camada Prata perfeita como alicerce.

- **Datalake Base:** `data/saida/prata/alba_YYYY_prata.json`
- **Fator Disparador:** Link do arquivo depositado no campo `url_pdf_nf`.
- **Repositório Temporário (Opcional):** Cache local ativado em `data/raw/alba/pdfs/YYYY/` para que não se baixe a mesma NF duas vezes no caso de reinício.

---

## 📤 Saídas (Outputs)

Gera um espelho "Audit-Ready" e "Forensic-Proof" validando até a base decimal das despesas públicas na Bahia.

- **Arquivo Principal:** `data/saida/kaka/alba_YYYY_kaka.json`
- **Dashboard Logs:** Terminal Output classificado como `Enterprise` que indica status Real-Time.

---

## 🛠️ Tecnologias e Bibliotecas

- **PyMuPDF (`fitz`):** Leitura instantânea de metadados nativos de impressoras/textos não-chapados em PDF.
- **Pyzbar & OpenCV:** Detecção nativa do painel 2D de QR Codes (Para notas oficiais base SERPRO) e melhoria inteligente de contraste/enquadramento (Deskew, CLAHE).
- **Invoice2Data / PyTesseract:** Fallback de leitura óptica passiva. Regex genéricas focadas no comércio.
- **Gemini Flash (`google-genai`):** LLM Multi-Modal (Vision) da Google usada exclusivamente quando nenhum dos modelos tradicionais resolve. Governança estrita rate-limited (Max 100~150 dia) para proteger cota financeira de processamento.
- **AsyncIO / AioHTTP / Tenacity:** Rate limiting tolerante a falhas (Network Polling), rodando assíncrono para velocidade bruta.

---

## ⚙️ Fluxo de Processamento de Extração em 4 Camadas (v4.1 Architecture)

A engenharia inteira consiste em rejeitar a Inteligência Artificial até a última gota, focando em matemática exata e algoritmos rápidos primeiro (economizando tempo e CPU):

1. **Downloader Engine & Fase 0 (Classificador):**
   - Baixa o PDF ou pega do cache interno.
   - **Motor de Filtro:** `classificar_tipo` varre as propriedades intrínsecas do laudo num piscar de olhos: Se o texto possuir > 800 caracteres brutos em vetor, ele cai na valeta `nf_digital`. Se for quase em branco (apenas chassi digital), a imagem foi chapada e é identificada como `imagem_ou_escan` (dependente de OCR/IA).

2. **Camada 1: QR CODE Forense (O Selo Dourado):**
   - Rastreia o box 2D de autenticação da nota em PNG na primeira/segunda página.
   - Extrai instantaneamente valores 100% reais sem processamento semântico. Confiança 1.0 (Auditável no Portal Nacional).

3. **Camada 2: Templates Específicos (Machine Routing):**
   - Analisa as texturas de *Headings*. É da Prefeitura de Salvador? Da Prefeitura de Feira de Santana? É DANFE (NF-e)?
   - Pula e insere uma `âncora regex` cirurgicamente montada só para o layout do órgão emissor. (Ex: "VALOR LÍQUIDO DA NOTA" vs "VALOR TOTAL DA NOTA"). Se identificado com sucesso, encerra a máquina e salva (Confiança 0.99+).

4. **Camada 3: Genérica de Regex / Tesseract Local (Fallback):**
   - Buscas generalizadas por `R$` usando a *Invoice2Data* library.

5. **Camada 4: Gemini 2.0 Flash Vision (O Martelo):**
   - Quando as prefeituras criam notas fiscais obscenas em Word/Caneta, envia-se à Cloud do Google e se exige via payload de Prompt os atributos de volta. Uma barreira *Tenacity* com Exponential Backoff monitoriza se o Google bloqueia (`RateLimit`), pausando globalmente 60~70 segundos.

6. **Validação (Triple-Check) & Saída:**
   Aplica um *match factor*. O PDF extraiu R$ 500,00? Na ALBA está relatado R$ 510,00? Se difere além de %10, a nota fiscal é reprovada (Flags: `"kaka_status": "revisao_manual"`).

---

## 🛡️ Regras de Negócio e Boas Práticas (Camada Kaká)

- **Custo Cognitivo Blindado:** O Kaká v4.1 jamais chamará IA para Ler NF de Salvador. Os regex templates baratearam o projeto em 97% na API LLM.
- **Rate Limit Assíncrono:** Para respeitar o servidor do Sefaz/ALBA e a infra, Semáforos (`asyncio.Semaphore(MAX_CONCURRENT=2)`) travam a sede por Threads contendo a banda do download.
- **Auditoria Plena:** Se um documento foi reprovado, é possível provar o "Por que" olhando as strings de rastreio (`kaka_modelo_detectado` e `fonte`(ex: template_salvador)).

---

## 🔗 Integrações na Esteira

- **⬅️ Consumidor de:** Agent 2 (Bebeto) — Usando as strings higienizadas e URLs sólidas.
- **➡️ Pai Alimentador de:** Dashboard PRISMA, Tribunal de Contas, Camada Ouro em si (substituindo Agents 5 e 6). Todo e qualquer PDF só pode ser carimbado com veredito ético do Agente 3 se antes passar pela confirmação que a NF "existe debaixo dos panos" lida pelo Kaká.

---

**[AGENT KAKÁ v4.1 DONE]** Operatório completo desenhado pela The C-Squad — Solução disruptiva em parsing de governança corporativa/pública.
