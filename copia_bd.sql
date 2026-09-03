-- ==========================
-- Etapa 01
-- ==========================

CREATE TABLE origem (
	agente_nome varchar(100) PRIMARY KEY not null,
	ramal INT not null,
	dt_inicio TIMESTAMP(0) not null, -- primeira ligação do usuário
	dt_fim TIMESTAMP(0) not null -- última ligação do usuário
);

CREATE TABLE registro_chamadas (
	id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
	ramal INT not null,
	agente_nome varchar(100) not null,
	data_ligacao TIMESTAMP(0) not null,
	log varchar(255) UNIQUE,
	transcricao TEXT,
	
	foreign key (agente_nome) references origem(agente_nome)
);

TRUNCATE TABLE origem CASCADE;
TRUNCATE TABLE registro_chamadas;
DROP TABLE registro_chamadas, origem CASCADE;

INSERT INTO origem (ramal, agente_nome, dt_inicio, dt_fim) VALUES
(121, 'Roberto Almeida', '2025-01-01 08:22:03', '2025-03-15 18:53:44'),
(121, 'Lucas Ferreira', '2025-03-16 08:01:04', '2025-06-20 18:03:11'),
(121, 'Ana Clara Silva', '2025-06-21 08:59:31', '2026-01-10 18:40:22'),
(121, 'Vanessa Dias', '2026-01-11 08:09:21', '2026-08-31 18:54:32'),
(122, 'Felipe Oliveira', '2025-01-01 08:44:13', '2026-08-31 18:56:07');


select * from origem; 
select * from registro_chamadas; 

-- ==========================
-- Etapa 02
-- ==========================

CREATE TABLE avaliacao_ia (
	id_avaliacao INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
	registro_chamada_id INT not null,
	nota_final INT not null,
	feedback_geral TEXT not null,
	data_avaliacao date not null,
	modelo_ia varchar(50) not null

	foreign key(registro_chamadas_id) references registro_chamadas(id)
);

CREATE TABLE avaliacao_criterio (
	id_av_por_criterio INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
	id_avaliacao INT not null,
	criterio ENUM('chamar pelo nome', 'agir com empatia', 'ouvir com atencao', 'eficiencia operacional', 'conexao humana', 'surpreender'),
	nota_criterio INT not null,
	justificativa_criterio TEXT
	
	foreign key(id_avaliacao) references avaliacao_ia(id_avaliacao)
);