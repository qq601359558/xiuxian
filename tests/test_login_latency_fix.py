"""login-latency-fix 验收测试（Spec §4：A2/A3/A4/A5/A6/A7/A8/A9/A10/A11/A12/A13/A14）。

约定：
- DB 一律用 tmp_path 隔离（monkeypatch storage.db.DB_PATH），不碰真实存档。
- server.log 是进程共享的运行日志：读日志前记字节偏移，只断言新增行。
- A6/A7/A10 按 Spec 修订 R1（有界获取 + 锁外回退）验收：锁被他线程持有时，
  登录/注册 2 秒内返回 200 回退快照或 503 SERVER_BUSY，永不挂起、永不假成功。
  原字面测试（锁被持有时仍返回完整 token）已删除，不再以 xfail 保留。
"""
import os

os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")
os.environ.setdefault("USE_CCSWITCH", "0")
os.environ.setdefault("LLM_API_KEY", "")

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

import config

config.ALLOW_LOCAL_AI = True
config.AI_REQUIRED = False

from ai import gateway
from server.log import LOG_PATH
from server.world import World
from storage.db import (
    CharacterRepository,
    ChronicleRepository,
    LegacyRepository,
    init_db,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_breaker():
    gateway.breaker_reset()
    yield
    gateway.breaker_reset()


@pytest.fixture()
def world(tmp_path, monkeypatch):
    test_db = tmp_path / "latency.db"
    monkeypatch.setattr("storage.db.DB_PATH", test_db)
    init_db()
    w = World(auto_tick=False)
    yield w
    w.stop_tick()


def _log_lines_since(offset: int):
    if not LOG_PATH.exists():
        return []
    raw = LOG_PATH.read_bytes()[offset:]
    out = []
    for line in raw.decode("utf-8", "replace").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


@pytest.fixture()
def log_offset():
    return LOG_PATH.stat().st_size if LOG_PATH.exists() else 0


def _db_count(db_path, sql, params=()):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


class _FakeResp:
    """OpenAI 兼容响应：content 为 message.content 的原始文本。"""

    def __init__(self, status_code=200, content="", text=""):
        self.status_code = status_code
        self._content = content
        self.text = text or content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _AnthropicResp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text
        self._data = {"content": [{"type": "text", "text": text}]}

    def json(self):
        return self._data


def _kill(world_obj, uid, name, stones=100):
    """把指定账号角色置为已死（death_settled=False），返回角色。"""
    from core.models import CharacterStatus

    char = CharacterRepository.get_by_user_id(uid)
    assert char is not None
    char.status = CharacterStatus.DEAD
    char.death_cause = "测试坐化"
    char.spirit_stones = stones
    char.death_settled = False
    CharacterRepository.save(char)
    return char


# ==================== A2：二次尝试仅限 HTTP 400 ====================

def test_chat_json_timeout_calls_once(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(timeout)
        raise httpx.ConnectTimeout("slow relay")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") is None
    assert len(calls) == 1


def test_chat_json_http500_calls_once(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _FakeResp(500, text="err")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") is None
    assert len(calls) == 1


def test_chat_json_http400_retries_once_without_format(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return _FakeResp(400, text="bad format")
        return _FakeResp(200, '{"line": "通"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") == {"line": "通"}
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_chat_json_http404_calls_once(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        return _FakeResp(404, text="nope")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") is None
    assert len(calls) == 1


def test_chat_json_parse_fail_calls_once(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        return _FakeResp(200, "not json at all")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") is None
    assert len(calls) == 1

# ==================== A3：通道上限无架空（CC Switch） ====================

def _cc_on(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", True)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    monkeypatch.setattr(
        gateway, "ccswitch_runtime",
        lambda: {"base": "http://ccswitch.local", "model": "m", "token": "t"},
    )


def test_ccswitch_timeout_no_longer_floored_at_30(monkeypatch):
    _cc_on(monkeypatch)
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["timeout"] = timeout
        return _AnthropicResp(200, '{"line": "通"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") == {"line": "通"}
    assert seen["timeout"] == config.LLM_TIMEOUT_SECONDS
    assert seen["timeout"] == 12.0


def test_ccswitch_401_retries_once_with_bearer(monkeypatch):
    _cc_on(monkeypatch)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(dict(headers or {}))
        if len(calls) == 1:
            return _AnthropicResp(401)
        return _AnthropicResp(200, '{"line": "通"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") == {"line": "通"}
    assert len(calls) == 2
    assert calls[1].get("Authorization", "").startswith("Bearer ")


def test_ccswitch_500_calls_once(monkeypatch):
    _cc_on(monkeypatch)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "")  # 关掉 OpenAI 兜底，只量 CC 通道本身
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        return _AnthropicResp(500)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") is None
    assert len(calls) == 1


def test_ccswitch_timeout_calls_once(monkeypatch):
    _cc_on(monkeypatch)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "")  # 关掉 OpenAI 兜底，只量 CC 通道本身
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        raise httpx.ConnectTimeout("slow relay")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert gateway._chat_json("hi") is None
    assert len(calls) == 1


# ==================== A4：单次 AI 最坏耗时约 15 秒 ====================

def test_chat_json_blackhole_returns_within_budget(monkeypatch):
    """黑洞式慢速 stub：真实 httpx 超时 2 秒即返回 None，墙钟远小于 15 秒。"""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Blackhole(BaseHTTPRequestHandler):
        def do_POST(self):
            time.sleep(30)

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Blackhole)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
        monkeypatch.setattr(gateway, "LLM_API_BASE", f"http://127.0.0.1:{httpd.server_port}")
        monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
        t0 = time.time()
        assert gateway._chat_json("hi", timeout=2.0) is None
        assert time.time() - t0 < 15.0
    finally:
        httpd.shutdown()
        httpd.server_close()


# ==================== A13：熔断器 ====================

def test_breaker_opens_after_3_timeouts_and_short_circuits(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        raise httpx.ConnectTimeout("slow relay")

    monkeypatch.setattr(httpx, "post", fake_post)
    for _ in range(3):
        assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    assert len(calls) == 3
    t0 = time.time()
    assert gateway._chat_json("hi") is None
    assert time.time() - t0 < 1.0
    assert len(calls) == 3  # 熔断后不再发网络请求
    assert gateway._chat_json("hi") is None
    assert len(calls) == 3


def test_breaker_http4xx_does_not_count(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        if len(calls) <= 6:
            return _FakeResp(400, text="bad")
        return _FakeResp(200, '{"line": "通"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    # 3 次 400（每次重试一次，共 6 个请求）都不计入熔断
    for _ in range(3):
        assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "closed"
    assert gateway._chat_json("hi") == {"line": "通"}


def test_breaker_half_open_success_closes(monkeypatch, log_offset):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    monkeypatch.setattr(gateway, "NPC_TICK_INTERVAL_SECONDS", 0.2)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        if len(calls) <= 3:
            raise httpx.ConnectTimeout("slow relay")
        return _FakeResp(200, '{"line": "通"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    for _ in range(3):
        assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    time.sleep(0.3)  # 熔断期满 → 半开
    assert gateway._chat_json("hi") == {"line": "通"}
    assert gateway.breaker_state()["state"] == "closed"
    assert gateway.breaker_state()["failures"] == 0
    kinds = [r.get("msg") for r in _log_lines_since(log_offset) if r.get("kind") == "GATE"]
    assert "breaker_open" in kinds
    assert "breaker_half_open" in kinds
    assert "breaker_closed" in kinds


def test_breaker_half_open_failure_reopens(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    monkeypatch.setattr(gateway, "NPC_TICK_INTERVAL_SECONDS", 0.2)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        raise httpx.ConnectTimeout("slow relay")

    monkeypatch.setattr(httpx, "post", fake_post)
    for _ in range(3):
        assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    time.sleep(0.3)
    assert gateway._chat_json("hi") is None  # 半开探测失败
    assert gateway.breaker_state()["state"] == "open"
    assert gateway._chat_json("hi") is None  # 再次短路，不发请求
    assert len(calls) == 4


def test_breaker_shared_by_chat_text(monkeypatch):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        raise httpx.ConnectTimeout("slow relay")

    monkeypatch.setattr(httpx, "post", fake_post)
    for _ in range(3):
        assert gateway._chat_text("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    assert gateway._chat_json("hi") is None  # 同一熔断器，_chat_json 也被短路
    assert len(calls) == 3


# ==================== A12：Tick 计时日志 ====================

def test_tick_once_logs_phases(world, monkeypatch, log_offset):
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    world._tick_once()
    rows = [r for r in _log_lines_since(log_offset) if r.get("kind") == "TICK"]
    starts = [r for r in rows if r.get("msg") == "tick_start"]
    ends = [r for r in rows if r.get("msg") == "tick_end"]
    assert len(starts) == 1 and len(ends) == 1
    phases = ends[0].get("phases") or {}
    assert {"agenda", "director", "auction"} <= set(phases)
    assert isinstance(ends[0].get("hold_ms"), int)


def test_tick_phase_error_logged_and_tick_continues(world, monkeypatch, log_offset):
    import core.faction as faction_mod

    monkeypatch.setattr(faction_mod, "tick_world", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    world._tick_once()
    rows = [r for r in _log_lines_since(log_offset) if r.get("kind") == "TICK"]
    errs = [r for r in rows if r.get("msg") == "tick_phase_error" and r.get("phase") == "faction"]
    assert len(errs) == 1
    assert [r for r in rows if r.get("msg") == "tick_end"]


def test_tick_ai_timeouts_capped_at_12(world, monkeypatch):
    """tick 内每次 AI 调用的超时都不超过 12 秒（A5 的预算依据）。

    把 ai_available mock 成 True，迫使 tick 各阶段真实走网关（fake 只记
    超时、不发网络），再断言全部超时 <= 12。
    """
    seen = []

    def fake_chat_json(prompt, timeout=None):
        seen.append(timeout)
        return None

    monkeypatch.setattr(gateway, "_chat_json", fake_chat_json)
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "ai_available", lambda: True)
    monkeypatch.setattr(config, "ai_available", lambda: True)
    world._tick_once()
    assert seen, "tick 应至少发起一次 AI 调用"
    assert all(t is not None and t <= 12.0 for t in seen), seen


# ==================== A11：HTTP 计时日志 ====================

def test_http_requests_logged_without_secrets(tmp_path, monkeypatch, log_offset):
    import json as _json
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from server.app import GameHandler

    test_db = tmp_path / "http.db"
    monkeypatch.setattr("storage.db.DB_PATH", test_db)
    init_db()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    secret = "SECRET-PW-9f3a7"
    try:
        with opener.open(base + "/health", timeout=5) as r:
            assert _json.loads(r.read())["ok"] is True
        req = urllib.request.Request(
            base + "/login",
            data=_json.dumps({"username": "nobody", "password": secret}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            opener.open(req, timeout=5)
        except urllib.error.HTTPError as e:
            assert e.code == 401
    finally:
        httpd.shutdown()
        httpd.server_close()
    rows = [r for r in _log_lines_since(log_offset) if r.get("kind") == "HTTP"]
    by_path = {(r.get("method"), r.get("path")): r for r in rows}
    assert ("GET", "/health") in by_path
    assert ("POST", "/login") in by_path
    assert by_path[("GET", "/health")]["status"] == 200
    assert by_path[("POST", "/login")]["status"] == 401
    for r in rows:
        assert isinstance(r.get("duration_ms"), int)
        assert secret not in _json.dumps(r, ensure_ascii=False)



# ==================== A6/A7：持锁登录 / 注册 ====================

def _run_in_thread(fn):
    box = {}

    def _wrap():
        try:
            box["result"] = fn()
        except Exception as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=_wrap, daemon=True)
    t.start()
    return t, box


def test_login_waits_only_for_short_critical_section(world):
    s1 = world.join("短临界", user_id="lock_short")
    assert s1.get("token")

    def holder():
        with world.lock:
            time.sleep(0.3)

    ht = threading.Thread(target=holder, daemon=True)
    t0 = time.time()
    ht.start()
    t, box = _run_in_thread(lambda: world.join("短临界", user_id="lock_short"))
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert time.time() - t0 < 2.0
    assert box.get("result", {}).get("token")

# ==================== A7：新号 first-night 异步 ====================

_TONGCHANG = "\u3010\u540c\u573a\u3011"
_TIANDAO = "\u3010\u5929\u9053\u3011"


def test_register_returns_pending_and_first_night_completes(world):
    s = world.join("新号异步", user_id="fn_async_1")
    assert s.get("token")
    assert s.get("is_new_life") is True
    assert s.get("first_night") == {"pending": True}
    assert "初入道" in s.get("newbie_feed", "")
    assert _TONGCHANG not in s.get("newbie_feed", "")
    assert _TIANDAO not in s.get("newbie_feed", "")
    cid = s["character_id"]
    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        status = world.first_night_status(cid)
        if status in ("done", "failed"):
            break
        time.sleep(0.2)
    assert status in ("done", "failed")
    if status == "done":
        recent = ChronicleRepository.get_recent(10)
        assert any(_TONGCHANG in r or _TIANDAO in r for r in recent)


def test_join_seeds_roster_synchronously_before_first_night_ai(tmp_path, monkeypatch):
    """A7 补充 / Spec §2.2.3：seed_roster() 调用位置语义不改动——新号 join
    同步返回前花名册已落盘，只把两次强制 AI 留给后台线程。

    回归锚点：若 seed_roster 被整个搬进后台线程，注册返回后角色表仍在
    变化，test_auth_hardening 的 before/after 快照会随机失败。
    """
    test_db = tmp_path / "latency_seed.db"
    monkeypatch.setattr("storage.db.DB_PATH", test_db)
    init_db()
    monkeypatch.setattr(World, "_seed_npcs", lambda self: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    w = World(auto_tick=False)
    try:
        assert CharacterRepository.get_by_user_id("npc_wj_07") is None
        res = w.join("同步播种客", "seed_sync_uid_1")
        assert res["is_new_life"] is True
        assert res.get("first_night") == {"pending": True}
        seeded = CharacterRepository.get_by_user_id("npc_wj_07")
        assert seeded is not None and seeded.name == "小环"
    finally:
        w.stop_tick()


def test_register_first_night_ai_failure_does_not_block(world, monkeypatch):
    from core import npc_proactive as npp
    from core import world_director as wd

    monkeypatch.setattr(wd.WorldDirector, "run_cycle", staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ai down"))))
    monkeypatch.setattr(npp.NpcProactiveEngine, "maybe_engage", staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ai down"))))
    s = world.join("新号失败", user_id="fn_fail_1")
    assert s.get("token")
    assert s.get("first_night") == {"pending": True}
    cid = s["character_id"]
    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        status = world.first_night_status(cid)
        if status in ("done", "failed"):
            break
        time.sleep(0.2)
    assert status == "failed"
    recent = ChronicleRepository.get_recent(10)
    assert not any("ai down" in r or "error" in r.lower() for r in recent)
    assert world.get_char(s["token"]) is not None


def test_resume_does_not_rerun_first_night(world):
    s1 = world.join("不再跑", user_id="fn_once_1")
    cid = s1["character_id"]
    deadline = time.time() + 30
    while time.time() < deadline:
        if world.first_night_status(cid) in ("done", "failed"):
            break
        time.sleep(0.2)
    assert world.first_night_status(cid) in ("done", "failed")
    s2 = world.join("不再跑", user_id="fn_once_1")
    assert s2.get("resumed") is True
    assert s2.get("first_night") is None

# ==================== A8：并发 join 同账号只建一个角色 ====================

def test_concurrent_join_same_user_creates_one_character(world, tmp_path):
    uid = "race_a8"
    name = "并发客"
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(lambda _: world.join(name, user_id=uid), range(10)))
    assert all(r.get("token") for r in results)
    db_path = tmp_path / "latency.db"
    assert _db_count(db_path, "SELECT COUNT(*) FROM characters WHERE user_id = ?", (uid,)) == 1
    char_ids = {world.get_char(r["token"]).id for r in results}
    assert len(char_ids) == 1


# ==================== A9/A10：并发死亡结算恰好一次 + 死者快照一致 ====================

def test_concurrent_dead_settle_exactly_once(world, tmp_path):
    uid = "race_a9"
    name = "将死客"
    s = world.join(name, user_id=uid)
    _kill(world, uid, name, stones=500)
    db_path = tmp_path / "latency.db"

    def _call(i):
        if i % 2 == 0:
            return world.join(name, user_id=uid)
        return world.dead_payload(uid)

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_call, range(10)))
    assert all(r and r.get("dead") for r in results)
    assert _db_count(
        db_path,
        "SELECT COUNT(*) FROM world_chronicle WHERE event_type = 'LEGACY_SETTLE' AND actor_name = ?",
        (name,),
    ) == 1
    w1 = LegacyRepository.get_or_create(uid).wallet_stones
    again = world.dead_payload(uid)
    assert again and again.get("dead")
    assert LegacyRepository.get_or_create(uid).wallet_stones == w1
    assert _db_count(
        db_path,
        "SELECT COUNT(*) FROM world_chronicle WHERE event_type = 'LEGACY_SETTLE' AND actor_name = ?",
        (name,),
    ) == 1


def test_dead_payload_snapshot_matches_db(world):
    uid = "snap_a10"
    name = "快照客"
    s = world.join(name, user_id=uid)
    char = _kill(world, uid, name, stones=123)
    payload = world.dead_payload(uid)
    assert payload and payload.get("dead") is True
    assert payload["token"]
    db_char = CharacterRepository.get_by_user_id(uid)
    assert payload["character_id"] == db_char.id
    assert payload["name"] == db_char.name
    assert payload["realm"] == db_char.realm.name
    account = LegacyRepository.get_or_create(uid)
    assert payload["wallet"]["balance"] == account.wallet_stones
    assert payload["consignment_open_count"] == 0
    assert payload["legacy"]["points"] == account.points
    assert payload["legacy"]["lives"] == account.total_lives
    if account.past_lives:
        assert payload["legacy"]["lifespan_lived"] == account.past_lives[-1].lifespan_lived


# ==================== A14：旧存档兼容（无迁移、pending 不写角色行） ====================

def test_first_night_pending_not_persisted_in_character_row(world, tmp_path):
    s = world.join("不污染", user_id="compat_a14")
    db_path = tmp_path / "latency.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT data_json FROM characters WHERE id = ?", (s["character_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert "first_night" not in row[0]
    # pending 标记（{"pending": true} 形态）不得落盘；角色固有字段
    # crane_pending_item / pending_pet_species 不在此限
    assert '"pending": true' not in row[0]
    s2 = world.join("不污染", user_id="compat_a14")
    assert s2["character_id"] == s["character_id"]
    assert s2["rem_years"] == s["rem_years"]
    assert s2["legacy_points"] == s["legacy_points"]

# ==================== A6/A7/A10（修订 R1）：有界获取 + 锁外回退 ====================

def _http_post(base, path, payload, timeout=5.0):
    """真实 HTTP POST（绕过代理，直连 127.0.0.1），返回 (status, headers, body)。"""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read() or b"{}")


@pytest.fixture()
def http_world(world, monkeypatch):
    """真实 HTTP 服，但 WORLD 换成 tmp 库上的 fixture world。"""
    from server import app as app_mod

    monkeypatch.setattr(app_mod, "WORLD", world)
    from http.server import ThreadingHTTPServer

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.GameHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", world
    finally:
        httpd.shutdown()
        httpd.server_close()


def _make_account(name, password="password123"):
    from core.account import register as acct_register

    reg = acct_register(name, password, display_name=name)
    assert reg["ok"], reg
    return reg["user_id"]


def test_login_live_fallback_snapshot_while_lock_held(http_world, tmp_path):
    """A6（修订 R1）：活人登录，锁被他线程持有时真实 POST /login ≤2 秒返回
    200 回退快照：lock_fallback、session_issued:false、无 token，且零写会话。"""
    base, w = http_world
    uid = _make_account("活人持锁")
    s1 = w.join("活人持锁", user_id=uid)
    assert s1.get("token")
    db_path = tmp_path / "latency.db"
    ll_before = _last_login(db_path, uid)
    assert ll_before is not None
    sessions_before = _db_count(db_path, "SELECT COUNT(*) FROM auth_sessions")
    t0 = time.time()
    with w.lock:
        status, _headers, body = _http_post(
            base, "/login", {"username": "活人持锁", "password": "password123"}
        )
    assert time.time() - t0 < 2.0
    assert status == 200, body
    assert body.get("ok") is True
    assert body.get("lock_fallback") is True
    assert body.get("session_issued") is False
    assert not body.get("token")
    assert body.get("character_id") == s1["character_id"]
    assert body.get("name") == "活人持锁"
    assert body.get("realm") == s1["realm"]
    assert _db_count(db_path, "SELECT COUNT(*) FROM auth_sessions") == sessions_before
    # MF-3：回退快照未发会话，last_login 不变
    assert _last_login(db_path, uid) == ll_before
    # 释放锁后再次登录即正常发 token
    status2, _, body2 = _http_post(
        base, "/login", {"username": "活人持锁", "password": "password123"}
    )
    assert status2 == 200 and body2.get("token")
    assert body2.get("lock_fallback") is False
    assert body2.get("session_issued") is True
    # MF-3：实际发会话后 last_login 才推进
    assert _last_login(db_path, uid) > ll_before


def test_login_dead_fallback_then_settles_on_retry(http_world, tmp_path):
    """A6 + A10(b)（修订 R1）：死者登录，锁被持有时 ≤2 秒返回未结算快照
    （settlement_pending:true、settled:false、无 token、零结算写操作）；
    释放锁后再次登录完成结算：钱包等于单次归集期望值（与对照账号一致）、
    LEGACY_SETTLE 恰好一条、再登录不再重复结算。"""
    from storage.db import LegacyRepository as _LR

    base, w = http_world
    db_path = tmp_path / "latency.db"

    def _settle_count(name):
        return _db_count(
            db_path,
            "SELECT COUNT(*) FROM world_chronicle WHERE event_type = 'LEGACY_SETTLE' AND actor_name = ?",
            (name,),
        )

    # 对照账号：同样 500 灵石坐化，不持锁正常登录，得到单次归集期望钱包值
    ctrl_uid = _make_account("对照死者")
    w.join("对照死者", user_id=ctrl_uid)
    _kill(w, ctrl_uid, "对照死者", stones=500)
    _, _, ctrl_body = _http_post(
        base, "/login", {"username": "对照死者", "password": "password123"}
    )
    assert ctrl_body.get("dead") is True and ctrl_body.get("token")
    assert ctrl_body.get("settlement_pending") is False
    assert ctrl_body.get("settled") is True
    expected_wallet = ctrl_body["wallet"]["balance"]
    assert _settle_count("对照死者") == 1

    # 持锁账号：同样 500 灵石坐化
    uid = _make_account("持锁死者")
    w.join("持锁死者", user_id=uid)
    _kill(w, uid, "持锁死者", stones=500)
    ll_before = _last_login(db_path, uid)
    assert ll_before is not None
    pre_wallet = _LR.get(uid).wallet_stones
    assert _settle_count("持锁死者") == 0
    sessions_before = _db_count(db_path, "SELECT COUNT(*) FROM auth_sessions")

    t0 = time.time()
    with w.lock:
        status, _headers, body = _http_post(
            base, "/login", {"username": "持锁死者", "password": "password123"}
        )
    assert time.time() - t0 < 2.0
    assert status == 200, body
    assert body.get("dead") is True
    assert body.get("lock_fallback") is True
    assert body.get("settlement_pending") is True
    assert body.get("settled") is False
    assert body.get("session_issued") is False
    assert not body.get("token")
    # 未结算旧值 + 零结算写操作
    assert body["wallet"]["balance"] == pre_wallet
    assert _settle_count("持锁死者") == 0
    assert _LR.get(uid).wallet_stones == pre_wallet
    assert _db_count(db_path, "SELECT COUNT(*) FROM auth_sessions") == sessions_before
    # MF-3：回退快照未发会话，last_login 不变
    assert _last_login(db_path, uid) == ll_before

    # 释放锁后再次登录：恰好结算一次，钱包等于单次归集期望值
    status2, _, body2 = _http_post(
        base, "/login", {"username": "持锁死者", "password": "password123"}
    )
    assert status2 == 200 and body2.get("token")
    assert body2.get("settlement_pending") is False
    assert body2.get("settled") is True
    assert body2["wallet"]["balance"] == expected_wallet
    assert _settle_count("持锁死者") == 1
    # MF-3：实际发会话后 last_login 才推进
    assert _last_login(db_path, uid) > ll_before
    # 第三次登录不再重复结算
    _http_post(base, "/login", {"username": "持锁死者", "password": "password123"})
    assert _settle_count("持锁死者") == 1
    assert _LR.get(uid).wallet_stones == expected_wallet


def test_register_busy_while_lock_held_then_retry_succeeds(http_world, tmp_path):
    """A7（修订 R1）：锁被持有时真实 POST /register ≤2 秒返回 503 SERVER_BUSY
    （固定错误体 + Retry-After: 2），DB 无新角色行/会话行/JOIN 编年史行、
    无 first-night 调度；释放锁后原样重试一次即成功建角。"""
    from storage.db import AccountRepository as _AR

    base, w = http_world
    db_path = tmp_path / "latency.db"
    chars_before = _db_count(db_path, "SELECT COUNT(*) FROM characters")
    sessions_before = _db_count(db_path, "SELECT COUNT(*) FROM auth_sessions")
    payload = {"username": "忙时新号", "password": "password123", "name": "忙时新号"}

    t0 = time.time()
    with w.lock:
        status, headers, body = _http_post(base, "/register", payload)
    assert time.time() - t0 < 2.0
    assert status == 503, body
    assert body == {
        "ok": False,
        "error": "SERVER_BUSY",
        "message": "世界正在演化，请稍后重试",
        "retryable": True,
    }
    assert headers.get("Retry-After") == "2"
    assert _db_count(db_path, "SELECT COUNT(*) FROM characters") == chars_before
    assert _db_count(db_path, "SELECT COUNT(*) FROM auth_sessions") == sessions_before
    assert (
        _db_count(
            db_path,
            "SELECT COUNT(*) FROM world_chronicle WHERE event_type = 'JOIN' AND actor_name = ?",
            ("忙时新号",),
        )
        == 0
    )
    assert _AR.get_by_username("忙时新号") is None  # 繁忙即未写：账号行亦回滚，重试安全
    assert not w._first_night_inflight

    status2, _, body2 = _http_post(base, "/register", payload)
    assert status2 == 200, body2
    assert body2.get("token")
    assert body2.get("is_new_life") is True
    assert body2.get("first_night") == {"pending": True}
    assert body2.get("character_id")


def test_join_direct_live_fallback_and_write_busy(world):
    """A6/A7（World 层直接调用）：活人 join 锁外回退快照；新建角/收养类写路径
    抛 WorldBusyError，且 2 秒内返回/抛出。

    注意：锁必须由另一线程持有——同线程持锁时 RLock 会重入、取锁立即成功，
    模拟不出“锁被他线程持有”的场景（生产上 tick 线程与 HTTP 线程本就是
    不同线程）。
    """
    from server.world import WorldBusyError

    uid = "direct_a6"
    s1 = world.join("直接持锁", user_id=uid)
    assert s1.get("token")
    dead_uid = "direct_dead"
    world.join("直接死者", user_id=dead_uid)
    _kill(world, dead_uid, "直接死者", stones=100)

    held = threading.Event()
    release = threading.Event()

    def _holder():
        with world.lock:
            held.set()
            release.wait(timeout=30)

    ht = threading.Thread(target=_holder, daemon=True)
    ht.start()
    assert held.wait(timeout=5)
    try:
        t0 = time.time()
        snap = world.join("直接持锁", user_id=uid)
        assert time.time() - t0 < 2.0
        assert snap.get("lock_fallback") is True
        assert snap.get("session_issued") is False
        assert not snap.get("token")
        assert snap.get("character_id") == s1["character_id"]
        assert snap.get("resumed") is True
        # 死者直接回退：未结算快照
        t1 = time.time()
        dead = world.dead_payload(dead_uid)
        assert time.time() - t1 < 2.0
        assert dead.get("dead") is True
        assert dead.get("lock_fallback") is True
        assert dead.get("settlement_pending") is True
        assert dead.get("settled") is False
        assert not dead.get("token")
        # 写路径：新建角与匿名收养/建角一律繁忙
        t2 = time.time()
        with pytest.raises(WorldBusyError):
            world.join("全新路人", user_id="direct_new")
        assert time.time() - t2 < 2.0
        t3 = time.time()
        with pytest.raises(WorldBusyError):
            world.join("匿名新号", user_id=None)
        assert time.time() - t3 < 2.0
    finally:
        release.set()
        ht.join(timeout=5)


# ==================== MF-1：首夜陈旧写回（评审 must-fix）====================
# apply_directive（两处目标投射循环）与 spawn_from_directive（run_cycle 经
# absorb_director_cycle 调用）须在 save 前重读当前行：死亡或已被改过的角色
# 跳过，绝不把建角时快照整行写回（死者复活 / 位置灵石回滚）。

def _join_without_first_night_thread(world, monkeypatch, name, uid):
    """join 但不启动 first-night 后台线程，避免其 run_cycle 干扰确定性断言。"""
    with monkeypatch.context() as m:
        m.setattr(threading.Thread, "start", lambda self: None)
        return world.join(name, user_id=uid)


def _last_login(db_path, user_id):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT last_login FROM accounts WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


@pytest.mark.parametrize("dtype", ["omen", "calamity_forecast"])
def test_apply_directive_skips_dead_stale_snapshot(world, monkeypatch, dtype):
    """MF-1（确定性）：list_all_alive 读到的快照已死后，apply_directive 不得
    把快照整行写回“复活”死者；死亡状态/灵石/位置保持 DB 当前值。"""
    import copy

    from core import world_director as wd
    from core.models import CharacterStatus

    _join_without_first_night_thread(world, monkeypatch, "陈旧死者", "mf1_dead")
    live = CharacterRepository.get_by_user_id("mf1_dead")
    assert live is not None
    snapshot = copy.deepcopy(live)  # 建角时快照：活体
    monkeypatch.setattr(
        "storage.db.CharacterRepository.list_all_alive",
        staticmethod(lambda: [snapshot]),
    )
    # 快照之后角色已死，且灵石/位置被改过
    live.status = CharacterStatus.DEAD
    live.death_cause = "测试坐化"
    live.spirit_stones = 999
    live.location = "改后之地"
    live.death_settled = False
    CharacterRepository.save(live)

    if dtype == "omen":
        directive = {
            "type": "omen",
            "title": "天机测试",
            "narrative": "测试叙事",
            "effects": {"goal_title": "机缘·测试", "goal_detail": "测试机缘详情"},
        }
    else:
        directive = {
            "type": "calamity_forecast",
            "title": "大劫测试",
            "narrative": "测试叙事",
            "effects": {},
        }
    wd.apply_directive(directive)

    fresh = CharacterRepository.get_by_user_id("mf1_dead")
    assert fresh.status == CharacterStatus.DEAD
    assert fresh.spirit_stones == 999
    assert fresh.location == "改后之地"
    assert fresh.death_settled is False


def test_apply_directive_applies_opportunity_to_fresh_row(world, monkeypatch):
    """MF-1（确定性）：快照之后角色位置/灵石被改过（仍活着），机缘须挂到
    最新行上——新目标加上，位置/灵石保持最新值，不被写回建角时快照。"""
    import copy

    from core import world_director as wd

    _join_without_first_night_thread(world, monkeypatch, "陈旧活人", "mf1_alive")
    live = CharacterRepository.get_by_user_id("mf1_alive")
    assert live is not None
    snapshot = copy.deepcopy(live)
    monkeypatch.setattr(
        "storage.db.CharacterRepository.list_all_alive",
        staticmethod(lambda: [snapshot]),
    )
    live.location = "改后之地"
    live.spirit_stones = 777
    CharacterRepository.save(live)

    wd.apply_directive(
        {
            "type": "omen",
            "title": "天机测试",
            "narrative": "测试叙事",
            "effects": {"goal_title": "机缘·测试", "goal_detail": "测试机缘详情"},
        }
    )
    fresh = CharacterRepository.get_by_user_id("mf1_alive")
    assert fresh.location == "改后之地"
    assert fresh.spirit_stones == 777
    titles = [g.get("title") for g in (fresh.goals or [])]
    assert "机缘·测试" in titles


def test_spawn_from_directive_skips_dead_stale_snapshot(world, monkeypatch):
    """MF-1（同根因）：run_cycle 经 absorb_director_cycle 调用的
    spawn_from_directive，预兆机缘同样不得把陈旧快照写回已死角色。"""
    import copy

    from core import world_arc as wa
    from core.models import CharacterStatus

    _join_without_first_night_thread(world, monkeypatch, "弧线死者", "mf1_arc_dead")
    live = CharacterRepository.get_by_user_id("mf1_arc_dead")
    assert live is not None
    snapshot = copy.deepcopy(live)
    monkeypatch.setattr(
        "storage.db.CharacterRepository.list_all_alive",
        staticmethod(lambda: [snapshot]),
    )
    live.status = CharacterStatus.DEAD
    live.death_cause = "测试坐化"
    live.spirit_stones = 999
    live.location = "改后之地"
    live.death_settled = False
    CharacterRepository.save(live)

    arc = wa.spawn_from_directive(
        {"type": "omen", "title": "弧线测试", "narrative": "测试叙事", "effects": {}}
    )
    assert arc is not None
    fresh = CharacterRepository.get_by_user_id("mf1_arc_dead")
    assert fresh.status == CharacterStatus.DEAD
    assert fresh.spirit_stones == 999
    assert fresh.location == "改后之地"


def test_save_if_unchanged_skips_modified_or_dead_row(world, monkeypatch):
    """MF-1（仓库层原子校验）：save_if_unchanged 仅当行未被改写且仍存活时落盘；
    重读后被改过（位置/灵石）或已死的行一律返回 False 且一行不写。"""
    from core.models import CharacterStatus

    _join_without_first_night_thread(world, monkeypatch, "乐观写回", "mf1_ouc")
    live = CharacterRepository.get_by_user_id("mf1_ouc")
    fresh, updated_at = CharacterRepository.get_by_id_with_meta(live.id)
    assert fresh is not None and updated_at is not None

    # 未改写：写回成功
    fresh.spirit_stones = 201
    assert CharacterRepository.save_if_unchanged(fresh, updated_at) is True
    assert CharacterRepository.get_by_user_id("mf1_ouc").spirit_stones == 201

    # 重读后行被另一写者改过：旧 updated_at 的写回被丢弃
    stale, old_updated_at = CharacterRepository.get_by_id_with_meta(live.id)
    newer = CharacterRepository.get_by_user_id("mf1_ouc")
    newer.location = "另一写者之地"
    newer.spirit_stones = 555
    CharacterRepository.save(newer)
    stale.spirit_stones = 202
    assert CharacterRepository.save_if_unchanged(stale, old_updated_at) is False
    kept = CharacterRepository.get_by_user_id("mf1_ouc")
    assert kept.location == "另一写者之地"
    assert kept.spirit_stones == 555

    # 行已死：写回被丢弃
    dead_view, dead_updated_at = CharacterRepository.get_by_id_with_meta(live.id)
    dead_row = CharacterRepository.get_by_user_id("mf1_ouc")
    dead_row.status = CharacterStatus.DEAD
    dead_row.death_cause = "测试坐化"
    dead_row.death_settled = False
    CharacterRepository.save(dead_row)
    dead_view.spirit_stones = 203
    assert CharacterRepository.save_if_unchanged(dead_view, dead_updated_at) is False
    assert CharacterRepository.get_by_user_id("mf1_ouc").status == CharacterStatus.DEAD


def test_first_night_does_not_resurrect_killed_character(world):
    """MF-1（端到端）：入世后立即杀死角色，first-night 后台 run_cycle 完成后
    死者仍为死者，灵石/位置不变。"""
    from core.models import CharacterStatus

    s = world.join("入世即杀", user_id="mf1_e2e")
    assert s.get("token")
    cid = s["character_id"]
    loc_before = CharacterRepository.get_by_user_id("mf1_e2e").location
    _kill(world, "mf1_e2e", "入世即杀", stones=100)
    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        status = world.first_night_status(cid)
        if status in ("done", "failed"):
            break
        time.sleep(0.2)
    assert status in ("done", "failed")
    fresh = CharacterRepository.get_by_user_id("mf1_e2e")
    assert fresh.status == CharacterStatus.DEAD
    assert fresh.spirit_stones == 100
    assert fresh.location == loc_before
    assert fresh.death_settled is False


# ==================== MF-2：熔断器半开探测异常卡死 ====================

def test_parse_json_loose_rejects_non_string():
    """MF-2（逃逸点加固）：_parse_json_loose 收到非字符串真值时返回 None 而非抛错。"""
    assert gateway._parse_json_loose(["not", "a", "string"]) is None
    assert gateway._parse_json_loose(123) is None
    assert gateway._parse_json_loose(None) is None
    assert gateway._parse_json_loose('{"a": 1}') == {"a": 1}


def test_breaker_half_open_probe_exception_recovers(monkeypatch):
    """MF-2：半开探测恰好撞上畸形响应（OpenAI 分支 content 为非字符串）时，
    _chat_json 不抛错、不卡死：本次返回 None、熔断器重开，冷却后再探测成功即关闭。"""
    monkeypatch.setattr(gateway, "USE_CCSWITCH", False)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    monkeypatch.setattr(gateway, "NPC_TICK_INTERVAL_SECONDS", 0.2)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        if len(calls) <= 3:
            raise httpx.ConnectTimeout("slow relay")
        if len(calls) == 4:
            # 半开探测撞上畸形响应：content 为列表
            return _FakeResp(200, content=["not", "a", "string"])
        return _FakeResp(200, '{"line": "通"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    for _ in range(3):
        assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    time.sleep(0.3)
    # 半开探测遇畸形响应：不抛错，返回 None，熔断器重开而非卡死在半开
    assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    assert gateway.breaker_state()["failures"] == 3
    # 冷却后再次探测成功 → 关闭
    time.sleep(0.3)
    assert gateway._chat_json("hi") == {"line": "通"}
    assert gateway.breaker_state()["state"] == "closed"
    assert gateway.breaker_state()["failures"] == 0


def test_breaker_half_open_cc_malformed_json_recovers(monkeypatch):
    """MF-2（CC 分支逃逸点）：resp.json() 返回非 dict（如数组）时 _handle 不抛错；
    半开探测后熔断器重开，冷却后好探测关闭。"""
    _cc_on(monkeypatch)
    monkeypatch.setattr(gateway, "LLM_API_KEY", "")  # 关掉 OpenAI 兜底，只量 CC 通道本身
    monkeypatch.setattr(gateway, "NPC_TICK_INTERVAL_SECONDS", 0.2)
    calls = []

    class _ListResp:
        status_code = 200
        text = "[1, 2]"

        def json(self):
            return ["not", "a", "dict"]

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        if len(calls) <= 3:
            raise httpx.ConnectTimeout("slow relay")
        if len(calls) == 4:
            return _ListResp()
        return _AnthropicResp(200, '{"line": "通"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    for _ in range(3):
        assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    time.sleep(0.3)
    assert gateway._chat_json("hi") is None
    assert gateway.breaker_state()["state"] == "open"
    time.sleep(0.3)
    assert gateway._chat_json("hi") == {"line": "通"}
    assert gateway.breaker_state()["state"] == "closed"


# ==================== MF-3：503 前不写 last_login ====================

def test_account_login_does_not_touch_last_login(world, tmp_path):
    """MF-3：core.account.login 只验密，不写 last_login；写操作只在 app 层
    实际发会话后发生。"""
    from core.account import login as acct_login

    db_path = tmp_path / "latency.db"
    uid = _make_account("只验密")
    before = _last_login(db_path, uid)
    assert before is not None
    assert acct_login("只验密", "password123").get("ok") is True
    assert _last_login(db_path, uid) == before


def test_login_busy_503_does_not_touch_last_login(http_world, tmp_path):
    """MF-3：写路径拿不到锁返回 503 时，accounts.last_login 不变（繁忙即未写）。"""
    base, w = http_world
    db_path = tmp_path / "latency.db"
    uid = _make_account("忙时登录")
    # 该账号尚未 join：无角色行，/login 走写路径，持锁时必 503
    assert CharacterRepository.get_by_user_id(uid) is None
    before = _last_login(db_path, uid)
    assert before is not None
    t0 = time.time()
    with w.lock:
        status, _headers, body = _http_post(
            base, "/login", {"username": "忙时登录", "password": "password123"}
        )
    assert time.time() - t0 < 2.0
    assert status == 503, body
    assert body.get("error") == "SERVER_BUSY"
    assert _last_login(db_path, uid) == before
    assert CharacterRepository.get_by_user_id(uid) is None
    assert _db_count(db_path, "SELECT COUNT(*) FROM auth_sessions") == 0


# ==================== MF-4：/register 繁忙回滚条件删除 ====================

def test_account_delete_guarded_when_character_or_session_exists(world):
    """MF-4：账号已有角色行/会话行时 delete 不得删账号行（返回 False）；
    裸账号行可删（返回 True）。"""
    from storage.db import AccountRepository as _AR
    from storage.db import AuthSessionRepository as _SR

    uid = _make_account("删不掉")
    s = world.join("删不掉", user_id=uid)
    assert s.get("token")
    assert _AR.delete(uid) is False
    assert _AR.get_by_username("删不掉") is not None
    assert CharacterRepository.get_by_user_id(uid) is not None

    uid2 = _make_account("只有会话")
    _SR.save("tok_guard", uid2, "char_guard", "只有会话")
    assert _AR.delete(uid2) is False
    assert _AR.get_by_username("只有会话") is not None

    uid3 = _make_account("裸账号")
    assert _AR.delete(uid3) is True
    assert _AR.get_by_username("裸账号") is None


def test_account_delete_race_never_orphans_character(world):
    """MF-4（并发）：角色行一旦落盘，并发 delete 一律不得删账号行。"""
    from storage.db import AccountRepository as _AR

    uid = _make_account("竞态删号")
    done = threading.Event()

    def _joiner():
        world.join("竞态删号", user_id=uid)
        done.set()

    t = threading.Thread(target=_joiner, daemon=True)
    t.start()
    # 等角色行出现后再删：此后 delete 必须全部返回 False
    deadline = time.time() + 10
    while CharacterRepository.get_by_user_id(uid) is None and time.time() < deadline:
        time.sleep(0.01)
    assert CharacterRepository.get_by_user_id(uid) is not None
    for _ in range(100):
        assert _AR.delete(uid) is False
    t.join(timeout=10)
    assert done.is_set()
    assert _AR.get_by_username("竞态删号") is not None
    assert CharacterRepository.get_by_user_id(uid) is not None
