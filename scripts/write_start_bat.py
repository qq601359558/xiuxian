from pathlib import Path

server_bat = """@echo off
title TianDao LAN Server
cd /d \"%~dp0\"

set PYTHON=%~dp0.venv\\Scripts\\python.exe
if not exist \"%PYTHON%\" set PYTHON=python

echo ============================================
echo   TianDao YinGuoLu LAN Server
echo ============================================
echo Project: %cd%
echo Open in browser:
echo   http://127.0.0.1:8765/
echo   http://YOUR_IP:8765/
echo Find YOUR_IP with:  ipconfig
echo Stop: Ctrl+C in this window
echo --------------------------------------------
\"%PYTHON%\" -m server.run
echo.
echo Server stopped. Port 875 may be busy if restart fails.
pause
"""

alias_bat = """@echo off
title TianDao LAN Server
cd /d \"%~dp0\"
set PYTHON=%~dp0.venv\\Scripts\\python.exe
if not exist \"%PYTHON%\" set PYTHON=python
echo Starting TianDao LAN Server...
echo Browser: http://127.0.0.1:8765/
\"%PYTHON%\" -m server.run
pause
"""

root = Path(r"D:\\codex\\xiuxian")
# ASCII-only .bat — safest for double-click on any Windows code page
(root / "start_server.bat").write_text(alias_bat, encoding="ascii", newline="\\r\\n")
# Chinese name file: same ASCII body so cmd never chokes
(root / "启动服务器.bat").write_text(alias_bat, encoding="ascii", newline="\\r\\n")
print("start_server.bat:")
print((root / "start_server.bat").read_text(encoding="ascii"))
print("bytes", (root / "start_server.bat").stat().st_size)
