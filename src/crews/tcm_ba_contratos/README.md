# TCM-BA Contratos Municipais

**Status:** ⏳ Pendente  
**Fase:** 4 — Auditoria Final  
**Tabela destino:** `contratos_municipios`  
**Portal:** [TCM-BA — Portal de Consultas](https://www.tcm.ba.gov.br/consultas/)  
**Formato:** Scraping ou CSV exportado

## O que extrai

Contratos municipais fiscalizados pelo Tribunal de Contas dos Municípios da Bahia

## Dependências

`municipios`, `fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
