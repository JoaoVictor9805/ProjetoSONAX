-- ============================================================================
-- Migração 010: Alinhar constraints CHECK de crm.acao e
-- analise_perfil.faturamento_regra ao padrão do código e de copia_bd_final.sql
--
-- Problemas corrigidos:
--   1. crm.acao: constraint antiga aceitava 'não se aplica' (minúsculo),
--      enquanto o código/schema define 'Não se aplica' (N maiúsculo).
--   2. analise_perfil.faturamento_regra: constraint antiga aceitava valores
--      com espaço/acento ('declarado mensal', 'calculado 12 meses',
--      'não confirmado', 'não informado'), enquanto o código/schema define
--      'declarado_mensal', 'calculado_12_meses', 'nao_confirmado', 'nao_informado'.
-- ============================================================================

BEGIN;

-- 1. Tabela crm (acao)
ALTER TABLE crm DROP CONSTRAINT IF EXISTS crm_acao_check;
ALTER TABLE crm DROP CONSTRAINT IF EXISTS chk_crm_acao;

UPDATE crm
SET acao = 'Não se aplica'
WHERE acao IS NOT NULL
  AND LOWER(TRIM(acao)) IN ('não se aplica', 'nao se aplica')
  AND acao <> 'Não se aplica';

ALTER TABLE crm
ADD CONSTRAINT crm_acao_check
CHECK (acao IS NULL OR acao IN (
    'reunião confirmada',
    'reunião proposta sem aceite',
    'retorno com data combinado',
    'envio de material solicitado',
    'sem próximo passo definido',
    'sem interesse explícito',
    'Não se aplica'
));

-- 2. Tabela analise_perfil (faturamento_regra)
ALTER TABLE analise_perfil DROP CONSTRAINT IF EXISTS analise_perfil_faturamento_regra_check;
ALTER TABLE analise_perfil DROP CONSTRAINT IF EXISTS chk_analise_perfil_faturamento_regra;

UPDATE analise_perfil
SET faturamento_regra = CASE LOWER(TRIM(faturamento_regra))
    WHEN 'declarado mensal' THEN 'declarado_mensal'
    WHEN 'calculado 12 meses' THEN 'calculado_12_meses'
    WHEN 'não confirmado' THEN 'nao_confirmado'
    WHEN 'nao confirmado' THEN 'nao_confirmado'
    WHEN 'não informado' THEN 'nao_informado'
    WHEN 'nao informado' THEN 'nao_informado'
    ELSE faturamento_regra
END
WHERE LOWER(TRIM(faturamento_regra)) IN (
    'declarado mensal',
    'calculado 12 meses',
    'não confirmado',
    'nao confirmado',
    'não informado',
    'nao informado'
);

ALTER TABLE analise_perfil
ADD CONSTRAINT analise_perfil_faturamento_regra_check
CHECK (faturamento_regra IN (
    'declarado_mensal',
    'calculado_12_meses',
    'nao_confirmado',
    'nao_informado'
));

COMMIT;
