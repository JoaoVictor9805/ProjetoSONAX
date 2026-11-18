-- ============================================================================
-- MIGRATION 003: Padronização de CRM, Analise BANT e Empresa
-- ============================================================================

-- 1. TABELA EMPRESA: Definir defaults para 'não informado' e converter NULLs
ALTER TABLE empresa ALTER COLUMN setor SET DEFAULT 'não informado';
ALTER TABLE empresa ALTER COLUMN regime_tributario SET DEFAULT 'não informado';
ALTER TABLE empresa ALTER COLUMN setor_origem SET DEFAULT 'não informado';
ALTER TABLE empresa ALTER COLUMN regime_origem SET DEFAULT 'não informado';
ALTER TABLE empresa ALTER COLUMN faturamento_origem SET DEFAULT 'não informado';

UPDATE empresa SET setor = 'não informado' WHERE setor IS NULL;
UPDATE empresa SET regime_tributario = 'não informado' WHERE regime_tributario IS NULL;
UPDATE empresa SET setor_origem = 'não informado' WHERE setor_origem IS NULL;
UPDATE empresa SET regime_origem = 'não informado' WHERE regime_origem IS NULL;
UPDATE empresa SET faturamento_origem = 'não informado' WHERE faturamento_origem IS NULL;

-- 2. TABELA CRM: Padronizar 'Não se aplica' para 'não se aplica' (minúsculo)
ALTER TABLE crm DROP CONSTRAINT IF EXISTS crm_acao_check;

UPDATE crm SET acao = 'não se aplica' WHERE LOWER(acao) = 'não se aplica' OR LOWER(acao) = 'nao se aplica';
UPDATE crm SET responsavel = 'não se aplica' WHERE LOWER(responsavel) = 'não se aplica' OR LOWER(responsavel) = 'nao se aplica';
UPDATE crm SET prazo = 'não se aplica' WHERE LOWER(prazo) = 'não se aplica' OR LOWER(prazo) = 'nao se aplica';
UPDATE crm SET dados_extras = 'não se aplica' WHERE LOWER(dados_extras) = 'não se aplica' OR LOWER(dados_extras) = 'nao se aplica';
UPDATE crm SET resumo = 'não se aplica' WHERE LOWER(resumo) = 'não se aplica' OR LOWER(resumo) = 'nao se aplica';

ALTER TABLE crm ADD CONSTRAINT crm_acao_check 
CHECK (acao IS NULL OR acao IN (
    'reunião confirmada', 
    'reunião proposta sem aceite', 
    'retorno com data combinado', 
    'envio de material solicitado', 
    'sem próximo passo definido', 
    'sem interesse explícito', 
    'não se aplica'
));

-- 3. TABELA ANALISE_BANT: Padronizar evidências ausentes para 'não se aplica'
UPDATE analise_bant SET budget_evidencia = 'não se aplica' WHERE LOWER(budget_evidencia) = 'não se aplica' OR LOWER(budget_evidencia) = 'nao se aplica';
UPDATE analise_bant SET authority_evidencia = 'não se aplica' WHERE LOWER(authority_evidencia) = 'não se aplica' OR LOWER(authority_evidencia) = 'nao se aplica';
UPDATE analise_bant SET need_evidencia = 'não se aplica' WHERE LOWER(need_evidencia) = 'não se aplica' OR LOWER(need_evidencia) = 'nao se aplica';
UPDATE analise_bant SET timeline_evidencia = 'não se aplica' WHERE LOWER(timeline_evidencia) = 'não se aplica' OR LOWER(timeline_evidencia) = 'nao se aplica';

