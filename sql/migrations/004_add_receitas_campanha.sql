-- Migration 004: Tabela receitas_campanha
CREATE TABLE IF NOT EXISTS receitas_campanha (
    id              BIGSERIAL    PRIMARY KEY,
    prisma_id       TEXT         UNIQUE NOT NULL,
    politico_id     TEXT,
    sq_candidato    TEXT,
    doador_cnpj_cpf TEXT,
    doador_nome     TEXT,
    doador_nome_rfb TEXT,
    valor           NUMERIC(14,2),
    data_receita    DATE,
    fonte_recurso   TEXT,
    especie_recurso TEXT,
    ano_eleicao     SMALLINT,
    uf              CHAR(2),
    cargo           TEXT,
    sigla_partido   TEXT,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_receitas_politico_id  ON receitas_campanha (politico_id);
CREATE INDEX IF NOT EXISTS idx_receitas_doador_cnpj  ON receitas_campanha (doador_cnpj_cpf);
CREATE INDEX IF NOT EXISTS idx_receitas_ano_uf       ON receitas_campanha (ano_eleicao, uf);
