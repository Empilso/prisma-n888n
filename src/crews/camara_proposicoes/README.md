# Crew: camara_proposicoes — Proposições Legislativas Câmara Federal

**Status:** ✅ Implementada (v1.0)
**Fase:** 1 — Dinheiro Direto
**Tabelas destino:** `camara_proposicoes_wide` (canônica) + `camara_proposicoes` (legada, mantida por compat)
**Portal:** [Câmara Federal — Dados Abertos](https://dadosabertos.camara.leg.br/swagger/api.html)
**Formato:** JSON API REST (`/api/v2/proposicoes`)

---

## O que extrai

Todas as proposições legislativas federais (PL, PEC, MP, PLP, PRC) das legislaturas **55ª, 56ª e 57ª** (2015 → 2026). Cada registro contém:

- Identificação (id, tipo, número, ano)
- Texto (`ementa` + `ementa_detalhada`)
- Tramitação (situação atual, descrição, órgão atual, data do último ato)
- `keywords` extraídas
- **Lista de autores** com `idDeputado` da Câmara + cruzamento contra `politicos` (PRISMA `politico_id`)

---

## Fonte dos dados

```
GET https://dadosabertos.camara.leg.br/api/v2/proposicoes?siglaTipo={TIPO}&ano={ANO}&itens=100&pagina={N}
GET https://dadosabertos.camara.leg.br/api/v2/proposicoes/{id}
GET https://dadosabertos.camara.leg.br/api/v2/proposicoes/{id}/autores
```

A coleta itera **tipo × ano** dentro de cada legislatura e enriquece cada proposição com detalhe + autores. Rate-limit moderado (429 → backoff exponencial).

---

## Schema das tabelas

### `camara_proposicoes_wide` (canônica — criada por esta crew)

```sql
CREATE TABLE IF NOT EXISTS camara_proposicoes_wide (
    id                          BIGINT PRIMARY KEY,
    tipo                        TEXT NOT NULL,            -- PL, PEC, MP, PLP, PRC
    numero                      INTEGER NOT NULL,
    ano                         INTEGER NOT NULL,
    ementa                      TEXT,
    ementa_detalhada            TEXT,
    data_apresentacao           DATE,
    status_situacao             TEXT,
    status_descricao_tramitacao TEXT,
    status_data                 TIMESTAMPTZ,
    uri_orgao_atual             TEXT,
    sigla_orgao_atual           TEXT,
    keywords                    TEXT[],
    autores                     JSONB,                    -- [{id_camara, nome, partido, uf, tipo, politico_id_prisma, ...}]
    autores_politico_ids        TEXT[],                   -- denormalizado p/ busca rápida
    raw_hash                    TEXT UNIQUE,
    dt_carga                    TIMESTAMPTZ DEFAULT now()
);
-- índices: ano, tipo, GIN(autores_politico_ids), GIN(keywords)
```

### `camara_proposicoes` (legada — mantida por compat)

A tabela legada já existia no `prisma_data` com **724.806 registros** e PK `(id, politico_id)` (uma linha por autor). O Loader **não derruba** essa tabela: faz `ALTER TABLE ADD COLUMN IF NOT EXISTS` para acrescentar as colunas novas (status, keywords, ementa detalhada, raw_hash, dt_carga) e popula em paralelo com a wide.

---

## Cruzamento Autor → `politico_id` PRISMA

A tabela `politicos` **não** tem `id_legislativo_camara`. Estratégia em 2 níveis (no Agent C):

1. **Match exato** — `LOWER(nome_urna) = LOWER(autor.nome)` AND `uf` AND `sigla_partido`
2. **Fallback fuzzy** — `similarity(LOWER(nome_completo), LOWER(autor.nome)) >= 0.85` (pg_trgm), filtrando por UF do autor

Quando nenhum match casa, `politico_id_prisma` fica `NULL` dentro do JSONB de `autores` (a autoria fica registrada por nome). Esses autores **não** geram linha na tabela legada (que exige `politico_id NOT NULL`).

> Para ativar o fallback fuzzy, garantir extensão pg_trgm: `CREATE EXTENSION IF NOT EXISTS pg_trgm;`

---

## Agentes

### Agent A — Coletor (`agent_a_coletor.py`)
- Itera tipo × ano dentro da legislatura.
- Para cada proposição lista resumo + busca detalhe + autores (3 chamadas).
- Persiste Bronze JSON com hash SHA256 dos records.
- Backoff exponencial para 429 (tenacity).

```bash
# Legislatura 57 (atual)
python src/crews/camara_proposicoes/agent_a_coletor.py --legislatura 57

# Todas (55, 56, 57)
python src/crews/camara_proposicoes/agent_a_coletor.py --todos

# Re-baixa mesmo se Bronze já existe
python src/crews/camara_proposicoes/agent_a_coletor.py --legislatura 57 --force

# Restringir tipos
python src/crews/camara_proposicoes/agent_a_coletor.py --legislatura 57 --tipos PL,PEC
```

**Saída:** `data/camara_proposicoes/bronze/proposicoes_{LEG}_bronze.json`

---

### Agent B — Normalizador (`agent_b_normalizador.py`)
- Lê Bronze, achata `_resumo + _detalhe + _autores`.
- Computa `raw_hash` (SHA256 de `id|tipo|numero|ano|ementa[:200]`) — usado para dedup.
- Rejeita registros sem `id`, sem `tipo/numero/ano` ou sem `ementa`.
- Normaliza datas (DATE) e `status_data` (TIMESTAMPTZ ISO).

```bash
python src/crews/camara_proposicoes/agent_b_normalizador.py --todos
python src/crews/camara_proposicoes/agent_b_normalizador.py --bronze data/camara_proposicoes/bronze/proposicoes_57_bronze.json
```

**Saída:**
- `data/camara_proposicoes/prata/proposicoes_{LEG}_prata.json`
- `data/camara_proposicoes/rejeitados/proposicoes_{LEG}_rejeitados.json`

---

### Agent C — Loader (`agent_c_loader.py`)
- DDL idempotente: cria `camara_proposicoes_wide` + patcha legada.
- Resolve autores contra `politicos` (cache em memória).
- UPSERT lote 500 em ambas as tabelas.
- Registra execução em `etl_log` (best-effort).

```bash
# Dry-run (valida sem gravar)
python src/crews/camara_proposicoes/agent_c_loader.py --dry-run

# Um arquivo específico
python src/crews/camara_proposicoes/agent_c_loader.py --prata data/camara_proposicoes/prata/proposicoes_57_prata.json

# Carga completa
python src/crews/camara_proposicoes/agent_c_loader.py --todos
```

---

## Pipeline completo

```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma

# 1. Coleta (longa — várias horas via API por rate-limit)
python src/crews/camara_proposicoes/agent_a_coletor.py --todos

# 2. Normaliza
python src/crews/camara_proposicoes/agent_b_normalizador.py --todos

# 3. Dry-run
python src/crews/camara_proposicoes/agent_c_loader.py --todos --dry-run

# 4. Carga
python src/crews/camara_proposicoes/agent_c_loader.py --todos
```

---

## Dependências

- `politicos` (tabela base) — para resolver `politico_id` via nome+UF+partido / fuzzy
- Extensão `pg_trgm` no Postgres (opcional, mas melhora cobertura do match fuzzy)
- Variáveis de ambiente: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

---

## Volume estimado

| Legislatura | Anos | Proposições estimadas |
|:-:|:-:|--:|
| 55 | 2015–2018 |  ~80.000 |
| 56 | 2019–2022 |  ~90.000 |
| 57 | 2023–2026 |  ~80.000 (parcial) |
| **Total** | | **~250.000** |

> Cobertura PL+PEC+MP+PLP+PRC. Cada proposição faz **3 chamadas** à API (lista, detalhe, autores), com 40ms de cortesia entre requests — total ~30s/100 props.

---

## Observações importantes

- **Tabela legada não é apagada.** A crew evolui o schema via `ALTER TABLE ADD COLUMN IF NOT EXISTS`. Consumidores antigos continuam funcionando.
- **Banco vazio:** o Loader só cria a wide; a parte legada é pulada se a tabela não existir.
- **Re-execução:** ambos os UPSERTs são idempotentes — pode rodar quantas vezes quiser.
- **Atualização semanal:** rodar Agent A com `--legislatura 57 --force` re-baixa só o ano corrente e o ETL atualiza via UPSERT.
