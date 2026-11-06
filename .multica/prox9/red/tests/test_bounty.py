"""
悬赏与复仇自动化测试
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.models import CharacterStatus
from core.bounty import BountyEngine, Bounty, BountyStatus, KarmaLink


def _char(name: str, stones: int = 500):
    c = WorldClock.create_new_character(f"u_{name}", name)
    c.spirit_stones = stones
    return c


def test_place_bounty_deducts_and_creates_link():
    issuer = _char("苦主", stones=300)
    target = _char("仇家")
    res = BountyEngine.place_bounty(issuer, target, 100, reason="杀父之仇")
    assert res["success"] is True
    fee = max(1, int(100 * 0.10))
    assert issuer.spirit_stones == 300 - 100 - fee
    assert res["bounty"].status == BountyStatus.OPEN
    assert res["link"].link_type == "仇"
    print("✓ 挂赏扣款并建立仇怨链")


def test_reject_self_and_low_reward():
    a = _char("自赏")
    r1 = BountyEngine.place_bounty(a, a, 100)
    assert r1["success"] is False
    b = _char("贫者", stones=10)
    r2 = BountyEngine.place_bounty(b, a, 5)
    assert r2["success"] is False
    print("✓ 禁止自赏 / 赏金过低被拒")


def test_anonymous_costs_more():
    i1 = _char("明主", stones=400)
    i2 = _char("暗主", stones=400)
    t = _char("靶子")
    r1 = BountyEngine.place_bounty(i1, t, 100, anonymous=False)
    r2 = BountyEngine.place_bounty(i2, t, 100, anonymous=True)
    assert r1["success"] and r2["success"]
    assert r2["fee"] > r1["fee"]
    assert r2["bounty"].issuer_display() == "匿名苦主"
    print("✓ 匿名挂赏抽成更高")


def test_claim_rules():
    issuer = _char("令主")
    target = _char("猎物")
    hunter = _char("猎手")
    res = BountyEngine.place_bounty(issuer, target, 80)
    bounty = res["bounty"]

    r_self = BountyEngine.claim_bounty(target, bounty)
    assert r_self["success"] is False

    r_issuer = BountyEngine.claim_bounty(issuer, bounty)
    assert r_issuer["success"] is False

    r_ok = BountyEngine.claim_bounty(hunter, bounty)
    assert r_ok["success"] is True
    assert bounty.status == BountyStatus.CLAIMED
    assert bounty.hunter_id == hunter.id
    print("✓ 接令：禁目标/苦主，允许猎手")


def test_settle_on_kill_pays_once():
    issuer = _char("苦主甲", stones=500)
    hunter = _char("猎手甲")
    victim = _char("凶徒甲")
    victim.karma.add_sin(200)

    res = BountyEngine.place_bounty(issuer, victim, 150)
    bounty = res["bounty"]
    victim.status = CharacterStatus.DEAD

    stones_before = hunter.spirit_stones
    pay = BountyEngine.settle_on_kill(hunter, victim, [bounty])
    assert pay["bounty_paid"] is True
    assert pay["total_reward"] == 150
    assert hunter.spirit_stones == stones_before + 150
    assert bounty.status == BountyStatus.COMPLETED
    assert hunter.karma.merit_value > 0

    # 二次结算不得再付
    pay2 = BountyEngine.settle_on_kill(hunter, victim, [bounty])
    assert pay2["bounty_paid"] is False
    assert pay2["total_reward"] == 0
    print("✓ 击杀领赏一次结清，防双领")


def test_expired_bounty_not_paid():
    issuer = _char("苦主乙")
    hunter = _char("猎手乙")
    victim = _char("老鬼")
    now = time.time()
    bounty = Bounty(
        issuer_id=issuer.id,
        issuer_name=issuer.name,
        target_id=victim.id,
        target_name=victim.name,
        reward=90,
        created_at=now - 100000,
        expires_at=now - 1000,
        status=BountyStatus.OPEN,
    )
    victim.status = CharacterStatus.DEAD
    pay = BountyEngine.settle_on_kill(hunter, victim, [bounty], now=now)
    assert pay["bounty_paid"] is False
    assert bounty.status == BountyStatus.EXPIRED
    print("✓ 过期悬赏不发放")


def test_feud_link_strengthens():
    a = _char("张三")
    b = _char("李四")
    links = []
    l1 = BountyEngine.ensure_feud_link(links, a, b, note="初仇")
    assert l1 is not None and l1.strength == 1
    l2 = BountyEngine.ensure_feud_link(links, a, b, note="再仇")
    assert l2.id == l1.id
    assert l2.strength == 2
    assert len(links) == 1
    print("✓ 仇怨链不重复、可加强")


def main():
    test_place_bounty_deducts_and_creates_link()
    test_reject_self_and_low_reward()
    test_anonymous_costs_more()
    test_claim_rules()
    test_settle_on_kill_pays_once()
    test_expired_bounty_not_paid()
    test_feud_link_strengthens()
    print("\n✅ 悬赏与复仇 测试全部通过")


if __name__ == "__main__":
    main()
