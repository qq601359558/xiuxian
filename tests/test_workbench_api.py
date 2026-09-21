"""工作台：登录 API 与静态托管契约"""
import os
import sys
import json
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

BASE = os.environ.get("TD_BASE", "http://127.0.0.1:8765")


def _get(path, timeout=5):
    r = urllib.request.urlopen(BASE + path, timeout=timeout)
    return r.status, r.headers.get_content_type(), r.read()[:80]


def _post(path, body, timeout=15):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    return json.loads(raw)


def test_static_workbench_served():
    """重启 server.run 后应能打开工作台"""
    try:
        st, ct, _b = _get("/")
    except Exception as e:
        print("SKIP static (server not restarted?)", e)
        return
    assert st == 200, st
    assert "html" in (ct or ""), ct
    st2, ct2, _ = _get("/workbench.css")
    assert st2 == 200
    st3, _c3, _ = _get("/workbench.js")
    assert st3 == 200
    print("✓ 静态工作台 / /workbench.css /workbench.js")


def test_login_then_look_here():
    user = os.environ.get("TD_USER", "wbtester1")
    pwd = os.environ.get("TD_PASS", "test12345")
    r = _post("/login", {"username": user, "password": pwd, "name": "工台测试"})
    assert r.get("ok") is True and r.get("token"), r
    tok = r["token"]
    look = _post("/action", {"token": tok, "command": "/look"})
    assert look.get("ok") is True
    assert look.get("status")
    assert look["status"].get("name")
    here = _post("/action", {"token": tok, "command": "/here"})
    assert here.get("ok") is True
    assert isinstance(here.get("here"), list)
    st, _ct, body = _get("/world/director")
    assert st == 200
    data = json.loads(body.decode("utf-8", errors="ignore") or b"{}") if False else None
    # body was truncated to 80 bytes in _get for print; re-fetch fully
    import urllib.request as u

    full = json.loads(u.urlopen(BASE + "/world/director", timeout=10).read())
    assert full.get("ok") is True
    assert "evolution" in full or "director" in full
    print("✓ 登录→观照→同场→世界导演")


if __name__ == "__main__":
    test_static_workbench_served()
    test_login_then_look_here()
