# Crew: camara_ceap — CEAP Câmara Federal

**Status:** ✅ Implementada  
**Fase:** 1 — Dinheiro Direto  
**Tabela destino:** `camara_verbas_ceap` (prisma_data)  
**Portal:** [Câmara Federal — Gastos Parlamentares](https://www.camara.leg.br/transparencia/gastos-parlamentares)  
**Formato origem:** CSV nacional por ano, separador `;`, encoding `latin-1`

---

## O que extrai

A **Cota para Exercício da Atividade Parlamentar (CEAP)** é o gasto com cota de gabinete de **todos os 513 deputados federais** do Brasil. Inclui passagens aéreas, combustível, refeições, hospedagem, consultorias, divulgação de atividade parlamentar, etc.

Cada linha representa **um gasto de um deputado com um fornecedor** em uma data específica.

---

## Período

| Período | Legislatura | Observação |
|---------|-------------|------------|
| 2015–2018 | 55ª | Formato CSV pode ter variações de colunas |
| 2019–2022 | 56ª | Formato estabilizado (colunas camelCase) |
| 2023–2025 | 57ª | Legislatura atual |

**Total: 11 anos** → estimativa de 3–8 milhões de registros

---

## Fonte dos dados

URL padrão do ZIP anual:
```
https://www.camara.leg.br/cotas/Ano-{ANO}.csv.zip
```

Exemplo: `https://www.camara.leg.br/cotas/Ano-2024.csv.zip`

Cada ZIP contém um único arquivo CSV nacional com todos os deputados.
Tamanho típico: 20–80 MB por ZIP (csv descompactado: 80–300 MB/ano)

---

## Agentes

### Agent A — Coletor (`agent_a_coletor.py`)
**O que faz:**
- Faz download do ZIP anual direto do portal da Câmara
- Extrai o CSV de dentro do ZIP
- Detecta encoding automaticamente (UTF-8 ou latin-1)
- Salva os dados brutos como Bronze JSON com hash SHA256

**Quando rodar:**
- Uma vez por ano para anos passados (idempotente — pula se Bronze já existe)
- Mensalmente para o ano corrente (use `--force`)

**Execução:**
```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma

# Ano específico
python src/crews/camara_ceap/agent_a_coletor.py --ano 2024

# Todos os anos (2015–2025) — primeira carga completa
python src/crews/camara_ceap/agent_a_coletor.py --todos

# Forçar re-download (ex: atualizar ano corrente)
python src/crews/camara_ceap/agent_a_coletor.py --ano 2025 --force
```

**Saída:** `data/camara_ceap/bronze/ceap_{ANO}_bronze.json`

---

### Agent B — Normalizador (`agent_b_normalizador.py`)
**O que faz:**
- Lê Bronze e mapeia colunas para o schema de `camara_verbas_ceap`
- Trata variações de nomes de colunas entre 2015 e 2025 (via COL_MAP)
- Computa `politico_id` = SHA256(CPF do parlamentar) — igual ao padrão `politicos`
- Computa `id_documento`: usa `ideDocumento` da Câmara, ou SHA256 de campos-chave
- Formata `competencia` como `YYYY-MM`
- Rejeita registros sem CPF válido, sem valor, ou com data inválida

**Regras de rejeição:**
| Motivo | Ação |
|--------|------|
| CPF do parlamentar ausente | Rejeitado (sem como vincular ao politico) |
| valor_liquido ausente/negativo | Rejeitado |
| data_emissao inválida | Rejeitado |

**Execução:**
```bash
python src/crews/camara_ceap/agent_b_normalizador.py --todos
python src/crews/camara_ceap/agent_b_normalizador.py --bronze data/camara_ceap/bronze/ceap_2024_bronze.json
```

**Saída:**
- `data/camara_ceap/prata/ceap_{ANO}_prata.json`
- `data/camara_ceap/rejeitados/ceap_{ANO}_rejeitados.json`

---

### Agent C — Loader (`agent_c_loader.py`)
**O que faz:**
- Lê Prata e insere em lotes de 500 na tabela `camara_verbas_ceap`
- `ON CONFLICT (id_documento) DO NOTHING` — idempotente, seguro re-executar
- Registra execução em `etl_log` com total de registros, tempo e status
- `--dry-run` valida sem gravar nenhum dado

**Execução:**
```bash
# Teste sem gravar
python src/crews/camara_ceap/agent_c_loader.py --dry-run

# Carregar um ano
python src/crews/camara_ceap/agent_c_loader.py --prata data/camara_ceap/prata/ceap_2024_prata.json

# Carregar tudo (primeira carga completa)
python src/crews/camara_ceap/agent_c_loader.py --todos
```

---

## Pipeline completo (primeira carga — 2015 a 2025)

```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma

# Etapa 1: Download de todos os anos (~30–60 min, depende da internet)
python src/crews/camara_ceap/agent_a_coletor.py --todos

# Etapa 2: Normalização (~5–15 min)
python src/crews/camara_ceap/agent_b_normalizador.py --todos

# Etapa 3: Dry-run para validar
python src/crews/camara_ceap/agent_c_loader.py --todos --dry-run

# Etapa 4: Carga real
python src/crews/camara_ceap/agent_c_loader.py --todos
```

---

## Atualização mensal (manutenção)

O ano corrente tem dados novos todo mês. Para atualizar:

```bash
# Re-baixa apenas o ano atual
python src/crews/camara_ceap/agent_a_coletor.py --ano 2025 --force

# Re-normaliza
python src/crews/camara_ceap/agent_b_normalizador.py --bronze data/camara_ceap/bronze/ceap_2025_bronze.json

# Carrega (ON CONFLICT ignora o que já existe)
python src/crews/camara_ceap/agent_c_loader.py --prata data/camara_ceap/prata/ceap_2025_prata.json
```

---

## Schema da tabela destino

```sql
CREATE TABLE camara_verbas_ceap (
    id_documento    TEXT PRIMARY KEY,   -- ideDocumento da Câmara ou hash calculado
    politico_id     TEXT,               -- SHA256(CPF) — FK para politicos
    cnpj_fornecedor TEXT,               -- CNPJ/CPF do fornecedor (digits only)
    nome_fornecedor TEXT,
    tipo_despesa    TEXT,               -- ex: "COMBUSTÍVEIS E LUBRIFICANTES"
    valor_liquido   NUMERIC,            -- valor após glosas
    data_emissao    DATE,
    competencia     TEXT,               -- YYYY-MM (mês de competência)
    nr_documento    TEXT,               -- número da NF/documento
    descricao       TEXT,               -- especificação da subcota
    status_lneg     status_lneg_enum,   -- MATCH/OK/PENDENTE (cruzamento lista negra)
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## Dependências

- `politicos` — para resolver `politico_id` via SHA256(CPF)
- `fornecedores_rf` — futuramente para cruzar CNPJ com Receita Federal (status_lneg)

---

## Volume esperado

| Ano | Estimativa de registros |
|-----|------------------------|
| 2015 | ~250.000 |
| 2016 | ~280.000 |
| 2017 | ~320.000 |
| 2018 | ~350.000 |
| 2019 | ~380.000 |
| 2020 | ~320.000 (pandemia) |
| 2021 | ~350.000 |
| 2022 | ~400.000 |
| 2023 | ~420.000 |
| 2024 | ~450.000 |
| 2025 | ~400.000 (parcial) |
| **Total** | **~3,7 milhões** |
