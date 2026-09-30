# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Coleta RPA de Informações no Google via Pywinauto / Navegador.

Responsabilidades:
    1. Formatação e normalização do telefone da empresa contatada.
    2. Pesquisa automatizada no Google via navegador padrão do sistema
       (mantendo a sessão/cookies reais do usuário para evitar bloqueios anti-bot).
    3. Cópia do conteúdo da página via automação de teclado (Ctrl+A, Ctrl+C, Ctrl+W)
       e leitura segura da área de transferência via pyperclip.
    4. Cache por número de telefone para evitar requisições repetidas no mesmo lote.
    5. Suporte a cancelamento cooperativo e tratamento de falhas sem travar o pipeline.
============================================================================
"""
from __future__ import annotations

import re
import threading
import time
import urllib.parse
from typing import Callable


def formatar_telefone_busca(numero: str | None, estado_ddd: str | None = None) -> str | None:
    """Formata o número de telefone e DDD para a busca no Google.

    Remove o indicativo de país '+55' / '55' e formata no padrão nacional:
        '(DD) NNNN-NNNN' ou '(DD) 9NNNN-NNNN'.

    Exemplos:
        '554133462828' -> '(41) 3346-2828'
        '33101010', estado_ddd='41' -> '(41) 3310-1010'
        '4133101010' -> '(41) 3310-1010'
        '5541999992828' -> '(41) 99999-2828'
        '0800 591 2117' -> '0800 591 2117'
    """
    if not numero:
        return None

    num_str = str(numero).strip()
    ddd_str = str(estado_ddd).strip() if estado_ddd else ""

    # Remove qualquer caractere não numérico
    num_limpo = re.sub(r"[^\d]", "", num_str)
    ddd_limpo = re.sub(r"[^\d]", "", ddd_str)

    if not num_limpo:
        return None

    # 1. Se começa com 0800 ou 0300 (números corporativos especiais)
    if num_limpo.startswith("0800") or num_limpo.startswith("0300"):
        if len(num_limpo) == 11:
            return f"{num_limpo[:4]} {num_limpo[4:7]} {num_limpo[7:]}"
        return num_limpo

    # 2. Se começa com DDI 55 (Brasil): remove 55 se o restante tiver tamanho de telefone válido (10 ou 11 dígitos)
    if num_limpo.startswith("55") and len(num_limpo) in (12, 13):
        num_limpo = num_limpo[2:]

    # 3. Se agora num_limpo tem 10 ou 11 dígitos (já contém DDD + número)
    if len(num_limpo) in (10, 11):
        ddd = num_limpo[:2]
        resto = num_limpo[2:]
        if len(resto) == 8:
            return f"({ddd}) {resto[:4]}-{resto[4:]}"
        elif len(resto) == 9:
            return f"({ddd}) {resto[:5]}-{resto[5:]}"
        return f"({ddd}) {resto}"

    # 4. Se num_limpo tem 8 ou 9 dígitos e temos DDD fornecido
    if len(num_limpo) in (8, 9) and ddd_limpo:
        ddd = ddd_limpo[:2]
        if len(num_limpo) == 8:
            return f"({ddd}) {num_limpo[:4]}-{num_limpo[4:]}"
        elif len(num_limpo) == 9:
            return f"({ddd}) {num_limpo[:5]}-{num_limpo[5:]}"

    # 5. Fallback com DDD caso falte formatação específica
    if ddd_limpo and not num_limpo.startswith(ddd_limpo):
        return f"({ddd_limpo}) {num_str}".strip()

    return num_str


import os
import shutil


def listar_caminhos_google_chrome() -> list[str]:
    """Retorna uma lista priorizada de possíveis caminhos executáveis do Google Chrome no Windows.

    Cobre as diferentes versões e tipos de instalação do Google Chrome para suportar
    múltiplas máquinas (Admin, Não-Admin/Local, 64-bit, 32-bit, Beta, Dev, Canary e Registro).
    """
    candidatos: list[str] = []

    # 1. Consulta ao Registro do Windows (HKLM e HKCU - App Paths)
    try:
        import winreg
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(raiz, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as chave:
                    caminho_reg, _ = winreg.QueryValueEx(chave, "")
                    if caminho_reg and caminho_reg not in candidatos:
                        candidatos.append(str(caminho_reg).strip('"'))
            except OSError:
                pass
    except ImportError:
        pass

    # 2. Variáveis de ambiente de sistema do Windows
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_w6432 = os.environ.get("ProgramW6432", r"C:\Program Files")
    user_profile = os.environ.get("USERPROFILE", "")

    # Lista de subdiretórios e canais oficiais do Google Chrome no Windows
    padroes = [
        # Chrome Padrão / Estável (64-bit e 32-bit)
        os.path.join(program_files, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(program_files_x86, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(program_w6432, r"Google\Chrome\Application\chrome.exe"),

        # Chrome por Usuário (Instalação sem privilégios de Administrador / LocalAppData)
        os.path.join(local_app_data, r"Google\Chrome\Application\chrome.exe") if local_app_data else "",
        os.path.join(user_profile, r"AppData\Local\Google\Chrome\Application\chrome.exe") if user_profile else "",

        # Chrome Beta
        os.path.join(program_files, r"Google\Chrome Beta\Application\chrome.exe"),
        os.path.join(program_files_x86, r"Google\Chrome Beta\Application\chrome.exe"),
        os.path.join(local_app_data, r"Google\Chrome Beta\Application\chrome.exe") if local_app_data else "",

        # Chrome Dev
        os.path.join(program_files, r"Google\Chrome Dev\Application\chrome.exe"),
        os.path.join(program_files_x86, r"Google\Chrome Dev\Application\chrome.exe"),
        os.path.join(local_app_data, r"Google\Chrome Dev\Application\chrome.exe") if local_app_data else "",

        # Chrome Canary (SxS)
        os.path.join(local_app_data, r"Google\Chrome SxS\Application\chrome.exe") if local_app_data else "",
        os.path.join(user_profile, r"AppData\Local\Google\Chrome SxS\Application\chrome.exe") if user_profile else "",

        # Chrome for Testing / Standalone corporativo
        os.path.join(program_files, r"Google\Chrome for Testing\Application\chrome.exe"),
        os.path.join(local_app_data, r"Google\Chrome for Testing\Application\chrome.exe") if local_app_data else "",
    ]

    for p in padroes:
        if p and p not in candidatos:
            candidatos.append(p)

    # 3. Executável no PATH do sistema
    which_chrome = shutil.which("chrome") or shutil.which("chrome.exe") or shutil.which("google-chrome")
    if which_chrome and which_chrome not in candidatos:
        candidatos.append(which_chrome)

    return candidatos


def obter_caminho_chrome_instalado() -> str | None:
    """Testa os candidatos e retorna o primeiro executável do Google Chrome válido nesta máquina."""
    for caminho in listar_caminhos_google_chrome():
        if caminho and os.path.isfile(caminho):
            return caminho
    return None


def testar_versoes_chrome() -> list[dict[str, str | bool]]:
    """Testa e retorna o status de cada versão/caminho do Google Chrome suportado nesta máquina."""
    resultados = []
    for caminho in listar_caminhos_google_chrome():
        existe = bool(caminho and os.path.isfile(caminho))
        resultados.append({
            "caminho": caminho,
            "instalado": existe,
        })
    return resultados


def abrir_navegador_busca(url: str, caminho_navegador: str | None = None) -> bool:
    """Abre a URL de pesquisa no Google Chrome, priorizando caminhos testados.

    Se for passado um 'caminho_navegador' específico, tenta executá-lo.
    Caso contrário, busca dinamicamente entre as versões instaladas do Chrome.
    Se nenhuma versão for encontrada, utiliza o navegador padrão via webbrowser.
    """
    cmd_exec = caminho_navegador or obter_caminho_chrome_instalado()
    if cmd_exec and os.path.isfile(cmd_exec):
        try:
            import subprocess
            subprocess.Popen([cmd_exec, url])
            return True
        except Exception as exc:
            print(f"  [AVISO] Falha ao abrir navegador em '{cmd_exec}': {exc}. Usando fallback padrão.")

    import webbrowser
    return webbrowser.open(url)


def coletar_texto_google_telefone(
    telefone: str,
    *,
    cancel: threading.Event | None = None,
    tempo_espera_pagina: float = 6.0,
    caminho_navegador: str | None = None,
) -> str:
    """Abre o Google Chrome (ou padrão), busca o telefone no Google, copia o texto e fecha a aba.

    Retorna o texto capturado ou 'Não encontrado' em caso de erro/timeout.
    """
    if cancel is not None and cancel.is_set():
        return "Não encontrado"

    if not telefone or not telefone.strip():
        return "Não encontrado"

    import pyperclip
    from pywinauto import keyboard

    query = f"{telefone.strip()} telefone"
    url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"

    try:
        # 1. Limpa área de transferência
        pyperclip.copy("")

        # 2. Abre a aba no Google Chrome (priorizando versões instaladas na máquina)
        abrir_navegador_busca(url, caminho_navegador=caminho_navegador)

        # 3. Espera a página carregar com verificação periódica de cancelamento
        passo_espera = 0.2
        decorrido = 0.0
        while decorrido < tempo_espera_pagina:
            if cancel is not None and cancel.is_set():
                # Tenta fechar a aba aberta antes de sair
                try:
                    keyboard.send_keys('^w')
                except Exception:
                    pass
                return "Não encontrado"
            time.sleep(passo_espera)
            decorrido += passo_espera

        if cancel is not None and cancel.is_set():
            return "Não encontrado"

        # 4. Seleciona Tudo (Ctrl + A)
        keyboard.send_keys('^a')
        time.sleep(0.6)

        # 5. Copia (Ctrl + C)
        keyboard.send_keys('^c')
        time.sleep(0.6)

        # 6. Fecha a aba atual (Ctrl + W)
        keyboard.send_keys('^w')
        time.sleep(0.5)

        # 7. Captura o texto do clipboard
        texto_copiado = pyperclip.paste()
        if texto_copiado and texto_copiado.strip():
            return texto_copiado.strip()

        return "Não encontrado"

    except Exception as exc:
        print(f"  [AVISO] Falha ao coletar dados do Google para '{telefone}': {exc}")
        return "Não encontrado"


def coletar_textos_google_lote(
    telefones_por_chave: dict[str, str | None],
    *,
    cancel: threading.Event | None = None,
    tempo_espera_pagina: float = 6.0,
    caminho_navegador: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    """Coleta o texto do Google para um dicionário de chaves -> telefones.

    Aplica cache por telefone para evitar abrir o navegador mais de uma vez
    para o mesmo número de telefone no mesmo lote.
    """
    resultado_por_chave: dict[str, str] = {}
    cache_por_telefone: dict[str, str] = {}

    # Filtra telefones únicos válidos
    telefones_unicos: list[str] = []
    for tel in telefones_por_chave.values():
        if tel and tel.strip() and tel not in telefones_unicos:
            telefones_unicos.append(tel)

    total_unicos = len(telefones_unicos)
    from app.logs import log_dev

    for idx, tel in enumerate(telefones_unicos, 1):
        if cancel is not None and cancel.is_set():
            break

        if on_progress is not None:
            on_progress(idx, total_unicos, tel)

        print(f"  [INFO] [{idx}/{total_unicos}] Robô Google (RPA): Consultando telefone {tel} ...")

        texto = coletar_texto_google_telefone(
            tel,
            cancel=cancel,
            tempo_espera_pagina=tempo_espera_pagina,
            caminho_navegador=caminho_navegador,
        )
        cache_por_telefone[tel] = texto

        if texto and texto != "Não encontrado":
            print(f"  [INFO] Robô Google: Dados capturados com sucesso para {tel}")
            preview = texto[:200].replace("\n", " ").strip()
            log_dev(f"Google RPA ({tel}) conteúdo capturado ({len(texto)} chars): {preview}...")
        else:
            print(f"  [AVISO] Robô Google: Conteúdo não localizado para {tel} (fallback ativado)")
            log_dev(f"Google RPA ({tel}): Busca finalizada sem retorno útil.")

        # Pequena pausa entre buscas se houver mais de uma
        if idx < total_unicos and cancel is not None and not cancel.is_set():
            time.sleep(1.0)

    # Mapeia de volta para cada chave
    for chave, tel in telefones_por_chave.items():
        if not tel:
            resultado_por_chave[chave] = "Não encontrado"
        else:
            val = cache_por_telefone.get(tel, "Não encontrado")
            resultado_por_chave[chave] = val

    return resultado_por_chave
