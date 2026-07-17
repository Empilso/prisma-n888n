-- Migration 005: campos de match investigativo em socios_rf
--
-- socios_rf ja existia (criada fora deste historico de migrations), populada agora
-- pelo dataset oficial de Socios (QSA) da Receita Federal, 2026-07.
--
-- O CPF de pessoa fisica vem mascarado por LGPD no arquivo publico
-- (formato "***XXXXXX**" - só os 6 dígitos do meio aparecem). Não dá pra
-- recalcular o cpf_hash sha256(11 dígitos) usado em pessoas/politicos a partir
-- disso - por isso cpf_hash em socios_rf fica sempre NULL (nunca inventamos
-- um hash de dado parcial). O cruzamento com politicos é feito por
-- corroboração: 6 dígitos do meio do CPF completo (que já temos via TSE, tabela
-- politicos.cpf) + similaridade de nome. Ver .context/MASTER_CONTEXT.md
-- sessão 2026-07-08 para o racional completo.

ALTER TABLE socios_rf
    ADD COLUMN IF NOT EXISTS identificador_socio SMALLINT,      -- 1=PJ 2=PF 3=estrangeiro (layout oficial RF)
    ADD COLUMN IF NOT EXISTS qualificacao_codigo  TEXT,          -- código bruto da RF (tabela Qualificacoes)
    ADD COLUMN IF NOT EXISTS faixa_etaria_codigo  TEXT,          -- código bruto da RF (0-9)
    ADD COLUMN IF NOT EXISTS cpf_meio_visivel     CHAR(6),       -- 6 dígitos visíveis extraídos do CPF mascarado (PF)
    ADD COLUMN IF NOT EXISTS pessoa_id            UUID REFERENCES pessoas(id),
    ADD COLUMN IF NOT EXISTS match_confidence     SMALLINT,      -- 0-100, null = sem match
    ADD COLUMN IF NOT EXISTS match_method         TEXT,          -- 'cpf_parcial+nome' | 'nome_apenas' | null
    ADD COLUMN IF NOT EXISTS fonte_referencia     TEXT DEFAULT 'RFB - Dados Abertos CNPJ (Sócios/QSA)',
    ADD COLUMN IF NOT EXISTS fonte_exercicio      TEXT;          -- ex: '2026-06' (mês/ano do snapshot RF)

CREATE INDEX IF NOT EXISTS idx_socios_cpf_meio    ON socios_rf (cpf_meio_visivel) WHERE cpf_meio_visivel IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_socios_pessoa_id   ON socios_rf (pessoa_id) WHERE pessoa_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_socios_identificador ON socios_rf (identificador_socio);
