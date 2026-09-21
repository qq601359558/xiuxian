from pathlib import Path

lines = [
    "@echo off",
    "title TianDao LAN Server",
    r'cd /d "%~dp0"',
    r'set PYTHON=%~dp0.venv\Scripts\python.exe',
    r'if not exist "%PYTHON%" set PYTHON=python',
    "echo ============================================",
    "echo   TianDao YinGuoLu LAN Server",
    "echo ============================================",
    "echo Project: %cd%",
    "echo Open in browser:",
    "echo   http://127.0.0.1:8765/",
    "echo   http://YOUR_IP:8765/",
    "echo Find YOUR_IP with: ipconfig",
    "echo Stop server: Ctrl+C in this window",
    "echo --------------------------------------------",
    r'"%PYTHON%" -m server.run',
    "echo.",
    "echo Server process ended.",
    "pause",
]
body = "\r\n".join(lines) + "\r\n"
root = Path(r"D:\codex\xiuxian")
for name in ("start_server.bat", "启动服务器.bat"):
    path = root / name
    path.write_bytes(body.encode("ascii"))
    print(name, "bytes", path.stat().st_size)
print("---")
print((root / "start_server.bat").read_text(encoding="ascii"))
