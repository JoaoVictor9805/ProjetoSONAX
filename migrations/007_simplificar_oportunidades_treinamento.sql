-- ============================================================================
-- Migração 007: Simplificar descrições de dim_oportunidade_treinamento
-- Atualiza as descrições dos critérios de oportunidade de melhoria para formato
-- direto e no infinitivo, eliminando parágrafos longos para visualização no Power BI.
-- ============================================================================

UPDATE dim_oportunidade_treinamento
SET descricao = 'Apresentar-se com clareza e dizer o motivo da ligação nos primeiros segundos'
WHERE codigo = 'OP_ABERT_01';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Usar a oportunidade de crédito tributário como gancho inicial nos primeiros segundos'
WHERE codigo = 'OP_ABERT_02';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Expor o benefício de caixa sem sobrecarga técnica ou juridiquês'
WHERE codigo = 'OP_ABERT_03';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Confirmar se o interlocutor lida com a área fiscal ou financeira antes de aprofundar'
WHERE codigo = 'OP_ABERT_04';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Superar a recepção e direcionar o contato para o responsável financeiro ou fiscal'
WHERE codigo = 'OP_ABERT_05';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Tratar o crédito como hipótese comercial sem prometer valores certos ou garantidos'
WHERE codigo = 'OP_ABERT_06';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Fazer perguntas rápidas para mapear o cenário atual sem prolongar a chamada'
WHERE codigo = 'OP_SPIN_01';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Investigar atritos fiscais ou limitações da rotina contábil da empresa'
WHERE codigo = 'OP_SPIN_02';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Destacar o risco de prescrição da janela de 5 anos e dinheiro parado'
WHERE codigo = 'OP_SPIN_03';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Conectar a recuperação tributária à dor do lead e checar o interesse em resgatar caixa'
WHERE codigo = 'OP_SPIN_04';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Estimular o interlocutor a admitir a dor em vez de assumir teses próprias do SDR'
WHERE codigo = 'OP_SPIN_05';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Confirmar ativamente se a empresa opera no regime de Lucro Real'
WHERE codigo = 'OP_PERF_01';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Confirmar faturamento mínimo mensal igual ou superior a R$ 1 milhão'
WHERE codigo = 'OP_PERF_02';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Identificar se o segmento é industrial ou registrar outro setor confirmado'
WHERE codigo = 'OP_PERF_03';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Formular perguntas para que o próprio interlocutor declare e valide as informações'
WHERE codigo = 'OP_PERF_04';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Sondar a viabilidade de contratação e reforçar que o diagnóstico inicial é sem custo'
WHERE codigo = 'OP_BANT_01';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Mapear o papel do interlocutor na decisão e descobrir quem mais precisa participar'
WHERE codigo = 'OP_BANT_02';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Fazer perguntas para o lead verbalizar a necessidade em vez de apenas empurrar o pitch'
WHERE codigo = 'OP_BANT_03';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Mapear prazo ou evento motivador para criar senso de urgência no próximo passo'
WHERE codigo = 'OP_BANT_04';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Posicionar o projeto como suporte complementar e técnico, sem confrontar a contabilidade atual'
WHERE codigo = 'OP_ESC_01';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Praticar escuta ativa espelhando palavras do lead antes de contra-argumentar'
WHERE codigo = 'OP_ESC_02';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Acolher com segurança o receio de riscos ou fiscalização, explicando o processo técnico'
WHERE codigo = 'OP_ESC_03';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Evitar interrupções e sobreposição de falas no fluxo da conversa'
WHERE codigo = 'OP_ESC_04';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Investigar a razão de desinteresses genéricos para identificar e contornar a objeção real'
WHERE codigo = 'OP_ESC_05';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Sugerir dias e horários concretos usando dupla escolha em vez de perguntas abertas'
WHERE codigo = 'OP_PROX_01';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Confirmar claramente o formato da reunião (online ou presencial) e obter o contato correto'
WHERE codigo = 'OP_PROX_02';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Reancorar o valor da reunião técnica ao contornar pedidos de envio por e-mail'
WHERE codigo = 'OP_PROX_03';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Fixar com precisão o responsável, dia e horário quando o retorno for necessário'
WHERE codigo = 'OP_PROX_04';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Encerrar o contato com polidez e objetividade ao constatar empresa fora do perfil'
WHERE codigo = 'OP_DIR_01';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Superar a barreira da recepção para falar com quem decide'
WHERE codigo = 'OP_DIR_02';

UPDATE dim_oportunidade_treinamento
SET descricao = 'Conduzir a chamada até um status comercial conclusivo, evitando indefinição'
WHERE codigo = 'OP_DIR_03';
