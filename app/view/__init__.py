# -*- coding: utf-8 -*-
"""
============================================================================
Pacote `app.view` — interface gráfica do SONAX (CustomTkinter).

Este pacote NÃO importa `services.io` no nível do módulo para evitar ciclo
de import: `app.view.app` interage com worker que puxa `app.services.io.coletar_wavs` /
`app.services.io.resolver_destino` no momento da construção da janela.

Módulos:
    events    — dataclasses de eventos + fila thread-safe.
    stream    — file-like que enfileira linhas (redireciona stdout/stderr).
    worker    — orquestrador do pipeline em thread separada.
    dialogs   — helper para o diálogo nativo de seleção de pasta.
    app       — `App(ctk.CTk)`: monta a janela, faz polling, atualiza UI.
============================================================================
"""
