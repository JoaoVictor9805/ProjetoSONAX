prompt_revisao = """Corrija SOMENTE erros evidentes de transcrição (ASR), preservando palavras, significado, informalidade, ordem e estilo original.
Use apenas o contexto da própria transcrição; não invente, reescreva, resuma ou corrija por presunção. Em caso de dúvida, mantenha o original.
Retorne SOMENTE a transcrição corrigida, sem explicações ou texto adicional."""

prompt_analise = """Avalie a ligação exclusivamente pela transcrição, considerando o atendimento do atendente e os critérios PEAH.
Dê uma nota de 0 a 10 e faça um resumo curto e objetivo da avaliação, sem inventar informações ou comportamentos.
Retorne SOMENTE um JSON válido neste formato: 

{{
  "nota_final": 0,
  "feedback_geral": "string",
  "criterios": [
    {{
      "criterio": "chamar pelo nome",
      "nota_criterio": 0,
      "justificativa_criterio": "string"
    }},
    {{
      "criterio": "agir com empatia",
      "nota_criterio": 0,
      "justificativa_criterio": "string"
    }},
    {{
      "criterio": "ouvir com atencao",
      "nota_criterio": 0,
      "justificativa_criterio": "string"
    }},
    {{
      "criterio": "coordialidade na fala",
      "nota_criterio": 0,
      "justificativa_criterio": "string"
    }},
    {{
      "criterio": "eficiencia operacional",
      "nota_criterio": 0,
      "justificativa_criterio": "string"
    }},
    {{
      "criterio": "surpreender",
      "nota_criterio": 0,
      "justificativa_criterio": "string"
    }}
  ]
}}

."""