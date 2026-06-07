@echo off
:: ============================================================
::  PCARS2-AI — Promover modelo actual como BASE
::
::  Copia el modelo final de la carpeta models\ (formato antiguo,
::  plano) o el último checkpoint al directorio models\base\
::  y lo registra como el punto de partida para nuevos combos.
::
::  Uso:
::    promover_base.bat
::    promover_base.bat  models\pcars2_ppo_1074564_steps.zip
:: ============================================================
setlocal

set PYTHON=C:\Users\doski\projectIA\.venv\Scripts\python.exe
set TARGET=models\base

:: Crear carpeta destino si no existe
if not exist "%TARGET%" mkdir "%TARGET%"

:: ---- Determinar qué modelo promover ----
if not "%~1"=="" (
    :: Modelo especificado manualmente
    set SOURCE=%~1
    goto :copiar
)

:: Buscar en este orden:
:: 1. models\pcars2_ppo_final.zip  (sesión antigua plana)
:: 2. models\base\pcars2_base_final.zip  (ya hay un base, no hacer nada)
:: 3. Checkpoint más reciente en models\ raíz

if exist "models\pcars2_ppo_final.zip" (
    set SOURCE=models\pcars2_ppo_final.zip
    goto :copiar
)

if exist "models\base\pcars2_base_final.zip" (
    echo.
    echo [INFO] Ya existe un modelo base: models\base\pcars2_base_final.zip
    echo Si quieres reemplazarlo, especifica el modelo manualmente:
    echo   promover_base.bat models\pcars2_ppo_final.zip
    echo.
    pause
    exit /b 0
)

:: Checkpoint más reciente en raíz de models\
set LAST_FILE=
set LAST_STEPS=0
for /f "tokens=*" %%f in ('dir /b /o-n "models\pcars2_ppo_*_steps.zip" 2^>nul') do (
    for /f "tokens=3 delims=_" %%n in ("%%~nf") do (
        if %%n GTR %LAST_STEPS% (
            set LAST_STEPS=%%n
            set LAST_FILE=models\%%f
        )
    )
)

if not "%LAST_FILE%"=="" (
    set SOURCE=%LAST_FILE%
    goto :copiar
)

echo.
echo [ERROR] No se encontro ningun modelo en models\
echo Asegurate de haber entrenado al menos una sesion base.
echo.
pause
exit /b 1

:copiar
echo.
echo  Promoviendo como modelo BASE:
echo    Origen : %SOURCE%
echo    Destino: %TARGET%\pcars2_base_final.zip
echo.
echo  Este modelo sera el punto de partida para nuevos combos coche+pista.
echo.
pause

copy /y "%SOURCE%" "%TARGET%\pcars2_base_final.zip"

echo.
echo [OK] Modelo base guardado en: %TARGET%\pcars2_base_final.zip
echo.
echo Para entrenar un combo nuevo partiendo de este base:
echo   entrenar.bat refs\mi_referencia.json 500000 nombre_coche nombre_pista
echo.
pause
