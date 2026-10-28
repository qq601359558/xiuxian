"""
法宝装备总纲与穿戴锻造测试 (Equipments Catalog & EquipEngine Tests)
"""
import pytest
from core.models import Character, EquipmentSlots, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.catalogs.equipments import EQUIPMENT_CATALOG, RAW_EQUIPMENTS, EQUIPMENT_RECIPES
from core.catalogs import get_equipment, format_equipment_for_client, MATERIAL_CATALOG
from core.loot_equip import EquipEngine
import time


def _make_char() -> Character:
    now = time.time()
    return Character(
        user_id="u_test_forge",
        name="韩立",
        realm=Realm(tier=1, sub_tier=1, current_exp=100),
        lifespan=Lifespan(birth_base=100.0, accumulated_gain=0.0, death_timestamp=now + 86400 * 10),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WOOD, Element.EARTH], efficiency=1.0),
    )


def test_equipments_catalog_structure():
    """验证装备总纲 5 大槽位与 5 大品阶覆盖"""
    slots_found = set()
    tiers_found = set()
    
    for name, data in RAW_EQUIPMENTS.items():
        assert "id" in data
        assert "slot" in data
        assert "tier" in data
        assert "stats" in data
        assert "difficulty" in data
        assert 1 <= data["difficulty"] <= 100
        assert data["category"] == "equip"
        assert data["kind"] == "equip"
        assert data["slot"] in ("weapon", "armor", "trinket", "boots", "flying_treasure")
        
        slots_found.add(data["slot"])
        tiers_found.add(data["tier"])
        
        # 双键索引验证
        assert EQUIPMENT_CATALOG[name]["id"] == data["id"]
        assert EQUIPMENT_CATALOG[data["id"]]["name"] == name

    # 必须涵盖全部 5 个槽位与 1~5 阶
    assert slots_found == {"weapon", "armor", "trinket", "boots", "flying_treasure"}
    assert tiers_found == {1, 2, 3, 4, 5}


def test_equipment_format_client_isolation():
    """验证装备客户端展示环境隔离（测试环境保留锻造难度，生产环境剔除）"""
    test_view = format_equipment_for_client("青锋剑", is_prod=False)
    assert test_view is not None
    assert "_debug_difficulty" in test_view
    assert "【锻造难度: 20/100】" in test_view["_debug_difficulty"]

    prod_view = format_equipment_for_client("青锋剑", is_prod=True)
    assert prod_view is not None
    assert "difficulty" not in prod_view
    assert prod_view["_debug_difficulty"] is None


def test_equipment_recipes_integrity():
    """验证炼器器谱材料必须全部来自材料总纲"""
    assert len(EQUIPMENT_RECIPES) >= 20
    for r in EQUIPMENT_RECIPES:
        assert r["kind"] == "equip"
        assert r["output"] in RAW_EQUIPMENTS
        for mat_name, count in r["materials"].items():
            assert mat_name in MATERIAL_CATALOG, f"器谱 {r['name']} 依赖的材料 {mat_name} 不存在于 MATERIAL_CATALOG"
            assert count > 0


def test_equip_engine_five_slots_and_sync():
    """验证 5 大槽位穿戴、同槽替换与 Character.equip_slots 同步"""
    c = _make_char()
    c.inventory = ["青锋剑", "玄铁剑", "软猬甲", "平安符", "御风疾行靴", "青竹飞云舟"]

    # 1. 穿戴武器 (青锋剑)
    res = EquipEngine.equip(c, "青锋剑")
    assert res["success"] is True
    assert "青锋剑" in c.equipped
    assert "青锋剑" not in c.inventory
    assert c.equip_slots.weapon == "青锋剑"

    # 2. 穿戴护甲 (软猬甲)
    res = EquipEngine.equip(c, "软猬甲")
    assert res["success"] is True
    assert c.equip_slots.armor == "软猬甲"

    # 3. 穿戴饰品 (平安符)
    res = EquipEngine.equip(c, "平安符")
    assert res["success"] is True
    assert c.equip_slots.trinket == "平安符"

    # 4. 穿戴靴子 (御风疾行靴)
    res = EquipEngine.equip(c, "御风疾行靴")
    assert res["success"] is True
    assert c.equip_slots.boots == "御风疾行靴"

    # 5. 穿戴御空法宝 (青竹飞云舟)
    res = EquipEngine.equip(c, "青竹飞云舟")
    assert res["success"] is True
    assert c.equip_slots.flying_treasure == "青竹飞云舟"

    # 6. 同槽位替换：穿戴玄铁剑 (武器)，应将青锋剑卸回行囊
    res = EquipEngine.equip(c, "玄铁剑")
    assert res["success"] is True
    assert "玄铁剑" in c.equipped
    assert "青锋剑" not in c.equipped
    assert "青锋剑" in c.inventory
    assert c.equip_slots.weapon == "玄铁剑"

    # 7. 汇总装备属性
    stats = EquipEngine.get_total_stats(c)
    assert stats["phys_atk"] > 0
    assert stats["phys_def"] > 0
    assert stats["speed"] > 0
    assert stats["sense_range"] > 0

    # 8. 卸下法宝
    res = EquipEngine.unequip(c, "玄铁剑")
    assert res["success"] is True
    assert "玄铁剑" not in c.equipped
    assert "玄铁剑" in c.inventory
    assert c.equip_slots.weapon is None


def test_equipments_catalog_deep_parameters():
    """验证装备总纲深度参数全量覆盖 (66 件法宝、器型细分、禁制重数、修补材料、主动技能与被动心法)"""
    assert len(RAW_EQUIPMENTS) >= 60, f"装备库数量不足，当前仅有 {len(RAW_EQUIPMENTS)} 件"
    assert len(EQUIPMENT_RECIPES) >= 60, f"炼器谱数量不足，当前仅有 {len(EQUIPMENT_RECIPES)} 卷"

    for name, data in RAW_EQUIPMENTS.items():
        # 1. 器型细分
        assert "subtype" in data, f"{name} 缺少 subtype"
        assert len(data["subtype"]) >= 2, f"{name} subtype 过短"

        # 2. 禁制重数与类型
        assert "restrictions_count" in data, f"{name} 缺少 restrictions_count"
        assert data["restrictions_count"] >= 1, f"{name} 禁制重数非法"
        assert "restriction_type" in data, f"{name} 缺少 restriction_type"

        # 3. 耐久与温养修补材料
        assert data.get("durability", 0) >= 100, f"{name} 耐久度过低"
        assert "repair_materials" in data, f"{name} 缺少 repair_materials"
        for mat, count in data["repair_materials"].items():
            assert mat in MATERIAL_CATALOG, f"{name} 修补材料 {mat} 不存在于 MATERIAL_CATALOG"
            assert count >= 1

        # 4. 被动词缀心法与法宝主动威能
        assert "passive_skills" in data, f"{name} 缺少 passive_skills"
        assert len(data["passive_skills"]) >= 1, f"{name} 至少需具备 1 个被动心法词缀"
        for p in data["passive_skills"]:
            assert "id" in p and "name" in p and "desc" in p

        assert "active_spells" in data, f"{name} 缺少 active_spells"
        assert len(data["active_spells"]) >= 1, f"{name} 至少需具备 1 个主动威能神通"
        for s in data["active_spells"]:
            assert "id" in s and "name" in s and "cooldown" in s and "mp_cost" in s and "desc" in s

        # 5. 来源与掉落
        assert "source_types" in data and len(data["source_types"]) >= 1


def test_equipment_set_bonuses_activation():
    """验证天道装备套装（如青云初照套 2 件 / 4 件）羁绊逐级激发与战力属性加成"""
    c = _make_char()
    c.inventory = ["青锋剑", "青丝法衣", "清心温玉佩", "踏青草履"]

    # 1. 穿戴 1 件青锋剑，未达 2 件套门槛
    EquipEngine.equip(c, "青锋剑")
    assert len(EquipEngine.get_active_sets(c)) == 0

    # 2. 穿戴第 2 件青丝法衣，激发青云初照 2 件套羁绊 (气血+40, 真元+20, 遁速+3)
    EquipEngine.equip(c, "青丝法衣")
    active_2 = EquipEngine.get_active_sets(c)
    assert len(active_2) == 1
    assert active_2[0]["name"] == "青云初照 · 气脉绵延 (2件)"

    # 3. 穿戴第 3、4 件，激发 4 件套羁绊 (灵攻+15, 物攻+10, 神识感知+10米)
    EquipEngine.equip(c, "清心温玉佩")
    EquipEngine.equip(c, "踏青草履")
    active_4 = EquipEngine.get_active_sets(c)
    assert len(active_4) == 2
    assert any(b["threshold"] == 2 for b in active_4)
    assert any(b["threshold"] == 4 for b in active_4)

    # 4. 验证总属性已累加套装增益
    totals = EquipEngine.get_total_stats(c)
    assert totals["max_hp"] >= 40
    assert totals["spell_atk"] >= 15
    assert totals["phys_atk"] >= 10

    # 5. 验证战力系数包含套装羁绊加成
    power = EquipEngine.power_bonus(c)
    assert power > 1.0


def test_equipment_requirements_check():
    """验证佩戴门槛：练气修士不可越两阶佩戴四阶极品或五阶仙品法宝"""
    c = _make_char()
    c.realm.tier = 1  # 练气期
    c.inventory = ["青锋剑", "玄铁剑", "斩仙剑", "大罗诛仙剑"]

    # 1. 练气期穿一阶凡品青锋剑 -> 允许
    can_equip_1, _ = EquipEngine.check_equip_requirements(c, "青锋剑")
    assert can_equip_1 is True

    # 2. 练气期越一阶穿二阶灵品玄铁剑 -> 允许越阶御器
    can_equip_2, _ = EquipEngine.check_equip_requirements(c, "玄铁剑")
    assert can_equip_2 is True

    # 3. 练气期试图穿戴四阶极品斩仙剑 (需元婴期) -> 严厉拦截
    can_equip_4, reason_4 = EquipEngine.check_equip_requirements(c, "斩仙剑")
    assert can_equip_4 is False
    assert "境界悬殊" in reason_4

    # 4. 练气期试图佩戴五阶仙品大罗诛仙剑 (需化神期) -> 严厉拦截
    res = EquipEngine.equip(c, "大罗诛仙剑")
    assert res["success"] is False
    assert "境界悬殊" in res["message"]


def test_character_combat_soul_stats_sync():
    """验证法宝穿戴与卸下时，Character.combat 与 Character.soul 动态实时同步"""
    c = _make_char()
    EquipEngine.sync_character_stats(c)
    initial_patk = c.combat.phys_atk
    initial_sense = c.soul.divine_sense

    c.inventory = ["青锋剑", "清心温玉佩"]

    # 穿戴青锋剑 (phys_atk +15) 与清心温玉佩 (divine_sense +4)
    EquipEngine.equip(c, "青锋剑")
    EquipEngine.equip(c, "清心温玉佩")

    assert c.combat.phys_atk > initial_patk
    assert c.soul.divine_sense > initial_sense

    # 卸下后，属性自动平稳复原
    EquipEngine.unequip(c, "青锋剑")
    EquipEngine.unequip(c, "清心温玉佩")

    assert c.combat.phys_atk == initial_patk
    assert c.soul.divine_sense == initial_sense

