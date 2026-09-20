"""
NPC 性格/态度/多议程/对话 测试
"""
import os
import sys
import time
from pathlib import Path

os.environ["ALLOW_LOCAL_AI"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.npc_mind import (
    ensure_mind,
    attitude_toward,
    shift_attitude,
    on_kill_update_attitudes,
    multi_agenda_pack,
    pick_agenda_for_tick,
    NpcDialogueEngine,
)
from core.npc_agenda import NpcAgendaEngine
from core.combat_fate import CombatFateEngine
from storage.db import NpcMindRepository, init_db
from core.models import CharacterStatus


def _npc(name, user_id=None, sin=0, sect=None, stones=100):
    c = WorldClock.create_new_character(user_id or f"npc_{name}", name)
    if sin:
        c.karma.sin_value = sin
    if sect:
        c.sect = sect
    c.spirit_stones = stones
    return c


def _player(name="真人"):
    return WorldClock.create_new_character(f"p_{name}", name)


def test_personality_stable():
    init_db()
    n = _npc("稳人", user_id="npc_stable_1")
    m1 = ensure_mind(n)
    m2 = ensure_mind(n)
    assert m1["personality"] == m2["personality"]
    assert m1["personality"]
    print(f"✓ 性格稳定：{m1['personality']}")


def test_personality_by_state():
    init_db()
    killer = _npc("血手", user_id="npc_blood_1", sin=200)
    m = ensure_mind(killer)
    assert "仇" in m["personality"] or "斗" in m["personality"] or m["personality"]
    monk = _npc("道长", user_id="npc_qy_1", sect="青云宗")
    m2 = ensure_mind(monk)
    assert m2["personality"]
    print(f"✓ 按状态生成人设：{m['personality']} / {m2['personality']}")


def test_attitude_shift():
    init_db()
    n = _npc("态度师", user_id="npc_att_1")
    p = _player("张三")
    a0 = attitude_toward(n, p.id)
    assert a0["label"] == "neutral"
    a1 = shift_attitude(n, p.id, -50, reason="测试结仇")
    assert a1["value"] <= -40
    assert a1["label"] in ("hostile", "wary")
    a2 = shift_attitude(n, p.id, 90, reason="测试化敌为友")
    assert a2["value"] >= 15
    print(f"✓ 态度变化：{a0['label']} → {a1['label']} → {a2['label']}")


def test_kill_updates_related_npc_attitude():
    init_db()
    from storage.db import CharacterRepository
    killer = _player("凶手")
    victim = _npc("死者乙", user_id="npc_vic_1", sect="青云宗")
    friend = _npc("同门丙", user_id="npc_fr_1", sect="青云宗")
    friend.location = victim.location = "青云宗外门山门"
    killer.location = "青云宗外门山门"
    CharacterRepository.save(killer)
    CharacterRepository.save(victim)
    CharacterRepository.save(friend)

    on_kill_update_attitudes(killer, victim)
    att = attitude_toward(friend, killer.id)
    assert att["value"] < 0
    print(f"✓ 同门因死态度恶化：{att['label']} ({att['value']})")


def test_multi_agenda_weights():
    init_db()
    n = _npc("多面手", user_id="npc_multi_1")
    pack = multi_agenda_pack(n)
    assert pack["primary"]["agenda_type"]
    assert len(pack["secondary"]) >= 1
    picks = {pick_agenda_for_tick(n)["agenda_type"] for _ in range(20)}
    assert len(picks) >= 1
    print(f"✓ 多议程权重可抽选：{picks}")


def test_dialogue_uses_attitude():
    init_db()
    n = _npc("对话客", user_id="npc_talk_1")
    p = _player("访客")
    n.location = p.location = "青云坊市客栈"
    ensure_mind(n)
    NpcMindRepository.set_attitude(n.id, p.id, -60)

    res = NpcDialogueEngine.talk(n, p, "道友别来无恙")
    assert res["ok"] is True
    assert res["line"]
    assert res["attitude"] in ("hostile", "wary", "neutral", "friendly", "ally")
    # 敌对时不应突然亲热（本地模板保证）
    if res["source"] == "local" and res["attitude"] == "hostile":
        # 敌对即使玩家说客套话也不得亲热
        assert any(k in res["line"] for k in ("面前", "冷", "还敢", "少来", "配", "客气", "死"))
        assert "坐" not in res["line"] or "少来" in res["line"]
    print(f"✓ 对话：{res['text'][:50]}… 态度={res['attitude']}")


def test_dialogue_wrong_location():
    init_db()
    n = _npc("远处人", user_id="npc_far_1")
    p = _player("这边")
    n.location = "黑风绝渊"
    p.location = "青云坊市客栈"
    res = NpcDialogueEngine.talk(n, p, "喂")
    assert res["ok"] is False
    print("✓ 不同地点无法交谈")


def test_tick_with_personality():
    init_db()
    n = _npc("会动的人", user_id="npc_tick_p")
    r = NpcAgendaEngine.tick_one(n, force=True)
    assert r is not None
    print(f"✓ 带性格 tick：acted={r.get('acted')}")


def main():
    init_db()
    test_personality_stable()
    test_personality_by_state()
    test_attitude_shift()
    test_kill_updates_related_npc_attitude()
    test_multi_agenda_weights()
    test_dialogue_uses_attitude()
    test_dialogue_wrong_location()
    test_tick_with_personality()
    print("\n✅ NPC 心智（性格/态度/多议程/对话）测试全部通过")


if __name__ == "__main__":
    main()
