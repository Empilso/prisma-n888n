# 🗺️ CREW IBGE MUNICÍPIOS

**Fase:** 0 — Hub Central  
**Versão:** v1.0  
**Status:** ✅ Ativo

---

## 📋 DESCRIÇÃO

Extrai todos os **5.570 municípios brasileiros** da API do IBGE e carrega na tabela `municipios` do banco PostgreSQL `prisma_data`.

Esta é a **base territorial de todo o projeto** — Foreign Key de todas as outras tabelas que referenciam municípios.

---

## 🎯 OBJETIVO

Criar e manter atualizada a tabela de municípios que serve como referência para:
- Emendas parlamentares (destino dos recursos)
- Candidatos (município de nascimento/domicílio)
- Empresas (sede/filiais)
- Contas municipais (TCM)

---

## 📊 DADOS

- **Fonte:** API IBGE — Malha Municipal
- **URL:** https://servicodados.ibge.gov.br/api/v1/localidades/municipios
- **Formato:** JSON API REST
- **Total:** 5.570 municípios
- **Atualização:** Anual (IBGE atualiza quando há criação/extinção de municípios)

---

## 🤖 AGENTES

### Agent A: Coletor IBGE
**Arquivo:** `agent_a_coletor.py`  
**Camada:** Bronze (Raw)

**O que faz:**
- Baixa JSON da API IBGE
- Salva Bronze imutável em `data/raw/ibge/municipios_{YYYY-MM-DD}_bronze.json`
- Calcula SHA256 do payload
- Registra metadados (fonte, timestamp, total)
- Retry automático (3x, backoff 2-10s)

**Como rodar:**
```bash
python agent_a_coletor.py
```

**Saída esperada:**
```
╔════════════════════════════════════════════════════════════════════╗
║              AGENT-A v1.0 — COLETOR IBGE                          ║
╚════════════════════════════════════════════════════════════════════╝
🔹 Baixando API IBGE...
✅ 5570 municípios recebidos
🔹 Bronze salvo: municipios_2026-04-05_bronze.json (sha256: abc123...)
✅ Concluído em 2.3s

[AGENT-A DONE] ✅
```

---

### Agent B: Normalizador
**Arquivo:** `agent_b_normalizador.py`  
**Camada:** Prata (Normalizado)

**O que faz:**
- Lê Bronze mais recente
- Normaliza campos:
  - `id_ibge`: 7 dígitos (zero-padded)
  - `nome`: Title Case
  - `uf`: UPPER (2 letras)
  - `regiao`: Title Case
- Valida com Pydantic (3 validators)
- Separa válidos e rejeitados
- Salva Prata em `data/saida/prata/ibge/municipios_{YYYY-MM-DD}_prata.json`

**Como rodar:**
```bash
python agent_b_normalizador.py
```

**Saída esperada:**
```
╔════════════════════════════════════════════════════════════════════╗
║              AGENT-B v1.0 — NORMALIZADOR                          ║
╚════════════════════════════════════════════════════════════════════╝
🔹 Lendo Bronze: municipios_2026-04-05_bronze.json
🔹 Normalizando...
✅ Válidos: 5570 | ❌ Rejeitados: 0
🔹 Prata salvo: municipios_2026-04-05_prata.json
✅ Concluído em 1.2s

[AGENT-B DONE] ✅
```

---

### Agent C: Loader PostgreSQL
**Arquivo:** `agent_c_loader.py`  
**Camada:** Ouro → Banco

**O que faz:**
- Lê Prata mais recente
- Conecta PostgreSQL (`prisma_data`)
- Upsert em batch de 500 via `execute_values`
- `ON CONFLICT (id_ibge) DO UPDATE` (idempotência)
- Registra em `etl_log`
- Suporta `--dry-run` (testa sem gravar)

**Como rodar:**
```bash
# Dry-run (testa sem gravar)
python agent_c_loader.py --dry-run

# Carga real
python agent_c_loader.py
```

**Saída esperada:**
```
╔════════════════════════════════════════════════════════════════════╗
║              AGENT-C v1.0 — LOADER POSTGRESQL                     ║
╚════════════════════════════════════════════════════════════════════╝
🔹 Lendo Prata: municipios_2026-04-05_prata.json
🔹 Gravando no banco...
✅ Novos: 5570 | 🔄 Atualizados: 0
✅ etl_log registrado | Duração: 3.5s

[AGENT-C DONE] ✅
```

---

## 🚀 EXECUÇÃO COMPLETA

### Opção 1: Agente por Agente
```bash
cd ~/Documentos/zikualdo/Prisma888/n888n-prisma/src/crews/ibge_municipios

# 1. Coletar
python agent_a_coletor.py

# 2. Normalizar
python agent_b_normalizador.py

# 3. Carregar (dry-run primeiro)
python agent_c_loader.py --dry-run
python agent_c_loader.py
```

### Opção 2: Via Dashboard (Recomendado)
1. Abrir dashboard: http://localhost:5173
2. Localizar card "IBGE — Municípios"
3. Clicar em "Rodar Crew" ou "Dry Run"
4. Acompanhar logs em tempo real

### Opção 3: Via API
```bash
# Rodar crew completa
curl -X POST http://localhost:8003/api/run-crew/ibge_municipios

# Rodar agente específico
curl -X POST http://localhost:8003/api/run-crew/ibge_municipios/agent_a
```

---

## 📁 ESTRUTURA DE ARQUIVOS

```
data/
├── raw/ibge/                          ← Bronze (imutável)
│   └── municipios_2026-04-05_bronze.json
├── saida/
│   ├── prata/ibge/                    ← Prata (normalizado)
│   │   └── municipios_2026-04-05_prata.json
│   └── rejeitados/ibge/               ← Rejeitados (se houver)
│       └── municipios_2026-04-05_rejeitados.json
```

---

## 🗄️ TABELA DESTINO

**Tabela:** `municipios`  
**Banco:** `prisma_data` (PostgreSQL)

**Schema:**
```sql
CREATE TABLE municipios (
    id_ibge    CHAR(7)      PRIMARY KEY,
    nome       TEXT         NOT NULL,
    uf         CHAR(2)      NOT NULL,
    regiao     TEXT,
    populacao  INTEGER,
    lat        NUMERIC(9,6),
    lng        NUMERIC(9,6),
    created_at TIMESTAMPTZ  DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);
```

**Índices:**
```sql
CREATE INDEX idx_municipios_uf ON municipios(uf);
CREATE INDEX idx_municipios_regiao ON municipios(regiao);
```

---

## ✅ CHECKLIST DE VALIDAÇÃO

Após executar a crew, validar:

### 1. Arquivos Criados
```bash
# Bronze
ls -lh data/raw/ibge/municipios_*_bronze.json

# Prata
ls -lh data/saida/prata/ibge/municipios_*_prata.json
```

### 2. Contagem no Banco
```bash
psql -U postgres -d prisma_data -c "SELECT COUNT(*) FROM municipios;"
# Esperado: 5570
```

### 3. Amostra de Dados
```bash
psql -U postgres -d prisma_data -c "SELECT * FROM municipios LIMIT 5;"
```

### 4. Verificar ETL Log
```bash
psql -U postgres -d prisma_data -c "SELECT * FROM etl_log WHERE portal = 'ibge_municipios' ORDER BY created_at DESC LIMIT 1;"
```

### 5. Verificar Rejeitados
```bash
ls -lh data/saida/rejeitados/ibge/
# Esperado: vazio (0 rejeitados)
```

---

## 🔧 TROUBLESHOOTING

### Erro: "Nenhum arquivo Bronze encontrado"
**Causa:** Agent B ou C rodou antes do Agent A  
**Solução:** Rodar `agent_a_coletor.py` primeiro

### Erro: "Connection refused" (PostgreSQL)
**Causa:** Banco não está rodando  
**Solução:**
```bash
sudo systemctl start postgresql
# ou
pg_ctl start -D /var/lib/postgresql/data
```

### Erro: "Tabela municipios não existe"
**Causa:** Schema não foi criado  
**Solução:**
```bash
psql -U postgres -d prisma_data -f schema.sql
```

### Contagem diferente de 5570
**Causa:** API IBGE pode ter sido atualizada  
**Ação:** Normal se houver criação/extinção de municípios. Verificar no site do IBGE.

---

## 📊 MÉTRICAS

- **Tempo total:** ~15s (A + B + C)
- **Agent A:** ~2-3s (download API)
- **Agent B:** ~1-2s (normalização)
- **Agent C:** ~10-12s (upsert 5570 registros)

---

## 🔄 ATUALIZAÇÃO

**Frequência recomendada:** Anual (ou quando IBGE divulgar mudanças)

**Como atualizar:**
```bash
# Simplesmente rodar a crew novamente
python agent_a_coletor.py
python agent_b_normalizador.py
python agent_c_loader.py

# O sistema detecta mudanças e atualiza automaticamente
# (ON CONFLICT DO UPDATE)
```

---

## 🛠️ STACK TECNOLÓGICA

- **requests** — HTTP client
- **tenacity** — Retry decorator
- **psycopg2** — PostgreSQL driver
- **pydantic** — Validação de schema
- **hashlib** — SHA256 checksum

---

## 📚 REFERÊNCIAS

- [API IBGE — Localidades](https://servicodados.ibge.gov.br/api/docs/localidades)
- [Malha Municipal IBGE](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais.html)
- [Documentação PostgreSQL](https://www.postgresql.org/docs/)

---

**Crew criada em:** 2026-04-05  
**Última atualização:** 2026-04-05  
**Autor:** Sistema N888N-PRISMA
