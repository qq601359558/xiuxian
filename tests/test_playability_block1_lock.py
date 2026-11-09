"""playability-block1 T1 验收：tick 三段式 / director CAS / /转世 有界 / 注册兜底。

约定（沿用 test_login_latency_fix）：
- DB 一律 tmp_path 隔离（monkeypatch storage.db.DB_PATH），不碰真实存档。
- 角色名带唯一前缀 pb1lock；每测独立 tmp DB，零残留。
- (a) 旧行为：慢 AI 在 World.lock 内调用，主线程 1.5s 内拿不到锁 → 失败；
  新行为：AI 在锁外调用，拿锁 <1.5s 成功。
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

import pytest

import config

config.ALLOW_LOCAL_AI = True
config.AI_REQUIRED = False

from server.world import World, WorldBusyError
from storage.db import CharacterRepository, WorldStateRepository, init_db


@pytest.fixture()
def world(tmp_path, monkeypatch):
    test_db = tmp_path / "pb1lock.db"
    monkeypatch.setattr("storage.db.DB_PATH", test_db)
    init_db()
    w = World(auto_tick=False)
    yield w
    w.stop_tick()


@pytest.fixture()
def http_world(world, monkeypatch):
    """真实 HTTP 服，WORLD 换成 tmp 库 fixture world（同 latency 测试口径）。"""
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


def _http_post(base, path, payload, timeout=8.0):
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


def _hold_lock(world_obj, release: threading.Event, held: threading.Event):
    with world_obj.lock:
        held.set()
        release.wait(timeout=30)


# ==================== (a) 慢 AI 下 tick 不持锁 ====================

def test_tick_slow_ai_releases_world_lock(world, monkeypatch):
    """慢 AI（ai_invoke 睡 3s）期间主线程有界拿锁 <1.5s 成功。

    规则结算用桩保证每个候选 NPC 都 acted（确定性触发 AI 叙事润色）；
    director 闸门用 last_run_ts=now 关掉，避免其冷却路径干扰计时。
    """
    import core.npc_agenda as agenda_mod

    WorldStateRepository.set("director", {
        "last_run_ts": time.time(), "last_trigger": "", "last_source": "",
        "last_error": "", "last_accepted": 0, "active": [], "history": [],
        "player_events": [], "stats": {"runs": 0, "accepted": 0, "rejected": 0, "attempts": 0},
    })

    def _fake_resolve(npc, ag_type, ag, now=None):
        return {
            "acted": True, "action": "talk", "outcome": "snoop",
            "narrative": f"{npc.name}四下打探，袖中剑意森然。",
            "progress_delta": 1, "new_location": None,
            "notes": [], "cascade_notes": [],
            "target_id": None, "target_name": "",
        }

    monkeypatch.setattr(
        "core.jianghu_sim.JianghuSimulator.resolve_agenda",
        staticmethod(_fake_resolve),
    )
    monkeypatch.setattr(agenda_mod, "ai_ready", lambda: True)

    ai_calls = []

    def _slow_invoke(*args, **kwargs):
        ai_calls.append(time.time())
        time.sleep(3)
        return {"ok": True, "data": {"narrative": "慢AI润色叙事一句。"}}

    monkeypatch.setattr(agenda_mod, "ai_invoke", _slow_invoke)

    tick_thread = threading.Thread(target=world._tick_once, daemon=True)
    tick_thread.start()
    try:
        time.sleep(1.5)  # 让 tick 进入 agenda 的 AI 阶段
        t0 = time.time()
        ok = world.lock.acquire(timeout=1.5)
        elapsed = time.time() - t0
        assert ok, f"慢 AI 期间主线程 1.5s 内拿不到 World.lock（waited {elapsed:.2f}s）"
        assert elapsed < 1.5
        world.lock.release()
    finally:
        tick_thread.join(timeout=30)
    assert not tick_thread.is_alive()
    assert ai_calls, "桩 AI 未被调用，测试未真正覆盖慢 AI 路径"


# ==================== (b) director CAS：并发 player_event 不被覆盖 ====================

def test_director_cycle_preserves_concurrent_player_event(world):
    from core.world_director import WorldDirector, _load
    from core.clock import WorldClock

    WorldStateRepository.set("director", {
        "last_run_ts": 0.0, "last_trigger": "", "last_source": "",
        "last_error": "", "last_accepted": 0, "active": [], "history": [],
        "player_events": [], "stats": {"runs": 0, "accepted": 0, "rejected": 0, "attempts": 0},
    })
    pc = WorldClock.create_new_character("pb1lock_dir_player", "pb1观劫者")
    CharacterRepository.save(pc)

    def _gateway(prompt):
        # cycle 已读快照、AI 提案未落盘的窗口内，并发写入一条 player_event
        from core.world_director import note_player_event

        note_player_event("breakthrough", detail="pb1并发突破事件", now=time.time())
        return {"directives": [
            {"type": "omen", "title": "pb1并发兆", "narrative": "风起青萍之末"}
        ]}

    res = WorldDirector.run_cycle(trigger="manual", force=True, gateway=_gateway)
    assert res.get("ok"), res
    state = _load()
    details = [e.get("detail") for e in (state.get("player_events") or [])]
    assert "pb1并发突破事件" in details, f"并发 player_event 被旧快照覆盖：{details}"
    titles = [d.get("title") for d in (state.get("active") or [])]
    assert "pb1并发兆" in titles


def test_director_save_cas_merges_concurrent_append(world):
    """_save 的 CAS 合并口径：以旧快照保存时，并发追加的 player_events 必须存活。"""
    from core.world_director import _load, _save, note_player_event

    WorldStateRepository.set("director", {
        "last_run_ts": 0.0, "last_trigger": "", "last_source": "",
        "last_error": "", "last_accepted": 0, "active": [], "history": [],
        "player_events": [], "stats": {"runs": 0, "accepted": 0, "rejected": 0, "attempts": 0},
    })
    stale = _load()
    note_player_event("breakthrough", detail="pb1CAS并发事件", now=time.time())
    stale["last_error"] = "pb1-cas-marker"
    _save(stale)
    merged = _load()
    details = [e.get("detail") for e in (merged.get("player_events") or [])]
    assert "pb1CAS并发事件" in details, details
    assert merged.get("last_error") == "pb1-cas-marker"
    assert int(merged.get("revision") or 0) >= 2


# ==================== (c) /转世 有界锁 → WorldBusyError / 503 ====================

def test_reincarnate_handle_bounded_lock_busy(world):
    from core.models import CharacterStatus

    s = world.join("pb1转世者", user_id="pb1lock_reborn")
    token = s["token"]
    char = CharacterRepository.get_by_user_id("pb1lock_reborn")
    char.status = CharacterStatus.DEAD
    char.death_cause = "pb1测试坐化"
    CharacterRepository.save(char)

    held, release = threading.Event(), threading.Event()
    ht = threading.Thread(target=_hold_lock, args=(world, release, held), daemon=True)
    ht.start()
    assert held.wait(timeout=5)
    try:
        t0 = time.time()
        with pytest.raises(WorldBusyError):
            world.handle(token, "/转世")
        elapsed = time.time() - t0
        assert elapsed < 4.0, f"/转世 有界拿锁超时过久：{elapsed:.2f}s"
    finally:
        release.set()
        ht.join(timeout=5)
    # 锁释放后 /转世 正常可用
    res = world.handle(token, "/转世")
    assert res.get("ok"), res


def test_reincarnate_http_503_when_lock_held(http_world):
    base, w = http_world
    from core.models import CharacterStatus

    s = w.join("pb1转世乙", user_id="pb1lock_reborn_http")
    token = s["token"]
    char = CharacterRepository.get_by_user_id("pb1lock_reborn_http")
    char.status = CharacterStatus.DEAD
    char.death_cause = "pb1测试坐化"
    CharacterRepository.save(char)

    held, release = threading.Event(), threading.Event()
    ht = threading.Thread(target=_hold_lock, args=(w, release, held), daemon=True)
    ht.start()
    assert held.wait(timeout=5)
    try:
        t0 = time.time()
        status, headers, body = _http_post(base, "/action", {"token": token, "command": "/转世"})
        elapsed = time.time() - t0
    finally:
        release.set()
        ht.join(timeout=5)
    assert elapsed < 5.0
    assert status == 503, body
    assert body.get("error") == "SERVER_BUSY"
    assert body.get("retryable") is True


# ==================== (d) 注册路径 DB locked → 503，绝不裸 500 ====================

def test_join_db_locked_raises_world_busy(world, monkeypatch):
    def _locked(*a, **kw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(
        "storage.db.CharacterRepository.get_by_user_id", staticmethod(_locked)
    )
    with pytest.raises(WorldBusyError):
        world.join("pb1锁库者", user_id="pb1lock_dblocked")


def test_join_db_other_operational_error_not_converted(world, monkeypatch):
    def _ioerr(*a, **kw):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(
        "storage.db.CharacterRepository.get_by_user_id", staticmethod(_ioerr)
    )
    with pytest.raises(sqlite3.OperationalError):
        world.join("pb1磁盘错", user_id="pb1lock_ioerr")


def test_register_http_db_locked_returns_503(http_world, monkeypatch):
    base, _w = http_world

    def _locked_register(username, password, display_name=None):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("core.account.register", _locked_register)
    status, headers, body = _http_post(
        base, "/register",
        {"username": "pb1reglock", "password": "password123", "name": "pb1注锁者"},
    )
    assert status == 503, body
    assert body.get("error") == "SERVER_BUSY"
    assert body.get("retryable") is True
    assert headers.get("Retry-After") == "2"
