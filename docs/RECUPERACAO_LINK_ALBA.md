# Recuperação do Link de Detalhe ALBA

**Data:** 2026-04-09  
**Problema:** Links para páginas de detalhe no portal ALBA não estavam sendo carregados no banco

---

## 🔍 Diagnóstico

O campo `link_detalhe` existe nos arquivos JSON (prata e ouro):
- **Arquivo prata:** `link_detalhe` (raiz do objeto)
- **Arquivo ouro:** `metadados.link_detalhe` (dentro de metadados)
- **Cobertura:** 100% dos registros (42.440 registros)
- **Formato:** `https://www.al.ba.gov.br/transparencia/verbas-idenizatorias/{id}/`

**Exemplo:**
```json
{
  "deputado": "Cláudia Oliveira",
  "link_detalhe": "https://www.al.ba.gov.br/transparencia/verbas-idenizatorias/99643/",
  "url_pdf_nf": "https://www.al.ba.gov.br/fserver/:anexo:NFE_189.pdf"
}
```

---

## ✅ Solução Implementada

### 1. Schema SQL (`sql/schema.sql`)
Adicionada coluna `url_detalhe_alba` na tabela `alba.verbas_indenizatorias`:
```sql
url_detalhe_alba TEXT, -- Link para página de detalhe no portal ALBA
```

### 2. Migration (`sql/migrations/001_add_url_detalhe_alba.sql`)
Script para adicionar a coluna em bancos existentes:
```sql
ALTER TABLE alba_verbas_gabinete 
ADD COLUMN IF NOT EXISTS url_detalhe_alba TEXT;
```

### 3. Loader Python (`src/crews/alba_verbas_gabinete/agent_loader_alba.py`)
- Adicionado campo `url_detalhe_alba` no dicionário de dados (linha 123)
- Atualizado SQL de INSERT para incluir a nova coluna (linha 48)
- Atualizado SQL de UPDATE para atualizar o campo em conflitos (linha 57)

---

## 🚀 Como Aplicar

### 1. Atualizar o banco de dados
```bash
psql postgresql://postgres:${DB_PASSWORD}@localhost:5432/prisma_data \
  -f sql/migrations/001_add_url_detalhe_alba.sql
```

### 2. Recarregar os dados
```bash
source /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate
cd /home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma
python src/crews/alba_verbas_gabinete/agent_loader_alba.py
```

O loader usará `ON CONFLICT (prisma_id) DO UPDATE` para atualizar os registros existentes com o novo campo.

---

## 📊 Resultado Esperado

Após a recarga, todos os 42.440 registros terão:
- `url_pdf` → link para o PDF da nota fiscal
- `url_detalhe_alba` → link para a página de detalhe no portal ALBA

**Exemplo de uso no frontend:**
```javascript
// Link para ver o registro completo no site da ALBA
<a href={verba.url_detalhe_alba} target="_blank">
  Ver no Portal ALBA
</a>

// Link para baixar o PDF da nota fiscal
<a href={verba.url_pdf} target="_blank">
  Baixar Nota Fiscal
</a>
```

---

## 📝 Notas

- O campo estava presente nos dados desde o início (coletado pelo Romário)
- Apenas não estava sendo carregado no banco por falta de mapeamento
- Nenhum dado foi perdido, apenas não estava acessível via SQL
- A migration é idempotente (`IF NOT EXISTS`)
