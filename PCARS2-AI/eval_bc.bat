@echo off
cd /d "%~dp0"
..\.venv\Scripts\python.exe src\eval_universal.py --dataset data\universal_teacher.jsonl --model models\universal_bc.pt %*
