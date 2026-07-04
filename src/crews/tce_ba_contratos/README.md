# TCE-BA Contratos Estaduais

**Status:** ⏳ Pendente  
**Fase:** 4 — Auditoria Final  
**Tabela destino:** `contratos_estaduais`  
**Portal:** [TCE-BA / Transparência BA](https://www.transparencia.ba.gov.br)  
**Formato:** Portal web ou scraping

## O que extrai

Contratos estaduais fiscalizados pelo Tribunal de Contas do Estado da Bahia

## Dependências

`fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
