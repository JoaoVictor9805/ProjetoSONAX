-- ============================================================================
-- Migração 005: Criar tabela avaliacao_oportunidade_treinamento (N:N)
-- Remove a relação 1:1 de codigo_oportunidade em avaliacao_sdr e cria a tabela
-- de relacionamento N:N para suportar múltiplas oportunidades de treinamento por chamada.
-- ============================================================================

CREATE TABLE IF NOT EXISTS avaliacao_oportunidade_treinamento (
    log VARCHAR(255) NOT NULL,
    codigo_oportunidade VARCHAR(20) NOT NULL,
    
    PRIMARY KEY (log, codigo_oportunidade),
    FOREIGN KEY (log) REFERENCES avaliacao_sdr(log) ON DELETE CASCADE,
    FOREIGN KEY (codigo_oportunidade) REFERENCES dim_oportunidade_treinamento(codigo)
);

-- Backfill seguro e remoção da coluna antiga caso exista
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'avaliacao_sdr' AND column_name = 'codigo_oportunidade'
    ) THEN
        INSERT INTO avaliacao_oportunidade_treinamento (log, codigo_oportunidade)
        SELECT log, codigo_oportunidade
        FROM avaliacao_sdr
        WHERE codigo_oportunidade IS NOT NULL
        ON CONFLICT (log, codigo_oportunidade) DO NOTHING;
        
        ALTER TABLE avaliacao_sdr DROP COLUMN IF EXISTS codigo_oportunidade;
    END IF;
END $$;
