"""同场插话（话题相关才开口）+ 会话摘要"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("LLM_API_KEY", "")

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from core import npc_chat
from core import scene_banter
from core.scene_banter import format_banter
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
    CharacterRepository.save(b1)
    b2 = WorldClock.create_new_character(f"npc_{prefix}_b2", "过路散修")
    b2.location = "青云坊市客栈"
    CharacterRepository.save(b2)
    return p, n, b1, b2


def test_topic_extract():
    assert "goods" in scene_banter.extract_topics("这丹什么价，坊市灵石够不够")
    assert "realm" in scene_banter.extract_topics("落霞古洞秘境探险挖宝")
    print("✓ 话题抽取")


def test_banter_on_topic_max_one():
    init_db()
    scene_banter.reset_banter_cooldowns()
    p, n, b1, b2 = _pair("bt")
    lines = scene_banter.maybe_banter(
        p,
        n,
        transcript_tail="客人：这聚气丹怎么卖？\n掌柜：四十灵石。",
        force=True,
    )
    assert lines, "有主题且 force 应插话"
    assert len(lines) == 1
    txt = format_banter(lines)
    assert any(k in txt for k in ("丹", "价", "灵石", "货", "柜", "坊市")), txt
    print("✓ 有主题插话（最多1人）", txt.replace("\n", " ")[:80])


def test_banter_off_topic_silent():
    init_db()
    scene_banter.reset_banter_cooldowns()
    p, n, b1, b2 = _pair("ot")
    lines = scene_banter.maybe_banter(p, n, transcript_tail="嗯。\n哦。", force=False)
    assert lines == [], lines
    scene_banter.maybe_banter(p, n, transcript_tail="打听落霞古洞探险如何？", force=True)
    again = scene_banter.maybe_banter(p, n, transcript_tail="再说说秘境与挖宝。", force=False)
    assert again == [], again
    print("✓ 无关话题不插 / 地点冷却")


def test_talk_returns_bystanders_key():
    init_db()
    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    scene_banter.reset_banter_cooldowns()
    p, n, b1, b2 = _pair("tl")
    res = NpcDialogueEngine.talk(n, p, "聚气丹怎么卖？坊市灵石够吗？")
    assert res.get("ok"), res
    assert "bystanders" in res
    print("✓ talk 返回 bystanders", len(res.get("bystanders") or []))


def test_ai_summary_memory():
    init_db()
    p, n, b1, b2 = _pair("sm")
    opened = npc_chat.open_session(p, n)
    assert opened["success"], opened
    assert npc_chat.player_say(p, "我想打听落霞古洞的消息。").get("success")
    npc_chat.apply_npc_reply(p.id, "古洞灵机未稳，这几日最好别去。", will_continue=True, attitude_delta=3)
    npc_chat.player_say(p, "多谢指点。")
    rec = npc_chat.get_session(p.id)
    assert rec
    s = npc_chat.summarize_session_ai(rec, p, n)
    assert s
    closed = npc_chat.apply_npc_reply(p.id, "去吧，小心些。", will_continue=False)
    assert closed.get("success")
    assert "上次交谈记忆" in npc_chat.chat_memory_lines(p.id, n.id)
    print("✓ 会话摘要", s[:40])


def test_server_say_and_hangup():
    init_db()
    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    scene_banter.reset_banter_cooldowns()
    p, n, b1, b2 = _pair("sv")
    w = World(auto_tick=False)
    sess = w.join("交谈客", user_id=p.user_id)
    tok = sess["token"]
    ch = w.get_char(tok)
    ch.location = "青云坊市客栈"
    CharacterRepository.save(ch)
    n.location = "青云坊市客栈"
    CharacterRepository.save(n)
    r = w.handle(tok, f"/交谈 {n.name}")
    assert r.get("ok") is True, r
    r2 = w.handle(tok, "/说 这聚气丹什么价？坊市行情如何")
    assert r2.get("ok") is True, r2
    r4 = w.handle(tok, "/挂断")
    assert r4.get("ok") is True
    print("✓ 服务器交谈/挂断")


if __name__ == "__main__":
    test_topic_extract()
    test_banter_on_topic_max_one()
    test_banter_off_topic_silent()
    test_talk_returns_bystanders_key()
    test_ai_summary_memory()
    test_server_say_and_hangup()
    print("\nbanter discipline tests passed")
