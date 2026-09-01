# -*- coding: utf-8 -*-
"""
============================================================================
3. app.py — o balcão de atendimento (a janela)

Esse é o arquivo grande, o "rosto" do programa. Ele faz duas coisas bem diferentes:

a) Desenhar a tela. Métodos tipo _build_header, _build_selector, _build_progress, _build_log — cada um cria um pedaço da janela (título, botão "Procurar", barra de progresso, caixa de log). É só montagem de móveis, tijolo por tijolo.

b) Reagir a cliques. Os dois principais:

_on_procurar — roda quando você clica "Procurar". Chama o dialogs.py (arquivo 4) pra abrir a janelinha de escolher pasta.
_on_enviar — roda quando você clica "Enviar". Aqui é onde a mágica começa: ele manda a cozinha começar a trabalhar (cria uma thread separada) e começa a checar a espeteira de bilhetes de 50 em 50 milissegundos:

self._worker = threading.Thread(target=run_pipeline, args=(...))
self._worker.start()
self._after_id = self.after(50, self._poll)

self.after(50, self._poll) é literalmente "daqui a 50ms, chama _poll de novo". É o atendente voltando pra espeteira a cada 50ms pra ver se chegou bilhete.
============================================================================
"""

from app.view.app import App


def run_gui() -> None:
    """Cria a janela principal e inicia o mainloop do Tk."""
    App().mainloop()


if __name__ == "__main__":
    run_gui()
