-- ============================================================================
-- Migração 009: Criar tabela de cache para dados coletados pelo robô Google (RPA)
--
-- Objetivo:
--   Armazenar em banco os dados brutos de pesquisa retornados pelo Google
--   referentes a cada telefone consultado pelo robô RPA (app/services/rpa_google.py).
--
-- Benefícios:
--   1. Checkpointing: Se a execução for interrompida no meio, números já consultados
--      não precisam abrir o navegador novamente ao reiniciar.
--   2. Reaproveitamento histórico: Chamadas futuras para o mesmo número utilizam
--      o cache instantaneamente sem custo ou intervenção na máquina.
--   3. Menor risco de bloqueio/CAPTCHA pelo Google por redução de requisições redundantes.
-- ============================================================================

CREATE TABLE IF NOT EXISTS cache_rpa_google (
    telefone VARCHAR(30) PRIMARY KEY,
    texto_google TEXT NOT NULL,
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cache_rpa_google_atualizado ON cache_rpa_google(atualizado_em);
