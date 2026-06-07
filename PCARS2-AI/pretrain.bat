@echo off
setlocal

:: ============================================================
::  PCARS2-AI — Pre-entrenamiento por Behavioral Cloning
::  Entrena la IA por imitación SIN abrir el juego (~5 min)
::
::  Uso:
::    pretrain.bat                        → usa referencia por defecto
::    pretrain.bat refs\mi_pista.json     → referencia específica
::    pretrain.bat refs\mi_pista.json models\base_driver → con modelo base
:: ============================================================

set PYTHON=C:\Users\doski\projectIA\.venv\Scripts\python.exe

:: Referencia por defecto
if "%~1"=="" (
    set REFERENCE=src\refs\formula_rookie__sugo__gpyf.json
) else (
    set REFERENCE=%~1
)

:: Modelo base opcional (para transferencia entre pistas)
set BASE_ARG=
if not "%~2"=="" (
    set BASE_ARG=--base %~2
)

:: Salida: siempre models\pretrained (lo detecta entrenar.bat)
set OUTPUT=models\pretrained

:: ---- Verificar referencia ----
if not exist "%REFERENCE%" (
    echo.
    echo [ERROR] No se encontro: %REFERENCE%
    pause
    exit /b 1
)

echo.
echo  PCARS2-AI — Behavioral Cloning
echo  Referencia : %REFERENCE%
echo  Salida     : %OUTPUT%.zip
echo  Epochs     : 150
echo.
echo  NO es necesario abrir el juego.
echo  Duracion estimada: 5-15 minutos segun CPU.
echo.
pause

cd /d "%~dp0"
"%PYTHON%" src\pretrain.py --reference "%REFERENCE%" --output "%OUTPUT%" --epochs 150 %BASE_ARG%

echo.
echo [OK] Pre-entrenamiento completado.
echo      Ahora ejecuta entrenar.bat — cargara el modelo pre-entrenado automaticamente.
echo.
pause
