@echo off
cd /d "%~dp0"
set "PY=.build_venv_py313\Scripts\python.exe"
if not exist "%PY%" set "PY=.build_venv_py38_win7\Scripts\python.exe"
if not exist "%PY%" set "PY=.venv\Scripts\python.exe"
echo Launching Dazzle via %PY%
"%PY%" dev_launch.py
echo.
echo ==== Dazzle closed (exit code %errorlevel%) ====
pause
