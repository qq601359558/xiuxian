"""灰度运维自检：GET /health 应回显版本与 AI 状态（批次 A3）"""
import json
import os
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 与仓库其他测试一致：config 的开关在首次 import 时冻结，必须先设环境再导入项目模块；
# NPC_TICK_INTERVAL=0 避免 WORLD 后台 tick 线程干扰其他用例。
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from http.server import ThreadingHTTPServer

from config import VERSION
from server.app import GameHandler


def test_health_reports_version_and_ai_status():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
            body = json.loads(r.read().decode())
    finally:
        httpd.shutdown()
    # 旧字段兼容
    assert body["ok"] is True
    assert body["service"] == "tiandao-lan"
    # 灰度新增字段
    assert body["version"] == VERSION
    assert isinstance(body["ai_available"], bool)
    assert isinstance(body["ai_required"], bool)
    assert isinstance(body["allow_local_ai"], bool)
    assert isinstance(body["online"], int) and body["online"] >= 0
    print(f"✓ /health 版本与 AI 状态齐全：{body}")
