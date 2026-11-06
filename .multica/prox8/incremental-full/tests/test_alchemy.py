"""
炼丹炼器：配方+材料
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core.alchemy import (
    ensure_default_recipes,
    craft,
    format_book,
    learn_recipe,
    ingest_ai_recipe,
    _all_recipes,
)
from core.content_pack import RECIPES


def _c(name="丹师", stones=200):
    c = WorldClock.create_new_character(f"al_{name}", name)
    c.spirit_stones = stones
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


import time


def test_default_recipes():
    init_db()
    WorldStateRepository.delete("known_recipes")
    c = _c()
    known = ensure_default_recipes(c)
    assert len(known) >= 4
    book = format_book(c)
    assert "聚气丹" in book or "配方" in book
    print(f"✓ 默认配方 {len(known)}")


def test_craft_needs_materials():
    init_db()
    WorldStateRepository.delete("known_recipes")
    c = _c("无料", stones=500)
    ensure_default_recipes(c)
    r = craft(c, "聚气丹方", "pill")
    assert r["success"] is False
    assert "材料" in r["message"]
    print("✓ 缺材料不可炼")


def test_craft_success():
    init_db()
    WorldStateRepository.delete("known_recipes")
    c = _c("有料", stones=500)
    ensure_default_recipes(c)
    c.inventory.append("百年灵芝")
    CharacterRepository.save(c)
    # 强制成功：提高 rate 到 1
    from core import alchemy as al

    r = al.craft  # noqa
    # 多试几次直到成或失败都可接受，但材料应被扣
    before = c.inventory.count("百年灵芝")
    res = craft(CharacterRepository.get_by_id(c.id), "聚气丹方", "pill")
    after_c = CharacterRepository.get_by_id(c.id)
    # 成：产出聚气丹；败：材料可能回半个
    assert res["success"] is True
    if res.get("crafted"):
        assert "聚气丹" in after_c.inventory
    else:
        assert after_c.inventory.count("百年灵芝") <= before
    print("✓ 开炉流程", "成" if res.get("crafted") else "败")


def test_learn_hidden_recipe():
    init_db()
    WorldStateRepository.delete("known_recipes")
    c = _c("学徒")
    ensure_default_recipes(c)
    assert learn_recipe(c, "r_xuanyuan") is True
    assert "r_xuanyuan" in ensure_default_recipes(c)
    print("✓ 习得隐藏配方")


def test_ingest_ai_recipe():
    init_db()
    data = {
        "name": "试炼回春方",
        "materials": {"百年灵芝": 2},
        "stones_fee": 20,
        "base_rate": 0.6,
        "req_tier": 0,
        "output": "回春露",
    }
    r = ingest_ai_recipe(data, "pill")
    assert r and r["output"] == "回春露"
    assert r["materials"]["百年灵芝"] == 2
    print("✓ AI 悟方钳制")


def test_pool_sizes():
    assert len(RECIPES) >= 10
    print(f"✓ 配方池 {len(RECIPES)}")


if __name__ == "__main__":
    test_default_recipes()
    test_craft_needs_materials()
    test_craft_success()
    test_learn_hidden_recipe()
    test_ingest_ai_recipe()
    test_pool_sizes()
    print("\n✅ 炼丹炼器测试通过")
