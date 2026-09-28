# -*- coding: utf-8 -*-
"""
============================================================================
Gerenciador de Sessão de Logs e Anonimização.

Responsável por:
    1. Armazenar o histórico de linhas da execução atual.
    2. Aprender o mapeamento entre os rótulos de exibição ("Audio NN")
       e os nomes reais dos arquivos de áudio.
    3. Formatar o log dinamicamente de acordo com o modo ativo:
       - Modo Usuário: Rótulos genéricos ("Audio 01") e oculta linhas técnicas (`dev_only`).
       - Modo Desenvolvedor: Nomes reais dos arquivos e exibe detalhes técnicos.
============================================================================
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class LogEntry:
    """Entrada individual de log com metadados estruturados."""
    line: str
    stream: Literal["out", "err"] = "out"
    path: str | None = None
    dev_only: bool = False


class LogSessionManager:
    """Gerencia buffer de mensagens, apelidos de privacidade e visualização."""

    def __init__(self, modo_dev: bool = False) -> None:
        self._modo_dev: bool = modo_dev
        self._entries: list[LogEntry] = []
        self._rotulos: dict[str, str] = {}  # "Audio 01" -> "chamada_123.wav"

    @property
    def modo_dev(self) -> bool:
        return self._modo_dev

    @modo_dev.setter
    def modo_dev(self, valor: bool) -> None:
        self._modo_dev = valor

    def limpar(self) -> None:
        """Limpa o buffer e o mapa de rótulos para uma nova execução."""
        self._entries.clear()
        self._rotulos.clear()

    def registrar_rotulo(self, rotulo: str, nome_real: str) -> None:
        """Associa explicitamente um rótulo genérico ao nome real do arquivo."""
        if rotulo and nome_real:
            self._rotulos[rotulo] = nome_real

    def aprender_rotulo(self, texto: str, nome_real: str | None) -> None:
        """Detecta 'Audio NN' no texto e associa ao nome real se fornecido."""
        if nome_real and texto:
            match = re.search(r"Audio \d+", texto)
            if match:
                self._rotulos[match.group(0)] = nome_real

    def adicionar_linha(
        self,
        linha: str,
        stream: Literal["out", "err"] = "out",
        path: str | None = None,
        dev_only: bool = False,
    ) -> LogEntry:
        """Registra uma linha no buffer histórico."""
        entry = LogEntry(line=linha, stream=stream, path=path, dev_only=dev_only)
        self._entries.append(entry)
        if path:
            self.aprender_rotulo(linha, path)
        return entry

    def formatar_linha(self, entry: LogEntry, modo_dev: bool | None = None) -> str:
        """Formata uma linha substituindo rótulos genéricos pelo nome real se modo_dev ativo."""
        ativado = self._modo_dev if modo_dev is None else modo_dev
        if not ativado:
            return entry.line

        def _substituir(m: re.Match[str]) -> str:
            if entry.path is not None:
                return entry.path
            return self._rotulos.get(m.group(0), m.group(0))

        return re.sub(r"Audio \d+", _substituir, entry.line)

    def obter_linhas_formatadas(
        self, modo_dev: bool | None = None,
    ) -> list[tuple[str, Literal["out", "err"]]]:
        """Devolve todas as linhas visíveis formatadas para o modo solicitado."""
        ativado = self._modo_dev if modo_dev is None else modo_dev
        resultado: list[tuple[str, Literal["out", "err"]]] = []

        for entry in self._entries:
            if entry.dev_only and not ativado:
                continue
            texto_formatado = self.formatar_linha(entry, modo_dev=ativado)
            resultado.append((texto_formatado, entry.stream))

        return resultado
