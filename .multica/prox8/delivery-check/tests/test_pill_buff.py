"""聚气丹：服后下次闭关修为加成"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.market import MarketEngine
from storage.db import init_db, CharacterRepository


def test_juqi_buffs_meditation():
    init_db()
    c = WorldClock.create_new_character("pill_clo", "丹修客")
    c.born_at = time.time() - 80 * 3600  # 非新手，避免叠新手加成干扰
    c.inventory.append("聚气丹")
    r = MarketEngine.use_pill(c, "聚气丹")
    assert r["success"]
    assert c.pill_exp_mult >= 0.15

    WorldClock.start_meditation(c, hours_planned=4.0)
    s1 = WorldClock.settle_meditation(c, now=time.time() + 4 * 3600 + 2)
    assert s1["success"]
    assert s1["pill_mult"] >= 1.15
    assert s1["exp_gained"] > 0
    assert c.pill_exp_mult == 0.0  # 药力耗尽

    # 再次闭关无加成
    WorldClock.start_meditation(c, hours_planned=4.0)
    s2 = WorldClock.settle_meditation(c, now=time.time() + 4 * 3600 + 2)
    assert abs(s2["pill_mult"] - 1.0) < 1e-6
    print("✓ 聚气丹闭关加成", s1["pill_mult"], "修为+", s1["exp_gained"], "→用尽后", s2["pill_mult"])


def test_pill_grades():
    init_db()
    from core.market import MarketEngine
    from config import ITEM_CATALOG
    assert ITEM_CATALOG["聚气丹"]["pill_exp_mult"] == 0.15
    assert ITEM_CATALOG["玄元聚气丹"]["pill_exp_mult"] == 0.30
    assert ITEM_CATALOG["九转凝灵丹"]["pill_exp_mult"] == 0.50
    c = WorldClock.create_new_character("pill_g", "丹阶客")
    c.born_at = time.time() - 80 * 3600
    c.inventory.append("九转凝灵丹")
    r = MarketEngine.use_pill(c, "九转凝灵丹")
    assert r["success"] and c.pill_exp_mult >= 0.50
    print("✓ 三档丹药", c.pill_exp_note, c.pill_exp_mult)


def test_huilu_value():
    init_db()
    from config import ITEM_CATALOG
    from core.market import MarketEngine
    juqi = ITEM_CATALOG["聚气丹"]
    lu = ITEM_CATALOG["回春露"]
    # 性价比：回春露更便宜，加成更弱；不得「又贵又差」
    assert lu["price"] < juqi["price"]
    assert lu["pill_exp_mult"] < juqi["pill_exp_mult"]
    c = WorldClock.create_new_character("lu_user", "伤药客")
    c.born_at = time.time() - 80 * 3600
    life0 = c.lifespan.get_remaining_years()
    c.inventory.append("回春露")
    r = MarketEngine.use_pill(c, "回春露")
    assert r["success"]
    assert c.lifespan.get_remaining_years() >= life0 + 0.9
    print("✓ 回春露", lu["price"], "灵石 +", lu["pill_exp_mult"], "寿元+", lu["heal_lifespan"])


if __name__ == "__main__":
    test_juqi_buffs_meditation()
    test_pill_grades()
    test_huilu_value()
    print("\n✅ 丹药品阶与闭关加成测试通过")
