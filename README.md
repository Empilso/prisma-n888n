# PRISMA 888 — Pipeline ETL Backend

Pipeline de extração, transformação e carga de dados forenses de portais governamentais brasileiros para análise de corrupção.

## Estrutura

```
n888n-prisma/
├── src/
│   └── crews/                  # Uma crew por portal
│       ├── ibge_municipios/    ✅ completo
│       └── tse_candidatos/     ✅ completo
├── data/                       # Dados por portal
│   ├── ibge/                   # Bronze, Prata, Rejeitados
│   ├── tse/                    # Bronze, Prata (2006-2024)
│   │   └── raw/                # CSVs originais do TSE
│   └── alba/                   # Prata, Ouro (verbas 2015-2026)
├── sql/
│   └── schema.sql
└── docs/
```

## Padrão de Arquivos

```
data/{portal}/
├── {entidade}_{ano}_{uf}_bronze.json      # Imutável, com SHA256
├── {entidade}_{ano}_{uf}_prata.json       # Normalizado e validado
├── {entidade}_{ano}_{uf}_ouro.json        # Enriquecido
└── {entidade}_{ano}_{uf}_rejeitados.json  # Registros inválidos
```

## Padrão de Crew

Cada portal tem exatamente 3 agentes:

```
src/crews/{portal}/
├── crew_manifest.json       # Metadados da crew
├── agent_a_coletor.py       # Fonte → Bronze
├── agent_b_normalizador.py  # Bronze → Prata
└── agent_c_loader.py        # Prata → PostgreSQL
```

## Execução

```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate

python src/crews/{portal}/agent_a_coletor.py
python src/crews/{portal}/agent_b_normalizador.py
python src/crews/{portal}/agent_c_loader.py        # --dry-run para testar
```

## Banco de Dados

```
host: localhost | porta: 5432 | banco: prisma_data | user: postgres
```

```bash
psql postgresql://postgres:${DB_PASSWORD}@localhost:5432/prisma_data
SELECT * FROM etl_log ORDER BY data_execucao DESC;
```

## Status das Crews

### Fase 0 — Hub Central
| Crew                    | Agent A | Agent B | Agent C | Registros no BD     | Última Atualização |
|-------------------------|---------|---------|---------|---------------------|--------------------|
| ibge_municipios         | ✅      | ✅      | ✅      | 5.571               | 2026-04-06         |
| tse_candidatos          | ✅      | ✅      | ✅      | 802.660 (BA/SP/MG/RJ) | 2026-04-06       |
| tse_receitas_campanha   | ⏳      | ⏳      | ⏳      | —                   | —                  |
| tse_despesas_campanha   | ⏳      | ⏳      | ⏳      | —                   | —                  |
| tse_bens_declarados     | ⏳      | ⏳      | ⏳      | —                   | —                  |
| tse_votos_municipio     | ⏳      | ⏳      | ⏳      | —                   | —                  |

### Fase 1 — Dinheiro Direto
| Crew                    | Agent A | Agent B | Agent C | Registros no BD | Última Atualização |
|-------------------------|---------|---------|---------|-----------------|-------------------|
| alba_verbas_gabinete    | ✅      | ✅      | ✅      | 42.440 (R$ 284M) | 2026-04-07       |
| alba_servidores         | ⏳      | ⏳      | ⏳      | —               | —                 |
| camara_ceap             | ⏳      | ⏳      | ⏳      | —               | —                 |
| camara_votacoes         | ⏳      | ⏳      | ⏳      | —               | —                 |
| senado_ceap             | ⏳      | ⏳      | ⏳      | —               | —                 |
| camara_proposicoes      | ⏳      | ⏳      | ⏳      | —               | —                 |
| camara_discursos        | ⏳      | ⏳      | ⏳      | —               | —                 |

### Fase 2 — Dinheiro Indireto
| Crew                    | Agent A | Agent B | Agent C | Registros no BD |
|-------------------------|---------|---------|---------|-----------------|
| cgu_emendas_federais    | ⏳      | ⏳      | ⏳      | —               |
| siga_ba_emendas         | ⏳      | ⏳      | ⏳      | —               |
| cgu_docs_emendas        | ⏳      | ⏳      | ⏳      | —               |
| transferegov_convenios  | ⏳      | ⏳      | ⏳      | —               |
| seplan_loa_pdf          | ⏳      | ⏳      | ⏳      | —               |

### Fase 3 — Motor Forense
| Crew                    | Agent A | Agent B | Agent C | Registros no BD |
|-------------------------|---------|---------|---------|-----------------|
| cgu_servidores_federais | ⏳      | ⏳      | ⏳      | —               |
| brasil_io_empresas      | ⏳      | ⏳      | ⏳      | —               |
| brasil_io_socios        | ⏳      | ⏳      | ⏳      | —               |
| cgu_lista_negra         | ⏳      | ⏳      | ⏳      | —               |
| cnj_processos           | ⏳      | ⏳      | ⏳      | —               |
| pncp_contratos          | ⏳      | ⏳      | ⏳      | —               |
| doe_ba                  | ⏳      | ⏳      | ⏳      | —               |

### Fase 4 — Auditoria Final
| Crew                    | Agent A | Agent B | Agent C | Registros no BD |
|-------------------------|---------|---------|---------|-----------------|
| tcm_ba_contratos        | ⏳      | ⏳      | ⏳      | —               |
| tce_ba_contratos        | ⏳      | ⏳      | ⏳      | —               |
