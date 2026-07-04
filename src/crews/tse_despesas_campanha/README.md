# TSE Despesas de Campanha

**Status:** ⏳ Pendente  
**Fase:** 0 — Hub Central  
**Tabela destino:** `despesas_campanha`  
**Portal:** [TSE — Prestação de Contas Eleitorais](https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais)  
**Formato:** CSV compactado (latin-1)

## O que extrai

Despesas declaradas por candidatos nas prestações de contas eleitorais

## Dependências

`politicos`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
