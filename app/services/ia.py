# -*- coding: utf-8 -*-
"""
============================================================================
Costura de Adaptadores para Provedores de IA do SONAX.

Responsabilidades:
    1. Definir o Protocolo `ProvedorIA` (Strategy) unificando capacidades cognitivas:
       - Transcrição ASR
       - Diarização e Revisão Textual
       - Avaliação de Atendimento (PEAH)
    2. Fornecer a implementação de produção `ProvedorIAReal` (OpenRouter + OpenAI).
    3. Fornecer a implementação em memória `FakeProvedorIA` para testes determinísticos,
       offline, com suporte a simulação de falhas transitórias e retries.
============================================================================
"""
from __future__ import annotations

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
        nome_atendente: str | None = None,
    ) -> str:
        """Diariza locutores e corrige pontuação da transcrição contínua."""
        ...

    def analisar(
        self,
        ligacao: str,
    ) -> dict[str, Any]:
        """Avalia critérios PEAH e gera resumo, notas e feedbacks da ligação."""
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
        nome_atendente: str | None = None,
    ) -> str:
        from app.services.revisao import revisar_texto
        return revisar_texto(transcricao, nome_atendente=nome_atendente)

    def analisar(
        self,
        ligacao: str,
    ) -> dict[str, Any]:
        from app.services.analise_final_AI import analisar_ligacao
        return analisar_ligacao(ligacao)


class FakeProvedorIA:
    """Adaptador em memória para testes offline determinísticos."""

    def __init__(
        self,
        *,
        transcricao_padrao: dict[str, Any] | None = None,
        revisao_padrao: str | None = None,
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
        self.analise_padrao = analise_padrao or {
            "nota_final": 9,
            "feedback_geral": "Atendimento cordial e muito eficiente.",
            "titulo": "Contato Financeiro - Agendamento",
            "resumo_chamada": "Atendente confirmou dados e agendou retorno com o cliente.",
            "pontos_fortes": "Boa comunicação e agilidade.",
            "fragilidades": None,
            "oportunidades": None,
            "criterios": [
                {"criterio": "chamar pelo nome", "nota_criterio": 10, "justificativa_criterio": "Chamou pelo nome do cliente."},
                {"criterio": "agir com empatia", "nota_criterio": 9, "justificativa_criterio": "Demonstrou empatia."},
                {"criterio": "ouvir com atencao", "nota_criterio": 9, "justificativa_criterio": "Ouviu com atenção."},
                {"criterio": "eficiencia operacional", "nota_criterio": 9, "justificativa_criterio": "Muito eficiente."},
                {"criterio": "surpreender", "nota_criterio": 8, "justificativa_criterio": "Bom atendimento."},
            ],
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
        nome_atendente: str | None = None,
    ) -> str:
        self.chamadas_revisar.append(transcricao)
        if self.falhas_restantes > 0:
            self.falhas_restantes -= 1
            raise self.excecao_falha
        return self.revisao_padrao

    def analisar(
        self,
        ligacao: str,
    ) -> dict[str, Any]:
        self.chamadas_analisar.append(ligacao)
        if self.falhas_restantes > 0:
            self.falhas_restantes -= 1
            raise self.excecao_falha
        return dict(self.analise_padrao)
