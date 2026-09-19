@echo off
cd /d "%~dp0"
echo.
echo  Autonomia total — solo red BC (teacher solo en emergencia)
echo  Usar tras aprender.bat etapa L5 o varias vueltas limpias en hybrid.
echo.
pause
..\.venv\Scripts\python.exe src\imitation_driver.py --universal --reference src\refs\sugo_ai.json --model models\universal_bc.pt --mode autonomous --open-report %*
