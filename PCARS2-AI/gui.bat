@echo off
setlocal

:: ============================================================
::  PCARS2-AI v2 — GUI de entrenamiento
:: ============================================================

set SCRIPT_DIR=%~dp0
set "PYTHON=%SCRIPT_DIR%..\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] No se encuentra el venv: %PYTHON%
    pause
    exit /b 1
)

cd /d "%SCRIPT_DIR%"
"%PYTHON%" -m v2.gui
