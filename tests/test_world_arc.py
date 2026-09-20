"""
M2 世界弧：起弧 → 升级 → 决算 → 传说/修饰
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "0")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, WorldStateRepository
from core.world_arc import (
    active_arcs,
    advance_arc,
    format_arc_board,
    handle_arc_command,
    spawn_from_directive,
    tick_world,
    agenda_bias_from_arcs,
    _KEY as ARC_KEY,
)
from core.world_director import (
    WorldDirector,
    admit_directive,
    apply_directive,
    world_modifiers,
    location_heat,
    agenda_bias_for_npc,
)
from core.clock import WorldClock
from storage.db import CharacterRepository
from config import SECRET_REALMS


def _reset_channel():
    import core.world_channel as wc

    wc._recent_keys.clear()
    wc._min_window_start = 0.0
    wc._min_count = 0


def _reset_arcs():
    WorldStateRepository.set(
        ARC_KEY,
        {"arcs": [], "history": [], "stats": {"spawned": 0, "advanced": 0, "climaxed": 0}},
    )
    WorldStateRepository.set(
        "director",
        {
            "last_run_ts": 0.0,
            "last_trigger": "",
            "last_source": "",
            "last_error": "",
            "last_accepted": 0,
            "active": [],
            "history": [],
            "player_events": [],
            "stats": {"runs": 0, "accepted": 0, "rejected": 0, "attempts": 0},
        },
    )
    _reset_channel()


def _blood_directive(loc="黑风绝渊"):
    ok, _, d = admit_directive(
        {
            "type": "blood_tide",
            "title": "血煞潮起",
            "narrative": "绝渊血气翻涌",
            "location": loc,
            "effects": {"location": loc, "whisper": "潮"},
        }
    )
    assert ok
    d["source"] = "test"
    d["applied"] = apply_directive(d)
    return d


def test_spawn_escalate_climax_legend():
    init_db()
    _reset_arcs()
    rid = next(iter(SECRET_REALMS.keys()))
    d_loc = SECRET_REALMS[rid]["location"]
    ok, _, d = admit_directive(
        {
            "type": "secret_realm_pressure",
            "title": "禁制松动",
            "narrative": f"【{rid}】有风暴酝酿",
            "location": d_loc,
            "effects": {"realm_id": rid, "force_open": True},
        }
    )
    assert ok
    d["source"] = "test"
    apply_directive(d)
    arc = spawn_from_directive(d, force=True)
    assert arc is not None
    assert arc["stage"] == "prophesy"
    assert arc["kind"] == "realm_storm"
    board = format_arc_board()
    assert "世界弧" in board and "预兆" in board
    # 未到期不可推进
    r_skip = advance_arc(arc["id"], force=False)
    assert r_skip.get("ok") is False
    # 强制升级
    r1 = advance_arc(arc["id"], force=True)
    assert r1["ok"] is True and r1["stage"] == "escalate"
    # 升级应尝试开秘境
    from core.secret_realm import realm_status

    rows = {r["name"]: r for r in realm_status()}
    assert rows[rid]["is_open"] is True
    # 强制决算 → 传说
    r2 = advance_arc(arc["id"], force=True)
    assert r2["ok"] is True and r2["stage"] == "climax"
    from core.legends import list_legends

    texts = " ".join(x.text + x.title for x in list_legends(limit=10))
    assert arc["title"] in texts or "禁制" in texts or "风暴" in texts
    assert active_arcs() == []
    _reset_arcs()
    print("✓ 世界弧起→升→决算→传说")


def test_dedupe_and_modifiers_and_bias():
    init_db()
    _reset_arcs()
    d = _blood_directive("黑风绝渊")
    a1 = spawn_from_directive(d, force=True)
    assert a1 is not None
    a2 = spawn_from_directive(d, force=False)
    assert a2 is None  # 同 kind+loc 去重
    mods = world_modifiers()
    assert "黑风绝渊" in mods["blood_tide_locations"]
    assert mods["hunt_heat"] >= 1.25
    assert location_heat("黑风绝渊") >= 1.2
    npc = WorldClock.create_new_character("arc_npc", "绝渊客")
    npc.location = "黑风绝渊"
    npc.sect = ""
    CharacterRepository.save(npc)
    bias = agenda_bias_from_arcs(npc)
    assert bias and "世界弧" in bias["note"]
    # director bias 也会读弧
    b2 = agenda_bias_for_npc(npc)
    assert b2 and ("世界弧" in b2["note"] or "血煞" in b2["note"])
    _reset_arcs()
    print("✓ 弧去重 + 世界修饰 + NPC 偏置")


def test_tick_auto_advance():
    init_db()
    _reset_arcs()
    # 缩短阶段窗
    import config

    old_p, old_e = config.WORLD_ARC_PROPHESY_SEC, config.WORLD_ARC_ESCALATE_SEC
    config.WORLD_ARC_PROPHESY_SEC = 1.0
    config.WORLD_ARC_ESCALATE_SEC = 1.0
    try:
        d = _blood_directive("落霞山灵泉")
        arc = spawn_from_directive(d, force=True)
        assert arc["stage"] == "prophesy"
        acted = tick_world(now=time.time() + 2.0, max_advance=3)
        assert acted, "到期应自动推进"
        # 可能一次 tick 连推到 climax（deadline 重算）
        arcs_now = active_arcs(now=time.time() + 2.0)
        stages = [a.get("stage") for a in arcs_now]
        assert stages in ([], ["escalate"], ["climax"]) or not arcs_now
        board = handle_arc_command(["/世界弧"])[ "text"]
        assert "世界弧" in board
    finally:
        config.WORLD_ARC_PROPHESY_SEC = old_p
        config.WORLD_ARC_ESCALATE_SEC = old_e
        _reset_arcs()
    print("✓ tick 到期自动推进")


def test_director_run_spawns_arc():
    init_db()
    _reset_arcs()
    import config

    old = (config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH)
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    try:
        res = WorldDirector.run_cycle(trigger="test", force=True)
        assert res["ok"] is True
        # local 降级至少可能产出 omen/blood/secret 之一 → 可能起弧
        board = format_arc_board()
        assert "世界弧" in board
        # 无弧时也应有友好空态
        mods = world_modifiers()
        assert "hunt_heat" in mods
    finally:
        config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH = old
        _reset_arcs()
    print("✓ 导演周期可吸收为世界弧")


def test_server_arc_route():
    init_db()
    _reset_arcs()
    import config

    old = (config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH)
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    try:
        w = World(auto_tick=False)
        sess = w.join("弧观测者", user_id="arc_cli_user")
        tok = sess["token"]
        r = w.handle(tok, "/世界弧")
        assert r.get("ok") is True
        assert "世界弧" in r.get("text", "")
        r2 = w.handle(tok, "/天道")
        assert "天道导演" in r2.get("text", "")
    finally:
        config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH = old
        _reset_arcs()
    print("✓ 服务器 /世界弧 路由")


if __name__ == "__main__":
    test_spawn_escalate_climax_legend()
    test_dedupe_and_modifiers_and_bias()
    test_tick_auto_advance()
    test_director_run_spawns_arc()
    test_server_arc_route()
    print("\nworld_arc tests all passed")
