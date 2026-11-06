"""
极简局域网客户端（命令行）
用法：
  python -m server.client join 厉飞雨
  python -m server.client <token> /look
"""
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any, Dict

BASE = "http://127.0.0.1:8765"


def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if sys.argv[1] == "join":
        name = sys.argv[2] if len(sys.argv) > 2 else "散修"
        r = _post("/join", {"name": name})
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print("\n保存 token 后：python -m server.client <token> /look")
        return

    token = sys.argv[1]
    command = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "/look"
    r = _post("/action", {"token": token, "command": command})
    print(r.get("text") or r.get("error") or json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
