# PLANO: Enriquecimento de Deputados Estaduais BA com Dados ALBA

**Data:** 2026-04-09  
**Objetivo:** Adicionar fotos e dados ricos dos 72 deputados estaduais BA

---

## 📊 SITUAÇÃO ATUAL

### Banco de Dados
- **Tabela:** `politicos`
- **Deputados BA:** 2.747 registros
- **Com foto:** 0 (campo `foto_url` vazio)
- **Campos disponíveis:** `foto_url` (TEXT) já existe

### Dados ALBA Disponíveis
- **Total:** 72 deputados ativos
- **Arquivo:** `/BACK UP/n888n-prisma (copiar 1)/data/parlamentares/parlamentares_ids.json`
- **Campos:**
  - `parlamentar_id` (ID único ALBA)
  - `nome_parlamentar` (ex: "Deputada Cláudia Oliveira")
  - `partido_atual` (ex: "PSD")
  - `status` ("ativo")
  - `foto_url` (URL da foto - **com bug de duplicação**)
  - `url_perfil` (link para perfil ALBA)

### Frontend
- ✅ **Preparado** para receber `foto_url`
- ✅ Usa em múltiplos componentes:
  - `AlbaCandidateList.tsx`
  - `EmendasCityTab.tsx`
  - `VisaoGeralTab.tsx`
  - `radar2/[slug]/page.tsx`
- ✅ Fallback para avatar gerado: `ui-avatars.com`

---

## 🔧 PROBLEMAS IDENTIFICADOS

### 1. URL de Foto Duplicada
```
❌ https://albalegis.nopapercloud.com.brhttps://albalegis.nopapercloud.com.br/arquivo/...
✅ https://albalegis.nopapercloud.com.br/arquivo/documents/migracao/vereadores/fotos/claudiaoliveira1.jpg
```

### 2. Match de Nomes
- ALBA: "Deputada Cláudia Oliveira"
- TSE: "CLÁUDIA OLIVEIRA" (nome_urna)
- Precisa: fuzzy matching + limpeza de prefixos

### 3. Campos Extras
Frontend espera (mas não tem nos dados ALBA):
- `biografia_resumo`
- `biografia_completa`
- `formacao_academica`
- `carreira_politica`

---

## ✅ PLANO DE AÇÃO

### Etapa 1: Criar Tabela Auxiliar
```sql
CREATE TABLE IF NOT EXISTS alba_parlamentares (
    parlamentar_id INTEGER PRIMARY KEY,
    autor_id INTEGER,
    nome_parlamentar TEXT,
    partido_atual TEXT,
    status TEXT,
    foto_url TEXT,
    url_perfil TEXT,
    politico_id TEXT, -- FK para politicos (via match)
    match_score FLOAT,
    coletado_em TIMESTAMP DEFAULT NOW()
);
```

### Etapa 2: Importar Dados ALBA
- Ler JSON dos 72 deputados
- Corrigir URLs duplicadas
- Inserir na tabela `alba_parlamentares`

### Etapa 3: Match com Tabela `politicos`
- Buscar deputados BA mais recentes (ano_eleicao >= 2022)
- Fuzzy match por nome (remover "Deputado/Deputada")
- Validar por partido (se disponível)
- Salvar `politico_id` e `match_score`

### Etapa 4: Atualizar `politicos.foto_url`
```sql
UPDATE politicos p
SET foto_url = a.foto_url
FROM alba_parlamentares a
WHERE p.politico_id = a.politico_id
  AND a.match_score >= 0.85
  AND p.foto_url IS NULL;
```

### Etapa 5: Adicionar Colunas Extras (Opcional)
```sql
ALTER TABLE politicos 
ADD COLUMN IF NOT EXISTS alba_parlamentar_id INTEGER,
ADD COLUMN IF NOT EXISTS alba_perfil_url TEXT;

UPDATE politicos p
SET 
    alba_parlamentar_id = a.parlamentar_id,
    alba_perfil_url = a.url_perfil
FROM alba_parlamentares a
WHERE p.politico_id = a.politico_id;
```

---

## 📈 RESULTADO ESPERADO

### Banco de Dados
- ✅ 72 deputados BA com `foto_url` preenchido
- ✅ Links para perfil ALBA
- ✅ Rastreabilidade via `alba_parlamentar_id`

### Frontend
- ✅ Fotos aparecem automaticamente
- ✅ Fallback só para deputados sem match
- ✅ Links para perfil oficial ALBA

---

## 🚨 VALIDAÇÕES NECESSÁRIAS

1. **Testar URLs de foto** (verificar se estão acessíveis)
2. **Validar match** (conferir se nomes batem corretamente)
3. **Verificar duplicatas** (garantir 1:1 entre ALBA e politicos)
4. **Testar frontend** (ver se fotos aparecem)

---

## 📝 ARQUIVOS A CRIAR

1. `sql/migrations/002_add_alba_parlamentares.sql` - Schema
2. `src/crews/alba_parlamentares/agent_importer.py` - Importador
3. `docs/ENRIQUECIMENTO_ALBA.md` - Documentação

---

**Próximo passo:** Criar script de importação? (y/n)
