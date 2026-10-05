-- ============================================================================
-- Migração 001: Criar tabela analise_perfil e enriquecer tabela empresa
-- Responsável por registrar a qualificação de perfil (setor, regime, faturamento)
-- com granularidade por chamada e rastreamento da confiabilidade da fonte.
-- ============================================================================

-- 1. Enriquecer tabela empresa com campos de faturamento e origens
ALTER TABLE empresa ADD COLUMN IF NOT EXISTS faturamento_anual NUMERIC(15,2);
ALTER TABLE empresa ADD COLUMN IF NOT EXISTS setor_origem VARCHAR(50);
ALTER TABLE empresa ADD COLUMN IF NOT EXISTS regime_origem VARCHAR(50);
ALTER TABLE empresa ADD COLUMN IF NOT EXISTS faturamento_origem VARCHAR(50);

-- Conversão segura de faturamento_mensal de VARCHAR para NUMERIC se ainda não for
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'empresa' AND column_name = 'faturamento_mensal' AND data_type != 'numeric'
    ) THEN
        ALTER TABLE empresa ALTER COLUMN faturamento_mensal TYPE NUMERIC(15,2) 
        USING (NULLIF(regexp_replace(faturamento_mensal, '[^0-9.]', '', 'g'), '')::NUMERIC);
    END IF;
END $$;

-- 2. Criar tabela analise_perfil (vinculada a avaliacao_ia pelo log)
CREATE TABLE IF NOT EXISTS analise_perfil (
    log VARCHAR(255) PRIMARY KEY NOT NULL,
    setor VARCHAR(50) CHECK (setor IS NULL OR setor IN (
        'industrial',
        'outro confirmado',
        'não informado'
    )),
    setor_origem VARCHAR(50) NOT NULL CHECK (setor_origem IN (
        'confirmado pelo interlocutor',
        'afirmado apenas pelo SDR',
        'inferência plausível',
        'não informado'
    )),
    regime_tributario VARCHAR(50),
    regime_origem VARCHAR(50) NOT NULL CHECK (regime_origem IN (
        'confirmado pelo interlocutor',
        'afirmado apenas pelo SDR',
        'inferência plausível',
        'não informado'
    )),
    faturamento_declarado_texto TEXT,
    faturamento_anual NUMERIC(15,2),
    faturamento_mensal NUMERIC(15,2),
    periodo_meses INT,
    faturamento_origem VARCHAR(50) NOT NULL CHECK (faturamento_origem IN (
        'confirmado pelo interlocutor',
        'afirmado apenas pelo SDR',
        'inferência plausível',
        'não informado',
        'calculado'
    )),
    faturamento_regra VARCHAR(50) NOT NULL CHECK (faturamento_regra IN (
        'declarado_mensal',
        'calculado_12_meses',
        'nao_confirmado',
        'nao_informado'
    )),
    detalhes_faturamento TEXT,
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log) ON DELETE CASCADE
);
