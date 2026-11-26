BEGIN;
CREATE TEMP TABLE _logs_remover ON COMMIT DROP AS
SELECT rc.log
FROM registro_chamadas rc
JOIN chamadas c ON c.protocolo = rc.protocolo
WHERE c.duracao_segundos < 90;
-- Filhas de avaliacao_sdr
DELETE FROM avaliacao_criterio                WHERE log IN (SELECT log FROM _logs_remover);
DELETE FROM avaliacao_oportunidade_treinamento WHERE log IN (SELECT log FROM _logs_remover);
DELETE FROM avaliacao_sdr                     WHERE log IN (SELECT log FROM _logs_remover);
-- Filhas de avaliacao_ia
DELETE FROM analise_spin   WHERE log IN (SELECT log FROM _logs_remover);
DELETE FROM analise_bant   WHERE log IN (SELECT log FROM _logs_remover);
DELETE FROM interlocutor   WHERE log IN (SELECT log FROM _logs_remover);
DELETE FROM crm            WHERE log IN (SELECT log FROM _logs_remover);
DELETE FROM analise_perfil WHERE log IN (SELECT log FROM _logs_remover);
-- Nível principal de avaliação e registro
DELETE FROM avaliacao_ia      WHERE log IN (SELECT log FROM _logs_remover);
DELETE FROM registro_chamadas WHERE log IN (SELECT log FROM _logs_remover);