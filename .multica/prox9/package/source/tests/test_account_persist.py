"""账号续玩：重启后 token 库恢复、同道号不串号。"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from server.world import World
from storage.db import init_db, CharacterRepository, AuthSessionRepository


def test_persist_across_restart():
    init_db()
    uid = f"acct_persist_{int(time.time()*1000)}"
    w1 = World(auto_tick=False)
    r = w1.join("续玩道人", user_id=uid)
    assert r.get("token")
    tok = r["token"]
    # 修炼一点
    w1.handle(tok, "/look")
    char = w1.get_char(tok)
    char.spirit_stones = 999
    CharacterRepository.save(char)
    stones_before = char.spirit_stones

    # 模拟重启：新 World，内存 sessions 为空
    w2 = World(auto_tick=False)
    assert tok not in w2.sessions
    char2 = w2.get_char(tok)
    assert char2 is not None, "token 应能从库恢复会话"
    assert char2.spirit_stones == stones_before
    res = w2.handle(tok, "/look")
    assert res.get("ok") is True
    print("✓ 重启后 token 续玩", char2.name, char2.spirit_stones)


def test_same_name_does_not_resume_other_account():
    w = World(auto_tick=False)
    uname = f"同名{int(time.time())%100000}"
    r = w.join(uname, user_id=f"acct_name_{int(time.time()*1000)}")
    r2 = w.join(uname, user_id=f"acct_other_{int(time.time()*1000)}")
    assert r2["resumed"] is False
    assert r2["is_new_life"] is True
    assert r2["user_id"] != r["user_id"]
    assert r2["character_id"] != r["character_id"]
    assert r2["name"] == r["name"]
    print("✓ 同道号保持独立账号")


def test_logout_clears_token():
    w = World(auto_tick=False)
    r = w.join("下线客", user_id="acct_logout_1")
    tok = r["token"]
    w.logout(tok)
    w2 = World(auto_tick=False)
    assert w2.get_char(tok) is None
    print("✓ 下线后 token 失效")


if __name__ == "__main__":
    test_persist_across_restart()
    test_same_name_does_not_resume_other_account()
    test_logout_clears_token()
    print("\n✅ 账号续玩测试通过")
