# CGU Emendas Federais

**Status:** ⏳ Pendente  
**Fase:** 2 — Dinheiro Indireto  
**Tabela destino:** `emendas_federais`  
**Portal:** [Portal da Transparência — CGU](https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares)  
**Formato:** CSV anual

## O que extrai

Emendas parlamentares federais com beneficiários e valores pagos

## Dependências

`politicos`, `municipios`, `fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
