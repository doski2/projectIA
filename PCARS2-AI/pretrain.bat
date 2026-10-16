@echo off
setlocal
set PYTHONUTF8=1
set "SCRIPT_DIR=%~dp0"
set "PYTHON=%SCRIPT_DIR%..\.venv\Scripts\python.exe"

:: Referencia por defecto
if "%~1"=="" (
    set "REFERENCE=src\refs\sugo_ai.json"
) else (
    set "REFERENCE=%~1"
)

:: Modelo base opcional
set "BASE_ARG="
if not "%~2"=="" (
    set "BASE_ARG=--base %~2"
)

:: Salida
set "OUTPUT=models\pretrained"

if not exist "%REFERENCE%" (
    echo.
    echo [ERROR] No se encontro: %REFERENCE%
    pause
    exit /b 1
)

echo.
echo  PCARS2-AI - Behavioral Cloning
echo  Referencia : %REFERENCE%
echo  Salida     : %OUTPUT%.zip
echo.
pause

cd /d "%SCRIPT_DIR%"
"%PYTHON%" src\pretrain.py --reference "%REFERENCE%" --output "%OUTPUT%" --epochs 150 %BASE_ARG%

echo.
echo [OK] Pre-entrenamiento completado.
pause
