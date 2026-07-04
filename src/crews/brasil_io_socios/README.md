# Brasil.IO Sócios (RF)

**Status:** ⏳ Pendente  
**Fase:** 3 — Motor Forense  
**Tabela destino:** `socios_rf`  
**Portal:** [Receita Federal via Brasil.IO](https://dadosabertos.rfb.gov.br/CNPJ/)  
**Formato:** CSV gigante — DuckDB

## O que extrai

Quadro societário das empresas da Receita Federal via Brasil.IO

## Dependências

`fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
