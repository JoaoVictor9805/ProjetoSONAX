# README — Atualizações e Correções do Pipeline de Análise (SONAX)

Este documento registra todas as alterações e correções estruturais, determinísticas e de prompt implementadas no pipeline de ingestão, sanitização e persistência de chamadas comerciais da plataforma **SONAX**.

---

## 1. Proteção da Média no Power BI (`AVERAGE` x Nulos)

* **Problema Original:** Chamadas não avaliáveis (ex.: URA eletrônica, queda de ligação, secretária) recebiam nota final `0`. No Power BI, a função `AVERAGE(nota_final)` ignora valores nulos (`NULL`), mas inclui o `0` na divisão, derrubando e distorcendo artificialmente a média de qualidade dos SDRs.
* **Implementação Concreta:**
  * O sanitizador determinístico em `app/services/analise_final_AI.py` força incondicionalmente `av_sdr["nota_final"] = None` e `crit["nota_criterio"] = None` em todas as ligações identificadas como não avaliáveis.
  * O prompt oficial em `app/config/prompts.py` (Regra 8) foi atualizado com instrução categórica para retornar `null` em vez de zero.

---

## 2. Sobreposição Autoritativa de Metadados do Sistema

* **Problema Original:** O sanitizador utilizava verificações do tipo `if not av_ia.get("campo")`, confiando na resposta do LLM. Como o prompt trazia `"empresa_contatada": 1054` no exemplo, o modelo frequentemente copiava esse ID, associando a ligação à empresa errada. Além disso, `data_avaliacao` e `modelo_ia` eram inventados pelo LLM.
* **Implementação Concreta:**
  * Em `app/services/analise_final_AI.py`:
    * `protocolo`: recebe obrigatoriamente o protocolo real da chamada fornecido pelo sistema.
    * `empresa_contatada`: recebe o ID real resolvido pelo sistema. Se o sistema passar `None`, o sanitizador força `None` no registro, eliminando qualquer alucinação.
    * `data_avaliacao`: preenchido deterministicamente com a data da execução (`date.today()`).
    * `modelo_ia`: preenchido deterministicamente com o identificador configurado no ambiente (`MODELO_ANALISE`).
  * Em `app/config/prompts.py`: o exemplo JSON foi corrigido para `"empresa_contatada": null`.

---

## 3. Correção de Boundary na Detecção de URA (Falsos Positivos)

* **Problema Original:** A verificação `or "ura" in feedback.lower()` fazia busca por substring simples, disparando falso positivo de chamada não avaliável quando o feedback continha palavras comuns como `"abertura"` ou `"postura"`.
* **Implementação Concreta:**
  * Substituído por verificação com limite de palavra exato via regex: `bool(re.search(r"\bura\b", feedback.lower()))`.
  * Mantida a sensibilidade para capturar URA real isolada sem penalizar elogios de postura ou comentários de abertura.

---

## 4. Hierarquia de Status Comercial da Empresa (Anti-Regressão)

* **Problema Original:** Ao processar uma nova chamada fraca ou não avaliável para uma empresa que já estava qualificada, o pipeline sobrescrevia o campo `empresa.status_comercial`, regredindo empresas qualificadas para `"Dados insuficientes"`.
* **Implementação Concreta:**
  * Em `app/database/chamadas_dao.py`, a query de consulta da empresa agora recupera o `status_comercial` atual.
  * Implementada hierarquia de pesos:
    * `"Perfil confirmado"` (peso 3)
    * `"Fora do perfil desta campanha"` (peso 3)
    * `"Perfil pendente"` (peso 2)
    * `"Dados insuficientes"` (peso 1)
  * Uma chamada com peso inferior nunca rebaixa o status comercial já conquistado pela empresa no banco de dados.

---

## 5. Regra de Recepção / Transferência e Próximo Passo no CRM

* **Problema Original:** Toda chamada sem diálogo com decisor era forçada para `resultado: "Dados insuficientes"` e `crm.acao: "Não se aplica"`, descartando avanços comerciais obtidos na recepção (agendamento de retorno com secretária ou solicitação de material).
* **Implementação Concreta:**
  * **Ligações Transferidas:** Chamadas iniciadas na recepção e transferidas com sucesso para o setor correto (Financeiro, Fiscal, Contas a Pagar, Diretoria) são classificadas como `ligacao_relevante: "s"` e avaliadas tecnicamente com notas (0–100), SPIN e BANT.
  * **Chamadas Retidas na Recepção com Próximo Passo:**
    * Classificadas como `ligacao_relevante: "s"` (contato útil para a prospecção).
    * `resultado: "Perfil pendente"`.
    * Preservam o avanço no CRM: `crm.acao` (`"retorno com data combinado"` com `prazo`, ou `"envio de material solicitado"`).
    * **Notas do SDR estritamente `NULL`** para proteger a média de notas no Power BI.
  * **Chamadas Infrutíferas:** Queda, URA pura, engano ou recusa imediata na recepção sem margem de retorno continuam como `ligacao_relevante: "n"`, `crm.acao: "Não se aplica"` e `resultado: "Dados insuficientes"`.

---

## 6. Aplicação Estrita do Teto por Critério (`max_pontos`) e Soma Determinística

* **Problema Original:** O catálogo `CRITERIOS_OFICIAIS` definia a pontuação máxima de cada critério, mas o código não validava os valores individuais. A IA podia atribuir notas infladas (ex.: 20 ou 30 em Abertura, cujo teto é 10), gerando notas distorcidas e somas acima de 100.
* **Implementação Concreta:**
  * Em `app/services/analise_final_AI.py`, cada nota de critério é limitada deterministicamente ao seu teto oficial:
    * `CRIT_ABERTURA`: máx **10** (ex.: nota 20 vira 10)
    * `CRIT_SPIN`: máx **30**
    * `CRIT_PERFIL`: máx **25**
    * `CRIT_BANT`: máx **15**
    * `CRIT_ESCUTA`: máx **10**
    * `CRIT_PROX_PASSO`: máx **10**
  * A `nota_final` é recalculada como a soma estrita dessas notas limitadas, garantindo intervalo de 0 a 100.
  * Tipagem estrita de `codigo_criterio` no Pydantic via `Literal` dos 6 códigos oficiais.

---

## 7. Deduplicação e Ordem Canônica dos Critérios Oficiais

* **Problema Original:** Caso o LLM repetisse um critério na resposta JSON ou omitisse algum dos 6, o banco recebia linhas duplicadas ou faltantes na tabela `avaliacao_criterio`.
* **Implementação Concreta:**
  * O sanitizador indexa os critérios recebidos pelo código oficial, descartando duplicatas (mantendo a primeira ocorrência).
  * A lista de critérios é sempre reconstituída com exatamente os 6 critérios oficiais na ordem canônica, inserindo `nota_criterio: None` e justificativa padrão para qualquer dimensão omitida.

---

## 8. Normalização e Tipagem Estrita das Dimensões BANT

* **Problema Original:** As classificações de BANT (`budget_classificacao`, `authority_classificacao`, `need_classificacao`, `timeline_classificacao`) eram aceitas como strings livres, gerando inconsistências no banco (`"Confirmado"`, `"indicio"`, `"Sim"`).
* **Implementação Concreta:**
  * Tipagem Pydantic em `AnaliseBantModel` com `Literal["confirmado", "indício", "não informado", "negado"]`.
  * Criação da função determinística `normalizar_classificacao_bant()` em `app/services/analise_final_AI.py`, mapeando maiúsculas, sinônimos e ausência de acentos para as 4 categorias oficiais.
  * Evidências de texto vazias ou informais normalizadas para `"Não se aplica"`.

---

## 9. Eliminação de Instruções DDL em Tempo de Execução (`garantir_schema_avaliacao`)

* **Problema Original:** A cada chamada inserida, a função `garantir_schema_avaliacao` executava comandos `ALTER TABLE` e `INSERT` em tabelas de dimensão. Isso causava bloqueios exclusivos de tabela (`ACCESS EXCLUSIVE LOCK`), falhas de concorrência com o Power BI e abortava transações ativas do PostgreSQL sob concorrência.
* **Implementação Concreta:**
  * Em `app/database/chamadas_dao.py`, a chamada a `garantir_schema_avaliacao(cur)` foi removida de `inserir_analise()`.
  * A função foi tornada um no-op depreciado. Alterações estruturais e dados iniciais pertencem exclusivamente aos scripts SQL de migração (`migrations/` e `copia_bd_final.sql`).

---

## 10. Harmonização do Prompt Oficial de Análise

* **Arquivo:** `app/config/prompts.py`
* **Implementação Concreta:**
  * Harmonização da **Regra 6**: instruções claras sobre chamadas transferidas vs. chamadas retidas na recepção com agendamento de retorno.
  * Inclusão da **Regra 8**: proibição estrita de notas zero para chamadas não avaliáveis (exigência de `null`).
  * Inclusão dos **tetos numéricos por critério** diretamente na tabela de instruções do prompt.
  * Padronização das **7 ações oficiais de CRM**: `"reunião confirmada"`, `"reunião proposta sem aceite"`, `"retorno com data combinado"`, `"envio de material solicitado"`, `"sem próximo passo definido"`, `"sem interesse explícito"`, `"Não se aplica"`.
  * Correção da numeração sequencial das seções (seções 1 a 10).

---

## 11. Suíte de Testes Automatizados e Validação Cruzada (Fase 1)

* **Testes Dedicados Implementados:**
  * `test_sobrescrita_incondicional_metadados_sistema`: injeção forçada de protocolo, data, modelo e substituição/limpeza de ID de empresa alucinado (1054).
  * `test_teto_por_criterio_respeita_max_pontos`: teto individual de cada critério (ex.: nota 20 em abertura vira 10) e soma máxima 100.
  * `test_deduplicacao_de_criterios_duplicados`: remoção de repetições e garantia dos 6 critérios canônicos.
  * `test_recepcao_nao_avaliavel_com_retorno_preserva_crm_e_perfil_pendente`: recepção com retorno mantém CRM, status `Perfil pendente`, `ligacao_relevante: 's'` e notas `NULL`.
  * `test_recepcao_sem_proximo_passo_marca_nao_relevante`: recepção sem retorno resulta em `ligacao_relevante: 'n'` e `Dados insuficientes`.
  * `test_feedback_com_palavras_contendo_ura_nao_dispara_falso_positivo`: boundary de URA vs. "postura"/"abertura", testando falso positivo e detecção real de URA.
  * `test_hierarquia_status_comercial_impede_regressao_perfil_confirmado_para_dados_insuficientes`: proteção contra regressão de status forte da empresa.
  * `test_inserir_analise_nao_executa_ddl_runtime`: verificação de ausência de comandos `ALTER TABLE` / `CREATE TABLE` em runtime.
  * `test_bant_normalizado`: normalização das 4 classificações BANT e suas evidências.

---

## 12. Validação Estrita de Faturamento e Qualificação de Perfil (Ponto 1.1)

* **Problema Original:** Quando o SDR afirmava o faturamento da empresa ("Vocês faturam 500 mil, né?") e o cliente apenas concordava monossilabicamente ou desconversava, o LLM classificava a origem como `"calculado"` ou `"afirmado pelo SDR"`. Mesmo assim, o sistema promovia a chamada para `"Perfil confirmado"`. Além disso, a opção `"calculado"` existia no `CHECK` constraint do banco e no schema Pydantic, permitindo inferências não auditadas.
* **Implementação Concreta:**
  * **Remoção de `"calculado"`:** Eliminado de `ORIGENS_FATURAMENTO_VALIDAS`, do enum Pydantic `AnalisePerfilModel`, do prompt oficial e do `CHECK` constraint em `copia_bd_final.sql`. Caso o LLM gere `"calculado"`, a função determinística `normalizar_origem_faturamento()` converte automaticamente para `"não informado"`.
  * **Coerção Rigorosa de Status da Chamada:** Para que uma chamada receba `resultado: "Perfil confirmado"`, é mandatório que `faturamento_origem == "confirmado pelo interlocutor"`. Se a origem for `"afirmado pelo SDR"` ou `"não informado"`, o status da chamada é coagido deterministicamente para `"Perfil pendente"`, impedindo que presunções do vendedor distorçam as métricas do BI.

---

## 13. Consolidação Multi-Chamada do Perfil da Empresa no DAO (Ponto 1.2)

* **Problema Original:** O status comercial da empresa (`empresa.status_comercial`) era atualizado com base apenas no resultado isolado da última chamada. Se a Chamada 1 confirmava o regime tributário (ex.: Lucro Real) e a Chamada 2 confirmava o faturamento (ex.: R$ 200k), a Chamada 2 isoladamente era classificada como `"Perfil pendente"` e o status da empresa permanecia `"Perfil pendente"`, ignorando os dados já acumulados no cadastro da empresa.
* **Implementação Concreta:**
  * Implementada a função `derivar_status_consolidado_empresa(cur, empresa_id)` em `app/database/chamadas_dao.py`.
  * Na persistência da análise (`inserir_analise`), o sistema consolida as informações acumuladas na tabela `empresa` (regime tributário e faturamento mensal histórico + dados da chamada atual).
  * Se a união dos dados acumulados atender aos critérios de qualificação (regime tributário conhecido e elegível + faturamento dentro da faixa de interesse com origem confirmada), o status acumulado da empresa é promovido para `"Perfil confirmado"`. A hierarquia anti-regressão impede que contatos subsequentes fracos rebaixem esse status consolidado.

---

## 14. Aumento do Limite de Saída do LLM (`max_tokens = 4096`) (Ponto 1.3)

* **Problema Original:** O parâmetro `max_tokens` da chamada ao modelo de análise final estava configurado em `2500`. Em conversas longas ou com justificativas detalhadas em todos os 6 critérios, o JSON de resposta estourava o teto e era truncado, causando erro de parsing de JSON.
* **Implementação Concreta:**
  * O limite `max_tokens` foi elevado para `4096` em `app/services/analise_final_AI.py` (e no cliente LLM correspondente), acomodando com folga o payload estruturado completo (SPIN, BANT, Perfil, 6 Critérios, CRM e Oportunidades).

---

## 15. Idempotência das Cargas Iniciais DDL (`ON CONFLICT DO NOTHING`) (Ponto 1.4)

* **Problema Original:** Os comandos de carga inicial nas tabelas `dim_criterio_avaliacao` e `dim_oportunidade_treinamento` no script `copia_bd_final.sql` eram `INSERT INTO ...` diretos. Se o script fosse executado mais de uma vez para atualização do banco, gerava violação de chave primária duplicada (`unique_violation`).
* **Implementação Concreta:**
  * Adicionada a cláusula `ON CONFLICT (codigo) DO NOTHING;` aos blocos de inserção de dimensões em `copia_bd_final.sql`, tornando o script SQL seguro e 100% idempotente para reexecução contínua.

---

## 16. Oportunidades de Treinamento e Confirmação de Reunião (Ponto 1.5)

* **Problema Original:**
  1. O código de oportunidade `OP_ESC_04` ("Interrupção ou sobreposição excessiva de fala") gerava frequentes falsos positivos porque os áudios gravados são mono sem diarização acústica por locutor, impossibilitando mensuração fidedigna de interrupções reais.
  2. Caso o LLM sugerisse um código inexistente, a restrição de FK no banco falhava.
  3. Quando uma reunião era agendada com data definida (`crm.prazo`), o campo booleano `data_confirmada` não era automaticamente preenchido.
* **Implementação Concreta:**
  * **Remoção de `OP_ESC_04`:** O código foi retirado do prompt oficial (`app/config/prompts.py`) e da tabela `dim_oportunidade_treinamento`.
  * **Fallback Seguro de Oportunidades:** Se o modelo retornar um código desconhecido ou o legado `OP_ESC_04`, o sanitizador converte graciosamente para `None`, sem quebrar a ingestão.
  * **Derivação de `data_confirmada`:** Quando `crm.prazo` contiver uma data/horário válido de agendamento e a ação indicar reunião marcada, o sanitizador preenche deterministicamente `data_confirmada = 's'`, garantindo consistência com o visual de reuniões no Power BI.

---

## 17. Normalização Proporcional de Notas com Cláusula de Barreira (Ponto 1.6)

* **Problema Original:** Em chamadas enxutas ou objetivas onde o interlocutor aceitou a proposta rapidamente ou não permitiu aprofundar todos os blocos (ex.: sem necessidade de BANT completo na ligação), zerar critérios não abordados penalizaria injustamente a nota do SDR. Por outro lado, avaliar apenas 1 critério isolado (ex.: Abertura, 10/10) e extrapolar para 100 criaria notas máximas ilusórias em ligações de 30 segundos.
* **Implementação Concreta:**
  * **Normalização Proporcional (Regra dos 100 pontos):**
    * Quando determinados critérios não puderem ser avaliados por falta de oportunidade na conversa, o LLM retorna `nota_criterio: null` com a justificativa *"Sem oportunidade na conversa"*.
    * O sanitizador preserva as notas individuais dos critérios abordados (alimentando o coaching do SDR).
    * A nota final da chamada é recalculada proporcionalmente em base 100:
      $$\text{nota\_final} = \text{round}\left(\frac{\sum \text{notas obtidas}}{\sum \text{tetos dos critérios avaliados}} \times 100\right)$$
  * **Cláusula de Barreira (Mínimo de 50 pontos possíveis):**
    * Se a soma dos tetos dos critérios avaliáveis for **menor que 50 pontos** (ex.: apenas Abertura de 10 pts ou Abertura + Escuta = 20 pts), a ligação é considerada sem profundidade suficiente para ter nota final representativa.
    * Nesses casos, o sanitizador força `nota_final = None` (não entra no cálculo de `AVERAGE` do Power BI), enquanto as notas dos critérios existentes permanecem armazenadas para histórico e mentoria.

---

## 18. Suíte de Testes Automatizados e Validação Cruzada Atualizada

* **Novos Testes Adicionados:**
  * `test_faturamento_afirmado_sdr_nao_confirma_perfil`: garante que faturamento afirmado apenas pelo SDR ou calculado coaja o status da chamada para `Perfil pendente`.
  * `test_normalizacao_proporcional_nota_final_acima_50_pontos`: valida recálculo proporcional (ex.: 62/75 pontos possíveis normalizado para 83/100).
  * `test_normalizacao_proporcional_abaixo_50_pontos_anula_nota_final`: valida cláusula de barreira (< 50 pontos possíveis resulta em `nota_final = None`).
  * `test_oportunidade_treinamento_invalida_vira_none`: garante fallback para `None` em códigos inválidos ou `OP_ESC_04`.
  * `test_prazo_crm_preenche_data_confirmada`: valida derivação automática de `data_confirmada = 's'`.
  * `test_derivar_status_consolidado_empresa`: testa a consolidação multi-chamada dos dados cadastrais acumulados da empresa.

* **Status da Validação nas Duas Branches:**
  * **Branch `testeMatt`** (OpenRouter / GPT-4o-mini): **97 testes aprovados** (OK).
  * **Branch `testeIa-gratuita`** (Gemini `ChatGoogleGenerativeAI`): **102 testes aprovados** (OK).

