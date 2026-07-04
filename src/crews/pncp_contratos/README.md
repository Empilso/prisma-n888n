# PNCP Contratos Públicos

**Status:** ⏳ Pendente  
**Fase:** 3 — Motor Forense  
**Tabela destino:** `contratos_pncp`  
**Portal:** [PNCP — Portal Nacional de Contratações Públicas](https://pncp.gov.br/api/pncp/v1/contratos)  
**Formato:** JSON paginado API REST

## O que extrai

Contratos públicos registrados no Portal Nacional de Contratações Públicas

## Dependências

`fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
