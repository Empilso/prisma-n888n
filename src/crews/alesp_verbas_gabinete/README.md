# ALESP Verbas de Gabinete — Crew ETL

Pipeline de extração das despesas de gabinete dos deputados estaduais de São Paulo (ALESP).

## O que extrai

Todas as despesas de gabinete dos ~94 deputados estaduais da ALESP desde **2002** até o mês atual. A ALESP disponibiliza um único XML com o histórico completo, atualizado continuamente.

## Fonte

| Campo | Valor |
|---|---|
| Portal | ALESP — Assembleia Legislativa do Estado de São Paulo |
| URL | `https://www.al.sp.gov.br/repositorioDados/deputados/despesas_gabinetes.xml` |
| Formato | XML único (~14 MB), atualizado mês a mês |
| Campos | Ano, Mes, Matricula, Deputado, Tipo, Fornecedor, CNPJ, Valor |

## Período

| Início | Fim | Deputados históricos | Legislaturas |
|--------|-----|---------------------|--------------|
| 2002 | atual | ~379 únicos | ~6 (desde 2002) |

> **Nota:** Como o XML inclui dados desde 2002, há ~6 legislaturas com ~94 deputados cada. O volume de nomes únicos ultrapassa 200 porque inclui deputados de mandatos anteriores.

## Tabela destino

```sql
CREATE TABLE alesp_verbas_gabinete (
    id               VARCHAR(64)  PRIMARY KEY,  -- SHA256[:32](matricula|competencia|cnpj|valor)
    politico_id      VARCHAR(64),               -- SHA256(CPF) via fuzzy match nome
    matricula        VARCHAR(20)  NOT NULL,      -- ID interno ALESP
    nome_deputado    TEXT,
    cnpj_fornecedor  VARCHAR(14),
    nome_fornecedor  TEXT,
    tipo_despesa     TEXT,
    valor            NUMERIC(12,2),
    mes              INTEGER,
    ano              INTEGER,
    competencia      VARCHAR(7),                -- YYYY-MM
    status_lneg      status_lneg_enum,
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);
```

## Agentes

### Agent A — Coletor
```bash
python agent_a_coletor.py            # Baixa XML e converte para Bronze JSON
python agent_a_coletor.py --force    # Re-baixa mesmo se Bronze já existe
```
**Saída:** `data/alesp_verbas_gabinete/bronze/alesp_verbas_bronze.json`

### Agent B — Normalizador
```bash
python agent_b_normalizador.py
```
- Gera `id` determinístico: `SHA256(matricula|competencia|cnpj|valor)[:32]`
- Faz fuzzy match de nome do deputado contra `politicos` (uf=SP, cargo=DEPUTADO ESTADUAL) para atribuir `politico_id`
- Threshold fuzzy: 80% (rapidfuzz token_sort_ratio)
- Rejeita: valor ausente/≤0, matricula ausente, ano/mes inválido

**Saída:** `data/alesp_verbas_gabinete/prata/alesp_verbas_prata.json`

### Agent C — Loader
```bash
python agent_c_loader.py             # Carrega Prata → DB
python agent_c_loader.py --dry-run   # Valida sem inserir
```
- `ON CONFLICT (id) DO NOTHING` — idempotente, pode re-rodar sem duplicar

### Agent V — Quality Gate
```bash
python agent_verify.py               # Verifica qualidade dos dados
python agent_verify.py --strict      # Falha com exit 1 para CI
```

| Check | Threshold | Nível |
|-------|-----------|-------|
| Volume total | >= 50.000 registros | Crítico |
| Período | ano_min ≤ 2016, ano_max ≥ 2024 | Crítico |
| Deputados únicos | 80–600 | Crítico |
| Valor total | R$ 50M – R$ 2B | Crítico |
| Valores inválidos (≤0) | = 0 | Crítico |
| Cobertura politico_id | >= 60% | Aviso |
| Duplicatas de id | = 0 | Crítico |
| Categorias distintas | >= 5 | Aviso |

## Execução completa

### Primeira vez
```bash
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma/src/crews/alesp_verbas_gabinete
python agent_a_coletor.py
python agent_b_normalizador.py
python agent_c_loader.py
python agent_verify.py
```

### Atualização mensal
```bash
python agent_a_coletor.py --force
python agent_b_normalizador.py
python agent_c_loader.py
python agent_verify.py
```

## Volumes esperados

| Métrica | Valor |
|---------|-------|
| Registros total | ~614.000 |
| Com politico_id | ~441.000 (72%) |
| Deputados únicos | ~379 |
| Valor total histórico | ~R$ 523M |
| Categorias de despesa | ~14 |

## Notas importantes

- **Sem CPF**: A ALESP usa `Matricula` (código interno) como identificador. O link com `politico_id` é feito por fuzzy match de nome. Cobertura ~72%.
- **Formato de valor**: XML usa ponto como decimal (formato US): `200.0`, `2850.0`.
- **Update incremental**: O XML completo é baixado a cada update (`--force`). O `ON CONFLICT DO NOTHING` garante que apenas registros novos são inseridos.
- **Radar integração**: O backend (`verbas_gabinete.py`) auto-detecta deputados estaduais SP via `politicos.uf = 'SP'` e roteia para `alesp_verbas_gabinete`.
