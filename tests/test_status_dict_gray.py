"""灰度批次 B：_status_dict 下发行囊/穿戴与天道可感知标志"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from core.clock import WorldClock
from server.world import WORLD

WORLD.stop_tick()


def test_status_dict_includes_bag_and_marks():
    c = WorldClock.create_new_character("gray_bag_user", "灰度行囊客")
    c.inventory = ["聚气丹", "聚气丹", "青锋剑"]
    c.equipped = ["青锋剑"]
    c.arrays = ["一阶青木迷踪阵"]
    st = WORLD._status_dict(c)
    # 旧字段仍在（向后兼容）
    assert st["name"] == "灰度行囊客" and "realm" in st and "skills" in st
    # 新增字段
    assert st["inventory"] == ["聚气丹", "聚气丹", "青锋剑"]
    assert st["equipped"] == ["青锋剑"]
    assert st["arrays"] == ["一阶青木迷踪阵"]
    assert st["blood_marked"] is False
    assert st["lifespan_warning"] is False
    print("✓ status 行囊字段齐全，默认无血煞/大限标志")


def test_status_dict_blood_and_lifespan_warning():
    c = WorldClock.create_new_character("gray_mark_user", "灰度示警客")
    c.karma.blood_mark_until = time.time() + 3600
    c.lifespan.death_timestamp = time.time() + 86400 * 5  # 余寿 5 年 < 阈值 10 年
    st = WORLD._status_dict(c)
    assert st["blood_marked"] is True
    assert st["lifespan_warning"] is True
    print("✓ status 血煞/大限标志按规则侧口径点亮")
