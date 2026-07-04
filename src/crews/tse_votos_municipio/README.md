# TSE Votos por Município

**Status:** ⏳ Pendente  
**Fase:** 0 — Hub Central  
**Tabela destino:** `votos_municipio`  
**Portal:** [TSE — Resultados Eleitorais](https://dadosabertos.tse.jus.br/dataset/resultados-2024)  
**Formato:** CSV compactado (latin-1)

## O que extrai

Resultados eleitorais agregados por município e candidato

## Dependências

`politicos`, `municipios`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
