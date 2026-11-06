"""自测：线程内起服并注册、凭 token 续玩、执行行动。"""
import json
import sys
import threading
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from http.server import ThreadingHTTPServer
from server.app import GameHandler


def main():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def post(path, payload):
        req = urllib.request.Request(
            base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(req, timeout=30) as r:
            return json.loads(r.read().decode())

    try:
        with opener.open(base + "/health", timeout=5) as response:
            assert json.loads(response.read())["ok"] is True
        registered = post("/register", {
            "username": "smoke_" + uuid.uuid4().hex[:8],
            "password": uuid.uuid4().hex, "name": "自测修士",
        })
        assert registered["ok"] is True
        joined = post("/join", {"token": registered["token"]})
        assert joined["ok"] is True and joined["character_id"] == registered["character_id"]
        action = post("/action", {"token": joined["token"], "command": "/look"})
        assert action["ok"] is True
        who = post("/action", {"token": joined["token"], "command": "/who"})
        assert who["ok"] is True
        print("health/register/token join/look/who OK")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
    print("LAN smoke OK")


if __name__ == "__main__":
    main()
