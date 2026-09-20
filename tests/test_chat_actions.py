"""
会话内动作：分类 / 赠礼 / 交易 / 偷窃 / 擒拿 / 释放
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core import npc_chat
from core import chat_actions as CA
from core.models import CharacterStatus


def _p(name, loc="青云坊市客栈", tier=1):
    c = WorldClock.create_new_character(f"ch_{name}", name)
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    c.realm.tier = tier
    CharacterRepository.save(c)
    return c


def test_classify_local_intents():
    assert CA.classify_local("你好啊")["intent"] == "dialogue"
    assert CA.classify_local("我递上聚气丹")["intent"] == "gift"
    assert CA.classify_local("一掌拍过去")["intent"] == "attack"
    assert CA.classify_local("顺走他的灵石")["intent"] == "steal"
    assert CA.classify_local("一把擒住他")["intent"] == "kidnap"
    assert CA.classify_local("用100灵石买你的丹")["intent"] == "trade"
    assert CA.classify_local("递上《聚气丹》")["target_item"] == "聚气丹"
    assert CA._extract_stones("出价 80 灵石") == 80
    print("✓ 本地意图分类")


def test_gift_transfers_item_and_attitude():
    init_db()
    WorldStateRepository.delete(npc_chat._KEY)
    p = _p("赠客")
    n = _p("受礼")
    p.inventory.append("聚气丹")
    CharacterRepository.save(p)
    out = CA.do_gift(p, n, "聚气丹", 0)
    assert out["ok"] is True
    assert "聚气丹" not in p.inventory
    assert out.get("ended") is False
    CharacterRepository.save(p)
    print("✓ 赠礼扣行囊")


def test_gift_missing_item_rejected():
    init_db()
    p = _p("空手")
    n = _p("挑剔")
    out = CA.do_gift(p, n, "九转还魂丹", 0)
    assert out["ok"] is False
    print("✓ 无货赠礼被拒")


def test_trade_catalog_purchase():
    init_db()
    p = _p("买主")
    n = _p("掌柜测")
    p.spirit_stones = 10000
    CharacterRepository.save(p)
    # 放宽态度为友好，便于成交
    from core.npc_mind import shift_attitude

    shift_attitude(n, p.id, 40, reason="test")
    name = next(iter(__import__("config").ITEM_CATALOG))
    out = CA.do_trade(p, n, name, 0)
    assert out["ok"] is True, out
    assert name in p.inventory or "成交" in out.get("text", "")
    print("✓ 目录购物成交")


def test_steal_safe_zone_blocked():
    init_db()
    p = _p("窃客", loc="青云坊市客栈")
    n = _p("肥羊", loc="青云坊市客栈")
    n.spirit_stones = 100
    CharacterRepository.save(n)
    out = CA.do_steal(p, n, {})
    assert out["ok"] is False
    assert "安全" in out.get("error", "")
    print("✓ 安全区不可偷")


def test_kidnap_and_release():
    init_db()
    wild = "落霞山灵泉"
    p = _p("擒者", loc=wild, tier=3)
    n = _p("肉票", loc=wild, tier=1)
    import random as _rnd

    orig = _rnd.random
    _rnd.random = lambda: 0.0  # 必成功
    try:
        out = CA.do_kidnap(p, n, {"willingness": 50})
    finally:
        _rnd.random = orig
    assert out.get("ok") is True, out
    assert out.get("action") == "kidnap"
    n2 = CharacterRepository.get_by_id(n.id)
    assert n2.status == CharacterStatus.CAPTURED
    assert n2.captor_id == p.id
    r = CA.release_captive(p, n.name)
    assert r.get("ok") is True
    n3 = CharacterRepository.get_by_id(n.id)
    assert n3.status == CharacterStatus.IDLE
    assert n3.captor_id is None
    print("✓ 擒拿→释放闭环")


def test_kidnap_blocked_in_safe_zone():
    init_db()
    p = _p("坊市恶霸", loc="青云坊市客栈", tier=5)
    n = _p("坊市散修", loc="青云坊市客栈", tier=1)
    out = CA.do_kidnap(p, n, {})
    assert out["ok"] is False
    assert "安全" in out.get("error", "")
    print("✓ 安全区不可擒人")


def test_captured_cannot_be_talked():
    init_db()
    WorldStateRepository.delete(npc_chat._KEY)
    p = _p("问话人")
    n = _p("阶下囚")
    n.status = CharacterStatus.CAPTURED
    n.captor_id = "someone"
    CharacterRepository.save(n)
    o = npc_chat.open_session(p, CharacterRepository.get_by_id(n.id))
    assert o["success"] is False
    print("✓ 被擒者不可新开会话")


def test_trade_underbid_rejected():
    init_db()
    p = _p("压价客")
    n = _p("硬气掌柜")
    p.spirit_stones = 10000
    CharacterRepository.save(p)
    from core.npc_mind import shift_attitude

    shift_attitude(n, p.id, 40, reason="test")
    name = next(iter(__import__("config").ITEM_CATALOG))
    out = CA.do_trade(p, n, name, 1)  # 只出 1 灵石
    assert out["ok"] is False
    assert "作价" in out.get("error", "") or "不卖" in out.get("error", "")
    assert name not in p.inventory
    print("✓ 压价交易被拒")


def test_kidnap_willingness_path():
    init_db()
    wild = "落霞山灵泉"
    # 同境界，但会话意愿极低（聊崩）→ 可动手
    p = _p("激怒者", loc=wild, tier=2)
    n = _p("被说动", loc=wild, tier=2)
    import random as _rnd

    orig = _rnd.random
    _rnd.random = lambda: 0.0
    try:
        out = CA.do_kidnap(p, n, {"willingness": 10})
    finally:
        _rnd.random = orig
    assert out.get("ok") is True, out
    assert out.get("action") == "kidnap"
    n2 = CharacterRepository.get_by_id(n.id)
    assert n2.status == CharacterStatus.CAPTURED
    print("✓ 低意愿可擒（聊崩路径）")


if __name__ == "__main__":
    test_classify_local_intents()
    test_gift_transfers_item_and_attitude()
    test_gift_missing_item_rejected()
    test_trade_catalog_purchase()
    test_trade_underbid_rejected()
    test_steal_safe_zone_blocked()
    test_kidnap_and_release()
    test_kidnap_willingness_path()
    test_kidnap_blocked_in_safe_zone()
    test_captured_cannot_be_talked()
    print("\n✅ chat_actions 测试通过")
