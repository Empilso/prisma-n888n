# DOE-BA — Atos de Pessoal (SRH/ALBA)

**Status:** ✅ Concluído local (2026-07-20) — 951 atos carregados
**Fase:** 3 — Motor Forense
**Tabela destino:** `doe_publicacoes`
**Fonte:** [Diário Oficial da ALBA](https://www.doe.ba.gov.br/alba) — subtema `alba` do
motor de busca público EGBA/IONEWS
**Formato:** JSON (busca full-text, sem login, sem paywall neste endpoint)

## O que extrai

Recon 2026-07-20 descobriu que `doe.ba.gov.br` (portal comercial da EGBA) roda
um motor de busca full-text público sobre Elasticsearch:

```
GET https://dool.egba.ba.gov.br/busca/busca/buscar/query/{pagina}/?1=1&q={termo}&subtheme={subtema}
```

Sem `subtheme`, a busca cobre TODO o Diário Oficial do Executivo (122k+
páginas — fora de escopo). Com `subtheme=alba`, restringe ao **Diário Oficial
próprio da Assembleia Legislativa** (~1.036 páginas com o termo "SRH" —
seção "SUPERINTENDÊNCIA DE RECURSOS HUMANOS — ATOS ADMINISTRATIVOS").

Essa seção publica nomeação/exoneração/designação/dispensa/promoção de cargo
comissionado no formato fixo:

```
ATO Nº. 12.693/2021 - Nomear RAISSA MARINHO BENVINDO, para a função
comissionada de Secretário Parlamentar (Gab. Dep. Ângelo Almeida)
Nível SP-18, a partir de 01/05/2021.
```

O Agent B extrai só o que casa nesse padrão explícito (regra "zero tolerância
a dado errado" — nunca infere nome/data ausente). Quando o ato cita
`(Gab. Dep. FULANO)`, o campo `orgao` grava `"Gabinete Dep. FULANO"`.

## Escopo desta etapa (decisão do usuário, 2026-07-20)

**Sem heurística de nepotismo.** `alerta_nepotismo` sempre grava `false`.
Comparar sobrenome do nomeado com sobrenome de deputados é indício fraco
(homônimo é comum em nomes brasileiros) — fica reservado pra uma fase futura,
só em ambiente de teste, com selo obrigatório "não é prova de parentesco"
antes de qualquer uso em produção (ver protocolo de dado sensível do projeto).

## Vínculo ao deputado

Feito em **runtime no backend Forbes** (`/api/doe-ba/{politico_id}/atos-pessoal`),
não nesta crew — por correspondência de nome entre `orgao` e
`alba_parlamentares.nome_parlamentar`. É melhor esforço (grafia varia:
"Deputado X", "Dep. X Filho", apelido) — o endpoint sempre expõe
`match_metodo` explicando a limitação.

## Rastreabilidade forense

`ato_hash` (data+número do ato+ano+nome+verbo) garante idempotência — re-rodar
a crew nunca duplica linha. `diario_id`/`pagina`/`url_fonte` permitem abrir a
edição original do diário e conferir o ato.

## Agentes

- **Agent A** — Coletor: pagina a busca `subtheme=alba&q=SRH` → bronze (1 JSON/página de resultado)
- **Agent B** — Normalizador: regex extrai atos de pessoal → prata
- **Agent C** — Loader: DDL idempotente (colunas de rastreabilidade + índice único `ato_hash`) → `doe_publicacoes`

## Pendente

- Rodar na VPS (só local até agora)
- Registrar frequência real no Vigia depois de observar cadência de publicação
- Fase futura (só teste): heurística de sobrenome pra sinalizar possível parentesco
