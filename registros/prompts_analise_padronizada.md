# 📋 Prompts Padronizados para Análise de Dados e Qualidade (SONAX)

Este documento contém 2 prompts prontos e padronizados para solicitar análises avançadas no banco de dados e transcrições do sistema **SONAX**. 

Cada prompt foi arquitetado para guiar o agente/modelo a inspecionar as tabelas do PostgreSQL (`chamadas`, `registro_chamadas`, `avaliacao_ia`, `avaliacao_sdr`, `avaliacao_criterio`, `analise_spin`, `analise_bant`, `crm`), cruzar dados quantitativos com evidências qualitativas e devolver relatórios executivos prontos para tomada de decisão.

---

## 📑 Índice
1. [Prompt 1: Diagnóstico de Desempenho e Causa-Raiz de SDR (Notas e Critérios)](#prompt-1-diagnóstico-de-desempenho-e-causa-raiz-de-sdr)
2. [Prompt 2: Auditoria e Validação de Reuniões Agendadas (Transcrições vs. Flag 's')](#prompt-2-auditoria-e-validação-de-reuniões-agendadas)

---

<a name="prompt-1-diagnóstico-de-desempenho-e-causa-raiz-de-sdr"></a>
## 🎯 Prompt 1: Diagnóstico de Desempenho e Causa-Raiz de SDR

> **Quando usar:** Quando um SDR estiver com média baixa, quando você quiser entender por que um atendente específico está tirando notas ruins, ou para preparar um feedback/1:1 com evidências concretas extraídas do banco.

### 📝 Texto do Prompt para Copiar e Colar:

```markdown
Atue como um Especialista em Inteligência de Vendas B2B e Auditor de Qualidade do sistema SONAX.

Preciso de um diagnóstico aprofundado e padronizado do desempenho do SDR [NOME DO SDR] no banco de dados [OPCIONAL: no período de DD/MM/AAAA a DD/MM/AAAA].

Execute as consultas necessárias no banco PostgreSQL (`chamadas`, `registro_chamadas`, `avaliacao_sdr`, `avaliacao_criterio`, `avaliacao_ia`, `dim_oportunidade_treinamento`, `analise_spin`, `analise_bant`) e devolva um relatório estruturado no seguinte padrão:

### 1. Panorama Geral do SDR
- Total de chamadas discadas e registradas.
- Chamadas não avaliáveis (URA, secretária, queda ou sem diálogo comercial — `ligacao_relevante: 'n'` e `nota_final: NULL`).
- Chamadas avaliadas tecnicamente (`avaliacao_sdr`).
- Média geral de pontuação (0 a 100) e distribuição das notas:
  * Notas críticas/baixas (<= 45)
  * Notas medianas (46 a 69)
  * Notas altas (>= 70)

### 2. Tabela de Desempenho por Dimensão Oficial
Apresente uma tabela comparando os 6 critérios oficiais do SONAX:
| Critério | Código | Peso Máx. | Média Obtida | % Aproveitamento | Qtd. Notas Zero |
Inclua: CRIT_ABERTURA (10), CRIT_SPIN (30), CRIT_PERFIL (25), CRIT_BANT (15), CRIT_ESCUTA (10) e CRIT_PROX_PASSO (10).

### 3. Diagnóstico de Causa-Raiz das Notas Baixas
Explique objetivamente por que as notas baixas aconteceram, detalhando:
- **Critério de Perfil (Lucro Real e Faturamento):** Houve questionamento ativo desses requisitos eliminatórios?
- **Critério SPIN (Investigação Consultiva vs. Pitch):** O SDR aplicou perguntas de Situação, Problema, Implicação e Necessidade ou focou apenas em despejar teses tributárias e debater objeções?
- **Critério BANT (Qualificação de Oportunidade):** Onde ocorreram as maiores lacunas (Budget, Authority, Need, Timeline)?
- **Oportunidades de Treinamento Mais Frequentes:** Liste os códigos e descrições do catálogo `dim_oportunidade_treinamento` mais atribuídos ao SDR com contagem e percentual.

### 4. Análise de Contraste (Pontos Fortes x Ligações Críticas)
- Por que em algumas ligações o SDR consegue notas altas (ex.: 80 a 100) enquanto em outras a nota despenca (ex.: 18 a 40)?
- Explique se as notas altas decorrem de redistribuição proporcional em follow-ups/retenção na recepção versus prospecção com decisor.
- Liste os principais pontos fortes comportamentais observados (postura, educação, tom de voz, etc.).

### 5. Plano de Ação e Recomendações
- 3 ações corretivas prioritárias e práticas para o SDR aplicar nas próximas ligações para elevar sua média.
```

---

<a name="prompt-2-auditoria-e-validação-de-reuniões-agendadas"></a>
## 🎯 Prompt 2: Auditoria e Validação de Reuniões Agendadas

> **Quando usar:** No fechamento de metas semanais ou mensais, para conferir se o número de reuniões computadas pelo sistema bate com o que realmente foi falado nas ligações, e auditar se a IA cometeu falsos positivos ou falsos negativos.

### 📝 Texto do Prompt para Copiar e Colar:

```markdown
Atue como um Auditor de Métricas Comerciais e Analista de Dados do sistema SONAX.

Preciso de uma auditoria rigorosa das reuniões agendadas pelo SDR [NOME DO SDR] [OPCIONAL: no mês de [MÊS/ANO] ou no período de DD/MM/AAAA a DD/MM/AAAA].

Verifique no banco de dados as tabelas `chamadas`, `registro_chamadas`, `avaliacao_ia` (campo `reuniao_confirmada`), `crm` e analise as transcrições/revisões textuais para validar se o número de reuniões computadas condiz com a realidade.

Devolva o relatório estruturado no seguinte padrão:

### 1. Resumo Quantitativo do Período
- Total de chamadas discadas pelo SDR no período.
- Total de chamadas transcritas e avaliadas pela IA.
- Total de chamadas marcadas com reunião confirmada no banco (`reuniao_confirmada = 's'`).

### 2. Auditoria Individual das Reuniões Confirmadas (`reuniao_confirmada = 's'`)
Para cada uma das reuniões marcadas com 's' no banco, apresente:
- **Número do Protocolo e Data/Hora da Ligação**
- **Empresa Contatada e Nome/Cargo do Interlocutor**
- **Data e Horário Acordados da Reunião**
- **Canal/Meio (Online / Presencial / Link)** e dados de contato coletados (E-mail / WhatsApp)
- **Tipo de Compromisso:** Reunião Nova com Decisor / Reagendamento / Reunião agendada via Secretária/Intermediário
- **Trecho da Transcrição/Revisão:** Citar o diálogo final que comprova o aceite e o acordo mútuo da data/hora
- **Veredito do Caso:** Válida ou Falso Positivo (com justificativa técnica).

### 3. Varredura Exaustiva de Falsos Negativos (Reuniões Omitidas)
Varra as transcrições e resumos de CRM das demais ligações do período que NÃO estão marcadas com 's' buscando termos de compromisso (*"reunião"*, *"agendamento"*, *"horário"*, *"quarta às"*, etc.):
- Houve alguma reunião de fato agendada com data e horário que a IA deixou de marcar como 's'?
- Detalhe eventuais casos limítrofes encontrados (ex.: cobrança de no-show, reagendamento frustrado por ausência/doença, envio de material/apresentação com promessa de retorno).

### 4. Veredito Final de Consistência e Qualidade
- **Conclusão:** O número de reuniões reportado pelo banco de dados bate com as transcrições reais?
- **Índice de Acurácia da IA:** Foram identificados falsos positivos ou falsos negativos?
- **Alertas Operacionais:** Reagendamentos que inflacionam a métrica ou reuniões marcadas sem qualificação prévia de perfil (Lucro Real/Faturamento).
```

---

## 🛠️ Consultas SQL de Referência Rápida (PostgreSQL)

Caso deseje extrair previamente os dados no banco para alimentar os prompts ou validar os relatórios:

### Consulta para o Prompt 1 (Notas e Critérios do SDR):
```sql
SELECT 
    c.protocolo,
    c.agente_nome,
    c.dt_inicio,
    c.duracao_segundos,
    rc.log,
    ai.resultado,
    ai.ligacao_relevante,
    sdr.nota_final,
    sdr.feedback_geral,
    ot.codigo_oportunidade,
    dot.descricao AS op_descricao
FROM chamadas c
JOIN registro_chamadas rc ON c.protocolo = rc.protocolo
LEFT JOIN avaliacao_ia ai ON rc.log = ai.log
LEFT JOIN avaliacao_sdr sdr ON rc.log = sdr.log
LEFT JOIN avaliacao_oportunidade_treinamento ot ON rc.log = ot.log
LEFT JOIN dim_oportunidade_treinamento dot ON ot.codigo_oportunidade = dot.codigo
WHERE c.agente_nome ILIKE '%NOME_DO_SDR%'
ORDER BY c.dt_inicio DESC;
```

### Consulta para o Prompt 2 (Reuniões Confirmadas):
```sql
SELECT 
    c.protocolo,
    c.dt_inicio,
    c.duracao_segundos,
    e.nome AS empresa_nome,
    rc.log,
    ai.reuniao_confirmada,
    ai.data_confirmada,
    crm.acao,
    crm.resumo,
    rc.revisao
FROM chamadas c
JOIN registro_chamadas rc ON c.protocolo = rc.protocolo
JOIN avaliacao_ia ai ON rc.log = ai.log
LEFT JOIN crm ON rc.log = crm.log
LEFT JOIN empresa e ON rc.id_empresa = e.id_empresa
WHERE c.agente_nome ILIKE '%NOME_DO_SDR%'
  AND ai.reuniao_confirmada = 's'
ORDER BY c.dt_inicio ASC;
```

