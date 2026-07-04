# STATUS — PRISMA 888 ETL Pipeline

**Data:** 2026-04-07 (origem) — atualizado em 2026-06-19
**Sessão:** Prompts 10-16 (origem) — sessão 2026-06-19 adicionou 4 crews em paralelo

---

## 🆕 2026-06-19 — Frente legislativa + fiscal (crews em construção paralela)

Quatro crews iniciadas em paralelo nesta sessão. Status: **EM CONSTRUÇÃO** (agentes paralelos rodando). Validação ponta-a-ponta é trabalho separado.

| Crew | Origem | Destino (`prisma_data`) | Cobertura | Origem do código |
|---|---|---|---|---|
| `camara_proposicoes` | API Câmara dos Deputados | `camara_proposicoes` | Legislaturas 55-57 (2015-2026) | Nova |
| `camara_votacoes` (extensão) | API Câmara | `camara_votacoes` + `camara_votos_nominais` | Continua 163k votos já carregados | Extensão da existente |
| `senado_proposicoes` + `senado_votacoes` | API Senado (`legis.senado.leg.br`) | `senado_proposicoes` + `senado_votacoes` + `senado_votos_nominais` | A definir pelos agentes | **DO ZERO** |
| `siconfi_universal` | API SICONFI (Tesouro Nacional) | `siconfi_rreo` + `siconfi_dca` + `siconfi_rgf` | 27 estados + 5.570 municípios | **DO ZERO** |

**Pendente após sessão:** validar workers ponta-a-ponta, conectar a endpoints FastAPI no PRISMA888FORBES e a tabs do dossier (matriz `cargo-tab-matrix.ts` no frontend já prevê posições).

**Gaps assumidos (NÃO iniciados):** ALMG, BA emendas via Playwright (CKAN sem autor), SAPL genérico (vereadores 600+ câmaras), TransfereGov convênios, PNCP contratos, DOE-BA, TCE/TCM-BA contratos.

---

## 📍 Onde Estamos

### ✅ Completado

**Infraestrutura:**
- Schema PostgreSQL corrigido (21 FKs removidas)
- `politico_id` implementado (SHA256 para tracking cross-year)
- Padrão de estrutura de dados definido (Bronze/Prata/Ouro/Rejeitados)
- 26 crews mapeadas com `crew_manifest.json`

**Dados Carregados:**
- **IBGE:** 5.571 municípios
- **TSE Candidatos:** 802.660 registros (BA, SP, MG, RJ | 2006-2024)
  - 609.080 pessoas únicas via `politico_id`
- **ALBA Verbas:** 42.440 registros, R$ 284M (2015-2026)
  - 97,7% com `politico_id` resolvido via fuzzy match

**Crews Completas:**
1. `ibge_municipios` (Fase 0)
2. `tse_candidatos` (Fase 0)
3. `alba_verbas_gabinete` (Fase 1)

---

## 🔧 Problemas Resolvidos

### PROMPT 10 v2 — politico_id Estável
- Implementado hash SHA256 para tracking de políticos entre anos
- Lógica: CPF → hash direto | Sem CPF → hash(nome+nascimento+uf)
- Índice de reuso: quem aparece com CPF depois reutiliza o hash
- Resultado: 0 NULLs em 802k registros

### PROMPT 13 — Reorganização de Estrutura
- Migração de dados para padrão Bronze/Prata/Ouro
- 26 crews criadas com manifests
- Validação de datas (rejeição de inválidas)
- Truncamento de `uf_nascimento` para CHAR(2)

### PROMPT 15 — ALBA Verbas (tentativa 1)
- Carregamento inicial de arquivos Ouro
- Descoberta de FKs erradas no schema
- 21 constraints removidas (politicos + fornecedores_rf)
- Mapeamento manual de 12 nomes ALBA → TSE

### PROMPT 16 — ALBA Verbas v2
- Reescrita do loader usando arquivos Prata
- PK corrigida: `num_processo` → `prisma_id` (MD5 único)
- 42.440 registros carregados (vs 24.974 da v1)
- Dados mais ricos: `url_pdf`, `qualidade_score`, `ano`

---

## 📊 Métricas

| Indicador | Valor |
|-----------|-------|
| Crews completas | 3 / 26 (11,5%) |
| Registros totais | ~850.000 |
| Estados TSE | 4 / 27 (BA, SP, MG, RJ) |
| Valor ALBA | R$ 284.028.135,84 |
| Match rate ALBA | 97,7% (41.444 / 42.440) |
| Tempo médio carga | 20-30s por crew |

---

## 🎯 Próximos Passos

### Imediato
1. **Expandir TSE** — carregar RS, PR, PE, CE, DF (5 estados)
2. **TSE Receitas** — doações de campanha
3. **Validar Radar2** — testar dashboard com dados reais

### Curto Prazo
4. **Câmara CEAP** — verbas federais
5. **ALBA Servidores** — folha de pagamento
6. **Brasil.io Empresas** — CNPJ e sócios

### Médio Prazo
7. **CGU Lista Negra** — cruzamento com verbas
8. **Emendas Federais** — CGU API
9. **Migração Supabase** — quando tudo estiver validado

---

## 🚨 Pendências Conhecidas

- **996 registros ALBA sem `politico_id`** — HERZEM GUSMÃO e LEUR LOMANTO JÚNIOR (não existem no TSE BA)
- **Frontend aponta para Supabase** — dados estão no PostgreSQL local
- **23 estados TSE faltando** — priorizar estados grandes (RS, PR, PE)
- **Fornecedores_rf vazia** — tabela existe mas sem dados (FK removida)

---

## 📝 Decisões Técnicas

1. **Sem FKs para `politico_id`** — referência lógica, não constraint (permite duplicatas na tabela `politicos`)
2. **Sem FKs para `cnpj_fornecedor`** — tabela `fornecedores_rf` será carregada depois
3. **Supabase só no final** — desenvolvimento 100% local até validação completa
4. **Prioridade: backend > frontend** — dados corretos primeiro, UI depois

---

## 🔗 Arquivos Importantes

- `README.md` — visão geral do projeto
- `ROADMAP.md` — planejamento de longo prazo
- `docs/PADRAO_ESTRUTURA_DADOS.md` — padrão Bronze/Prata/Ouro
- `sql/schema.sql` — schema PostgreSQL (PRISMA-DADOS2)
- `src/crews/*/crew_manifest.json` — metadados de cada crew

---

**Banco:** `postgresql://postgres:${DB_PASSWORD}@localhost:5432/prisma_data`  
**Projeto:** `/home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma/`
