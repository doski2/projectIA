@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
..\.venv\Scripts\python.exe src\teaching_driver.py --mode teacher --phase f1_linea --reference src\refs\sugo_ai.json --open-report %*
