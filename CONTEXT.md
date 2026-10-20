# CONTEXT.md — Domínio SONAX

Documento vivo de contexto de domínio e decisões arquiteturais do projeto **SONAX**.

---

## 1. Visão Geral do Sistema

O **SONAX** é uma plataforma desktop de ingestão, transcrição, enriquecimento e análise de qualidade de atendimento para chamadas comerciais B2B de pré-vendas (SDRs) da **Falavinha Next**.

O pipeline processa arquivos de áudio `.wav` (diretamente ou extraídos de arquivos `.zip`/`.rar`), transcreve o conteúdo, consulta informações externas da empresa contatada via robô RPA, realiza diarização e revisão textual com IA e avalia a qualidade comercial do contato segundo metodologias de mercado (SPIN Selling e BANT), persistindo os dados em banco relacional PostgreSQL para consumo no Power BI.

---

## 2. Glossário de Domínio

- **SDR (Sales Development Representative)**: Pré-vendedor responsável pela prospecção ativa via telefone, qualificação preliminar da empresa e agendamento de reuniões técnicas.
- **Chamada / Áudio**: Gravação telefônica em formato WAV. Identificada internamente pelo `call_id` (protocolo) e `ramal`.
- **Origem / Chamadas**: Tabela no banco de dados com metadados brutos das ligações geradas pela central (protocolo, ramal, atendente, número discado, DDD, duração, data/hora).
- **Robô Google (RPA)**: Serviço de automação (`app/services/rpa_google.py`) que abre o navegador padrão / Google Chrome local, pesquisa o telefone formatado no Google, copia os dados da entidade comercial (Google My Business / cartões locais) e fecha a aba sem custos de API externa.
- **Triangulação de Dados**: Comparação contextual no prompt de IA entre os dados coletados pelo robô Google e a transcrição da chamada para identificar a entidade comercial correta.
- **Fonte de Dados da Empresa (`fonte_dados`)**: Campo cadastral em `empresa` que identifica as fontes humanas na ligação que forneceram as informações (`Interlocutor`, `Agente` ou `Interlocutor / Agente`), garantindo rastreabilidade fidedigna sem persistir texto web raspado no banco.
- **Resolução de Entidades por Telefone**: Ancoragem primária do cadastro da `empresa` no número de telefone para evitar duplicatas geradas por variações de grafia ou nomes fantasia informados na fala.
- **Revisão e Diarização Textual**: Etapa conduzida por LLM (`deepseek/deepseek-v4-flash-0731`) que segmenta os locutores (URA, Agente e Cliente), normaliza a pontuação fonética do ASR e extrai o nome da empresa.
- **Análise Comercial (SPIN / BANT / SDR)**: Avaliação conduzida por LLM (`deepseek/deepseek-v4-flash-0731`) com saída estruturada tipada (Pydantic / Structured Output) distribuída em 7 tabelas normalizadas.
- **Critérios Oficiais (`dim_criterio_avaliacao`)**: Seis dimensões com pontuação máxima total de 100 pontos:
  - `CRIT_ABERTURA` (10 pts)
  - `CRIT_SPIN` (30 pts)
  - `CRIT_PERFIL` (25 pts)
  - `CRIT_BANT` (15 pts)
  - `CRIT_ESCUTA` (10 pts)
  - `CRIT_PROX_PASSO` (10 pts)
- **Oportunidade de Treinamento (`dim_oportunidade_treinamento`)**: Catálogo pré-definido de 27 códigos (`OP_ABERT_*`, `OP_SPIN_*`, `OP_PERF_*`, `OP_BANT_*`, `OP_ESC_*`, `OP_PROX_*`, `OP_DIR_*`), onde cada chamada avaliável recebe **exatamente 1 código prioritário**.
- **Chamada Relevante (`ligacao_relevante: 's'`)**: Chamada com diálogo comercial efetivo com decisor/área de interesse OU retenção na recepção com próximo passo comercial concreto (retorno agendado, envio de material, reunião proposta/confirmada). Toda ligação relevante gera obrigatoriamente a avaliação completa do SDR (`avaliacao_sdr`, critérios pontuados proporcionalmente, oportunidade de melhoria e feedback sem prefixo 'Não avaliável').
- **Chamada Não Avaliável / Não Relevante (`ligacao_relevante: 'n'`)**: Chamadas sem contato útil (URA, queda imediata, número errado, secretária eletrônica ou retenção na recepção sem próximo passo / `crm.acao == "Não se aplica"`). Recebem nota final, notas de critério e código de oportunidade como **NULL** no banco para não distorcer médias ou quebrar tipos inteiros (`Int64`) no Power BI.
- **Hierarquia e Expiração Temporal de Status Comercial (`data_status_comercial`)**: O status comercial da empresa (`status_comercial`) segue regras anti-regressão de pesos para proteger empresas qualificadas contra rebaixamento por chamadas fracas posteriores. Possui janela de validade de 1 mês (30 dias) ancorada na data de compromisso agendada (`crm.prazo_data`) ou, subsidiariamente, na data da ligação (`chamadas.dt_inicio`). Se recontatada após essa janela (> 30 dias), o status anterior expira e a nova ligação pode redefinir o status vigente da empresa.

---

## 3. Arquitetura do Pipeline

```
Arquivos WAV / ZIP / RAR
          │
          ▼
1. Varredura & Inspeção Acústica (AudioInspector)
          │ (> 1 min, SNR / CQT / ZCR)
          ▼
2. Cópia Segura para Pasta Temporária de Trabalho
          │
          ▼
3. Transcrição ASR (Faster-Whisper local com fallback OpenRouter)
          │ Persistência em `registro_chamadas`
          ▼
4. Coleta RPA Google (Triangulação de Dados)
          │ Pywinauto + Navegador local + Cache por telefone
          ▼
5. Revisão & Diarização com IA (DeepSeek V4 Flash)
          │ Identificação de empresa -> Tabela `empresa`
          │ Gravação de texto revisado -> `registro_chamadas.revisao`
          ▼
6. Análise de Qualidade Comercial (DeepSeek V4 Flash)
          │ Persistência atômica nas 7 tabelas normalizadas:
          │   - avaliacao_ia
          │   - avaliacao_sdr
          │   - avaliacao_criterio (6 linhas)
          │   - analise_spin
          │   - analise_bant
          │   - interlocutor
          │   - crm
          ▼
7. Limpeza Segura de Diretórios Temporários
```

---

## 4. Sistema de Logs e Visualização

A aplicação implementa um padrão desacoplado de logging gerenciado por `app/logs.py`, `app/engine/log_session.py` e `app/engine/stream.py`:

- **Log User**: Visível por padrão na janela principal (`CustomTkinter`), contendo mensagens limpas, orientadas ao usuário final, anonimizadas por rótulos amigáveis (`Audio 01`, `Audio 02`), notas resumidas e status das etapas.
- **Log Dev**: Ativado pelo botão de alternância no rodapé da aplicação. Exibe:
  - Nomes reais dos arquivos no disco;
  - Tracebacks completos de erros tratados;
  - Saídas com prefixo `[DEV]` emitidas por `log_dev(...)`;
  - Prévia dos textos capturados pelo Robô Google;
  - Triangulação de dados e fontes da empresa;
  - Detalhamento dos critérios SPIN, BANT e resumo executivo CRM.
