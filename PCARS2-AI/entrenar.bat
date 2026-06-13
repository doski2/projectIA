@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  PCARS2-AI — Lanzador de entrenamiento
::
::  El coche y la pista se detectan AUTOM\u00c1TICAMENTE desde
::  la telemetr\u00eda UDP. Simplemente \u00e9ntralo en pista antes de
::  lanzar el entrenamiento.
::
::  Uso:
::    entrenar.bat                          \u2190 referencia y pasos por defecto
::    entrenar.bat  refs\mi_ref.json        \u2190 referencia personalizada
::    entrenar.bat  refs\mi_ref.json  500000  \u2190 + n\u00famero de pasos
::
::  Override manual (raro, solo si la detecci\u00f3n falla):
::    Edita las variables CAR_OVERRIDE y TRACK_OVERRIDE m\u00e1s abajo.
::
::  Estructura de modelos generada autom\u00e1ticamente:
::    models\base\                       \u2190 entrenamiento general
::    models\{coche}__{pista}\           \u2190 combo detectado
:: ============================================================

set SCRIPT_DIR=%~dp0
set "PYTHON=%SCRIPT_DIR%..\.venv\Scripts\python.exe"

:: ---- Argumentos ----
if "%~1"=="" (
    set REFERENCE=src\refs\sugo_ai.json
) else (
    set REFERENCE=%~1
)

if "%~2"=="" (
    set TIMESTEPS=500000
) else (
    set TIMESTEPS=%~2
)

:: ---- Argumentos extra (todos los que vienen a partir del 3º) ----
shift
shift
set EXTRA_ARGS=
:_extra_loop
if "%~1"=="" goto _extra_done
set EXTRA_ARGS=%EXTRA_ARGS% %~1
shift
goto _extra_loop
:_extra_done

:: ---- Override manual (dejar vac\u00edo para usar auto-detecci\u00f3n) ----
set CAR_OVERRIDE=
set TRACK_OVERRIDE=

set CAR_ARG=
set TRACK_ARG=
if not "%CAR_OVERRIDE%"==""   set CAR_ARG=--car %CAR_OVERRIDE%
if not "%TRACK_OVERRIDE%"=="" set TRACK_ARG=--track %TRACK_OVERRIDE%

:: ---- Verificar que existe el archivo de referencia ----
if not exist "%REFERENCE%" (
    echo.
    echo [ERROR] No se encontro el archivo de referencia: %REFERENCE%
    echo Graba primero una vuelta con:
    echo   %PYTHON% src\reference_recorder.py --source ai --laps 3 --output src\refs\referencia.json
    echo.
    pause
    exit /b 1
)

:: ---- Mostrar info y arrancar ----
echo.
echo  PCARS2-AI Entrenamiento
echo  Referencia : %REFERENCE%
echo  Timesteps  : %TIMESTEPS%
echo  Coche+Pista: se detecta autom\u00e1ticamente al arrancar (30s)
echo  Modelos    : models\{combo detectado}\
echo.
echo  Asegurate de que Project CARS 2 esta corriendo EN PISTA antes de continuar.
echo.
pause

cd /d "%SCRIPT_DIR%"
set PYTHONUNBUFFERED=1
"%PYTHON%" -u src\main.py --reference "%REFERENCE%" --timesteps %TIMESTEPS% %CAR_ARG% %TRACK_ARG% %EXTRA_ARGS%

echo.
echo [PCARS2-AI] Entrenamiento finalizado.
pause
