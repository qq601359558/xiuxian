"""
NPC 议程 tick 测试
"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.npc_agenda import (
    NpcAgendaEngine,
    ensure_agenda,
    default_agenda_for,
    list_npc_characters,
)
from storage.db import NpcAgendaRepository, EventLedgerRepository, init_db
from core.models import CharacterStatus


def _npc(name, user_id=None, sin=0, full=False, sect=None, stones=100):
    c = WorldClock.create_new_character(user_id or f"npc_{name}", name)
    c.karma.sin_value = sin
    if sin:
        c.karma.add_sin(0)  # keep
        c.karma.sin_value = sin
    if full:
        c.realm.current_exp = c.realm.max_exp
    if sect:
        c.sect = sect
    c.spirit_stones = stones
    return c


def test_default_agenda_by_state():
    a = _npc("血魔", sin=200)
    assert default_agenda_for(a)["agenda_type"] in ("survive", "revenge")
    b = _npc("圆满者", full=True)
    assert default_agenda_for(b)["agenda_type"] == "seclusion"
    c = _npc("门徒", sect="青云宗")
    assert default_agenda_for(c)["agenda_type"] == "patrol"
    print("✓ 默认议程按状态生成")


def test_ensure_and_tick_one():
    init_db()
    n = _npc("陆小仙", user_id="npc_test_lu")
    ag = ensure_agenda(n)
    assert ag["npc_id"] == n.id
    assert ag["state"] == "active"

    # 冷却：刚 tick 过应跳过
    NpcAgendaRepository.mark_tick(n.id, last_action="刚动过")
    r_skip = NpcAgendaEngine.tick_one(n, force=False)
    assert r_skip is None

    r = NpcAgendaEngine.tick_one(n, force=True)
    assert r is not None
    assert r.get("ok") is True
    print(f"✓ NPC tick：acted={r.get('acted')} source={r.get('source')} {r.get('narrative','')[:30]}")


def test_tick_writes_ledger():
    init_db()
    n = _npc("记账客", user_id="npc_test_ledger")
    r = NpcAgendaEngine.tick_one(n, force=True)
    if r and r.get("acted"):
        assert r.get("event_id")
        rows = EventLedgerRepository.query_for_memory(n.id, limit=5)
        assert any(x["type"] == "NPC_TICK" for x in rows)
        print("✓ NPC 行动写入事件账")
    else:
        # 静观也应更新 last_tick
        ag = NpcAgendaRepository.get(n.id)
        assert ag and ag["last_tick"] > 0
        print("✓ NPC 静观也更新议程时间戳")


def test_world_tick_batch():
    init_db()
    # 保证世界有 NPC
    _npc("甲修士", user_id="npc_batch_a")
    _npc("乙修士", user_id="npc_batch_b")
    acted = NpcAgendaEngine.tick_world(max_npcs=3, force=True)
    assert isinstance(acted, list)
    print(f"✓ 批量 tick：{len(acted)} 名 NPC 有行动")


def test_player_not_ticked_as_npc():
    init_db()
    p = WorldClock.create_new_character("player_x", "真人玩家")
    assert NpcAgendaEngine.tick_one(p, force=True) is None
    print("✓ 玩家不被当作 NPC tick")


def main():
    init_db()
    test_default_agenda_by_state()
    test_ensure_and_tick_one()
    test_tick_writes_ledger()
    test_world_tick_batch()
    test_player_not_ticked_as_npc()
    print("\n✅ NPC 议程 tick 测试全部通过")


if __name__ == "__main__":
    main()
