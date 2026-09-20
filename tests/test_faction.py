"""
M3 势力操盘：关系 / 宗门令 / 围剿 / 导师指令 / 敌对修正
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "0")

from storage.db import init_db, WorldStateRepository, CharacterRepository
from core.clock import WorldClock
from core import faction
from core.faction import (
    get_relation,
    shift_relation,
    status_from_score,
    open_mission,
    accept_mission,
    complete_mission,
    open_siege,
    active_sieges,
    format_faction_board,
    hostile_power_bonus,
    location_faction_heat,
    director_apply_faction_order,
    director_apply_sect_siege,
    on_director_sect_tension,
    on_sect_crisis_climax,
    tick_world,
    _KEY as FKEY,
)
from core.world_director import admit_directive, apply_directive, world_modifiers
from core.hunt import is_marked


def _reset():
    WorldStateRepository.set(
        FKEY,
        {
            "relations": {},
            "missions": [],
            "sieges": [],
            "log": [],
            "stats": {"missions_open": 0, "missions_done": 0, "sieges": 0, "shifts": 0},
        },
    )
    WorldStateRepository.set(
        "director",
        {
            "last_run_ts": 0,
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
    try:
        from core.world_arc import _KEY as AKEY

        WorldStateRepository.set(AKEY, {"arcs": [], "history": [], "stats": {"spawned": 0, "advanced": 0, "climaxed": 0}})
    except Exception:
        pass


def _char(name, uid=None, sect=None, loc="青云坊市客栈", sin=0):
    c = WorldClock.create_new_character(uid or f"fac_{name}", name)
    c.sect = sect
    c.location = loc
    if sin:
        c.karma.add_sin(sin)
        try:
            c.karma.blood_mark_until = time.time() + 3600
        except Exception:
            pass
    CharacterRepository.save(c)
    return c


def test_relation_shift_and_status():
    init_db()
    _reset()
    r0 = get_relation("青云宗", "九幽天魔宗")
    assert r0["score"] < 0
    assert status_from_score(-55) == "hostile"
    res = shift_relation("青云宗", "九幽天魔宗", -20, note="测试敌对加深")
    assert res["ok"]
    r1 = get_relation("青云宗", "九幽天魔宗")
    assert r1["status"] == "hostile"
    assert r1["score"] < r0["score"]
    assert hostile_power_bonus("青云宗", "九幽天魔宗") > 1.0
    assert location_faction_heat("九幽天魔宗坛", "青云宗") >= 1.2
    board = format_faction_board()
    assert "天下势力" in board and "敌对" in board
    _reset()
    print("✓ 关系分/敌对修正/势力板")


def test_mission_accept_complete():
    init_db()
    _reset()
    m = open_mission("青云宗", "patrol", location="青云宗外门山门", title="巡守山门")
    assert m
    p = _char("巡山弟子", uid="npc_patrol_1", sect="青云宗", loc="青云坊市客栈")
    r = accept_mission(p, m["id"])
    assert r["success"]
    bad = complete_mission(p, m["id"])
    assert bad["success"] is False  # 不在山门
    p.location = "青云宗外门山门"
    CharacterRepository.save(p)
    ok = complete_mission(p, m["id"])
    assert ok["success"], ok
    assert p.sect_contribution >= 8
    _reset()
    print("✓ 宗门令接取与验收")


def test_director_faction_order_and_siege():
    init_db()
    _reset()
    ok, _, d = admit_directive(
        {
            "type": "faction_order",
            "title": "抵制魔门",
            "narrative": "青云宗示下，少与魔门往来",
            "effects": {"sect": "青云宗", "order_kind": "boycott", "target_sect": "九幽天魔宗"},
        }
    )
    assert ok, d
    applied = apply_directive(d)
    assert any("faction_order_ok" in f for f in applied["flags"]), applied
    # 血煞目标 + 宗门围剿指令
    victim = _char("血刀凶人", uid="npc_blood_siege", sect="九幽天魔宗", loc="黑风绝渊", sin=200)
    assert is_marked(victim)
    ok2, _, d2 = admit_directive(
        {
            "type": "sect_siege",
            "title": "正道除魔",
            "narrative": "青云宗号令围剿",
            "effects": {"sect": "青云宗", "target_name": victim.name},
        }
    )
    assert ok2, d2
    ap2 = apply_directive(d2)
    assert any("siege_ok" in f for f in ap2["flags"]), ap2
    sieges = active_sieges()
    assert sieges and sieges[0]["target_name"] == victim.name
    mods = world_modifiers()
    assert mods.get("faction", {}).get("active_sieges")
    # 非法 sect
    ok3, reason, _ = admit_directive(
        {
            "type": "faction_order",
            "title": "x",
            "narrative": "y",
            "effects": {"sect": "不存在宗门", "order_kind": "patrol"},
        }
    )
    assert ok3 is False
    _reset()
    print("✓ 导师 faction_order / sect_siege 落账")


def test_sect_tension_syncs_faction():
    init_db()
    _reset()
    before = get_relation("青云宗", "万剑仙门")["score"]
    ok, _, d = admit_directive(
        {
            "type": "sect_tension",
            "title": "龃龉",
            "narrative": "两宗不睦",
            "effects": {"sect_a": "青云宗", "sect_b": "万剑仙门"},
        }
    )
    assert ok
    apply_directive(d)
    after = get_relation("青云宗", "万剑仙门")["score"]
    assert after < before
    # 紧张后应有抵制令
    from core.faction import list_missions

    ms = list_missions(status="open")
    assert any(m.get("kind") == "boycott" for m in ms), ms
    _reset()
    print("✓ 宗门紧张同步势力关系与抵制令")


def test_arc_climax_faction_and_siege():
    init_db()
    _reset()
    from core.world_arc import spawn_from_directive, advance_arc
    from core.hunt import accept as hunt_accept

    ok, _, d = admit_directive(
        {
            "type": "sect_tension",
            "title": "两宗对峙",
            "narrative": "剑拔弩张",
            "effects": {"sect_a": "青云宗", "sect_b": "九幽天魔宗"},
        }
    )
    assert ok
    apply_directive(d)
    arc = spawn_from_directive({**d, "source": "test"}, force=True)
    assert arc["kind"] == "sect_crisis"
    r1 = advance_arc(arc["id"], force=True)
    assert r1["ok"]
    r2 = advance_arc(arc["id"], force=True)
    assert r2["ok"]
    # 决算后关系被弧钩子改动
    rel = get_relation("青云宗", "九幽天魔宗")
    assert "status" in rel
    board = format_faction_board()
    assert "天下势力" in board
    _reset()
    print("✓ 世界弧宗门危机决算联动势力")


def test_npc_bias_and_tick():
    init_db()
    _reset()
    victim = _char("被围凶人", uid="npc_siege_target", sect="九幽天魔宗", loc="黑风绝渊", sin=220)
    hunter = _char("青云执法", uid="npc_qy_hunter", sect="青云宗", loc="青云宗外门山门")
    res = open_siege("青云宗", victim, reason="测试围剿")
    assert res["success"], res
    from core.world_director import agenda_bias_for_npc

    bias = agenda_bias_for_npc(hunter)
    assert bias and "围剿" in bias["note"]
    # 敌境
    scout = _char("探子", uid="npc_qy_scout", sect="青云宗", loc="九幽天魔宗坛")
    b2 = agenda_bias_for_npc(scout)
    assert b2 and ("敌境" in b2["note"] or "紧张" in b2["note"] or "围剿" in b2["note"])
    # tick 不抛错
    tr = tick_world()
    assert "decayed" in tr
    _reset()
    print("✓ NPC 议程偏置与势力 tick")


def test_server_faction_routes():
    init_db()
    _reset()
    import config

    old = (config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH)
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    try:
        p = _char("宗门弟子", uid="npc_faction_player", sect="青云宗", loc="青云坊市客栈")
        m = open_mission("青云宗", "patrol", location="青云宗外门山门")
        w = World(auto_tick=False)
        sess = w.join("宗门弟子", user_id="faction_player_user")
        tok = sess["token"]
        # join 可能复用角色，确保有宗籍
        ch = w.get_char(tok)
        ch.sect = "青云宗"
        CharacterRepository.save(ch)
        r = w.handle(tok, "/势力")
        assert r.get("ok") is True and "天下势力" in r.get("text", "")
        r2 = w.handle(tok, "/宗门令")
        assert r2.get("ok") is True
        r3 = w.handle(tok, f"/接宗门令 {m['id']}")
        assert r3.get("ok") is True, r3
        r4 = w.handle(tok, "/宗门势")
        assert r4.get("ok") is True
        r5 = w.handle(tok, "/天道")
        assert "天道导演" in r5.get("text", "")
    finally:
        config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH = old
        _reset()
    print("✓ 服务器 /势力 /宗门令 路由")


def test_admit_strip_keeps_faction_keys():
    init_db()
    _reset()
    ok, _, d = admit_directive(
        {
            "type": "faction_order",
            "title": "令",
            "narrative": "文",
            "effects": {
                "sect": "青云宗",
                "order_kind": "hunt",
                "exp": 9999,
                "stones": 100,
                "target_name": "某人",
            },
        }
    )
    assert ok
    assert "exp" not in d["effects"] and "stones" not in d["effects"]
    assert d["effects"]["sect"] == "青云宗"
    assert d["effects"]["order_kind"] == "hunt"
    print("✓ 势力指令数值键剥离")


if __name__ == "__main__":
    test_relation_shift_and_status()
    test_mission_accept_complete()
    test_director_faction_order_and_siege()
    test_sect_tension_syncs_faction()
    test_arc_climax_faction_and_siege()
    test_npc_bias_and_tick()
    test_server_faction_routes()
    test_admit_strip_keeps_faction_keys()
    print("\nfaction tests all passed")
