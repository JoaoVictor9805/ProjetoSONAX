-- ============================================================================
-- Migração 004: Adicionar flags de investigação de SPIN Selling na tabela analise_spin
-- Flags booleanas ('s'/'n') para cada uma das 4 dimensões do SPIN Selling:
-- situacao_investigada, problema_investigado, implicacao_investigada, necessidade_investigada.
-- Permite ao Power BI calcular indicadores e frequências de execução sem depender de parsing de texto livre.
-- ============================================================================

ALTER TABLE analise_spin 
ADD COLUMN IF NOT EXISTS situacao_investigada VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (situacao_investigada IN ('s', 'n'));

ALTER TABLE analise_spin 
ADD COLUMN IF NOT EXISTS problema_investigado VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (problema_investigado IN ('s', 'n'));

ALTER TABLE analise_spin 
ADD COLUMN IF NOT EXISTS implicacao_investigada VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (implicacao_investigada IN ('s', 'n'));

ALTER TABLE analise_spin 
ADD COLUMN IF NOT EXISTS necessidade_investigada VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (necessidade_investigada IN ('s', 'n'));

-- Normaliza e backfill de registros legados com base na presença de texto substantivo
UPDATE analise_spin
SET 
    situacao_investigada = CASE 
        WHEN situacao IS NOT NULL AND TRIM(situacao) NOT IN ('Não se aplica', 'não informado', 'Nenhum', '', 'null', 'none') THEN 's' 
        ELSE 'n' 
    END,
    problema_investigado = CASE 
        WHEN problema IS NOT NULL AND TRIM(problema) NOT IN ('Não se aplica', 'não informado', 'Nenhum', '', 'null', 'none') THEN 's' 
        ELSE 'n' 
    END,
    implicacao_investigada = CASE 
        WHEN implicacao IS NOT NULL AND TRIM(implicacao) NOT IN ('Não se aplica', 'não informado', 'Nenhum', '', 'null', 'none') THEN 's' 
        ELSE 'n' 
    END,
    necessidade_investigada = CASE 
        WHEN necessidade_solucao IS NOT NULL AND TRIM(necessidade_solucao) NOT IN ('Não se aplica', 'não informado', 'Nenhum', '', 'null', 'none') THEN 's' 
        ELSE 'n' 
    END;
