@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: 1. Detecta se existe 'python' ou o inicializador oficial 'py'
set "PY_CMD="
python --version >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
    py -3 --version >nul 2>&1 && set "PY_CMD=py -3"
)

:: 2. Se o Python nao foi encontrado, instala automaticamente
if not defined PY_CMD (
    echo Python nao foi detectado neste computador!
    echo Baixando e instalando o Python 3.12 automaticamente, aguarde...
    
    :: Baixa e instala o Python oficial com 'Add to PATH' silenciosamente
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe', 'python_installer.exe')}"
    
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
    del python_installer.exe

    :: Atualiza a sessao atual para reconhecer o PATH recem-instalado
    set "PATH=%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%PATH%"
    set "PY_CMD=python"
    
    python --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo Nao foi possivel carregar o Python automaticamente. 
        echo Por favor, feche e abra o iniciar.bat novamente.
        pause
        exit /b
    )
)

:: 3. Cria a .venv se nao existir
if not exist ".venv" (
    echo Criando ambiente virtual (.venv)...
    !PY_CMD! -m venv .venv
    echo Instalando dependencias do requirements.txt...
    call .\.venv\Scripts\pip install -r requirements.txt
)

:: 4. Executa a aplicacao com a .venv
call .\.venv\Scripts\activate.bat
python run_gui.py

:: 5. Se der erro ao executar, segura a tela
if %errorlevel% neq 0 (
    echo.
    echo Ocorreu um erro ao executar a aplicacao.
    pause
)
