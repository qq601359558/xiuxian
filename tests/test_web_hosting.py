"""Web 静态托管（spec: web-static-hosting）：游戏服直接发玩家页面。

真实 HTTP 层验证：线程内起 GameHandler（随机端口），urllib / http.client 发请求。
- 白名单 5 路径 200 + 类型 + 内容与磁盘一致 + no-cache
- prototype.html 与路径穿越尝试一律 404、绝不返回文件内容
- 既有 API 不回归：/health JSON、/ailog JSON（不是 HTML 页面）
"""
import http.client
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# config 开关在首次 import 时冻结，必须先设环境再导入项目模块
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from http.server import ThreadingHTTPServer

from server.app import GameHandler
from server.world import WORLD

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


class _Server:
    """模块级单例：整文件共用一个随机端口的服。"""

    httpd = None
    port = None

    @classmethod
    def start(cls):
        if cls.httpd is None:
            cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
            cls.port = cls.httpd.server_address[1]
            t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
            t.start()
        return cls.port


def teardown_module(module):
    if _Server.httpd is not None:
        _Server.httpd.shutdown()
        _Server.httpd = None
    try:
        WORLD.stop_tick()
    except Exception:
        pass


def _get(path):
    """urllib GET；返回 (status, headers, body_bytes)，4xx 不抛异常。"""
    port = _Server.start()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def _get_raw(path):
    """http.client GET，路径原样发送（不做任何规范化），专测穿越。"""
    port = _Server.start()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        return r.status, r.getheaders(), r.read()
    finally:
        conn.close()


def test_root_serves_login_page():
    status, headers, body = _get("/")
    assert status == 200
    assert headers.get("Content-Type") == "text/html; charset=utf-8"
    text = body.decode("utf-8")
    # 登录页标志：标题 + 服务器地址输入框
    assert "<title>天道因果录</title>" in text
    assert 'id="serverUrl"' in text
    # 内容与磁盘文件逐字一致、长度头正确
    assert body == (WEB / "index.html").read_bytes()
    assert int(headers.get("Content-Length")) == len(body)
    print("✓ GET / 返回登录页且与磁盘一致")


def test_login_page_has_no_loopback_default():
    # 127.0.0.1 在玩家设备上永远指向玩家自己的设备，服不在那里：登录页不得再向
    # 玩家展示 127.0.0.1:8765（占位/页脚都算），默认阵枢是 NAS 域名（见下条测试）。
    _, _, body = _get("/")
    text = body.decode("utf-8")
    assert "127.0.0.1:8765" not in text
    assert "127.0.0.1" not in text
    print("✓ 登录页不含 127.0.0.1 默认地址")


def test_login_page_default_server_is_nas_domain():
    # 默认阵枢 = NAS 域名：登录页占位、实际登录路径 workbench.js、app.js 三处一致，
    # 打开即用，不用手动改；127.0.0.1:8765 只许留在 JS 的本机调试回落分支里，
    # 不得再成为无条件默认（`|| "http://127.0.0.1:8765"` 不得出现）。
    _, _, body = _get("/")
    text = body.decode("utf-8")
    assert 'placeholder="http://mn.20230803.xyz:8765"' in text
    _, _, wb = _get("/workbench.js")
    wb_text = wb.decode("utf-8")
    assert "http://mn.20230803.xyz:8765" in wb_text
    assert '|| "http://127.0.0.1:8765"' not in wb_text
    _, _, app = _get("/app.js")
    app_text = app.decode("utf-8")
    assert "http://mn.20230803.xyz:8765" in app_text
    assert '|| "http://127.0.0.1:8765"' not in app_text
    print("✓ 登录页默认阵枢为 NAS 域名 mn.20230803.xyz:8765")


def test_index_html_path():
    status, headers, body = _get("/index.html")
    assert status == 200
    assert headers.get("Content-Type") == "text/html; charset=utf-8"
    assert body == (WEB / "index.html").read_bytes()
    print("✓ GET /index.html 200 html")


def test_app_js_content_type_and_body():
    status, headers, body = _get("/app.js")
    assert status == 200
    assert headers.get("Content-Type") == "text/javascript; charset=utf-8"
    assert body == (WEB / "app.js").read_bytes()
    print("✓ GET /app.js 200 javascript 且与磁盘一致")


def test_style_css_content_type_and_body():
    status, headers, body = _get("/style.css")
    assert status == 200
    assert headers.get("Content-Type") == "text/css; charset=utf-8"
    assert body == (WEB / "style.css").read_bytes()
    print("✓ GET /style.css 200 css 且与磁盘一致")


def test_ailog_html_page():
    status, headers, body = _get("/ailog.html")
    assert status == 200
    assert headers.get("Content-Type") == "text/html; charset=utf-8"
    assert body == (WEB / "ailog.html").read_bytes()
    print("✓ GET /ailog.html 200 html 页面")


def test_static_responses_no_cache():
    for path in ("/", "/index.html", "/app.js", "/style.css", "/ailog.html"):
        status, headers, _ = _get(path)
        assert status == 200
        assert headers.get("Cache-Control") == "no-cache", path
    print("✓ 静态响应一律 Cache-Control: no-cache")


def test_prototype_not_served():
    status, _, body = _get("/prototype.html")
    assert status == 404
    assert body != (WEB / "prototype.html").read_bytes()
    print("✓ GET /prototype.html → 404（开发原型不对外）")


def test_path_traversal_blocked():
    config_bytes = (ROOT / "config.py").read_bytes()
    for raw_path in ("/../config.py", "/%2e%2e/config.py", "//etc/passwd",
                     "/..%2fconfig.py", "/web/../config.py",
                     "/%2E%2E/config.py", "/..%5cconfig.py", "/APP.JS"):
        status, _, body = _get_raw(raw_path)
        assert status in (400, 404), (raw_path, status)
        assert body != config_bytes, raw_path
        assert b"LAN_PORT" not in body, raw_path
    print("✓ 路径穿越尝试全部 404/400，无文件内容泄漏")


def test_health_api_unchanged():
    status, headers, body = _get("/health")
    assert status == 200
    assert headers.get_content_type() == "application/json"
    data = json.loads(body.decode("utf-8"))
    assert data["ok"] is True and data["service"] == "tiandao-lan"
    print("✓ /health 仍是 JSON 接口，未被静态托管影响")


def test_ailog_api_still_json_not_page():
    status, headers, body = _get("/ailog")
    assert status == 200
    assert headers.get_content_type() == "application/json"
    data = json.loads(body.decode("utf-8"))
    assert data["ok"] is True and "items" in data
    print("✓ /ailog 仍返回 JSON（不是 ailog.html 页面）")


def test_unknown_path_still_404():
    status, _, _ = _get("/no-such-thing")
    assert status == 404
    print("✓ 未知路径仍 404")
