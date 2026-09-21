from pathlib import Path

lines = Path(r"D:\codex\xiuxian\server\world.py").read_text(encoding="utf-8").splitlines()
# 打印 1490-2245 里所有 if action 的行号与缩进
for i in range(1480, 2250):
    if i > len(lines):
        break
    s = lines[i - 1]
    if "if action" in s or "elif action" in s or "return {" in s and "未知指令" in s:
        indent = len(s) - len(s.lstrip(" "))
        print(f"{i:4d} ind={indent:2d} {s.strip()[:80]}")
