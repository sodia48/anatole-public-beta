@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Lance d'abord run_dashboard.bat pour creer l'environnement.
  pause
  exit /b 1
)
.venv\Scripts\python.exe alert_worker.py --interval 60
pause
