from pathlib import Path

server_bat = """@echo off
chcp 65001 >nul
title Tiandao LAN Server
cd /d \"%~dp0\"

set PYTHON=%~dp0.venv\\Scripts\\python.exe
if not exist \"%PYTHON%\" set PYTHON=python

echo ============================================
echo   TianDao YinGuoLu - LAN Server
echo ============================================
echo Project dir: %cd%
echo Local URL:   http://127.0.0.1:8765/
echo LAN URL:     http://YOUR-IP:8765/
echo Find IP:     ipconfig  -^> IPv4
echo Stop server: Ctrl+C in this window
echo --------------------------------------------

\"%PYTHON%\" -m server.run
if errorlevel 1 (
  echo.
  echo [ERROR] Server stopped. Check .venv and port 8765.
)
echo.
pause
"""

alias_bat = """@echo off
chcp 65001 >nul
call \"%~dp0启动服务器.bat\"
"""

root = Path(r"D:\\codex\\xiuxian")
# write UTF-8 with BOM so Windows cmd + chcp 65001 reads Chinese path name file consistently
(root / "启动服务器.bat").write_bytes(server_bat.encode("utf-8-sig"))
(root / "start_server.bat").write_bytes(alias_bat.encode("utf-8-sig"))
print("ok", (root / "启动服务器.bat").stat().st_size)
print("--- preview ---")
print((root / "启动服务器.bat").read_text(encoding="utf-8-sig"))
