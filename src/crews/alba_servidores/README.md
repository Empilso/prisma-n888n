# ALBA Servidores

**Status:** ⏳ Pendente  
**Fase:** 1 — Dinheiro Direto  
**Tabela destino:** `alba_servidores`  
**Portal:** [ALBA — Portal de Transparência](https://transparencia.alba.ba.gov.br)  
**Formato:** CSV ou scraping

## O que extrai

Servidores e funcionários da Assembleia Legislativa da Bahia

## Dependências

`politicos`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
