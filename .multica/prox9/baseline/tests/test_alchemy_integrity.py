"""
炼丹与炼器系统的道体合规守恒测试
"""
import pytest
from core.clock import WorldClock
from core.alchemy import craft, learn_recipe, ensure_default_recipes
from core.models import CharacterStatus
from core.items import ItemEntity, ItemKind
from storage.db import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def _make_crafter(name: str, stones: int = 200):
    c = WorldClock.create_new_character(f"alc_{name}", name)
    c.spirit_stones = stones
    ensure_default_recipes(c)
    return c


def test_craft_blocked_when_bag_full():
    c = _make_crafter("满囊丹修", stones=500)
    # 把纳戒塞满 64 格
    c.items = [
        ItemEntity(name=f"废渣_{i}", kind=ItemKind.CONSUMABLE) for i in range(64)
    ]
    # 给足够材料（聚气草×2）
    c.inventory.extend(["聚气草", "聚气草"])

    res = craft(c, "初阶聚气丹", "pill")
    assert res["success"] is False
    assert "纳戒百宝囊已满" in res["message"]


def test_craft_blocked_when_insufficient_stones():
    c = _make_crafter("赤贫丹修", stones=0)
    c.inventory.extend(["聚气草", "聚气草"])

    # 开炉需 15 灵石
    res = craft(c, "聚气丹", "pill")
    assert res["success"] is False
    assert "开炉需" in res["message"] and "灵石不足" in res["message"]


def test_craft_blocked_when_dead_or_meditating():
    c = _make_crafter("入定修士", stones=100)
    c.inventory.extend(["聚气草", "聚气草"])
    c.status = CharacterStatus.MEDITATING

    res = craft(c, "初阶聚气丹", "pill")
    assert res["success"] is False
    assert "闭关锁门" in res["message"]

    c.status = CharacterStatus.DEAD
    c.death_cause = "寿尽"
    res2 = craft(c, "初阶聚气丹", "pill")
    assert res2["success"] is False
    assert "已坐化道消" in res2["message"]
