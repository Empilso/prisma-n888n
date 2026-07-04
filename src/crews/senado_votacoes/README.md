# Crew: senado_votacoes — Votações Nominais do Senado Federal

**Status:** implementado (v1.0)
**Fase:** 2 — Atividade Legislativa
**Tabelas destino:** `senado_votacoes` (cabeçalho) + `senado_votos_nominais` (votos individuais)
**Portal:** [Senado Federal — Dados Abertos](https://legis.senado.leg.br/dadosabertos/docs/)

---

## O que extrai

Votações nominais do **plenário do Senado Federal**:

- **Cabeçalho** da votação: data, descrição, matéria associada, resultado
  (APROVADA / REJEITADA / PREJUDICADA), totais SIM/NÃO/ABSTENÇÃO.
- **Voto individual** de cada um dos ~81 senadores presentes
  (SIM / NÃO / OBSTRUÇÃO / ABSTENÇÃO / PRESIDENTE / AUSENTE).

Cada voto carrega `politico_id` resolvido contra a tabela `politicos`, permitindo
cruzar **histórico de voto × dossiê do senador** no radar.

---

## Período e volume

| Período | Legislatura | Volume estimado |
|---------|-------------|-----------------|
| 2015–2018 | 55ª | ~3.500 votações |
| 2019–2022 | 56ª | ~4.000 votações |
| 2023–2026 | 57ª | ~4.500 votações |
| **Total** | — | **~12.000 votações** |

Multiplicando por ~81 senadores: **~970.000 registros** em `senado_votos_nominais`.

---

## API utilizada

Base: `https://legis.senado.leg.br/dadosabertos`

| Endpoint | Uso |
|----------|-----|
| `GET /plenario/lista/votacao/{ANO}` | Lista todas as votações nominais do ano |
| `GET /votacao/{CODIGO}` | Detalhes + votos por senador |

**Formato:** API tende a entregar XML; forçamos `Accept: application/json`.
Quando o servidor responde XML, fazemos parse via `xmltodict`. Estruturas
testadas: `ListaVotacoes → Votacoes → Votacao[]` e
`VotacaoMateria → Votacao → Votos → VotoParlamentar[]`.

---

## Agentes

### Agent A — Coletor (`agent_a_coletor.py`)

- Lista votações do ano e itera cada uma chamando `/votacao/{codigo}`.
- Retry com `tenacity` (4 tentativas, backoff exponencial).
- Sleep de 50ms entre chamadas.
- Salva Bronze por ano com hash SHA256.

**Execução:**
```bash
python src/crews/senado_votacoes/agent_a_coletor.py --ano 2024
python src/crews/senado_votacoes/agent_a_coletor.py --legislatura 57
python src/crews/senado_votacoes/agent_a_coletor.py --todos
python src/crews/senado_votacoes/agent_a_coletor.py --ano 2026 --force
```

**Saída:** `data/senado_votacoes/bronze/senado_vot_{ANO}_bronze.json`

---

### Agent B — Normalizador (`agent_b_normalizador.py`)

- Extrai cabeçalho + lista de votos.
- Canoniza `SiglaVoto`/`DescricaoVoto` em valores fixos:
  `SIM`, `NAO`, `OBSTRUCAO`, `ABSTENCAO`, `PRESIDENTE`, `AUSENTE`, `NAO_VOTOU`.
- **Resolve `politico_id` por senador** via:
  1. `politicos.id_legislativo_senado` = `CodigoParlamentar`.
  2. Fallback: nome+UF+partido (fuzzy).
- Calcula totais a partir dos votos se a API não devolver os campos `TotalVotosSim/Nao/Abstencao`.
- `raw_hash` para auditoria.

**Execução:**
```bash
python src/crews/senado_votacoes/agent_b_normalizador.py --todos
python src/crews/senado_votacoes/agent_b_normalizador.py --bronze data/senado_votacoes/bronze/senado_vot_2024_bronze.json
```

**Saída:**
- `data/senado_votacoes/prata/senado_vot_{ANO}_prata.json`
- `data/senado_votacoes/rejeitados/senado_vot_{ANO}_rejeitados.json`

---

### Agent C — Loader (`agent_c_loader.py`)

- Cria tabelas e índices se não existirem.
- Para cada votação, dentro de uma transação:
  1. `UPSERT` no cabeçalho (`senado_votacoes`).
  2. `DELETE` + `INSERT ... ON CONFLICT DO UPDATE` em `senado_votos_nominais`
     — garante consistência se a API revisar uma votação.
- Registra execução em `etl_log`.

**Execução:**
```bash
python src/crews/senado_votacoes/agent_c_loader.py --dry-run
python src/crews/senado_votacoes/agent_c_loader.py --todos
```

---

## Schema das tabelas destino

```sql
CREATE TABLE IF NOT EXISTS senado_votacoes (
    codigo BIGINT PRIMARY KEY,
    data DATE,
    descricao TEXT,
    materia_codigo BIGINT,
    resultado TEXT,
    total_sim INT, total_nao INT, total_abstencao INT,
    sessao_codigo BIGINT,
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS senado_votos_nominais (
    votacao_codigo BIGINT NOT NULL REFERENCES senado_votacoes(codigo) ON DELETE CASCADE,
    senador_codigo INT NOT NULL,
    politico_id TEXT,
    nome TEXT,
    sigla_partido TEXT,
    sigla_uf TEXT,
    tipo_voto TEXT,
    PRIMARY KEY (votacao_codigo, senador_codigo)
);
CREATE INDEX IF NOT EXISTS idx_senado_votos_pol
    ON senado_votos_nominais(politico_id) WHERE politico_id IS NOT NULL;
```

`senado_votacoes.materia_codigo` é **FK lógica** para `senado_proposicoes.codigo`
(não declarada formalmente porque as duas crews podem ser carregadas em ordens
diferentes; o join é feito em query).

---

## Cruzamento `politico_id`

Igual ao da crew `senado_proposicoes`: prioriza `politicos.id_legislativo_senado`
(match exato com `CodigoParlamentar` do Senado) e cai para fuzzy `nome+UF+partido`
quando a coluna não existe ou não tem o senador.

Para a primeira carga, a taxa de resolução fuzzy tende a ficar entre 70% e 90% —
recomenda-se criar uma crew dedicada para popular `id_legislativo_senado` e elevar
para 95%+.

---

## Pipeline completo (primeira carga)

```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma

# 1. Coleta (20–40 min)
python src/crews/senado_votacoes/agent_a_coletor.py --todos

# 2. Normalização (~3 min)
python src/crews/senado_votacoes/agent_b_normalizador.py --todos

# 3. Validação
python src/crews/senado_votacoes/agent_c_loader.py --todos --dry-run

# 4. Carga (5–10 min)
python src/crews/senado_votacoes/agent_c_loader.py --todos
```

## Atualização semanal

```bash
python src/crews/senado_votacoes/agent_a_coletor.py --ano 2026 --force
python src/crews/senado_votacoes/agent_b_normalizador.py --bronze data/senado_votacoes/bronze/senado_vot_2026_bronze.json
python src/crews/senado_votacoes/agent_c_loader.py --prata data/senado_votacoes/prata/senado_vot_2026_prata.json
```

---

## Dependências

- `politicos` — resolução de `politico_id` por senador
- `senado_proposicoes` — FK lógica via `materia_codigo` para joins
- `xmltodict`, `tenacity`, `requests`, `psycopg2`, `tqdm`
