@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ======================================================================
echo                     Instalador do SONAX
echo ======================================================================
echo.

:: 1. Define o caminho de destino permanente
set "DEST=%LOCALAPPDATA%\Programs\SONAX"

:: 2. Identifica a pasta com os arquivos compilados do SONAX (_internal e SONAX.exe)
set "SRC="
if exist "%~dp0SONAX\_internal" (
    set "SRC=%~dp0SONAX"
) else if exist "%~dp0_internal" (
    set "SRC=%~dp0"
) else if exist "%~dp0dist\SONAX\_internal" (
    set "SRC=%~dp0dist\SONAX"
)

if not defined SRC (
    echo [ERRO] Os arquivos compilados do SONAX nao foram encontrados!
    echo Execute primeiro o compilar_instalador.bat para gerar a pasta do programa.
    echo.
    pause
    exit /b 1
)

echo [1/4] Preparando pasta de instalacao:
echo       %DEST%
echo.

if not exist "%DEST%" mkdir "%DEST%"

echo [2/4] Copiando arquivos do SONAX para o destino permanente...
robocopy "%SRC%" "%DEST%" /E /R:2 /W:1 /NP /NDL >nul
if errorlevel 8 (
    echo [ERRO] Ocorreu uma falha ao copiar os arquivos para %DEST%.
    pause
    exit /b 1
)

:: Garante que o .env esteja presente no destino
if not exist "%DEST%\.env" (
    if exist "%SRC%\.env" (
        copy /y "%SRC%\.env" "%DEST%\.env" >nul 2>&1
    ) else if exist "%~dp0.env" (
        copy /y "%~dp0.env" "%DEST%\.env" >nul 2>&1
    ) else if exist "%~dp0..\.env" (
        copy /y "%~dp0..\.env" "%DEST%\.env" >nul 2>&1
    )
)

echo [3/4] Criando atalhos no Windows...

:: Cria atalho na Area de Trabalho (Desktop)
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut([System.IO.Path]::Combine($desktop, 'SONAX.lnk')); $s.TargetPath = '%DEST%\SONAX.exe'; $s.WorkingDirectory = '%DEST%'; $s.Description = 'SONAX - Transcricao e Analise Comercial de Chamadas'; $s.Save()"

:: Cria atalho no Menu Iniciar (Start Menu)
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $startMenu = [System.IO.Path]::Combine([Environment]::GetFolderPath('StartMenu'), 'Programs'); $s = $ws.CreateShortcut([System.IO.Path]::Combine($startMenu, 'SONAX.lnk')); $s.TargetPath = '%DEST%\SONAX.exe'; $s.WorkingDirectory = '%DEST%'; $s.Description = 'SONAX - Transcricao e Analise Comercial de Chamadas'; $s.Save()"

echo [4/4] Concluido!
echo.
echo ======================================================================
echo           SONAX instalado com sucesso na sua maquina!
echo ======================================================================
echo.
echo  - O aplicativo agora abre INSTANTANEAMENTE (sem pasta temporaria).
echo  - Atalho criado na sua Area de Trabalho: 'SONAX.lnk'
echo  - Atalho criado no seu Menu Iniciar.
echo  - Pasta da instalacao: %DEST%
echo.

set /p ABRIR="Deseja iniciar o SONAX agora? (S/N): "
if /i "!ABRIR!"=="S" (
    start "" "%DEST%\SONAX.exe"
)

exit /b 0
