# Câmara Discursos

**Status:** ⏳ Pendente  
**Fase:** 1 — Dinheiro Direto  
**Tabela destino:** `discursos_federais`  
**Portal:** [Câmara Federal — Dados Abertos](https://dadosabertos.camara.leg.br)  
**Formato:** JSON API REST

## O que extrai

Discursos e pronunciamentos dos deputados federais

## Dependências

`politicos`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
