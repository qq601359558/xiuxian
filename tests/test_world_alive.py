"""
世界自己活：传闻池 · 关系网 · 同场合谋
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, WorldStateRepository, CharacterRepository, KarmaLinkRepository
from core.clock import WorldClock
from core import rumors
from core.collusion import (
    ensure_link,
    links_between,
    links_of,
    try_collude_pair,
    format_links,
    _COOLDOWN_KEY,
)
from core.models import CharacterStatus


def _npc(name: str, loc: str = "青云坊市客栈", user_id: str = None):
    uid = user_id or f"npc_{name}"
    c = WorldClock.create_new_character(uid, name)
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def test_rumor_pool_add_list_purge():
    init_db()
    WorldStateRepository.delete(rumors._KEY)
    r = rumors.add_rumor("测试传闻：青云坊市有人斗法", origin="测试", truth=0.9)
    assert r["id"]
    rows = rumors.list_rumors(5)
    assert any("测试传闻" in x["text"] for x in rows)
    board = rumors.format_rumor_board(5)
    assert "坊间传闻" in board
    print("✓ 传闻池读写")


def test_rumor_event_hooks():
    init_db()
    WorldStateRepository.delete(rumors._KEY)
    rumors.note_kill("甲", "乙", "落霞山")
    rumors.note_trade("甲", "丙", "青云坊市客栈")
    rumors.note_auction("丁", "青锋剑", 200)
    rumors.note_apocalypse(3)
    rows = rumors.list_rumors(10)
    texts = " ".join(x["text"] for x in rows)
    assert "斩" in texts and "交割" in texts and "落槌" in texts and "大劫" in texts
    print("✓ 击杀/成交/拍卖/大劫写入传闻")


def test_ensure_link_and_format():
    init_db()
    a = _npc("仇甲")
    b = _npc("仇乙")
    link = ensure_link(a, b, "仇", note="测试血仇")
    assert link.link_type == "仇"
    again = ensure_link(a, b, "仇")
    assert again.strength >= 2
    assert links_between(a.id, b.id)
    assert links_of(a.id)
    text = format_links(a)
    assert "仇" in text and "仇乙" in text
    print("✓ 关系边建立与查询")


def test_collude_pair_emits_event():
    init_db()
    WorldStateRepository.delete(_COOLDOWN_KEY)
    WorldStateRepository.delete(rumors._KEY)
    a = _npc("密甲")
    b = _npc("密乙")
    ensure_link(a, b, "恩", note="曾共探秘境")
    # 冷却已写入，先清
    WorldStateRepository.delete(_COOLDOWN_KEY)
    # 高概率：多试几次
    hit = None
    for _ in range(8):
        WorldStateRepository.delete(_COOLDOWN_KEY)
        hit = try_collude_pair(a, b, use_ai=False)
        if hit:
            break
    assert hit is not None, "应能产生合谋事件"
    assert hit["kind"] in ("密谈", "寻仇未遂", "结伴而行", "分赃不均")
    assert hit["narrative"]
    rows = rumors.list_rumors(10)
    assert any(a.name in x["text"] for x in rows)
    print(f"✓ 同场合谋事件：{hit['kind']} source={hit['source']}")


def test_collude_requires_link():
    init_db()
    WorldStateRepository.delete(_COOLDOWN_KEY)
    a = _npc("孤甲")
    b = _npc("孤乙")
    assert try_collude_pair(a, b, use_ai=False) is None
    print("✓ 无关系边不合谋")


if __name__ == "__main__":
    test_rumor_pool_add_list_purge()
    test_rumor_event_hooks()
    test_ensure_link_and_format()
    test_collude_pair_emits_event()
    test_collude_requires_link()
    print("\n✅ 世界自己活 测试通过")
