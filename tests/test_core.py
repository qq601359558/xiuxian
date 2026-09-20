"""
核心规则引擎自动化测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, ChronicleRepository
from core.clock import WorldClock
from core.breakthrough import BreakthroughEngine
from core.combat import CombatEngine
from ai.gateway import AIGateway
from ai.validator import DSLValidator


def test_game_flow():
    print("=== 1. 初始化数据库 ===")
    init_db()

    print("=== 2. 创建测试修士 ===")
    c1 = WorldClock.create_new_character("test_user_01", "厉飞雨")
    print(f"创建成功: {c1.name}, 灵根: {c1.spiritual_root.display_name()}, 出生寿元: {c1.lifespan.birth_base:.1f}岁")
    assert c1.lifespan.get_remaining_years() > 69.0

    print("=== 3. 测试现实时间并行闭关（闭关锁定与出关结算） ===")
    import time
    start_res = WorldClock.start_meditation(c1, hours_planned=2.0, stones_to_pledge=30)
    print(f"发起闭关: {start_res['message']}")
    assert c1.status.value == "MEDITATING"
    
    # 模拟现实时间推进 2 小时后出关结算
    mock_now = time.time() + 7200.0
    settle_res = WorldClock.settle_meditation(c1, force_interrupt=False, now=mock_now)
    print(f"出关结算: 消耗现实2小时 -> 度过游戏日 {settle_res['consumed_days']} 天, 损耗寿元 {settle_res['consumed_years']:.3f} 岁, 获得修为 {settle_res['exp_gained']}")
    assert settle_res["success"] is True
    assert c1.status.value == "IDLE"
    assert settle_res["consumed_days"] == 30

    print("=== 4. 测试修为满溢与小阶突破 ===")
    c1.realm.current_exp = c1.realm.max_exp
    res = BreakthroughEngine.attempt_breakthrough(c1)
    print(f"小阶突破结果: {res['message']}")
    assert res["success"] is True
    assert c1.realm.sub_tier == 1

    print("=== 5. 测试大境界天劫突破（练气圆满冲刺筑基） ===")
    c1.realm.sub_tier = 3
    c1.realm.current_exp = c1.realm.max_exp
    trib_res = BreakthroughEngine.attempt_breakthrough(c1, use_pill=True)
    print(f"大境界突破判定: success={trib_res['success']}, 报告: {trib_res['message']}")

    print("=== 6. 测试神识探查与野外斗法 ===")
    c2 = WorldClock.create_new_character("test_user_02", "陆仁贾")
    c2.spirit_stones = 500
    c1.location = "落霞山灵泉(野外)"
    c2.location = "落霞山灵泉(野外)"
    scan_res = CombatEngine.scan_surroundings(c1, [c2])
    print(f"神识扫描探查到目标数量: {len(scan_res)}")
    assert len(scan_res) > 0

    fight_res = CombatEngine.execute_ambush(c1, c2)
    print(f"斗法结果摘要:\n{fight_res.get('report', fight_res.get('message'))}")

    print("=== 7. 测试 AI 功法自创与 DSL 校验 ===")
    art = AIGateway.generate_custom_art("吞噬同门精血炼骨", c1.name)
    valid, check_msg = DSLValidator.validate_custom_art(art)
    print(f"自创功法: {art['name']}, 校验结果: {valid} ({check_msg})")
    assert valid is True

    print("\n✅ 所有核心规则自动化单元测试均 100% 通过！")


if __name__ == "__main__":
    test_game_flow()
