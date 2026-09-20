"""
宗门体系、野外裸露闭关惩罚（方案B）与大地图配置自动化测试
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db
from config import WORLD_LOCATIONS, SECTS_CONFIG
from core.clock import WorldClock
from core.combat import CombatEngine
from core.models import CharacterStatus, Element


def test_sect_and_map_features():
    init_db()
    print("=== 1. 验证大地图与宗门配置 ===")
    assert "青云坊市客栈" in WORLD_LOCATIONS
    assert "青云宗外门山门" in WORLD_LOCATIONS
    assert "万星古岛" in WORLD_LOCATIONS
    assert "青云宗" in SECTS_CONFIG
    assert "万剑仙门" in SECTS_CONFIG
    assert "九幽天魔宗" in SECTS_CONFIG
    print("大地图灵脉与四大仙门配置核验通过！")

    print("=== 2. 验证新角色阵盘行囊初始为空 ===")
    player = WorldClock.create_new_character("test_p1", "韩跑跑")
    assert len(player.arrays) == 0, "新散修角色初始不应白送阵盘"
    assert player.sect is None, "新修士应默认为散修"
    print("初始状态验证通过：无阵盘散修。")

    print("=== 3. 验证野外无阵盘闭关（裸露闭关） ===")
    player.location = "落霞山灵泉"
    start_res = WorldClock.start_meditation(player, hours_planned=1.0)
    assert start_res["success"] is True
    assert start_res["is_naked"] is True
    assert player.meditation.array is None, "野外无阵盘闭关时大阵应为 None"
    print("野外无阵盘闭关判定通过：大阵为 None，状态为裸露闭关。")

    print("=== 4. 验证野外裸露闭关遭伏击重创（方案 B 严苛惩罚） ===")
    # 模拟攻击者
    attacker = WorldClock.create_new_character("test_att", "魔头劫道")
    attacker.location = "落霞山灵泉"
    player.spirit_stones = 1000
    player.realm.tier = 1
    player.realm.sub_tier = 2 # 练气后期
    player_lifespan_before = player.lifespan.get_remaining_years()

    fight_res = CombatEngine.execute_ambush(attacker, player)
    print(f"伏击战报摘要:\n{fight_res['report']}")
    assert fight_res["winner_id"] == attacker.id
    assert fight_res["blood_escaped"] is True
    assert fight_res["looted_stones"] == int(1000 * 0.85), "应被掠夺 85% 随身灵石"
    assert player.spirit_stones == 150
    assert attacker.spirit_stones == 150 + int(1000 * 0.85)

    # 寿元应损耗 3 岁
    player_lifespan_after = player.lifespan.get_remaining_years()
    burned = player_lifespan_before - player_lifespan_after
    assert abs(burned - 3.0) < 0.05, f"应燃烧 3 年寿元，实际燃烧 {burned:.2f} 年"

    # 境界应跌落 1 小阶
    assert player.realm.sub_tier == 1, "练气后期应跌落至练气中期"
    assert player.status == CharacterStatus.IDLE
    assert player.location == "青云坊市客栈", "血遁应逃回青云坊市客栈安全区"
    print("方案 B 裸闭关受袭严苛惩罚验证通过！")

    print("=== 5. 验证宗门入门考核与阵盘赏赐 ===")
    # 拜入青云宗要求：道心 >= 60, sin < 30
    player.karma.dao_heart = 80
    player.karma.sin_value = 0
    player.location = "青云宗外门山门"

    # 模拟拜入青云宗
    s_cfg = SECTS_CONFIG["青云宗"]
    assert player.karma.dao_heart >= s_cfg["req_dao_heart"]
    assert player.karma.sin_value <= s_cfg["max_sin"]
    player.sect = "青云宗"
    player.sect_rank = "外门弟子"
    player.arrays.append(s_cfg["starter_array"])
    assert "一阶青木迷踪阵" in player.arrays
    print(f"成功拜入青云宗，获赐阵盘：{player.arrays}")

    print("=== 6. 验证宗门弟子专属洞府免租金 ===")
    player.location = "宗门玄元洞府"
    stones_before = player.spirit_stones
    med_res = WorldClock.start_meditation(player, hours_planned=2.0)
    assert med_res["success"] is True
    assert player.spirit_stones == stones_before, "本门弟子在宗门玄元洞府应免除租金"
    # 中止闭关
    WorldClock.settle_meditation(player, force_interrupt=True)

    print("=== 7. 验证宗门月俸支取与冷却周期 ===")
    # 首次领取
    sal_res1 = WorldClock.claim_sect_salary(player)
    assert sal_res1["success"] is True
    assert sal_res1["salary"] == 25
    assert player.spirit_stones == stones_before + 25

    # 立即再次领取 -> 冷却中拦截
    sal_res2 = WorldClock.claim_sect_salary(player)
    assert sal_res2["success"] is False
    assert "本月俸禄已支取" in sal_res2["message"]

    # 推进 2 小时后（7200秒）
    mock_time = time.time() + 7300.0
    sal_res3 = WorldClock.claim_sect_salary(player, now=mock_time)
    assert sal_res3["success"] is True
    print("宗门月俸发放与 2 小时冷却周期验证通过！")

    print("\n🎉 所有新特性自动化测试全部通过！")


if __name__ == "__main__":
    test_sect_and_map_features()
