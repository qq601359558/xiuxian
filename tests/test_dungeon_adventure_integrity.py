"""
秘境副本与历练探险的道体合规守恒测试
"""
import pytest
from core.clock import WorldClock
from core.dungeon import DungeonEngine
from core.adventure import AdventureEngine, ADVENTURE_FEE
from core.models import CharacterStatus
from core.items import ItemEntity, ItemKind
from storage.db import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def _make_traveler(name: str, stones: int = 200):
    c = WorldClock.create_new_character(f"d_{name}", name)
    c.spirit_stones = stones
    return c


def test_dungeon_start_blocked_when_bag_full():
    c = _make_traveler("满囊修士", stones=100)
    # 塞满 64 格
    c.items = [
        ItemEntity(name=f"矿石_{i}", kind=ItemKind.MATERIAL) for i in range(64)
    ]
    res = DungeonEngine.start_dungeon(c)
    assert res["success"] is False
    assert "纳戒百宝囊已满" in res["message"]


def test_dungeon_start_blocked_when_insufficient_stones():
    c = _make_traveler("赤贫散修", stones=10)
    # 开启法阵需 30 灵石
    res = DungeonEngine.start_dungeon(c)
    assert res["success"] is False
    assert "灵石不足" in res["message"]


def test_adventure_blocked_when_bag_full():
    c = _make_traveler("行者", stones=200)
    c.items = [
        ItemEntity(name=f"杂草_{i}", kind=ItemKind.CONSUMABLE) for i in range(64)
    ]
    res = AdventureEngine.explore(c, use_ai=False)
    assert res["success"] is False
    assert "纳戒百宝囊已满" in res["message"]


def test_adventure_blocked_when_insufficient_fee():
    c = _make_traveler("无资修士", stones=ADVENTURE_FEE - 1)
    res = AdventureEngine.explore(c, use_ai=False)
    assert res["success"] is False
    assert "灵石不足" in res["message"]
