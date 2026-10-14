-- ============================================================================
-- Migração 007: Adicionar data_status_comercial TIMESTAMP em empresa
-- Armazena a data âncora em que o status comercial foi estabelecido:
-- 1ª prioridade: data de agenda (crm.prazo_data para reuniões e retornos)
-- 2ª prioridade (fallback): data de realização da chamada (chamadas.dt_inicio)
-- ============================================================================

ALTER TABLE empresa 
ADD COLUMN IF NOT EXISTS data_status_comercial TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_empresa_data_status ON empresa(data_status_comercial);

-- Backfill histórico para empresas já cadastradas
UPDATE empresa e
SET data_status_comercial = sub.dt_ref
FROM (
    SELECT rc.id_empresa, MAX(COALESCE(c.prazo_data, ch.dt_inicio, ai.data_avaliacao::timestamp)) AS dt_ref
    FROM registro_chamadas rc
    LEFT JOIN crm c ON c.log = rc.log
    LEFT JOIN chamadas ch ON ch.protocolo = rc.protocolo
    LEFT JOIN avaliacao_ia ai ON ai.log = rc.log
    GROUP BY rc.id_empresa
) sub
WHERE e.id_empresa = sub.id_empresa AND e.data_status_comercial IS NULL;
