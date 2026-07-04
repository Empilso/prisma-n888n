-- Migration: Adicionar coluna url_detalhe_alba
-- Data: 2026-04-09
-- Descrição: Link para página de detalhe no portal ALBA (ex: /transparencia/verbas-idenizatorias/99643/)

-- Adicionar coluna na tabela alba_verbas_gabinete
ALTER TABLE alba_verbas_gabinete 
ADD COLUMN IF NOT EXISTS url_detalhe_alba TEXT;

-- Comentário explicativo
COMMENT ON COLUMN alba_verbas_gabinete.url_detalhe_alba IS 
'URL completa para página de detalhe do registro no portal ALBA (ex: https://www.al.ba.gov.br/transparencia/verbas-idenizatorias/99643/)';

-- Verificar se a coluna foi criada
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'alba' 
  AND table_name = 'verbas_gabinete' 
  AND column_name = 'url_detalhe_alba';
