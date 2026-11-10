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


# ================= 评审 MF-1：锁内 AI 点缀短超时 + 熔断不计账 =================

def test_mf1_chat_json_count_failure_false_skips_breaker(monkeypatch):
    """点缀调用（count_failure=False）连续可数失败不计入主通道熔断；
    默认口径仍按既有规则计数开闸（熔断记账评估的接缝直测）。"""
    import ai.gateway as gw

    monkeypatch.setattr(gw, "_chat_json_inner", lambda prompt, timeout=0: (None, "timeout"))
    gw.breaker_reset()
    try:
        for _ in range(3):
            assert gw._chat_json("点缀", timeout=2, count_failure=False) is None
        snap = gw.breaker_state()
        assert snap["failures"] == 0 and snap["state"] == "closed", snap
        for _ in range(3):
            assert gw._chat_json("主通道", timeout=2) is None
        snap = gw.breaker_state()
        assert snap["failures"] >= 3 and snap["state"] == "open", snap
    finally:
        gw.breaker_reset()
    print("✓ MF-1 熔断接缝：count_failure=False 不计数、默认口径仍开闸")


def test_mf1_collusion_ai_short_timeout(world, monkeypatch):
    """合谋点缀（tick 锁内 apply 段调用链）：_chat_json 收到 timeout=2 +
    count_failure=False；AI 叙事仍被采用（行为与既有成功路径一致）。"""
    import ai.gateway as gw
    from core.clock import WorldClock
    from core.collusion import ensure_link, try_collude_pair

    a = WorldClock.create_new_character("npc_mf1_a", "合谋甲")
    b = WorldClock.create_new_character("npc_mf1_b", "合谋乙")
    a.location = b.location = "青云坊市客栈"
    CharacterRepository.save(a)
    CharacterRepository.save(b)
    ensure_link(a, b, "恩", note="同乡")

    seen = {}

    def _fake_chat_json(prompt, timeout=0, **kw):
        seen["timeout"] = timeout
        seen["count_failure"] = kw.get("count_failure")
        return {"narrative": "二人低语数句，旋即分开。"}

    monkeypatch.setattr(gw, "ai_ready", lambda: True)
    monkeypatch.setattr(gw, "_chat_json", _fake_chat_json)
    r = try_collude_pair(a, b, use_ai=True)
    assert r is not None and r.get("source") == "ai", r
    assert seen["timeout"] == 2, seen
    assert seen["count_failure"] is False, seen
    print("✓ MF-1 合谋：短超时 2s + count_failure=False 透传、AI 叙事采用")


def test_mf1_world_arc_ai_short_timeout(monkeypatch):
    """世界弧阶段点缀（tick 锁内、每 tick ≤2 次）：router.invoke 收到
    timeout=2 + count_failure=False；成功叙事仍被采用。"""
    import ai.router as router
    import config as cfg
    from core.world_arc import _ai_stage_text

    monkeypatch.setattr(cfg, "LLM_API_KEY", "mf1-test-key")
    seen = {}

    def _fake_invoke(scene_id, payload=None, actor_id="system", timeout=0, **kw):
        seen["timeout"] = timeout
        seen["count_failure"] = kw.get("count_failure")
        return {"ok": True, "data": {"narrative": "弧光叙事"}}

    monkeypatch.setattr(router, "invoke", _fake_invoke)
    out = _ai_stage_text({"id": "arc_mf1", "kind": "blood_feud"}, "escalate", "模板句")
    assert out == "弧光叙事", out
    assert seen["timeout"] == 2, seen
    assert seen["count_failure"] is False, seen
    print("✓ MF-1 世界弧：短超时 2s + count_failure=False 透传、AI 叙事采用")
