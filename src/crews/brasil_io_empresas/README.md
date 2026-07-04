# Brasil.IO Empresas (RF)

**Status:** ⏳ Pendente  
**Fase:** 3 — Motor Forense  
**Tabela destino:** `fornecedores_rf`  
**Portal:** [Receita Federal via Brasil.IO](https://dadosabertos.rfb.gov.br/CNPJ/)  
**Formato:** CSV gigante (~20GB) — DuckDB

## O que extrai

Cadastro de empresas da Receita Federal via Brasil.IO — CNPJ completo

## Dependências

Nenhuma

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
