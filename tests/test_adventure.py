"""
外出探险：规则成功率、掉落钳制、失败亏损
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.adventure import AdventureEngine, resolve_target, _roll_loot, _success_prob
from config import SECRET_REALMS, ADVENTURE_LOOT_P


def _mk(name="探子", tier=1):
    now = time.time()
    c = Character(
        user_id=f"adv_{name}",
        name=name,
        realm=Realm(tier=tier, sub_tier=0, current_exp=1000),
        lifespan=Lifespan(birth_base=80, accumulated_gain=0, death_timestamp=now + 80 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.METAL], efficiency=1.2),
        location="青云坊市客栈",
        spirit_stones=500,
    )
    c.born_at = now - 80 * 3600.0
    return c


def test_targets_and_prob():
    t = resolve_target("野外")
    assert t and t["name"] == "野外"
    t2 = resolve_target("剑冢残碑")
    assert t2 and t2["name"] in SECRET_REALMS
    assert len(SECRET_REALMS) >= 6
    c = _mk()
    p = _success_prob(c, t)
    assert 0.15 <= p <= 0.92
    print("✓ 目标与成功率", round(p, 2), "秘境数", len(SECRET_REALMS))


def test_explore_local():
    import config
    import ai.gateway as gw
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    gw.LLM_API_KEY = ""
    gw.USE_CCSWITCH = False

    c = _mk("野外客")
    # 清冷却
    c.adventure_cd_until = 0
    res = AdventureEngine.explore(c, "野外", use_ai=False)
    assert res["success"] is True
    assert "盘缠" in res["message"] or "探险" in res["message"]
    assert res["stones_delta"] is not None
    print("✓ 本地探险结算", res["combat_success"], "exp", res["exp_delta"])


def test_loot_map_rare():
    import random
    hits = 0
    n = 2000
    for i in range(n):
        loot = _roll_loot(True, random.Random(i))
        if any(x["kind"] == "map" for x in loot):
            hits += 1
    rate = hits / n
    assert rate < 0.2, rate  # 应远低于其他掉落，允许波动
    print(f"✓ 藏宝图经验命中率 {rate:.3f}（目标约 {ADVENTURE_LOOT_P['map']}）")


def test_cooldown_and_fee():
    c = _mk("穷鬼", tier=1)
    c.spirit_stones = 5
    r = AdventureEngine.explore(c, "野外", use_ai=False)
    assert r["success"] is False
    c.spirit_stones = 500
    c.adventure_cd_until = time.time() + 1000
    r2 = AdventureEngine.explore(c, "野外", use_ai=False)
    assert r2["success"] is False and "未平" in r2["message"]
    print("✓ 盘缠与冷却门禁")


if __name__ == "__main__":
    test_targets_and_prob()
    test_explore_local()
    test_loot_map_rare()
    test_cooldown_and_fee()
    print("\n✅ 外出探险测试通过")
