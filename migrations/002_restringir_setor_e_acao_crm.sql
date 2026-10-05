-- ============================================================================
-- Migração 002: Restringir setor em analise_perfil e acao em crm
-- Garante integridade referencial com os domínios de negócio definidos:
-- - analise_perfil.setor: 'industrial', 'outro confirmado', 'não informado'
-- - crm.acao: 'reunião confirmada', 'reunião proposta sem aceite',
--             'retorno com data combinado', 'envio de material solicitado',
--             'sem próximo passo definido', 'sem interesse explícito', 'Não se aplica'
-- ============================================================================

-- 1. Normalizar dados existentes em analise_perfil (se houver)
UPDATE analise_perfil 
SET setor = 'não informado' 
WHERE setor IS NULL OR setor NOT IN ('industrial', 'outro confirmado', 'não informado');

-- 2. Adicionar constraint CHECK em analise_perfil.setor
ALTER TABLE analise_perfil 
DROP CONSTRAINT IF EXISTS chk_analise_perfil_setor;

ALTER TABLE analise_perfil 
ADD CONSTRAINT chk_analise_perfil_setor 
CHECK (setor IS NULL OR setor IN ('industrial', 'outro confirmado', 'não informado'));

-- 3. Adicionar constraint CHECK em crm.acao
ALTER TABLE crm 
DROP CONSTRAINT IF EXISTS chk_crm_acao;

ALTER TABLE crm 
ADD CONSTRAINT chk_crm_acao 
CHECK (acao IS NULL OR acao IN (
    'reunião confirmada',
    'reunião proposta sem aceite',
    'retorno com data combinado',
    'envio de material solicitado',
    'sem próximo passo definido',
    'sem interesse explícito',
    'Não se aplica'
));
