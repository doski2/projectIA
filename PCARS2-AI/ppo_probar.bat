@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
echo.
echo  PPO anclado al BC - PRIMERA PRUEBA (parte de models\ppo_universal_base.zip)
echo  Regenerar el modelo base desde el BC: python src\ppo_bootstrap.py
echo  Observacion universal_v1, compensacion de volante, objetivo 60 km/h
echo  Metricas: metricas.csv en la carpeta de logs   TensorBoard: logs\ 
echo  Ctrl+C guarda el modelo y para.
echo.
pause
..\.venv\Scripts\python.exe src\main.py --reference src\refs\sugo_ai.json --obs-schema universal_v1 --steer-comp --base-model models\ppo_universal_base.zip --speed-target-kmh 60 --frame-skip 1 --warmup-steps 30 --timesteps 50000 --save-freq 5000 %*
