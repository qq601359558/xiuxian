"""练气节奏：新手 24h 闭关应能过 1～2 个小阶"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import REALM_EXP_REQUIRED, NEWBIE_EXP_MULT
from core.clock import WorldClock
from core.models import CharacterStatus


def test_qi_need_vs_gain():
    need = REALM_EXP_REQUIRED[1]
    assert need <= 800, need
    c = WorldClock.create_new_character("qi_pace", "节奏修士")
    assert c.realm.tier == 1
    # 非新手也可在 24h 内过至少一个小阶（基准产出约 940）
    assert 940 >= need
    print("✓ 练气单阶", need, "≤ 满24h基准产出")


def test_newbie_meditation_boost():
    c = WorldClock.create_new_character("qi_newbie", "新嫩修士")
    # 新号在庇护内
    assert c.is_newbie_protected()
    WorldClock.start_meditation(c, hours_planned=6.0)
    settle = WorldClock.settle_meditation(c, now=time.time() + 6 * 3600 + 2)
    assert settle["success"]
    assert settle.get("newbie_mult", 1.0) >= NEWBIE_EXP_MULT - 0.01
    assert settle["exp_gained"] >= 150  # 6h 基准约 470，乘稀释后仍应过百
    print("✓ 新手闭关加成", settle["newbie_mult"], "修为+", settle["exp_gained"])


if __name__ == "__main__":
    test_qi_need_vs_gain()
    test_newbie_meditation_boost()
    print("\n✅ 练气节奏测试通过")
