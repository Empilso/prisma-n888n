# Doutrina AIOX: Arsenal de Tools CrewAI

O pacote `crewai-tools` (já injetado na versão 1.8.0 do ecossistema) garante acesso às extensões *plug-and-play* originais da OpenAI e agentes super-equipados. Para elevar a precisão mecânica do nosso Extrator N888N, o Mestre deve solicitar a ativação das seguintes ferramentas oficiais nos Agentes:

## 1. ScrapeWebsiteTool (O Ceifador Visual)
**Para que serve:** Em vez de codarmos lógicas de `requests` ou lutar contra Selenium, essa ferramenta permite que o Agente Scraper (Agente 1) entre num Portal de Transparência dinâmico, contorne bloqueios e leia não apenas HTML, mas o texto da tela renderizada.
* **Ganho Tático:** Precisão absoluta em sites do Governo. O Agente 1 deixa de precisar de Bypass de arquivo caso a rede caia, ele mesmo fura a barreira.

## 2. DirectoryReadTool & FileReadTool 
**Para que serve:** O Agente 1 (Sourcing) tem a meta de ler os milhares de PDFs de Notas Fiscais e Empenhos que caírem na pasta C:\Downloads ou `/bronze`.
* **Ganho Tático:** Resolvemos o problema *"Tenho arquivo limpo / Arquivo Sujo"*. Podemos amarrar o FileReadTool num Agente "Roteador", que olhará a pasta e decidirá: *"Se isso for TXT Sujo, mando pro Llama-3 processar. Se for um JSON do Tribunal, jogo direto para a Camada Ouro"*.

## 3. SerperDevTool (Inteligência Central Google)
**Para que serve:** Dá aos Agentes acesso à rede mundial. 
* **Ganho Tático no Compliance:** Imagine que o Agente 3 (Auditor) vê que Gastaram R$ 40 Mil em "Gráfica José". Se ele usar essa Tool e pesquisar na Receita Federal e ver que a Gráfica tem "Capital Social de 2 Mil reais e Inativa", ele marca Fraude = ALTO Risco na hora. Nenhuma lógica Hard Code ganha disso. Precisão Cirúrgica.

## 4. RAGTool (Knowledge Base)
**Para que serve:** Você alimenta o Agente com todas as Leis e Regimentos da ALBA (TCM, TCE). 
* **Ganho Tático:** Ele só aprova a rubrica se ela estiver 100% de acordo com as Leis de Licitação descritas nos manuais institucionais que você cravou nele. Impede que o modelo crie devaneios morais e siga estritamente a burocracia governamental.
