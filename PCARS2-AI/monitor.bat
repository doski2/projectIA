@echo off
:: ============================================================
:: monitor.bat  —  Dashboard de entrenamiento PCARS2-AI
:: ============================================================
:: Uso:
::   monitor.bat               <- Auto-detecta el CSV más reciente
::   monitor.bat --refresh 10  <- Actualiza cada 10 segundos
::   monitor.bat logs\formula_rookie__sugo\metricas.csv
:: ============================================================

setlocal

set "VENV=%~dp0..\\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Entorno virtual no encontrado en: %VENV%
    echo         Ejecuta primero: python -m venv .venv
    pause
    exit /b 1
)

set PYTHONUNBUFFERED=1
"%PYTHON%" -u "%~dp0src\monitor.py" %*
