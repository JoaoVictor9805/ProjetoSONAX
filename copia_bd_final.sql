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
    faturamento_origem VARCHAR(50),
    data_status_comercial TIMESTAMP
);

CREATE INDEX IF NOT EXISTS empresa_telefone ON empresa(telefone);
CREATE INDEX IF NOT EXISTS idx_empresa_data_status ON empresa(data_status_comercial);


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
    conversa_decisor VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (conversa_decisor IN ('s','n')),
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
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log)
);


CREATE TABLE IF NOT EXISTS avaliacao_oportunidade_treinamento (
    log VARCHAR(255) NOT NULL,
    codigo_oportunidade VARCHAR(20) NOT NULL,
    
    PRIMARY KEY (log, codigo_oportunidade),
    FOREIGN KEY (log) REFERENCES avaliacao_sdr(log) ON DELETE CASCADE,
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
    situacao_investigada VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (situacao_investigada IN ('s', 'n')),
    problema TEXT,
    problema_investigado VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (problema_investigado IN ('s', 'n')),
    implicacao TEXT,
    implicacao_investigada VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (implicacao_investigada IN ('s', 'n')),
    necessidade_solucao TEXT,
    necessidade_investigada VARCHAR(1) NOT NULL DEFAULT 'n' CHECK (necessidade_investigada IN ('s', 'n')),
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
    acao VARCHAR(100) CHECK (acao IS NULL OR acao IN (
        'reunião confirmada',
        'reunião proposta sem aceite',
        'retorno com data combinado',
        'envio de material solicitado',
        'sem próximo passo definido',
        'sem interesse explícito',
        'Não se aplica'
    )),
    responsavel VARCHAR(100),
    prazo VARCHAR(100),
    prazo_data TIMESTAMP,
    dados_extras TEXT,
    resumo TEXT,
   
    FOREIGN KEY (log) REFERENCES avaliacao_ia(log)
);

CREATE INDEX IF NOT EXISTS idx_crm_prazo_data ON crm(prazo_data);


CREATE TABLE IF NOT EXISTS analise_perfil (
    log VARCHAR(255) PRIMARY KEY NOT NULL,
    setor VARCHAR(50) CHECK (setor IS NULL OR setor IN (
        'industrial',
        'outro confirmado',
        'não informado'
    )),
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
        'não informado'
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
('CRIT_PROX_PASSO', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro')
ON CONFLICT (codigo) DO NOTHING;


INSERT INTO dim_oportunidade_treinamento (codigo, fase_venda, descricao) VALUES
-- 1. Abertura e Relevância
('OP_ABERT_01', '1. Abertura e Relevância', 'Apresentar-se com clareza e dizer o motivo da ligação nos primeiros segundos'),
('OP_ABERT_02', '1. Abertura e Relevância', 'Usar a oportunidade de crédito tributário como gancho inicial nos primeiros segundos'),
('OP_ABERT_03', '1. Abertura e Relevância', 'Expor o benefício de caixa sem sobrecarga técnica ou juridiquês'),
('OP_ABERT_04', '1. Abertura e Relevância', 'Confirmar se o interlocutor lida com a área fiscal ou financeira antes de aprofundar'),
('OP_ABERT_05', '1. Abertura e Relevância', 'Superar a recepção e direcionar o contato para o responsável financeiro ou fiscal'),
('OP_ABERT_06', '1. Abertura e Relevância', 'Tratar o crédito como hipótese comercial sem prometer valores certos ou garantidos'),

-- 2. Descoberta SPIN
('OP_SPIN_01', '2. Descoberta SPIN', 'Fazer perguntas rápidas para mapear o cenário atual sem prolongar a chamada'),
('OP_SPIN_02', '2. Descoberta SPIN', 'Investigar atritos fiscais ou limitações da rotina contábil da empresa'),
('OP_SPIN_03', '2. Descoberta SPIN', 'Destacar o risco de prescrição da janela de 5 anos e dinheiro parado'),
('OP_SPIN_04', '2. Descoberta SPIN', 'Conectar a recuperação tributária à dor do lead e checar o interesse em resgatar caixa'),
('OP_SPIN_05', '2. Descoberta SPIN', 'Estimular o interlocutor a admitir a dor em vez de assumir teses próprias do SDR'),

-- 3. Investigação de Perfil Técnico (Crucial)
('OP_PERF_01', '3. Investigação de Perfil Técnico', 'Confirmar ativamente se a empresa opera no regime de Lucro Real'),
('OP_PERF_02', '3. Investigação de Perfil Técnico', 'Confirmar faturamento mínimo mensal igual ou superior a R$ 1 milhão'),
('OP_PERF_03', '3. Investigação de Perfil Técnico', 'Identificar se o segmento é industrial ou registrar outro setor confirmado'),
('OP_PERF_04', '3. Investigação de Perfil Técnico', 'Formular perguntas para que o próprio interlocutor declare e valide as informações'),

-- 4. Investigação BANT (Budget, Authority, Need, Timeline)
('OP_BANT_01', '4. Investigação BANT', 'Sondar a viabilidade de contratação e reforçar que o diagnóstico inicial é sem custo'),
('OP_BANT_02', '4. Investigação BANT', 'Mapear o papel do interlocutor na decisão e descobrir quem mais precisa participar'),
('OP_BANT_03', '4. Investigação BANT', 'Fazer perguntas para o lead verbalizar a necessidade em vez de apenas empurrar o pitch'),
('OP_BANT_04', '4. Investigação BANT', 'Mapear prazo ou evento motivador para criar senso de urgência no próximo passo'),

-- 5. Escuta e Objeções
('OP_ESC_01', '5. Escuta e Objeções', 'Posicionar o projeto como suporte complementar e técnico, sem confrontar a contabilidade atual'),
('OP_ESC_02', '5. Escuta e Objeções', 'Praticar escuta ativa espelhando palavras do lead antes de contra-argumentar'),
('OP_ESC_03', '5. Escuta e Objeções', 'Acolher com segurança o receio de riscos ou fiscalização, explicando o processo técnico'),
('OP_ESC_04', '5. Escuta e Objeções', 'Evitar interrupções e sobreposição de falas no fluxo da conversa'),
('OP_ESC_05', '5. Escuta e Objeções', 'Investigar a razão de desinteresses genéricos para identificar e contornar a objeção real'),

-- 6. Próximo Passo e Compromisso
('OP_PROX_01', '6. Próximo Passo e Compromisso', 'Sugerir dias e horários concretos usando dupla escolha em vez de perguntas abertas'),
('OP_PROX_02', '6. Próximo Passo e Compromisso', 'Confirmar claramente o formato da reunião (online ou presencial) e obter o contato correto'),
('OP_PROX_03', '6. Próximo Passo e Compromisso', 'Reancorar o valor da reunião técnica ao contornar pedidos de envio por e-mail'),
('OP_PROX_04', '6. Próximo Passo e Compromisso', 'Fixar com precisão o responsável, dia e horário quando o retorno for necessário'),

-- 7. Direcionamento Final e Resolução da Chamada
('OP_DIR_01', '7. Direcionamento Final e Resolução da Chamada', 'Encerrar o contato com polidez e objetividade ao constatar empresa fora do perfil'),
('OP_DIR_02', '7. Direcionamento Final e Resolução da Chamada', 'Superar a barreira da recepção para falar com quem decide'),
('OP_DIR_03', '7. Direcionamento Final e Resolução da Chamada', 'Conduzir a chamada até um status comercial conclusivo, evitando indefinição')
ON CONFLICT (codigo) DO UPDATE SET 
    fase_venda = EXCLUDED.fase_venda,
    descricao = EXCLUDED.descricao;

