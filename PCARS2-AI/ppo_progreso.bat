@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
echo.
..\.venv\Scripts\python.exe src\ppo_progress.py %*
echo.
pause
