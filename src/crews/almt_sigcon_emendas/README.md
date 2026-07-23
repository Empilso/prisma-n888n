# SIGCON Emendas Estaduais MT

**Status:** 🟡 Piloto validado local (2026-07-23) — 1 ano (2024) carregado, NUNCA rodou em escala/VPS

**Fase:** 2 — Dinheiro Indireto
**Tabelas destino:** `emendas_estaduais` (agregado, `uf='MT'`) + `emendas_estaduais_aplicacoes` (granular)
**Portal:** [SIGCON — SEPLAN/SEFAZ MT](https://transp.sigcon.seplan.mt.gov.br)
**Formato:** HTML (scraping autenticado por sessão PHP)

## Por que essa crew existe

Investigação disparada por uma pergunta real sobre o dossiê do vice-governador
de MT Otaviano Pivetta (deputado estadual MT em 2006, mandato 2007-2010):
por que ele não tem emendas nem verba de gabinete no radar? CEAP é exclusivo
da Câmara Federal (não aplica — ele nunca foi deputado federal). Emendas
estaduais, porém, tinham uma lacuna real: `emendas_estaduais` só cobria BA,
e BA é **órfã** (CKAN só publica pagamento, sem autor — ver
`siga_ba_emendas/README.md`). MT nunca foi investigado.

## O que extrai

Diferente da Bahia, o SIGCON de MT tem vínculo autor↔pagamento **real e
funcional**: cada convênio (tipo "Repasse") pode ter uma sub-tabela
"Nm.Emenda / Parlamentar / Val.Utilizada Emenda" — uma emenda pode
financiar mais de um convênio, e um convênio pode ser financiado por mais
de uma emenda de mais de um deputado (split real, confirmado nos dados).

Por convênio: concedente (órgão estadual), proponente (geralmente
"PREFEITURA MUNICIPAL DE X"), objeto, processo, nº do convênio, valor
total, vigência. Por emenda aplicada: nº da emenda (na fonte, por
parlamentar), nome do parlamentar, valor utilizado daquela emenda
especificamente naquele convênio.

## Achado técnico: numeração de emenda é por parlamentar, não global

Bug real encontrado e corrigido no piloto: "Nm.Emenda" do SIGCON reinicia a
numeração por deputado — dois parlamentares podem ter "emenda 46" no mesmo
ano (medido: 25 colisões reais em 2024). A PK original de
`emendas_estaduais` — `(uf, numero_emenda, ano_orcamento)` — não distinguia
isso: emendas de deputados diferentes colidiam na mesma chave e uma
sobrescrevia a outra silenciosamente no upsert.

Fix (`migrations/2026-07-23_emendas_estaduais_numero_por_parlamentar.sql`):
`numero_emenda` (a chave) passa a ser um valor composto
`{numero_origem}/{slug_do_parlamentar}`; o número como publicado na fonte
fica preservado em `numero_emenda_origem`. O slug usa o **nome** do
parlamentar (não `politico_id`) — precisa ficar estável mesmo se o match
de `politico_id` mudar numa recarga futura, senão a mesma emenda vira uma
linha nova em vez de atualizar a existente.

## Duas camadas de tabela (mesmo padrão de `emendas_federais_pagamentos`)

`emendas_estaduais` sozinha não aguenta 1 emenda financiando N convênios
sem perder informação (município, objeto, convênio específico). Por isso:

- **`emendas_estaduais`** — 1 linha por emenda (agregado, soma
  `valor_utilizado` de todas as aplicações). `municipio_ibge`/`objeto`
  ficam `NULL` quando a emenda tem mais de 1 aplicação (não fabricar um
  "representante" quando a fonte não garante 1:1).
- **`emendas_estaduais_aplicacoes`** (nova, migration
  `2026-07-23_emendas_estaduais_aplicacoes.sql`) — 1 linha por
  (emenda, convênio): granularidade real da fonte, com município
  beneficiado, objeto e valor daquela aplicação específica.

## Cobertura confirmada (sondagem manual antes de escrever código)

- Filtro por ano (`ano_ass`) funciona de verdade: 2009→977 convênios,
  2018→346, 2026(padrão)→949.
- Filtro por parlamentar (`par_id`) funciona de verdade — testado Júlio
  Campos: 2022→0, 2024→36, 2025→43, todos-anos→97.
- `par_id` só existe de 1 a 39 — o vínculo parlamentar↔convênio **não
  alcança deputados de legislaturas antigas**. Otaviano Pivetta (dep.
  estadual MT só em 2006-2010) não está no dropdown — a crew NÃO resolve
  o caso que a motivou, mas resolve deputados de ~2015 em diante (a medir
  de verdade com `--todos`, nunca assumir).
- Dicionário de Dados oficial (CSV) do portal **não documenta**
  "Parlamentar"/"Emenda" como campo exportável — só existem na tela de
  busca. Por isso é scraping de HTML, não consumo de CSV/API.

## Vínculo ao deputado (`politico_id`)

Nome do parlamentar (texto livre do SIGCON) → `politico_id`, match exato
ou fuzzy (rapidfuzz ≥ 90) contra `politicos` filtrado por `uf='MT' AND
cargo='DEPUTADO ESTADUAL'` (pool de ~1.270 candidaturas distintas, todas
as legislaturas). Sem match → `None`, nunca fabricar. Medido no piloto
(2024): 88,1% de match (95,7% excluindo "Lideranças Partidárias"/"Comissão
de Fiscalização", que não são pessoa física).

## Agentes

- **Agent A** — Extrator: sessão PHP (`PHPSESSID`) + scraping por ano
  (`pag_tela=500`) → Bronze JSON. Regex tolerante ao HTML legado/inconsistente
  do SIGCON.
- **Agent B** — Normalizador: Bronze → Prata (aplicações + agregado),
  resolve `politico_id` e `municipio_ibge` (proponente "PREFEITURA
  MUNICIPAL DE X" → `municipios` uf=MT).
- **Agent C** — Loader: Prata → as duas tabelas via UPSERT.
- **Agent Verify** — 10 checks: volume, anos cobertos, duplicata de PK,
  valor pago, atribuição só com autor real, % match `politico_id`, soma de
  aplicações bate com o agregado (guarda de regressão do bug de colisão),
  parlamentares distintos, FK de município só dentro de MT.

## Piloto (2026-07-23, local, ano 2024 apenas)

| Etapa | Resultado |
|---|---|
| Agent A, ano 2024 | 1.329 convênios (3 páginas de 500) |
| Agent B | 798 aplicações, 192 emendas agregadas, 88,1% match `politico_id` |
| Agent C | 0 erros, R$ 235,4M total pago |
| Agent Verify `--strict` | 9/10 PASS (só falha `ANOS_COBERTOS`, esperado com 1 ano só) |

## Pendente

1. **`--todos` (2007-2026) na VPS** — nunca rodar escala no PC (mesma regra
   do `sapl_generico`). `rodar_carga.sh almt_sigcon_emendas agent_a_extrator.py --todos`
   depois `agent_b_normalizador.py --todos` depois `agent_c_loader.py --todos`.
2. **Medir cobertura histórica real** — confirmar a partir de que ano o
   vínculo parlamentar realmente existe na fonte (suspeita: ~2015+, não
   2007+).
3. **Backend + frontend** — endpoint espelhando `/api/emendas/federais/{politico_id}`,
   entrada no Catálogo de Fontes (`_CATALOGO_FONTES` em `auditoria.py`), e
   plugar em `EmendasFederaisTab.tsx`/nova tab pro cargo DEPUTADO ESTADUAL
   em `cargo-tab-matrix.ts`. Fica pra depois da carga real confirmar volume.
