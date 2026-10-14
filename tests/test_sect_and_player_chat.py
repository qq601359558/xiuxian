import time
import pytest
from core.clock import WorldClock
from core.models import Character, CharacterStatus
from core.npc_mind import _is_npc
from core.npc_chat import (
    open_session,
    player_say,
    deliver_player_message,
    pop_player_inbox,
    get_p2p_history,
    _KEY,
    _INBOX_KEY,
    _P2P_KEY,
)
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import World


@pytest.fixture(autouse=True)
def clean_state():
    init_db()
    WorldStateRepository.delete(_KEY)
    WorldStateRepository.delete(_INBOX_KEY)
    WorldStateRepository.delete(_P2P_KEY)
    yield
    WorldStateRepository.delete(_KEY)
    WorldStateRepository.delete(_INBOX_KEY)
    WorldStateRepository.delete(_P2P_KEY)


def test_status_dict_sect_fields_and_catalog():
    ws = World()
    c = WorldClock.create_new_character("test_player_1", "顾青玄")
    c.location = "宗门玄元洞府"
    c.sect = "青云宗"
    c.sect_rank = "外门弟子"
    c.sect_contribution = 150
    CharacterRepository.save(c)

    st = ws._status_dict(c)
    assert st["sect"] == "青云宗"
    assert st["rank"] == "外门弟子"
    assert st["sect_contribution"] == 150
    assert "salary_claimable" in st
    assert "salary_cd_sec" in st
    assert "sects_catalog" in st
    assert len(st["sects_catalog"]) >= 4
    names = [s["name"] for s in st["sects_catalog"]]
    assert "青云宗" in names
    assert "万剑仙门" in names


def test_player_to_player_chat_bypasses_ai():
    ws = World()
    # 模拟两位同场的真人玩家（user_id 非 npc_ 开头）
    p1 = WorldClock.create_new_character("player_lan_001", "云中子")
    p2 = WorldClock.create_new_character("player_lan_002", "太素散人")
    p1.location = "青云坊市客栈"
    p2.location = "青云坊市客栈"
    CharacterRepository.save(p1)
    CharacterRepository.save(p2)

    assert not _is_npc(p1)
    assert not _is_npc(p2)

    # 1. p1 与 p2 建立会话并传音
    token1 = ws.join(p1.name, user_id=p1.user_id)["token"]
    token2 = ws.join(p2.name, user_id=p2.user_id)["token"]

    # 点名开聊
    res_talk = ws.handle(token1, f"/交谈 {p2.name} 道友安好，可愿同赴黑风绝渊？")
    assert res_talk["ok"] is True
    assert res_talk.get("is_player") is True
    assert res_talk.get("source") == "player_direct"
    assert "道友安好" in res_talk["text"]

    # 检查双向历史已持久化
    hist = get_p2p_history(p1.id, p2.id)
    assert len(hist) == 1
    assert hist[0]["who"] == "云中子"
    assert "黑风绝渊" in hist[0]["text"]

    # 检查 p2 的信箱收到了未读传音
    st2 = ws._status_dict(p2)
    assert "unread_messages" in st2
    assert len(st2["unread_messages"]) == 1
    assert st2["unread_messages"][0]["from_name"] == "云中子"

    # p2 会话中直接 /说 回复 p1
    ws.handle(token2, f"/交谈 {p1.name}")
    res_reply = ws.handle(token2, "/说 善！吾备上两件地品法宝，立时启程。")
    assert res_reply["ok"] is True
    assert res_reply.get("is_player") is True
    assert res_reply.get("source") == "player_direct"

    # p1 再次拉取状态即可看到 p2 的回信
    st1 = ws._status_dict(p1)
    assert len(st1["unread_messages"]) == 1
    assert st1["unread_messages"][0]["from_name"] == "太素散人"
    assert "地品法宝" in st1["unread_messages"][0]["text"]


def test_npc_chat_still_uses_npc_flow():
    ws = World()
    p = WorldClock.create_new_character("player_real_001", "楚凌虚")
    npc = WorldClock.create_new_character("npc_qy_06", "苏婉清")
    p.location = "青云宗外门山门"
    npc.location = "青云宗外门山门"
    CharacterRepository.save(p)
    CharacterRepository.save(npc)

    assert not _is_npc(p)
    assert _is_npc(npc)

    token = ws.join(p.name, user_id=p.user_id)["token"]

    # 打开与 NPC 的会话
    res = ws.handle(token, f"/交谈 {npc.name}")
    assert res["ok"] is True
    assert res.get("is_player") is not True

    # 发言（若无 AI 网关可用，走本地 local_hangup_or_reply，但 session 正常流转）
    say_res = ws.handle(token, "/说 苏师姐，请问洗剑池在何方？")
    assert say_res["ok"] is True
    assert say_res.get("npc") == "苏婉清"
    # NPC 模式下 source 不是 player_direct
    assert say_res.get("source") != "player_direct"


def test_sect_operations_return_status():
    ws = World()
    c = WorldClock.create_new_character("player_sect_test", "韩立")
    c.location = "青云宗外门山门"
    c.karma.dao_heart = 80
    c.karma.sin_value = 0
    c.spirit_stones = 100
    CharacterRepository.save(c)

    token = ws.join(c.name, user_id=c.user_id)["token"]

    # 1. 拜入
    r_join = ws.handle(token, "/拜入 青云宗")
    assert r_join["ok"] is True
    assert r_join.get("status") is not None
    assert r_join["status"]["sect"] == "青云宗"

    # 2. 领取俸禄
    r_sal = ws.handle(token, "/领俸禄")
    assert r_sal["ok"] is True
    assert r_sal.get("status") is not None
    assert r_sal["status"]["stones"] > 100

    # 3. 叛门
    r_leave = ws.handle(token, "/叛门")
    assert r_leave["ok"] is True
    assert r_leave.get("status") is not None
    assert r_leave["status"]["sect"] == ""
