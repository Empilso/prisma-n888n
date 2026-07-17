-- Migration 007: tabelas de ranking pré-computadas pra Rede Societária
--
-- Agregações sobre emendas_federais_pagamentos (1,7M linhas), camara_verbas_ceap
-- (2,5M) e socios_rf (27,8M) são caras demais pra rodar a cada visita de
-- página. Pré-computamos aqui e um script repopula sob demanda (ver
-- backend/src/workers/rankings_rede_societaria_worker.py).

CREATE TABLE IF NOT EXISTS ranking_empresas_verba (
    cnpj_raiz       TEXT PRIMARY KEY,
    nome            TEXT,
    total_emendas   NUMERIC(16,2) NOT NULL DEFAULT 0,
    total_ceap      NUMERIC(16,2) NOT NULL DEFAULT 0,
    total_geral     NUMERIC(16,2) NOT NULL DEFAULT 0,
    qtd_politicos   INTEGER NOT NULL DEFAULT 0,
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ranking_empresas_total ON ranking_empresas_verba (total_geral DESC);

CREATE TABLE IF NOT EXISTS ranking_lista_negra_verba (
    cnpj_raiz       TEXT PRIMARY KEY,
    nome            TEXT,
    tipo_punicao    TEXT,
    orgao_sancionador TEXT,
    total_recebido  NUMERIC(16,2) NOT NULL DEFAULT 0,
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ranking_lneg_total ON ranking_lista_negra_verba (total_recebido DESC);

CREATE TABLE IF NOT EXISTS ranking_socios_rede (
    cpf_meio_visivel  TEXT NOT NULL,
    nome_socio        TEXT NOT NULL,
    qtd_empresas      INTEGER NOT NULL,
    cnpjs_raiz        TEXT[] NOT NULL,
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cpf_meio_visivel, nome_socio)
);
CREATE INDEX IF NOT EXISTS idx_ranking_socios_qtd ON ranking_socios_rede (qtd_empresas DESC);

CREATE TABLE IF NOT EXISTS politico_socio_matches (
    id                BIGSERIAL PRIMARY KEY,
    politico_id       TEXT NOT NULL,
    politico_nome     TEXT NOT NULL,
    politico_cargo    TEXT,
    politico_uf       TEXT,
    cnpj_raiz         TEXT NOT NULL,
    nome_socio        TEXT NOT NULL,
    qualificacao      TEXT,
    confianca_pct     SMALLINT NOT NULL,
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_psm_politico ON politico_socio_matches (politico_id);
CREATE INDEX IF NOT EXISTS idx_psm_confianca ON politico_socio_matches (confianca_pct DESC);
