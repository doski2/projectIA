@echo off
cd /d "%~dp0"
..\.venv\Scripts\python.exe src\teaching_driver.py --mode teacher --phase f3_frenar --reference src\refs\sugo_ai.json --open-report %*
