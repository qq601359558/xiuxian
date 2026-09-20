"""性格化副议程 + 关服结算辅助测试"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.npc_mind import (
    ensure_mind,
    multi_agenda_pack,
    _secondary_for_personality,
    NpcMindRepository,
)
from storage.db import NpcAgendaRepository, init_db


def test_secondary_by_personality():
    init_db()
    n = WorldClock.create_new_character("npc_pers_sec", "性格副议程")
    NpcMindRepository.upsert(n.id, "阴鸷记仇", {}, {})
    NpcAgendaRepository.upsert(
        npc_id=n.id, npc_name=n.name, agenda_type="survive",
        note="测试", state="active", last_tick=0, progress=0,
    )
    pack = multi_agenda_pack(n)
    types = [s["agenda_type"] for s in pack["secondary"]]
    assert len(types) >= 1
    assert "revenge" in types or "social" in types
    notes = " ".join(s.get("note", "") for s in pack["secondary"])
    assert "仇" in notes or "打听" in notes
    print(f"✓ 阴鸷记仇副议程：{pack['secondary']}")

    greedy = _secondary_for_personality("贪财好利", "social")
    assert any(x["agenda_type"] == "treasure" for x in greedy)
    print(f"✓ 贪财好利偏好夺宝：{greedy}")

    proud = _secondary_for_personality("清高自持", "patrol")
    assert any(x["agenda_type"] == "seclusion" for x in proud)
    print(f"✓ 清高自持偏好闭关：{proud}")


def test_secondary_not_same_as_primary():
    init_db()
    n = WorldClock.create_new_character("npc_no_dup", "不重复")
    NpcMindRepository.upsert(n.id, "莽撞好斗", {}, {})
    NpcAgendaRepository.upsert(
        npc_id=n.id, npc_name=n.name, agenda_type="patrol",
        note="主", state="active", last_tick=0, progress=0,
    )
    pack = multi_agenda_pack(n)
    for s in pack["secondary"]:
        assert s["agenda_type"] != "patrol"
    print("✓ 副议程不与主议程撞车")


def main():
    test_secondary_by_personality()
    test_secondary_not_same_as_primary()
    print("\n✅ 性格化副议程 测试通过")


if __name__ == "__main__":
    main()
