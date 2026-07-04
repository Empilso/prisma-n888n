# SIGA-BA Emendas Estaduais

**Status:** ⏳ Pendente  
**Fase:** 2 — Dinheiro Indireto  
**Tabela destino:** `emendas_estaduais`  
**Portal:** [SIGA Bahia / SIAFEB](https://www.siga.ba.gov.br)  
**Formato:** CSV ou scraping

## O que extrai

Emendas parlamentares estaduais da Bahia via SIGA/SIAFEB

## Dependências

`politicos`, `municipios`, `fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
