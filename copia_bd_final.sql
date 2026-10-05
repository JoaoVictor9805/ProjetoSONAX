-- 1. TABELAS INDEPENDENTES E DIMENSÕES (Devem ser criadas primeiro)


CREATE TABLE IF NOT EXISTS chamadas (
    protocolo BIGINT,
    identificacao_cliente BIGINT,
    estado_ddd VARCHAR(3),
    numero VARCHAR(20),
    atendido CHAR(1),
    ramal VARCHAR(20),
    duracao_segundos INT,
    fila_id INT,
    fila_descricao VARCHAR(150),
    tabulacao_id INT,
    tabulacao_descricao VARCHAR(150),
    agente_login VARCHAR(50),
    agente_nome VARCHAR(100),
    campanha_id INT,
    campanha_descricao VARCHAR(150),
    dt_inicio TIMESTAMP,
    dt_fim TIMESTAMP,
    status VARCHAR(50),
    hash_registro VARCHAR(64),
    last_sync TIMESTAMP
);


CREATE TABLE IF NOT EXISTS empresa (
    id_empresa INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    telefone VARCHAR(20),
    setor VARCHAR(100),
    regime_tributario VARCHAR(50),
    faturamento_mensal NUMERIC(15,2),
    faturamento_anual NUMERIC(15,2),
    status_comercial VARCHAR(100),
    fonte_dados TEXT,
    setor_origem VARCHAR(50),
    regime_origem VARCHAR(50),
    faturamento_origem VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS empresa_telefone ON empresa(telefone);


CREATE TABLE IF NOT EXISTS registro_chamadas (
    log VARCHAR(255) PRIMARY KEY,
    protocolo BIGINT,
    transcricao TEXT,
    revisao TEXT,
    id_empresa INT REFERENCES empresa(id_empresa)
);


CREATE TABLE IF NOT EXISTS dim_oportunidade_treinamento (
    codigo VARCHAR(20) PRIMARY KEY,
    fase_venda VARCHAR(100),
    descricao TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS dim_criterio_avaliacao (
    codigo VARCHAR(20) PRIMARY KEY,
    descricao TEXT NOT NULL
);


-- 2. TABELAS DEPENDENTES (Nível 1)


CREATE TABLE IF NOT EXISTS avaliacao_ia (
    log VARCHAR(255) PRIMARY KEY NOT NULL,
    data_avaliacao DATE NOT NULL,
    modelo_ia VARCHAR(50) NOT NULL,
    interlocutor VARCHAR(100),
    cargo VARCHAR(100),
    empresa_contatada INT,
    resultado VARCHAR(255),
    ligacao_relevante VARCHAR(1) NOT NULL CHECK (ligacao_relevante IN ('s','n')),
    reuniao_confirmada VARCHAR(1) NOT NULL CHECK (reuniao_confirmada IN ('s','n')),
    data_confirmada VARCHAR(1) NOT NULL CHECK (data_confirmada IN ('s','n')),
    resultado_frase TEXT NOT NULL,
   
    FOREIGN KEY (log) REFERENCES registro_chamadas(log),
    FOREIGN KEY (empresa_contatada) REFERENCES empresa(id_empresa)
);


-- 3. TABELAS DEPENDENTES (Nível 2 - Referenciam a avaliacao_ia e as Dimensões)


CREATE TABLE IF NOT EXISTS avaliacao_sdr (
	log VARCHAR(255) PRIMARY KEY NOT NULL,
	nota_final INT,
    feedback_geral TEXT NOT NULL,
    acertos TEXT,
    melhorias TEXT,
    frase_alternativa VARCHAR(500),
    codigo_oportunidade VARCHAR(20),    
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log),
    FOREIGN KEY (codigo_oportunidade) REFERENCES dim_oportunidade_treinamento(codigo)
);


CREATE TABLE IF NOT EXISTS avaliacao_criterio (
    id_criterio INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    log VARCHAR(255) NOT NULL,
    criterio VARCHAR(100) NOT NULL,
    nota_criterio INT,
    justificativa_criterio TEXT,
    codigo_criterio VARCHAR(20) NOT NULL,
   
    FOREIGN KEY (log) REFERENCES avaliacao_sdr(log),
    FOREIGN KEY (codigo_criterio) REFERENCES dim_criterio_avaliacao(codigo)
);


CREATE TABLE IF NOT EXISTS analise_spin (
    log VARCHAR(255) PRIMARY KEY NOT null,
    situacao TEXT,
    problema TEXT,
    implicacao TEXT,
    necessidade_solucao TEXT,
    evidencias TEXT,
    lacunas TEXT,
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log)
);


CREATE TABLE IF NOT EXISTS analise_bant (
    log VARCHAR(255) PRIMARY KEY NOT null,
    budget_classificacao VARCHAR(50),
    budget_evidencia TEXT,
    authority_classificacao VARCHAR(50),
    authority_evidencia TEXT,
    need_classificacao VARCHAR(50),
    need_evidencia TEXT,
    timeline_classificacao VARCHAR(50),
    timeline_evidencia TEXT,
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log)
);


CREATE TABLE IF NOT EXISTS interlocutor (
	log VARCHAR(255) PRIMARY KEY NOT null,
	interesse_expresso TEXT,
    duvidas TEXT,            
    objecoes TEXT,          
    resposta_sdr TEXT,      
    reacao_interlocutor TEXT,
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log)
);


CREATE TABLE IF NOT EXISTS crm (
    log VARCHAR(255) PRIMARY KEY NOT null,
    acao VARCHAR(255),
    responsavel VARCHAR(100),
    prazo VARCHAR(100),
    dados_extras TEXT,
    resumo TEXT,
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log)
);


CREATE TABLE IF NOT EXISTS analise_perfil (
    log VARCHAR(255) PRIMARY KEY NOT NULL,
    setor VARCHAR(100),
    setor_origem VARCHAR(50) NOT NULL CHECK (setor_origem IN (
        'confirmado pelo interlocutor',
        'afirmado apenas pelo SDR',
        'inferência plausível',
        'não informado'
    )),
    regime_tributario VARCHAR(50),
    regime_origem VARCHAR(50) NOT NULL CHECK (regime_origem IN (
        'confirmado pelo interlocutor',
        'afirmado apenas pelo SDR',
        'inferência plausível',
        'não informado'
    )),
    faturamento_declarado_texto TEXT,
    faturamento_anual NUMERIC(15,2),
    faturamento_mensal NUMERIC(15,2),
    periodo_meses INT,
    faturamento_origem VARCHAR(50) NOT NULL CHECK (faturamento_origem IN (
        'confirmado pelo interlocutor',
        'afirmado apenas pelo SDR',
        'inferência plausível',
        'não informado',
        'calculado'
    )),
    faturamento_regra VARCHAR(50) NOT NULL CHECK (faturamento_regra IN (
        'declarado_mensal',
        'calculado_12_meses',
        'nao_confirmado',
        'nao_informado'
    )),
    detalhes_faturamento TEXT,
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log) ON DELETE CASCADE
);


-- 4. INSERÇÃO DOS DADOS NAS DIMENSÕES


INSERT INTO dim_criterio_avaliacao (codigo, descricao) VALUES
('CRIT_ABERTURA', 'Abertura clara, motivo do contato e relevância para o interlocutor'),
('CRIT_SPIN', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução'),
('CRIT_PERFIL', 'Investigação adequada do perfil: setor, regime tributário, faturamento'),
('CRIT_BANT', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo'),
('CRIT_ESCUTA', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções'),
('CRIT_PROX_PASSO', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro');


INSERT INTO dim_oportunidade_treinamento (codigo, fase_venda, descricao) VALUES
-- 1. Abertura e Relevância
('OP_ABERT_01', '1. Abertura e Relevância', 'Apresentar-se e situar a empresa com objetividade: Dizer nome e empresa de forma clara e rápida, sem monólogos institucionais, partindo direto para a razão da chamada.'),
('OP_ABERT_02', '1. Abertura e Relevância', 'Utilizar a oportunidade de crédito mapeada como gancho: Usar o dado/tese tributária ou o segmento da empresa já presente no sistema para justificar o motivo do contato logo nos primeiros segundos.'),
('OP_ABERT_03', '1. Abertura e Relevância', 'Expor o benefício da oportunidade sem sobrecarga técnica: Apresentar a proposta de crédito tributário com foco no ganho para a empresa (recuperação de valores, fôlego de caixa), evitando juridiquês ou detalhes fiscais complexos logo na largada.'),
('OP_ABERT_04', '1. Abertura e Relevância', 'Confirmar o alinhamento com o interlocutor antes de aprofundar: Checar se a pessoa na linha é quem lida com a área fiscal/financeira ou captar a atenção dela antes de detalhar o cenário.'),
('OP_ABERT_05', '1. Abertura e Relevância', 'Direcionar o contato para o responsável fiscal, tributário ou financeiro: Identificar a área do interlocutor e, caso o contato esteja retido na recepção ou em setor não correlato, buscar a transferência ou dados diretos do decisor competente.'),
('OP_ABERT_06', '1. Abertura e Relevância', 'Evitar promessas de valores ou garantia de créditos: Tratar o benefício fiscal como hipótese comercial a ser avaliada tecnicamente, sem afirmar créditos certos, valores recuperáveis garantidos ou emitir conclusões jurídicas na chamada.'),


-- 2. Descoberta SPIN
('OP_SPIN_01', '2. Descoberta SPIN', 'Mapear o cenário inicial com perguntas rápidas e indispensáveis: Coletar apenas os dados de situação estritamente necessários para direcionar a conversa, mantendo a abordagem dinâmica e focada na oportunidade.'),
('OP_SPIN_02', '2. Descoberta SPIN', 'Mapear atritos fiscais ou lacunas na rotina da empresa: Identificar se a contabilidade atual não tem braço para revisar tributos ou se a empresa tem receio/dúvidas sobre créditos acumulados.'),
('OP_SPIN_03', '2. Descoberta SPIN', 'Destacar implicações simples e tangíveis (como a prescrição de créditos): Evidenciar o impacto prático de não revisar o cenário fiscal, focando no risco iminente de prescrição (perda da janela de 5 anos) ou dinheiro parado sem render para a operação.'),
('OP_SPIN_04', '2. Descoberta SPIN', 'Conectar a solução à dor e checar a viabilidade de avanço: Posicionar a oportunidade de crédito como a solução direta para a lacuna mapeada e checar se faz sentido para o lead avaliar esse resgate de caixa.'),
('OP_SPIN_05', '2. Descoberta SPIN', 'Diferenciar dor reconhecida pelo lead de argumentos do SDR: Estimular o interlocutor a admitir expressamente a lacuna ou interesse na revisão fiscal, evitando assumir teses do SDR como dores já confirmadas pela empresa.'),


-- 3. Investigação de Perfil Técnico (Crucial)
('OP_PERF_01', '3. Investigação de Perfil Técnico', 'Investigar o regime tributário da empresa: Confirmar ativamente se a empresa opera no regime de Lucro Real, que é o critério eliminatório da campanha, sem fazer deduções baseadas no porte do lead.'),
('OP_PERF_02', '3. Investigação de Perfil Técnico', 'Confirmar o faturamento mínimo: Garantir que a empresa possui faturamento igual ou superior a R$ 1 milhão mensal (ou média anual correspondente), diferenciando dados confirmados pelo interlocutor de meras suposições.'),
('OP_PERF_03', '3. Investigação de Perfil Técnico', 'Mapear o segmento de atuação: Identificar se a empresa pertence ao setor industrial (segmento preferencial) ou registrar claramente caso pertença a outro setor, sem descartá-la automaticamente se cumprir faturamento e regime tributário.'),
('OP_PERF_04', '3. Investigação de Perfil Técnico', 'Garantir a confirmação ativa dos dados: Avaliar se o SDR formulou as perguntas de maneira que o próprio interlocutor declare ou valide as informações, penalizando abordagens em que o SDR apenas joga a afirmação no ar sem obter o "sim" do cliente.'),


-- 4. Investigação BANT (Budget, Authority, Need, Timeline)
('OP_BANT_01', '4. Investigação BANT', 'Budget (Viabilidade Comercial): Avaliar se o SDR sondou sutilmente o processo interno de aprovação ou a viabilidade de contratação futura, utilizando a gratuidade do diagnóstico inicial de forma estratégica para desarmar objeções de orçamento.'),
('OP_BANT_02', '4. Investigação BANT', 'Authority (Autoridade): Avaliar se o SDR investigou ativamente o papel do interlocutor na tomada de decisão (se ele decide, influencia ou apenas repassa recados) e se perguntou quem mais precisaria estar envolvido para o negócio avançar.'),
('OP_BANT_03', '4. Investigação BANT', 'Need (Necessidade): Observar se o SDR fez as perguntas certas para estimular o próprio lead a verbalizar um interesse ou problema real, penalizando a postura de apenas apresentar o pitch comercial e assumir que o cliente "comprou" a ideia.'),
('OP_BANT_04', '4. Investigação BANT', 'Timeline (Prazo): Verificar se o SDR tentou mapear uma prioridade, um evento motivador ou um prazo ideal para a empresa resolver a questão fiscal, buscando gerar senso de urgência para o próximo passo.'),


-- 5. Escuta e Objeções
('OP_ESC_01', '5. Escuta e Objeções', 'Posicionar o trabalho como complementar à contabilidade atual: Ao ouvir que a empresa já tem contador/escritório, esclarecer de forma respeitosa que o projeto não substitui a contabilidade de rotina, funcionando como um suporte técnico especializado para teses específicas.'),
('OP_ESC_02', '5. Escuta e Objeções', 'Retomar e espelhar termos utilizados pelo lead: Demonstrar escuta ativa citando fatos ou palavras que o próprio cliente acabou de mencionar antes de contra-argumentar, evitando parecer uma leitura de script pronta.'),
('OP_ESC_03', '5. Escuta e Objeções', 'Tratar com empatia o receio de riscos ou fiscalização: Quando o lead demonstrar desconfiança ou medo de atrito com o Fisco, acolher a dúvida e esclarecer a segurança do processo administrativo com dados concretos, sem confrontar ou desmerecer o receio do cliente.'),
('OP_ESC_04', '5. Escuta e Objeções', 'Evitar interrupções e sobreposição de falas no fluxo da conversa: Esperar a conclusão do raciocínio do interlocutor antes de intervir, mantendo a postura consultiva mesmo diante de resistências.'),
('OP_ESC_05', '5. Escuta e Objeções', 'Investigar o motivo do desinteresse para direcionar a melhor saída: Diante de recusas genéricas como "não temos interesse", questionar respeitosamente a razão desse posicionamento para identificar a real objeção e conduzir com a solução mais adequada ao cenário do cliente (ex.: flexibilizar formato, esclarecer o modelo de risco zero ou focar em outra tese).'),


-- 6. Próximo Passo e Compromisso
('OP_PROX_01', '6. Próximo Passo e Compromisso', 'Propor opções objetivas de data e horário (técnica de dupla escolha): Sugerir dias e horários concretos (ex.: "amanhã às 14h ou quinta pela manhã fica melhor para você?") em vez de perguntas genéricas e abertas como "quando podemos conversar?".'),
('OP_PROX_02', '6. Próximo Passo e Compromisso', 'Alinhar formalmente a modalidade escolhida (online ou presencial): Confirmar com clareza o formato preferido pelo lead — se por link de videoconferência ou visita do executivo na sede da empresa — coletando o endereço ou e-mail correto conforme o caso.'),
('OP_PROX_03', '6. Próximo Passo e Compromisso', 'Contornar o pedido passivo de envio de material: Diante de respostas evasivas como "mande por e-mail" ou "vamos conversando", reancorar o valor da conversa técnica para buscar um compromisso com data e horário definidos.'),
('OP_PROX_04', '6. Próximo Passo e Compromisso', 'Definir responsável e data concreta para retornos agendados: Quando a reunião imediata não for viável, estabelecer com precisão quem realizará o próximo contato e fixar dia e horário para a retomada.'),


-- 7. Direcionamento Final e Resolução da Chamada
('OP_DIR_01', '7. Direcionamento Final e Resolução da Chamada', 'Direcionamento assertivo com base no perfil: Avaliar se o SDR identificou corretamente quando uma empresa estava fora do perfil (ex: Simples Nacional ou faturamento baixo) e encerrou a conversa de forma polida e adequada, sem forçar avanço em leads desqualificados.'),
('OP_DIR_02', '7. Direcionamento Final e Resolução da Chamada', 'Condução para uma conversa substantiva: Observar se o vendedor teve a habilidade de transpor a barreira inicial (recepção, desinteresse inicial) para gerar uma conversa real com o decisor, em vez de aceitar recusas passivas nos primeiros segundos.'),
('OP_DIR_03', '7. Direcionamento Final e Resolução da Chamada', 'Consolidação de um status claro: Verificar se o SDR conduziu a ligação até um desfecho conclusivo (perfil confirmado, perfil pendente com próximo passo ou descarte claro), evitando encerrar a chamada deixando o status da empresa como uma "área cinzenta" de dados insuficientes por falta de perguntas.');

