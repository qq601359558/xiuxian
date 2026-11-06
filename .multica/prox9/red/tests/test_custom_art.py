"""
自创功法品阶与功效
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.art import clamp_art, infer_rank, format_art_card, best_exp_multiplier, total_burn_per_year, ART_RANKS
from ai.validator import DSLValidator
from ai.gateway import AIGateway
import config
import ai.gateway as gw


def test_infer_rank():
    assert infer_rank(1.1, 0, 0) == "MORTAL"
    assert infer_rank(1.3, 0, 0) == "EARTH"
    assert infer_rank(1.6, 0.3, 0) == "MYSTIC"
    assert infer_rank(1.9, 0.4, 0.2) == "HEAVEN"
    assert infer_rank(2.3, 1.0, 0.3) == "IMMORTAL"
    print("✓ 品阶反推")


def test_clamp_forces_cost():
    data = {
        "name": "无代价魔功",
        "rank": "MORTAL",
        "nature": "EVIL",
        "cultivation_modifiers": {
            "exp_gain_multiplier": 1.8,
            "lifespan_burn_per_year": 0.0,
            "tribulation_power_add": 0.0,
        },
        "spells": [{"name": "x", "effect_type": "DAMAGE", "multiplier": 9.0}],
    }
    out = clamp_art(data)
    mods = out["cultivation_modifiers"]
    assert mods["exp_gain_multiplier"] <= 2.5
    assert mods["lifespan_burn_per_year"] >= 0.2 or mods["tribulation_power_add"] >= 0.15
    assert out["spells"][0]["multiplier"] <= 3.0
    assert out["rank"] == "HEAVEN"
    assert "修炼加速" in out["effects_text"]
    print("✓ 钳制与功效文本")


def test_card_and_local_gen():
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    gw.LLM_API_KEY = ""
    gw.USE_CCSWITCH = False
    art = AIGateway.generate_custom_art("噬血炼骨", "测试道人")
    valid, msg = DSLValidator.validate_custom_art(art)
    assert valid, msg
    card = format_art_card(art)
    assert "自创功法" in card
    assert "修炼" in card
    assert art.get("rank_cn") in ("凡品", "人品", "地品", "天品", "仙品")
    m = best_exp_multiplier([art])
    b = total_burn_per_year([art])
    assert m >= 1.0 and b >= 0.0
    print(card.splitlines()[0])
    print("✓ 卡片与本地生成")


if __name__ == "__main__":
    test_infer_rank()
    test_clamp_forces_cost()
    test_card_and_local_gen()
    print("\n✅ 功法品阶测试通过")
