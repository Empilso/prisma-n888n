# SIGA-BA Emendas Estaduais

**Status:** ⚠️ Implementada para execução financeira; autoria parlamentar ainda indisponível na fonte CKAN

**Fase:** 2 — Dinheiro Indireto  
**Tabela destino:** `emendas_estaduais`  
**Portal:** [SIGA Bahia / SIAFEB](https://www.siga.ba.gov.br)  
**Formato:** CSV ou scraping

## O que extrai

Emendas parlamentares estaduais da Bahia via SIGA/SIAFEB

## Dependências

`politicos`, `municipios`, `fornecedores_rf`

## Limite atual da fonte

A view CKAN oficial publica pagamentos, mas não publica o autor parlamentar.
Por isso `parlamentar_nome` e `politico_id` permanecem `NULL`: nenhuma autoria
pode ser inferida. A publicação por político depende de captura oficial do
Painel BI e aprovação do Agent V.

## Agentes

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata, soma parcelas e preserva `NULL` honesto
- **Agent C** — Loader: Prata → PostgreSQL com chave `numero_emenda + ano_orcamento`
- **Agent V** — Bloqueia valores forjados, atribuição sem autor e chave incorreta
