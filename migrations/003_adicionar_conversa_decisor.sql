-- ============================================================================
-- Migração 003: Adicionar campo conversa_decisor na tabela avaliacao_ia
-- Flag booleana ('s'/'n') identificando se houve conversa com decisor ou influenciador.
-- ============================================================================

ALTER TABLE avaliacao_ia 
ADD COLUMN IF NOT EXISTS conversa_decisor VARCHAR(1) DEFAULT 'n' CHECK (conversa_decisor IN ('s', 'n'));

-- Normaliza registros legados (se houver)
UPDATE avaliacao_ia 
SET conversa_decisor = 'n' 
WHERE conversa_decisor IS NULL;
