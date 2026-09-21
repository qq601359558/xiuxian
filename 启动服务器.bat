@echo off
chcp 65001 >nul
title Tiandao LAN Server
cd /d "%~dp0"

set PYTHON=%~dp0.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

echo ============================================
echo   TianDao YinGuoLu - LAN Server
echo ============================================
echo Project dir: %cd%
echo Local URL:   http://127.0.0.1:8765/
echo LAN URL:     http://YOUR-IP:8765/
echo Find IP:     ipconfig  -^> IPv4
echo Stop server: Ctrl+C in this window
echo --------------------------------------------

"%PYTHON%" -m server.run
if errorlevel 1 (
  echo.
  echo [ERROR] Server stopped. Check .venv and port 8765.
)
echo.
pause
