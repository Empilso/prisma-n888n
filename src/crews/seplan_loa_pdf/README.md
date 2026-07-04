# SEPLAN-BA LOA PDF

**Status:** ⏳ Pendente  
**Fase:** 2 — Dinheiro Indireto  
**Tabela destino:** `loa_emendas_pdf`  
**Portal:** [SEPLAN-BA / DOE-BA — LOA em PDF](https://www.doe.ba.gov.br)  
**Formato:** PDF → PyMuPDF

## O que extrai

Lei Orçamentária Anual da Bahia com emendas parlamentares extraídas de PDF

## Dependências

`politicos`, `municipios`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
