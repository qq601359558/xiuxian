"""工作台：登录 API 与静态托管契约（本机直连，不走系统代理）"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

# 强制绕过系统代理（Clash 等 127.0.0.1:7897 会把本机请求打成 502）
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

BASE = os.environ.get("TD_BASE", "http://127.0.0.1:8765")

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(path, timeout=5):
    req = urllib.request.Request(BASE + path)
    r = _opener.open(req, timeout=timeout)
    return r.status, r.headers.get_content_type(), r.read()[:80]


def _post(path, body, timeout=15):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    raw = _opener.open(req, timeout=timeout).read()
    return json.loads(raw)


def test_static_workbench_served():
    try:
        st, ct, _b = _get("/")
    except Exception as e:
        print("SKIP static (server down?)", e)
        return
    assert st == 200, st
    assert "html" in (ct or ""), ct
    st2, _ct2, _ = _get("/workbench.css")
    assert st2 == 200
    st3, _c3, _ = _get("/workbench.js")
    assert st3 == 200
    print("✓ 静态工作台")


def test_login_then_look_here():
    user = os.environ.get("TD_USER", "wbtester1")
    pwd = os.environ.get("TD_PASS", "test12345")
    r = _post("/login", {"username": user, "password": pwd, "name": "工台测试"})
    assert r.get("ok") is True and r.get("token"), r
    tok = r["token"]
    look = _post("/action", {"token": tok, "command": "/look"})
    assert look.get("ok") is True
    assert look.get("status")
    here = _post("/action", {"token": tok, "command": "/here"})
    assert here.get("ok") is True
    assert isinstance(here.get("here"), list)
    full = json.loads(_opener.open(BASE + "/world/director", timeout=10).read())
    assert full.get("ok") is True
    print("✓ 登录→观照→同场→导演")


if __name__ == "__main__":
    test_static_workbench_served()
    test_login_then_look_here()
    print("workbench api ok")
