"""
闭关托管上限、大限预警与洞府坐化兜底自动化测试
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SECONDS_PER_GAME_YEAR, MEDITATION_MAX_HOURS, LIFESPAN_WARNING_YEARS
from core.clock import WorldClock
from core.models import CharacterStatus


def _make_char(user_id: str, name: str, rem_years: float = 80.0):
    c = WorldClock.create_new_character(user_id, name)
    now = time.time()
    c.lifespan.death_timestamp = now + rem_years * SECONDS_PER_GAME_YEAR
    return c


def test_max_planned_hours_rejected():
    c = _make_char("t_cap", "上限真人")
    res = WorldClock.start_meditation(c, hours_planned=MEDITATION_MAX_HOURS * 3 + 1)
    assert res["success"] is False
    assert "至多" in res["message"] or "72" in res["message"]
    print("✓ 超过 72h 计划被拒绝")


def test_idle_sit_caps_exp_but_burns_lifespan():
    c = _make_char("t_idle", "枯坐道人", rem_years=100.0)
    start = time.time()
    res_start = WorldClock.start_meditation(c, hours_planned=30.0)
    assert res_start["success"] is True
    assert res_start.get("will_idle_sit") is True

    # 推进 30 小时后结算
    mock_now = start + 30 * 3600.0
    res = WorldClock.settle_meditation(c, force_interrupt=False, now=mock_now)
    assert res["success"] is True
    assert res["is_idle_sitting"] is True
    assert res["is_fatal"] is False
    # 有效吐纳封顶 24h
    assert abs(res["effective_hours"] - 24.0) < 0.01
    assert abs(res["actual_real_hours"] - 30.0) < 0.01
    # 寿元按 30h 全额扣除
    assert abs(res["consumed_years"] - 30.0 / 24.0) < 0.01
    # 修为应 >0（前 24h 仍有进境），不是全灭
    assert res["exp_gained"] > 0
    assert c.status == CharacterStatus.IDLE
    print("✓ 超 24h 枯坐：修为封顶、寿元照扣")


def test_lifespan_warning_during_meditation():
    # 剩余寿元约 9.5 岁，闭关 1 小时会维持在阈值以下
    c = _make_char("t_warn", "大限将至", rem_years=9.5)
    start = time.time()
    res_start = WorldClock.start_meditation(c, hours_planned=1.0)
    assert res_start["success"] is True
    assert res_start.get("near_death_warning") is True

    mid = start + 0.5 * 3600.0
    prog = WorldClock.get_meditation_progress(c, now=mid)
    assert prog["is_meditating"] is True
    assert prog["lifespan_warning"] is True
    assert prog["is_expired"] is False
    print("✓ 闭关途中触发大限预警")


def test_cannot_start_if_would_die_in_cave():
    c = _make_char("t_deny", "寿元不足", rem_years=0.05)
    # 1 小时 = 1/24 岁 ≈ 0.0417，0.05 略大于；2 小时必超
    res = WorldClock.start_meditation(c, hours_planned=2.0)
    assert res["success"] is False
    assert "坐化" in res["message"] or "寿元" in res["message"]
    print("✓ 计划时长会坐化时拒绝入关")


def test_death_mid_cave_settles_as_fatal():
    c = _make_char("t_die", "洞府坐化客", rem_years=50.0)
    res_start = WorldClock.start_meditation(c, hours_planned=2.0)
    assert res_start["success"] is True

    start = c.meditation.start_time
    end = c.meditation.end_time
    wall_span = max(1.0, end - start)
    # 入关后把死亡时刻挪到闭关中途（墙钟中点，兼容 TIME_SCALE 加速）
    c.lifespan.death_timestamp = start + wall_span * 0.5

    mock_now = end + 2.0
    res = WorldClock.settle_meditation(c, force_interrupt=False, now=mock_now)
    assert res["success"] is True
    assert res["is_fatal"] is True
    assert res["died_in_cave"] is True
    assert c.status == CharacterStatus.DEAD
    # 截断到死亡时刻：设计时长应小于完整 2 小时
    assert res["actual_real_hours"] < 1.5
    print("✓ 洞府中途坐化：截断结算并标记 DEAD")


def test_offline_return_after_planned_end_normal():
    c = _make_char("t_off", "离线闭关客", rem_years=80.0)
    start = time.time()
    WorldClock.start_meditation(c, hours_planned=2.0)
    # 离线 48h 后回来，仍只按计划 2h 结算
    mock_now = start + 48 * 3600.0
    res = WorldClock.settle_meditation(c, force_interrupt=False, now=mock_now)
    assert res["success"] is True
    assert res["is_fatal"] is False
    assert abs(res["actual_real_hours"] - 2.0) < 0.01
    assert abs(res["effective_hours"] - 2.0) < 0.01
    print("✓ 离线超时返回：只按计划时长结算")


def test_ambient_events_returns_list():
    events = WorldClock.generate_ambient_events(1.0)
    assert isinstance(events, list)
    assert len(events) >= 1
    print("✓ generate_ambient_events 返回列表")


def main():
    test_max_planned_hours_rejected()
    test_idle_sit_caps_exp_but_burns_lifespan()
    test_lifespan_warning_during_meditation()
    test_cannot_start_if_would_die_in_cave()
    test_death_mid_cave_settles_as_fatal()
    test_offline_return_after_planned_end_normal()
    test_ambient_events_returns_list()
    print("\n✅ 闭关托管 / 大限预警 / 洞府坐化 测试全部通过")


if __name__ == "__main__":
    main()
