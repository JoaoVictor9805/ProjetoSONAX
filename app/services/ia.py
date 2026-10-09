# -*- coding: utf-8 -*-
"""
============================================================================
Costura de Adaptadores para Provedores de IA do SONAX.

Responsabilidades:
    1. Definir o Protocolo `ProvedorIA` (Strategy) unificando capacidades cognitivas:
       - Transcrição ASR
       - Diarização e Revisão Textual
       - Avaliação de Qualidade Comercial (SPIN/BANT/SDR)
    2. Fornecer a implementação de produção `ProvedorIAReal` (OpenRouter + OpenAI).
    3. Fornecer a implementação em memória `FakeProvedorIA` para testes determinísticos,
       offline, com suporte a simulação de falhas transitórias e retries.
============================================================================
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


SubProgressCallback = Callable[[float, str], None]


@runtime_checkable
class ProvedorIA(Protocol):
    """Protocolo abstrato que define as operações cognitivas de IA do sistema."""

    def transcrever(
        self,
        caminho: Path | str,
        *,
        cancel: threading.Event | None = None,
        on_progress: SubProgressCallback | None = None,
        timeout: int = 90,
    ) -> dict[str, Any]:
        """Transcreve áudio para texto com métricas de qualidade acústica/ASR."""
        ...

    def revisar(
        self,
        transcricao: str,
        *,
        texto_copiado_google: str | None = None,
        nome_atendente: str | None = None,
    ) -> dict[str, str]:
        """Diariza locutores e corrige pontuação da transcrição contínua."""
        ...

    def analisar(
        self,
        ligacao: str,
        *,
        protocolo: int | None = None,
        empresa_contatada: int | None = None,
        empresa_nome: str | None = None,
        nome_sdr: str | None = None,
        data_referencia: str | None = None,
    ) -> dict[str, Any]:
        """Avalia qualidade comercial B2B (SPIN, BANT, SDR, CRM) da ligação."""
        ...


class ProvedorIAReal:
    """Adaptador de produção que realiza chamadas reais de rede."""

    def transcrever(
        self,
        caminho: Path | str,
        *,
        cancel: threading.Event | None = None,
        on_progress: SubProgressCallback | None = None,
        timeout: int = 90,
    ) -> dict[str, Any]:
        from app.services.transcricao import transcrever_audio_openrouter
        return transcrever_audio_openrouter(
            caminho,
            cancel=cancel,
            on_progress=on_progress,
            timeout=timeout,
        )

    def revisar(
        self,
        transcricao: str,
        *,
        texto_copiado_google: str | None = None,
        nome_atendente: str | None = None,
    ) -> dict[str, str]:
        from app.services.revisao import revisar_texto
        return revisar_texto(
            transcricao,
            texto_copiado_google=texto_copiado_google,
            nome_atendente=nome_atendente,
        )

    def analisar(
        self,
        ligacao: str,
        *,
        protocolo: int | None = None,
        empresa_contatada: int | None = None,
        empresa_nome: str | None = None,
        nome_sdr: str | None = None,
        data_referencia: str | None = None,
    ) -> dict[str, Any]:
        from app.services.analise_final_AI import analisar_ligacao
        return analisar_ligacao(
            ligacao,
            protocolo=protocolo,
            empresa_contatada=empresa_contatada,
            empresa_nome=empresa_nome,
            nome_sdr=nome_sdr,
            data_referencia=data_referencia,
        )


class FakeProvedorIA:
    """Adaptador em memória para testes offline determinísticos."""

    def __init__(
        self,
        *,
        transcricao_padrao: dict[str, Any] | None = None,
        revisao_padrao: str | None = None,
        empresa_padrao: str | None = None,
        fonte_dados_padrao: str | None = None,
        analise_padrao: dict[str, Any] | None = None,
        falhas_antes_de_acerto: int = 0,
        excecao_falha: Exception | None = None,
    ):
        self.transcricao_padrao = transcricao_padrao or {
            "texto": "Bom dia, gostaria de falar com o financeiro da empresa.",
            "duracao_segundos": 45.0,
            "confidence": 0.95,
            "metricas": {
                "logprob_media": -0.2,
                "taxa_compressao_media": 1.1,
                "probabilidade_media_sem_fala": 0.02,
            },
            "turnos": [],
            "speakers": [],
        }
        self.revisao_padrao = revisao_padrao or (
            "Agente (Carlos): Bom dia, gostaria de falar com o financeiro da empresa.\n"
            "Cliente (Empresa): Olá, pode falar comigo."
        )
        self.empresa_padrao = empresa_padrao or "Empresa Teste"
        self.fonte_dados_padrao = fonte_dados_padrao or (
            "[GOOGLE]\nTexto Google Teste\n\n[DIARIZAÇÃO]\nEmpresa Teste"
        )
        self.analise_padrao = analise_padrao or {
            "avaliacao_ia": {
                "protocolo": 123456789,
                "data_avaliacao": "2026-09-30",
                "modelo_ia": "meta-llama/llama-3.1-8b-instruct",
                "interlocutor": "Carlos Silva",
                "cargo": "Diretor Financeiro",
                "empresa_contatada": 1,
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
                "resultado_frase": "O SDR validou o regime de Lucro Real e agendou reunião técnica.",
            },
            "analise_spin": {
                "situacao": "Empresa industrial com contabilidade interna.",
                "problema": "Dificuldades com obrigações fiscais.",
                "implicacao": "Risco de multas e sobrecarga.",
                "necessidade_solucao": "Consultoria tributária especializada.",
                "evidencias": "\"A nossa principal dor hoje é cruzar dados\" (14:22).",
                "lacunas": "Não aprofundou impacto financeiro.",
            },
            "analise_bant": {
                "budget_classificacao": "não informado",
                "budget_evidencia": "Não abordado.",
                "authority_classificacao": "confirmado",
                "authority_evidencia": "Interlocutor é o decisor.",
                "need_classificacao": "confirmado",
                "need_evidencia": "Reconheceu risco fiscal.",
                "timeline_classificacao": "indício",
                "timeline_evidencia": "Até fechamento do trimestre.",
            },
            "avaliacao_sdr": {
                "nota_final": 85,
                "feedback_geral": "Postura consultiva e boa qualificação.",
                "acertos": "1. Escuta ativa. 2. Investigação do regime tributário.",
                "melhorias": "1. Explorar implicações. 2. Confirmar decisores.",
                "frase_alternativa": "Que impacto financeiro esses erros trouxeram?",
                "codigo_oportunidade": "OP_SPIN_03",
            },
            "avaliacao_criterio": [
                {
                    "criterio": "Abertura clara, motivo do contato e relevância para o interlocutor",
                    "nota_criterio": 10,
                    "justificativa_criterio": "Apresentou motivo claro.",
                    "codigo_criterio": "CRIT_ABERTURA",
                },
                {
                    "criterio": "Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução",
                    "nota_criterio": 22,
                    "justificativa_criterio": "Boa descoberta inicial.",
                    "codigo_criterio": "CRIT_SPIN",
                },
                {
                    "criterio": "Investigação adequada do perfil: setor, regime tributário, faturamento",
                    "nota_criterio": 25,
                    "justificativa_criterio": "Validou setor e faturamento.",
                    "codigo_criterio": "CRIT_PERFIL",
                },
                {
                    "criterio": "Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo",
                    "nota_criterio": 12,
                    "justificativa_criterio": "Mapeou autoridade e necessidade.",
                    "codigo_criterio": "CRIT_BANT",
                },
                {
                    "criterio": "Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções",
                    "nota_criterio": 8,
                    "justificativa_criterio": "Tratamento respeitoso.",
                    "codigo_criterio": "CRIT_ESCUTA",
                },
                {
                    "criterio": "Proposta de próximo passo pertinente e tentativa de obter compromisso claro",
                    "nota_criterio": 8,
                    "justificativa_criterio": "Compromisso agendado.",
                    "codigo_criterio": "CRIT_PROX_PASSO",
                },
            ],
            "interlocutor": {
                "interesse_expresso": "Interesse em avaliar créditos.",
                "duvidas": "Questionou impacto na contabilidade.",
                "objecoes": "não houve",
                "resposta_sdr": "Explicou modelo complementar.",
                "reacao_interlocutor": "Aceitou explicação.",
            },
            "crm": {
                "acao": "Reunião confirmada (apresentação técnica)",
                "responsavel": "SDR Carlos",
                "prazo": "06/10/2026 às 14:00",
                "dados_extras": "Confirmar presenças.",
                "resumo": "Empresa industrial em Lucro Real com faturamento > 1M. Agendada reunião técnica.",
            },
        }
        self.chamadas_transcrever: list[Path] = []
        self.chamadas_revisar: list[str] = []
        self.chamadas_analisar: list[str] = []
        self.falhas_restantes = falhas_antes_de_acerto
        self.excecao_falha = excecao_falha or ConnectionError("Falha de rede simulada no provedor de IA")

    def transcrever(
        self,
        caminho: Path | str,
        *,
        cancel: threading.Event | None = None,
        on_progress: SubProgressCallback | None = None,
        timeout: int = 90,
    ) -> dict[str, Any]:
        self.chamadas_transcrever.append(Path(caminho))
        if cancel is not None and cancel.is_set():
            from app.services.transcricao import TranscricaoCancelada
            raise TranscricaoCancelada()

        if self.falhas_restantes > 0:
            self.falhas_restantes -= 1
            raise self.excecao_falha

        if on_progress is not None:
            try:
                on_progress(1.0, "Transcrição simulada concluída")
            except Exception:
                pass

        return dict(self.transcricao_padrao)

    def revisar(
        self,
        transcricao: str,
        *,
        texto_copiado_google: str | None = None,
        nome_atendente: str | None = None,
    ) -> dict[str, str]:
        self.chamadas_revisar.append(transcricao)
        if self.falhas_restantes > 0:
            self.falhas_restantes -= 1
            raise self.excecao_falha
        return {
            "empresa": self.empresa_padrao,
            "revisao": self.revisao_padrao,
            "fonte_dados": self.fonte_dados_padrao,
        }

    def analisar(
        self,
        ligacao: str,
        *,
        protocolo: int | None = None,
        empresa_contatada: int | None = None,
        empresa_nome: str | None = None,
        nome_sdr: str | None = None,
        data_referencia: str | None = None,
    ) -> dict[str, Any]:
        self.chamadas_analisar.append(ligacao)
        if self.falhas_restantes > 0:
            self.falhas_restantes -= 1
            raise self.excecao_falha
        res = json.loads(json.dumps(self.analise_padrao))
        if protocolo is not None:
            res["avaliacao_ia"]["protocolo"] = protocolo
        if empresa_contatada is not None:
            res["avaliacao_ia"]["empresa_contatada"] = empresa_contatada
        return res
