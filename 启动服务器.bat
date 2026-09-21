@echo off
chcp 65001 >nul
title 天道因果录 · 局域网服
cd /d "%~dp0"

set PYTHON=%~dp0.venv\Scripts\python.exe
if not exist "%PYTHON%" (
  set PYTHON=python
)

echo ============================================
echo   天道因果录 · 启动局域网服
echo ============================================
echo 项目目录：%cd%
echo 本机访问：http://127.0.0.1:8765/
echo 局域网：http://&lt;本机IP&gt;:8765/  （可用 ipconfig 查看 IPv4）
echo 按 Ctrl+C 可停止服务器
echo --------------------------------------------

rem 避免本地模板干扰真 AI 时，可在此取消注释：
rem set ALLOW_LOCAL_AI=0
rem set AI_REQUIRED=1

"%PYTHON%" -m server.run
if errorlevel 1 (
  echo.
  echo [错误] 服务器异常退出。请检查：.venv 是否存在、端口 8765 是否被占用。
)
echo.
pause
