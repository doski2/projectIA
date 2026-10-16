@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
..\.venv\Scripts\python.exe src\teaching_driver.py --mode record --universal --reference src\refs\sugo_ai.json --speed-target 20 --output data\universal_teacher.jsonl %*
