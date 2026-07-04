# CGU Lista Negra

**Status:** ⏳ Pendente  
**Fase:** 3 — Motor Forense  
**Tabela destino:** `lista_negra_governo`  
**Portal:** [CGU — CEIS + CNEP + CEPIM](https://portaldatransparencia.gov.br/download-de-dados/ceis)  
**Formato:** CSV

## O que extrai

Empresas e pessoas sancionadas — CEIS, CNEP e CEPIM

## Dependências

Nenhuma

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
