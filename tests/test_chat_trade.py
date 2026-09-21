"""聊天窗内交易：买/卖/货单"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("LLM_API_KEY", "")

import config

config.ALLOW_LOCAL_AI = True
config.LLM_API_KEY = ""
config.USE_CCSWITCH = False

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from core.chat_actions import execute_chat_action, do_trade, classify_local
from config import ITEM_CATALOG


def _shopkeeper(name="柳三娘", uid="npc_shop_lz"):
    c = WorldClock.create_new_character(uid, name)
    c.sect = "四海散修商会"
    c.sect_rank = "掌柜"
    c.location = "青云坊市客栈"
    CharacterRepository.save(c)
    return c


def _player(name="买客", uid="player_shop_a", stones=2000):
    c = WorldClock.create_new_character(uid, name)
    c.location = "青云坊市客栈"
    c.spirit_stones = stones
    CharacterRepository.save(c)
    return c


def test_classify_trade_phrases():
    for s in ("我想买下聚气丹", "卖你妖兽内丹", "有什么货", "出价100灵石"):
        cls = classify_local(s)
        assert cls["intent"] == "trade", (s, cls)
    print("✓ 交易语句可分类")


def test_chat_buy_from_shop():
    init_db()
    p = _player()
    npc = _shopkeeper()
    stones0 = p.spirit_stones
    inv0 = len(p.inventory) + len(p.arrays)
    res = execute_chat_action(p, npc, "买下聚气丹", use_ai_classify=False)
    assert res.get("ok") is True, res
    assert "成交" in res.get("text", "") or "灵石" in res.get("text", "")
    p2 = CharacterRepository.get_by_id(p.id)
    assert p2.spirit_stones < stones0
    assert (len(p2.inventory) + len(p2.arrays)) > inv0
    print("✓ 聊天买货", res.get("text", "")[:50])


def test_chat_sell_to_shop():
    init_db()
    p = _player("卖家", uid="player_shop_b")
    p.inventory.append("妖兽内丹")
    p.inventory.append("妖兽内丹")
    CharacterRepository.save(p)
    stones0 = p.spirit_stones
    res = execute_chat_action(p, _shopkeeper(uid="npc_shop_lz2"), "卖你妖兽内丹 2", use_ai_classify=False)
    assert res.get("ok") is True, res
    p2 = CharacterRepository.get_by_id(p.id)
    assert p2.spirit_stones > stones0, (p2.spirit_stones, stones0)
    assert "妖兽内丹" not in p2.inventory
    print("✓ 聊天卖货", res.get("text", "")[:50])


def test_chat_goods_list():
    init_db()
    p = _player("问货", uid="player_shop_c")
    npc = _shopkeeper(uid="npc_shop_lz3")
    res = execute_chat_action(p, npc, "你有什么货", use_ai_classify=False)
    assert res.get("ok") is True
    assert "货架" in res.get("text", "") or "坊市" in res.get("text", "")
    print("✓ 聊天问货单", res.get("text", "")[:40])


def test_server_chat_trade():
    init_db()
    from server.world import World

    w = World(auto_tick=False)
    sess = w.join("柜台客", user_id="chat_trade_user")
    tok = sess["token"]
    ch = w.get_char(tok)
    ch.location = "青云坊市客栈"
    ch.spirit_stones = 3000
    CharacterRepository.save(ch)
    npc = _shopkeeper("柳三娘", uid="npc_shop_srv")
    npc.location = "青云坊市客栈"
    CharacterRepository.save(npc)
    r1 = w.handle(tok, "/交谈 柳三娘")
    assert r1.get("ok") is True, r1
    r2 = w.handle(tok, "有什么货")
    assert r2.get("ok") is True, r2
    r3 = w.handle(tok, "买下聚气丹")
    # 可能被 chat_actions 成交（need_dialogue=False）或 NPC 台词
    assert r3.get("ok") is True, r3
    assert r3.get("text")
    print("✓ 服务器聊天交易", str(r3.get("text"))[:60])


if __name__ == "__main__":
    test_classify_trade_phrases()
    test_chat_buy_from_shop()
    test_chat_sell_to_shop()
    test_chat_goods_list()
    test_server_chat_trade()
    print("\nchat trade tests passed")
