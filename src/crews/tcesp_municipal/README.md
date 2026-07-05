# Crew TCE-SP — Fiscal Municipal

Fonte canônica de dados fiscais dos municípios paulistas, via **API oficial do
TCE-SP** (`https://transparencia.tce.sp.gov.br/api/json`). Substitui o fluxo
antigo de CSV manual (`backend/data/tce_sp_real/*.csv` → Supabase
`municipal_revenues`), que fica **deprecated** quando a Fase 2 entrar.

## Por que existe

Auditoria 2026-07-05: a receita de Votorantim exibida no Radar vinha de um CSV
exportado à mão em abril e importado no Supabase SaaS — sem rastreabilidade,
congelado no tempo e no banco errado (dado público deve viver no `prisma_data`).
A API do TCE-SP tem **receitas E despesas** mensais para todos os municípios
fiscalizados — dá pra automatizar tudo.

## Fases

### Fase 1 — Cadastro (esta versão) ✅
Mapa `slug_tcesp ↔ id_ibge` dos ~644 municípios de SP na tabela
`tcesp_municipios`. Sem esse mapa, dado fiscal pode ser associado à cidade
errada. Regra: **sem match confiável, não carrega**.

- Match exato por slug (confidence 1.0) → esperado ~100%
- Fallback fuzzy `SequenceMatcher >= 0.90` (logado, revisável)
- `match_status='manual'`: correção humana via SQL, preservada em re-cargas
- **Exceção documentada:** a capital São Paulo é fiscalizada pelo TCM-SP e não
  aparece na API do TCE-SP.

### Fase 2 — Receitas e despesas (próxima)
- `GET /api/json/receitas/{slug}/{ano}/{mes}` → `tcesp_receitas`
- `GET /api/json/despesas/{slug}/{ano}/{mes}` → `tcesp_despesas`
- `agent_verify`: reconciliação contra CSV local (Votorantim R$ 683M/2025) e
  SICONFI RREO antes de publicar no Radar.
- Piloto: Votorantim (3557006).

## Rodar

```bash
cd n888n-prisma
python src/crews/tcesp_municipal/agent_a_coletor.py   # Bronze
python src/crews/tcesp_municipal/agent_b_normalizador.py  # Prata + match report
python src/crews/tcesp_municipal/agent_c_loader.py    # Ouro (ou --dry-run)
```

Dependências: crew `ibge_municipios` já carregada; `DB_PASSWORD` no `.env`.

## Tabela

`tcesp_municipios(slug_tcesp PK, nome_tcesp, uf, id_ibge FK→municipios,
nome_ibge, match_status, match_confidence, ativo, raw_payload jsonb,
dt_extracao, created_at, updated_at)`
