"""
M5 纪元回流：传说 bias → 导师提案 → 大劫快照
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "0")

from storage.db import init_db, WorldStateRepository
from core.legends import add_legend, list_legends
from core.era_reentry import (
    compute_legend_bias,
    legend_tags_to_bias,
    rebuild_active_bias,
    on_apocalypse_settle,
    active_bias,
    preferred_directive_types,
    seed_local_directives,
    reorder_by_bias,
    format_era_board,
    handle_era_command,
    _KEY as EKEY,
)
from core.world_director import (
    admit_directive,
    apply_directive,
    gather_world_brief,
    WorldDirector,
    _is_duplicate_directive,
)


def _reset():
    WorldStateRepository.set("legends", [])
    WorldStateRepository.set(
        EKEY,
        {
            "current_season": 0,
            "completed_eras": [],
            "active_bias": {},
            "anchors": [],
            "last_reentry_ts": 0.0,
            "last_apocalypse_season": 0,
            "cited_count": 0,
            "log": [],
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


def test_legend_bias_aggregation():
    init_db()
    _reset()
    add_legend(
        title="血洗黑风",
        text="黑风绝渊血煞潮，多人应劫",
        season=1,
        tags=["world_arc", "blood_feud"],
        weight=3,
    )
    add_legend(
        title="两宗对峙",
        text="青云与九幽对峙暂歇",
        season=1,
        tags=["world_arc", "sect_crisis"],
        weight=2,
    )
    b = compute_legend_bias()
    assert b.get("blood_tide", 0) >= 3
    assert b.get("sect_tension", 0) >= 2
    assert legend_tags_to_bias(["blood_feud"], 2)["blood_tide"] == 2
    print("✓ 传说标签聚合 bias")


def test_apocalypse_snapshot_and_board():
    init_db()
    _reset()
    add_legend(
        title="第1纪血雨",
        text="绝渊凶名昭著",
        season=1,
        tags=["apocalypse", "blood_feud"],
        weight=4,
    )
    add_legend(
        title="秘境风暴",
        text="落霞古洞禁制崩解",
        season=1,
        tags=["world_arc", "realm_storm"],
        weight=2,
    )
    res = on_apocalypse_settle(1)
    assert res["ok"], res
    bias = active_bias()
    assert bias.get("blood_tide", 0) > 0
    # 重复结算幂等
    res2 = on_apocalypse_settle(1)
    assert res2.get("ok") is False
    board = format_era_board()
    assert "纪元回流" in board and "活跃权重" in board
    r = handle_era_command(["/纪元回流"])
    assert r["ok"] and "纪元回流" in r["text"]
    print("✓ 大劫快照与回流面板")


def test_local_director_uses_era_seeds():
    init_db()
    _reset()
    add_legend(
        title="血债未清",
        text="黑风绝渊再起风波",
        season=2,
        tags=["world_arc", "blood_feud"],
        weight=5,
    )
    rebuild_active_bias()
    prefs = preferred_directive_types()
    assert "blood_tide" in prefs
    seeds = seed_local_directives()
    assert seeds and any(s["type"] == "blood_tide" for s in seeds)
    # admit 种子
    ok, _, item = admit_directive(seeds[0])
    assert ok, seeds[0]
    assert item["type"] in ("blood_tide", "sect_tension", "secret_realm_pressure", "omen", "calamity_forecast")
    print("✓ 史笔种子可过门禁")


def test_director_brief_and_run_reflects_bias():
    init_db()
    _reset()
    import config

    old = (config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH)
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    try:
        add_legend(
            title="秘境余威",
            text="落霞古洞旧事",
            season=3,
            tags=["realm_storm"],
            weight=6,
        )
        rebuild_active_bias()
        brief = gather_world_brief()
        assert "纪元回流权重" in brief["text"]
        res = WorldDirector.run_cycle(trigger="test", force=True)
        assert res["ok"] is True
        types = [d.get("type") for d in (res.get("directives") or [])]
        assert types, res
        board = WorldDirector.format_heaven_board()
        assert "天道导演" in board
        # reorder：secret_realm bias 更高时应排前
        rows = [
            {"type": "omen", "priority": 1},
            {"type": "secret_realm_pressure", "priority": 1},
        ]
        ordered = reorder_by_bias(rows)
        assert ordered[0]["type"] == "secret_realm_pressure", ordered
        print("✓ 导师简报/运行接入回流")
    finally:
        config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH = old
        _reset()


def test_server_era_commands():
    init_db()
    _reset()
    import config

    old = (config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH)
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    try:
        add_legend(
            title="大劫记忆",
            text="上纪血火未冷",
            season=4,
            tags=["apocalypse"],
            weight=5,
        )
        on_apocalypse_settle(4)
        w = World(auto_tick=False)
        sess = w.join("史官", user_id="era_cli_user")
        tok = sess["token"]
        r = w.handle(tok, "/纪元回流")
        assert r.get("ok") is True and "纪元回流" in r.get("text", "")
        r2 = w.handle(tok, "/传说")
        assert r2.get("ok") is True
        assert "纪元回流" in r2.get("text", "") or "传说" in r2.get("text", "")
        r3 = w.handle(tok, "/天道")
        assert "天道导演" in r3.get("text", "")
        print("✓ 服务器 /纪元回流 /传说")
    finally:
        config.ALLOW_LOCAL_AI, config.LLM_API_KEY, config.USE_CCSWITCH = old
        _reset()


if __name__ == "__main__":
    test_legend_bias_aggregation()
    test_apocalypse_snapshot_and_board()
    test_local_director_uses_era_seeds()
    test_director_brief_and_run_reflects_bias()
    test_server_era_commands()
    print("\nera_reentry tests all passed")
