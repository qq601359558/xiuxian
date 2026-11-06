"""免斜杠：同场自由发言路由到会话/AI 行为"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from server.world import World
import config


def test_free_text_routes_to_chat():
    init_db()
    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    w = World(auto_tick=False)
    sess = w.join("免令修士", user_id="free_chat_user")
    tok = sess["token"]
    ch = w.get_char(tok)
    ch.location = "青云坊市客栈"
    CharacterRepository.save(ch)
    # 造一个同场 NPC
    npc = WorldClock.create_new_character("npc_free_lz", "柳三娘")
    npc.location = "青云坊市客栈"
    CharacterRepository.save(npc)
    # 无会话：点名开聊
    r = w.handle(tok, "柳三娘，最近可太平？")
    assert r.get("ok") is True or r.get("chat_open") is True, r
    assert "柳三娘" in str(r.get("text", "")) or r.get("npc") == "柳三娘"
    # 有会话：免斜杠继续
    r2 = w.handle(tok, "坊市丹药什么价？")
    assert r2.get("ok") is True or r2.get("chat_open") is True, r2
    text = r2.get("text", "")
    assert text
    r3 = w.handle(tok, "/会话")
    assert r3.get("ok") is True
    print("✓ 免斜杠自由发言", str(text)[:40])


def test_free_text_no_one():
    init_db()
    config.ALLOW_LOCAL_AI = True
    w = World(auto_tick=False)
    sess = w.join("独行客", user_id="free_chat_alone")
    tok = sess["token"]
    ch = w.get_char(tok)
    ch.location = "万星古岛"
    CharacterRepository.save(ch)
    # 清场困难，至少不崩
    r = w.handle(tok, "有人吗？")
    assert "error" in r or r.get("ok") is True
    print("✓ 无人时提示/不崩")


if __name__ == "__main__":
    test_free_text_routes_to_chat()
    test_free_text_no_one()
    print("free chat tests passed")
