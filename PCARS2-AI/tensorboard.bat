@echo off
set PYTHONUTF8=1
:: ============================================================
::  PCARS2-AI — TensorBoard
::  Abre el dashboard en http://localhost:6006
:: ============================================================

set PYTHON=C:\Users\doski\projectIA\.venv\Scripts\python.exe

echo.
echo  Iniciando TensorBoard...
echo  Abre en el navegador: http://localhost:6006
echo  Ctrl+C para detener.
echo.

%PYTHON% -m tensorboard.main --logdir logs\formula_rookie__sugo

pause
