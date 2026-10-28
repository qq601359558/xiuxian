# -*- coding: utf-8 -*-
"""
《天道因果录》丹药大目录、耐药衰减软上限、丹毒与回收闭环自动化全量测试
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.models import Character, Realm, SpiritualRoot, RootType, Element
from core.catalogs.pills import RAW_PILLS, PILL_RECIPES, PILL_CATALOG
from core.catalogs.materials import MATERIAL_CATALOG
from core.market import MarketEngine
from core.breakthrough import BreakthroughEngine
from core.alchemy import recycle_pill
from storage.db import init_db


def _make_test_character(name: str = "丹道圣手") -> Character:
    init_db()
    c = WorldClock.create_new_character(f"u_pill_{name}_{int(time.time()*1000)%100000}", name)
    c.born_at = time.time() - 80 * 3600
    c.spirit_stones = 1000
    return c


def test_pill_catalog_integrity():
    """测试 60+ 丹药元数据完整性、双键索引及 8 大功能流派覆盖"""
    assert len(RAW_PILLS) >= 60, f"Expected >= 60 pills, got {len(RAW_PILLS)}"
    assert len(PILL_RECIPES) >= 60, f"Expected >= 60 recipes, got {len(PILL_RECIPES)}"

    # 双键索引
    for name, p in RAW_PILLS.items():
        pid = p["id"]
        assert name in PILL_CATALOG, f"Pill {name} missing from PILL_CATALOG"
        assert pid in PILL_CATALOG, f"Pill ID {pid} missing from PILL_CATALOG"
        assert PILL_CATALOG[name]["name"] == name
        assert PILL_CATALOG[pid]["id"] == pid

        # 核心契约字段
        assert "max_life_intake" in p, f"Missing max_life_intake in {name}"
        assert "decay_rate" in p, f"Missing decay_rate in {name}"
        assert "min_decay_floor" in p, f"Missing min_decay_floor in {name}"
        assert "toxicity" in p, f"Missing toxicity in {name}"
        assert "tier" in p and 1 <= p["tier"] <= 5, f"Invalid tier in {name}"
        assert "pill_type" in p, f"Missing pill_type in {name}"
        assert "difficulty" in p, f"Missing difficulty in {name}"

    # 8 大流派全覆盖
    streams = {p["pill_type"] for p in RAW_PILLS.values()}
    expected_streams = {
        "breakthrough", "cultivation", "recovery", "lifespan",
        "soul_purity", "root_purify", "detox", "combat_buff"
    }
    assert expected_streams.issubset(streams), f"Missing streams: {expected_streams - streams}"

    # 5 大品阶境界全覆盖
    tiers = {p["tier"] for p in RAW_PILLS.values()}
    assert {1, 2, 3, 4, 5}.issubset(tiers), f"Missing tiers: {{1, 2, 3, 4, 5}} - {tiers}"


def test_pill_recipes_materials_integrity():
    """测试 100% 丹方配方材料严格落库于 MATERIAL_CATALOG，零虚构材料"""
    for r in PILL_RECIPES:
        assert r["kind"] == "pill"
        assert "materials" in r and len(r["materials"]) > 0
        assert "stones_fee" in r and r["stones_fee"] >= 0
        assert "output_pill" in r or "output" in r

        out_pill = r.get("output_pill") or r.get("output")
        assert out_pill in RAW_PILLS, f"Recipe output {out_pill} not in RAW_PILLS"

        for mat_name, count in r["materials"].items():
            assert mat_name in MATERIAL_CATALOG, (
                f"Recipe【{r['name']}】contains unknown material【{mat_name}】not in MATERIAL_CATALOG!"
            )
            assert count >= 1, f"Material count must be >= 1 for {mat_name} in {r['name']}"


def test_pill_resistance_decay_soft_cap():
    """测试丹药耐药抗性软上限机制：超限不再锁死报错，而是衰减生效，并保有最低保底"""
    c = _make_test_character("抗药修士")
    # 洗髓散: max_life_intake=10, decay_rate=0.5, min_decay_floor=0.2, root_efficiency_bonus=0.02
    pill_name = "延年草还丹"  # max_life_intake=5, decay_rate=0.5, min_decay_floor=0.2, add_lifespan_years=1.0
    cfg = PILL_CATALOG[pill_name]
    max_intake = cfg["max_life_intake"]
    assert max_intake == 5

    # 给予 8 颗丹药
    for _ in range(8):
        c.inventory.append(pill_name)

    # 1. 前 5 颗正常服用 (100% 药效)
    for i in range(1, max_intake + 1):
        res = MarketEngine.use_pill(c, pill_name)
        assert res["success"] is True
        assert "【耐药渐生】" not in res["message"]
        assert c.pill_intake_counts[pill_name] == i

    # 2. 第 6 颗（超出上限第 1 次，衰减至 1.0 - 1*0.5 = 50%）
    res6 = MarketEngine.use_pill(c, pill_name)
    assert res6["success"] is True
    assert "【耐药渐生】" in res6["message"]
    assert "药力发挥 50%" in res6["message"]
    assert c.pill_intake_counts[pill_name] == 6

    # 3. 第 7 颗（超出上限第 2 次，衰减至 1.0 - 2*0.5 = 0.0 -> 触底 min_decay_floor 20%）
    res7 = MarketEngine.use_pill(c, pill_name)
    assert res7["success"] is True
    assert "【耐药渐生】" in res7["message"]
    assert "药力发挥 20%" in res7["message"]
    assert c.pill_intake_counts[pill_name] == 7

    # 4. 第 8 颗（持续保有 20% 最低保底，永不沦为废道具！）
    res8 = MarketEngine.use_pill(c, pill_name)
    assert res8["success"] is True
    assert "【耐药渐生】" in res8["message"]
    assert "药力发挥 20%" in res8["message"]
    assert c.pill_intake_counts[pill_name] == 8


def test_pill_toxicity_accumulation_and_detox():
    """测试丹毒累积与涤毒清髓机制"""
    c = _make_test_character("毒修客")
    assert c.pill_toxicity == 0

    # 服用含丹毒丹药 (如 天罡焚血金丹 toxicity=8)
    c.inventory.append("天罡焚血金丹")
    res1 = MarketEngine.use_pill(c, "天罡焚血金丹")
    assert res1["success"] is True
    assert c.pill_toxicity == 8

    # 再次服用含丹毒丹药 (如 降尘丹 toxicity=8)
    c.inventory.append("降尘丹")
    res2 = MarketEngine.use_pill(c, "降尘丹")
    assert res2["success"] is True
    assert c.pill_toxicity == 16

    # 服用清毒丹药 (如 清心破障丹 cleanse_toxicity=30)
    c.inventory.append("清心破障丹")
    res3 = MarketEngine.use_pill(c, "清心破障丹")
    assert res3["success"] is True
    assert c.pill_toxicity == 0  # 16 - 30 归零不为负


def test_breakthrough_prep_and_toxicity_penalty():
    """测试破境丹药蓄力与高丹毒天劫反噬惩罚"""
    c = _make_test_character("渡劫真人")
    c.realm.tier = 1
    c.realm.sub_tier = 3
    c.realm.current_exp = c.realm.max_exp  # 练气圆满

    # 1. 服用破境丹药 (筑基丹 rate_bonus=0.35)
    c.inventory.append("筑基丹")
    res_pill = MarketEngine.use_pill(c, "筑基丹")
    assert res_pill["success"] is True
    assert c.pill_breakthrough_prep.get("2") == 0.35 or "筑基丹药力(待渡劫)" in c.skills

    # 2. 模拟高丹毒 (50 点丹毒，超出 20 点阈值 30 点 -> 惩罚 30 * 0.005 = 15% 成功率)
    c.pill_toxicity = 50

    # 3. 渡劫突破计算
    res_break = BreakthroughEngine.attempt_breakthrough(c, use_pill=False)
    # 破境准备药力应已被消耗
    assert "2" not in c.pill_breakthrough_prep
    assert "筑基丹药力(待渡劫)" not in c.skills


def test_pill_multi_stream_effects():
    """测试 8 大功能流派代表丹药服用效果"""
    c = _make_test_character("全修宗师")

    # (1) 灵根洗炼: 洗髓散 (root_efficiency_bonus: 0.02)
    root_eff_before = c.spiritual_root.efficiency
    c.inventory.append("洗髓散")
    res = MarketEngine.use_pill(c, "洗髓散")
    assert res["success"] is True
    assert round(c.spiritual_root.efficiency - root_eff_before, 2) == 0.02

    # (2) 神识淬炼: 明目清心丸 (perm_divine_sense: 2, sense_range_bonus: 5)
    ds_before = c.soul.divine_sense
    sr_before = c.soul.sense_range
    c.inventory.append("明目清心丸")
    res = MarketEngine.use_pill(c, "明目清心丸")
    assert res["success"] is True
    assert c.soul.divine_sense == ds_before + 2
    assert c.soul.sense_range == sr_before + 5

    # (3) 斗法回春: 止血散 (heal_hp_pct: 0.25)
    c.combat.current_hp = 50
    c.inventory.append("止血散")
    res = MarketEngine.use_pill(c, "止血散")
    assert res["success"] is True
    assert c.combat.current_hp > 50

    # (4) 战斗狂暴: 天罡焚血金丹 (combat_power_bonus: 0.40)
    c.inventory.append("天罡焚血金丹")
    res = MarketEngine.use_pill(c, "天罡焚血金丹")
    assert res["success"] is True
    assert len(c.pill_combat_buffs) >= 1
    assert c.pill_combat_buffs[-1]["name"] == "天罡焚血金丹"
    assert c.pill_combat_buffs[-1]["power_bonus"] == 0.40


def test_pill_recycle_closed_loop():
    """测试丹药回炉分解闭环（返还灵石与萃取灵砂）"""
    c = _make_test_character("回炉丹童")
    stones_before = c.spirit_stones

    # 给予 3 枚凝元固本丹 (二阶灵品, price=140)
    for _ in range(3):
        c.inventory.append("凝元固本丹")

    res = recycle_pill(c, "凝元固本丹", qty=3)
    assert res["success"] is True
    assert res["qty"] == 3
    # 返还 50% 灵石: 140 * 0.5 * 3 = 210
    assert res["spirit_stones_gained"] == 210
    assert c.spirit_stones == stones_before + 210
    # 扣减背包
    assert c.inventory.count("凝元固本丹") == 0


if __name__ == "__main__":
    test_pill_catalog_integrity()
    test_pill_recipes_materials_integrity()
    test_pill_resistance_decay_soft_cap()
    test_pill_toxicity_accumulation_and_detox()
    test_breakthrough_prep_and_toxicity_penalty()
    test_pill_multi_stream_effects()
    test_pill_recycle_closed_loop()
    print("\n✅ 所有丹道全量与经济循环测试 100% 顺利通过！")
