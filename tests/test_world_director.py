"""
M1 天道导演：门禁 / 调度 / 落账 / 指令
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("ALLOW_LOCAL_AI", "0")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, WorldStateRepository, CharacterRepository
from core.clock import WorldClock
from core.world_channel import WorldChannel
from core.world_director import (
    WorldDirector,
    admit_directive,
    apply_directive,
    gather_world_brief,
    handle_heaven_command,
)
from core.secret_realm import director_force_open, realm_status
from config import SECRET_REALMS


def _reset_channel_limit():
    import core.world_channel as wc

    wc._recent_keys.clear()
    wc._min_window_start = 0.0
    wc._min_count = 0


def _reset_director():
    WorldStateRepository.set("director", {
        "last_run_ts": 0.0,
        "last_trigger": "",
        "last_source": "",
        "last_error": "",
        "last_accepted": 0,
        "active": [],
        "history": [],
        "stats": {"runs": 0, "accepted": 0, "rejected": 0},
    })
    _reset_channel_limit()


def _char(name, uid=None, loc="青云坊市客栈"):
    c = WorldClock.create_new_character(uid or f"dir_{name}", name)
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def test_admit_rejects_illegal_type_and_strips_numeric_effects():
    init_db()
    ok, reason, item = admit_directive({"type": "nuke", "title": "x", "narrative": "y"})
    assert ok is False and "illegal_type" in reason
    ok, reason, item = admit_directive(
        {
            "type": "omen",
            "title": "测",
            "narrative": "风起",
            "effects": {"exp": 9999, "stones": 500, "goal_title": "机缘", "whisper": "x"},
        }
    )
    assert ok is True and item is not None
    assert "exp" not in item["effects"] and "stones" not in item["effects"]
    assert item["effects"].get("goal_title") == "机缘"
    print("✓ admit 类型白名单与数值键剥离")


def test_admit_calamity_window_and_realm():
    init_db()
    season_open = {"is_final_week": False, "remain_real_days": 80}
    season_warn = {"is_final_week": True, "remain_real_days": 3}
    ok, reason, _ = admit_directive(
        {"type": "calamity_forecast", "title": "劫", "narrative": "大劫将至"},
        season=season_open,
    )
    assert ok is False and reason == "calamity_out_of_window"
    ok, _, item = admit_directive(
        {"type": "calamity_forecast", "title": "劫", "narrative": "大劫将至"},
        season=season_warn,
    )
    assert ok and item["channel_level"] == "epic"
    rid = next(iter(SECRET_REALMS.keys()))
    ok, reason, _ = admit_directive(
        {
            "type": "secret_realm_pressure",
            "title": "潮",
            "narrative": "禁制松动",
            "effects": {"realm_id": "不存在的秘境"},
        }
    )
    assert ok is False and reason == "unknown_realm"
    ok, _, item = admit_directive(
        {
            "type": "secret_realm_pressure",
            "title": "潮",
            "narrative": f"【{rid}】禁制松动",
            "effects": {"realm_id": rid, "force_open": True},
        }
    )
    assert ok and item["effects"]["realm_id"] == rid
    print("✓ 大劫窗口与秘境门禁")


def test_local_director_run_persists_and_channel():
    init_db()
    _reset_director()
    _char("观察者", uid="dir_player_a")
    import config

    old_local = config.ALLOW_LOCAL_AI
    old_key = config.LLM_API_KEY
    old_cc = config.USE_CCSWITCH
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    try:
        res = WorldDirector.run_cycle(trigger="test", force=True)
        assert res["ok"] is True
        assert res["source"] == "local", res
        state = WorldStateRepository.get("director") or {}
        assert len(state.get("active") or []) >= 1
        assert state.get("last_source") == "local"
        board = WorldDirector.format_heaven_board()
        assert "天道导演" in board
        assert "local" in board or "本地降级" in board
        rows = WorldChannel.recent(limit=10)
        assert any("天道导演" in m.text for m in rows)
    finally:
        config.ALLOW_LOCAL_AI = old_local
        config.LLM_API_KEY = old_key
        config.USE_CCSWITCH = old_cc
        _reset_director()
    print("✓ 本地降级导演落账与 /天道 面板")


def test_no_ai_no_local_blocks_without_fake():
    init_db()
    _reset_director()
    import config

    old_local = config.ALLOW_LOCAL_AI
    old_key = config.LLM_API_KEY
    old_cc = config.USE_CCSWITCH
    config.ALLOW_LOCAL_AI = False
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    try:
        assert config.ai_available() is False
        res = WorldDirector.run_cycle(trigger="test", force=True)
        assert res["ok"] is False, res
        state = WorldStateRepository.get("director") or {}
        assert state.get("last_source") == "error"
        assert not state.get("active")
        r = handle_heaven_command("/天道", ["/天道"])
        assert "天道导演" in r["text"]
        # 不得出现 local 伪装成功
        assert "本地降级" not in r["text"] or "不可用" in r["text"] or "未配置" in r["text"] or "error" in str(state.get("last_source"))
    finally:
        config.ALLOW_LOCAL_AI = old_local
        config.LLM_API_KEY = old_key
        config.USE_CCSWITCH = old_cc
        _reset_director()
    print("✓ 无 AI 不伪造导演成功")


def test_cooldown_and_force():
    init_db()
    _reset_director()
    import config

    old_local = config.ALLOW_LOCAL_AI
    old_key = config.LLM_API_KEY
    old_cc = config.USE_CCSWITCH
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    try:
        r1 = WorldDirector.run_cycle(trigger="test", force=True, now=1_000_000.0)
        assert r1["ok"] is True
        r2 = WorldDirector.run_cycle(trigger="timer", force=False, now=1_000_000.0 + 10)
        assert r2["ok"] is False
        assert r2.get("skipped") in ("cooldown", "tick_gate")
        r3 = WorldDirector.run_cycle(trigger="command", force=True, now=1_000_000.0 + 10)
        assert r3["ok"] is True
    finally:
        config.ALLOW_LOCAL_AI = old_local
        config.LLM_API_KEY = old_key
        config.USE_CCSWITCH = old_cc
        _reset_director()
    print("✓ 冷却与 force 推演")


def test_secret_realm_force_open():
    init_db()
    rid = next(iter(SECRET_REALMS.keys()))
    assert director_force_open(rid) is True
    rows = realm_status()
    hit = [r for r in rows if r["name"] == rid]
    assert hit and hit[0]["is_open"] is True
    assert director_force_open("无此秘境") is False
    print("✓ 秘境导演开启")


def test_apply_secret_realm_pressure_goal_and_channel():
    init_db()
    _reset_director()
    _char("目标修士", uid="dir_player_b")
    rid = next(iter(SECRET_REALMS.keys()))
    ok, _, d_open = admit_directive(
        {
            "type": "secret_realm_pressure",
            "title": "潮",
            "narrative": f"【{rid}】提前松动",
            "effects": {"realm_id": rid, "force_open": True},
        }
    )
    assert ok
    applied_open = apply_directive(d_open)
    assert applied_open.get("realm") == rid
    rows = realm_status()
    hit = [r for r in rows if r["name"] == rid]
    assert hit and hit[0]["is_open"] is True

    ok, _, d = admit_directive(
        {
            "type": "omen",
            "title": "灵机",
            "narrative": "坊市上空有剑鸣",
            "location": "青云坊市客栈",
            "effects": {"goal_title": "天道示警", "goal_detail": "关注 /天道"},
        }
    )
    assert ok
    applied = apply_directive(d)
    assert applied["channel"] is True
    assert applied["goals"] >= 1
    # schedule
    from core.schedule import format_world_schedule

    WorldStateRepository.set(
        "director",
        {
            "last_run_ts": time.time(),
            "last_trigger": "test",
            "last_source": "local",
            "last_error": "",
            "last_accepted": 1,
            "active": [d],
            "history": [],
            "stats": {"runs": 1, "accepted": 1, "rejected": 0},
        },
    )
    sch = format_world_schedule(viewer_id="dir_player_b")
    assert "天道导演" in sch["text"]
    print("✓ 落账目标 + 世情天道节 + 秘境 force_open")


def test_heaven_command_board_and_run():
    init_db()
    _reset_director()
    import config

    old_local = config.ALLOW_LOCAL_AI
    old_key = config.LLM_API_KEY
    old_cc = config.USE_CCSWITCH
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    try:
        r = handle_heaven_command("/天道", ["/天道"])
        assert r["ok"] is True and "天道导演" in r["text"]
        r2 = handle_heaven_command("/天道", ["/天道", "推演"])
        assert "天道导演" in r2["text"]
        assert r2["ok"] is True  # local 降级可推演
        assert r2["director"]["ok"] is True
    finally:
        config.ALLOW_LOCAL_AI = old_local
        config.LLM_API_KEY = old_key
        config.USE_CCSWITCH = old_cc
        _reset_director()
    print("✓ /天道 与 /天道 推演")


def test_world_server_route():
    init_db()
    _reset_director()
    import config

    old_local = config.ALLOW_LOCAL_AI
    old_key = config.LLM_API_KEY
    old_cc = config.USE_CCSWITCH
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    try:
        w = World(auto_tick=False)
        sess = w.join("导演测试员", user_id="dir_cli_user")
        token = sess.get("token")
        assert token, sess
        r = w.handle(token, "/天道")
        assert r.get("ok") is True, r
        assert "天道导演" in r.get("text", "")
        print("✓ 服务器 /天道 路由")
    finally:
        config.ALLOW_LOCAL_AI = old_local
        config.LLM_API_KEY = old_key
        config.USE_CCSWITCH = old_cc
        _reset_director()


if __name__ == "__main__":
    test_admit_rejects_illegal_type_and_strips_numeric_effects()
    test_admit_calamity_window_and_realm()
    test_local_director_run_persists_and_channel()
    test_no_ai_no_local_blocks_without_fake()
    test_cooldown_and_force()
    test_secret_realm_force_open()
    test_apply_secret_realm_pressure_goal_and_channel()
    test_heaven_command_board_and_run()
    test_world_server_route()
    print("\nworld_director tests all passed")
