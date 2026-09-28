# -*- coding: utf-8 -*-
"""
============================================================================
Entrypoint da interface gráfica do SONAX.

Inicializa e executa a aplicação gráfica `App`.
============================================================================
"""

from app.view.app import App


def run_gui() -> None:
    """Cria a janela principal e inicia o mainloop do Tk."""
    App().mainloop()


if __name__ == "__main__":
    run_gui()
