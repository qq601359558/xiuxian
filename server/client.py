"""
极简局域网客户端（命令行）
用法：
  python -m server.client join <账号>（提示输入密匙）
  python -m server.client join --token <token>
  python -m server.client <token> /look
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.error
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
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        with error:
            return json.loads(error.read().decode("utf-8"))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if sys.argv[1] == "join":
        parser = argparse.ArgumentParser(prog="python -m server.client join")
        parser.add_argument("username", nargs="?", help="仙籍账号，不是道号")
        parser.add_argument("password", nargs="?", help="密匙；建议省略并按提示输入")
        parser.add_argument("--token", help="凭既有会话续玩")
        args = parser.parse_args(sys.argv[2:])
        if args.token:
            if args.username or args.password:
                parser.error("token 与账号密匙只能选择一种")
            payload = {"token": args.token}
        elif args.username:
            password = args.password if args.password is not None else getpass.getpass("神识密匙：")
            payload = {"username": args.username, "password": password}
        else:
            parser.error("需要账号与密匙，或 --token")
        r = _post("/join", payload)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        if r.get("token"):
            print("\n保存 token 后：python -m server.client <token> /look")
        return

    token = sys.argv[1]
    command = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "/look"
    r = _post("/action", {"token": token, "command": command})
    print(r.get("text") or r.get("error") or json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
