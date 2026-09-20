"""
转世与道统点自动化测试
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SECONDS_PER_GAME_YEAR, LEGACY_MAX_PER_LIFE, LEGACY_MAX_BOOSTS_PER_LIFE
from core.clock import WorldClock
from core.models import CharacterStatus
from core.legacy import LegacyEngine, LegacyAccount


def _fresh_char(name: str, tier: int = 1, sin: int = 0, merit: int = 0):
    c = WorldClock.create_new_character(f"user_{name}", name)
    c.realm.tier = tier
    c.karma.sin_value = sin
    c.karma.merit_value = merit
    return c


def test_points_scales_with_realm():
    low = LegacyEngine.compute_points(_fresh_char("凡人甲", tier=1))
    high = LegacyEngine.compute_points(_fresh_char("金丹乙", tier=3))
    assert high["capped"] > low["capped"]
    assert low["capped"] >= 1
    print("✓ 道统点随境界提升")


def test_sin_reduces_points():
    clean = LegacyEngine.compute_points(_fresh_char("清白", tier=2, sin=0))
    sinner = LegacyEngine.compute_points(_fresh_char("凶人", tier=2, sin=300))
    assert sinner["capped"] < clean["capped"]
    print("✓ 业力折损道统点")


def test_settle_awards_once_and_archives():
    account = LegacyAccount(user_id="t_settle")
    c = _fresh_char("坐化真人", tier=2, merit=80)
    c.status = CharacterStatus.DEAD

    res = LegacyEngine.settle_death(account, c, death_cause="寿尽坐化")
    assert res["success"] is True
    assert res["points_gained"] > 0
    assert account.points == res["points_gained"]
    assert account.total_lives == 1
    assert len(account.past_lives) == 1
    assert c.death_settled is True
    assert c.death_cause == "寿尽坐化"
    print("✓ 死亡结算入账并归档前世")


def test_suicide_penalty_and_gate():
    account = LegacyAccount(user_id="t_suicide")
    now = time.time()
    # 模拟窗口内已死 3 次
    account.death_times = [now - 100, now - 50, now - 10]

    c = _fresh_char("速死流", tier=1)
    c.status = CharacterStatus.DEAD
    res = LegacyEngine.settle_death(account, c, death_cause="故意送死", now=now + 1)
    assert res["penalty_applied"] is True
    assert res["points_gained"] <= res["points_raw"]

    # 再死两次触发转世冷却
    for i in range(2):
        c2 = _fresh_char(f"速死{i}", tier=1)
        c2.status = CharacterStatus.DEAD
        LegacyEngine.settle_death(account, c2, death_cause="故意送死", now=now + 2 + i)

    ok, msg = LegacyEngine.check_reincarnate_gate(account, now=now + 10)
    assert ok is False
    assert "静养" in msg or "转世" in msg or "轮回" in msg
    print("✓ 快速送死：道统点减半 + 转世冷却")


def test_birth_boosts_spend_points():
    account = LegacyAccount(user_id="t_boost", points=10)
    c = WorldClock.create_new_character("t_boost", "道统之子")
    base_stones = c.spirit_stones
    base_life = c.lifespan.get_remaining_years()
    base_eff = c.spiritual_root.efficiency

    res = LegacyEngine.apply_birth_boosts(c, account, ["stones", "lifespan", "skill"])
    assert res["success"] is True
    assert "出身灵石" in res["applied"]
    assert c.spirit_stones == base_stones + 150
    assert c.lifespan.get_remaining_years() > base_life
    assert any("御风" in s or "龟息" in s or "周天" in s or "血遁" in s for s in c.skills)
    assert account.points == 10 - res["spent"]
    assert res["spent"] == 1 + 2 + 2
    print("✓ 降生加成正确扣点并生效")

    # 洗练灵根单独验证
    c2 = WorldClock.create_new_character("t_root", "洗髓者")
    eff0 = c2.spiritual_root.efficiency
    res2 = LegacyEngine.apply_birth_boosts(c2, account, ["root"])
    assert res2["success"] is True
    assert c2.spiritual_root.efficiency == min(2.5, eff0 + 0.25)
    print("✓ 洗练灵根提升吸收效率")


def test_boost_limit():
    account = LegacyAccount(user_id="t_limit", points=100)
    c = WorldClock.create_new_character("t_limit", "贪心者")
    res = LegacyEngine.apply_birth_boosts(c, account, ["stones", "lifespan", "root", "skill"])
    assert res["success"] is False
    assert LEGACY_MAX_BOOSTS_PER_LIFE in range(1, 10)
    print("✓ 超过 3 项出身加成被拒绝")


def test_points_cap():
    c = _fresh_char("大能", tier=8, merit=5000)
    bd = LegacyEngine.compute_points(c)
    assert bd["capped"] == LEGACY_MAX_PER_LIFE
    print(f"✓ 单世道统点封顶 {LEGACY_MAX_PER_LIFE}")


def main():
    test_points_scales_with_realm()
    test_sin_reduces_points()
    test_settle_awards_once_and_archives()
    test_suicide_penalty_and_gate()
    test_birth_boosts_spend_points()
    test_boost_limit()
    test_points_cap()
    print("\n✅ 转世与道统点 测试全部通过")


if __name__ == "__main__":
    main()
