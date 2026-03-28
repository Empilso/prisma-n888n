# Agent 2 – Bebeto (O Purificador Prata)

**Objetivo Geral**
O **Agent 2 (Bebeto)** é a inteligência de transformação e higienização (ETL) da esteira N888N. Ele tem como objetivo consumir o amontoado de dados brutos (Camada Bronze), eliminar ruídos, remover duplicatas, padronizar nomes de deputados e faturas, resolvendo anomalias e criando a **Camada Prata** (Silver Layer) limpa, padronizada e unificada por um hash irreversível de rastreio (`prisma_id`).

---

## 📥 Entradas (Inputs)

O Bebeto reage ativamente à geração de novos arquivos pelo [Agent 1 (Romário)](../agent_1_romario/README_ALBA_VERBAS.md).

- **Arquivo Principal:** `data/saida/bronze/alba_YYYY_bronze.json`
- **Parâmetros de Execução:** Normalmente engatilhado pela pipeline global para cada `ano` raspado.

---

## 📤 Saídas (Outputs)

Gera um Datalake intermediário de alta confiabilidade, isento de duplicidades estruturais.

- **Arquivo Principal:** `data/saida/prata/alba_YYYY_prata.json`
- **Tabela de De-duplicação:** As chaves de hash protegem a integridade do arquivo. Reduz o volume do Bronze eliminando notas fiscais fantasmas (links clonados por falha do portal ALBA).

---

## 🛠️ Tecnologias e Bibliotecas

- **Hashlib (MD5):** Geração de chaves robustas (`prisma_id`) cruzando {deputado + CNPJ + mes/ano + nf + valor} para garantir idempotência.
- **Regex (`re`):** Limpeza pesada de tabulações (`\t`), quebras de linha múltiplas e normalização do formato comercial do CNPJ.
- **JSON e OS/Sys:** Manipulação no nível de SO.
- **Orientação a Objetos:** Módulo instanciado sob a classe estrita `PurificadorBebeto v2.2`.

---

## ⚙️ Fluxo de Processamento (Passo a Passo)

1. **Ingestão Bronze:**
   O Bebeto lê em memória o arquivo massivo do Romário contendo os detalhes brutos da tabela e das PDFs.

2. **Geração do `prisma_id` (Deduplicação Forense):**
   Cria um identificador forense único combinando:
   `[Nome_Deputado_Raw] + [Categoria_Limpa] + [Competencia] + [CNPJ_Fornecedor] + [Valor_Detonado]`.
   Se o hash resultante já existir na memória do Bebeto, o registro é descartado sumariamente como duplicata nativa da ALBA.

3. **Ciclo de Normalização de Texto (`normalizar_texto`):**
   - Extrai espaços múltiplos gerados pelas falhas do servidor PHP da ALBA.
   - Força o padrão Título (`Title Case`) em nomes de parlamentares para evitar que "JOSÉ SILVA" e "José silva" sejam considerados deputados diferentes depois.
   - Força CAIXA ALTA (`UPPER`) nos nomes das categorias e dos fornecedores.

4. **Tratamento Matemático Financeiro (`clean_valor_br`):**
   - Transita qualquer valor mal formatado (vírgulas trocadas, valores N/A, strings corrompidas) e garante a entrega rigorosa de um tipo `Float` asséptico à nuvem (Camada Prata exige Tipagem Forte).

5. **Higienização de URLs relativas:**
   Muitas vezes, a ALBA cadastra uma URL morta como `/fserver/:anexo:NFE-123.pdf` em vez da URL oficial. O Bebeto verifica a anomalia e injeta transparentemente a raiz `https://www.al.ba.gov.br/` concatenando-a de volta em um novo campo universal batizado de `url_pdf_nf`.

6. **Score de Qualidade (`qualidade_score`):**
   Atribui uma medalha de confiabilidade original àquela linha [0.0 até 1.0]. Linhas sem PDF diminuem o score, linhas com dados anônimos derrubam o score, facilitando as revisões heurísticas do **Agent 3 (Águia)** depois.

7. **Escrita Silver:**
   Guarda o JSON lapidado com timestamp UTM de higienização.

---

## 🛡️ Regras de Negócio e Boas Práticas (Camada Prata)

- **Idempotência Rigorosa:** Se o Bebeto processar a base de 2022 mil vezes, a Camada Prata vai produzir exatamente os mesmos 3.474 registros. Sempre com a mesma `id`.
- **Rastreabilidade (Lineage):** Mantém os dados crus (`link_pdf_nf_raw`, `numero_nf_recibo_raw`) preservando a forense do erro mesmo depois de tentar consertá-lo. As tags em `flags` marcam as auto-correções (ex: `["pdf_url_relativa_corrigida"]`).
- **Data Pruning:** Se linhas completamente inúteis ou corrompidas de metadados forem injetadas, Bebeto atua sumariamente com *Drop*.

---

## 🔗 Integrações na Esteira

O Bebeto atua como o **Portal de Triagem** da arquitetura:

- **⬅️ Consumidor de:** Agent 1 (Romário / Bronze)
- **➡️ Pai Alimentador de:** Agent Kaká v4.1 Enterprise. Todas as automações e lógicas forenses de PDF usam única e ativamente a coluna `url_pdf_nf` corrigida do Bebeto para evitar Timeouts de 404 em documentos zumbis.
- **➡️ Pai Alimentador de:** Agent 3 (Águia) e Agent 4 (Prisma DB).

---

**[AGENT 2 DONE]** O filtro renal da plataforma Prisma. Responsável pela estabilidade algorítmica de toda IA acoplada a posteriori.
