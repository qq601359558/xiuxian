"""
链路级：/交谈 道号 内容 必须到达台词引擎
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from server.world import World
from storage.db import CharacterRepository
from core.clock import WorldClock


def test_talk_command_end_to_end():
    w = World(auto_tick=False)
    r = w.join("链路对谈客2", user_id="talk_command_e2e_player")
    tok = r["token"]
    char = w.get_char(tok)

    from core.here import list_here

    rows = [x for x in list_here(char) if x.get("is_npc")]
    assert rows, "坊市应有 NPC"
    name = rows[0]["name"]

    # 空话
    r1 = w.handle(tok, f"/交谈 {name}")
    assert r1.get("ok") is True, r1
    assert r1.get("text")

    # 有内容：不同话应不同（或至少 ok 且非空）
    r2 = w.handle(tok, f"/交谈 {name} 打听血刀老祖下落")
    r3 = w.handle(tok, f"/交谈 {name} 你找死")
    assert r2.get("ok") is True and r3.get("ok") is True
    assert r2["text"] != r3["text"], "不同内容不应完全同一句"

    # 查无此人 → 给同场提示
    r4 = w.handle(tok, "/交谈 没这个人 你好")
    assert r4.get("ok") is False
    assert "同场" in r4.get("error", "") or "查无此人" in r4.get("error", "")

    # 闭关中交谈被拒
    char.spirit_stones = max(char.spirit_stones, 50)
    med_res = WorldClock.start_meditation(char, 1.0)
    assert med_res.get("success"), f"闭关启动失败: {med_res}"
    CharacterRepository.save(char)
    r5 = w.handle(tok, f"/交谈 {name} 你好")
    assert r5.get("ok") is False
    assert "闭关" in r5.get("error", "")
    w.handle(tok, "/出关")

    r6 = w.handle(tok, f"/交谈 {name} 打听消息")
    assert r6.get("ok") is True
    print("✓ 链路：/交谈 道号 内容 可用；空话/有话/错误道号/闭关均已覆盖")


def test_talk_open_includes_avatar_matching_here():
    """SF-1（spec §10.3-5）：交谈开启/会话结构下发 avatar，与同场逐字一致。"""
    import uuid

    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from core.here import list_here
    from core import npc_chat
    from storage.db import WorldStateRepository

    tag = uuid.uuid4().hex[:8]
    loc = f"头像地{tag}"  # 唯一地点隔离同场列表（避免客栈积压角色超 list_here 上限）
    w = World(auto_tick=False)
    r = w.join(f"头像客{tag}", user_id=f"talk_avatar_player_{tag}")
    tok = r["token"]
    char = w.get_char(tok)
    char.location = loc
    CharacterRepository.save(char)

    npc = WorldClock.create_new_character(f"npc_talk_avatar_{tag}", f"头像掌柜{tag}")
    npc.location = loc
    npc.sect = "四海散修商会"
    npc.sect_rank = "掌柜"
    CharacterRepository.save(npc)

    peer = WorldClock.create_new_character(f"ch_talk_avatar_{tag}", f"同场道友{tag}")
    peer.location = loc
    CharacterRepository.save(peer)
    try:
        rows = {x["name"]: x for x in list_here(char)}
        assert npc.name in rows and peer.name in rows
        npc_avatar = rows[npc.name]["avatar"]
        peer_avatar = rows[peer.name]["avatar"]
        assert npc_avatar.startswith("/assets/")  # 完整路径（NPC 原型图）

        # /交谈 无话开启
        r1 = w.handle(tok, f"/交谈 {npc.name}")
        assert r1.get("ok") is True, r1
        assert r1.get("avatar") == npc_avatar, r1
        # /说 会话内发言（最终 payload）
        r2 = w.handle(tok, "/说 这聚气丹什么价？坊市行情如何")
        assert r2.get("ok") is True, r2
        assert r2.get("avatar") == npc_avatar, r2
        w.handle(tok, "/挂断")
        # /交谈 带话开启
        r3 = w.handle(tok, f"/交谈 {npc.name} 打听血刀老祖下落")
        assert r3.get("ok") is True, r3
        assert r3.get("avatar") == npc_avatar, r3
        w.handle(tok, "/挂断")
        # 真人目标开启：avatar 走玩家定相口径，仍与同场逐字一致
        r4 = w.handle(tok, f"/交谈 {peer.name}")
        assert r4.get("ok") is True, r4
        assert r4.get("is_player") is True
        assert r4.get("avatar") == peer_avatar, r4
        # 真人目标带话开启（player_direct）
        r5 = w.handle(tok, f"/交谈 {peer.name} 道友安好")
        assert r5.get("ok") is True, r5
        assert r5.get("avatar") == peer_avatar, r5
        print("✓ 交谈开启/会话 avatar 与同场逐字一致（NPC + 真人）")
    finally:
        WorldStateRepository.delete(npc_chat._KEY)


if __name__ == "__main__":
    test_talk_command_end_to_end()
    test_talk_open_includes_avatar_matching_here()
    print("\n✅ 交谈链路测试通过")
