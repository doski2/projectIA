@echo off
cd /d "%~dp0"
echo.
echo  Aprendizaje online — BC conduce, teacher corrige, fine-tune cada vuelta
echo  Curriculo L1 -^> L5: domina cada etapa antes de avanzar
echo  Etapa: ultima guardada en v2\user_learn_settings.json
echo  Forzar L1: --stage l1_linea   Velocidad: --speed-target 20
echo  HTML: logs\learning\   Buffer: data\online_buffer.jsonl
echo.
pause
..\.venv\Scripts\python.exe src\learn_driver.py --reference src\refs\sugo_ai.json --model models\universal_bc.pt --open-report %*
