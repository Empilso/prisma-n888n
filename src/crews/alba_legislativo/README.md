# ALBA Legislativo

**Status:** ✅ Implementado 2026-07-19
**Tabelas:** `alba_proposicoes`, `alba_comissoes`
**Fonte:** API pública oficial ALBA (NoPaperCloud) — `/api/publico/proposicao`, `/api/publico/comissoes`

## O que extrai
Produção legislativa (proposições: PL, IND, MOC, REQ…) e participação em comissões
(com cargo Presidente/Vice/Titular) de cada deputado estadual da Bahia.

## Pegadinha da API (recon 2026-07-19)
A API **só pagina por `?autorId=`** — o param `pg` é ignorado (pg1=pg2=pg3) e
`qtd` grande dá timeout. Por isso o coletor itera os `autor_id` de
`alba_parlamentares` e busca `?autorId={id}&qtd=3000`. Bônus: já vem pré-atribuído
a politico_id (autorId→alba_parlamentares.politico_id; fallback por CPF).

## Rodar
```
python agent_a_coletor.py --recurso todos        # API → bronze (por autor)
python agent_b_normalizador.py --recurso todos    # bronze → prata + match politico_id
python agent_c_loader.py --recurso todos          # prata → Postgres (TRUNCATE+load)
```

## Fase 2 pendente
Frequência/presença por sessão plenária (a API pública não expõe direto — precisa
de outra rota do NoPaperCloud ou raspagem da aba "presença" do perfil).
