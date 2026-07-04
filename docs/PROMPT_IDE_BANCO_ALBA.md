# PROMPT PARA IDE DO BANCO (DADOSPRISMA2)

## 🎯 O QUE FOI FEITO NO BANCO DE DADOS

Enriquecemos a base de deputados estaduais da Bahia com fotos oficiais e links de perfil do portal da ALBA (Assembleia Legislativa da Bahia).

---

## 📊 ESTRUTURA CRIADA

### 1. Nova Tabela: `alba_parlamentares`

```sql
CREATE TABLE alba_parlamentares (
    parlamentar_id INTEGER PRIMARY KEY,        -- ID único do deputado na ALBA
    autor_id INTEGER,                          -- ID de autor (sistema ALBA)
    nome_parlamentar TEXT NOT NULL,            -- Nome completo (ex: "Deputado João Silva")
    partido_atual TEXT,                        -- Partido atual (ex: "PSD", "PT")
    status TEXT,                               -- Status: "ativo" ou "inativo"
    foto_url TEXT,                             -- URL da foto oficial
    url_perfil TEXT,                           -- Link para perfil no portal ALBA
    politico_id TEXT,                          -- FK lógica para politicos.politico_id
    match_score FLOAT,                         -- Score do matching (0-100)
    match_metodo TEXT,                         -- Método: "exato", "fuzzy", "manual"
    coletado_em TIMESTAMP DEFAULT NOW(),
    importado_em TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_alba_politico_id ON alba_parlamentares(politico_id);
```

**Propósito:** Armazenar dados oficiais dos 72 deputados estaduais BA ativos, coletados do portal da ALBA.

---

### 2. Colunas Adicionadas em `politicos`

```sql
ALTER TABLE politicos 
ADD COLUMN alba_parlamentar_id INTEGER,  -- ID do deputado na ALBA
ADD COLUMN alba_perfil_url TEXT;         -- Link para perfil oficial

CREATE INDEX idx_politicos_alba_id ON politicos(alba_parlamentar_id);
```

**Propósito:** Criar vínculo entre dados TSE (tabela `politicos`) e dados ALBA.

---

## 🔄 DADOS IMPORTADOS

### Origem
- **Fonte:** Portal ALBA (albalegis.nopapercloud.com.br)
- **Arquivo:** `parlamentares_ids.json` (coletado em 2026-03-24)
- **Total:** 72 deputados estaduais ativos

### Processo de Matching
1. **Fuzzy matching** entre nomes ALBA e nomes TSE (threshold 85%)
2. **Mapeamento manual** para 8 casos especiais
3. **Validação por partido** quando disponível

### Resultado
- **71 deputados** com match bem-sucedido (98,6%)
- **1 deputado** sem match (Osni Cardoso - não encontrado no TSE)

---

## 📈 IMPACTO NOS DADOS

### Tabela `alba_parlamentares`
```sql
SELECT COUNT(*) FROM alba_parlamentares;
-- Resultado: 72 registros

SELECT COUNT(*) FROM alba_parlamentares WHERE politico_id IS NOT NULL;
-- Resultado: 71 registros (com match)
```

### Tabela `politicos` (atualizada)
```sql
-- Registros atualizados com foto
SELECT COUNT(*) 
FROM politicos 
WHERE uf = 'BA' 
  AND cargo = 'DEPUTADO ESTADUAL' 
  AND foto_url IS NOT NULL;
-- Resultado: 241 registros

-- Por que 241? Cada deputado tem múltiplos registros (histórico de eleições)
-- Exemplo: Adolfo Menezes tem registros em 2014, 2018, 2022
-- Todos receberam a mesma foto via politico_id
```

---

## 🔍 QUERIES ÚTEIS

### 1. Ver deputados com foto e perfil ALBA
```sql
SELECT 
    p.nome_urna,
    p.sigla_partido,
    p.ano_eleicao,
    p.foto_url,
    p.alba_perfil_url,
    a.nome_parlamentar,
    a.match_score
FROM politicos p
JOIN alba_parlamentares a ON p.politico_id = a.politico_id
WHERE p.uf = 'BA' 
  AND p.cargo = 'DEPUTADO ESTADUAL'
  AND p.foto_url IS NOT NULL
ORDER BY p.nome_urna;
```

### 2. Verificar qualidade do matching
```sql
SELECT 
    match_metodo,
    COUNT(*) as total,
    AVG(match_score) as score_medio,
    MIN(match_score) as score_minimo
FROM alba_parlamentares
WHERE politico_id IS NOT NULL
GROUP BY match_metodo;

-- Resultado esperado:
-- exato:  ~60 registros (100% score)
-- fuzzy:  ~5 registros  (85-95% score)
-- manual: ~6 registros  (100% score)
```

### 3. Deputados sem match
```sql
SELECT 
    nome_parlamentar,
    partido_atual,
    match_metodo
FROM alba_parlamentares
WHERE politico_id IS NULL;

-- Resultado: 1 registro (Osni Cardoso)
```

### 4. Histórico de um deputado específico
```sql
SELECT 
    p.ano_eleicao,
    p.nome_urna,
    p.sigla_partido,
    p.status_eleicao,
    p.foto_url IS NOT NULL as tem_foto
FROM politicos p
WHERE p.politico_id = (
    SELECT politico_id 
    FROM alba_parlamentares 
    WHERE nome_parlamentar LIKE '%Adolfo Menezes%'
)
ORDER BY p.ano_eleicao DESC;
```

---

## 🎨 EXEMPLOS DE DADOS

### Registro em `alba_parlamentares`
```json
{
  "parlamentar_id": 1010629,
  "nome_parlamentar": "Deputado Adolfo Menezes",
  "partido_atual": "PSD",
  "status": "ativo",
  "foto_url": "https://albalegis.nopapercloud.com.br/arquivo/documents/migracao/vereadores/fotos/adolfomenezes.jpg",
  "url_perfil": "https://albalegis.nopapercloud.com.br/spl/parlamentar.aspx?id=1010629",
  "politico_id": "abc123...",
  "match_score": 100.0,
  "match_metodo": "exato"
}
```

### Registro em `politicos` (atualizado)
```json
{
  "politico_id": "abc123...",
  "nome_urna": "Adolfo Menezes",
  "sigla_partido": "PSD",
  "ano_eleicao": 2022,
  "foto_url": "https://albalegis.nopapercloud.com.br/.../adolfomenezes.jpg",
  "alba_parlamentar_id": 1010629,
  "alba_perfil_url": "https://albalegis.nopapercloud.com.br/spl/parlamentar.aspx?id=1010629"
}
```

---

## 🔄 RELACIONAMENTOS

```
alba_parlamentares (72 registros)
    ↓ (politico_id - FK lógica)
politicos (2.747 registros BA)
    ↓ (politico_id - agrupamento)
241 registros atualizados com foto
```

**Nota:** O relacionamento é lógico (não há FOREIGN KEY constraint) para permitir flexibilidade.

---

## ✅ VALIDAÇÕES

### Integridade dos Dados
```sql
-- 1. Verificar URLs de foto válidas
SELECT COUNT(*) 
FROM alba_parlamentares 
WHERE foto_url NOT LIKE 'https://albalegis.nopapercloud.com.br/%';
-- Resultado esperado: 0

-- 2. Verificar duplicatas
SELECT politico_id, COUNT(*) 
FROM alba_parlamentares 
WHERE politico_id IS NOT NULL
GROUP BY politico_id 
HAVING COUNT(*) > 1;
-- Resultado esperado: 0 linhas

-- 3. Verificar consistência de partido
SELECT 
    a.nome_parlamentar,
    a.partido_atual as partido_alba,
    p.sigla_partido as partido_tse
FROM alba_parlamentares a
JOIN politicos p ON a.politico_id = p.politico_id
WHERE a.partido_atual != p.sigla_partido
  AND p.ano_eleicao = 2022;
-- Resultado: Algumas divergências esperadas (mudanças de partido)
```

---

## 🚀 PRÓXIMOS PASSOS

1. **Resolver pendência:** Investigar "Osni Cardoso" (único sem match)
2. **Validar URLs:** Testar se todas as fotos estão acessíveis
3. **Atualização periódica:** Rodar importador quando houver mudanças na ALBA
4. **Enriquecer mais:** Coletar biografias completas (não disponível no JSON atual)

---

## 📝 ARQUIVOS DE REFERÊNCIA

- **Migration:** `sql/migrations/002_add_alba_parlamentares.sql`
- **Importador:** `src/crews/alba_parlamentares/agent_importer.py`
- **Análise:** `src/crews/alba_parlamentares/analise_match.py`
- **Relatório:** `docs/ENRIQUECIMENTO_ALBA.md`

---

**Resumo:** Criamos uma nova tabela `alba_parlamentares` com 72 deputados BA, fizemos matching com a tabela `politicos` existente, e atualizamos 241 registros com fotos oficiais e links de perfil. Taxa de sucesso: 98,6%.
