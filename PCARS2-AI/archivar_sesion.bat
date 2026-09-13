@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  PCARS2-AI — Archivar modelos y logs antes de empezar desde 0
::
::  Uso:
::    archivar_sesion.bat
::    archivar_sesion.bat formula_rookie__sugo
:: ============================================================

set SCRIPT_DIR=%~dp0
set COMBO=%~1
if "%COMBO%"=="" set COMBO=formula_rookie__sugo

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set STAMP=%%i

set MODEL_SRC=%SCRIPT_DIR%models\%COMBO%
set LOG_SRC=%SCRIPT_DIR%logs\%COMBO%
set MODEL_DST=%SCRIPT_DIR%models\%COMBO%_archive_%STAMP%
set LOG_DST=%SCRIPT_DIR%logs\%COMBO%_archive_%STAMP%

echo.
echo  PCARS2-AI — Archivar sesion anterior
echo  Combo : %COMBO%
echo  Fecha : %STAMP%
echo.

if exist "%MODEL_SRC%" (
    echo  Moviendo modelos:
    echo    %MODEL_SRC%
    echo    -^> %MODEL_DST%
    move "%MODEL_SRC%" "%MODEL_DST%"
) else (
    echo  [OK] No hay carpeta de modelos: %MODEL_SRC%
)

if exist "%LOG_SRC%" (
    echo  Moviendo logs:
    echo    %LOG_SRC%
    echo    -^> %LOG_DST%
    move "%LOG_SRC%" "%LOG_DST%"
) else (
    echo  [OK] No hay carpeta de logs: %LOG_SRC%
)

if exist "%SCRIPT_DIR%models\pretrained.zip" (
    set PRE_DST=%SCRIPT_DIR%models\pretrained_archive_%STAMP%.zip
    echo  Moviendo pretrained.zip -^> %PRE_DST%
    move "%SCRIPT_DIR%models\pretrained.zip" "%PRE_DST%"
)

echo.
echo  Listo. Abre gui.bat y entrena con checkpoint vacio (--fresh).
echo.
pause
