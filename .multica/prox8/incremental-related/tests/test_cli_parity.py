"""
CLI 对齐：局域网服指令（探查/自创功法/悬赏/寄售等）
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from server.world import World
from storage.db import CharacterRepository, init_db
import config
import ai.gateway as gw

# 测试不打真实 AI（.env 会覆盖 os.environ）；打开本地降级以便自创功法等可跑
config.LLM_API_KEY = ""
config.USE_CCSWITCH = False
config.ALLOW_LOCAL_AI = True
gw.LLM_API_KEY = ""
gw.USE_CCSWITCH = False


def test_cli_parity_commands():
    init_db()
    w = World(auto_tick=False)
    r = w.join("指令对齐客")
    tok = r["token"]
    char = w.get_char(tok)
    char.born_at = time_past()
    CharacterRepository.save(char)

    checks = [
        ("/探查", True),
        ("/大事记", True),
        ("/告示", True),
        ("/坊市", True),
        ("/自创功法 噬血炼骨", True),
        ("/挂赏", False),  # 缺参数
        ("/接令", False),
        ("/支取", False),
        ("/寄售", False),
        ("/买寄售", False),
        ("/撤单", False),
        ("/世情", True),
    ]
    for cmd, expect_ok in checks:
        res = w.handle(tok, cmd)
        ok = bool(res.get("ok"))
        assert ok == expect_ok, (cmd, res)
        print(f"  {cmd} -> ok={ok}")

    # 未知指令仍应报错（不是静默）
    res = w.handle(tok, "/不存在的指令")
    assert res.get("ok") is False
    print("✓ CLI 对齐指令全链路")


def time_past():
    import time
    return time.time() - 80 * 3600.0


def test_create_art_writes_skill():
    w = World(auto_tick=False)
    r = w.join("创法客")
    tok = r["token"]
    res = w.handle(tok, "/自创功法 玄天正气")
    assert res.get("ok") is True, res
    assert "功法" in res.get("text", "") or "真经" in res.get("text", "") or "残卷" in res.get("text", "")
    char = w.get_char(tok)
    assert char and len(char.skills) >= 2
    print("✓ 自创功法学入 skills")


if __name__ == "__main__":
    test_cli_parity_commands()
    test_create_art_writes_skill()
    print("\n✅ UI/CLI 指令对齐测试通过")
