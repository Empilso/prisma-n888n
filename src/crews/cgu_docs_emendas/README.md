# CGU Documentos de Emendas

**Status:** ⏳ Pendente  
**Fase:** 2 — Dinheiro Indireto  
**Tabela destino:** `emendas_documentos`  
**Portal:** [Portal da Transparência — CGU](https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares)  
**Formato:** CSV

## O que extrai

Documentos e notas de empenho vinculados às emendas parlamentares

## Dependências

`emendas_federais`, `fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
