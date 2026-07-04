# Correção API Verbas de Gabinete - PostgreSQL Local

**Data:** 2026-04-09  
**Arquivo:** `backend/src/api/core/verbas_gabinete.py`

---

## 🔧 Problema

A API estava buscando dados em:
- ❌ **Supabase** → tabela `despesas_gabinete` (vazia)

Mas os dados reais estão em:
- ✅ **PostgreSQL Local** → tabela `alba_verbas_gabinete` (42.440 registros)

---

## ✅ Solução Implementada

### 1. Conexão alterada
```python
# ANTES
from supabase import create_client
def get_supabase(): ...

# DEPOIS
import psycopg2
def get_db():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="prisma_data",
        user="postgres",
        password="${DB_PASSWORD}"
    )
```

### 2. Query reescrita para PostgreSQL
- Busca por `politico_id` ou `nome_deputado_raw`
- Filtros: ano, mês, categoria, fornecedor
- Paginação com LIMIT/OFFSET
- Retorna **todos os campos**, incluindo:
  - ✅ `url_pdf` (link do PDF da nota fiscal)
  - ✅ `url_detalhe_alba` (link da página no portal ALBA)

### 3. Campos retornados na API

**Modo KPIs (`?modo=kpis`):**
- totalGasto, totalNotas, totalFornecedores
- categorias (agregado)
- topFornecedores (top 10)
- gastosMensais (série temporal)
- anos e categorias disponíveis

**Modo Paginado (padrão):**
```json
{
  "registros": [
    {
      "prisma_id": "...",
      "num_processo": "...",
      "nome_deputado_raw": "...",
      "nome_fornecedor": "...",
      "cnpj_fornecedor": "...",
      "categoria": "...",
      "valor_pago": 1000.00,
      "data_emissao": "2026-03-01",
      "competencia": "03/2026",
      "url_pdf": "https://www.al.ba.gov.br/fserver/:anexo:NFE_189.pdf",
      "url_detalhe_alba": "https://www.al.ba.gov.br/transparencia/verbas-idenizatorias/99643/",
      "qualidade_score": 1.0,
      "ano": 2026
    }
  ],
  "totalRegistros": 42440,
  "pagina": 0,
  "pageSize": 25
}
```

---

## 🚀 Como Testar

### 1. Reiniciar o backend
```bash
cd /home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA888FORBES/backend
# Parar o servidor atual (Ctrl+C)
# Reiniciar
python -m uvicorn src.main:app --reload --port 8000
```

### 2. Testar endpoint
```bash
# KPIs de um deputado
curl "http://localhost:8000/api/verbas/NOME_DEPUTADO?modo=kpis"

# Dados paginados
curl "http://localhost:8000/api/verbas/NOME_DEPUTADO?page=0&pageSize=25"

# Com filtros
curl "http://localhost:8000/api/verbas/NOME_DEPUTADO?ano=2026&categoria=divulgacao"
```

### 3. Verificar no frontend
- Abrir página de um deputado
- Ir na aba "Verbas de Gabinete"
- Verificar se aparecem os botões:
  - 📄 Abrir PDF
  - 📋 Detalhe (link para portal ALBA)

---

## 📊 Resultado Esperado

- ✅ API retorna dados reais do PostgreSQL local
- ✅ Frontend recebe `url_pdf` e `url_detalhe_alba`
- ✅ Botões de link funcionam
- ✅ 42.440 registros acessíveis (2015-2026)

---

## 🔄 Próximos Passos

1. Testar API com diferentes deputados
2. Validar filtros (ano, categoria, fornecedor)
3. Verificar performance com grandes volumes
4. Considerar migração para Supabase quando estável
