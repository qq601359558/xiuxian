"""
环境时间缩放 + 坊市购买
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.models import CharacterStatus
from core.market import MarketEngine


def test_time_scale_helpers():
    import config
    # 测试环境默认可加速
    assert not config.is_production()
    s = config.time_scale()
    assert s > 1.0 or abs(s - 1.0) < 1e-9
    # 8 设计小时 → 墙钟秒
    wall = config.design_hours_to_wall_seconds(8.0)
    assert abs(wall - 8 * 3600 / s) < 1e-6
    # 往返
    d = config.wall_to_design_seconds(wall)
    assert abs(d - 8 * 3600) < 1e-3
    print(f"✓ TIME_SCALE={s:g}，8h 设计 → 墙钟 {wall/60:.1f} 分钟")


def test_meditation_uses_wall_scale():
    import config
    c = WorldClock.create_new_character("scale_user", "倍速修士")
    c.born_at = time.time() - 80 * 3600.0
    res = WorldClock.start_meditation(c, hours_planned=8.0)
    assert res["success"] is True
    scale = config.time_scale()
    expect_wall = 8 * 3600.0 / scale
    actual_wall = c.meditation.end_time - c.meditation.start_time
    assert abs(actual_wall - expect_wall) < 1.0, (actual_wall, expect_wall, scale)

    # 用「墙钟走完」的 now 结算 → 设计 8 小时
    now = c.meditation.start_time + expect_wall + 1
    prog = WorldClock.get_meditation_progress(c, now=now)
    assert prog["is_completed"] is True
    assert abs(prog["elapsed_design_hours"] - 8.0) < 0.05

    settle = WorldClock.settle_meditation(c, now=now)
    assert settle["success"] is True
    assert abs(settle["effective_hours"] - 8.0) < 0.1
    print(f"✓ 8h 闭关墙钟 {expect_wall/60:.1f} 分，按设计 8h 结算收益")


def test_production_forces_realtime(monkey=False):
    os.environ["GAME_ENV"] = "production"
    os.environ["TIME_SCALE"] = "999"
    # 重新 import 不方便；直接调用读 env 的函数需 reload
    import importlib
    import config
    importlib.reload(config)
    assert config.is_production()
    assert config.time_scale() == 1.0
    # 还原
    os.environ["GAME_ENV"] = "test"
    os.environ.pop("TIME_SCALE", None)
    importlib.reload(config)
    assert not config.is_production()
    print("✓ production 强制 TIME_SCALE=1")


def test_buy_from_guild():
    from storage.db import init_db
    init_db()
    c = WorldClock.create_new_character("buyer_u", "坊市客")
    c.born_at = time.time() - 80 * 3600.0
    c.spirit_stones = 500
    r = MarketEngine.buy_from_guild(c, "聚气丹", 1)
    assert r["success"] is True
    assert "聚气丹" in c.inventory
    assert c.spirit_stones == 500 - 40
    r2 = MarketEngine.buy_from_guild(c, "不存在的货", 1)
    assert r2["success"] is False
    print("✓ 商会购买")


if __name__ == "__main__":
    test_time_scale_helpers()
    test_meditation_uses_wall_scale()
    test_production_forces_realtime()
    test_buy_from_guild()
    print("\n✅ 环境时间缩放 + 坊市购买 测试通过")
