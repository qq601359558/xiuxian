"""
藏宝图八卦方位风水算法与文言天机指引测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db
from core.clock import WorldClock
from core.models import Character
from core.world_grid import WorldGridEngine, WorldNode
from core.treasure_system import TreasureEngine, calculate_fengshui_direction


def test_calculate_fengshui_direction_sectors():
    # 测试不同坐标方位的八卦映射
    center = WorldNode(id="n0", base_name="中枢坊市", region="东荒", coordinates=(0, 0))

    # 正东 (dx=5, dy=0)
    east_node = WorldNode(id="n1", base_name="东极沧海", region="东荒", coordinates=(5, 0))
    res_e = calculate_fengshui_direction(center, east_node)
    assert "震位" in res_e["bagua"]
    assert "东" in res_e["direction_cn"]

    # 极北 (dx=0, dy=5)
    north_node = WorldNode(id="n2", base_name="北荒寒潭", region="北冥", coordinates=(0, 5))
    res_n = calculate_fengshui_direction(center, north_node)
    assert "坎位" in res_n["bagua"]
    assert "北" in res_n["direction_cn"]

    # 西极 (dx=-5, dy=0)
    west_node = WorldNode(id="n3", base_name="西昆仑", region="西荒", coordinates=(-5, 0))
    res_w = calculate_fengshui_direction(center, west_node)
    assert "兑位" in res_w["bagua"]
    assert "西" in res_w["direction_cn"]

    # 正南 (dx=0, dy=-5)
    south_node = WorldNode(id="n4", base_name="南离火谷", region="南荒", coordinates=(0, -5))
    res_s = calculate_fengshui_direction(center, south_node)
    assert "离位" in res_s["bagua"]
    assert "南" in res_s["direction_cn"]

    # 东南 (dx=4, dy=-4)
    se_node = WorldNode(id="n5", base_name="东南大泽", region="东荒", coordinates=(4, -4))
    res_se = calculate_fengshui_direction(center, se_node)
    assert "巽位" in res_se["bagua"] or "东南" in res_se["direction_cn"]


def test_directional_guide_content():
    init_db()
    c = WorldClock.create_new_character("u_dir_tester", "定盘真人")
    # 位于青云坊市客栈 (0, 0)
    c.location = "青云坊市客栈"
    
    # 生成一张目标位于黑水沼泽 (3, -3) 的宝图
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    c.add_item_entity(tmap)

    curr_node = WorldGridEngine.get_node(c.location)
    target_node = WorldGridEngine.get_node(tmap.custom_metadata["target_node_id"])

    guide = TreasureEngine.get_directional_guide(c, tmap, curr_node, target_node)
    assert guide["bagua"] != ""
    assert "【天机定盘 · 寻龙点穴】" in guide["full_text"]
    assert "谶语判词" in guide["full_text"]
    assert "黑水沼泽" in guide["full_text"]


def test_dig_at_wrong_location_returns_guide():
    init_db()
    c = WorldClock.create_new_character("u_wrong_dig", "莽撞道童")
    c.location = "青云坊市客栈"

    # 生成宝图指定在黑水沼泽
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    c.add_item_entity(tmap)

    # 尝试在青云坊市客栈直接挖宝
    res = TreasureEngine.dig(c)
    assert res["success"] is False
    assert res.get("wrong_location") is True
    assert "【天机定盘 · 寻龙点穴】" in res["message"]
    # 宝图依然完好未损耗
    assert any(it.uid == tmap.uid for it in c.items)
