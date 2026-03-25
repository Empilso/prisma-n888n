-- Schema ALBA: Verbas Indenizatórias
CREATE SCHEMA IF NOT EXISTS alba;

CREATE TABLE alba.verbas_indenizatorias (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    num_processo VARCHAR(50),
    nm_deputado VARCHAR(200),
    ds_verba VARCHAR(200),
    nm_fornecedor VARCHAR(300),
    cnpj_fornecedor VARCHAR(14),
    dt_emissao DATE,
    vl_reembolso DECIMAL(15, 2),
    slug_url_anexo TEXT,
    raw_hash TEXT UNIQUE, -- Controle de CDC
    dt_carga TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Schema Transparência BA: Emendas Parlamentares
CREATE SCHEMA IF NOT EXISTS transp_ba;

CREATE TABLE transp_ba.emendas_2026 (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ano_referencia INTEGER DEFAULT 2026,
    nm_parlamentar VARCHAR(200),
    ds_emenda TEXT,
    vl_empenhado DECIMAL(15, 2),
    vl_pago DECIMAL(15, 2),
    nm_municipio_beneficiado VARCHAR(200),
    status_execucao VARCHAR(100),
    raw_hash TEXT UNIQUE,
    dt_carga TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Tabela Global de Fornecedores (Referência Brasil.IO)
CREATE TABLE public.fornecedores (
    cnpj VARCHAR(14) PRIMARY KEY,
    razao_social VARCHAR(300),
    nome_fantasia VARCHAR(300),
    situacao_cadastral VARCHAR(100),
    cnae_principal VARCHAR(20),
    dt_abertura DATE
);

CREATE INDEX idx_alba_cnpj ON alba.verbas_indenizatorias (cnpj_fornecedor);
CREATE INDEX idx_transp_mun ON transp_ba.emendas_2026 (nm_municipio_beneficiado);
