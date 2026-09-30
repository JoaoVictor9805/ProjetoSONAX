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
- **Triangulação de Dados**: Consolidação entre o texto coletado pelo robô Google (`[GOOGLE]`) e os nomes citados na chamada (`[DIARIZAÇÃO]`) para identificar a entidade comercial.
- **Resolução de Entidades por Telefone**: Ancoragem primária do cadastro da `empresa` no número de telefone para evitar duplicatas geradas por variações de grafia ou nomes fantasia informados na fala.
- **Revisão e Diarização Textual**: Etapa conduzida por LLM (`qwen/qwen3-30b-a3b-instruct-2507`) que segmenta os locutores (URA, Agente e Cliente), normaliza a pontuação fonética do ASR e extrai o nome da empresa.
- **Análise Comercial (SPIN / BANT / SDR)**: Avaliação conduzida por LLM (`openai/gpt-4o-mini`) com saída estruturada tipada (Pydantic / Structured Output) distribuída em 7 tabelas normalizadas.
- **Critérios Oficiais (`dim_criterio_avaliacao`)**: Seis dimensões com pontuação máxima total de 100 pontos:
  - `CRIT_ABERTURA` (10 pts)
  - `CRIT_SPIN` (30 pts)
  - `CRIT_PERFIL` (25 pts)
  - `CRIT_BANT` (15 pts)
  - `CRIT_ESCUTA` (10 pts)
  - `CRIT_PROX_PASSO` (10 pts)
- **Oportunidade de Treinamento (`dim_oportunidade_treinamento`)**: Catálogo pré-definido de 27 códigos (`OP_ABERT_*`, `OP_SPIN_*`, `OP_PERF_*`, `OP_BANT_*`, `OP_ESC_*`, `OP_PROX_*`, `OP_DIR_*`), onde cada chamada avaliável recebe **exatamente 1 código prioritário**.
- **Chamada Não Avaliável**: Chamadas sem conversa substantiva (URA, queda imediata, secretária eletrônica ou recusa nos primeiros segundos). Recebem nota final e critérios como **NULL** no banco para não distorcer médias ou quebrar tipos inteiros (`Int64`) no Power BI.

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
3. Transcrição ASR (NVIDIA Nemotron via OpenRouter / AssemblyAI)
          │ Persistência em `registro_chamadas`
          ▼
4. Coleta RPA Google (Triangulação de Dados)
          │ Pywinauto + Navegador local + Cache por telefone
          ▼
5. Revisão & Diarização com IA (Qwen 30B Instruct)
          │ Identificação de empresa -> Tabela `empresa`
          │ Gravação de texto revisado -> `registro_chamadas.revisao`
          ▼
6. Análise de Qualidade Comercial (GPT-4o-mini)
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
