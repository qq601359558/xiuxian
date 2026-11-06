"""
B1：世界频道 · GM · 事件链 · 纪元传说
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, WorldStateRepository, CharacterRepository
from core.clock import WorldClock
from core.world_channel import WorldChannel, check_gm_token, post_gm, post_system
from core.event_chains import EventChainEngine, TEMPLATES
from core.legends import add_legend, list_legends, format_legends, write_apocalypse_legends
from config import WORLD_MSG_PER_MIN


def _reset_channel_limit():
    import core.world_channel as wc

    wc._recent_keys.clear()
    wc._min_window_start = 0.0
    wc._min_count = 0


def _char(name, stones=500, loc="青云坊市客栈"):
    c = WorldClock.create_new_character(f"b1_{name}", name)
    c.spirit_stones = stones
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def test_channel_post_recent():
    init_db()
    _reset_channel_limit()
    msg = WorldChannel.post("test", "测试大事件播报", level="major", actor="甲")
    assert msg is not None
    rows = WorldChannel.recent(limit=5)
    assert any("测试大事件" in m.text for m in rows)
    board = WorldChannel.format_board(5)
    assert "世界频道" in board
    print("✓ 频道写入与读取")


def test_channel_dedupe_and_rate_limit():
    init_db()
    _reset_channel_limit()
    a = WorldChannel.post("kill", "同一凶手连杀", level="major", actor="凶手A")
    b = WorldChannel.post("kill", "同一凶手连杀", level="major", actor="凶手A")
    assert a is not None
    assert b is None  # 60s 去重
    # 不同 actor 可继续，直到限流
    n = 0
    for i in range(WORLD_MSG_PER_MIN + 3):
        m = WorldChannel.post("kill", f"消息{i}", level="major", actor=f"人{i}")
        if m:
            n += 1
    assert n <= WORLD_MSG_PER_MIN
    print(f"✓ 去重与限流 n={n}")


def test_gm_token():
    init_db()
    _reset_channel_limit()
    import config

    old = config.GM_TOKEN
    # 直接改模块全局供 check 使用
    config.GM_TOKEN = "secret123"
    import core.world_channel as wc

    # check_gm_token 读 config.GM_TOKEN via import at load - need reimport
    import importlib

    importlib.reload(wc)
    assert wc.check_gm_token("secret123") is True
    assert wc.check_gm_token("wrong") is False
    assert wc.check_gm_token("") is False
    msg = wc.post_gm("今夜子时秘境轮换")
    assert msg is not None and msg.level == "gm"
    ann = wc.WorldChannel.format_announcements(5)
    assert "公告" in ann
    config.GM_TOKEN = old
    print("✓ GM Token 校验与公告")


def test_event_chain_two_steps():
    init_db()
    WorldStateRepository.delete("event_chains")
    c = _char("奇遇客", loc="落霞山灵泉(野外)")
    ch = EventChainEngine.maybe_start(c, trigger="travel", force=True)
    assert ch is not None
    assert ch.max_steps >= 2
    assert len(ch.steps[0]["choices"]) >= 2
    res1 = EventChainEngine.choose(c, "1")
    assert res1["success"] is True
    assert res1.get("done") is False
    res2 = EventChainEngine.choose(c, "1")
    assert res2["success"] is True
    assert res2.get("done") is True
    print("✓ 奇遇链两步走通")


def test_event_chain_abandon():
    init_db()
    WorldStateRepository.delete("event_chains")
    c = _char("弃链客")
    EventChainEngine.maybe_start(c, trigger="travel", force=True)
    r = EventChainEngine.abandon(c)
    assert r["success"] is True
    assert EventChainEngine.active_for(c.id) is None
    print("✓ 弃链")


def test_legends_and_apocalypse():
    init_db()
    WorldStateRepository.delete("legends")
    add_legend("测试史笔", "某人于某纪元名动天下。", season=1, weight=2)
    rows = list_legends(season=1)
    assert rows and rows[0].text.startswith("某人")
    text = format_legends(season=1)
    assert "传说" in text
    # 大劫写入
    _reset_channel_limit()
    written = write_apocalypse_legends(9, now=time.time())
    assert written
    assert any(x.season == 9 for x in list_legends(season=9, limit=10))
    print("✓ 传说库与大劫快照")


def test_templates_clamped():
    for tpl in TEMPLATES:
        assert len(tpl["steps"]) >= 2
        for st in tpl["steps"]:
            assert len(st["choices"]) >= 2
    print("✓ 模板结构")


if __name__ == "__main__":
    test_channel_post_recent()
    test_channel_dedupe_and_rate_limit()
    test_gm_token()
    test_event_chain_two_steps()
    test_event_chain_abandon()
    test_legends_and_apocalypse()
    test_templates_clamped()
    print("\n✅ B1 世界频道/奇遇/传说 测试通过")
