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
    r = w.join("链路对谈客2")
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
    WorldClock.start_meditation(char, 1.0)
    CharacterRepository.save(char)
    r5 = w.handle(tok, f"/交谈 {name} 你好")
    assert r5.get("ok") is False
    assert "闭关" in r5.get("error", "")
    w.handle(tok, "/出关")

    r6 = w.handle(tok, f"/交谈 {name} 打听消息")
    assert r6.get("ok") is True
    print("✓ 链路：/交谈 道号 内容 可用；空话/有话/错误道号/闭关均已覆盖")


if __name__ == "__main__":
    test_talk_command_end_to_end()
    print("\n✅ 交谈链路测试通过")
