# ROADMAP — PRISMA 888 Pipeline ETL

**Última atualização:** 2026-04-09  
**Status geral:** 🟢 Em desenvolvimento ativo

---

## 🎯 Objetivo

Pipeline ETL completo para análise forense de dados governamentais brasileiros, alimentando o dashboard **Radar2** (PRISMA888FORBES).

---

## ✅ Concluído (3 de 26 crews + Enriquecimento)

### Fase 0 — Hub Central
- **ibge_municipios** → 5.571 municípios indexados
- **tse_candidatos** → 802.660 candidaturas (BA, SP, MG, RJ) com `politico_id` estável

### Fase 1 — Dinheiro Direto  
- **alba_verbas_gabinete** → 42.440 registros, R$ 284M (2015-2026)
  - ✅ Links para portal ALBA (`url_detalhe_alba`)
  - ✅ PDFs das notas fiscais (`url_pdf`)

### Enriquecimento de Dados
- **alba_parlamentares** → 72 deputados BA com fotos oficiais
  - ✅ 241 registros atualizados com `foto_url`
  - ✅ Links para perfil ALBA (`alba_perfil_url`)
  - ✅ Taxa de match: 98,6% (71/72)

---

## 🔄 Em Progresso

### Infraestrutura
- ✅ Schema PostgreSQL corrigido (21 FKs removidas)
- ✅ `politico_id` implementado via SHA256 (cross-year tracking)
- ✅ Padrão de estrutura de dados definido (Bronze/Prata/Ouro)
- ✅ Tabela `alba_parlamentares` para dados ricos
- ⏳ Migração para Supabase (pendente)

### Dados
- ✅ TSE: 4 estados carregados (BA, SP, MG, RJ)
- ⏳ TSE: 23 estados restantes
- ✅ ALBA: verbas de gabinete completas
- ✅ ALBA: fotos e perfis de 71 deputados
- ⏳ ALBA: servidores

---

## 📋 Próximos Passos (prioridade)

### Curto Prazo (1-2 semanas)
1. **Expandir TSE** — carregar mais estados (RS, PR, PE, CE, DF)
2. **TSE Receitas** — doações de campanha
3. **Câmara CEAP** — verbas federais
4. **ALBA Servidores** — folha de pagamento

### Médio Prazo (1 mês)
5. **Brasil.io Empresas** — CNPJ e sócios
6. **CGU Lista Negra** — empresas sancionadas
7. **Emendas Federais** — CGU API
8. **Contratos PNCP** — licitações federais

### Longo Prazo (2-3 meses)
9. **TCM-BA** — contratos municipais
10. **TCE-BA** — contratos estaduais
11. **DOE-BA** — diário oficial
12. **CNJ Processos** — ações judiciais

---

## 🏗️ Arquitetura

### Camadas de Dados
```
dados_brutos/  → CSVs, JSONs, PDFs originais (imutável)
bronze/        → JSON com SHA256 (rastreabilidade)
prata/         → JSON normalizado e validado
ouro/          → JSON enriquecido (opcional)
rejeitados/    → Registros inválidos com motivo
```

### Padrão de Crew (3 agentes)
```
agent_a_coletor.py      → Fonte → Bronze
agent_b_normalizador.py → Bronze → Prata
agent_c_loader.py       → Prata → PostgreSQL
```

### Banco de Dados
- **Local:** PostgreSQL 15 (`prisma_data`)
- **Produção:** Supabase (migração pendente)
- **Tabelas principais:** `politicos`, `alba_verbas_gabinete`, `alba_parlamentares`, `municipios`

---

## 📊 Métricas Atuais

| Métrica | Valor |
|---------|-------|
| Crews completas | 3 / 26 (11,5%) |
| Registros no banco | ~850k |
| Estados TSE | 4 / 27 (14,8%) |
| Valor total verbas ALBA | R$ 284M |
| Anos cobertos ALBA | 2015-2026 (12 anos) |
| Deputados BA com foto | 71 / 72 (98,6%) |
| Tempo médio de carga | ~30s por crew |

---

## 🚧 Desafios Técnicos Resolvidos

1. ✅ **politico_id estável** — hash SHA256 para tracking cross-year
2. ✅ **FKs problemáticas** — removidas 21 constraints erradas
3. ✅ **Fuzzy matching de nomes** — 97,7% de match ALBA ↔ TSE
4. ✅ **Deduplicação por prisma_id** — PK única via MD5
5. ✅ **Validação de datas** — rejeição de datas inválidas
6. ✅ **URLs duplicadas** — correção automática de fotos ALBA
7. ✅ **Enriquecimento de perfis** — 241 registros com foto oficial

---

## 🎯 Metas 2026 Q2

- [ ] 10 crews completas (38%)
- [ ] TSE completo (27 estados)
- [ ] Fase 1 completa (Dinheiro Direto)
- [x] Fotos de deputados BA (98,6% concluído)
- [ ] Dashboard Radar2 100% funcional
- [ ] Migração Supabase concluída

---

## 📝 Notas

- **Sem Supabase até tudo pronto** — desenvolvimento 100% local
- **Prioridade: dados > frontend** — backend primeiro
- **Qualidade > velocidade** — validação rigorosa
- **Documentação contínua** — cada crew tem README próprio
- **Enriquecimento progressivo** — dados ALBA complementam TSE

---

## 📅 Changelog Recente

### 2026-04-09
- ✅ Adicionado campo `url_detalhe_alba` em verbas de gabinete
- ✅ Criada tabela `alba_parlamentares` (72 deputados)
- ✅ Importadas fotos oficiais de 71 deputados BA
- ✅ API de verbas corrigida (Supabase → PostgreSQL local)
- ✅ Frontend preparado para exibir fotos automaticamente

### 2026-04-07
- ✅ ALBA verbas de gabinete completa (42.440 registros)

### 2026-04-06
- ✅ TSE candidatos BA completo (802.660 registros)
- ✅ IBGE municípios completo (5.571 registros)

---

**Repositório:** `n888n-prisma/`  
**Banco:** `postgresql://postgres:${DB_PASSWORD}@localhost:5432/prisma_data`  
**Docs:** `docs/`, `ZnOTAÇÕES/PROMPTS/`
