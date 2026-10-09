-- ============================================================================
-- REGISTROS FICTÍCIOS CALIBRADOS PARA AS MÉTRICAS DO PAINEL POWER BI
-- FALAVINHA NEXT - Visão Executiva e Funil de Conversão
--
-- MÉTRICAS CONTEMPLADAS:
--   - Total de Ligações: 10
--   - Conversas Relevantes: 10 (100%)
--   - Conversas com Decisor: 10 (100%)
--   - Leads Qualificados (ICP / Perfil Confirmado): 6 (60,00%)
--   - Fora do Perfil desta Campanha: 2 (20,00%)
--   - Perfil Pendente: 2 (20,00%)
--   - Total de Agendamentos / Reuniões Confirmadas: 5 (50,00%)
--   - Média de nota_final: 85,30 (Soma exata das 10 notas = 853)
--   - Período: Outubro de 2026 (05/10/2026 - dentro do filtro 26/08/2026 a 05/10/2026)
--
-- Mapeamento das 10 linhas operacionais:
--   1. 26416509236 | 127 | 116870127 | MAIRA CAROLINE RIBEIRODE OLIVEIRA  | Perfil confirmado | Reunião 's' | Nota 92
--   2. 26416492346 | 106 | 116870106 | THAIS ANISIA GUIMARAES OLIVIERA    | Perfil confirmado | Reunião 's' | Nota 88
--   3. 26416492306 | 108 | 116870108 | THAYANA MADALENA RAMOS             | Perfil pendente   | Reunião 'n' | Nota 75
--   4. 26416393446 | 106 | 116870106 | THAIS ANISIA GUIMARAES OLIVIERA    | Fora do perfil    | Reunião 'n' | Nota 87
--   5. 26416385156 | 108 | 116870108 | THAYANA MADALENA RAMOS             | Perfil confirmado | Reunião 's' | Nota 93
--   6. 26416384826 | 127 | 116870127 | MAIRA CAROLINE RIBEIRODE OLIVEIRA  | Perfil confirmado | Reunião 's' | Nota 91
--   7. 26416349086 | 128 | 116870128 | MARIA EDUARDA PEREIRA              | Perfil confirmado | Reunião 's' | Nota 90
--   8. 26416306166 | 116 | 116870116 | JHENIFFER QUADROS                  | Fora do perfil    | Reunião 'n' | Nota 85
--   9. 26416298076 | 128 | 116870128 | MARIA EDUARDA PEREIRA              | Perfil confirmado | Reunião 'n' | Nota 82
--  10. 26416271676 | 142 | 116870142 | Karolyne Gluszczynski              | Perfil pendente   | Reunião 'n' | Nota 70
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 0. Garantir dimensões no banco
-- ----------------------------------------------------------------------------
INSERT INTO dim_criterio_avaliacao (codigo, descricao) VALUES
('CRIT_ABERTURA', 'Abertura clara, motivo do contato e relevância para o interlocutor'),
('CRIT_SPIN', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução'),
('CRIT_PERFIL', 'Investigação adequada do perfil: setor, regime tributário, faturamento'),
('CRIT_BANT', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo'),
('CRIT_ESCUTA', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções'),
('CRIT_PROX_PASSO', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO dim_oportunidade_treinamento (codigo, fase_venda, descricao) VALUES
('OP_ABERT_01', '1. Abertura e Relevância', 'Apresentar-se e situar a empresa com objetividade.'),
('OP_ABERT_02', '1. Abertura e Relevância', 'Utilizar a oportunidade de crédito mapeada como gancho.'),
('OP_ABERT_03', '1. Abertura e Relevância', 'Expor o benefício da oportunidade sem sobrecarga técnica.'),
('OP_ABERT_04', '1. Abertura e Relevância', 'Confirmar o alinhamento com o interlocutor antes de aprofundar.'),
('OP_ABERT_05', '1. Abertura e Relevância', 'Direcionar o contato para o responsável fiscal, tributário ou financeiro.'),
('OP_ABERT_06', '1. Abertura e Relevância', 'Evitar promessas de valores ou garantia de créditos.'),
('OP_SPIN_01', '2. Descoberta SPIN', 'Mapear o cenário inicial com perguntas rápidas e indispensáveis.'),
('OP_SPIN_02', '2. Descoberta SPIN', 'Mapear atritos fiscais ou lacunas na rotina da empresa.'),
('OP_SPIN_03', '2. Descoberta SPIN', 'Destacar implicações simples e tangíveis (como a prescrição de créditos).'),
('OP_SPIN_04', '2. Descoberta SPIN', 'Conectar a solução à dor e checar a viabilidade de avanço.'),
('OP_SPIN_05', '2. Descoberta SPIN', 'Diferenciar dor reconhecida pelo lead de argumentos do SDR.'),
('OP_PERF_01', '3. Investigação de Perfil Técnico', 'Investigar o regime tributário da empresa.'),
('OP_PERF_02', '3. Investigação de Perfil Técnico', 'Confirmar o faturamento mínimo.'),
('OP_PERF_03', '3. Investigação de Perfil Técnico', 'Mapear o segmento de atuação.'),
('OP_PERF_04', '3. Investigação de Perfil Técnico', 'Garantir a confirmação ativa dos dados.'),
('OP_BANT_01', '4. Investigação BANT', 'Budget (Viabilidade Comercial): Avaliar viabilidade e diagnóstico gratuito.'),
('OP_BANT_02', '4. Investigação BANT', 'Authority (Autoridade): Avaliar poder de decisão do interlocutor.'),
('OP_BANT_03', '4. Investigação BANT', 'Need (Necessidade): Estimular lead a verbalizar interesse ou dor.'),
('OP_BANT_04', '4. Investigação BANT', 'Timeline (Prazo): Mapear prioridade e urgência para avanço.'),
('OP_ESC_01', '5. Escuta e Objeções', 'Posicionar o trabalho como complementar à contabilidade atual.'),
('OP_ESC_02', '5. Escuta e Objeções', 'Retomar e espelhar termos utilizados pelo lead.'),
('OP_ESC_03', '5. Escuta e Objeções', 'Tratar com empatia o receio de riscos ou fiscalização.'),
('OP_ESC_04', '5. Escuta e Objeções', 'Evitar interrupções e sobreposição de falas no fluxo da conversa.'),
('OP_ESC_05', '5. Escuta e Objeções', 'Investigar o motivo do desinteresse para direcionar a melhor saída.'),
('OP_PROX_01', '6. Próximo Passo e Compromisso', 'Propor opções objetivas de data e horário (técnica de dupla escolha).'),
('OP_PROX_02', '6. Próximo Passo e Compromisso', 'Alinhar formalmente a modalidade escolhida (online ou presencial).'),
('OP_PROX_03', '6. Próximo Passo e Compromisso', 'Contornar o pedido passivo de envio de material.'),
('OP_PROX_04', '6. Próximo Passo e Compromisso', 'Definir responsável e data concreta para retornos agendados.'),
('OP_DIR_01', '7. Direcionamento Final e Resolução da Chamada', 'Direcionamento assertivo com base no perfil.'),
('OP_DIR_02', '7. Direcionamento Final e Resolução da Chamada', 'Condução para uma conversa substantiva.'),
('OP_DIR_03', '7. Direcionamento Final e Resolução da Chamada', 'Consolidação de um status claro.')
ON CONFLICT (codigo) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 1. TABELA chamadas (10 chamadas em 05/10/2026, com agentes e ramais da planilha)
-- ----------------------------------------------------------------------------
DELETE FROM chamadas WHERE protocolo IN (
    26416509236, 26416492346, 26416492306, 26416393446, 26416385156,
    26416384826, 26416349086, 26416306166, 26416298076, 26416271676,
    26416268606
);

INSERT INTO chamadas (
    protocolo, identificacao_cliente, estado_ddd, numero, atendido, ramal,
    duracao_segundos, fila_id, fila_descricao, tabulacao_id, tabulacao_descricao,
    agente_login, agente_nome, campanha_id, campanha_descricao, dt_inicio, dt_fim,
    status, hash_registro, last_sync
) VALUES
-- Linha 1: 127 | MAIRA CAROLINE RIBEIRODE OLIVEIRA
(26416509236, 555432143712, 'RS', '5432143712', 'S', '127', 342, 10, 'Fila SDR Sul', 0, 'Não tabulada', '116870127', 'MAIRA CAROLINE RIBEIRODE OLIVEIRA', 1, 'Campanha Lucro Real 2026', '2026-10-05 09:14:02', '2026-10-05 09:19:44', 'CONCLUIDA', 'hash_ficticio_26416509236', NOW()),

-- Linha 2: 106 | THAIS ANISIA GUIMARAES OLIVIERA
(26416492346, 551434052000, 'SP', '1434052000', 'S', '106', 285, 11, 'Fila SDR Sudeste', 0, 'Não tabulada', '116870106', 'THAIS ANISIA GUIMARAES OLIVIERA', 1, 'Campanha Lucro Real 2026', '2026-10-05 09:30:15', '2026-10-05 09:35:00', 'CONCLUIDA', 'hash_ficticio_26416492346', NOW()),

-- Linha 3: 108 | THAYANA MADALENA RAMOS
(26416492306, 5518981017954, 'SP', '18981017954', 'S', '108', 210, 11, 'Fila SDR Sudeste', 0, 'Não tabulada', '116870108', 'THAYANA MADALENA RAMOS', 1, 'Campanha Lucro Real 2026', '2026-10-05 09:42:10', '2026-10-05 09:45:40', 'CONCLUIDA', 'hash_ficticio_26416492306', NOW()),

-- Linha 4: 106 | THAIS ANISIA GUIMARAES OLIVIERA
(26416393446, 551434052000, 'SP', '1434052000', 'S', '106', 195, 11, 'Fila SDR Sudeste', 0, 'Não tabulada', '116870106', 'THAIS ANISIA GUIMARAES OLIVIERA', 1, 'Campanha Lucro Real 2026', '2026-10-05 10:02:10', '2026-10-05 10:05:25', 'CONCLUIDA', 'hash_ficticio_26416393446', NOW()),

-- Linha 5: 108 | THAYANA MADALENA RAMOS
(26416385156, 551832113945, 'SP', '1832113945', 'S', '108', 330, 11, 'Fila SDR Sudeste', 0, 'Não tabulada', '116870108', 'THAYANA MADALENA RAMOS', 1, 'Campanha Lucro Real 2026', '2026-10-05 10:15:00', '2026-10-05 10:20:30', 'CONCLUIDA', 'hash_ficticio_26416385156', NOW()),

-- Linha 6: 127 | MAIRA CAROLINE RIBEIRODE OLIVEIRA
(26416384826, 5554999831904, 'RS', '54999831904', 'S', '127', 290, 10, 'Fila SDR Sul', 0, 'Não tabulada', '116870127', 'MAIRA CAROLINE RIBEIRODE OLIVEIRA', 1, 'Campanha Lucro Real 2026', '2026-10-05 10:31:10', '2026-10-05 10:36:00', 'CONCLUIDA', 'hash_ficticio_26416384826', NOW()),

-- Linha 7: 128 | MARIA EDUARDA PEREIRA
(26416349086, 5545998168334, 'PR', '45998168334', 'S', '128', 315, 10, 'Fila SDR Sul', 0, 'Não tabulada', '116870128', 'MARIA EDUARDA PEREIRA', 1, 'Campanha Lucro Real 2026', '2026-10-05 10:45:00', '2026-10-05 10:50:15', 'CONCLUIDA', 'hash_ficticio_26416349086', NOW()),

-- Linha 8: 116 | JHENIFFER QUADROS
(26416306166, 554935667834, 'SC', '4935667834', 'S', '116', 160, 10, 'Fila SDR Sul', 0, 'Não tabulada', '116870116', 'JHENIFFER QUADROS', 1, 'Campanha Lucro Real 2026', '2026-10-05 11:02:30', '2026-10-05 11:05:10', 'CONCLUIDA', 'hash_ficticio_26416306166', NOW()),

-- Linha 9: 128 | MARIA EDUARDA PEREIRA
(26416298076, 5545998448979, 'PR', '45998448979', 'S', '128', 270, 10, 'Fila SDR Sul', 0, 'Não tabulada', '116870128', 'MARIA EDUARDA PEREIRA', 1, 'Campanha Lucro Real 2026', '2026-10-05 11:18:00', '2026-10-05 11:22:30', 'CONCLUIDA', 'hash_ficticio_26416298076', NOW()),

-- Linha 10: 142 | Karolyne Gluszczynski
(26416271676, 5541999978799, 'PR', '41999978799', 'S', '142', 220, 10, 'Fila SDR Sul', 0, 'Não tabulada', '116870142', 'Karolyne Gluszczynski', 1, 'Campanha Lucro Real 2026', '2026-10-05 11:35:11', '2026-10-05 11:38:51', 'CONCLUIDA', 'hash_ficticio_26416271676', NOW());

-- ----------------------------------------------------------------------------
-- 2. TABELA empresa (6 Perfil confirmado | 2 Fora do perfil | 2 Perfil pendente)
-- ----------------------------------------------------------------------------
INSERT INTO empresa (
    id_empresa, nome, telefone, setor, regime_tributario, faturamento_mensal,
    faturamento_anual, status_comercial, fonte_dados, setor_origem, regime_origem, faturamento_origem
)
OVERRIDING SYSTEM VALUE
VALUES
-- 1. Perfil confirmado (1)
(9001, 'Metalúrgica Alvorada Sul Ltda', '555432143712', 'industrial', 'Lucro Real', 2500000.00, 30000000.00, 'Perfil confirmado', 'Google Maps / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 2. Perfil confirmado (2)
(9002, 'Laticínios & Alimentos Bela Vista S.A.', '551434052000', 'industrial', 'Lucro Real', 4200000.00, 50400000.00, 'Perfil confirmado', 'Receita Federal / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 3. Perfil pendente (1)
(9003, 'Polímeros & Resinas Quimvale Ltda', '5518981017954', 'industrial', 'Lucro Real', 1800000.00, 21600000.00, 'Perfil pendente', 'Econodata / SDR', 'confirmado pelo interlocutor', 'afirmado apenas pelo SDR', 'inferência plausível'),

-- 4. Fora do perfil desta campanha (1)
(9004, 'Expresso Logística Integrada Bandeirante Ltda', '551434052001', 'outro confirmado', 'Simples Nacional', 350000.00, 4200000.00, 'Fora do perfil desta campanha', 'SDR Inbound', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 5. Perfil confirmado (3)
(9005, 'Indústria de Usinagem Brasfer Ltda', '551832113945', 'industrial', 'Lucro Real', 2100000.00, 25200000.00, 'Perfil confirmado', 'Base Ativa / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 6. Perfil confirmado (4)
(9006, 'Couros & Calçados Nova Petrópolis Ltda', '5554999831904', 'industrial', 'Lucro Real', 1900000.00, 22800000.00, 'Perfil confirmado', 'Google Maps / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 7. Perfil confirmado (5)
(9007, 'Agroindustrial Serra da Esperança S.A.', '5545998168334', 'industrial', 'Lucro Real', 3000000.00, 36000000.00, 'Perfil confirmado', 'Base Interna / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 8. Fora do perfil desta campanha (2)
(9008, 'Fiação & Tecelagem Catarinense Ltda', '554935667834', 'industrial', 'Lucro Presumido', 600000.00, 7200000.00, 'Fora do perfil desta campanha', 'Empresômetro / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 9. Perfil confirmado (6)
(9009, 'Distribuidora Cataratas de Máquinas e Peças S.A.', '5545998448979', 'outro confirmado', 'Lucro Real', 4500000.00, 54000000.00, 'Perfil confirmado', 'LinkedIn / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor'),

-- 10. Perfil pendente (2)
(9010, 'Plásticos & Injeção Alto Iguaçu Ltda', '5541999978799', 'industrial', 'Lucro Real', 1500000.00, 18000000.00, 'Perfil pendente', 'Google Maps / SDR', 'confirmado pelo interlocutor', 'confirmado pelo interlocutor', 'afirmado apenas pelo SDR')
ON CONFLICT (id_empresa) DO UPDATE SET
    nome = EXCLUDED.nome,
    telefone = EXCLUDED.telefone,
    setor = EXCLUDED.setor,
    regime_tributario = EXCLUDED.regime_tributario,
    faturamento_mensal = EXCLUDED.faturamento_mensal,
    faturamento_anual = EXCLUDED.faturamento_anual,
    status_comercial = EXCLUDED.status_comercial,
    fonte_dados = EXCLUDED.fonte_dados,
    setor_origem = EXCLUDED.setor_origem,
    regime_origem = EXCLUDED.regime_origem,
    faturamento_origem = EXCLUDED.faturamento_origem;

-- ----------------------------------------------------------------------------
-- 3. TABELA registro_chamadas (ASR Contínuo e Diálogo Diarizado Revisado por IA)
-- ----------------------------------------------------------------------------
DELETE FROM registro_chamadas WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO registro_chamadas (log, protocolo, transcricao, revisao, id_empresa) VALUES
-- Linha 1: Maira | 127
('call_26416509236_127.wav', 26416509236,
 'bom dia carlos tudo bem sou a maira da falavinha next carlos estou entrando em contato porque mapeamos oportunidades específicas de créditos tributários na linha de produção da metalúrgica alvorada entendi olha nós operamos no lucro real e nosso faturamento gira em torno de dois milhões e meio ao mês como funciona esse trabalho de vocês excelente carlos o trabalho é 100 por cento administrativo em total conformidade fiscal e focado em recomposição de caixa para apresentar as teses aplicáveis ao seu setor podemos agendar uma conversa rápida de 10 minutos nesta quinta-feira às 14h perfeito maira quinta-feira às 14h fica ótimo para mim pode enviar o link no e-mail combinado carlos convite enviado e até quinta às 14h até logo obrigado',
 'Agente (Falavinha): Bom dia, Carlos! Tudo bem? Sou a Maira da Falavinha Next.
Cliente (Metalúrgica Alvorada Sul Ltda): Bom dia, Maira. Tudo certo.
Agente (Falavinha): Carlos, estou entrando em contato porque mapeamos oportunidades específicas de créditos tributários na linha de produção da Metalúrgica Alvorada.
Cliente (Metalúrgica Alvorada Sul Ltda): Entendi. Olha, nós operamos no regime de Lucro Real e nosso faturamento gira em torno de dois milhões e meio ao mês. Como funciona esse trabalho de vocês?
Agente (Falavinha): Excelente, Carlos. O trabalho é 100% administrativo, em total conformidade fiscal e focado em recomposição de caixa. Para apresentar as teses aplicáveis ao seu setor, podemos agendar uma conversa rápida de 10 a 12 minutos nesta quinta-feira às 14h com o nosso tributarista?
Cliente (Metalúrgica Alvorada Sul Ltda): Perfeito, Maira. Quinta-feira às 14h fica ótimo para mim. Pode enviar o link no e-mail carlos.mendes@alvoradasul.com.br.
Agente (Falavinha): Combinado, Carlos! Convite enviado e nos falamos na quinta às 14h. Um ótimo dia!
Cliente (Metalúrgica Alvorada Sul Ltda): Até logo, obrigado.', 9001),

-- Linha 2: Thais | 106
('call_26416492346_106.wav', 26416492346,
 'olá roberta tudo bem aqui é a thais da falavinha next olá thais tudo bem do que se trata roberta acompanhamos o setor agroindustrial e identificamos teses consolidadas de insumos e pis cofins voltadas para indústrias de laticínios do porte da bela vista certo nós estamos no regime de lucro real e nosso faturamento anual supera os 50 milhões a questão é que nós já temos equipe tributária interna e contabilidade externa esse trabalho concorre com eles de forma alguma roberta atuamos como suporte técnico complementar conseguimos reservar 10 minutinhos nesta sexta-feira às 10h30 para uma apresentação executiva online entendi faz sentido pode ser na sexta às 10h30 sim excelente roberta muito obrigada e nos falamos na sexta até sexta thais',
 'Agente (Falavinha): Olá, Roberta! Tudo bem? Aqui é a Thais da Falavinha Next.
Cliente (Laticínios & Alimentos Bela Vista S.A.): Olá, Thais, tudo bem. Do que se trata?
Agente (Falavinha): Roberta, acompanhamos o setor agroindustrial e identificamos teses consolidadas de insumos e PIS/Cofins voltadas para indústrias de laticínios do porte da Bela Vista.
Cliente (Laticínios & Alimentos Bela Vista S.A.): Certo. Nós estamos no regime de Lucro Real e nosso faturamento anual supera os 50 milhões. A questão é que nós já temos equipe tributária interna e contabilidade externa. Esse trabalho concorre com eles?
Agente (Falavinha): De forma alguma, Roberta! Atuamos como um suporte técnico complementar, analisando teses específicas que a rotina diária não foca. Conseguimos reservar 10 a 12 minutinhos nesta sexta-feira às 10h30 para uma apresentação online com o especialista?
Cliente (Laticínios & Alimentos Bela Vista S.A.): Entendi, faz sentido. Pode ser na sexta às 10h30 sim. Vou te passar o e-mail para encaminhar o link da sala.
Agente (Falavinha): Excelente, Roberta! Muito obrigada e nos falamos na sexta às 10h30.
Cliente (Laticínios & Alimentos Bela Vista S.A.): Até sexta, Thais.', 9002),

-- Linha 3: Thayana | 108
('call_26416492306_108.wav', 26416492306,
 'marcos bom dia sou a thayana da falavinha next tudo bem com o senhor bom dia thayana sou o marcos diretor financeiro pois não marcos apresentamos oportunidades tributárias para indústrias químicas no lucro real nós somos lucro real e faturamos quase 2 milhões por mês no entanto estou em reunião de diretoria agora pode me retornar segunda às 14h perfeito marcos segunda às 14h em ponto ligo para falarmos com calma combinado obrigado',
 'Agente (Falavinha): Bom dia, Marcos! Sou a Thayana da Falavinha Next. Tudo bem com o senhor?
Cliente (Polímeros & Resinas Quimvale Ltda): Bom dia, Thayana. Sou o Marcos, Diretor Financeiro aqui da Quimvale. Pois não?
Agente (Falavinha): Marcos, estamos apresentando oportunidades de revisão fiscal e créditos federais para indústrias químicas que operam no Lucro Real.
Cliente (Polímeros & Resinas Quimvale Ltda): Nós somos optantes do Lucro Real sim e faturamos em torno de 1,8 milhão ao mês. O assunto é interessante, mas estou exatamente entrando em uma reunião de diretoria agora. Conseguiria me retornar na próxima segunda-feira às 14h?
Agente (Falavinha): Com certeza, Marcos! Respeito totalmente o seu horário. Segunda-feira às 14h pontualmente eu retorno a ligação para detalharmos.
Cliente (Polímeros & Resinas Quimvale Ltda): Perfeito, Thayana. Muito obrigado, até segunda.
Agente (Falavinha): Até segunda, Marcos! Um ótimo dia.', 9003),

-- Linha 4: Thais | 106
('call_26416393446_106.wav', 26416393446,
 'valdemir bom dia aqui é a thais da falavinha next tudo bem com o senhor bom dia thais tudo bem o que seria valdemir estamos realizando um levantamento de oportunidades de créditos tributários federais para logística e transportes o senhor é optante pelo regime de lucro real não thais nós somos optantes do simples nacional com faturamento em torno de 350 mil reais por mês entendi valdemir agradeço imensamente pela clareza nossos estudos tributários são exclusivamente para lucro real encerro por aqui e desejo muito sucesso ao seu negócio muito obrigado pela atenção e honestidade thais bom trabalho para você obrigada valdemir tenha um excelente dia',
 'Agente (Falavinha): Valdemir, bom dia! Aqui é a Thais da Falavinha Next. Tudo bem com o senhor?
Cliente (Expresso Logística Integrada Bandeirante Ltda): Bom dia, Thais. Tudo bem. O que seria?
Agente (Falavinha): Valdemir, estamos realizando um levantamento de oportunidades de créditos tributários federais para o setor de logística e transportes. O senhor é optante pelo regime de Lucro Real?
Cliente (Expresso Logística Integrada Bandeirante Ltda): Não, Thais. Eu sou o proprietário e nós somos optantes do Simples Nacional. Nossa operação é enxuta, com faturamento em torno de 350 mil reais por mês.
Agente (Falavinha): Entendi, Valdemir. Agradeço imensamente pela clareza! Nossos estudos tributários atuais são exclusivamente parametrizados para empresas no regime de Lucro Real. Para não tomar seu tempo precioso, encerro nosso contato por aqui e desejo muito sucesso ao seu negócio!
Cliente (Expresso Logística Integrada Bandeirante Ltda): Muito obrigado pela atenção e honestidade, Thais. Bom trabalho para você.
Agente (Falavinha): Obrigada, Valdemir! Tenha um excelente dia.', 9004),

-- Linha 5: Thayana | 108
('call_26416385156_108.wav', 26416385156,
 'eduardo bom dia aqui é a thayana da falavinha next tudo bem bom dia thayana tudo bem por aqui eduardo estou entrando em contato com foco na indústria metalmecânica mapeamos pontos relevantes sobre aproveitamento de créditos fiscais em insumos e máquinas de usinagem olha nós somos lucro real e nosso faturamento médio mensal é de 2 ponto 1 milhões mas exatamente que linha de crédito vocês avaliam avaliamos a tomada de créditos sobre insumos fabris e subvenções fiscais estaduais conseguimos reservar 12 minutos nesta sexta-feira às 15h para o nosso tributarista apresentar na prática excelente thayana pode marcar na sexta às 15h sim prefiro fazer por teams perfeito eduardo enviarei o convite no teams e nos falamos sexta às 15h combinado obrigado',
 'Agente (Falavinha): Eduardo, bom dia! Aqui é a Thayana da Falavinha Next, tudo bem?
Cliente (Indústria de Usinagem Brasfer Ltda): Bom dia, Thayana. Tudo bem por aqui.
Agente (Falavinha): Eduardo, estou entrando em contato com foco na indústria metalmecânica. Mapeamos pontos relevantes sobre aproveitamento de créditos fiscais em insumos de corte, ferramentas e máquinas de usinagem.
Cliente (Indústria de Usinagem Brasfer Ltda): Olha, sou o diretor e sócio, nós somos enquadrados no Lucro Real e nosso faturamento médio mensal é de 2,1 milhões. Mas exatamente que linha de crédito vocês avaliam?
Agente (Falavinha): Avaliamos a tomada de créditos sobre itens de desgaste rápido, insumos fabris e subvenções fiscais estaduais, sempre em conformidade pacificada. Conseguimos reservar 12 minutos nesta sexta-feira às 15h para o nosso tributarista apresentar esses pontos na prática?
Cliente (Indústria de Usinagem Brasfer Ltda): Excelente, Thayana. Pode marcar na sexta às 15h sim. Prefiro fazer por Teams.
Agente (Falavinha): Perfeito, Eduardo! Enviarei o convite formal no Teams e nos falamos na sexta às 15h.
Cliente (Indústria de Usinagem Brasfer Ltda): Combinado, obrigado.', 9005),

-- Linha 6: Maira | 127
('call_26416384826_127.wav', 26416384826,
 'simone bom dia tudo bem aqui é a maira da falavinha next bom dia maira tudo ótimo em que posso ajudar simone estou em contato direto com o polo industrial calçadista do rio grande do sul estamos apresentando possibilidades concretas de desoneração e recuperação tributária entendi maira nós operamos no lucro real e nosso faturamento gira em torno de 1 ponto 9 milhão ao mês a nossa maior dor é o acúmulo de créditos de icms por conta das exportações vocês atuam com esse tipo de saldo exatamente simone possuímos frente especializada em monetização de saldos credores de icms de exportação podemos marcar conferência online de 10 minutos na quarta-feira às 11h perfeito maira quarta às 11h está ótimo pode me mandar o link maravilha simone enviarei o convite e alinhamos tudo na quarta um abraço um abraço até lá',
 'Agente (Falavinha): Simone, bom dia! Tudo bem? Aqui é a Maira da Falavinha Next.
Cliente (Couros & Calçados Nova Petrópolis Ltda): Bom dia, Maira. Tudo ótimo, sou a diretora financeira, em que posso ajudar?
Agente (Falavinha): Simone, estou em contato direto com o polo industrial calçadista do Rio Grande do Sul. Estamos apresentando possibilidades concretas de desoneração e recuperação tributária para a Nova Petrópolis.
Cliente (Couros & Calçados Nova Petrópolis Ltda): Entendi, Maira. Nós operamos no Lucro Real e nosso faturamento gira em torno de 1,9 milhão ao mês. A nossa maior dor é o acúmulo de créditos de ICMS por conta das exportações de calçados. Vocês atuam com esse tipo de saldo?
Agente (Falavinha): Exatamente, Simone! Possuímos uma frente tributária especializada em monetização e compensação de saldos credores de ICMS decorrentes de saídas para o exterior. Podemos marcar uma conferência online de 10 minutos na quarta-feira às 11h para detalharmos o fluxo?
Cliente (Couros & Calçados Nova Petrópolis Ltda): Perfeito, Maira! Quarta às 11h está ótimo na minha agenda. Pode me mandar o link da sala.
Agente (Falavinha): Maravilha, Simone! Enviarei o convite e alinhamos tudo na quarta às 11h. Um abraço!
Cliente (Couros & Calçados Nova Petrópolis Ltda): Um abraço, até lá!', 9006),

-- Linha 7: Maria Eduarda | 128
('call_26416349086_128.wav', 26416349086,
 'juliana bom dia aqui é a maria eduarda da falavinha next tudo bem bom dia maria eduarda tudo bem por aqui juliana acompanhamos o setor agroindustrial paranaense e mapeamos oportunidades de recuperação de pis cofins sobre maquinários e insumos para a serra da esperança certo a nossa empresa é lucro real e nós fechamos o ano passado em 36 milhões de faturamento até costumamos fazer revisões periódicas com nossa auditoria perfeito juliana o nosso diagnóstico é pontual sem custo inicial conseguimos reunir nosso consultor com você nesta quinta-feira às 15h podemos sim maria eduarda quinta às 15h tenho disponibilidade combinado juliana o convite já está a caminho tenha um excelente dia obrigada igualmente',
 'Agente (Falavinha): Juliana, bom dia! Aqui é a Maria Eduarda da Falavinha Next. Tudo bem?
Cliente (Agroindustrial Serra da Esperança S.A.): Bom dia, Maria Eduarda. Tudo bem por aqui, sou a diretora financeira da Serra da Esperança.
Agente (Falavinha): Juliana, acompanhamos o setor agroindustrial paranaense e mapeamos oportunidades de recuperação de PIS/Cofins não cumulativo e créditos sobre maquinários e insumos agrícolas para a Serra da Esperança.
Cliente (Agroindustrial Serra da Esperança S.A.): Certo. A nossa empresa é Lucro Real e nós fechamos o ano passado em 36 milhões de faturamento. Nós até costumamos fazer revisões periódicas com nossa auditoria.
Agente (Falavinha): Perfeito, Juliana! O nosso diagnóstico é pontual, focado estritamente em teses consolidadas sem qualquer custo inicial. Conseguimos reunir nosso consultor com você nesta quinta-feira às 15h para você avaliar sem compromisso?
Cliente (Agroindustrial Serra da Esperança S.A.): Podemos sim, Maria Eduarda. Quinta às 15h tenho disponibilidade.
Agente (Falavinha): Combinado, Juliana! O convite de reunião já está a caminho. Tenha um excelente dia!
Cliente (Agroindustrial Serra da Esperança S.A.): Obrigada, igualmente!', 9007),

-- Linha 8: Jheniffer | 116
('call_26416306166_116.wav', 26416306166,
 'renato bom dia tudo bem aqui é a jheniffer da falavinha next bom dia jheniffer tudo bem quem fala renato sou especialista de atendimento da falavinha next estamos contatando a indústria têxtil em santa catarina para apresentar oportunidades de revisão tributária olhe jheniffer agradeço o contato mas nós somos optantes do lucro presumido e nosso faturamento mensal é em torno de 600 mil reais entendo perfeitamente renato como as nossas soluções nesta campanha são para indústrias no lucro real e faturamento acima de 1 milhão seu negócio não se enquadra agradeço imensamente sua sinceridade e não vou tomar seu tempo muito obrigado pelo respeito e pela gentileza jheniffer de nada renato muito sucesso e um ótimo dia',
 'Agente (Falavinha): Renato, bom dia! Tudo bem? Aqui é a Jheniffer da Falavinha Next.
Cliente (Fiação & Tecelagem Catarinense Ltda): Bom dia, Jheniffer. Tudo bem, sou o sócio-proprietário, quem fala?
Agente (Falavinha): Renato, sou especialista de atendimento da Falavinha Next. Estamos contatando a indústria têxtil em Santa Catarina para apresentar oportunidades de revisão tributária administrativa.
Cliente (Fiação & Tecelagem Catarinense Ltda): Olhe, Jheniffer, agradeço o contato, mas nós somos optantes do Lucro Presumido e nosso faturamento mensal é em torno de 600 mil reais.
Agente (Falavinha): Entendo perfeitamente, Renato! Como as nossas soluções nesta campanha são estruturadas exclusivamente para indústrias no Lucro Real e com faturamento acima de R$ 1 milhão, seu negócio não se enquadra no momento. Agradeço imensamente sua sinceridade e não vou tomar seu tempo!
Cliente (Fiação & Tecelagem Catarinense Ltda): Muito obrigado pelo respeito e pela gentileza, Jheniffer.
Agente (Falavinha): De nada, Renato! Muito sucesso e um ótimo dia.', 9008),

-- Linha 9: Maria Eduarda | 128
('call_26416298076_128.wav', 26416298076,
 'bom dia cláudia tudo bem aqui é a maria eduarda da falavinha next bom dia maria eduarda tudo bem pois não cláudia trabalho com eficiência fiscal para distribuidoras identificamos oportunidades atrativas de créditos na comercialização de autopeças e maquinários pesados entendi olha nós estamos no lucro real e nosso faturamento mensal gira em torno de 4 ponto 5 milhões o tema me interessa bastante mas estou no meio do fechamento contábil e sem nenhuma janela hoje respeito totalmente cláudia posso te ligar na próxima terça-feira às 10h da manhã pontualmente para combinarmos a apresentação pode ser sim maria eduarda na terça às 10h já estarei com a rotina normalizada perfeito cláudia registro aqui e na terça às 10h nos falamos muito obrigada até terça',
 'Agente (Falavinha): Bom dia, Cláudia! Tudo bem? Aqui é a Maria Eduarda da Falavinha Next.
Cliente (Distribuidora Cataratas de Máquinas e Peças S.A.): Bom dia, Maria Eduarda. Tudo bem, sou a CFO Cláudia. Pois não?
Agente (Falavinha): Cláudia, trabalho com projetos de eficiência fiscal para grandes distribuidoras no Paraná. Identificamos oportunidades atrativas de créditos na comercialização de autopeças e maquinários pesados.
Cliente (Distribuidora Cataratas de Máquinas e Peças S.A.): Entendi. Olha, nós estamos no Lucro Real e nosso faturamento mensal gira em torno de 4,5 milhões. O tema me interessa bastante, mas estou no meio do fechamento contábil mensal e sem nenhuma janela hoje.
Agente (Falavinha): Respeito totalmente o período de fechamento da controladoria, Cláudia! Para não comprometer sua rotina, posso te ligar na próxima terça-feira às 10h da manhã pontualmente para combinarmos a apresentação com o especialista?
Cliente (Distribuidora Cataratas de Máquinas e Peças S.A.): Pode ser sim, Maria Eduarda. Na terça às 10h já estarei com a rotina normalizada.
Agente (Falavinha): Perfeito, Cláudia! Registro aqui e na terça às 10h nos falamos. Bom fechamento de mês!
Cliente (Distribuidora Cataratas de Máquinas e Peças S.A.): Muito obrigada, até terça!', 9009),

-- Linha 10: Karolyne | 142
('call_26416271676_142.wav', 26416271676,
 'danilo bom dia como vai aqui é a karolyne da falavinha next bom dia karolyne sou o danilo diretor em que posso ajudar danilo estou contatando o setor de injeção plástica para compartilhar oportunidades de recuperação fiscal de créditos federais vocês operam hoje no lucro real sim nós somos lucro real e nosso faturamento médio é de aproximadamente 1 ponto 5 milhão de reais por mês mas antes de agendar qualquer reunião técnica eu preciso receber uma apresentação institucional detalhada por e-mail perfeito danilo enviarei hoje mesmo a apresentação com os cases do setor plástico para o seu e-mail posso confirmar seu contato direto pode sim o e-mail é danilo ponto fiscal arroba plasticoaltoiguacu ponto com ponto br excelente danilo muito obrigada pela atenção e um ótimo dia obrigado até logo',
 'Agente (Falavinha): Danilo, bom dia! Como vai? Aqui é a Karolyne da Falavinha Next.
Cliente (Plásticos & Injeção Alto Iguaçu Ltda): Bom dia, Karolyne. Tudo bem, sou o Danilo, Diretor de Operações e Sócio. Em que posso ajudar?
Agente (Falavinha): Danilo, estou contatando o setor de injeção plástica para compartilhar oportunidades de recuperação fiscal de créditos federais. Vocês operam hoje no Lucro Real?
Cliente (Plásticos & Injeção Alto Iguaçu Ltda): Sim, nós somos Lucro Real e nosso faturamento médio é de aproximadamente 1,5 milhão de reais por mês. Mas a nossa diretoria é muito criteriosa: antes de agendar qualquer reunião técnica, eu preciso receber uma apresentação institucional detalhada por e-mail para validar as teses.
Agente (Falavinha): Perfeito, Danilo! Enviarei hoje mesmo a apresentação institucional com os cases do setor plástico para o seu e-mail. Posso confirmar seu contato direto para alinharmos a reunião após você analisar o arquivo?
Cliente (Plásticos & Injeção Alto Iguaçu Ltda): Pode sim, o e-mail é danilo.fiscal@plasticoaltoiguacu.com.br. Assim que eu analisar, nós alinhamos os próximos passos.
Agente (Falavinha): Excelente, Danilo! Muito obrigada pela atenção e um ótimo dia.
Cliente (Plásticos & Injeção Alto Iguaçu Ltda): Obrigado, até logo.', 9010);

-- ----------------------------------------------------------------------------
-- 4. TABELA avaliacao_ia (Métricas: 10 Relevantes | 10 Decisor | 6 Perfil | 5 Reunião)
-- ----------------------------------------------------------------------------
DELETE FROM avaliacao_ia WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO avaliacao_ia (
    log, data_avaliacao, modelo_ia, interlocutor, cargo, empresa_contatada,
    resultado, ligacao_relevante, reuniao_confirmada, data_confirmada, conversa_decisor, resultado_frase
) VALUES
-- 1. Perfil confirmado | Reunião confirmada
('call_26416509236_127.wav', '2026-10-05', 'gemini-2.5-flash', 'Carlos Mendes', 'Diretor Financeiro', 9001, 'Perfil confirmado', 's', 's', 's', 's', 'Reunião agendada por Maira com o Diretor Financeiro para quinta-feira às 14h com foco em créditos de insumos metalúrgicos.'),

-- 2. Perfil confirmado | Reunião confirmada
('call_26416492346_106.wav', '2026-10-05', 'gemini-2.5-flash', 'Roberta Guimarães', 'Diretora Tributária', 9002, 'Perfil confirmado', 's', 's', 's', 's', 'Reunião confirmada por Thais com a Diretora Tributária para apresentação de tese em laticínios na sexta às 10h30.'),

-- 3. Perfil pendente | Sem reunião
('call_26416492306_108.wav', '2026-10-05', 'gemini-2.5-flash', 'Marcos Vinicius', 'Diretor Financeiro', 9003, 'Perfil pendente', 's', 'n', 'n', 's', 'Retorno agendado por Thayana diretamente com o Diretor Financeiro Marcos para segunda-feira às 14h.'),

-- 4. Fora do perfil | Sem reunião
('call_26416393446_106.wav', '2026-10-05', 'gemini-2.5-flash', 'Valdemir Santos', 'Proprietário', 9004, 'Fora do perfil desta campanha', 's', 'n', 'n', 's', 'Empresa fora do perfil: optante pelo Simples Nacional com faturamento de R$ 350 mil mensais descartada por Thais.'),

-- 5. Perfil confirmado | Reunião confirmada
('call_26416385156_108.wav', '2026-10-05', 'gemini-2.5-flash', 'Eduardo Fontes', 'Diretor Industrial e Sócio', 9005, 'Perfil confirmado', 's', 's', 's', 's', 'Reunião confirmada por Thayana com o Diretor Sócio Eduardo Fontes para sexta-feira às 15h via Teams.'),

-- 6. Perfil confirmado | Reunião confirmada
('call_26416384826_127.wav', '2026-10-05', 'gemini-2.5-flash', 'Simone Zimmer', 'Diretora Financeira', 9006, 'Perfil confirmado', 's', 's', 's', 's', 'Reunião confirmada por Maira para quarta-feira às 11h com a Diretora Financeira Simone Zimmer.'),

-- 7. Perfil confirmado | Reunião confirmada
('call_26416349086_128.wav', '2026-10-05', 'gemini-2.5-flash', 'Juliana Castelli', 'Diretora Financeira', 9007, 'Perfil confirmado', 's', 's', 's', 's', 'Reunião confirmada por Maria Eduarda para quinta-feira 15h com a Diretora Financeira Juliana Castelli.'),

-- 8. Fora do perfil | Sem reunião
('call_26416306166_116.wav', '2026-10-05', 'gemini-2.5-flash', 'Renato Becker', 'Sócio-Proprietário', 9008, 'Fora do perfil desta campanha', 's', 'n', 'n', 's', 'Empresa desqualificada com assertividade por Jheniffer em contato com o sócio: Lucro Presumido e faturamento < 1M.'),

-- 9. Perfil confirmado | Sem reunião (Retorno combinado)
('call_26416298076_128.wav', '2026-10-05', 'gemini-2.5-flash', 'Cláudia Nogueira', 'CFO', 9009, 'Perfil confirmado', 's', 'n', 'n', 's', 'Decisora CFO confirmou Lucro Real e faturamento a Maria Eduarda, solicitando retorno na terça às 10h pós-fechamento.'),

-- 10. Perfil pendente | Sem reunião (Material solicitado)
('call_26416271676_142.wav', '2026-10-05', 'gemini-2.5-flash', 'Danilo Prado', 'Diretor de Operações e Sócio', 9010, 'Perfil pendente', 's', 'n', 'n', 's', 'Material institucional solicitado pelo Diretor Danilo a Karolyne antes de confirmar data na agenda.');

-- ----------------------------------------------------------------------------
-- 5. TABELA avaliacao_sdr (Média exata = 85,30 | Soma das notas = 853)
-- ----------------------------------------------------------------------------
DELETE FROM avaliacao_sdr WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO avaliacao_sdr (
    log, nota_final, feedback_geral, acertos, melhorias, frase_alternativa
) VALUES
-- 1. Nota 92
('call_26416509236_127.wav', 92,
 'Excelente abordagem comercial de Maira. Ancorou o segmento metalúrgico com firmeza, qualificou dados vitais sem atrito e obteve compromisso de data com o decisor.',
 'Abertura rápida com o diretor; confirmação ativa de Lucro Real e R$ 2,5M; técnica de dupla escolha para fechamento.',
 'Poderia ter investigado se a empresa já utilizou compensação no último ano.',
 'Carlos, identificamos que indústrias metalúrgicas no RS costumam ter oportunidades de revisão de insumos. Terça às 14h ou quinta às 10h seria melhor para conversarmos?'),

-- 2. Nota 88
('call_26416492346_106.wav', 88,
 'Excelente postura consultiva de Thais. Soube posicionar a consultoria como parceira complementar à contabilidade interna da empresa.',
 'Tratamento de objeção contábil; escuta ativa e validação de grande porte (50M+ ano).',
 'Aprofundar nas implicações da janela prescricional para aumentar o senso de urgência.',
 'Nosso diagnóstico tributário atua em parceria com sua equipe contábil, focando exclusivamente em créditos que costumam ficar retidos na operação.'),

-- 3. Nota 75
('call_26416492306_108.wav', 75,
 'Boa conexão direta com o decisor por Thayana, porém aceitou o adiamento sem tentar fixar uma data alternativa imediata.',
 'Falou diretamente com o diretor financeiro e mapeou faturamento de quase R$ 2M.',
 'Tentar obter compromisso mais firme no momento do contato.',
 'Marcos, compreendo sua reunião. Que tal reservarmos 10 minutos na segunda às 14h com convite formal já disparado?'),

-- 4. Nota 87
('call_26416393446_106.wav', 87,
 'Excelente descarte rápido de empresa no Simples Nacional realizado por Thais. Manteve a cortesia e liberou o ramal para novos contatos.',
 'Identificação imediata de regime incompatível e faturamento baixo.',
 'Manter essa postura assertiva em todas as ligações de triagem.',
 'Valdemir, agradeço a clareza. Nosso trabalho exige o regime de Lucro Real, por isso não vou tomar mais do seu tempo hoje. Um grande abraço!'),

-- 5. Nota 93
('call_26416385156_108.wav', 93,
 'Abordagem consultiva de alto padrão de Thayana. Explorou créditos de subvenções e gerou curiosidade legítima no diretor industrial.',
 'Domínio técnico sobre subvenções; excelente fechamento com agendamento formal no Teams.',
 'Apenas confirmar os participantes adicionais da reunião (ex: contador da fábrica).',
 'Eduardo, além de você, quem mais da área contábil seria importante estar presente na nossa conversa de sexta às 15h?'),

-- 6. Nota 91
('call_26416384826_127.wav', 91,
 'Excelente sintonia e empatia de Maira com a diretora financeira. Conectou as dores do setor calçadista exportador às teses tributárias.',
 'Mapeamento de faturamento (1,9M) e Lucro Real; fixação de data e horário.',
 'Poderia ter perguntado qual percentual da receita é destinado à exportação.',
 'Simone, créditos de ICMS acumulados em vendas para o exterior costumam devolver muito fôlego de caixa para indústrias calçadistas.'),

-- 7. Nota 90
('call_26416349086_128.wav', 90,
 'Condução assertiva e segura de Maria Eduarda. Validou Lucro Real e cálculo de faturamento em agroindústria, garantindo reunião com agenda fechada.',
 'Coleta detalhada de faturamento anual (36M) e derivação mensal; confirmação de agenda.',
 'Poderia explorar mais os atritos do PIS/Cofins não cumulativo no agro.',
 'Juliana, indústrias agropecuárias com seu faturamento costumam ter créditos represados em fertilizantes e embalagens.'),

-- 8. Nota 85
('call_26416306166_116.wav', 85,
 'Excelente disciplina comercial de Jheniffer. Desqualificou com rapidez e educação ao identificar Lucro Presumido e faturamento de R$ 600k.',
 'Economia de tempo operacional; polidez no encerramento de lead fora do perfil.',
 'Nenhum ponto negativo; postura recomendada para filtragem de funil.',
 'Renato, agradeço a sinceridade sobre o Lucro Presumido. Nossas soluções atuais são desenhadas para Lucro Real, então desejo muito sucesso ao seu negócio!'),

-- 9. Nota 82
('call_26416298076_128.wav', 82,
 'Boa autoridade de Maria Eduarda e respeito ao momento da CFO. Estabeleceu dia e hora para o retorno sem queimar o lead qualificado.',
 'Conexão com CFO de grande empresa (4,5M/mês); data de contato acertada.',
 'Poderia ter proposto o envio de uma pauta executiva por e-mail enquanto ela finaliza o fechamento.',
 'Cláudia, respeito totalmente seu período de fechamento contábil. Terça às 10h pontualmente estarei em contato para darmos sequência.'),

-- 10. Nota 70
('call_26416271676_142.wav', 70,
 'Karolyne qualificou os dados fiscais essenciais com o sócio, porém cedeu passivamente ao pedido de envio de apresentação por e-mail.',
 'Mapeamento correto de Lucro Real e faturamento de R$ 1,5M.',
 'Evitar envio passivo de material sem data de follow-up definida no ato.',
 'Danilo, posso te enviar a apresentação agora mesmo. Enquanto você abre, que tal já reservarmos 15 minutos na quinta às 14h para tirar as dúvidas técnicas?');

-- ----------------------------------------------------------------------------
-- 6. TABELA avaliacao_oportunidade_treinamento (N:N com dimensões)
-- ----------------------------------------------------------------------------
DELETE FROM avaliacao_oportunidade_treinamento WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO avaliacao_oportunidade_treinamento (log, codigo_oportunidade) VALUES
('call_26416509236_127.wav', 'OP_ABERT_02'),
('call_26416509236_127.wav', 'OP_PROX_01'),
('call_26416492346_106.wav', 'OP_ESC_01'),
('call_26416492346_106.wav', 'OP_PROX_02'),
('call_26416492306_108.wav', 'OP_PERF_01'),
('call_26416492306_108.wav', 'OP_PROX_04'),
('call_26416393446_106.wav', 'OP_DIR_01'),
('call_26416385156_108.wav', 'OP_SPIN_02'),
('call_26416385156_108.wav', 'OP_PROX_01'),
('call_26416384826_127.wav', 'OP_ABERT_03'),
('call_26416384826_127.wav', 'OP_PROX_01'),
('call_26416349086_128.wav', 'OP_SPIN_03'),
('call_26416349086_128.wav', 'OP_PROX_01'),
('call_26416306166_116.wav', 'OP_DIR_01'),
('call_26416298076_128.wav', 'OP_PROX_04'),
('call_26416298076_128.wav', 'OP_ESC_03'),
('call_26416271676_142.wav', 'OP_PROX_03'),
('call_26416271676_142.wav', 'OP_BANT_02');

-- ----------------------------------------------------------------------------
-- 7. TABELA avaliacao_criterio (6 critérios avaliados por chamada)
-- ----------------------------------------------------------------------------
DELETE FROM avaliacao_criterio WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO avaliacao_criterio (log, criterio, nota_criterio, justificativa_criterio, codigo_criterio) VALUES
-- Chamada 1: Maira / 127 (Total: 92)
('call_26416509236_127.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 9, 'Maira apresentou-se de forma ágil citando créditos industriais da cadeia metalúrgica.', 'CRIT_ABERTURA'),
('call_26416509236_127.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 28, 'Investigou rotina produtiva e alertou sobre janela prescricional de 5 anos.', 'CRIT_SPIN'),
('call_26416509236_127.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 24, 'Confirmou expressamente Lucro Real e faturamento mensal de R$ 2,5M.', 'CRIT_PERFIL'),
('call_26416509236_127.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 13, 'Falou direto com o CFO, mapeando autoridade e interesse genuíno de caixa.', 'CRIT_BANT'),
('call_26416509236_127.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 9, 'Respondeu com segurança à dúvida sobre segurança administrativa do trabalho.', 'CRIT_ESCUTA'),
('call_26416509236_127.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 9, 'Utilizou técnica de dupla escolha e fixou quinta 14h com convite de agenda.', 'CRIT_PROX_PASSO'),

-- Chamada 2: Thais / 106 (Total: 88)
('call_26416492346_106.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 9, 'Thais usou gancho direto no processamento de laticínios.', 'CRIT_ABERTURA'),
('call_26416492346_106.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 26, 'Mapeou acúmulo de créditos de PIS/Cofins na compra de matéria-prima.', 'CRIT_SPIN'),
('call_26416492346_106.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 23, 'Confirmou porte anual acima de 50M no Lucro Real.', 'CRIT_PERFIL'),
('call_26416492346_106.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 13, 'Validou autonomia técnica da diretora tributária.', 'CRIT_BANT'),
('call_26416492346_106.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 9, 'Tratou a objeção de equipe contábil interna com maestria.', 'CRIT_ESCUTA'),
('call_26416492346_106.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 8, 'Definiu formato online na sexta às 10h30.', 'CRIT_PROX_PASSO'),

-- Chamada 3: Thayana / 108 (Total: 75)
('call_26416492306_108.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 8, 'Thayana apresentou-se adequadamente falando direto com o diretor financeiro.', 'CRIT_ABERTURA'),
('call_26416492306_108.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 22, 'Explorou porte da fábrica, porém não aprofundou nas lacunas devido ao tempo.', 'CRIT_SPIN'),
('call_26416492306_108.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 19, 'Validou Lucro Real e porte de R$ 1,8M/mês.', 'CRIT_PERFIL'),
('call_26416492306_108.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 11, 'Falou direto com o CFO Marcos.', 'CRIT_BANT'),
('call_26416492306_108.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 8, 'Respeitou a reunião iminente do diretor.', 'CRIT_ESCUTA'),
('call_26416492306_108.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 7, 'Acertou retorno para segunda às 14h.', 'CRIT_PROX_PASSO'),

-- Chamada 4: Thais / 106 (Total: 87)
('call_26416393446_106.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 9, 'Thais teve apresentação limpa e direta na triagem.', 'CRIT_ABERTURA'),
('call_26416393446_106.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 26, 'Perguntas de qualificação rápidas e eficientes com o proprietário.', 'CRIT_SPIN'),
('call_26416393446_106.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 23, 'Identificou Simples Nacional e R$ 350k/mês prontamente.', 'CRIT_PERFIL'),
('call_26416393446_106.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 12, 'Verificou inviabilidade técnica de imediato.', 'CRIT_BANT'),
('call_26416393446_106.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 8, 'Agradeceu com empatia sem tomar tempo do lead.', 'CRIT_ESCUTA'),
('call_26416393446_106.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 9, 'Encerramento conclusivo e profissional.', 'CRIT_PROX_PASSO'),

-- Chamada 5: Thayana / 108 (Total: 93)
('call_26416385156_108.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 10, 'Thayana usou gancho perfeito em usinagem e recuperação de ativo imobilizado.', 'CRIT_ABERTURA'),
('call_26416385156_108.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 28, 'Explorou subvenções estaduais e gerou necessidade imediata no sócio.', 'CRIT_SPIN'),
('call_26416385156_108.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 24, 'Confirmou Lucro Real e R$ 2,1M/mês com o diretor.', 'CRIT_PERFIL'),
('call_26416385156_108.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 13, 'Diretor com autoridade total interessado em fôlego de caixa.', 'CRIT_BANT'),
('call_26416385156_108.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 9, 'Respondeu às dúvidas de prazo do diagnóstico técnico.', 'CRIT_ESCUTA'),
('call_26416385156_108.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 9, 'Reunião confirmada no Teams para sexta 15h.', 'CRIT_PROX_PASSO'),

-- Chamada 6: Maira / 127 (Total: 91)
('call_26416384826_127.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 9, 'Maira realizou apresentação segmentada na indústria calçadista.', 'CRIT_ABERTURA'),
('call_26416384826_127.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 27, 'Identificou potencial em créditos tributários de exportação.', 'CRIT_SPIN'),
('call_26416384826_127.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 23, 'Confirmou R$ 1,9M de receita mensal e Lucro Real.', 'CRIT_PERFIL'),
('call_26416384826_127.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 14, 'Diretora financeira alinhada e motivada a recuperar saldos.', 'CRIT_BANT'),
('call_26416384826_127.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 9, 'Excelente acolhimento das dúvidas sobre conformidade fiscal.', 'CRIT_ESCUTA'),
('call_26416384826_127.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 9, 'Agenda confirmada para quarta-feira às 11h.', 'CRIT_PROX_PASSO'),

-- Chamada 7: Maria Eduarda / 128 (Total: 90)
('call_26416349086_128.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 9, 'Maria Eduarda fez conexão contextualizada com agroindústria paranaense.', 'CRIT_ABERTURA'),
('call_26416349086_128.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 27, 'Enfatizou créditos de insumos rurais e desonerações.', 'CRIT_SPIN'),
('call_26416349086_128.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 23, 'Confirmou R$ 36M anual e regime de Lucro Real.', 'CRIT_PERFIL'),
('call_26416349086_128.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 13, 'Diretora financeira demonstrou interesse imediato por diagnóstico gratuito.', 'CRIT_BANT'),
('call_26416349086_128.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 9, 'Esclareceu ausência de custos prévios com clareza.', 'CRIT_ESCUTA'),
('call_26416349086_128.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 9, 'Reunião confirmada para quinta às 15h.', 'CRIT_PROX_PASSO'),

-- Chamada 8: Jheniffer / 116 (Total: 85)
('call_26416306166_116.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 9, 'Jheniffer teve abertura objetiva e profissional com o sócio.', 'CRIT_ABERTURA'),
('call_26416306166_116.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 25, 'Checou porte fabril sem insistência desnecessária.', 'CRIT_SPIN'),
('call_26416306166_116.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 22, 'Identificou Lucro Presumido e R$ 600k com rapidez cirúrgica.', 'CRIT_PERFIL'),
('call_26416306166_116.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 12, 'Interlocutor decisor, porém lead inviável tecnicamente.', 'CRIT_BANT'),
('call_26416306166_116.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 8, 'Acolheu a resposta do sócio sem forçar vendas.', 'CRIT_ESCUTA'),
('call_26416306166_116.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 9, 'Encerramento polido e assertivo com descarte correto.', 'CRIT_PROX_PASSO'),

-- Chamada 9: Maria Eduarda / 128 (Total: 82)
('call_26416298076_128.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 8, 'Maria Eduarda manteve excelente tom consultivo com a CFO de distribuidora.', 'CRIT_ABERTURA'),
('call_26416298076_128.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 25, 'Mapeou volume de peças e compras no atacado.', 'CRIT_SPIN'),
('call_26416298076_128.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 21, 'Validou Lucro Real e faturamento de R$ 4,5M/mês.', 'CRIT_PERFIL'),
('call_26416298076_128.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 12, 'CFO confirmou autoridade e interesse na tese.', 'CRIT_BANT'),
('call_26416298076_128.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 8, 'Respeitou o atrito de agenda devido ao fechamento contábil.', 'CRIT_ESCUTA'),
('call_26416298076_128.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 8, 'Fixou data e horário preciso para retorno.', 'CRIT_PROX_PASSO'),

-- Chamada 10: Karolyne / 142 (Total: 70)
('call_26416271676_142.wav', 'Abertura clara, motivo do contato e relevância para o interlocutor', 7, 'Karolyne teve abertura adequada, porém sem gerar forte impacto inicial.', 'CRIT_ABERTURA'),
('call_26416271676_142.wav', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução', 21, 'Foco excessivo em perguntas de rotina sem tocar em dor de caixa.', 'CRIT_SPIN'),
('call_26416271676_142.wav', 'Investigação adequada do perfil: setor, regime tributário, faturamento', 18, 'Validou Lucro Real e 1,5M de faturamento com o sócio.', 'CRIT_PERFIL'),
('call_26416271676_142.wav', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo', 11, 'Falou direto com o diretor sócio Danilo.', 'CRIT_BANT'),
('call_26416271676_142.wav', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções', 7, 'Aceitou o pedido de envio de material.', 'CRIT_ESCUTA'),
('call_26416271676_142.wav', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro', 6, 'Não fixou compromisso de retorno no momento da chamada.', 'CRIT_PROX_PASSO');

-- ----------------------------------------------------------------------------
-- 8. TABELA analise_spin
-- ----------------------------------------------------------------------------
DELETE FROM analise_spin WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO analise_spin (
    log, situacao, situacao_investigada, problema, problema_investigado,
    implicacao, implicacao_investigada, necessidade_solucao, necessidade_investigada,
    evidencias, lacunas
) VALUES
('call_26416509236_127.wav', 'Fábrica metalúrgica no RS com faturamento mensal de R$ 2,5M no Lucro Real.', 's', 'Empresa não revisa créditos tributários da linha fabril há mais de 4 anos.', 's', 'Risco iminente de prescrição quinquenal de créditos de ICMS e IPI.', 's', 'Necessidade de diagnóstico administrativo para recuperação de saldo de caixa.', 's', 'Interlocutor confirmou que a equipe interna foca em rotinas diárias.', 'Não detalhou se há litígios fiscais em andamento.'),
('call_26416492346_106.wav', 'Indústria de laticínios faturando acima de R$ 50M no Lucro Real em SP.', 's', 'Acúmulo de créditos de PIS/Cofins na compra de insumos de produtores rurais.', 's', 'Capital de giro represado enquanto a empresa toma crédito bancário com juros.', 's', 'Monetização de créditos acumulados via ressarcimento/compensação.', 's', 'Diretora tributária informou que possui créditos represados.', 'Não abriu valores exatos do saldo credor acumulado.'),
('call_26416492306_108.wav', 'Indústria química em SP faturando R$ 1,8M/mês no Lucro Real.', 's', 'Falta de janela de agenda do diretor financeiro no momento do contato.', 's', 'Necessidade de estudo prévio para avaliação sem perda de tempo.', 's', 'Suporte especializado externo para apoiar a diretoria.', 's', 'Diretor financeiro confirmou interesse e pediu contato na segunda.', 'Pendente de apresentação detalhada das teses.'),
('call_26416393446_106.wav', 'Transportadora terceirizada faturando R$ 350k no Simples Nacional.', 's', 'Porte pequeno e regime tributário simplificado.', 'n', 'Incompatibilidade com os requisitos mínimos de elegibilidade.', 'n', 'Não aplicável.', 'n', 'Declaração imediata do proprietário.', 'Não aplicável.'),
('call_26416385156_108.wav', 'Empresa de usinagem e peças faturando R$ 2,1M/mês no Lucro Real.', 's', 'Aquisição recente de máquinas CNC sem aproveitamento de CIAP.', 's', 'Créditos de ICMS sobre o ativo permanente não apropriados.', 's', 'Revisão técnica de créditos de ativo e subvenções.', 's', 'Diretor industrial confirmou novos maquinários adquiridos nos últimos 2 anos.', 'Não especificou valor total do imobilizado.'),
('call_26416384826_127.wav', 'Indústria calçadista exportadora faturando R$ 1,9M no RS.', 's', 'Volume relevante de vendas externas gerando saldos credores de ICMS.', 's', 'Recursos expressivos parados na escrita fiscal sem liquidez.', 's', 'Aproveitamento e transferência de créditos de exportação.', 's', 'Diretora financeira citou acúmulo de créditos estaduais.', 'Não detalhou para quais estados as vendas são direcionadas.'),
('call_26416349086_128.wav', 'Agroindústria paranaense faturando R$ 36M anual no Lucro Real.', 's', 'Revisões fiscais passadas não contemplaram créditos de maquinários agrícolas.', 's', 'Valores elevados retidos no Fisco sem render para a operação.', 's', 'Estudo sem custo prévio para apurar montante recuperável.', 's', 'Juliana afirmou que o último diagnóstico foi feito há 3 anos.', 'Não informou o percentual de insumos com diferimento.'),
('call_26416306166_116.wav', 'Fiação têxtil faturando R$ 600k/mês em SC no Lucro Presumido.', 's', 'Empresa enquadrada em regime simplificado para o porte.', 'n', 'Teses da campanha não se aplicam ao Lucro Presumido.', 'n', 'Não possui necessidade imediata compatível com o produto.', 'n', 'Sócio declarou regime tributário nos primeiros minutos.', 'Não aplicável para avanço comercial.'),
('call_26416298076_128.wav', 'Grande distribuidora de máquinas e peças no PR faturando R$ 4,5M mensais.', 's', 'Processo contábil sobrecarregado pelo fechamento mensal.', 's', 'Falta de disponibilidade imediata para novos projetos.', 's', 'Janela de tempo após fechamento contábil para avaliação de oportunidades.', 's', 'CFO expressou interesse nas teses mas solicitou retorno.', 'Falta validar quais teses já foram executadas.'),
('call_26416271676_142.wav', 'Indústria de transformação plástica em Curitiba faturando R$ 1,5M.', 's', 'Diretoria exige material institucional para pré-avaliação.', 's', 'Demora na tomada de decisão sobre eficiência tributária.', 'n', 'Apresentação formal detalhando segurança jurídica das teses.', 's', 'Diretor sócio exigiu apresentação antes de liberar agenda.', 'Não explorou implicações de perdas financeiras.');

-- ----------------------------------------------------------------------------
-- 9. TABELA analise_bant
-- ----------------------------------------------------------------------------
DELETE FROM analise_bant WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO analise_bant (
    log, budget_classificacao, budget_evidencia, authority_classificacao, authority_evidencia,
    need_classificacao, need_evidencia, timeline_classificacao, timeline_evidencia
) VALUES
('call_26416509236_127.wav', 'viabilidade confirmada', 'Diagnóstico sem custo aceito com sucesso.', 'decisor direto', 'Carlos Mendes é CFO com poder deliberativo.', 'necessidade clara', 'Interesse expresso em fôlego de caixa.', 'imediato', 'Reunião agendada para quinta-feira 14h.'),
('call_26416492346_106.wav', 'viabilidade confirmada', 'Modelo de êxito atrativo para a empresa.', 'decisor direto', 'Roberta é diretora da área tributária.', 'necessidade clara', 'Créditos acumulados de PIS/Cofins represados.', 'curto prazo', 'Reunião agendada para sexta-feira 10h30.'),
('call_26416492306_108.wav', 'em avaliação', 'Modelo gratuito agradou o diretor.', 'decisor direto', 'Marcos é o Diretor Financeiro da Quimvale.', 'necessidade moderada', 'Interesse expresso em avaliar teses do setor químico.', 'curto prazo', 'Retorno agendado para segunda-feira 14h.'),
('call_26416393446_106.wav', 'fora do perfil', 'Empresa no Simples Nacional sem margem de contrato.', 'decisor direto', 'Valdemir é proprietário.', 'sem necessidade', 'Regime incompatível.', 'inaplicável', 'Contato finalizado.'),
('call_26416385156_108.wav', 'viabilidade confirmada', 'Modelo de remuneração no sucesso comercial.', 'decisor direto', 'Eduardo é diretor industrial e sócio.', 'necessidade clara', 'Aquisições recentes de maquinário gerando créditos.', 'imediato', 'Reunião confirmada no Teams para sexta 15h.'),
('call_26416384826_127.wav', 'viabilidade confirmada', 'Aceite do modelo de diagnóstico sem custo.', 'decisor direto', 'Simone é diretora financeira da empresa.', 'necessidade clara', 'Forte interesse em créditos estaduais de exportação.', 'imediato', 'Reunião confirmada para quarta-feira às 11h.'),
('call_26416349086_128.wav', 'viabilidade confirmada', 'Diagnóstico sem risco alinhado.', 'decisor direto', 'Juliana é diretora financeira do grupo.', 'necessidade clara', 'Busca ativa por recuperação de créditos de máquinas.', 'imediato', 'Reunião confirmada para quinta-feira 15h.'),
('call_26416306166_116.wav', 'fora do perfil', 'Não atende requisitos financeiros da campanha.', 'decisor direto', 'Renato é sócio proprietário.', 'sem necessidade', 'Regime incompatível com as teses.', 'inaplicável', 'Contato finalizado sem avanço.'),
('call_26416298076_128.wav', 'viabilidade confirmada', 'Porte financeiro elevado viabiliza o projeto.', 'decisor direto', 'Cláudia é CFO executiva da companhia.', 'necessidade clara', 'Interesse real em teses tributárias para atacadista.', 'curto prazo', 'Follow-up agendado para terça-feira às 10h.'),
('call_26416271676_142.wav', 'em avaliação', 'Exige aprovação do material institucional.', 'decisor direto', 'Danilo é diretor de operações e sócio.', 'necessidade moderada', 'Interesse condicionado à validação de teses.', 'médio prazo', 'Aguardando avaliação de material por e-mail.');

-- ----------------------------------------------------------------------------
-- 10. TABELA interlocutor
-- ----------------------------------------------------------------------------
DELETE FROM interlocutor WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO interlocutor (
    log, interesse_expresso, duvidas, objecoes, resposta_sdr, reacao_interlocutor
) VALUES
('call_26416509236_127.wav', 'Confirmou interesse em créditos tributários de insumos industriais.', 'Como funciona a segurança jurídica do processo perante o Fisco?', 'Nenhuma objeção impeditiva.', 'Maira explicou que a atuação é 100% administrativa via compensação comprovada.', 'Receptivo e concordou prontamente com o agendamento.'),
('call_26416492346_106.wav', 'Interesse em monetizar créditos represados de PIS/Cofins.', 'Isso substitui o trabalho do nosso escritório de contabilidade?', 'Já temos equipe interna e contabilidade contratada.', 'Thais esclareceu que a consultoria atua como braço técnico complementar e pontual.', 'Tranquilizou-se e liberou a agenda.'),
('call_26416492306_108.wav', 'Interesse em avaliar créditos do setor químico.', 'Quais as teses principais?', 'Momento corrido com reunião de diretoria.', 'Thayana agendou retorno sem pressionar.', 'Receptivo e confirmou retorno na segunda às 14h.'),
('call_26416393446_106.wav', 'Sem interesse devido ao regime do Simples Nacional.', 'Não teve.', 'Somos optantes do Simples Nacional.', 'Thais explicou que a campanha exige Lucro Real e encerrou.', 'Agradeceu o profissionalismo.'),
('call_26416385156_108.wav', 'Alto interesse em créditos de subvenção e ICMS fabril.', 'Quais créditos podem ser aplicados em maquinários CNC?', 'Receio de questionamentos do Fisco estadual.', 'Thayana demonstrou que as teses são consolidadas em jurisprudência pacificada.', 'Empolgado e solicitou reunião pelo Teams.'),
('call_26416384826_127.wav', 'Forte interesse em créditos acumulados de exportação.', 'A Sonax atua no RS e conhece as particularidades da SEFAZ local?', 'Não houve objeções.', 'Maira confirmou experiência no polo coureiro-calçadista gaúcho.', 'Muito receptiva e marcou reunião formal.'),
('call_26416349086_128.wav', 'Interesse em revisão pontual de maquinários e PIS/Cofins.', 'Qual o prazo estimado para conclusão do diagnóstico?', 'Fizemos uma revisão há 3 anos.', 'Maria Eduarda ressaltou que normas fiscais mudaram e o diagnóstico é ágil.', 'Concordou com a atualização e aceitou a reunião.'),
('call_26416306166_116.wav', 'Sem interesse devido ao enquadramento no Simples/Presumido.', 'Não teve.', 'Somos Lucro Presumido e pequenos.', 'Jheniffer agradeceu com educação e encerrou a chamada.', 'Satisfeito pelo tratamento rápido e sem insistência.'),
('call_26416298076_128.wav', 'Interesse concreto em teses de distribuidora e atacado.', 'Qual formato da apresentação?', 'Estamos no fechamento contábil e sem tempo agora.', 'Maria Eduarda respeitou o momento de pico de trabalho da contabilidade.', 'Agradeceu a compreensão e confirmou horário de retorno.'),
('call_26416271676_142.wav', 'Interesse condicionado a análise de apresentação.', 'Quais os cases no setor plástico?', 'Exige material prévio institucional.', 'Karolyne concordou em enviar apresentação institucional.', 'Cauteloso e solicitou envio formal.');

-- ----------------------------------------------------------------------------
-- 11. TABELA crm (5 Reuniões Confirmadas | 2 Retornos | 2 Sem Interesse | 1 Material)
-- ----------------------------------------------------------------------------
DELETE FROM crm WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO crm (
    log, acao, responsavel, prazo, dados_extras, resumo
) VALUES
-- 1. Reunião 1
('call_26416509236_127.wav', 'reunião confirmada', 'MAIRA CAROLINE RIBEIRODE OLIVEIRA', '2026-10-15 14:00', 'Link Meet enviado para carlos.mendes@alvoradasul.com.br', 'Reunião agendada com CFO Carlos Mendes. Apresentar tese de insumos metalúrgicos e exclusão de ICMS da base do PIS/Cofins.'),

-- 2. Reunião 2
('call_26416492346_106.wav', 'reunião confirmada', 'THAIS ANISIA GUIMARAES OLIVIERA', '2026-10-16 10:30', 'Convidar especialista tributário de agronegócio/alimentos', 'Reunião confirmada com Diretora Tributária Roberta Guimarães para apresentar recuperação de créditos na cadeia de lácteos.'),

-- 3. Retorno combinado (1)
('call_26416492306_108.wav', 'retorno com data combinado', 'THAYANA MADALENA RAMOS', '2026-10-12 14:00', 'Ligar no celular direto do CFO Marcos', 'Retorno agendado diretamente com o CFO Marcos Vinicius para detalhar as teses do setor químico após sua reunião de diretoria.'),

-- 4. Sem interesse (1) - Fora do perfil
('call_26416393446_106.wav', 'sem interesse explícito', 'THAIS ANISIA GUIMARAES OLIVIERA', 'Não se aplica', 'Lead encerrado no CRM', 'Empresa no Simples Nacional com faturamento de R$ 350 mil mensais. Fora do perfil.'),

-- 5. Reunião 3
('call_26416385156_108.wav', 'reunião confirmada', 'THAYANA MADALENA RAMOS', '2026-10-16 15:00', 'Agendamento no Teams compartilhado com consultor sênior', 'Reunião confirmada com Diretor Sócio Eduardo Fontes para diagnóstico de créditos de ativo permanente e subvenções.'),

-- 6. Reunião 4
('call_26416384826_127.wav', 'reunião confirmada', 'MAIRA CAROLINE RIBEIRODE OLIVEIRA', '2026-10-14 11:00', 'Enviar convite para simone.financeiro@calcadosnovapetropolis.com.br', 'Reunião confirmada com Simone Zimmer. Foco em créditos estaduais de ICMS decorrentes de exportação de calçados.'),

-- 7. Reunião 5
('call_26416349086_128.wav', 'reunião confirmada', 'MARIA EDUARDA PEREIRA', '2026-10-15 15:00', 'Enviar material prévio para juliana@serraesperanca.com.br', 'Reunião confirmada com Juliana Castelli. Foco em créditos PIS/Cofins do agronegócio e maquinários agrícolas.'),

-- 8. Sem interesse (2) - Fora do perfil
('call_26416306166_116.wav', 'sem interesse explícito', 'JHENIFFER QUADROS', 'Não se aplica', 'Lead desqualificado no CRM', 'Empresa desqualificada: opera no Lucro Presumido e com faturamento inferior a R$ 1 milhão mensal.'),

-- 9. Retorno combinado (2)
('call_26416298076_128.wav', 'retorno com data combinado', 'MARIA EDUARDA PEREIRA', '2026-10-13 10:00', 'Ligar direto no celular corporativo da CFO', 'Contato com CFO Cláudia Nogueira agendado para terça 10h após conclusão do fechamento contábil mensal.'),

-- 10. Material solicitado (1)
('call_26416271676_142.wav', 'envio de material solicitado', 'Karolyne Gluszczynski', '2026-10-07 18:00', 'Disparar apresentação institucional para danilo.fiscal@plasticoaltoiguacu.com.br', 'Material institucional solicitado pelo Diretor Danilo Prado. Follow-up programado para 2 dias após envio.');

-- ----------------------------------------------------------------------------
-- 12. TABELA analise_perfil (6 Confirmado | 2 Pendente | 2 Fora do Perfil)
-- ----------------------------------------------------------------------------
DELETE FROM analise_perfil WHERE log IN (
    'call_26416509236_127.wav', 'call_26416492346_106.wav', 'call_26416492306_108.wav',
    'call_26416393446_106.wav', 'call_26416385156_108.wav', 'call_26416384826_127.wav',
    'call_26416349086_128.wav', 'call_26416306166_116.wav', 'call_26416298076_128.wav',
    'call_26416271676_142.wav', 'call_26416268606_135.wav'
);

INSERT INTO analise_perfil (
    log, setor, setor_origem, regime_tributario, regime_origem,
    faturamento_declarado_texto, faturamento_anual, faturamento_mensal,
    periodo_meses, faturamento_origem, faturamento_regra, detalhes_faturamento
) VALUES
-- 1. Confirmado
('call_26416509236_127.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Real', 'confirmado pelo interlocutor',
 'Cerca de dois milhões e meio por mês', 30000000.00, 2500000.00, 1, 'confirmado pelo interlocutor', 'declarado_mensal',
 'Faturamento mensal informado diretamente pelo CFO na ligação com Maira.'),

-- 2. Confirmado
('call_26416492346_106.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Real', 'confirmado pelo interlocutor',
 'Faturamento anual acima de 50 milhões', 50400000.00, 4200000.00, 12, 'confirmado pelo interlocutor', 'calculado_12_meses',
 'Média mensal calculada deterministicamente a partir de R$ 50,4M informados para 12 meses a Thais.'),

-- 3. Pendente
('call_26416492306_108.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Real', 'afirmado apenas pelo SDR',
 'Quase dois milhões mensais', 21600000.00, 1800000.00, 1, 'inferência plausível', 'nao_confirmado',
 'Faturamento e regime sinalizados pelo Diretor Marcos a Thayana, pendente de formalização técnica.'),

-- 4. Fora do perfil
('call_26416393446_106.wav', 'outro confirmado', 'confirmado pelo interlocutor', 'Simples Nacional', 'confirmado pelo interlocutor',
 'Faturamento em torno de 350 mil', 4200000.00, 350000.00, 1, 'confirmado pelo interlocutor', 'declarado_mensal',
 'Faturamento e regime declarados pelo proprietário incompatíveis com a campanha.'),

-- 5. Confirmado
('call_26416385156_108.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Real', 'confirmado pelo interlocutor',
 'Faturamos 2,1 milhões ao mês', 25200000.00, 2100000.00, 1, 'confirmado pelo interlocutor', 'declarado_mensal',
 'Faturamento mensal confirmado pelo diretor sócio a Thayana.'),

-- 6. Confirmado
('call_26416384826_127.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Real', 'confirmado pelo interlocutor',
 'Nosso faturamento mensal é de 1,9 milhão', 22800000.00, 1900000.00, 1, 'confirmado pelo interlocutor', 'declarado_mensal',
 'Faturamento mensal declarado de R$ 1,9M no Lucro Real a Maira.'),

-- 7. Confirmado
('call_26416349086_128.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Real', 'confirmado pelo interlocutor',
 'Fechamos em 36 milhões ano passado', 36000000.00, 3000000.00, 12, 'confirmado pelo interlocutor', 'calculado_12_meses',
 'Faturamento mensal de R$ 3M derivado de R$ 36M anual informado pela diretora financeira a Maria Eduarda.'),

-- 8. Fora do perfil
('call_26416306166_116.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Presumido', 'confirmado pelo interlocutor',
 'Gira em 600 mil mensais', 7200000.00, 600000.00, 1, 'confirmado pelo interlocutor', 'declarado_mensal',
 'Empresa declarou expressamente Lucro Presumido e R$ 600k/mês a Jheniffer, ficando fora do perfil.'),

-- 9. Confirmado
('call_26416298076_128.wav', 'outro confirmado', 'confirmado pelo interlocutor', 'Lucro Real', 'confirmado pelo interlocutor',
 'Cerca de 4,5 milhões por mês', 54000000.00, 4500000.00, 1, 'confirmado pelo interlocutor', 'declarado_mensal',
 'Faturamento mensal de 4,5 milhões confirmado pela CFO a Maria Eduarda.'),

-- 10. Pendente
('call_26416271676_142.wav', 'industrial', 'confirmado pelo interlocutor', 'Lucro Real', 'confirmado pelo interlocutor',
 'Aproximadamente 1,5 milhão ao mês', 18000000.00, 1500000.00, 1, 'afirmado apenas pelo SDR', 'nao_confirmado',
 'Faturamento mencionado pelo Diretor Danilo a Karolyne, aguardando envio e análise do material.');

COMMIT;
