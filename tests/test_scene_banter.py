"""同场插话 + 会话 AI 摘要"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from core import npc_chat
from core import scene_banter
from core.npc_mind import NpcDialogueEngine


def _pair(prefix="sc"):
    p = WorldClock.create_new_character(f"player_{prefix}", "交谈客")
    p.location = "青云坊市客栈"
    CharacterRepository.save(p)
    n = WorldClock.create_new_character(f"npc_{prefix}_main", "主谈掌柜")
    n.location = "青云坊市客栈"
    n.sect = "四海散修商会"
    n.sect_rank = "掌柜"
    CharacterRepository.save(n)
    b1 = WorldClock.create_new_character(f"npc_{prefix}_b1", "跑堂伙计")
    b1.location = "青云坊市客栈"
    b1.user_id = "npc_banter_1"
    CharacterRepository.save(b1)
    b2 = WorldClock.create_new_character(f"npc_{prefix}_b2", "过路散修")
    b2.location = "青云坊市客栈"
    b2.user_id = "npc_banter_2"
    CharacterRepository.save(b2)
    return p, n, b1, b2


def test_bystanders_and_force_banter():
    init_db()
    p, n, b1, b2 = _pair("bt")
    bystanders = scene_banter.list_bystanders("青云坊市客栈", exclude_ids=[p.id, n.id], limit=10)
    assert bystanders, "坊市应有旁听 NPC"
    # 不依赖具体花名册姓名
    ids = {c.id for c in bystanders}
    assert p.id not in ids and n.id not in ids
    lines = scene_banter.maybe_banter(p, n, transcript_tail="客人：这丹怎么卖？\n掌柜：四十。", force=True)
    assert lines, "force 应至少一条插话"
    assert all(x.get("line") for x in lines)
    assert len(lines) <= scene_banter._MAX_BANTER
    txt = scene_banter.format_banter(lines)
    assert "同场" in txt
    print("✓ 同场插话", txt.replace("\n", " ")[:80])


def test_talk_returns_bystanders():
    init_db()
    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    p, n, b1, b2 = _pair("tl")
    res = NpcDialogueEngine.talk(n, p, "最近坊市有什么动静？")
    assert res.get("ok"), res
    # 可能无插话（概率），但键应存在
    assert "bystanders" in res
    assert "text" in res
    print("✓ talk 返回 bystanders 字段", len(res.get("bystanders") or []))


def test_ai_summary_upgrade_and_memory():
    init_db()
    p, n, b1, b2 = _pair("sm")
    opened = npc_chat.open_session(p, n)
    assert opened["success"], opened
    said = npc_chat.player_say(p, "我想打听落霞古洞的消息。")
    assert said.get("success"), said
    npc_chat.apply_npc_reply(p.id, "古洞灵机未稳，这几日最好别去。", will_continue=True, attitude_delta=3)
    npc_chat.player_say(p, "多谢指点。")
    rec = npc_chat.get_session(p.id)
    assert rec, "会话应仍在"
    ai_or_rule = npc_chat.summarize_session_ai(rec, p, n)
    assert ai_or_rule
    closed = npc_chat.apply_npc_reply(
        p.id, "去吧，小心些。", will_continue=False, attitude_delta=0, hangup_reason="话尽于此。"
    )
    assert closed.get("success"), closed
    mem = npc_chat.chat_memory_lines(p.id, n.id)
    assert "上次交谈记忆" in mem
    print("✓ 会话摘要（ai→规则回退）", ai_or_rule[:40])


def test_server_say_banter_hooks():
    init_db()
    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    p, n, b1, b2 = _pair("sv")
    w = World(auto_tick=False)
    # 用已有角色 join 不方便；直接 handle 需 token — 用 World 内 join 同道号可能复用
    sess = w.join("交谈客", user_id=p.user_id)
    tok = sess["token"]
    ch = w.get_char(tok)
    ch.location = "青云坊市客栈"
    CharacterRepository.save(ch)
    # 确保主谈同场
    n.location = "青云坊市客栈"
    CharacterRepository.save(n)
    r = w.handle(tok, f"/交谈 {n.name}")
    assert r.get("ok") is True, r
    r2 = w.handle(tok, "/说 坊市近来如何？")
    assert r2.get("ok") is True, r2
    assert r2.get("text")
    r3 = w.handle(tok, "/会话")
    assert r3.get("ok") is True
    r4 = w.handle(tok, "/挂断")
    assert r4.get("ok") is True
    assert "会话已结束" in r4.get("text", "")
    print("✓ 服务器 /说 插话与 /挂断 摘要")


if __name__ == "__main__":
    test_bystanders_and_force_banter()
    test_talk_returns_bystanders()
    test_ai_summary_upgrade_and_memory()
    test_server_say_banter_hooks()
    print("\nbanter+summary tests passed")
