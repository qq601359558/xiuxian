"""导师提案多样性：世界态势应驱动非 omen 类型"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, WorldStateRepository, CharacterRepository
from core.clock import WorldClock
from core.era_reentry import seed_local_directives, variety_seeds_from_world, TAG_TO_TYPE
from core.world_director import admit_directive, apply_directive, WorldDirector
from core import faction
from core.hunt import is_marked


def _reset():
    WorldStateRepository.set("director", {
        "last_run_ts": 0, "last_trigger": "", "last_source": "", "last_error": "",
        "last_accepted": 0, "active": [], "history": [], "player_events": [],
        "stats": {"runs": 0, "accepted": 0, "rejected": 0, "attempts": 0},
    })
    WorldStateRepository.set("faction", {
        "relations": {}, "missions": [], "sieges": [], "log": [],
        "stats": {"missions_open": 0, "missions_done": 0, "sieges": 0, "shifts": 0},
    })
    WorldStateRepository.set("era_legacy", {
        "current_season": 0, "completed_eras": [], "active_bias": {}, "anchors": [],
        "last_reentry_ts": 0, "last_apocalypse_season": 0, "cited_count": 0, "log": [],
    })
    WorldStateRepository.set("player_echo", {
        "echoes": {}, "region": {},
        "market": {"buy_mult": 1.0, "sell_mult": 1.0, "panic": 0.0, "reason": ""},
        "bounty": {"n_marked": 0, "pool_bonus": 0, "hunt_heat": 1.0},
        "mood": {"blood_index": 0.0, "fear_index": 0.0},
        "log": [],
        "stats": {"kills_recorded": 0, "region_updates": 0, "market_shifts": 0, "director_wakes": 0},
    })
    WorldStateRepository.set("legends", [])


def test_world_arc_tag_not_forced_to_omen():
    assert "world_arc" not in TAG_TO_TYPE
    print("✓ world_arc 标签不再硬推 omen")


def test_variety_seeds_from_siege_and_hostile():
    init_db()
    _reset()
    victim = WorldClock.create_new_character("npc_var_siege", "血煞目标")
    victim.karma.add_sin(200)
    victim.karma.blood_mark_until = __import__("time").time() + 9999
    victim.location = "黑风绝渊"
    CharacterRepository.save(victim)
    assert is_marked(victim)
    faction.ensure_defaults()
    faction.shift_relation("青云宗", "九幽天魔宗", -30, note="test")
    res = faction.open_siege("青云宗", victim, reason="测试", source="test")
    assert res.get("success"), res
    seeds = seed_local_directives()
    types = {s["type"] for s in seeds}
    assert "omen" not in types or len(types) > 1
    v = variety_seeds_from_world()
    vt = {s["type"] for s in v}
    assert "omen" not in vt
    assert "blood_tide" in vt or "sect_tension" in vt or "faction_order" in vt
    # admit 至少一条非 omen
    ok_any = False
    for s in v:
        ok, _, item = admit_directive(s)
        if ok and item and item["type"] != "omen":
            ok_any = True
            break
    assert ok_any
    print("✓ 围剿/敌对驱动多样性种子", vt)


def test_local_run_not_all_omen():
    init_db()
    _reset()
    import config

    old = (config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH)
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    try:
        victim = WorldClock.create_new_character("npc_var_s2", "重业者")
        victim.karma.add_sin(200)
        victim.karma.blood_mark_until = __import__("time").time() + 9999
        victim.location = "落霞山灵泉"
        CharacterRepository.save(victim)
        faction.ensure_defaults()
        faction.open_siege("青云宗", victim, reason="t", source="test")
        res = WorldDirector.run_cycle(trigger="test", force=True)
        assert res.get("ok") is True, res
        types = [d.get("type") for d in (res.get("directives") or [])]
        assert types
        assert set(types) != {"omen"}, types
        print("✓ 一轮提案类型", types)
    finally:
        config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH = old
        _reset()


if __name__ == "__main__":
    test_world_arc_tag_not_forced_to_omen()
    test_variety_seeds_from_siege_and_hostile()
    test_local_run_not_all_omen()
    print("\nvariety tests passed")
