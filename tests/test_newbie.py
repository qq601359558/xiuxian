"""新手庇护测试"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.models import CharacterStatus
from core.combat_fate import CombatFateEngine
from config import SECONDS_PER_GAME_YEAR


def _char(name, tier=1, sub=0, born_offset=0.0):
    c = WorldClock.create_new_character(f"nb_{name}", name)
    c.realm.tier = tier
    c.realm.sub_tier = sub
    c.born_at = time.time() - born_offset
    return c


def main():
    # 新号应受保护
    p = _char("菜鸟")
    assert p.is_newbie_protected() is True
    print("✓ 新号 72h 庇护生效")

    # 超 72h 不保护
    old = _char("老鸟", born_offset=73 * 3600)
    assert old.is_newbie_protected() is False
    print("✓ 超过 72h 解除庇护")

    # 高境界不保护
    strong = _char("高手", tier=2, sub=1)
    assert strong.is_newbie_protected() is False
    print("✓ 筑基中期以上无新手庇护")

    # 斗法互拦
    a = _char("杀手", born_offset=80 * 3600)
    d = _char("目标")
    a.location = d.location = "落霞山灵泉(野外)"
    res = CombatFateEngine.resolve_ambush(a, d)
    assert res["success"] is False
    assert "新手" in res["message"] or "庇护" in res["message"]
    print(f"✓ 攻击新手被拦：{res['message'][:30]}…")

    # 新手也不能主动动手
    a2 = _char("莽夫")
    d2 = _char("路人", born_offset=80 * 3600, tier=1)
    a2.location = d2.location = "落霞山灵泉(野外)"
    res2 = CombatFateEngine.resolve_ambush(a2, d2)
    assert res2["success"] is False
    print("✓ 新手不可主动伤人（对称）")

    print("\n✅ 新手庇护 测试通过")


if __name__ == "__main__":
    main()
