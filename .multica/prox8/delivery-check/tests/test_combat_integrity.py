"""
斗法伏击系统的道体合规守恒测试
"""
import pytest
import time
from core.clock import WorldClock
from core.combat import CombatEngine
from core.models import CharacterStatus, ArrayFormation
from storage.db import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def _make_fighter(name: str, stones: int = 100):
    c = WorldClock.create_new_character(f"cb_{name}", name)
    c.spirit_stones = stones
    c.born_at = time.time() - 80 * 3600.0  # 过新手庇护
    c.location = "黑水沼泽"  # 危险区域非安全区
    return c


def test_ambush_blocked_when_attacker_dead():
    att = _make_fighter("亡命刺客")
    dfe = _make_fighter("猎物")
    att.status = CharacterStatus.DEAD
    att.death_cause = "寿尽"

    res = CombatEngine.execute_ambush(att, dfe)
    assert res["success"] is False
    assert "已坐化道消" in res["message"]


def test_ambush_blocked_when_defender_dead():
    att = _make_fighter("刺客")
    dfe = _make_fighter("坐化老祖")
    dfe.status = CharacterStatus.DEAD

    res = CombatEngine.execute_ambush(att, dfe)
    assert res["success"] is False
    assert "已坐化道消" in res["message"]


def test_ambush_blocked_when_attacker_busy():
    att = _make_fighter("入定刺客")
    dfe = _make_fighter("猎物")
    att.status = CharacterStatus.MEDITATING

    res = CombatEngine.execute_ambush(att, dfe)
    assert res["success"] is False
    assert "闭关锁门" in res["message"]

    att.status = CharacterStatus.CAPTURED
    res2 = CombatEngine.execute_ambush(att, dfe)
    assert res2["success"] is False
    assert "身陷囹圄" in res2["message"]


def test_ambush_blocked_when_defender_captured():
    att = _make_fighter("刺客")
    dfe = _make_fighter("狱中散修")
    dfe.status = CharacterStatus.CAPTURED

    res = CombatEngine.execute_ambush(att, dfe)
    assert res["success"] is False
    assert "身陷囹圄被擒" in res["message"]


def test_combat_burn_lifespan_to_death():
    """验证燃寿防穿透：寿元不足时严格判定身死道消，绝不可穿透为 IDLE 苟活"""
    att = _make_fighter("强盗", stones=500)
    dfe = _make_fighter("垂死修士", stones=50)
    dfe.status = CharacterStatus.MEDITATING
    # 剩余寿元仅剩 0.5 年（少于荒野受创需燃寿的 3.0 年）
    dfe.lifespan.death_timestamp = time.time() + 86400 * 0.5

    res = CombatEngine.execute_ambush(att, dfe)
    assert res["target_died"] is True
    assert dfe.status == CharacterStatus.DEAD
    assert "燃寿道消" in res["report"] or "燃寿枯竭道消" in (dfe.death_cause or "")
