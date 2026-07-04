# Transferegov Convenios

Status: em construcao (smoke 2024 OK em 2026-06-20)
Fase: 2 - Dinheiro Indireto
Tabela destino: convenios_federais
Portal: TransfereGov API (transferenciasespeciais)
Endpoint base: https://api.transferegov.dth.api.gov.br/transferenciasespeciais/
Doc: https://docs.api.transferegov.gestao.gov.br/transferenciasespeciais/
Formato: JSON PostgREST (?ano_plano_acao=eq.2024&limit=1000&offset=0)

## O que extrai

- plano_acao_especial: 1 linha por plano (convenio Emenda Pix individual). Tem cnpj_beneficiario, uf, nome_parlamentar, ano, valor_custeio, valor_investimento, modalidade, situacao.
- programa_especial: catalogo para enriquecer orgao_concedente.

## Pipeline

1. Agent A (coletor) - pagina plano_acao_especial por ano e baixa programa_especial. Salva em data/transferegov_convenios/bronze/.
2. Agent B (normalizador) - limpa CNPJ, mapeia municipio IBGE por (nome_beneficiario, uf), enriquece orgao_concedente via id_programa, vincula politico_id pelo nome_parlamentar (cargo dep/senador), valor_repasse = custeio + investimento, vigencia_inicio extraida do prefixo DDMMYYYY do codigo_plano_acao.
3. Agent C (loader) - UPSERT em convenios_federais por nr_convenio. Loga em etl_log.

## Smoke test 2026-06-20

50 convenios 2024 -> bronze -> prata -> upsert.

    python agent_a_coletor.py --ano 2024 --limit 50
    python agent_b_normalizador.py --bronze planos_acao_especial_2024_smoke50_bronze.json
    python agent_c_loader.py --prata planos_acao_especial_2024_smoke50_prata.json

## Dependencias

municipios, politicos

## Schema

Ver PRISMA888FORBES/migrations/2026-06-20_convenios_federais.sql.
