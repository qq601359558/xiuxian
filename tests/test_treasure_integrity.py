"""
藏宝探险系统的道体合规守恒测试
"""
import pytest
from core.clock import WorldClock
from core.treasure_system import TreasureEngine, TreasureArchetype
from core.models import CharacterStatus
from core.items import ItemEntity, ItemKind
from storage.db import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def _make_explorer(name: str):
    c = WorldClock.create_new_character(f"t_{name}", name)
    c.location = "青云坊市客栈"
    # 给一张藏宝图
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target="青云坊市客栈"
    )
    c.add_item_entity(tmap)
    return c


def test_dig_blocked_when_bag_full():
    c = _make_explorer("满囊探修")
    # 把剩下的格子全部塞满至 64 格
    needed = c.MAX_BAG_SLOTS - len(c.items)
    for i in range(needed):
        c.items.append(ItemEntity(name=f"杂灵矿_{i}", kind=ItemKind.MATERIAL))

    res = TreasureEngine.dig(c)
    assert res["success"] is False
    assert "纳戒百宝囊已满" in res["message"]


def test_dig_blocked_when_dead():
    c = _make_explorer("坐化探修")
    c.status = CharacterStatus.DEAD
    c.death_cause = "寿尽"
    res = TreasureEngine.dig(c)
    assert res["success"] is False
    assert "已坐化道消" in res["message"]


def test_dig_blocked_when_meditating():
    c = _make_explorer("闭关探修")
    c.status = CharacterStatus.MEDITATING
    res = TreasureEngine.dig(c)
    assert res["success"] is False
    assert "闭关锁门" in res["message"]


def test_dig_blocked_when_captured():
    c = _make_explorer("被擒探修")
    c.status = CharacterStatus.CAPTURED
    res = TreasureEngine.dig(c)
    assert res["success"] is False
    assert "身陷囹圄" in res["message"]
