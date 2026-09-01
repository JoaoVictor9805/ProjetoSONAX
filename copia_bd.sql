CREATE TABLE origem (
	ramal INT PRIMARY key not null,
	nome_atendente varchar(100) not null
);

CREATE TABLE registro_chamadas (
	id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
	ramal INT not null,
	nome_atendente varchar(100) not null,
	data_ligacao date not null,
	log varchar(255),
	transcricao TEXT,
	
	foreign key (ramal) references origem(ramal)
);


TRUNCATE TABLE origem CASCADE;

INSERT INTO origem (ramal, nome_atendente) VALUES
(100, 'Roberto Almeida'),
(101, 'Ana Clara Silva'),
(102, 'Carlos Eduardo Santos'),
(103, 'Mariana Costa'),
(104, 'Camila Santos'),
(105, 'João Paulo Alves'),
(106, 'Fernanda Oliveira'),
(107, 'Ricardo Gomes'),
(108, 'Juliana Mendes'),
(109, 'Marcos Costa'),
(110, 'Lucas Ferreira'),
(111, 'Beatriz Souza'),
(112, 'Thiago Ribeiro'),
(113, 'Aline Martins'),
(114, 'Gabriel Pereira'),
(115, 'Juliana Silva'),
(116, 'Pedro Henrique'),
(117, 'Larissa Rocha'),
(118, 'Diego Fernandes'),
(119, 'Renata Castro'),
(120, 'Gustavo Barbosa'),
(121, 'Vanessa Dias'),
(122, 'Felipe Oliveira'),
(123, 'Tatiana Melo'),
(124, 'Alexandre Correia'),
(125, 'Bruna Carvalho'),
(126, 'Rodrigo Monteiro'),
(127, 'Carolina Nunes'),
(128, 'Letícia Ferreira'),
(129, 'Matheus Cardoso'),
(130, 'Natália Pires'),
(131, 'Daniel Cavalcanti'),
(132, 'Paula Farias'),
(133, 'Leonardo Moura'),
(134, 'Rafael Souza'),
(135, 'Bianca Teixeira'),
(136, 'Eduardo Campos'),
(137, 'Sabrina Vieira'),
(138, 'Victor Nogueira'),
(139, 'Flávia Batista'),
(140, 'Marcelo Moraes'),
(141, 'Amanda Lima'),
(142, 'Leandro Pinto'),
(143, 'Cíntia Mendes'),
(144, 'André Reis'),
(145, 'Priscila Freitas'),
(146, 'Fernando Borges'),
(147, 'Bruno Pereira'),
(148, 'Isabela Machado'),
(149, 'Guilherme Peixoto'),
(150, 'Carla Mendes');


select * from registro_chamadas; 