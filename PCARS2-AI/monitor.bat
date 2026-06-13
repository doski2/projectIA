@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PYTHON=%SCRIPT_DIR%..\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Entorno virtual no encontrado en: %SCRIPT_DIR%..\.venv
    pause
    exit /b 1
)

set PYTHONUNBUFFERED=1
"%PYTHON%" -u "%SCRIPT_DIR%src\monitor.py" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INFO] El monitor se ha detenido. 
    echo        Si acabas de borrar los logs, es normal: no hay nada que monitorizar aun.
    pause
)
