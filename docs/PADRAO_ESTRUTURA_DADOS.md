# Padrão de Estrutura de Dados — PRISMA 888

**Versão:** 1.0  
**Data:** 2026-04-06  
**Regra:** Toda crew segue este padrão sem exceção

---

## Estrutura Obrigatória

```
data/raw/{portal}/
  dados_brutos/   ← Arquivos originais da fonte (CSV, JSON, PDF) — NUNCA modificar
  bronze/         ← Agent A gera aqui (JSON com SHA256)
  prata/          ← Agent B gera aqui (JSON normalizado)
  ouro/           ← Agent C gera aqui (JSON enriquecido) — opcional
  rejeitados/     ← Registros inválidos com motivo
```

---

## Nomenclatura de Arquivos

### Bronze
```
{entidade}_{ano}_{uf}_bronze.json
```
Exemplo: `candidatos_2024_BA_bronze.json`

### Prata
```
{entidade}_{ano}_{uf}_prata.json
```
Exemplo: `candidatos_2024_BA_prata.json`

### Ouro
```
{entidade}_{ano}_{uf}_ouro.json
```
Exemplo: `candidatos_2024_BA_ouro.json`

### Rejeitados
```
{entidade}_{ano}_{uf}_rejeitados.json
```
Exemplo: `candidatos_2024_BA_rejeitados.json`

---

## Metadados Obrigatórios

Todos os arquivos JSON devem ter:

```json
{
  "meta": {
    "portal": "Nome do Portal",
    "entidade": "nome_entidade",
    "ano": 2024,
    "uf": "BA",
    "camada": "bronze|prata|ouro",
    "data_extracao": "2026-04-06T10:30:00-03:00",
    "hash_sha256": "abc123...",
    "total_registros": 35209,
    "versao_agente": "v1.0"
  },
  "records": [...]
}
```

---

## Banco de Dados

**Conexão única:**
```
postgresql://postgres:${DB_PASSWORD}@localhost:5432/prisma_data
```

**NUNCA usar Supabase ou outro banco.**

---

## Padrão de Agentes

Cada crew tem exatamente 3 agentes:

### Agent A — Coletor
- **Input:** `dados_brutos/` ou API
- **Output:** `bronze/`
- **Função:** Gera SHA256, salva JSON imutável

### Agent B — Normalizador
- **Input:** `bronze/`
- **Output:** `prata/` + `rejeitados/`
- **Função:** Normaliza, valida, fuzzy match

### Agent C — Loader
- **Input:** `prata/`
- **Output:** PostgreSQL
- **Função:** UPSERT idempotente em batches

---

## Exemplo Completo: TSE Candidatos

```
data/raw/tse/candidatos/
  dados_brutos/
    consulta_cand_2024/
      consulta_cand_2024_BA.csv
      consulta_cand_2024_SP.csv
      ...
  bronze/
    candidatos_2024_BA_bronze.json
    candidatos_2024_SP_bronze.json
  prata/
    candidatos_2024_BA_prata.json
    candidatos_2024_SP_prata.json
  ouro/
    (vazio por enquanto)
  rejeitados/
    candidatos_2024_BA_rejeitados.json
```

---

## Validação

Antes de commitar qualquer crew, verificar:

- [ ] Pasta `dados_brutos/` existe e tem os arquivos originais
- [ ] Agent A salva em `bronze/` com SHA256
- [ ] Agent B salva em `prata/` e `rejeitados/`
- [ ] Agent C lê de `prata/` e grava no PostgreSQL
- [ ] `crew_manifest.json` tem os caminhos corretos
- [ ] Todos os JSONs têm metadados completos

---

**Arquivo de referência obrigatória para todas as crews.**
