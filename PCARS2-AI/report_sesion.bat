@echo off
cd /d "%~dp0"
if "%~1"=="" (
  echo Uso: report_sesion.bat logs\teaching\sesion.jsonl
  exit /b 1
)
..\.venv\Scripts\python.exe src\session_report.py %1 --force --open
