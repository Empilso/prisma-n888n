# Crew — TSE Votos por Seção/Local (`tse_votos_cache`)

**Status:** ✅ Ativo (v1.0, 2026-07-16)
**Fase:** 0 — Hub Central
**Tabela destino:** `tse_votos_cache` (Postgres local `prisma_data`)
**Portal:** TSE — Votação por Seção Eleitoral (CDN `cdn.tse.jus.br`)

Carrega a **votação por seção eleitoral** do TSE (agregada por município ×
zona × local × candidato × turno). É a tabela que alimenta os mapas eleitorais
do Forbes (`/api/tse/votos-candidato`, `gerar-csv`, modo performance do mapa).

## Uso

```bash
cd n888n-prisma/src/crews/tse_votos_municipio
# DB_PASSWORD precisa estar no ambiente (ex.: source do backend/.env do Forbes)
python main.py --ano 2022 --uf SP            # deputados/senador/governador SP
python main.py --ano 2022 --uf 7ufs          # BA MG PE PR RJ RS SP
python main.py --ano 2018 --uf BA --force    # recarrega do zero
```

- **Idempotente**: pode rodar de novo à vontade (ON CONFLICT DO UPDATE).
- **Retomável**: ZIP fica em `data/tse_votos_municipio/raw/` — se cair no meio,
  roda de novo e pula o download.
- **RAM segura**: o ZIP vai pra disco e o CSV é lido em streaming (o endpoint
  antigo do Forbes carregava 769 MB na RAM — este crew não).
- Status por UF/ano: `SELECT * FROM tse_votos_cache_status;`

## O que cada eleição traz

| Ano | Tipo | Cargos |
|---|---|---|
| 2024, 2020, 2016, 2012 | Municipal | Prefeito, Vereador |
| 2022, 2018, 2014, 2010 | Geral | Dep. Federal, Dep. Estadual, Senador, Governador, Presidente |

## Estado das cargas (2026-07-16)

- 2024: 7 UFs prontas (BA MG PE PR RJ RS SP) — 6,4M registros (via endpoint Forbes).
- 2022: em carga a partir de 2026-07-16 (começando por SP) — habilita voto real
  de deputados no mapa territorial estadual do Forbes.

## Verificação pós-carga

```sql
SELECT ano_eleicao, sg_uf, ds_cargo, COUNT(*), SUM(qt_votos)
FROM tse_votos_cache
WHERE ano_eleicao = 2022
GROUP BY 1,2,3 ORDER BY 2,3;
```

Conferir contra os totais oficiais do TSE antes de citar qualquer número
(protocolo zero-tolerância a dado errado).
