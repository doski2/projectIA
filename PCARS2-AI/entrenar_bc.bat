@echo off
cd /d "%~dp0"
echo.
echo  F5 paso 2 — Entrenar BC universal desde record.bat
echo  Entrada: data\universal_teacher.jsonl
echo  Salida : models\universal_bc.pt
echo.
pause
..\.venv\Scripts\python.exe src\pretrain_universal.py --dataset data\universal_teacher.jsonl --output models\universal_bc.pt %*
