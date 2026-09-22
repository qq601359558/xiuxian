"""任务系统：初玩教学 T1–T10 与发奖"""
import os
import sys
import time
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
from core import tasks
from core.tasks import (
    ensure_tasks,
    complete_step,
    take_daily,
    format_task_board,
    abandon_task,
    TASK_DEFS,
)


def _char(name="学员", uid=None):
    c = WorldClock.create_new_character(uid or f"tsk_{int(time.time()*1000)%100000}", name)
    c.location = "青云坊市客栈"
    CharacterRepository.save(c)
    return c


def test_intro_chain_all_steps():
    init_db()
    p = _char("教习")
    rec = ensure_tasks(p)
    assert any(a.get("task_id") == "intro_teach" for a in rec["active"])
    board = format_task_board(p)
    assert "初玩教学" in board["text"]
    checks = [
        "chat_say",
        "trade_query",
        "trade_buy",
        "use_pill",
        "move",
        "look_board",
        "look_schedule",
        "cultivate_done",
        "look_breakthrough",
        "look_echo",
        "look_task",
    ]
    stones0 = p.spirit_stones
    for ck in checks:
        res = complete_step(p, ck)
        assert res.get("messages") or res.get("advanced") or ck == "trade_query", (ck, res)
    p2 = CharacterRepository.get_by_id(p.id)
    assert p2.spirit_stones > stones0
    rec2 = ensure_tasks(p)
    assert not any(a.get("task_id") == "intro_teach" for a in rec2["active"])
    assert any(d.get("task_id") == "intro_teach" for d in rec2["done"])
    text = format_task_board(p)["text"]
    assert "初玩既毕" not in text  # 收束句在 messages
    print("✓ 初玩 T1–T10 完成与发奖")


def test_skip_ahead_and_daily():
    init_db()
    p = _char("速通客", uid=f"tsk_skip_{int(time.time())}")
    # 跳步：直接买货，应完成更早未完成的匹配步
    r = complete_step(p, "trade_buy")
    rec = ensure_tasks(p)
    ids = rec["active"][0]["done_steps"] if rec.get("active") else []
    assert "t3_buy" in ids
    # daily
    t = take_daily(p, "daily_greet")
    assert t["success"]
    t2 = take_daily(p, "daily_greet")
    assert not t2["success"]
    ab = abandon_task(p, "intro_teach")
    assert not ab["success"]
    print("✓ 跳步与日常/不可弃 intro")


def test_server_task_cmd():
    init_db()
    from server.world import World

    w = World(auto_tick=False)
    name = f"任务客{int(time.time())%10000}"
    sess = w.join(name, user_id=f"tsk_srv_{int(time.time())}")
    tok = sess["token"]
    r = w.handle(tok, "/任务")
    assert r.get("ok") is True
    assert "初玩教学" in r.get("text", "") or "任务" in r.get("text", "")
    r2 = w.handle(tok, "/天道")
    assert r2.get("ok") is True
    # look_board 应触发 T6
    board = w.handle(tok, "/任务")
    assert "✓" in board.get("text", "") or "→" in board.get("text", "")
    r3 = w.handle(tok, "/任务 接 daily_scout")
    assert r3.get("ok") is True
    print("✓ 服务器 /任务 与钩子")


if __name__ == "__main__":
    test_intro_chain_all_steps()
    test_skip_ahead_and_daily()
    test_server_task_cmd()
    print("\ntask system tests passed")
