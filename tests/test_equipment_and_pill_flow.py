"""
法宝同槽替换实体防丢失、藏宝图神兵权威生成、动态灵丹服食回归测试
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.items import ItemEntity, ItemKind, ItemFactory, ItemAffix
from core.loot_equip import EquipEngine
from core.market import MarketEngine
from core.models import Character, Realm
from core.treasure_system import TreasureEngine, TreasureArchetype
from storage.db import init_db


def _make_test_character(name: str = "昆仑道子") -> Character:
    init_db()
    c = WorldClock.create_new_character(f"u_{name}", name)
    c.realm.tier = 2
    c.realm.sub_tier = 1
    c.realm.current_exp = 100
    c.spirit_stones = 500
    c.location = "黑水沼泽"
    return c


def test_equipment_same_slot_replace_preserves_entities():
    """测试同槽法宝替换时，旧法宝实体与词缀 100% 完好保存在纳戒中，绝不丢失"""
    c = _make_test_character("藏剑尊者")

    # 1. 锻造两柄绝世神兵实体
    sword1 = ItemEntity(
        uid="sword_dragon_001",
        name="斩龙古剑",
        kind=ItemKind.EQUIP,
        slot="weapon",
        tier=3,
        stats={"power": 90.0},
        affixes=[
            ItemAffix(name="斩龙", desc="对龙属威慑", stat_key="power", value=0.35),
            ItemAffix(name="破煞", desc="破罡真伤", stat_key="pierce", value=0.25),
        ],
        lineage_lore="古修洞府遗存真剑。",
    )
    c.add_item_entity(sword1)

    spear2 = ItemEntity(
        uid="spear_taiyi_002",
        name="太乙玄天戈",
        kind=ItemKind.EQUIP,
        slot="weapon",
        tier=4,
        stats={"power": 120.0},
        affixes=[
            ItemAffix(name="嗜血", desc="饮血固本", stat_key="lifesteal", value=0.15),
        ],
        lineage_lore="太乙玄门传承杀伐重器。",
    )
    c.add_item_entity(spear2)

    # 初始状态：两件武器均在 items 和 inventory 中
    assert len(c.items) == 2
    assert "斩龙古剑" in c.inventory
    assert "太乙玄天戈" in c.inventory

    # 2. 佩戴第一把武器（斩龙古剑）
    res1 = EquipEngine.equip(c, "斩龙古剑")
    assert res1["success"] is True
    assert "斩龙古剑" in c.equipped
    assert "斩龙古剑" not in c.inventory
    # 实体依然安然保存在 c.items
    found_sword1 = c.find_item("斩龙古剑")
    assert found_sword1 is not None
    assert len(found_sword1.affixes) == 2

    # 3. 佩戴第二把武器（太乙玄天戈，同槽 weapon 替换）
    res2 = EquipEngine.equip(c, "太乙玄天戈")
    assert res2["success"] is True
    assert "太乙玄天戈" in c.equipped
    assert "太乙玄天戈" not in c.inventory

    # 关键断言：旧武器【斩龙古剑】必须安全回到 inventory，且实体仍在 c.items，词缀完好无损！
    assert "斩龙古剑" in c.inventory
    assert "斩龙古剑" not in c.equipped
    assert len(c.items) == 2

    rechecked_sword1 = c.find_item("斩龙古剑")
    assert rechecked_sword1 is not None
    assert rechecked_sword1.uid == "sword_dragon_001"
    assert rechecked_sword1.affixes[0].name == "斩龙"
    assert rechecked_sword1.affixes[1].name == "破煞"

    # 4. 卸下太乙玄天戈
    res3 = EquipEngine.unequip(c, "太乙玄天戈")
    assert res3["success"] is True
    assert "太乙玄天戈" not in c.equipped
    assert "太乙玄天戈" in c.inventory
    assert len(c.items) == 2


def test_treasure_dig_generates_authoritative_equipment_and_pill():
    """测试藏宝图挖宝时服务端权威生成神兵与仙丹实体并入库"""
    c = _make_test_character("探宝道人")
    tmap = TreasureEngine.generate_treasure_map(c, tier=3, preferred_target="黑水沼泽")
    tmap.custom_metadata["archetype"] = TreasureArchetype.ELEMENT_PUZZLE
    c.add_item_entity(tmap)
    c.location = "黑水沼泽"

    initial_item_count = len(c.items)
    initial_exp = c.realm.current_exp
    initial_stones = c.spirit_stones

    # 敕令巧破五行 (选项 1)
    res = TreasureEngine.dig(c, choice_id="1")
    assert res["success"] is True
    assert res["outcome"] == "perfect_solve"

    # 宝图已被消耗
    assert tmap.uid not in [it.uid for it in c.items]

    # 服务端权威生成了神兵与灵丹实体
    assert "equipment" in res
    assert "pill" in res
    assert res["equipment"]["slot"] == "weapon"
    assert res["equipment"]["tier"] >= 2
    assert res["equipment"]["name"] in ["斩龙古剑", "太乙玄天戈", "七星诛魔剑", "赤霄惊神刃"]

    # 实体确实入库在 c.items 中
    eq_name = res["equipment"]["name"]
    found_eq = c.find_item(eq_name)
    assert found_eq is not None
    assert found_eq.kind == ItemKind.EQUIP
    assert len(found_eq.affixes) >= 1

    pill_name = res["pill"]["name"]
    found_pill = c.find_item(pill_name)
    assert found_pill is not None
    assert found_pill.kind == ItemKind.PILL

    # 收益结算
    assert c.realm.current_exp > initial_exp
    assert c.spirit_stones > initial_stones


def test_dynamic_pill_consumption_xuanbing_yulu():
    """测试洞府灵泉产出的【玄冰玉露】可正常服用并原子扣除"""
    c = _make_test_character("冰心客")
    dew = ItemEntity.create(
        name="玄冰玉露",
        kind=ItemKind.PILL,
        quality=3,
        description="洞府玄冰九曲灵泉孕育的灵露，饮之清心涤滤，修为倍增。",
    )
    c.add_item_entity(dew)
    c.karma.dao_heart = 80
    init_exp = c.realm.current_exp

    assert c.find_item("玄冰玉露") is not None

    # 服食灵露
    res = MarketEngine.use_pill(c, "玄冰玉露")
    assert res["success"] is True
    assert "清寒玉露涤荡周身经脉" in res["message"]

    # 实体已被原子扣减移除
    assert c.find_item("玄冰玉露") is None
    assert "玄冰玉露" not in c.inventory

    # 真元增长与道心提升
    assert c.realm.current_exp > init_exp
    assert c.karma.dao_heart == 85
    assert c.pill_exp_mult >= 0.20


def test_dynamic_pill_consumption_jiuzhuan_huanhun():
    """测试藏宝图掘出的【九转还魂真丹】服食大补寿元与真元"""
    c = _make_test_character("长生客")
    pill = ItemEntity.create(
        name="九转还魂真丹",
        kind=ItemKind.PILL,
        quality=3,
        description="上古秘藏绝品仙丹，服用可大补元气。",
    )
    c.add_item_entity(pill)
    c.lifespan.death_timestamp = time.time() + 100 * 365.25 * 86400
    rem_before = c.lifespan.get_remaining_years()

    res = MarketEngine.use_pill(c, "九转还魂真丹")
    assert res["success"] is True
    assert "纯阳仙力直冲华盖" in res["message"]

    # 实体扣除
    assert c.find_item("九转还魂真丹") is None

    # 寿元增长 3 岁
    rem_after = c.lifespan.get_remaining_years()
    assert round(rem_after - rem_before, 1) == 3.0


def test_non_pill_consumption_rejected():
    """测试对非丹药道具（如武器装备）点击服用被优雅拦截"""
    c = _make_test_character("铁头娃")
    armor = ItemEntity.create(
        name="玄铁护腕",
        kind=ItemKind.EQUIP,
        slot="armor",
        quality=2,
    )
    c.add_item_entity(armor)

    res = MarketEngine.use_pill(c, "玄铁护腕")
    assert res["success"] is False
    assert "不是可服用的丹药或灵露" in res["message"]
    # 实体未被误删
    assert c.find_item("玄铁护腕") is not None


def test_status_dict_includes_equipped_and_filters_unworn():
    """测试服务端 _status_dict 正确输出 equipped 并保证 items 不与身上穿戴重复"""
    from server.world import World
    w = World(auto_tick=False)
    c = _make_test_character("万法仙君")

    # 穿戴青锋剑
    c.inventory.append("青锋剑")
    EquipEngine.equip(c, "青锋剑")
    assert "青锋剑" in c.equipped

    # 纳戒中留存另一柄赤霄剑
    red_sword = ItemFactory.create_equip("赤霄剑", tier=3, slot="weapon")
    c.add_item_entity(red_sword)

    st = w._status_dict(c)
    assert "equipped" in st
    assert len(st["equipped"]) == 1
    assert st["equipped"][0]["name"] == "青锋剑"
    assert st["equipped"][0]["slot"] == "weapon"

    # items 纳戒列表中只包含赤霄剑，不重复包含已穿戴的青锋剑
    item_names = [it["name"] for it in st["items"]]
    assert "赤霄剑" in item_names
    assert "青锋剑" not in item_names
