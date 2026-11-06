@echo off
chcp 65001 >nul
title 《天道因果录》- 文字修仙 MUD
cd /d "%~dp0"
echo 正在进入《天道因果录》九州大世界...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cli\main.py
) else (
    echo 未找到 .venv，先执行: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    echo 本次改用系统 python 启动...
    python cli\main.py
)
pause
