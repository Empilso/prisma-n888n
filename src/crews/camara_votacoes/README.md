# Crew: camara_votacoes — Votações Nominais Câmara Federal

**Status:** ✅ Implementado
**Fase:** 1 — Dinheiro Direto
**Tabelas destino:** `camara_votacoes`, `camara_votos_nominais` (prisma_data)
**Portal:** [Câmara Federal — Dados Abertos](https://dadosabertos.camara.leg.br)
**Formato origem:** JSON via API REST v2

---

## O que extrai

Todas as **votações nominais em plenário** da Câmara dos Deputados — uma linha por
deputado por votação — com o tipo de voto (Sim / Não / Obstrução / Abstenção /
Art. 17), além das orientações de bancada e metadados da votação.

Cobertura padrão: **legislaturas 55, 56, 57** (fev/2015 → jan/2027, limitado a hoje).

Endpoints utilizados:
- `GET /votacoes`                  → lista paginada (filtros `dataInicio`, `dataFim`, `idLegislatura`)
- `GET /votacoes/{id}/votos`       → votos nominais (1 registro por deputado por votação)
- `GET /votacoes/{id}/orientacoes` → orientações de bancada (snapshot bronze)

---

## Estratégia de paginação

A API tem limite prático ~10 000 itens por consulta. Por isso o coletor itera
**mês a mês**, montando arquivos Bronze independentes — facilita re-processo
seletivo e mantém cada arquivo em tamanho gerenciável.

Para cada janela mensal:
1. Lista votações (segue `rel="next"` até esgotar).
2. Para cada votação, baixa votos + orientações.
3. Pausa de 150 ms entre chamadas (educado com a API; evita 429).

---

## Resolução `politico_id`

Crítico para cruzar voto com nosso ID PRISMA. Estratégia em três camadas:

1. **`id_legislativo_camara`** — se `politicos` tiver a coluna populada (qualquer um destes
   nomes é aceito: `id_legislativo_camara`, `id_camara`, `id_deputado_camara`,
   `id_parlamentar_camara`), é o caminho mais confiável.
2. **Match exato por (nome, UF, partido)** — normalizando `nome_urna`.
3. **Fuzzy `rapidfuzz.token_sort_ratio` ≥ 88** dentro do mesmo UF.

Filtro do índice: candidatos a Deputado Federal nas eleições 2014, 2018, 2022, 2024.
Quando nenhuma camada bate, `politico_id` fica `NULL` e o voto é gravado mesmo assim
(o `deputado_id_camara` permite resolução posterior).

Stats por arquivo Prata ficam em `meta.match_politico`.

---

## Agentes

### Agent A — Coletor (`agent_a_coletor.py`)

API → Bronze JSON, **mês a mês**.

```bash
# Uma legislatura inteira
python src/crews/camara_votacoes/agent_a_coletor.py --legislatura 57

# Um ano específico (descobre legislatura)
python src/crews/camara_votacoes/agent_a_coletor.py --ano 2024

# Todas (55, 56, 57)
python src/crews/camara_votacoes/agent_a_coletor.py --todos

# Re-baixar mesmo se Bronze existe
python src/crews/camara_votacoes/agent_a_coletor.py --legislatura 57 --force
```

Retry: `tenacity` com 5 tentativas, backoff exponencial (2-30s).
**Saída:** `data/camara_votacoes/bronze/votacoes_{LEG}_{ANO}_{MES}_bronze.json`

### Agent B — Normalizador (`agent_b_normalizador.py`)

Bronze → Prata. Resolve `politico_id`, normaliza tipos, agrega contagens
`sim / nao / outros / abstencoes` no nível da votação.

```bash
python src/crews/camara_votacoes/agent_b_normalizador.py --todos
python src/crews/camara_votacoes/agent_b_normalizador.py --bronze data/camara_votacoes/bronze/votacoes_57_2024_05_bronze.json
```

Regras de rejeição:

| Tipo            | Motivo                          |
| --------------- | ------------------------------- |
| Votação         | `id` ausente                    |
| Votação         | `dataHoraRegistro` inválida     |
| Voto nominal    | `deputado.id` ausente           |
| Voto nominal    | `tipoVoto` vazio                |

**Saída:**
- `data/camara_votacoes/prata/votacoes_{LEG}_{ANO}_{MES}_prata.json`
- `data/camara_votacoes/rejeitados/votacoes_{LEG}_{ANO}_{MES}_rejeitados.json`

### Agent C — Loader (`agent_c_loader.py`)

Prata → PostgreSQL. Cria tabelas (`IF NOT EXISTS`) na primeira execução.

- Votações: `INSERT ... ON CONFLICT (id) DO UPDATE` em campos voláteis
  (contagens, descrição, aprovação).
- Votos nominais: `COPY FROM STDIN (CSV)` para TEMP TABLE, depois
  `INSERT ... SELECT ... ON CONFLICT (votacao_id, deputado_id_camara) DO NOTHING` —
  rápido em massa e idempotente.

```bash
# Validar sem gravar
python src/crews/camara_votacoes/agent_c_loader.py --dry-run

# Um arquivo
python src/crews/camara_votacoes/agent_c_loader.py --prata data/camara_votacoes/prata/votacoes_57_2024_05_prata.json

# Tudo
python src/crews/camara_votacoes/agent_c_loader.py --todos
```

Conexão Postgres via env vars (com fallback dev):
`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

Cada execução registra em `etl_log` (portal, fase, status, contagens, duração).

---

## Pipeline completo (primeira carga — legislaturas 55, 56, 57)

```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma

# 1) Coleta (longa — várias horas: ~10-15k votações com paginação por mês)
python src/crews/camara_votacoes/agent_a_coletor.py --todos

# 2) Normalização
python src/crews/camara_votacoes/agent_b_normalizador.py --todos

# 3) Dry-run (sanity check)
python src/crews/camara_votacoes/agent_c_loader.py --todos --dry-run

# 4) Carga real
python src/crews/camara_votacoes/agent_c_loader.py --todos
```

---

## Schemas (criados pelo Agent C)

```sql
CREATE TABLE camara_votacoes (
    id                  TEXT PRIMARY KEY,           -- id da Câmara
    legislatura         INT NOT NULL,
    data                DATE,
    data_hora_registro  TIMESTAMPTZ,
    sigla_orgao         TEXT,
    proposicao_id       BIGINT,                     -- FK lógica → camara_proposicoes(id)
    descricao           TEXT,
    aprovacao           INT,                        -- 0 / 1
    sim                 INT,
    nao                 INT,
    outros              INT,
    abstencoes          INT,
    raw_hash            TEXT UNIQUE,
    dt_carga            TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE camara_votos_nominais (
    votacao_id          TEXT NOT NULL REFERENCES camara_votacoes(id) ON DELETE CASCADE,
    deputado_id_camara  INT NOT NULL,               -- id parlamentar Câmara
    politico_id         TEXT,                       -- nosso ID PRISMA (NULL se sem match)
    nome                TEXT,
    sigla_partido       TEXT,
    sigla_uf            TEXT,
    tipo_voto           TEXT,                       -- 'Sim' | 'Não' | 'Obstrução' | 'Abstenção' | 'Art. 17'
    data_hora_voto      TIMESTAMPTZ,
    PRIMARY KEY (votacao_id, deputado_id_camara)
);
```

Índices:
- `idx_votacoes_leg_data (legislatura, data)`
- `idx_votacoes_proposicao (proposicao_id) WHERE proposicao_id IS NOT NULL`
- `idx_votos_nominais_pol (politico_id) WHERE politico_id IS NOT NULL`
- `idx_votos_nominais_dep (deputado_id_camara)`

---

## Dependências

- **`politicos`** — para resolver `politico_id`. Acrescente coluna
  `id_legislativo_camara` (INT) à `politicos` para ter resolução 100% determinística;
  sem ela o fallback fuzzy ainda funciona (≥ 88 score).
- **`camara_proposicoes`** — FK lógica via `proposicao_id`. Sem ela, drill-down
  para o conteúdo da matéria fica indisponível.

---

## Volume esperado

| Legislatura     | Período               | Estimativa votações | Estimativa votos nominais |
| --------------- | --------------------- | ------------------- | ------------------------- |
| 55ª             | 2015-02 → 2019-01     | ~3 500              | ~1 600 000                |
| 56ª             | 2019-02 → 2023-01     | ~3 800              | ~1 800 000                |
| 57ª (em curso)  | 2023-02 → hoje        | ~3 000+ (cresce)    | ~1 400 000+               |
| **Total**       | 2015-02 → 2026        | **~10 000+**        | **~4 800 000+**           |

Observação: nem toda votação tem votos nominais — votações simbólicas devolvem
404 em `/votos`, tratadas como `[]`.
