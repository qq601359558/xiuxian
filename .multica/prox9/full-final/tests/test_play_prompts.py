"""
玩法 Prompt 库
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.play_prompts import PROMPT_BUILDERS, combat_prompt, tribulation_prompt, world_event_prompt


def test_registry_size():
    assert len(PROMPT_BUILDERS) >= 20
    print(f"✓ Prompt builders {len(PROMPT_BUILDERS)}")


def test_combat_prompt_contains_schema():
    p = combat_prompt("甲", "乙", 0.6, facts=None)
    assert "outcome" in p and "kill" in p and "JSON" in p
    assert "硬约束" in p
    print("✓ combat prompt")


def test_tribulation_has_interval():
    p = tribulation_prompt("甲", "练气", "筑基", 0.45, 80, 10, 5, 90, lo=0.35, hi=0.55)
    assert "0.350" in p and "0.550" in p
    assert "adj_prob" in p
    print("✓ tribulation prompt")


def test_world_event_effects_clamp_mention():
    p = world_event_prompt("甲", "fortune", "赶路", 50, 3, "坊市")
    assert "effects" in p and "spawn" in p
    print("✓ world_event prompt")


def test_all_builders_callable():
    # 各 builder 至少能产出非空字符串（用默认/最小参）
    samples = [
        ("adventure", lambda: PROMPT_BUILDERS["adventure"]("甲", "野外", True, 1, "山")),
        ("omen_outcome", lambda: PROMPT_BUILDERS["omen_outcome"]("残碑", "坐", "修为+1", "甲")),
        ("rumor_twist", lambda: PROMPT_BUILDERS["rumor_twist"]("有人打架")),
        ("hunt_announce", lambda: PROMPT_BUILDERS["hunt_announce"]("甲", "乙", "坊市")),
        ("graduation", lambda: PROMPT_BUILDERS["graduation"]("师", "徒")),
        ("ring_accept", lambda: PROMPT_BUILDERS["ring_accept"]("青云宗", "巡山", "去", "甲")),
        ("master_task", lambda: PROMPT_BUILDERS["master_task"]("师", "徒", "采药")),
        ("custom_art", lambda: PROMPT_BUILDERS["custom_art"]("甲", "噬血")),
        ("forge", lambda: PROMPT_BUILDERS["forge"]("pill", "疗伤", "聚气丹")),
        ("collusion", lambda: PROMPT_BUILDERS["collusion"]("密谈", "仇", "n", "坊市", "甲", "练气", "乙", "筑基")),
        ("npc_proactive", lambda: PROMPT_BUILDERS["npc_proactive"]("柳", "练气", "谨慎", "人设", "甲", "中立", "坊市")),
        ("trade_haggle", lambda: PROMPT_BUILDERS["trade_haggle"]("甲", "柳三娘", "聚气丹", 40, 0.9, persona_seller="掌柜")),
        ("trade_face_offer", lambda: PROMPT_BUILDERS["trade_face_offer"]("甲", "乙", 100, 50, "灵芝", "", "坊市")),
        ("auction_bid", lambda: PROMPT_BUILDERS["auction_bid"]("甲", "青锋剑", 200, "乙", 500)),
        ("auction_settle", lambda: PROMPT_BUILDERS["auction_settle"]("青锋剑", "甲", 200, "乙")),
        ("market_guild", lambda: PROMPT_BUILDERS["market_guild"]("甲", "购入", "聚气丹", 1, 40)),
    ]
    for name, fn in samples:
        s = fn()
        assert isinstance(s, str) and len(s) > 20, name
    print(f"✓ {len(samples)} builders 可调用")


if __name__ == "__main__":
    test_registry_size()
    test_combat_prompt_contains_schema()
    test_tribulation_has_interval()
    test_world_event_effects_clamp_mention()
    test_all_builders_callable()
    print("\n✅ play_prompts 测试通过")
