# DOE-BA Diário Oficial

**Status:** ⏳ Pendente  
**Fase:** 3 — Motor Forense  
**Tabela destino:** `doe_publicacoes`  
**Portal:** [Diário Oficial do Estado da Bahia](https://www.doe.ba.gov.br)  
**Formato:** Scraping + PDF

## O que extrai

Publicações do Diário Oficial do Estado da Bahia para mineração de dados

## Dependências

Nenhuma

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
