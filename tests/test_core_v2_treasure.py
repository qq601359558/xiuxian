"""
Core-V2 藏宝探险系统全面测试 (test_core_v2_treasure.py)
覆盖：实体宝图生成、地点校验、五行解谜、战斗伏击、世界疤痕回写、以及自由语 DM 裁决（Fail Forward）。
"""
import pytest
from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.items import ItemKind
from core.world_grid import WorldGridEngine
from core.treasure_system import TreasureEngine, TreasureArchetype


def _make_char(name="凌虚子", loc="青云坊市客栈"):
    return Character(
        user_id="u_test_01",
        name=name,
        realm=Realm(tier=2, current_exp=100),
        lifespan=Lifespan(birth_base=120.0, death_timestamp=9999999999.0),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WATER]),
        location=loc,
    )


def test_map_generation_and_reading():
    c = _make_char()
    # 强制生成一张指向黑水沼泽的藏宝图
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    c.add_item_entity(tmap)
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 1

    # 查阅宝图详情
    res = TreasureEngine.read_map(c)
    assert res["success"] is True
    assert "黑水沼泽" in res["message"]
    assert "距宝藏地约" in res["message"] or "立即执行 /挖宝" in res["message"]


def test_wrong_location_warning():
    c = _make_char(loc="青云坊市客栈")  # 人在坊市
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    c.add_item_entity(tmap)

    # 在错误的地点执行挖宝
    res = TreasureEngine.dig(c)
    assert res["success"] is False
    assert res.get("wrong_location") is True
    assert "此地风水为" in res["message"]
    assert "与图中所指天机大相径庭" in res["message"]
    # 确保宝图未被误消耗！
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 1


def test_element_puzzle_archetype():
    c = _make_char(loc="黑水沼泽")  # 人在正确地点
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    tmap.custom_metadata["archetype"] = TreasureArchetype.ELEMENT_PUZZLE
    c.add_item_entity(tmap)

    # 第一步：唤起五行阵盘交互界面
    step1 = TreasureEngine.dig(c)
    assert step1["success"] is True
    assert step1.get("need_choice") is True
    assert "五行天机" in step1["message"]
    assert "以水克火" in step1["message"]

    # 第二步：选择 1（巧破五行）
    step2 = TreasureEngine.dig(c, choice_id="1")
    assert step2["success"] is True
    assert step2["outcome"] == "perfect_solve"
    assert "完好启封" in step2["message"]
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 0  # 宝图已消耗
    assert c.realm.current_exp > 100


def test_ruin_hazard_creates_world_scar():
    c = _make_char(loc="落霞山灵泉")
    tmap = TreasureEngine.generate_treasure_map(c, tier=3, preferred_target="落霞山灵泉")
    tmap.custom_metadata["archetype"] = TreasureArchetype.RUIN_HAZARD
    c.add_item_entity(tmap)

    # 触发破坏性破局
    res = TreasureEngine.dig(c)
    assert res["success"] is True
    assert res["outcome"] == "scar_created"
    assert "地貌永久异变为【赤焰火海】" in res["message"]

    # 验证节点被赋予世界疤痕
    node = WorldGridEngine.get_node("落霞山灵泉")
    assert "赤焰火海" in node.display_name
    assert node.effective_danger > node.danger


def test_free_action_dm_fail_forward():
    c = _make_char(loc="黑水沼泽")
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    c.add_item_entity(tmap)

    # 乱敲无逻辑操作触发 Fail Forward
    res = TreasureEngine.resolve_free_action(c, "我跳进石洞里发呆看风景")
    assert res["success"] is True
    assert res["outcome"] == "fail_forward"
    assert "因祸得福" in res["message"]
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 0  # 宝图消耗
    # 掉落了隐藏秘丹
    assert any("丹" in it.name for it in c.items)
