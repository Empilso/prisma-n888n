# TSE Bens Declarados

**Status:** ⏳ Pendente  
**Fase:** 0 — Hub Central  
**Tabela destino:** `bens_declarados`  
**Portal:** [TSE — Bens de Candidatos](https://dadosabertos.tse.jus.br/dataset/candidatos)  
**Formato:** CSV compactado (latin-1)

## O que extrai

Bens declarados por candidatos ao TSE no momento da candidatura

## Dependências

`politicos`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
