@echo off
cd /d "%~dp0"

echo ======================================================================
echo       Compilando Instalador Unico do SONAX (Inno Setup)
echo ======================================================================
echo.
echo [INFO] Este processo compila o SONAX no modo pasta permanente (--onedir)
echo [INFO] e gera um instalador executavel unico (dist\Instalador_SONAX.exe).
echo [INFO] A instalacao e feita uma unica vez e o app abrira instantaneamente!
echo.

:: 1. Ativa o ambiente virtual
call .\.venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERRO] Ambiente virtual .venv nao encontrado!
    pause
    exit /b 1
)

:: 2. Detecta o compilador do Inno Setup (ISCC.exe)
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
) else (
    where iscc >nul 2>&1
    if not errorlevel 1 (
        set "ISCC=iscc"
    )
)

if "%ISCC%"=="" (
    echo [AVISO] Compilador Inno Setup (ISCC.exe) nao foi encontrado!
    echo [INFO] Para gerar o instalador executavel unico (Instalador_SONAX.exe),
    echo        instale o Inno Setup executando no terminal:
    echo        winget install JRSoftware.InnoSetup
    echo.
)

:: 3. Limpa builds anteriores
if exist "build" rmdir /s /q "build"
if exist "dist\SONAX" rmdir /s /q "dist\SONAX"
if exist "dist\Instalador_SONAX.exe" del /f /q "dist\Instalador_SONAX.exe"

echo [1/2] Empacotando aplicacao com PyInstaller (--onedir)...
echo Isso levara cerca de 1 a 2 minutos...
echo.

:: 4. Executa o PyInstaller no modo --onedir e excluindo modulos pesados nao utilizados
pyinstaller --noconsole --onedir --name "SONAX" ^
    --add-data ".env;." ^
    --add-binary "bin/UnRAR.exe;bin" ^
    --collect-all customtkinter ^
    --collect-all psycopg ^
    --collect-all langchain ^
    --collect-all langchain_openai ^
    --collect-all requests ^
    --exclude-module torch ^
    --exclude-module torchvision ^
    --exclude-module torchaudio ^
    run_gui.py

if errorlevel 1 (
    echo.
    echo [ERRO] Ocorreu uma falha durante a compilacao do PyInstaller!
    pause
    exit /b 1
)

:: 5. Copia arquivos auxiliares para dentro de dist\SONAX
if exist "instalar.bat" (
    copy /y "instalar.bat" "dist\SONAX\instalar.bat" >nul 2>&1
    copy /y "instalar.bat" "dist\Instalar_SONAX.bat" >nul 2>&1
)
if exist ".env" (
    copy /y ".env" "dist\SONAX\.env" >nul 2>&1
)

:: 6. Gera o Instalador com Inno Setup (se disponivel)
if not "%ISCC%"=="" (
    echo.
    echo [2/2] Gerando instalador unico (.exe) com Inno Setup...
    "%ISCC%" inno_setup.iss
    if errorlevel 1 (
        echo.
        echo [ERRO] Falha ao compilar com Inno Setup!
        pause
        exit /b 1
    )
)

echo.
echo ======================================================================
echo               Compilacao Concluida com Sucesso!
echo ======================================================================
echo.
if exist "dist\Instalador_SONAX.exe" (
    echo  [PRODUTO FINAL PRONTO PARA DISTRIBUICAO]
    echo  - Instalador gerado: dist\Instalador_SONAX.exe
    echo.
    echo  Como enviar para os usuarios:
    echo    1. Envie apenas o arquivo "dist\Instalador_SONAX.exe" para o outro computador.
    echo    2. O usuario da 2 cliques e instala em segundos.
    echo    3. Atalhos sao criados na Area de Trabalho e Menu Iniciar.
    echo    4. O SONAX abrira instantaneamente a partir de entao!
) else (
    echo  - Pasta do aplicativo: dist\SONAX
    echo  - Instalador script:   dist\Instalar_SONAX.bat
)
echo.
pause
