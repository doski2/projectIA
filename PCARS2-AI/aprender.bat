@echo off
cd /d "%~dp0"
echo.
echo  Aprendizaje online — BC conduce, teacher corrige, fine-tune cada vuelta
echo  Curriculo L1 -^> L7 por banda 20/30/40/50/60 km/h
echo  Etapa y banda: v2\user_learn_settings.json
echo  Forzar: --stage l1_linea --speed-band 20
echo  HTML: logs\learning\   Buffer: data\online_buffer.jsonl
echo.
pause
..\.venv\Scripts\python.exe src\learn_driver.py --reference src\refs\sugo_ai.json --model models\universal_bc.pt --open-report %*
