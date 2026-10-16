@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
..\.venv\Scripts\python.exe src\imitation_driver.py --universal --reference src\refs\sugo_ai.json --model models\universal_bc.pt --mode bc_drive --open-report %*
