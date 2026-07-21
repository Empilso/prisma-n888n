# CGU Emendas Federais

**Status:** ✅ Implementada (2026-07-20)
**Fase:** 2 — Dinheiro Indireto
**Tabela destino:** `emendas_federais`
**Portal:** ZIP único, sem token — [EmendasParlamentares.zip](https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares/EmendasParlamentares.zip)
**Formato:** ZIP com 3 CSVs (histórico completo 2014-2026)

## Contexto

A tabela `emendas_federais` já tinha 76.290 registros (2015-2026) carregados por um
processo ad-hoc nunca versionado — sem migration, sem crew rastreável. Esta crew
substitui esse processo por algo documentado, idempotente e integrado ao Vigia,
e amplia a cobertura para 2014 (confirmado nesta sessão: o portal não tem 2013
disponível, ao contrário do que uma fonte secundária sugeria).

## O que extrai

Emendas parlamentares federais (Deputado Federal + Senador): autor, localidade,
função/subfunção orçamentária, valores empenhado/liquidado/pago/restos a pagar,
e o favorecido de maior valor recebido (agregado do CSV `PorFavorecido`).

## Dependências

`politicos` (resolução de `politico_id` por nome+UF), `municipios` (FK `municipio_ibge`)

## Agentes

- **Agent A** (`agent_a_extrator.py`) — baixa o ZIP único, parseia os 2 CSVs
  relevantes (`EmendasParlamentares.csv` + `EmendasParlamentares_PorFavorecido.csv`),
  particiona por ano (`Ano da Emenda` / prefixo de `codigo_emenda`) → bronze JSON.
- **Agent B** (`agent_b_normalizador.py`) — resolve `politico_id` (nome+UF, fallback
  fuzzy rapidfuzz ≥88), agrega `cnpj_favorecido` por maior valor recebido, mapeia
  campos → prata JSON com métricas de cobertura.
- **Agent C** (`agent_c_loader.py`) — UPSERT por `codigo_emenda` (PK natural),
  `COALESCE` em campos resolvidos (nunca regride match já feito), nunca sobrescreve
  `status_lneg` já promovido a OK/MATCH por matcher externo.
- **Agent V** (`agent_verify.py`) — quality gate: volume, duplicatas, % de match
  não regrediu vs. baseline (93%/50%/27.5%, medido 2026-07-20), cross-check com
  `emendas_federais_pagamentos`.

## Execução

```bash
python agent_a_extrator.py --ano 2014      # ano que faltava
python agent_b_normalizador.py --ano 2014
python agent_c_loader.py --dry-run --ano 2014
python agent_c_loader.py --ano 2014
python agent_verify.py

# Depois de validado, migrar o histórico completo do processo ad-hoc pro rastreável:
python agent_a_extrator.py --todos
python agent_b_normalizador.py --todos
python agent_c_loader.py --dry-run --todos
python agent_c_loader.py --todos
python agent_verify.py --strict
```

Sempre rodar na VPS via `rodar_carga.sh` — nunca no PC de desenvolvimento.
