# Crew: senado_proposicoes — Proposições do Senado Federal

**Status:** implementado (v1.0)
**Fase:** 2 — Atividade Legislativa
**Tabela destino:** `senado_proposicoes` (prisma_data)
**Portal:** [Senado Federal — Dados Abertos](https://legis.senado.leg.br/dadosabertos/docs/)

---

## O que extrai

Proposições legislativas autuadas no Senado Federal (Câmara Alta), incluindo:

| Sigla | Tipo |
|-------|------|
| PLS / PL | Projeto de Lei |
| PEC | Proposta de Emenda à Constituição |
| PRS | Projeto de Resolução do Senado |
| PDS | Projeto de Decreto Legislativo |
| MPV | Medida Provisória |
| PLP | Projeto de Lei Complementar |
| PLN | Projeto de Lei do Congresso Nacional |
| PDL | Projeto de Decreto Legislativo |
| PRN | Projeto de Resolução do Congresso |

Para cada proposição extrai: metadados (ementa, data, situação), autoria com
**`politico_id` resolvido para o sistema PRISMA** e detalhes completos por autor
(código parlamentar do Senado, partido, UF).

---

## Período

| Período | Legislatura |
|---------|-------------|
| 2015–2018 | 55ª |
| 2019–2022 | 56ª |
| 2023–2026 | 57ª |

**Volume estimado:** 3.000–5.000 proposições/ano × 12 anos = ~40.000–55.000 registros.

---

## API utilizada

Base: `https://legis.senado.leg.br/dadosabertos`

| Endpoint | Uso |
|----------|-----|
| `GET /materia/pesquisa/lista?ano=YYYY&sigla=SIGLA` | Lista do ano por sigla |
| `GET /materia/{codigo}` | Detalhes completos |
| `GET /materia/{codigo}/autoria` | Autores (cruzar com `politicos`) |

**Formato:** XML por padrão; forçamos `Accept: application/json` (alguns endpoints
honram, outros não). Fallback automático com `xmltodict` quando a resposta vem XML.

---

## Agentes

### Agent A — Coletor (`agent_a_coletor.py`)

- Itera siglas × anos → chama `/materia/pesquisa/lista`.
- Para cada material listado, busca `detalhe` + `autoria`.
- Retry com `tenacity` (4 tentativas, backoff exponencial).
- Sleep de 50ms entre chamadas (gentileza com a API).
- Salva **Bronze JSON** com hash SHA256 e meta de extração.

**Execução:**
```bash
# Ano específico
python src/crews/senado_proposicoes/agent_a_coletor.py --ano 2024

# Legislatura inteira
python src/crews/senado_proposicoes/agent_a_coletor.py --legislatura 57

# Tudo (2015–2026) — primeira carga
python src/crews/senado_proposicoes/agent_a_coletor.py --todos

# Re-coleta forçada
python src/crews/senado_proposicoes/agent_a_coletor.py --ano 2026 --force
```

**Saída:** `data/senado_proposicoes/bronze/senado_prop_{ANO}_bronze.json`

---

### Agent B — Normalizador (`agent_b_normalizador.py`)

- Extrai metadados estruturados de Bronze.
- **Resolve `politico_id`** via dois caminhos:
  1. `politicos.id_legislativo_senado` = `CodigoParlamentar` (match exato).
  2. Fallback fuzzy: `nome_normalizado + UF + partido`.
- Computa `raw_hash` (SHA256 do payload bruto) para auditoria.
- Rejeita registros sem `codigo` ou `ano`.

**Cache em memória:** o resolver carrega tudo da tabela `politicos` na primeira
chamada (uma consulta por execução).

**Execução:**
```bash
python src/crews/senado_proposicoes/agent_b_normalizador.py --todos
python src/crews/senado_proposicoes/agent_b_normalizador.py --bronze data/senado_proposicoes/bronze/senado_prop_2024_bronze.json
```

**Saída:**
- `data/senado_proposicoes/prata/senado_prop_{ANO}_prata.json`
- `data/senado_proposicoes/rejeitados/senado_prop_{ANO}_rejeitados.json`

---

### Agent C — Loader (`agent_c_loader.py`)

- Cria tabela e índices se não existirem (idempotente).
- Upsert em lotes de 500 via `ON CONFLICT (codigo) DO UPDATE` — re-execução é segura.
- Refresca `ementa`, `situacao_atual`, `autores_*` (mudam ao longo da tramitação).
- Registra execução em `etl_log` (se a tabela existir).

**Execução:**
```bash
python src/crews/senado_proposicoes/agent_c_loader.py --dry-run
python src/crews/senado_proposicoes/agent_c_loader.py --todos
```

---

## Schema da tabela destino

```sql
CREATE TABLE IF NOT EXISTS senado_proposicoes (
    codigo BIGINT PRIMARY KEY,                  -- CodigoMateria
    tipo TEXT NOT NULL,                         -- PLS, PEC, PRS, PDS, MPV, etc
    numero INT,
    ano INT NOT NULL,
    ementa TEXT,
    data_apresentacao DATE,
    autoria TEXT,                               -- texto bruto "Senador Fulano (PT/BA); ..."
    autores_politico_ids TEXT[],                -- politico_ids resolvidos
    autores_detalhes JSONB,                     -- [{codigo_parlamentar, nome, partido, uf, politico_id}]
    situacao_atual TEXT,
    casa TEXT DEFAULT 'SF',
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_senado_prop_ano     ON senado_proposicoes(ano);
CREATE INDEX IF NOT EXISTS idx_senado_prop_autores ON senado_proposicoes USING gin(autores_politico_ids);
```

---

## Cruzamento `politico_id` — observações

A coluna `politicos.id_legislativo_senado` **pode não existir** no schema atual.
Se ausente, o Agent B usa apenas o fallback `nome + UF + partido`. Recomenda-se
adicionar essa coluna e popular via crew dedicada de senadores ativos para elevar
a taxa de match acima de 95%.

---

## Pipeline completo (primeira carga)

```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma

# 1. Coleta (30–60 min)
python src/crews/senado_proposicoes/agent_a_coletor.py --todos

# 2. Normalização (~5 min)
python src/crews/senado_proposicoes/agent_b_normalizador.py --todos

# 3. Validação
python src/crews/senado_proposicoes/agent_c_loader.py --todos --dry-run

# 4. Carga
python src/crews/senado_proposicoes/agent_c_loader.py --todos
```

## Atualização semanal

```bash
python src/crews/senado_proposicoes/agent_a_coletor.py --ano 2026 --force
python src/crews/senado_proposicoes/agent_b_normalizador.py --bronze data/senado_proposicoes/bronze/senado_prop_2026_bronze.json
python src/crews/senado_proposicoes/agent_c_loader.py --prata data/senado_proposicoes/prata/senado_prop_2026_prata.json
```

---

## Dependências

- `politicos` — para resolver `politico_id` dos autores
- `xmltodict` — fallback XML→dict
- `tenacity`, `requests`, `psycopg2`, `tqdm`
