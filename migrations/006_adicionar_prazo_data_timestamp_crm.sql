-- ============================================================================
-- Migração 006: Adicionar coluna prazo_data TIMESTAMP em crm
-- Armazena a data e hora estipuladas calculadas pelo LLM a partir da data de início
-- da chamada (chamadas.dt_inicio). Caso dt_inicio não exista, permanece NULL.
-- ============================================================================

ALTER TABLE crm 
ADD COLUMN IF NOT EXISTS prazo_data TIMESTAMP;

-- Índice para otimizar relacionamentos temporais e consultas analíticas no Power BI
CREATE INDEX IF NOT EXISTS idx_crm_prazo_data ON crm(prazo_data);
