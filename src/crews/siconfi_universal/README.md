# SICONFI Universal — Execução Fiscal Nacional

**Fase:** 2 — Cobertura Nacional  
**Versão:** v1.0  
**Status:** Implementado (aguardando primeira execução)

---

## Descrição

Pipeline universal que substitui a dependência exclusiva do TCE-SP para o módulo "Execução de Verbas". Cobre **27 estados + 5.570 municípios** consumindo a API SICONFI do Tesouro Nacional.

Três documentos cobertos:

| Documento | Frequência | Anexos | Cobertura v1 |
|---|---|---|---|
| **RREO** (Relatório Resumido Execução Orçamentária) | bimestral (6/ano) | 1-14 | 27 UFs + 27 capitais, 2018-2025 |
| **RGF** (Relatório Gestão Fiscal) | quadrimestral (3/ano) | 1-6 | 27 UFs (Executivo), 2018-2025 |
| **DCA** (Declaração Contas Anuais) | anual | I-C, I-D, I-E | 27 UFs + 5.570 munis, 2018-2024 |

---

## Endpoints API

Base: `https://apidatalake.tesouro.gov.br/ords/siconfi/tt`

```
GET /rreo?an_exercicio=2024&nr_periodo=1&co_tipo_demonstrativo=RREO&id_ente=35
GET /rgf?an_exercicio=2024&nr_periodo=1&co_tipo_demonstrativo=RGF&id_ente=35&co_poder=E
GET /dca/anexo-i-c?an_exercicio=2023&id_ente=3550308
```

Docs oficiais: https://apidatalake.tesouro.gov.br/docs/siconfi/

---

## Tabelas destino (PostgreSQL `prisma_data`)

Criadas automaticamente pelo Agent C (DDL embutido):

- `siconfi_rreo(id, id_ente, ente_tipo, ente_nome, uf, exercicio, periodo, anexo, conta, coluna, valor, raw_hash UNIQUE, dt_carga)`
- `siconfi_dca (id, id_ente, ente_tipo, ente_nome, uf, exercicio,          anexo, conta, coluna, valor, raw_hash UNIQUE, dt_carga)`
- `siconfi_rgf (id, id_ente, ente_tipo, ente_nome, uf, exercicio, periodo, anexo, conta, coluna, valor, raw_hash UNIQUE, dt_carga)`

Índices em `(id_ente, exercicio[, periodo])` e `(uf, exercicio)`.

---

## Agentes

### Agent A — Coletor (`agent_a_coletor.py`)
- API SICONFI -> Bronze JSON por (ente × ano × período × anexo)
- Paralelismo: `ThreadPoolExecutor(max_workers=3)` (default)
- Anti-429: `time.sleep(2)` por thread + `tenacity` (5 tentativas, backoff 2-60s)
- Carrega lista de municípios de `prisma_data.municipios` (fallback: 27 capitais hardcoded)
- Skip se Bronze já existe (`--force` para re-baixar)

**Particionamento Bronze:**
```
data/siconfi_universal/bronze/rreo/2024/rreo_2024_p1_anexo1_uf-SP_bronze.json
data/siconfi_universal/bronze/dca/2023/dca_2023_p0_anexoIC_mun-3550308_bronze.json
```

### Agent B — Normalizador (`agent_b_normalizador.py`)
- Bronze -> Prata padronizado: `id_ente, ente_tipo, ente_nome, uf, exercicio, periodo, anexo, conta, coluna, valor, raw_hash`
- `raw_hash = SHA256(id_ente|exerc|periodo|anexo|conta|coluna|valor_raw)` garante idempotência
- Parser de valor tolerante (BR `1.234,56` / US `1234.56` / `NaN` -> None)
- Rejeita: sem conta OR sem valor numérico válido

### Agent C — Loader (`agent_c_loader.py`)
- Prata -> `siconfi_rreo|dca|rgf` via `INSERT ... ON CONFLICT (raw_hash) DO NOTHING`
- Cria schema se não existir (DDL no topo do arquivo)
- Lotes de 500 com rollback isolado por lote
- Suporta `--dry-run`
- Registra cada execução em `etl_log`

---

## CLI

### Agent A
```bash
python agent_a_coletor.py --documento RREO --ano 2024 --entes-tipo uf
python agent_a_coletor.py --documento RREO --ano 2024 --capitais-only --entes-tipo municipio
python agent_a_coletor.py --documento DCA  --ano 2023 --ufs SP,RJ --entes-tipo todos
python agent_a_coletor.py --documento RGF  --ano 2024 --entes-tipo uf --anexo 1
python agent_a_coletor.py --documento RREO --ano 2024 --entes-tipo municipio --workers 5 --force
```

Flags:
- `--documento {RREO|RGF|DCA}` (obrigatório)
- `--ano YYYY` (obrigatório)
- `--ufs SP,RJ,MG` — UFs separadas por vírgula (default: todas 27)
- `--entes-tipo {uf|municipio|todos}` (default `uf`)
- `--capitais-only` — restringe municípios às 27 capitais
- `--anexo N` — anexo específico (default: todos do documento)
- `--periodo N` — bimestre/quadrimestre específico
- `--workers N` — threads (default 3, MAX recomendado 5)
- `--force` — re-baixa mesmo se Bronze já existir

### Agent B
```bash
python agent_b_normalizador.py --documento RREO --todos
python agent_b_normalizador.py --bronze data/siconfi_universal/bronze/rreo/2024/rreo_2024_p1_anexo1_uf-SP_bronze.json
```

### Agent C
```bash
# Validação primeiro
python agent_c_loader.py --documento RREO --dry-run

# Carga
python agent_c_loader.py --documento RREO --todos
python agent_c_loader.py --todos                       # tudo: RREO + RGF + DCA
```

---

## Variáveis de ambiente

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=prisma_data
export DB_USER=postgres
export DB_PASSWORD=...   # OBRIGATÓRIO em produção
```

---

## Volume esperado

| Cenário | Requests | Bronze (MB) | Registros DB | Tempo |
|---|---:|---:|---:|---:|
| RREO 27 UFs, 1 ano, todos anexos | ~2.300 | ~600 | ~600.000 | ~30 min |
| RREO 27 capitais, 1 ano, todos anexos | ~2.300 | ~300 | ~300.000 | ~30 min |
| RREO 27 UFs + capitais, 2018-2025 | ~37.000 | ~10 GB | ~9 M | ~6 h |
| DCA 27 UFs, anexo I-C, 1 ano | ~27 | ~5 | ~10.000 | ~1 min |
| DCA 5.570 munis, anexo I-C, 1 ano | ~5.570 | ~1 GB | ~2 M | ~3-4 h |
| DCA 5.570 munis, I-C+I-D+I-E, 7 anos | ~117.000 | ~25 GB | ~50 M | ~5-7 dias |
| RGF 27 UFs, 3 quadrimestres, 6 anexos, 7 anos | ~3.400 | ~800 | ~800.000 | ~1 h |

Estimativas conservadoras assumindo 3 workers + sleep(2). Subir `--workers 5` reduz tempo mas aproxima do 429.

---

## Estratégia recomendada de primeira execução

Para começar a habilitar "Execução de Verbas" em outras UFs:

```bash
# 1) UFs primeiro (mais críticas pra governadores) — 30 min
python agent_a_coletor.py --documento RREO --ano 2024 --entes-tipo uf
python agent_b_normalizador.py --documento RREO --todos
python agent_c_loader.py --documento RREO --todos

# 2) 27 capitais (cobre ~30% da população municipal) — 30 min
python agent_a_coletor.py --documento RREO --ano 2024 --capitais-only --entes-tipo municipio
python agent_b_normalizador.py --documento RREO --todos
python agent_c_loader.py --documento RREO --todos

# 3) DCA pra ter cobertura anual de todos os 5.570 munis — overnight
python agent_a_coletor.py --documento DCA --ano 2023 --entes-tipo municipio
python agent_b_normalizador.py --documento DCA --todos
python agent_c_loader.py --documento DCA --todos
```

---

## Pegadinhas conhecidas

- A API SICONFI usa `co_tipo_demonstrativo` com **texto literal** (`"RREO"`, `"RREO Simplificado"`). Municípios usam Simplificado. UFs usam o full.
- DCA não tem `nr_periodo`. Por padronização, gravamos `periodo = 0` na Bronze e Prata (a coluna `periodo` não existe na tabela `siconfi_dca`).
- O nome do anexo no payload da API varia entre `no_anexo` (RREO/RGF) e `anexo` (DCA). O Normalizador padroniza para `meta.anexo`.
- Rate-limit: a API SICONFI não documenta limite oficial, mas observa-se 429 acima de ~30 req/min sustentado. Default conservador: 3 workers × sleep(2) ≈ 90 req/min teóricos, na prática ~60-80.
- Os valores na API SICONFI já vêm como `number` na maioria dos casos, mas alguns endpoints retornam string com vírgula BR. O parser tolera ambos.
- O DDL é executado a cada `agent_c_loader.py --todos` (idempotente via `IF NOT EXISTS`).

---

## Dependências

```
psycopg2-binary
requests
tenacity
tqdm        # opcional, melhora UX
```

Já presentes nos demais crews do n888n-prisma.

---

## Status

- Implementado: Agent A, Agent B, Agent C, manifest, README
- Não rodado: aguardando primeira execução manual / agendamento no scheduler do `n888n-prisma`
