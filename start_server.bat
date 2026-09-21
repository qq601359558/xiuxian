@echo off
title TianDao LAN Server
cd /d "%~dp0"
set PYTHON=%~dp0.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python
echo ============================================
echo   TianDao YinGuoLu LAN Server
echo ============================================
echo Project: %cd%
echo Open in browser:
echo   http://127.0.0.1:8765/
echo   http://YOUR_IP:8765/
echo Find YOUR_IP with: ipconfig
echo Stop server: Ctrl+C in this window
echo --------------------------------------------
"%PYTHON%" -m server.run
echo.
echo Server process ended.
pause
