@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist .venv-ui\Scripts\pythonw.exe (
  py -3.11 -m venv .venv-ui
  if errorlevel 1 goto failed
  .venv-ui\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
start "" .venv-ui\Scripts\pythonw.exe desktop.py
exit /b 0
:failed
echo Please install Python 3.11 and retry. Setup failed.
pause
