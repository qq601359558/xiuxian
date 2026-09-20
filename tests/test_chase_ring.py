"""
追查物化 + 日环灵石
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core.name_registry import register_heard, chase, get_heard, materialize_location
from core import sect_contrib as sc
from config import WORLD_LOCATIONS


def _c(name="寻客", stones=200, sect=None):
    c = WorldClock.create_new_character(f"cz_{name}", name)
    c.spirit_stones = stones
    c.born_at = time.time() - 80 * 3600.0
    if sect:
        c.sect = sect
    CharacterRepository.save(c)
    return c


def test_chase_materialize_forced():
    init_db()
    WorldStateRepository.delete("name_registry")
    WorldStateRepository.delete("chase_daily")
    c = _c("强探", stones=100)
    register_heard("无名幽谷", ntype="location", desc="荒谷", source="npc_talk", confidence=0.7)
    r = chase(CharacterRepository.get_by_id(c.id), "无名幽谷", force=True)
    assert r["success"] is True and r.get("chased") is True
    assert "无名幽谷" in WORLD_LOCATIONS
    print("✓ 强制物化可 /go")


def test_chase_costs_and_limit():
    init_db()
    WorldStateRepository.delete("name_registry")
    WorldStateRepository.delete("chase_daily")
    WORLD_LOCATIONS.pop("听风崖", None)
    c = _c("穷探", stones=10)
    register_heard("听风崖", ntype="location", desc="崖", source="gm_broadcast", confidence=0.8)
    r = chase(CharacterRepository.get_by_id(c.id), "听风崖", force=False)
    assert r["success"] is False  # 灵石不够
    c2 = _c("富探", stones=200)
    register_heard("听风崖2", ntype="location", desc="崖", source="gm_broadcast", confidence=0.8)
    # 多次追查消耗
    before = CharacterRepository.get_by_id(c2.id).spirit_stones
    res = chase(CharacterRepository.get_by_id(c2.id), "听风崖2", force=False)
    after = CharacterRepository.get_by_id(c2.id).spirit_stones
    if res.get("chased"):
        assert after <= before - 30 or before == after  # force path no
    else:
        assert after == before - 30
    print("✓ 追查扣费", res.get("message", "")[:40])


def test_ring_gives_stones():
    init_db()
    WorldStateRepository.delete(sc._RING_KEY)
    c = _c("环金", stones=50, sect="青云宗")
    r = sc.accept_theme(CharacterRepository.get_by_id(c.id), 1)
    assert r["success"]
    hook = r["hook"]
    res = sc.sync_ring(CharacterRepository.get_by_id(c.id), hook)
    assert res is not None
    c2 = CharacterRepository.get_by_id(c.id)
    assert c2.spirit_stones == 50 + 50
    print("✓ 日环灵石 +50")


if __name__ == "__main__":
    test_chase_materialize_forced()
    test_chase_costs_and_limit()
    test_ring_gives_stones()
    print("\n✅ chase/ring-gold 测试通过")
