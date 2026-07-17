# TSE Despesas de Campanha

**Status:** ✅ Implementada — carga nacional em validação  
**Fase:** 0 — Hub Central  
**Tabela destino:** `despesas_campanha`  
**Portal:** [TSE — Prestação de Contas Eleitorais](https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais)  
**Formato:** CSV compactado (latin-1)

## O que extrai

Despesas declaradas por candidatos nas prestações de contas eleitorais

## Dependências

`politicos`

## Pipeline

- **Agent A** — reutiliza os ZIPs da crew de receitas e extrai o CSV original por UF para Bronze `.csv.gz`.
- **Agent B** — normaliza em streaming para Prata `.jsonl.gz`; rejeitados mantêm linha e motivo.
- **Agent C** — upsert por SHA-256 da linha, resolve identidade somente por `SQ_CANDIDATO + ano` e calcula sanção vigente na data da despesa.
- **Agent V** — valida volume, identidade, valores, duplicatas e avaliação de sanções.
- **Agent P** — publica somente lotes cujo arquivo Prata ainda corresponde ao hash aprovado pelo Agent V.

Até a aprovação, `verificacao_status=PENDENTE` e a API Forbes não exibe o lote.

Anos cobertos: 2014, 2016, 2018, 2020, 2022 e 2024 — 27 UFs.

```bash
set -a; . /caminho/PRISMA888FORBES/backend/.env; set +a
python agent_a_coletor.py --ano 2022 --ufs BA
python agent_b_normalizador.py --bronze data/tse_despesas_campanha/bronze/despesas_2022_BA_bronze.csv.gz
python agent_c_loader.py --prata data/tse_despesas_campanha/prata/despesas_2022_BA_prata.jsonl.gz
python agent_v_verificador.py --ano 2022 --uf BA
```
