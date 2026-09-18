@echo off
cd /d "%~dp0"
..\.venv\Scripts\python.exe src\teaching_driver.py --mode teacher --reference src\refs\sugo_ai.json --speed-target 20 %*
