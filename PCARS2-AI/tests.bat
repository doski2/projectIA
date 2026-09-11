@echo off
setlocal

:: ============================================================
::  PCARS2-AI — Ejecutar tests con el venv del proyecto
::
::  Uso:
::    tests.bat
::    tests.bat -q
::    tests.bat tests\test_monitor.py -v
:: ============================================================

set SCRIPT_DIR=%~dp0
set "PYTHON=%SCRIPT_DIR%..\.venv\Scripts\python.exe"
set "REQUIREMENTS=%SCRIPT_DIR%requirements.txt"

if not exist "%PYTHON%" (
    echo.
    echo [ERROR] No se encuentra el venv:
    echo   %PYTHON%
    echo.
    echo Crea e instala dependencias:
    echo   python -m venv ..\.venv
    echo   ..\.venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

cd /d "%SCRIPT_DIR%"

if not exist "%REQUIREMENTS%" (
    echo [ERROR] No se encuentra requirements.txt en %SCRIPT_DIR%
    pause
    exit /b 1
)

"%PYTHON%" -m pip show gymnasium >nul 2>&1
if errorlevel 1 (
    echo [tests] Instalando dependencias desde requirements.txt...
    "%PYTHON%" -m pip install -r "%REQUIREMENTS%"
    if errorlevel 1 (
        echo [ERROR] pip install fallo.
        pause
        exit /b 1
    )
)

echo.
echo [tests] Python: %PYTHON%
echo.

"%PYTHON%" -m pytest tests %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% neq 0 (
    echo.
    echo [tests] Fallo con codigo %EXIT_CODE%
)

exit /b %EXIT_CODE%
