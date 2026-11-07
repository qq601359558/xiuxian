"""game-feel-phase1 复审返工第二轮验收（MF-R1 一条）。

MF-R1：briefing() 在 build_entry 之前先调 GoalEngine.sync_progress
（只改内存补目标 + E6 求值，未落盘），而 MF-1 修复在 build_entry 内
② advance_for 之后无条件重读 DB 行并逐字段就地同步，把内存 goals
整表冲掉——无 origin、DB goals=[] 的老角色经 briefing 后，
entry.lines.fate 误报「尚未立命」，与同一响应内 goals 字段自相矛盾。

Spec §2.3 写死口径：lines.fate 无 origin 时回退 = 第一个 active
目标的 title — detail；无任何 active 目标才用「尚未立命」。

修复口径（core/briefing.py）：取舍 (c) 重读合并策略——逐字段同步时
goals 按 id 并集、内存优先，其余字段以 DB 为准（MF-1 链兑现落账
不回滚、③ 基于兑现后数值求值的行为不回退；防回退证据为重跑
tests/test_game_feel_phase1_rework.py 的 test_mf1_* 全绿，见返工报告）。

DB 处理：本文件不新建因果链（避开共享 DB active 链 40/40 上限误报），
角色均为隔离 user_id 的新建角，goals/origin 显式清空后落盘。
"""
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"
os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

from core.clock import WorldClock
from storage.db import AuthSessionRepository, CharacterRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char_no_origin_empty_goals(name="无出身老角"):
    """无 origin + DB goals=[] 的老角色（MF-R1 实测场景）。"""
    c = WorldClock.create_new_character(f"mfr1_{name}_{_tag()}", f"{name}{_tag()}")
    c.location = LOC
    c.origin = {}
    c.goals = []
    CharacterRepository.save(c)
    got = CharacterRepository.get_by_id(c.id)
    assert got.origin == {} and (got.goals or []) == [], (
        f"夹具前提不成立：origin={got.origin} goals={got.goals}")
    return got


def _assert_fate_matches_first_active(body):
    goals = body.get("goals") or []
    active = [g for g in goals if g.get("status") == "active"]
    assert active, "sync_progress 应已补出 active 目标，响应 goals 不应为空"
    entry = body.get("entry")
    assert entry is not None, "briefing 响应应含 entry"
    fate = entry["lines"]["fate"]
    g0 = active[0]
    expected = f"命途：{g0.get('title', '')} — {g0.get('detail', '')}"
    assert fate == expected, (
        f"lines.fate 应回退为首个 active 目标（§2.3），实际 {fate!r}，期望 {expected!r}")
    assert "尚未立命" not in fate


# ================= MF-R1 =================

def test_mfr1_briefing_fate_fallback_first_active_goal():
    """无 origin + DB goals=[] 经 briefing()：fate 显示首个 active 目标，
    且响应 goals 字段与 entry 一致、入参对象内存 goals 不被重读冲掉。"""
    from core.briefing import briefing

    char = _char_no_origin_empty_goals()
    b = briefing(char)
    _assert_fate_matches_first_active(b)
    # 同一响应一致性：briefing 返回的 goals 与 build_entry 后入参对象
    # 内存中的 active goals 必须同集（不得被 DB 重读整表冲掉）
    mem_active_ids = [g.get("id") for g in (char.goals or [])
                      if g.get("status") == "active"]
    resp_active_ids = [g.get("id") for g in b["goals"]
                       if g.get("status") == "active"]
    assert mem_active_ids == resp_active_ids, (
        f"内存 goals 被冲掉/不一致：内存 {mem_active_ids} vs 响应 {resp_active_ids}")
    assert char.goals, "briefing 后 char.goals 不应被清空"


def test_mfr1_world_briefing_endpoint_fate_not_misreported():
    """同上角色经真实入口 GET /world/briefing：fate 行不误报。"""
    from server.app import GameHandler

    char = _char_no_origin_empty_goals("端点老角")
    token = f"mfr1_tok_{_tag()}"
    AuthSessionRepository.save(token, char.user_id, char.id, char.name)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/world/briefing",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read().decode())
    finally:
        httpd.shutdown()
    assert body.get("ok") is True
    _assert_fate_matches_first_active(body)
