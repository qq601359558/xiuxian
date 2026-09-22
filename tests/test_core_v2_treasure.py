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


def test_invalid_choice_does_not_consume_map():
    c = _make_char(loc="黑水沼泽")
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    tmap.custom_metadata["archetype"] = TreasureArchetype.ELEMENT_PUZZLE
    c.add_item_entity(tmap)

    # 输入 3（提示输入 /做）
    res3 = TreasureEngine.dig(c, choice_id="3")
    assert res3["success"] is False
    assert "自由破局" in res3["message"]
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 1

    # 输入非法选项 abc
    res_inv = TreasureEngine.dig(c, choice_id="abc")
    assert res_inv["success"] is False
    assert "无效选项" in res_inv["message"]
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 1


def test_free_action_location_protection():
    # 人在坊市，宝图在黑水沼泽
    c = _make_char(loc="青云坊市客栈")
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    c.add_item_entity(tmap)

    # 尝试在坊市远程 /做 破局
    res = TreasureEngine.resolve_free_action(c, "我以神雷破门")
    assert res["success"] is False
    assert res.get("not_at_ruin") is True
    assert "当前未在宝藏所在节点" in res["message"]
    # 宝图未被消耗
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 1


def test_scar_broadcast_to_world_channel():
    from core.world_channel import WorldChannel
    c = _make_char(loc="落霞山灵泉")
    tmap = TreasureEngine.generate_treasure_map(c, tier=3, preferred_target="落霞山灵泉")
    tmap.custom_metadata["archetype"] = TreasureArchetype.RUIN_HAZARD
    c.add_item_entity(tmap)

    # 触发引爆，验证广播生效
    res = TreasureEngine.dig(c)
    assert res["success"] is True

    # 检查 WorldChannel 最近消息
    recent = WorldChannel.recent(limit=5)
    scar_msg = next((m for m in recent if "赤焰火海" in m.text), None)
    assert scar_msg is not None
    assert scar_msg.actor == c.name


def test_equip_item_entity_power():
    from core.loot_equip import EquipEngine
    from core.items import ItemFactory
    c = _make_char()
    # 掉落实体武器
    sword = ItemFactory.create_equip(
        name="断魂幽煞剑", tier=3, slot="weapon", base_power=40.0, affix_count=1
    )
    c.add_item_entity(sword)

    # 穿戴实体装备
    res = EquipEngine.equip(c, "断魂幽煞剑")
    assert res["success"] is True
    assert "断魂幽煞剑" in c.equipped

    # 检查战斗力加成
    bonus = EquipEngine.power_bonus(c)
    assert bonus > 1.0


def test_item_entity_duplicate_sync():
    c = _make_char()
    from core.items import ItemFactory
    pill1 = ItemFactory.from_legacy_name("九转培元丹")
    pill2 = ItemFactory.from_legacy_name("九转培元丹")
    c.add_item_entity(pill1)
    c.add_item_entity(pill2)
    assert c.inventory.count("九转培元丹") == 2

    # 移除 1 颗
    c.remove_item_entity(pill1.uid)
    assert c.inventory.count("九转培元丹") == 1
    assert len(c.items) == 1

