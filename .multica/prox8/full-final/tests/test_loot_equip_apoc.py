"""挖宝 / 装备 / 大劫 / 功法战力"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.loot_equip import DigEngine, EquipEngine, art_combat_bonus
from core.combat import CombatEngine
from core.season import settle_apocalypse, set_epoch, season_info
from core.art import clamp_art
from config import SEASON_DAYS
import config
import ai.gateway as gw

config.LLM_API_KEY = ""
config.USE_CCSWITCH = False
gw.LLM_API_KEY = ""
gw.USE_CCSWITCH = False


def _mk(name="测", tier=2):
    now = time.time()
    c = Character(
        user_id=f"t_{name}",
        name=name,
        realm=Realm(tier=tier, sub_tier=0, current_exp=500),
        lifespan=Lifespan(birth_base=80, accumulated_gain=0, death_timestamp=now + 80 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.METAL], efficiency=1.1),
        location="青云坊市客栈",
        spirit_stones=200,
    )
    c.born_at = now - 80 * 3600
    return c


def test_dig():
    from core.items import ItemKind
    c = _mk("挖宝人")
    r = DigEngine.dig(c)
    assert r["success"] is False
    c.inventory.append("藏宝图")
    r = DigEngine.dig(c)
    assert r["wrong_location"] is True
    # 移动至目标地点
    tmap = c.find_items_by_kind(ItemKind.TREASURE_MAP)[0]
    c.location = tmap.custom_metadata["target_node_name"]
    r2 = DigEngine.dig(c, choice_id="1")
    assert r2["success"] is True
    print("✓ 挖宝 V2 成功", r2.get("outcome"))



def test_equip_power():
    c = _mk("剑客", tier=2)
    base = CombatEngine.calculate_power(c)
    c.inventory.append("青锋剑")
    r = EquipEngine.equip(c, "青锋剑")
    assert r["success"]
    assert "青锋剑" in c.equipped and "青锋剑" not in c.inventory
    p2 = CombatEngine.calculate_power(c)
    assert p2 > base
    r2 = EquipEngine.unequip(c, "青锋剑")
    assert r2["success"]
    # 功法战力
    art = clamp_art({
        "name": "试剑诀",
        "nature": "ORTHODOX",
        "cultivation_modifiers": {"exp_gain_multiplier": 1.3, "lifespan_burn_per_year": 0, "tribulation_power_add": 0},
        "spells": [{"name": "剑气", "effect_type": "DAMAGE", "multiplier": 2.0}],
    })
    c.custom_arts = [art]
    p3 = CombatEngine.calculate_power(c)
    assert p3 > base
    print("✓ 穿戴+功法战力", round(base,1), "->", round(p2,1), "->", round(p3,1))


def test_apocalypse():
    set_epoch(time.time())
    r = settle_apocalypse()
    assert r["ok"] is False
    # 纪元最后一分钟 → 应劫
    set_epoch(time.time() - (SEASON_DAYS * 86400.0 - 60))
    info = season_info()
    assert info["is_ended"] is True, info
    r2 = settle_apocalypse()
    assert r2["ok"] is True, r2
    info = season_info()
    assert info["remain_real_days"] > 1
    print("✓ 大劫结算后新纪元", info["season_number"], "余", info["remain_real_days"])


def test_equip_slots_grades():
    from config import ITEM_CATALOG
    from core.loot_equip import EquipEngine
    c = _mk("换装客", tier=2)
    for n in ["青锋剑", "玄铁剑", "赤霄剑"]:
        c.inventory.append(n)
    r1 = EquipEngine.equip(c, "青锋剑")
    assert r1["success"] and r1["grade"] == "凡品"
    r2 = EquipEngine.equip(c, "玄铁剑")
    assert r2["success"]
    assert "青锋剑" in c.inventory  # 同槽替换
    assert "玄铁剑" in c.equipped
    c.inventory.append("软猬甲")
    EquipEngine.equip(c, "软猬甲")
    assert len(c.equipped) == 2  # 武器+护甲
    assert ITEM_CATALOG["斩仙剑"]["power_bonus"] >= 0.12
    print("✓ 槽位替换与品阶", r2["message"][:40])


if __name__ == "__main__":
    test_dig()
    test_equip_power()
    test_equip_slots_grades()
    test_apocalypse()
    print("\n✅ 挖宝/装备/大劫/功法战力 通过")
