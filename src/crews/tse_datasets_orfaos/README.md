# tse_datasets_orfaos

Carrega 4 datasets do TSE Dados Abertos que nunca tiveram crew nem tabela de
destino: **Informações Complementares**, **Redes Sociais**, **Coligações**,
**Vagas**. Criados em 2026-08-18, achados ao verificar `candidatos-2026`.

## Tabelas (migration `migrations/2026-08-18_tse_datasets_orfaos.sql`)
- `tse_candidatos_complementar` — situação de cassação, julgamento, prestação
  de contas, reeleição, quilombola/indígena. Chave: `(ano_eleicao, sq_candidato)`.
- `tse_candidatos_redes_sociais` — URLs declaradas. Chave: `(ano_eleicao, sq_candidato, url)`.
- `tse_coligacoes` — composição por coligação×cargo (não por partido — o CSV
  bruto do TSE tem 1 linha por partido dentro da coligação; a composição
  completa já vem inteira no campo `composicao_coligacao`, então uma linha
  por coligação×cargo é a granularidade certa, sem perder dado).
  Chave: `(ano_eleicao, sq_coligacao, uf, ue, cargo)`.
- `tse_vagas` — nº de vagas por cargo/UE. Chave: `(ano_eleicao, uf, ue, cargo)`.

## Como rodar
```bash
# 1. baixar+extrair os 4 ZIPs em <stage>/extraido/{info_complementar,rede_social,coligacao,vagas}_{ano}/
#    URLs: cdn.tse.jus.br/estatistica/sead/odsele/{consulta_cand_complementar,
#    rede_social_candidato,consulta_coligacao,consulta_vagas}/*_{ano}.zip
# 2. rodar o loader (idempotente, ON CONFLICT DO NOTHING):
DB_PASSWORD=*** python3 loader.py <stage_dir> <ano>
```

## Frequência da fonte
Igual ao dataset `candidatos-{ano}` do mesmo ciclo: **diária** durante o
período de registro de candidaturas (confirmado no portal TSE em 2026-08-18).
`motivo_cassacao` normalmente fica em 0 linhas até a eleição acontecer.

## Verificado em 2026-08-18 (eleição geral 2026)
20.580 complementar · 47.754 redes sociais (dedup por URL) · 1.945 coligações
(dedup por partido, granularidade coligação×cargo) · 189 vagas.
