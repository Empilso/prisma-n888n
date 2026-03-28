# Crew 00 Zidane (Hub de Parlamentares)

**Objetivo Geral**
A **Crew Zidane** é o motor de Identidade e Enriquecimento do ecossistema N888N. Seu objetivo é criar o **"Golden Record" (Registro de Ouro)** de cada parlamentar, servindo como a fonte única de verdade (`Single Source of Truth`) para todos os outros agentes. Ela resolve a identidade dos deputados cruzando dados da ALBA Legis (API Oficial) com Scraping de biografia e mandatos.

---

## 🏗️ Composição da Crew

A Crew é dividida em dois agentes especializados que operam em cascata:

1. **Zidane-A (O Coletor de IDs):** Localiza os parlamentares e seus identificadores únicos.
2. **Zidane-B (O Biógrafo):** Enriquece os IDs com dados profundos (Bio, Profissão, Proposições).

---

## 📥 Entradas (Inputs)

- **Fonte Primária A:** API Dados Abertos ALBA (`albalegis.nopapercloud.com.br/api/publico/parlamentar`).
- **Fonte Primária B:** Portal Legis (Nopaper Cloud) via Selenium para fallback.
- **Tabela Mestre:** `DEPUTADOS_ATUAIS` (Hardcoded no [Agent 4](../../src/agents/agent_4_prisma_db.py)) para cross-check.

---

## 📤 Saídas (Outputs)

Gera a fundação da camada de **Parlamentares** no DataLake.

- **Hub de IDs:** `data/saida/parlamentares/parlamentares_ids.json` (Mapa mestre de relacionamentos).
- **Perfis Detalhados:** `data/saida/parlamentares/raw/parlamentar_{id}_api.json` (Atributos biográficos).
- **Consolidado (Gold):** `data/saida/parlamentares/gold/` (Em construção).

---

## 🛠️ Tecnologias e Libs

- **Requests:** Consumo da API REST de Dados Abertos (Rápido e Estruturado).
- **Selenium (Headless Chrome):** Fallback robusto para quando a API está instável ou omitindo nomes.
- **BeautifulSoup (LXML):** Parsing do DOM das páginas de perfil do Nopaper Cloud.
- **Regex (`re`):** Extração de IDs de dentro de URLs complexas de proposição/autor.

---

## ⚙️ Fluxo de Processamento (Passo a Passo)

### FASE 1: Zidane-A (Identidade Híbrida)
1. **API First:** Tenta baixar a lista completa de parlamentares ativos via API JSON.
2. **Resgate Selenium:** Se a API falhar ou estiver incompleta, inicia o motor Selenium, navega visualmente pelo portal, extrai os IDs dos cartões de perfil (`parlamentarID` e `autorID`).
3. **Mapeamento Hub:** Consolida os 63 deputados em um único arquivo de índice, garantindo que o `parlamentar_id` seja a chave estrangeira universal.

### FASE 2: Zidane-B (Enriquecimento Profundo)
1. **Iteração Hub:** Lê o arquivo gerado pelo Zidane-A.
2. **Deep Scrape API:** Para cada ID, faz uma chamada de detalhe para buscar:
   - Nome Civil, Data de Nascimento, Profissão, E-mail e Telefone.
3. **Mapeamento de Produção:** Busca o histórico de proposições legislativas atreladas ao `autorID`.
4. **Segmentação:** Salva um arquivo JSON por parlamentar na pasta `raw/`, permitindo atualizações incrementais.

---

## 🆔 O Identificador Único (O "Core" do Hub)

A Crew Zidane gera um par de IDs cruciais:
- **`parlamentar_id`:** Usado para fotos, perfis e comissões.
- **`autor_id`:** Usado para rastrear gastos (Verbas) e produção legislativa.

**A lógica do Hub Central:**
O ecossistema usa o `parlamentar_id` como a âncora principal. O [Agent 4 (Prisma DB)](../agent_4_prisma_db/README_PRISMA.md) usa esses nomes coletados pelo Zidane para fazer o *Fuzzy Matching* na Camada Prata, garantindo que "Adolfo" na verba seja o mesmo "Adolfo" da biografia.

---

## 🛡️ Regras de Negócio e Boas Práticas

- **Prioridade Estruturada:** Sempre prefere a API (Dados Abertos) ao Selenium para evitar flutuações de layout.
- **Persistência Incremental:** Zidane-B não re-processa perfis que já possuem JSON atualizado na pasta `raw/`, economizando banda e tempo.
- **Fidelidade Biográfica:** Mantém o texto original da biografia (`parlamentarDescricao`) sem cortes, para análise posterior via IA (LLM).

---

## 🔗 Integrações na Esteira

- **➡️ Agent 4 (Prisma DB):** Fornece a lista de nomes oficiais para validação de verbas.
- **➡️ UI (Studio):** Alimenta as fotos e perfis biográficos no Dashboard.
- **➡️ Agent Kaká:** Fornece o contexto de "Quem é o Deputado" para análises de risco reputacional.

---

**[CREW ZIDANE DONE]** A inteligência de identidade que impede o projeto de se perder em nomes duplicados ou apelidos parlamentares.
