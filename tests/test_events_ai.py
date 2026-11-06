"""
世界事件与 AI 渡劫判定（含降级）自动化测试
"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.events import EventEngine
from core.breakthrough import BreakthroughEngine
from ai.event_validator import EventValidator
from ai.gateway import AIGateway
from config import EVENT_EFFECT_CAPS


def _char(name="试炼者"):
    return WorldClock.create_new_character(f"e_{name}", name)


def test_validator_clamps_insane_effects():
    evil = {
        "type": "fortune",
        "title": "天降横财",
        "narrative": "你捡到一百万灵石。",
        "effects": {
            "stones": 1_000_000,
            "exp": 999999,
            "lifespan_years": 999,
            "sin": 0,
        },
    }
    ok, _msg, cleaned = EventValidator.validate_event(evil)
    assert ok is True
    assert cleaned["effects"]["stones"] <= EVENT_EFFECT_CAPS["stones_gain"]
    assert cleaned["effects"]["exp"] <= EVENT_EFFECT_CAPS["exp"]
    assert cleaned["effects"]["lifespan_years"] <= EVENT_EFFECT_CAPS["lifespan_gain"]
    print("✓ AI 超模效果被规则钳制")


def test_local_event_applies():
    c = _char()
    before_exp = c.realm.current_exp
    ev = EventEngine.fire(c, etype="fortune", force=True)
    # 无 API Key 时应走 local
    assert ev is not None
    assert ev["type"] == "fortune"
    assert ev["narrative"]
    assert "source" in ev
    print(f"✓ 本地机缘触发：{ev['title']} → {ev['effects_summary']}（source={ev['source']}）")


def _state_snapshot(c):
    """事件可改动的全部属性快照（与 EventEngine.apply_effects 的效果键对齐）"""
    return (
        c.spirit_stones,
        # 寿元随墙钟惰性流逝，四舍五入到 0.001 岁（≈86 秒）以免把自然流逝误判为事件改动
        round(c.lifespan.get_remaining_years(), 3),
        c.realm.current_exp,
        c.karma.sin_value,
        c.karma.merit_value,
        c.karma.dao_heart,
        c.karma.blood_mark_until,
        list(c.inventory),
        list(c.arrays),
        list(c.skills),
    )


def test_crisis_can_burn_lifespan_or_stones():
    c = _char("遇难者")
    c.spirit_stones = 500
    before = _state_snapshot(c)
    ev = EventEngine.fire(c, etype="crisis", force=True)
    assert ev is not None
    assert ev["type"] == "crisis"
<<<<<<< HEAD
    # 至少有一项被改动或纯叙事
    changed = (
        c.spirit_stones != stones0
        or abs(c.lifespan.get_remaining_years() - life0) > 1e-6
        or c.karma.dao_heart != 100
        or c.karma.sin_value != 0
        or c.realm.current_exp != 0
        or ev["effects"] == {}
    )
=======
    # 危机池并非每条都烧灵石/寿元（有的挫道心、有的增业力）：
    # 断言「任一可改属性发生变化，或纯叙事（效果为空）」，避免随机抽池导致的 flaky。
    changed = _state_snapshot(c) != before or ev["effects"] == {}
>>>>>>> fb383c1fb995e8dabd8bd77ac6775956a22274bf
    assert changed
    print(f"✓ 危机事件：{ev['title']} → {ev['effects_summary']}")


def test_force_trigger_always_fires():
    for et in ("fortune", "crisis", "omen"):
        c = _char(et)
        ev = EventEngine.fire(c, etype=et, force=True)
        assert ev is not None
        assert ev["type"] == et
    print("✓ 强制触发三类事件均成功")


def test_tribulation_fallback_rule_judge():
    """无 API Key 时渡劫应回退规则骰，且不是百分百成功/失败"""
    successes = 0
    trials = 40
    for i in range(trials):
        c = _char(f"劫{i}")
        c.realm.sub_tier = 3
        c.realm.current_exp = c.realm.max_exp
        res = BreakthroughEngine.attempt_breakthrough(c, use_pill=False)
        if res["success"]:
            successes += 1
        # 小阶不会走到这里；大境界应有 judge 信息
        assert "prob_pct" in res
    rate = successes / trials
    assert 0 < successes < trials, f"渡劫结果异常：{successes}/{trials}"
    print(f"✓ 渡劫非必成：{successes}/{trials} 成功（约 {rate*100:.0f}%）")


def test_tribulation_judge_return_shape():
    c = _char("判劫")
    j = AIGateway.judge_tribulation(c, rule_prob=0.35, target_realm="筑基期")
    assert "success" in j
    assert isinstance(j["success"], bool)
    assert j["source"] in ("ai", "rule")
    assert 0.05 <= j.get("adj_prob", 0.35) <= 0.95 or j["source"] == "rule"
    print(f"✓ 渡劫判定接口可用（source={j['source']}）")


def main():
    test_validator_clamps_insane_effects()
    test_local_event_applies()
    test_crisis_can_burn_lifespan_or_stones()
    test_force_trigger_always_fires()
    test_tribulation_fallback_rule_judge()
    test_tribulation_judge_return_shape()
    print("\n✅ 世界事件与渡劫判定 测试全部通过")


if __name__ == "__main__":
    main()
