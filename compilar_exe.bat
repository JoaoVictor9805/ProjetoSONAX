@echo off
cd /d "%~dp0"
echo ===================================================
echo       Compilando SONAX para Executavel (.exe)
echo ===================================================
echo.

:: 1. Ativa o ambiente virtual
call .\.venv\Scripts\activate.bat

:: 2. Limpa builds anteriores (se existirem)
if exist "build" rmdir /s /q "build"
if exist "dist\SONAX.exe" del /f /q "dist\SONAX.exe"

echo Iniciando processo de empacotamento com PyInstaller...
echo Isso pode levar de 1 a 3 minutos dependendo das bibliotecas.
echo.

:: 3. Executa o PyInstaller com todas as dependencias necessarias
pyinstaller --noconsole --onefile --name "SONAX" ^
    --add-data ".env;." ^
    --add-binary "bin/UnRAR.exe;bin" ^
    --collect-all customtkinter ^
    --collect-all psycopg ^
    --collect-all langchain ^
    --collect-all langchain_google_genai ^
    --collect-all assemblyai ^
    run_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Ocorreu uma falha durante a compilacao!
    pause
    exit /b %errorlevel%
)

echo.
echo ===================================================
echo   Compilacao concluida com sucesso!
echo   O executavel esta disponivel em: dist\SONAX.exe
echo ===================================================
echo.
pause
