"""
AI 叙事层：无 AI 时必须静默回退原文；有预算门禁
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, WorldStateRepository
from core import ai_flavor


def test_fallback_without_ai():
    init_db()
    # 强制无 AI：清 key
    import config
    import ai.gateway as gw

    old1, old2 = config.LLM_API_KEY, gw.LLM_API_KEY
    oldc, oldgc = config.USE_CCSWITCH, gw.USE_CCSWITCH
    config.LLM_API_KEY = ""
    gw.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    gw.USE_CCSWITCH = False
    try:
        assert ai_flavor.polish_omen_open("测试", "原文开场") == "原文开场"
        assert ai_flavor.polish_omen_outcome("测试", "选一", "修为+10")  # 非空
        assert ai_flavor.twist_rumor("有人在坊市打架") == "有人在坊市打架"
        assert ai_flavor.polish_ring_accept("青云宗", "巡山", "去巡山") == "去巡山"
    finally:
        config.LLM_API_KEY = old1
        gw.LLM_API_KEY = old2
        config.USE_CCSWITCH = oldc
        gw.USE_CCSWITCH = oldgc
    print("✓ 无 AI 回退原文")


def test_budget_gate():
    init_db()
    WorldStateRepository.delete(ai_flavor._BUDGET_KEY)
    import time as _t

    af = ai_flavor
    af._window_start = _t.time()
    af._used = af._BUDGET_PER_HOUR
    af._loaded = True
    assert af._consume() is False
    af._used = 0
    assert af._consume() is True
    print("✓ 预算门禁")


def test_polish_outcome_shape():
    r = ai_flavor.polish_omen_outcome("残碑", "静坐", "修为+80", who="甲")
    assert isinstance(r, str) and len(r) > 0
    print("✓ 落账判词非空")


def test_ask_short_timeout_no_circuit_count(monkeypatch):
    """MF-1 复审收口：_ask / polish 路径调 _chat_json 时 timeout<=2
    且 count_failure is False（纯叙事点缀，不计主通道熔断）。"""
    import ai.gateway as gw

    calls = []

    def _fake_chat_json(prompt, timeout=12.0, *, count_failure=True):
        calls.append({"timeout": timeout, "count_failure": count_failure})
        return {"line": "润色句"}

    monkeypatch.setattr(gw, "_chat_json", _fake_chat_json)
    monkeypatch.setattr(gw, "ai_ready", lambda: True)
    monkeypatch.setattr(ai_flavor, "_consume", lambda: True)

    # _ask 直调：调用方传 10.0 也须被钳制到 <=2
    assert ai_flavor._ask("prompt", timeout=10.0) == "润色句"
    # polish 路径：twist_rumor 内部传 timeout=10.0，同样须收口
    assert ai_flavor.twist_rumor("有人在坊市打架") == "润色句"
    assert ai_flavor.polish_auction_settle("剑", "甲", 100, "乙") == "润色句"
    assert ai_flavor.polish_karma_outcome("en", 1, "甲", "乙", "已落账") == "润色句"
    assert len(calls) == 4
    for c in calls:
        assert c["timeout"] <= 2.0, c
        assert c["count_failure"] is False, c
    print("✓ ai_flavor 收口：timeout<=2 且 count_failure=False")


if __name__ == "__main__":
    test_fallback_without_ai()
    test_budget_gate()
    test_polish_outcome_shape()
    print("\n✅ ai_flavor 测试通过")
