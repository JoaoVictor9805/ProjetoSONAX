# -*- coding: utf-8 -*-
"""
============================================================================
Entry-point da GUI: `python -m app.view`.

Instancia a `App` (CustomTkinter) e entra no mainloop do Tk. A
orquestração real do pipeline vive em `app.view.worker.run_pipeline`
e roda em uma thread separada para não congelar a interface.
============================================================================
"""

from app.view.app import App


def run_gui() -> None:
    """Cria a janela principal e inicia o mainloop do Tk."""
    App().mainloop()


if __name__ == "__main__":
    run_gui()
