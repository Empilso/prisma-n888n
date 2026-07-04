-- Migration: Criar tabela alba_parlamentares e enriquecer politicos
-- Data: 2026-04-09

-- 1. Criar tabela para dados ALBA
CREATE TABLE IF NOT EXISTS alba_parlamentares (
    parlamentar_id INTEGER PRIMARY KEY,
    autor_id INTEGER,
    nome_parlamentar TEXT NOT NULL,
    partido_atual TEXT,
    status TEXT,
    foto_url TEXT,
    url_perfil TEXT,
    politico_id TEXT, -- FK lógica para politicos
    match_score FLOAT,
    match_metodo TEXT,
    coletado_em TIMESTAMP DEFAULT NOW(),
    importado_em TIMESTAMP DEFAULT NOW()
);

-- 2. Adicionar colunas extras em politicos (se não existirem)
ALTER TABLE politicos 
ADD COLUMN IF NOT EXISTS alba_parlamentar_id INTEGER,
ADD COLUMN IF NOT EXISTS alba_perfil_url TEXT;

-- 3. Criar índices
CREATE INDEX IF NOT EXISTS idx_alba_politico_id ON alba_parlamentares(politico_id);
CREATE INDEX IF NOT EXISTS idx_politicos_alba_id ON politicos(alba_parlamentar_id);

-- 4. Comentários
COMMENT ON TABLE alba_parlamentares IS 'Dados dos 72 deputados estaduais BA coletados do portal ALBA';
COMMENT ON COLUMN politicos.alba_parlamentar_id IS 'ID do parlamentar no sistema ALBA';
COMMENT ON COLUMN politicos.alba_perfil_url IS 'URL do perfil oficial no portal ALBA';
