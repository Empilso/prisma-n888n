# SAPL Genérico — Atividade Legislativa Municipal (Vereadores)

**Status:** 🟡 Piloto validado local (2026-07-21) — NUNCA rodou em escala/VPS
**Fase:** 3 — Motor Forense
**Tabelas destino:** `sapl_instancias`, `sapl_parlamentares`, `sapl_materias`
**Fonte:** API pública REST de cada instância SAPL (`sapl.{município}.{uf}.leg.br/api/`)
**Formato:** JSON (Django REST Framework, sem login, paginado)

## Por que essa crew existe

O vereador é o tipo de candidato mais numeroso do país e, até esta crew,
tinha **zero dado de atuação legislativa** em qualquer fonte do PRISMA 888 —
só a "ficha TSE" (quem é, votos, bens, campanha). O SAPL (Sistema de Apoio ao
Processo Legislativo, programa Interlegis/Senado) é software livre padronizado
usado por centenas de câmaras municipais, cada uma no próprio domínio mas com
a mesma estrutura de API — uma integração cobre potencialmente centenas de
câmaras de uma vez. Ver `.context/AUDITORIA_TEMPLATE_PREFEITO_2026-07-18.md`
e `ROADMAP.md` (priorizado 2026-07-18, nunca implementado até agora).

## O que extrai

- **Cadastro do vereador** (`/api/parlamentares/parlamentar/`): nome completo,
  nome de urna/apelido, e-mail, situação. Sem CPF, sem partido, sem datas de
  mandato nesse endpoint específico.
- **Mandato** (`/api/parlamentares/mandato/`): legislatura, data de início/fim.
- **Filiação partidária** (`/api/parlamentares/filiacao/` + `/api/parlamentares/partido/`):
  partido vigente (filiação sem `data_desfiliacao`, ou a mais recente).
- **Projetos de lei e afins** (`/api/materia/materialegislativa/`): número,
  ano, tipo, ementa, autores (pode ter mais de um), se está em tramitação.

**Não confirmado como disponível de forma padronizada:** presença/falta em
sessão, gastos de gabinete. Não prometer isso nesta fase — variável por
instância, precisa reconhecimento caso a caso.

## Vínculo ao vereador (`politico_id`)

Por nome + `municipio_ibge` (câmara↔município é 1:1, pool de comparação bem
mais preciso que o cruzamento por UF usado em `cgu_emendas_federais`):
match exato primeiro, fuzzy (`rapidfuzz` ≥ 88) como fallback, `None` sem
match — nunca fabrica. `nome_parlamentar` do SAPL tende a já ser o apelido de
urna, então a taxa de match esperada é mais alta que em emendas federais
(nome civil completo), mas isso **só se confirma medindo** (`agent_verify.py`),
nunca assumindo. Medido no piloto: 62% (51 exato + 6 fuzzy de 92).

## Agentes

- **Agent 0** — Descoberta: testa o padrão de domínio
  `sapl.{slug(município)}.{uf}.leg.br` contra a tabela `municipios` inteira
  (5.570 linhas) e grava o resultado em `sapl_instancias`
  (`ativo`/`sem_resposta`/`fora_do_padrao`). Não existe lista pronta e
  confiável de "quais câmaras usam SAPL" — o diretório oficial do Interlegis
  não respondeu de forma estável na pesquisa que originou esta crew.
- **Agent A** — Extrator: pagina os 5 endpoints de cada câmara confirmada
  → bronze (`data/sapl_generico/bronze/{dominio}/{endpoint}.json`).
  Sequencial por domínio, nunca paralelo agressivo (são sites de terceiros).
- **Agent B** — Normalizador: resolve partido, mandato, `politico_id` →
  prata (`data/sapl_generico/prata/{dominio}.json`).
- **Agent C** — Loader: DDL idempotente + UPSERT (`ON CONFLICT (dominio,
  id_sapl) DO UPDATE`, `politico_id` só é sobrescrito se o novo valor não for
  nulo — nunca regride um match já resolvido).
- **Agent Verify** — Quality gate: volume, duplicatas, cobertura Fase 0→1,
  % de match.

## Piloto (2026-07-21, tudo local)

| Etapa | Resultado |
|---|---|
| Agent 0, 30 municípios do PR | 10 confirmados ativos (33%) |
| Agent A, 2 câmaras (Almirante Tamandaré, Alto Paraíso) | 92 parlamentares, 324 matérias coletadas |
| Agent B | 62% de match `politico_id` (51 exato + 6 fuzzy) |
| Agent C, 2 rodadas | idempotente confirmado (mesma contagem) |
| Agent Verify | 6/6 checks passaram |

## Pendente (decisão do usuário: rodar tudo na VPS)

1. **Fase 0 completa** — testar os 5.570 municípios (script já pronto,
   `agent_0_descoberta.py --todos`). Estimativa grosseira pelo piloto: ~33%
   de acerto → pode passar de 1.500 câmaras confirmadas (o piloto foi só 1
   UF, taxa real pode variar bastante entre estados).
2. **Fase 1 em escala** — `agent_a_extrator.py --todos` sobre todas as
   confirmadas. Volume desconhecido até a Fase 0 terminar, mas
   `materialegislativa` sozinha teve 36.747 registros numa única câmara média
   (Santarém) — a soma de centenas de câmaras é potencialmente milhões de
   linhas. **Nunca rodar essa escala no PC** (trava o HD mecânico) — usar
   `rodar_carga.sh sapl_generico agent_0_descoberta.py --todos` e depois
   `rodar_carga.sh sapl_generico agent_a_extrator.py --todos` na VPS.
3. **Backend + frontend** — endpoint `GET /api/sapl/{politico_id}/atividade-legislativa`
   (mesmo padrão de `doe_ba.py`) + entrada no catálogo de fontes
   (`_CATALOGO_FONTES` em `auditoria.py`) + nova tab no dossiê do vereador
   (`cargo-tab-matrix.ts` não tem nenhuma entrada pra isso hoje). Fica pra
   depois que a carga real na VPS confirmar volume e qualidade de match.
