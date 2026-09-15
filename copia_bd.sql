-- ==========================
-- Etapa 01
-- ==========================

DROP TABLE registro_chamadas, origem CASCADE;

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

alter table registro_chamadas add column revisao TEXT;

alter table registro_chamadas add column nota INT;

alter table registro_chamadas add column resumo TEXT;


TRUNCATE TABLE origem CASCADE;

TRUNCATE TABLE registro_chamadas restart IDENTITY;

INSERT INTO origem (ramal, agente_nome, dt_inicio, dt_fim) VALUES
(103, 'Marcos Vinicius Rocha', '2025-01-03 08:12:14', '2025-05-18 17:45:32'),
(103, 'Juliana Mendes Costa', '2025-05-19 08:03:21', '2026-08-29 18:12:44'),

(104, 'Rafael Henrique Souza', '2025-01-07 08:31:42', '2025-07-22 18:21:13'),
(104, 'Camila Beatriz Martins', '2025-07-23 08:15:08', '2026-08-30 18:43:27'),

(105, 'Gustavo Pereira Lima', '2025-01-10 08:22:51', '2025-06-14 18:07:35'),
(105, 'Larissa Fernanda Alves', '2025-06-15 08:04:19', '2026-08-28 18:51:06'),

(106, 'Daniel Augusto Ribeiro', '2025-01-14 08:46:27', '2025-09-03 18:16:41'),
(106, 'Beatriz Cristina Nunes', '2025-09-04 08:11:53', '2026-08-31 18:37:22'),

(107, 'Thiago Rodrigues Martins', '2025-02-02 08:19:36', '2025-08-11 18:42:15'),
(107, 'Amanda Vitória Cardoso', '2025-08-12 08:06:44', '2026-08-27 18:29:51'),

(108, 'Bruno Eduardo Carvalho', '2025-02-05 08:37:12', '2025-10-19 18:11:28'),
(108, 'Leticia Gabriela Moura', '2025-10-20 08:14:27', '2026-08-30 18:46:09'),

(109, 'Eduardo Felipe Barbosa', '2025-02-11 08:08:43', '2025-07-30 18:33:17'),
(109, 'Mariana Lopes Teixeira', '2025-07-31 08:21:09', '2026-08-29 18:55:42'),

(110, 'Pedro Henrique Castro', '2025-02-17 08:42:18', '2025-11-08 18:24:36'),
(110, 'Carolina Isabel Freitas', '2025-11-09 08:09:31', '2026-08-31 18:41:53'),

(111, 'Felipe Gabriel Monteiro', '2025-03-01 08:16:25', '2025-08-25 18:38:44'),
(111, 'Isabela Cristina Ramos', '2025-08-26 08:05:17', '2026-08-28 18:49:21'),

(112, 'Anderson Luiz Fernandes', '2025-03-04 08:29:47', '2025-10-12 18:17:35'),
(112, 'Renata Caroline Duarte', '2025-10-13 08:13:22', '2026-08-30 18:36:48'),

(113, 'Ricardo Alexandre Dias', '2025-03-08 08:41:09', '2025-09-21 18:27:53'),
(113, 'Patricia Helena Gomes', '2025-09-22 08:07:45', '2026-08-31 18:52:17'),

(114, 'Leonardo Martins Pinto', '2025-03-12 08:11:38', '2025-08-03 18:44:26'),
(114, 'Vanessa Cristina Lopes', '2025-08-04 08:18:52', '2026-08-29 18:31:09'),

(115, 'Matheus Vinicius Silva', '2025-03-18 08:35:21', '2025-11-16 18:09:47'),
(115, 'Gabriela Fernanda Castro', '2025-11-17 08:06:34', '2026-08-30 18:48:32'),

(116, 'Diego Henrique Oliveira', '2025-03-24 08:23:56', '2025-09-14 18:35:12'),
(116, 'Natalia Beatriz Santos', '2025-09-15 08:12:07', '2026-08-31 18:39:45'),

(117, 'Caio Augusto Martins', '2025-04-02 08:47:31', '2025-10-05 18:22:18'),
(117, 'Priscila Renata Ferreira', '2025-10-06 08:09:43', '2026-08-28 18:54:27'),

(118, 'Henrique Eduardo Ramos', '2025-04-07 08:14:26', '2025-08-18 18:46:39'),
(118, 'Sabrina Caroline Melo', '2025-08-19 08:04:58', '2026-08-30 18:33:16'),

(119, 'Vitor Gabriel Almeida', '2025-04-13 08:32:17', '2025-12-02 18:18:44'),
(119, 'Aline Beatriz Correia', '2025-12-03 08:11:29', '2026-08-31 18:47:53'),

(120, 'Rodrigo Felipe Martins', '2025-04-19 08:27:41', '2025-09-28 18:29:35'),
(120, 'Monique Cristina Vieira', '2025-09-29 08:06:13', '2026-08-29 18:42:21'),

(121, 'Alexandre Roberto Mendes', '2024-01-08 08:17:32', '2024-12-20 18:41:26'),
(121, 'Fernanda Luiza Carvalho', '2024-12-21 08:09:14', '2024-12-31 18:36:48'),
(121, 'Roberto Almeida', '2025-01-01 08:22:03', '2025-03-15 18:53:44'),
(121, 'Lucas Ferreira', '2025-03-16 08:01:04', '2025-06-20 18:03:11'),
(121, 'Ana Clara Silva', '2025-06-21 08:59:31', '2026-01-10 18:40:22'),
(121, 'Vanessa Dias', '2026-01-11 08:09:21', '2026-08-31 18:54:32'),

(122, 'Samuel Henrique Duarte', '2024-01-05 08:26:43', '2025-02-28 18:19:57'),
(122, 'Claudia Regina Martins', '2025-03-01 08:07:25', '2025-03-15 18:44:13'),
(122, 'Felipe Oliveira', '2025-01-01 08:44:13', '2026-08-31 18:56:07'),

(123, 'Wesley Augusto Rocha', '2025-05-02 08:38:16', '2025-10-27 18:25:42'),
(123, 'Elaine Cristina Barbosa', '2025-10-28 08:12:39', '2026-08-30 18:51:27'),

(124, 'Murilo Eduardo Lima', '2025-05-08 08:21:54', '2025-09-08 18:32:18'),
(124, 'Bianca Gabriela Souza', '2025-09-09 08:05:46', '2026-08-31 18:43:59'),

(125, 'Igor Henrique Nascimento', '2025-05-14 08:43:27', '2025-11-23 18:16:35'),
(125, 'Cintia Fernanda Ribeiro', '2025-11-24 08:10:18', '2026-08-29 18:55:04'),

(126, 'Joao Pedro Fernandes', '2025-05-20 08:16:39', '2025-10-13 18:28:47'),
(126, 'Tais Cristina Mendes', '2025-10-14 08:08:24', '2026-08-30 18:39:12'),

(127, 'Arthur Gabriel Costa', '2025-05-26 08:31:52', '2025-09-30 18:45:21'),
(127, 'Michelle Renata Alves', '2025-10-01 08:13:47', '2026-08-31 18:34:56'),

(128, 'Vinicius Eduardo Martins', '2025-06-01 08:24:15', '2025-11-11 18:23:39'),
(128, 'Raquel Beatriz Oliveira', '2025-11-12 08:06:51', '2026-08-28 18:47:18'),

(129, 'Cristian Felipe Souza', '2025-06-06 08:45:23', '2025-10-24 18:37:14'),
(129, 'Debora Caroline Lima', '2025-10-25 08:09:36', '2026-08-30 18:53:42'),

(130, 'Renan Augusto Carvalho', '2025-06-12 08:19:48', '2025-12-15 18:14:29'),
(130, 'Flavia Gabriela Santos', '2025-12-16 08:11:07', '2026-08-31 18:42:35'),

(131, 'Douglas Henrique Pereira', '2025-06-18 08:36:27', '2025-10-08 18:31:56'),
(131, 'Simone Cristina Rocha', '2025-10-09 08:04:32', '2026-08-29 18:49:13'),

(132, 'Bruno Rafael Mendes', '2025-06-24 08:28:41', '2025-11-29 18:26:47'),
(132, 'Luciana Beatriz Castro', '2025-11-30 08:07:18', '2026-08-30 18:38:25'),

(133, 'Fabio Alexandre Nunes', '2025-07-01 08:42:36', '2025-10-17 18:20:14'),
(133, 'Regina Helena Duarte', '2025-10-18 08:12:43', '2026-08-31 18:56:31'),

(134, 'Marcelo Vinicius Ramos', '2025-07-07 08:17:29', '2025-12-08 18:35:48'),
(134, 'Juliana Caroline Freitas', '2025-12-09 08:05:24', '2026-08-28 18:41:16'),

(135, 'Cesar Augusto Vieira', '2025-07-13 08:33:51', '2025-11-02 18:29:37'),
(135, 'Michele Fernanda Gomes', '2025-11-03 08:09:17', '2026-08-30 18:44:52'),

(136, 'Renato Eduardo Pinto', '2025-07-19 08:25:43', '2025-10-29 18:17:26'),
(136, 'Cristiane Beatriz Lopes', '2025-10-30 08:14:08', '2026-08-31 18:36:44'),

(137, 'Alan Gabriel Ferreira', '2025-07-25 08:47:19', '2025-12-20 18:24:51'),
(137, 'Kelly Cristina Martins', '2025-12-21 08:06:37', '2026-08-29 18:52:28'),

(138, 'Ramon Felipe Cardoso', '2025-08-01 08:18:34', '2025-11-18 18:39:16'),
(138, 'Viviane Caroline Souza', '2025-11-19 08:10:29', '2026-08-30 18:45:37'),

(139, 'Eder Henrique Barbosa', '2025-08-07 08:29:47', '2025-12-12 18:16:42'),
(139, 'Priscila Gabriela Nascimento', '2025-12-13 08:08:15', '2026-08-31 18:53:19'),

(140, 'Julio Cesar Almeida', '2025-08-13 08:41:26', '2025-11-25 18:33:08'),
(140, 'Marina Beatriz Ramos', '2025-11-26 08:11:43', '2026-08-28 18:48:36'),

(141, 'Guilherme Augusto Silva', '2025-08-19 08:23:58', '2025-12-28 18:21:45'),
(141, 'Daniela Cristina Costa', '2025-12-29 08:05:31', '2026-08-30 18:40:27'),

(142, 'Otavio Henrique Martins', '2025-08-25 08:37:14', '2025-12-05 18:27:53'),
(142, 'Lorena Gabriela Ferreira', '2025-12-06 08:09:26', '2026-08-31 18:55:18');

select * from origem; 
select * from registro_chamadas; 


-- ==========================
-- Etapa 02
-- ==========================

drop table avaliacao_ia
drop table avaliacao_criterio

ALTER TABLE registro_chamadas 
DROP COLUMN nota,
DROP COLUMN resumo;

CREATE TABLE avaliacao_ia (
	id_avaliacao INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
	registro_chamadas_log varchar(255) not null,
	nota_final VARCHAR(2) not null,
	feedback_geral TEXT not null,
	data_avaliacao date not null,
	modelo_ia varchar(50) not null,

	foreign key (registro_chamadas_log) references registro_chamadas(log)
);

CREATE TABLE avaliacao_criterio (
	id_av_por_criterio INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
	id_avaliacao INT not null,
	criterio VARCHAR(50) NOT NULL
        CHECK (criterio IN (
            'chamar pelo nome',
            'agir com empatia',
            'ouvir com atencao',
            'coordialidade na fala',
            'eficiencia operacional',
            'surpreender'
        )),
	nota_criterio VARCHAR(2) not null,
	justificativa_criterio TEXT,
	
	foreign key (id_avaliacao) references avaliacao_ia(id_avaliacao)
);

DELETE FROM registro_chamadas
WHERE id IN (1, 2);

SELECT *
FROM avaliacao_ia AS a
INNER JOIN avaliacao_criterio AS c
    ON a.id_avaliacao = c.id_avaliacao;