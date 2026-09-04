@echo off
setlocal
title Painel Constrained-off RN

rem Diretorio do proprio .bat (funciona com espacos e acentos no caminho)
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERRO] Ambiente virtual nao encontrado em .venv\Scripts\python.exe
    echo Crie com: py -3.13 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Iniciando painel com recarregamento automatico ativo...
echo Salve qualquer arquivo .py para ver a atualizacao em tempo real.
echo Pressione Ctrl+C nesta janela para encerrar.
echo.

"%VENV_PY%" -m streamlit run app.py --server.runOnSave=true --server.fileWatcherType=auto

endlocal
