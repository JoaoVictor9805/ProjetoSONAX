-- ============================================================================
-- MIGRATION 002: Padronização e Limpeza dos Dados de analise_perfil
-- ============================================================================

-- 1. Atualizar constraint de faturamento_regra para aceitar textos padronizados em linguagem natural
ALTER TABLE analise_perfil DROP CONSTRAINT IF EXISTS analise_perfil_faturamento_regra_check;

-- 2. Migrar registros antigos de faturamento_regra para os novos valores
UPDATE analise_perfil SET faturamento_regra = 'declarado mensal' WHERE faturamento_regra = 'declarado_mensal';
UPDATE analise_perfil SET faturamento_regra = 'calculado 12 meses' WHERE faturamento_regra = 'calculado_12_meses';
UPDATE analise_perfil SET faturamento_regra = 'não confirmado' WHERE faturamento_regra = 'nao_confirmado';
UPDATE analise_perfil SET faturamento_regra = 'não informado' WHERE faturamento_regra = 'nao_informado' OR faturamento_regra IS NULL;

-- 3. Recriar constraint de faturamento_regra com os novos valores oficiais
ALTER TABLE analise_perfil ADD CONSTRAINT analise_perfil_faturamento_regra_check 
    CHECK (faturamento_regra IN ('declarado mensal', 'calculado 12 meses', 'não confirmado', 'não informado'));

-- 4. Atualizar regime_tributario: campos vazios, nulos ou 'Não se aplica' viram 'não informado'
UPDATE analise_perfil 
SET regime_tributario = 'não informado' 
WHERE regime_tributario IS NULL OR TRIM(regime_tributario) = '' OR regime_tributario = 'Não se aplica';

-- 5. Atualizar faturamento_declarado_texto: 'Não se aplica', nulos ou vazios viram 'não informado'
UPDATE analise_perfil 
SET faturamento_declarado_texto = 'não informado' 
WHERE faturamento_declarado_texto = 'Não se aplica' OR faturamento_declarado_texto IS NULL OR TRIM(faturamento_declarado_texto) = '';

UPDATE analise_perfil
SET detalhes_faturamento = 'não se aplica'
WHERE detalhes_faturamento = 'Não se aplica'