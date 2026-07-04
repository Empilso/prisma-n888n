# Estrutura de Dados - PRISMA 888

## Padrão de Arquivos

Todos os portais seguem o mesmo padrão de nomenclatura e organização:

### Nomenclatura

```
{entidade}_{ano}_{uf}_{camada}.json
```

Exemplos:
- `municipios_prata.json` (sem ano/UF quando é base única)
- `candidatos_2024_BA_bronze.json`
- `receitas_2022_BA_prata.json`
- `despesas_2024_ouro.json`

### Camadas

1. **Bronze** (Imutável)
   - Dados brutos da fonte
   - Hash SHA256 para cada registro
   - Nunca é modificado após criação
   - Serve como auditoria

2. **Prata** (Normalizado)
   - Campos normalizados
   - Validações aplicadas
   - Enriquecimento com dados auxiliares
   - Registros inválidos vão para `_rejeitados.json`

3. **Ouro** (Enriquecido)
   - Cruzamento entre portais
   - Análises agregadas
   - Dados prontos para consumo

### Estrutura de Pastas

```
data/
├── ibge/
│   ├── municipios_original.json
│   ├── municipios_bronze.json
│   ├── municipios_prata.json
│   └── municipios_rejeitados.json
│
├── CONSULTA_CAND/
│   ├── candidatos_2024_BA_bronze.json
│   ├── candidatos_2024_BA_prata.json
│   ├── candidatos_2024_BA_ouro.json
│   └── candidatos_2024_BA_rejeitados.json
│
└── {portal}/
    └── {entidade}_{ano}_{uf}_{camada}.json
```

## Metadados

Cada arquivo JSON contém metadados no início:

```json
{
  "meta": {
    "fonte": "TSE",
    "entidade": "candidatos",
    "ano": 2024,
    "uf": "BA",
    "camada": "bronze",
    "data_coleta": "2026-04-06T01:10:00",
    "total_registros": 35209,
    "hash_algoritmo": "SHA256"
  },
  "dados": [...]
}
```

## Crews por Portal

Cada portal tem sua própria crew com 3 agentes:

```
src/crews/{portal}/
├── crew_manifest.json      # Metadados da crew
├── agent_a_coletor.py      # Fonte → Bronze
├── agent_b_normalizador.py # Bronze → Prata
└── agent_c_loader.py       # Prata → PostgreSQL
```

## Fluxo de Dados

```
Fonte Original
    ↓
Agent A (Coletor)
    ↓
Bronze (data/{portal}/)
    ↓
Agent B (Normalizador)
    ↓
Prata (data/{portal}/)
    ↓
Agent C (Loader)
    ↓
PostgreSQL (prisma_data)
```
