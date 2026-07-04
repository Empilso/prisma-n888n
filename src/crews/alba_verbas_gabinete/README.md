# ALBA — Verbas de Gabinete

**Status:** ✅ Completo  
**Última atualização:** 2026-04-07  
**Registros:** 42.440 | **Valor:** R$ 284M | **Período:** 2015-2026

---

## Descrição

Verbas indenizatórias dos deputados estaduais da Bahia (ALBA). Inclui pagamentos a fornecedores por assessorias, consultorias, materiais de expediente, combustível, etc.

---

## Fonte de Dados

- **Portal:** ALBA — Portal de Transparência
- **URL:** https://transparencia.alba.ba.gov.br
- **Formato:** JSON Prata (já processado)
- **Localização:** `data/alba/alba_{ano}_prata.json`
- **Período:** 2015-2026 (12 anos)

---

## Estrutura da Crew

```
src/crews/alba_verbas_gabinete/
├── crew_manifest.json       # Metadados da crew
├── agent_loader_alba.py     # Prata → PostgreSQL (v2)
└── README.md                # Este arquivo
```

**Nota:** Esta crew usa apenas Agent C (loader) porque os dados já vêm processados em Prata por outro pipeline.

---

## Execução

```bash
cd ~/Documentos/zikualdo/Prisma888/n888n-prisma
source ~/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/activate

# Dry-run
python src/crews/alba_verbas_gabinete/agent_loader_alba.py --dry-run

# Carga completa
python src/crews/alba_verbas_gabinete/agent_loader_alba.py

# Carga de um ano específico
python src/crews/alba_verbas_gabinete/agent_loader_alba.py --ano 2024
```

---

## Mapeamento de Dados

### Prata → PostgreSQL

| Campo Prata | Campo Banco | Tipo | Obs |
|-------------|-------------|------|-----|
| `prisma_id` | `prisma_id` | TEXT | **PK** (MD5 único) |
| `deputado` | `politico_id` | TEXT | Resolvido via fuzzy match |
| `cnpj_fornecedor` | `cnpj_fornecedor` | TEXT | |
| `cpf_fornecedor` | `cpf_fornecedor` | TEXT | |
| `nome_fornecedor_limpo` | `nome_fornecedor` | TEXT | |
| `categoria_slug` | `categoria` | TEXT | |
| `valor` | `valor_pago` | NUMERIC(14,2) | |
| `competencia_date` | `data_emissao` | DATE | |
| `competencia_raw` | `competencia` | TEXT | MM/YYYY |
| `url_pdf_nf` | `url_pdf` | TEXT | |
| `qualidade_score` | `qualidade_score` | NUMERIC(5,2) | |
| `competencia_ano` | `ano` | SMALLINT | |
| `num_processo` | `num_processo` | TEXT | Referência (não PK) |
| `uf` | `uf` | CHAR(2) | Sempre 'BA' |

---

## Resolução de `politico_id`

### Mapeamento Manual

12 nomes do portal ALBA foram mapeados manualmente para nomes do TSE:

```python
MAPA_NOMES_ALBA = {
    'BIRA CORÔA LULA':       'BIRA COROA',
    'GIKA LOPES LULA':       'GIKA',
    'JACÓ LULA DA SILVA':    'JACÓ',
    'ZÉ NETO LULA':          'ZÉ NETO',
    'MARCELL DOS ANIMAIS':   'MARCELL MORAES',
    'PASTOR ISIDÓRIO FILHO': 'PASTOR SARGENTO ISIDORIO',
    'TOM É MEU AMIGO':       'PASTOR TOM',
    'ÂNGELO CORONEL':        'ANGELO CORONEL FILHO',
    'HERZEM GUSMÃO':         None,  # não existe no TSE BA
    'LEUR LOMANTO JÚNIOR':   None,  # não existe no TSE BA
    'FABRÍCIO FALCÃO':       'FABRICIO FALCAO',
    'HASSAN':                'HASSAN DE ZÉ COCÁ',
}
```

### Fuzzy Match

- **Threshold:** 75% (token_sort_ratio)
- **Biblioteca:** rapidfuzz
- **Taxa de sucesso:** 97,7% (41.444 / 42.440)

### Registros sem `politico_id`

996 registros (2,3%) não têm `politico_id` porque pertencem a:
- **HERZEM GUSMÃO** — não encontrado no TSE BA
- **LEUR LOMANTO JÚNIOR** — não encontrado no TSE BA

Esses deputados podem ser de mandatos anteriores a 2006 ou de outros estados.

---

## Validação

```sql
-- Total geral
SELECT 
  count(*) as total,
  count(politico_id) as com_deputado,
  round(sum(valor_pago)::numeric, 2) as total_gasto,
  count(DISTINCT ano) as anos
FROM alba_verbas_gabinete;
-- Resultado: 42.440 | 41.444 | R$ 284.028.135,84 | 12 anos

-- Por ano
SELECT ano, count(*), round(sum(valor_pago)::numeric, 2) as total
FROM alba_verbas_gabinete
GROUP BY ano ORDER BY ano;

-- Top 10 deputados por gasto
SELECT p.nome_urna, count(*) as registros, round(sum(v.valor_pago)::numeric, 2) as total
FROM alba_verbas_gabinete v
JOIN politicos p ON p.politico_id = v.politico_id
GROUP BY p.nome_urna
ORDER BY total DESC LIMIT 10;

-- Por categoria
SELECT categoria, count(*), round(sum(valor_pago)::numeric, 2) as total
FROM alba_verbas_gabinete
GROUP BY categoria ORDER BY total DESC;
```

---

## Histórico de Versões

### v2 (2026-04-07) — PROMPT 16
- ✅ Reescrita completa usando arquivos Prata
- ✅ PK alterada: `num_processo` → `prisma_id`
- ✅ 42.440 registros (vs 24.974 da v1)
- ✅ Campos adicionais: `url_pdf`, `qualidade_score`, `ano`, `cpf_fornecedor`
- ✅ Mapeamento manual de 10 nomes ALBA → TSE

### v1 (2026-04-06) — PROMPT 15
- ✅ Primeira versão usando arquivos Ouro
- ✅ 24.974 registros carregados
- ⚠️ Descoberta de FKs erradas no schema
- ⚠️ 21 constraints removidas

---

## Dependências

- **Tabela:** `politicos` (para resolução de `politico_id`)
- **Biblioteca:** `rapidfuzz` (fuzzy matching)
- **Python:** 3.11+
- **PostgreSQL:** 15+

---

## Próximos Passos

1. ⏳ Migrar para Supabase (tabela `despesas_gabinete`)
2. ⏳ Validar no dashboard Radar2
3. ⏳ Cruzar com `lista_negra_governo` (fornecedores sancionados)
4. ⏳ Adicionar análise de outliers (gastos anormais)

---

**Tabela destino:** `alba_verbas_gabinete`  
**Banco:** `postgresql://postgres:${DB_PASSWORD}@localhost:5432/prisma_data`
