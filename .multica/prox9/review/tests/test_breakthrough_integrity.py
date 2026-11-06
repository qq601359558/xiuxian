"""
突破渡劫系统的道体合规守恒测试
"""
import pytest
from unittest.mock import patch
from core.clock import WorldClock
from core.breakthrough import BreakthroughEngine
from core.models import CharacterStatus
from storage.db import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def _make_cultivator(name: str):
    c = WorldClock.create_new_character(f"bt_{name}", name)
    c.status = CharacterStatus.IDLE
    return c


def test_breakthrough_blocked_when_dead():
    char = _make_cultivator("亡故修士")
    char.status = CharacterStatus.DEAD
    char.death_cause = "坐化"

    res = BreakthroughEngine.attempt_breakthrough(char)
    assert res["success"] is False
    assert res["is_fatal"] is True
    assert "已坐化道消" in res["message"]


def test_breakthrough_blocked_when_busy():
    char = _make_cultivator("入定修士")
    char.status = CharacterStatus.MEDITATING

    res = BreakthroughEngine.attempt_breakthrough(char)
    assert res["success"] is False
    assert "闭关锁门" in res["message"]

    char.status = CharacterStatus.CAPTURED
    res2 = BreakthroughEngine.attempt_breakthrough(char)
    assert res2["success"] is False
    assert "身陷囹圄" in res2["message"]


def test_breakthrough_blocked_when_exp_not_full():
    char = _make_cultivator("急功近利")
    char.realm.current_exp = char.realm.max_exp - 10

    res = BreakthroughEngine.attempt_breakthrough(char)
    assert res["success"] is False
    assert "修为尚未圆满" in res["message"]


def test_minor_breakthrough_success():
    char = _make_cultivator("稳健道友")
    char.realm.tier = 1
    char.realm.sub_tier = 0  # 练气初期
    char.realm.current_exp = char.realm.max_exp

    res = BreakthroughEngine.attempt_breakthrough(char)
    assert res["success"] is True
    assert res["is_major"] is False
    assert char.realm.sub_tier == 1
    assert "顺畅晋阶" in res["message"]


def test_major_breakthrough_fatal_on_lifespan_exhaustion():
    char = _make_cultivator("年迈道人")
    char.realm.tier = 1
    char.realm.sub_tier = 3  # 练气圆满
    char.realm.current_exp = char.realm.max_exp

    # 寿元仅剩 5 年
    import time
    from config import SECONDS_PER_GAME_YEAR
    char.lifespan.death_timestamp = time.time() + 5.0 * SECONDS_PER_GAME_YEAR

    # 模拟渡劫失败 -> 反噬削寿 15 年 -> 导致寿尽坐化
    with patch("ai.gateway.AIGateway.judge_tribulation", return_value={"success": False, "source": "rule", "reason": "雷劫过盛"}), \
         patch("random.randint", return_value=25), \
         patch("random.uniform", return_value=15.0):
        res = BreakthroughEngine.attempt_breakthrough(char)

    assert res["success"] is False
    assert res["is_fatal"] is True
    assert char.status == CharacterStatus.DEAD
    assert "寿尽道消" in res["message"]
    assert "雷火焚脉" in res["message"]
