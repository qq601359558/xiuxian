"""living-jianghu：因果账 / 离线 NPC / 目标 / 近况 / LAN feed"""
import os
import sys
from pathlib import Path

os.environ["ALLOW_LOCAL_AI"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_jianghu_ledger_write_and_project():
    from storage.db import init_db
    import core.jianghu as jh

    init_db()
    jh.reset_tick_budget()
    eid = jh.append_event(
        kind="npc_agenda",
        actor_ids=["npc_jh_a"],
        actor_names=["甲客"],
        target_ids=["npc_jh_b"],
        location="青云坊市客栈",
        summary="甲客于坊市打探消息",
        rule_result={"action": "talk"},
        narrative="甲客压低声音问起近日血案。",
        source="rule",
    )
    assert eid and eid.startswith("ev_")
    recent = jh.list_recent(limit=50)
    assert any(e.get("id") == eid for e in recent)
    rel = jh.project_related("npc_jh_b", limit=10)
    assert any(e.get("id") == eid for e in rel)
    # 投影行可读
    line = jh.format_event_line(next(e for e in recent if e["id"] == eid))
    assert "甲客" in line or "打探" in line


def test_npc_tick_without_ai_writes_jianghu():
    from storage.db import init_db, CharacterRepository
    from core.npc_agenda import NpcAgendaEngine, ensure_agenda
    from core.clock import WorldClock
    import core.jianghu as jh
    import core.npc_agenda as na

    init_db()
    jh.reset_tick_budget()
    npc = WorldClock.create_new_character("npc_jh_tick", "离线演武人")
    CharacterRepository.save(npc)
    ensure_agenda(npc)
    r = None
    acted = False
    for _ in range(12):
        old = na.ai_ready
        na.ai_ready = lambda: False
        try:
            r = NpcAgendaEngine.tick_one(npc, force=True)
        finally:
            na.ai_ready = old
        if r and r.get("acted"):
            acted = True
            break
    assert r is not None
    assert acted, "local tick 多次强制后应至少行动一次"
    assert r.get("jianghu_id") or r.get("event_id")
    evs = jh.list_recent(limit=40)
    assert any(npc.id in (e.get("actor_ids") or []) for e in evs), "因果账应含该 NPC"


def test_tick_budget_limits_public_events():
    import core.jianghu as jh
    from storage.db import init_db

    init_db()
    jh.reset_tick_budget()
    ids = []
    for i in range(6):
        eid = jh.append_event(
            kind="npc_agenda",
            actor_ids=[f"npc_bud_{i}"],
            actor_names=[f"预算客{i}"],
            summary=f"预算测试事件 {i}",
            enforce_budget=True,
        )
        ids.append(eid)
    ok = [x for x in ids if x]
    assert len(ok) <= jh.TICK_EVENT_BUDGET
    assert len(ok) >= 1


def test_goals_and_briefing():
    from storage.db import init_db, CharacterRepository
    from core.clock import WorldClock
    from core.goals import ensure_goals, format_goals, evaluate_and_complete
    from core.briefing import format_cli, briefing
    import core.jianghu as jh

    init_db()
    c = WorldClock.create_new_character("t_goal_p", "目标客")
    CharacterRepository.save(c)
    jh.append_event(
        kind="player_action",
        actor_ids=["someone_else"],
        actor_names=["旁人"],
        summary="旁人于黑风绝渊夺宝而归",
        location="黑风绝渊",
    )
    items = ensure_goals(c)
    assert items, "应至少生成一条世间目标"
    active = [g for g in items if g.get("status") == "active"]
    assert len(active) <= 6
    assert any(g.get("source") in ("dao", "newbie", "season", "fame", "sect", "omen") for g in active)
    text = format_goals(c)
    assert "目标" in text or "扬名" in text or "宗门" in text or "门庭" in text or "道途" in text
    b = briefing(c)
    assert b["ok"] is True
    assert "世间" in b["text"]
    cli = format_cli(c)
    assert c.name in cli
    # 完成路径不抛错
    evaluate_and_complete(c)
    # 脏数据清理
    CharacterRepository.save(c)  # no-op safety
    import sqlite3
    from storage.db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM characters WHERE user_id=?", ("t_goal_p",))
    conn.commit()
    conn.close()


def test_lan_feed_endpoint_contract():
    from storage.db import init_db
    import core.jianghu as jh
    from core.jianghu import list_recent, format_event_line

    init_db()
    eid = jh.append_event(
        kind="lan",
        actor_ids=["lan_feed_x"],
        actor_names=["联机道友"],
        summary="联机道友完成首战",
        location="青云坊市客栈",
    )
    events = list_recent(limit=10)
    assert any(e.get("id") == eid for e in events)
    lines = [format_event_line(e) for e in events]
    assert lines
    # 与 server 投影逻辑一致：lines 非空且含 summary 片段
    assert any("联机" in ln or "首战" in ln for ln in lines)


def test_prompt_builders_registered():
    from ai.registry import list_scenes, get_scene

    for sid in ("npc_agenda", "npc_talk", "npc_proactive", "combat", "world_event"):
        assert sid in list_scenes(), sid
        assert get_scene(sid) is not None


def main():
    test_jianghu_ledger_write_and_project()
    print("✓ 因果账写入与投影")
    test_npc_tick_without_ai_writes_jianghu()
    print("✓ 无 AI 时 NPC 规则 tick 可落账")
    test_tick_budget_limits_public_events()
    print("✓ tick 事件预算")
    test_goals_and_briefing()
    print("✓ 目标与近况")
    test_lan_feed_endpoint_contract()
    print("✓ LAN feed 投影契约")
    test_prompt_builders_registered()
    print("✓ 场景已注册")
    print("\n✅ living-jianghu 测试通过")


if __name__ == "__main__":
    main()
