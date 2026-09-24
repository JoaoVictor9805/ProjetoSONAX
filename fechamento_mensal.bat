@echo off
cd /d "%~dp0"

:: 1. Garante que o diretorio de logs exista
if not exist "logs" mkdir logs

:: 2. Registra o inicio da execucao no log
echo ================================================================== >> logs\fechamento.log
echo [INICIO] Fechamento Mensal disparado em %date% as %time% >> logs\fechamento.log
echo ================================================================== >> logs\fechamento.log

:: 3. Executa a CLI do fechamento de ciclo (passando argumentos adicionais se fornecidos)
.\.venv\Scripts\python.exe -m app.services.fechamento_ciclo %* >> logs\fechamento.log 2>&1

:: 4. Verifica o codigo de retorno
if %errorlevel% equ 0 (
    echo [SUCESSO] Fechamento mensal concluido com exito em %date% as %time% >> logs\fechamento.log
) else (
    echo [ERRO] Ocorreu uma falha no fechamento. Codigo de saida: %errorlevel% >> logs\fechamento.log
)
echo. >> logs\fechamento.log
