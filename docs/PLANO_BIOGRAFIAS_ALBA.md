# PLANO: Importação de Biografias Completas ALBA

**Data:** 2026-04-09  
**Fonte:** `parlamentares_hub_normalized.json` (149 deputados)  
**Qualidade:** 98% (dados muito ricos!)

---

## 📊 O QUE TEMOS

### Arquivo: parlamentares_hub_normalized.json
- **Total:** 149 deputados (histórico completo, não só ativos)
- **Cobertura:** 100% com biografia, foto, dados pessoais
- **Qualidade média:** 0.98 (excelente!)

### Campos Disponíveis (33 campos por deputado)
```
✅ prisma_id
✅ parlamentar_id (ID ALBA)
✅ nome_eleitoral / nome_limpo / nome_civil
✅ partido / sigla_partido
✅ foto_url (149 fotos!)
✅ biografia_completa (texto longo, 3-4k chars)
✅ dados_pessoais (dict com 7 campos)
✅ mandatos (array com histórico completo)
✅ filiacao_partidaria (array com histórico de partidos)
✅ data_nascimento / municipio_nascimento / uf_nascimento
✅ profissao / sexo / conjuge / filhos
✅ legislatura / esfera / uf / casa
✅ resumo_executivo
✅ contatos (email, telefones)
✅ url_oficial (perfil ALBA)
```

---

## 🎯 ESTRATÉGIA DE IMPORTAÇÃO

### Fase 1: Criar Tabela Auxiliar
```sql
CREATE TABLE alba_biografias (
    prisma_id TEXT PRIMARY KEY,
    parlamentar_id TEXT,
    politico_id TEXT, -- FK para politicos
    nome_eleitoral TEXT,
    nome_civil TEXT,
    biografia_completa TEXT,
    dados_pessoais JSONB,
    mandatos JSONB,
    filiacao_partidaria JSONB,
    profissao TEXT,
    data_nascimento DATE,
    municipio_nascimento TEXT,
    uf_nascimento TEXT,
    sexo TEXT,
    conjuge TEXT,
    filhos TEXT,
    foto_url TEXT,
    url_oficial TEXT,
    resumo_executivo TEXT,
    qualidade_score FLOAT,
    match_score FLOAT,
    match_metodo TEXT,
    importado_em TIMESTAMP DEFAULT NOW()
);
```

### Fase 2: Match com Tabela politicos
**Critérios:**
1. Match por `alba_parlamentar_id` (já temos 71 matches)
2. Fuzzy match por nome (para os 78 restantes)
3. Validação por partido e UF

**Resultado esperado:**
- 71 matches automáticos (já vinculados)
- ~60-70 matches fuzzy (deputados históricos)
- ~10-20 sem match (muito antigos ou não eleitos)

### Fase 3: Atualizar Tabela politicos
**Adicionar colunas:**
```sql
ALTER TABLE politicos
ADD COLUMN biografia_completa TEXT,
ADD COLUMN biografia_resumo TEXT,
ADD COLUMN dados_pessoais JSONB,
ADD COLUMN mandatos_historico JSONB,
ADD COLUMN filiacao_partidaria JSONB,
ADD COLUMN profissao TEXT,
ADD COLUMN municipio_nascimento TEXT,
ADD COLUMN conjuge TEXT,
ADD COLUMN filhos TEXT,
ADD COLUMN url_oficial_alba TEXT;
```

### Fase 4: Enriquecer politicos
```sql
UPDATE politicos p
SET 
    biografia_completa = b.biografia_completa,
    biografia_resumo = b.resumo_executivo,
    dados_pessoais = b.dados_pessoais,
    mandatos_historico = b.mandatos,
    filiacao_partidaria = b.filiacao_partidaria,
    profissao = b.profissao,
    municipio_nascimento = b.municipio_nascimento,
    conjuge = b.conjuge,
    filhos = b.filhos,
    url_oficial_alba = b.url_oficial,
    foto_url = COALESCE(p.foto_url, b.foto_url) -- Manter foto existente
FROM alba_biografias b
WHERE p.politico_id = b.politico_id
  AND b.politico_id IS NOT NULL;
```

---

## ⚠️ CUIDADOS ESPECIAIS

### 1. Não Sobrescrever Fotos Existentes
- Já temos 71 fotos dos deputados ativos
- Usar `COALESCE` para manter foto existente
- Só adicionar foto se não tiver

### 2. Match Conservador
- Threshold de 90% (mais rigoroso)
- Validar por partido quando possível
- Mapeamento manual para casos duvidosos

### 3. Dados JSONB
- `dados_pessoais`, `mandatos`, `filiacao_partidaria` em JSONB
- Permite queries flexíveis
- Mantém estrutura original

### 4. Versionamento
- Guardar `qualidade_score` e `match_score`
- Rastrear `match_metodo` (exato/fuzzy/manual)
- Timestamp de importação

---

## 📋 CAMPOS DO FRONTEND

### O que o frontend já espera (verificar):
```typescript
interface Politician {
  biografia?: string;
  biografia_resumo?: string;
  biografia_completa?: string;
  formacao_academica?: Array;
  carreira_politica?: Array;
  mandatos?: Array;
  profissao?: string;
  data_nascimento?: string;
  municipio_base?: string;
}
```

### Mapeamento:
```
biografia_completa → biografia_completa ✅
resumo_executivo → biografia_resumo ✅
mandatos → mandatos_historico ✅
profissao → profissao ✅
data_nascimento → data_nascimento ✅
municipio_nascimento → municipio_base ✅
```

---

## 🎯 RESULTADO ESPERADO

### Banco de Dados
- ✅ 149 biografias completas em `alba_biografias`
- ✅ ~130-140 deputados enriquecidos em `politicos`
- ✅ Dados estruturados em JSONB (fácil de consultar)

### Frontend
- ✅ Biografias completas aparecem automaticamente
- ✅ Histórico de mandatos visível
- ✅ Dados pessoais (profissão, nascimento, família)
- ✅ Histórico partidário

---

## 📝 PRÓXIMOS PASSOS

1. ✅ Criar migration SQL (tabela + colunas)
2. ✅ Criar importador Python (com match cuidadoso)
3. ✅ Executar em dry-run (validar matches)
4. ✅ Aplicar no banco (com backup antes)
5. ✅ Testar no frontend
6. ✅ Documentar mapeamento de campos

---

**Quer que eu comece pela migration SQL?** 🔧
