"""
五行神通与半即时连携战斗引擎单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db
from core.clock import WorldClock
from core.spells import (
    SPELL_CATALOG,
    CombatEntity,
    SpellCombatEngine,
    create_player_entity,
    create_monster_entity,
)


def test_spell_catalog_integrity():
    assert "metal_sword" in SPELL_CATALOG
    assert "wood_heal" in SPELL_CATALOG
    assert "water_freeze" in SPELL_CATALOG
    assert "fire_blast" in SPELL_CATALOG
    assert "earth_shield" in SPELL_CATALOG


def test_entity_creation():
    init_db()
    c = WorldClock.create_new_character("spell_tester_01", "风清扬")
    p = create_player_entity(c)
    assert p.name == "风清扬"
    assert p.max_hp > 100
    assert p.max_mp > 50
    assert p.hp == p.max_hp
    assert p.mp == p.max_mp

    m = create_monster_entity({"name": "赤火蝎", "base_hp": 120, "base_atk": 25, "base_def": 8}, floor=1)
    assert m.name == "赤火蝎"
    assert m.hp == 120


def test_metal_sword_shield_break():
    p = CombatEntity(
        id="p1", name="剑客", realm="筑基初期", tier=2,
        max_hp=200, hp=200, max_mp=100, mp=100, attack=50, defense=10
    )
    m = CombatEntity(
        id="m1", name="重甲龟", realm="二阶妖兽", tier=2,
        max_hp=200, hp=200, max_mp=50, mp=50, attack=20, defense=0, shield=50
    )

    # 施展太乙破虚剑气 (消耗 15 MP，回合末自然恢复 5 MP)
    res = SpellCombatEngine.step_round(p, m, action="spell", spell_key="metal_sword")
    assert p.mp == 100 - 15 + 5
    # 50 * 1.6 = 80，由于有护盾，额外 1.5 倍 = 120 伤害！
    # 50 护盾全碎，剩余 70 扣血，m.hp = 130
    assert res["monster"]["shield"] == 0
    assert res["monster"]["hp"] < 200
    any_shield_break_log = any("破盾" in line or "护盾碎裂" in line for line in res["logs"])
    assert any_shield_break_log


def test_water_and_fire_combo():
    p = CombatEntity(
        id="p1", name="法尊", realm="筑基中期", tier=2,
        max_hp=200, hp=200, max_mp=100, mp=100, attack=50, defense=10
    )
    m = CombatEntity(
        id="m1", name="炎魔幼崽", realm="二阶妖兽", tier=2,
        max_hp=300, hp=300, max_mp=50, mp=50, attack=20, defense=0
    )

    # 1. 施展水系神通冻结
    res1 = SpellCombatEngine.step_round(p, m, action="spell", spell_key="water_freeze")
    assert any("冻结" in line for line in res1["logs"])
    # 怪物处于 freeze 状态，无法反击，玩家不掉血
    assert res1["player"]["hp"] == 200

    # 2. 紧接着施展九幽地煞火触发阴阳爆燃！
    res2 = SpellCombatEngine.step_round(p, m, action="spell", spell_key="fire_blast")
    assert any("爆燃" in line for line in res2["logs"])
    # 连携伤害极高
    assert res2["monster"]["hp"] < 180


def test_earth_shield_and_wood_heal():
    p = CombatEntity(
        id="p1", name="修士", realm="筑基初期", tier=2,
        max_hp=200, hp=100, max_mp=100, mp=100, attack=30, defense=10
    )
    m = CombatEntity(
        id="m1", name="妖狼", realm="二阶妖兽", tier=2,
        max_hp=200, hp=200, max_mp=50, mp=50, attack=30, defense=0
    )

    # 1. 不动明王罡加盾
    res1 = SpellCombatEngine.step_round(p, m, action="spell", spell_key="earth_shield")
    assert res1["player"]["shield"] > 0
    assert any("不动明王" in line for line in res1["logs"])

    # 2. 青帝长生引回血
    res2 = SpellCombatEngine.step_round(p, m, action="spell", spell_key="wood_heal")
    assert res2["player"]["hp"] > 100
    assert any("青色生机" in line for line in res2["logs"])


def test_treasure_skill_single_use():
    p = CombatEntity(
        id="p1", name="剑圣", realm="结丹初期", tier=3,
        max_hp=500, hp=500, max_mp=200, mp=200, attack=100, defense=20,
        equipped_weapon="纯阳斩仙剑"
    )
    m = CombatEntity(
        id="m1", name="大妖", realm="三阶妖兽", tier=3,
        max_hp=600, hp=600, max_mp=100, mp=100, attack=40, defense=10
    )

    # 第一次使用法宝
    res1 = SpellCombatEngine.step_round(p, m, action="treasure")
    assert res1["player"]["treasure_used"] is True
    assert any("纯阳斩仙剑" in line for line in res1["logs"])
    assert res1["monster"]["hp"] <= 350

    # 第二次使用法宝被拒并回退普攻
    res2 = SpellCombatEngine.step_round(p, m, action="treasure")
    assert any("法宝温养中" in line for line in res2["logs"])


def test_reflect_damage_kill_monster():
    p = CombatEntity(
        id="p1", name="反伤道人", realm="筑基初期", tier=2,
        max_hp=200, hp=150, max_mp=100, mp=100, attack=30, defense=5
    )
    # 怪物血量很低 (仅剩 2 点)，但攻击较高 (20)
    m = CombatEntity(
        id="m1", name="残血妖狼", realm="二阶妖兽", tier=2,
        max_hp=200, hp=2, max_mp=50, mp=50, attack=20, defense=0
    )
    # 玩家已开启不动明王罡 (reflect 状态)
    p.status_effects["reflect"] = 2

    # 玩家本回合施展青帝长生引调理气血（不对怪物造成直接杀伤），怪物扑杀玩家触发反震 (20 * 0.2 = 4 反震伤害)
    res = SpellCombatEngine.step_round(p, m, action="spell", spell_key="wood_heal")
    # 反震造成 4 点伤害，怪物血量归 0，应当立即判定战斗胜利
    assert res["ended"] is True
    assert res["winner"] == "player"
    assert any("明王反震" in line for line in res["logs"])
    assert any("妖煞溃散" in line for line in res["logs"])


def test_wood_heal_preserves_reflect_buff():
    p = CombatEntity(
        id="p1", name="木系散修", realm="筑基初期", tier=2,
        max_hp=200, hp=80, max_mp=100, mp=100, attack=30, defense=10
    )
    m = CombatEntity(
        id="m1", name="炎蛛", realm="二阶妖兽", tier=2,
        max_hp=200, hp=200, max_mp=50, mp=50, attack=15, defense=0
    )
    # 玩家身上同时有 reflect 增益与 burn 负面
    p.status_effects["reflect"] = 2
    p.status_effects["burn"] = 1

    # 施展木系青帝长生引
    res = SpellCombatEngine.step_round(p, m, action="spell", spell_key="wood_heal")
    # 应当拔除真火灼烧，但保留明王反震
    assert "burn" not in p.status_effects
    # reflect 在反击和回合末递减 1，但不会被青帝长生引误当成负面拔除
    assert p.status_effects.get("reflect", 0) == 1
    assert any("真火灼烧" in line for line in res["logs"])


def test_equipped_gear_enhances_combat_entity():
    init_db()
    c = WorldClock.create_new_character("u_gear_tester", "多宝散修")
    from core.items import ItemFactory
    # 佩戴武器与玄龟甲
    weapon = ItemFactory.create_equip("纯阳金光剑", tier=3, slot="weapon", base_power=40.0)
    c.add_item_entity(weapon)
    c.equipped.append("纯阳金光剑")

    armor = ItemFactory.create_equip("玄龟灵甲", tier=2, slot="armor", base_power=20.0)
    c.add_item_entity(armor)
    c.equipped.append("玄龟灵甲")

    p = create_player_entity(c)
    assert p.equipped_weapon == "纯阳金光剑"
    assert p.attack > 25  # 显著高于基础攻击
    assert p.defense > 8  # 显著高于基础防御

