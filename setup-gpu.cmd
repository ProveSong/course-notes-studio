@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-gpu.ps1"
if errorlevel 1 (echo Setup failed. See the error above.) else (echo Setup completed.)
pause
