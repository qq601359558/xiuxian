"""
局域网 /交谈 <道号> <内容> 全链路
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_world_talk_with_words():
    from server.world import World
    from storage.db import CharacterRepository as CR, init_db
    from core.clock import WorldClock

    init_db()
    w = World(auto_tick=False)
    r = w.join("链路对谈客")
    tok = r["token"]
    c = w.get_char(tok)
    c.location = "青云坊市客栈"
    c.born_at = time.time() - 80 * 3600
    CR.save(c)

    n = WorldClock.create_new_character("npc_link_talk", "链路掌柜")
    n.location = "青云坊市客栈"
    CR.save(n)

    res0 = w.handle(tok, "/交谈 链路掌柜")
    assert res0.get("ok") is True, res0

    res1 = w.handle(tok, "/交谈 链路掌柜 打听血刀老祖下落")
    assert res1.get("ok") is True, res1
    t1 = res1.get("text") or ""

    res2 = w.handle(tok, "/交谈 链路掌柜 可有灵石买卖")
    assert res2.get("ok") is True, res2
    t2 = res2.get("text") or ""

    assert t1 != t2, f"不同内容应回不同话:\n{t1}\n{t2}"
    # 至少一条应体现「话被听进去了」
    assert any(k in t1 for k in ("打听", "消息", "买", "下落", "略知", "想想", "知悉", "出多少")), t1
    print("✓ /交谈 道号 内容 全链路区分内容")


if __name__ == "__main__":
    test_world_talk_with_words()
    print("\n✅ 交谈全链路通过")
