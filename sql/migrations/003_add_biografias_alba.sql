-- Migration: Adicionar biografias completas ALBA
-- Data: 2026-04-09
-- Fonte: parlamentares_hub_normalized.json (149 deputados)

-- 1. Criar tabela para biografias ALBA
CREATE TABLE IF NOT EXISTS alba_biografias (
    prisma_id TEXT PRIMARY KEY,
    parlamentar_id TEXT,
    politico_id TEXT, -- FK lógica para politicos
    nome_eleitoral TEXT,
    nome_civil TEXT,
    biografia_completa TEXT,
    dados_pessoais JSONB,
    mandatos JSONB,
    filiacao_partidaria JSONB,
    profissao TEXT,
    data_nascimento DATE,
    municipio_nascimento TEXT,
    uf_nascimento TEXT,
    sexo TEXT,
    conjuge TEXT,
    filhos TEXT,
    foto_url TEXT,
    url_oficial TEXT,
    resumo_executivo TEXT,
    qualidade_score FLOAT,
    match_score FLOAT,
    match_metodo TEXT,
    importado_em TIMESTAMP DEFAULT NOW()
);

-- 2. Adicionar colunas em politicos (se não existirem)
ALTER TABLE politicos
ADD COLUMN IF NOT EXISTS biografia_completa TEXT,
ADD COLUMN IF NOT EXISTS biografia_resumo TEXT,
ADD COLUMN IF NOT EXISTS dados_pessoais JSONB,
ADD COLUMN IF NOT EXISTS mandatos_historico JSONB,
ADD COLUMN IF NOT EXISTS filiacao_partidaria JSONB,
ADD COLUMN IF NOT EXISTS profissao TEXT,
ADD COLUMN IF NOT EXISTS municipio_nascimento TEXT,
ADD COLUMN IF NOT EXISTS conjuge TEXT,
ADD COLUMN IF NOT EXISTS filhos TEXT,
ADD COLUMN IF NOT EXISTS url_oficial_alba TEXT,
ADD COLUMN IF NOT EXISTS formacao_academica JSONB,
ADD COLUMN IF NOT EXISTS carreira_politica JSONB;

-- 3. Criar índices
CREATE INDEX IF NOT EXISTS idx_alba_bio_politico_id ON alba_biografias(politico_id);
CREATE INDEX IF NOT EXISTS idx_alba_bio_parlamentar_id ON alba_biografias(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_politicos_profissao ON politicos(profissao);

-- 4. Comentários
COMMENT ON TABLE alba_biografias IS 'Biografias completas de 149 deputados BA coletadas do portal ALBA';
COMMENT ON COLUMN politicos.biografia_completa IS 'Biografia completa do deputado (texto longo)';
COMMENT ON COLUMN politicos.biografia_resumo IS 'Resumo executivo da biografia';
COMMENT ON COLUMN politicos.dados_pessoais IS 'Dados pessoais estruturados (JSONB)';
COMMENT ON COLUMN politicos.mandatos_historico IS 'Histórico completo de mandatos (JSONB)';
COMMENT ON COLUMN politicos.filiacao_partidaria IS 'Histórico de filiação partidária (JSONB)';
COMMENT ON COLUMN politicos.formacao_academica IS 'Formação acadêmica estruturada (JSONB)';
COMMENT ON COLUMN politicos.carreira_politica IS 'Carreira política estruturada (JSONB)';
