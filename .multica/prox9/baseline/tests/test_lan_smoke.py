"""自测：线程内起服并请求 /join /action"""
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from http.server import ThreadingHTTPServer
from server.app import GameHandler


def main():
    httpd = ThreadingHTTPServer(("127.0.0.1", 8765), GameHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    def post(path, payload):
        req = urllib.request.Request(
            "http://127.0.0.1:8765" + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    health = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5).read()
    print("health", health.decode())
    j = post("/join", {"name": "自测修士"})
    print("join ok", j.get("name"), "token", j.get("token", "")[:8])
    a = post("/action", {"token": j["token"], "command": "/look"})
    print("look", a.get("ok"), (a.get("text") or "")[:80])
    w = post("/action", {"token": j["token"], "command": "/who"})
    print("who ok", w.get("ok"))
    httpd.shutdown()
    print("LAN smoke OK")


if __name__ == "__main__":
    main()
