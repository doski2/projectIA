@echo off
setlocal

:: ============================================================
::  PCARS2-AI — Monitor de metricas en vivo
::  Auto-detecta logs\**\metricas.csv mas reciente
:: ============================================================

set SCRIPT_DIR=%~dp0
set "PYTHON=%SCRIPT_DIR%..\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] No se encuentra el venv: %PYTHON%
    pause
    exit /b 1
)

cd /d "%SCRIPT_DIR%"
"%PYTHON%" src\monitor.py --refresh 20 %*
