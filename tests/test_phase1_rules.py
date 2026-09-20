"""
阶段1 规则引擎测试：庇护/逃遁、灵气稀释、目标、赛季
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.protection import ProtectionEngine, is_conflict_zone, protection_active
from core.qi import global_qi_multiplier, effective_density
from core.goals import GoalEngine
from core.season import season_info
from core.clock import WorldClock


def _make_char(name="测试修士", tier=1, loc="青云坊市客栈"):
    now = time.time()
    c = Character(
        user_id=f"t_{name}",
        name=name,
        realm=Realm(tier=tier, sub_tier=0, current_exp=0),
        lifespan=Lifespan(birth_base=80.0, accumulated_gain=0.0, death_timestamp=now + 80 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.METAL], efficiency=1.1),
        location=loc,
    )
    # 跳过新手庇护，便于测归隐/寄存
    c.born_at = now - 80 * 3600.0
    return c


def test_protection_and_flee():
    c = _make_char("归隐客", loc="青云坊市客栈")
    assert not is_conflict_zone(c.location)

    # 可归隐
    res = ProtectionEngine.enter_reclusion(c, hours=2)
    assert res["success"] is True
    assert protection_active(c)
    ok, _ = ProtectionEngine.can_be_attacked(c)
    assert ok is False

    # 庇护中不可寄存
    from core.market import MarketEngine

    c.spirit_stones = 500
    d = MarketEngine.deposit_stones(c, 100)
    assert d["success"] is False

    # 出隐后可寄存
    ProtectionEngine.exit_reclusion(c)
    d = MarketEngine.deposit_stones(c, 100)
    assert d["success"] is True

    # 冲突区不可归隐
    wild = _make_char("野修", loc="落霞山灵泉")
    assert is_conflict_zone(wild.location)
    r2 = ProtectionEngine.enter_reclusion(wild)
    assert r2["success"] is False

    # 冲突区下线 → 仓皇遁走
    wild.spirit_stones = 1000
    res = ProtectionEngine.settle_logout(wild)
    assert res["kind"] == "panic_flee"
    assert wild.spirit_stones < 1000

    # 斗法中下线 → 逃遁失败
    fighter = _make_char("搏杀者", loc="落霞山灵泉")
    fighter.spirit_stones = 1000
    ProtectionEngine.mark_combat(fighter)
    res = ProtectionEngine.settle_logout(fighter)
    assert res["kind"] == "combat_flee_fail"
    assert wild.spirit_stones < 1000
    print("✓ 庇护 / 逃遁失败 / 仓皇遁走")


def test_qi_dilution():
    m0 = global_qi_multiplier(high_count=0)
    assert abs(m0 - 1.0) < 1e-6
    m3 = global_qi_multiplier(high_count=3)
    assert m3 < 1.0
    m100 = global_qi_multiplier(high_count=100)
    assert m100 >= 0.50 - 1e-9
    info = effective_density(2.0, high_count=2)
    assert abs(info["effective"] - 2.0 * info["qi_multiplier"]) < 1e-9
    print("✓ 灵气总量稀释")


def test_goals():
    c = _make_char("问道者", tier=1)
    GoalEngine.ensure_goals(c)
    sources = {g["source"] for g in c.goals}
    assert "dao" in sources
    assert "newbie" in sources
    assert "season" in sources
    # 新机缘可拒
    r = GoalEngine.add_opportunity(c, "探落霞秘洞", "山中有异光。")
    assert r["success"]
    gid = r["goal"]["id"]
    rj = GoalEngine.reject(c, gid)
    assert rj["success"]
    # 道途不可拒
    dao_id = next(g["id"] for g in c.goals if g["source"] == "dao")
    rj2 = GoalEngine.reject(c, dao_id)
    assert rj2["success"] is False
    # 大境界突破刷新
    c.realm.tier = 2
    c.realm.sub_tier = 0
    GoalEngine.on_breakthrough_major(c)
    print("✓ 目标系统六类源 / 可接可拒")


def test_season():
    info = season_info()
    assert info["total_days"] == 84
    assert 0 <= info["day_in_season"] <= 84
    assert info["season_number"] >= 1
    print("✓ 赛季时钟")


def test_meditation_uses_qi():
    c = _make_char("闭关客", tier=1)
    start = WorldClock.start_meditation(c, hours_planned=1.0, stones_to_pledge=0)
    assert start["success"] is True
    mock_now = time.time() + 3600.0
    settle = WorldClock.settle_meditation(c, force_interrupt=False, now=mock_now)
    assert settle["success"] is True
    assert "qi_multiplier" in settle
    assert 0.50 <= settle["qi_multiplier"] <= 1.0
    print("✓ 闭关结算纳入灵气稀释")


if __name__ == "__main__":
    test_protection_and_flee()
    test_qi_dilution()
    test_goals()
    test_season()
    test_meditation_uses_qi()
    print("\n✅ 阶段1 新规则测试全部通过")
