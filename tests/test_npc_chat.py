"""
NPC 会话聊天
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core import npc_chat
from core.models import CharacterStatus


def _p(name, loc="青云坊市客栈"):
    c = WorldClock.create_new_character(f"ch_{name}", name)
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def test_open_and_say_then_hangup_no_ai():
    init_db()
    WorldStateRepository.delete(npc_chat._KEY)
    p = _p("话客")
    n = _p("柳三娘测")
    o = npc_chat.open_session(p, n)
    assert o["success"] is True
    s = npc_chat.player_say(CharacterRepository.get_by_id(p.id), "道友安好")
    assert s["success"] is True and s.get("need_ai")
    # 无 AI 本地回复
    loc = npc_chat.local_hangup_or_reply(CharacterRepository.get_by_id(n.id), p, s["session"])
    out = npc_chat.apply_npc_reply(p.id, loc["line"], loc["will_continue"], 0, loc.get("hangup_reason") or "")
    assert out["success"]
    # 挂断
    npc_chat.close_session(p.id, "测试挂断", by="player")
    s2 = npc_chat.player_say(CharacterRepository.get_by_id(p.id), "还在吗")
    assert s2["success"] is False
    assert s2.get("ended") is True
    assert "会话已终" in s2["message"] or "不会" in s2["message"] or "重新" in s2["message"]
    print("✓ 开启→发言→挂断→再发言拒绝")


def test_remote_cannot_open():
    init_db()
    WorldStateRepository.delete(npc_chat._KEY)
    p = _p("近", loc="青云坊市客栈")
    n = _p("远", loc="万星古岛")
    o = npc_chat.open_session(p, n)
    assert o["success"] is False
    print("✓ 异地不可开会话")


def test_timeout_closes():
    init_db()
    WorldStateRepository.delete(npc_chat._KEY)
    p = _p("久候")
    n = _p("冷淡")
    npc_chat.open_session(p, n)
    d = WorldStateRepository.get(npc_chat._KEY) or {}
    d[p.id]["updated_at"] = time.time() - 2000
    WorldStateRepository.set(npc_chat._KEY, d)
    assert npc_chat.get_session(p.id) is None
    print("✓ 超时散会")


def test_force_hangup_low_willingness():
    init_db()
    WorldStateRepository.delete(npc_chat._KEY)
    p = _p("絮叨")
    n = _p("不耐")
    npc_chat.open_session(p, n)
    # 压低意愿
    d = WorldStateRepository.get(npc_chat._KEY) or {}
    d[p.id]["willingness"] = 3
    d[p.id]["turns"] = 10
    WorldStateRepository.set(npc_chat._KEY, d)
    rec = npc_chat.get_session(p.id)
    loc = npc_chat.local_hangup_or_reply(n, p, rec)
    assert loc["will_continue"] is False
    out = npc_chat.apply_npc_reply(p.id, loc["line"], False, 0, loc.get("hangup_reason") or "")
    assert out.get("ended") is True
    print("✓ 低意愿强制挂断")


if __name__ == "__main__":
    test_open_and_say_then_hangup_no_ai()
    test_remote_cannot_open()
    test_timeout_closes()
    test_force_hangup_low_willingness()
    print("\n✅ npc_chat 测试通过")
