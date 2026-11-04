"""QA 第二轮 · 重点 3：双端交替操作一致性。

同一角色/同一状态对象交替经 server handle 与引擎（CLI 同引擎）操作：
- 除凶：server 接令 → 引擎可见同一单 → 引擎结算恰一次 → server 视图无残单；
- 诺言：server 立诺 → 引擎践诺结算恰一次（功德恰 +10）→ 重复触发零重复入账；
- 议政：server 投票 → 引擎改票 → 同一票仓单条记录；引擎投票与 server 投票同仓。
CLI 侧以源码对齐断言佐证：三域 CLI 处理器调用同一引擎入口（非另写一套）。
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core import hunt
from core.clock import WorldClock
from core.council import CouncilEngine
from core.models import CharacterStatus
from core.promises import PromiseEngine
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"
LOC_B = "青云宗外门山门"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _kill(c):
    if c is None:
        return
    live = _get(c.id)
    if live and live.status != CharacterStatus.DEAD:
        live.status = CharacterStatus.DEAD
        CharacterRepository.save(live)


def _merit(cid):
    return _get(cid).karma.merit_value


# ---------------- 除凶：server 接令 × 引擎结算 ----------------

def test_hunt_server_accept_engine_settle_once():
    r = WORLD.join(f"QA2双端猎{_tag()}")
    tok = r["token"]
    hunter_char = WORLD.get_char(tok)
    victim = WorldClock.create_new_character(f"qa2_de_v_{_tag()}", f"QA2双端凶{_tag()}")
    victim.location = LOC_A
    victim.karma.sin_value = 120
    CharacterRepository.save(victim)
    try:
        res = WORLD.handle(tok, f"/接令 {victim.name}")
        assert res["ok"], res
        orders = WorldStateRepository.get("hunt_orders") or {}
        mine = [o for o in orders.values()
                if o.get("target_id") == victim.id and o.get("status") == "OPEN"]
        assert mine and hunter_char.id in (mine[0].get("hunters") or {}), mine
        km0 = _merit(hunter_char.id)
        out = hunt.settle_kill(_get(hunter_char.id), _get(victim.id))
        assert out is not None and out["merit"] == 40, out
        assert _merit(hunter_char.id) == km0 + 40
        # 二次结算（另一端重复触发）必须零入账
        out2 = hunt.settle_kill(_get(hunter_char.id), _get(victim.id))
        assert out2 is None, out2
        assert _merit(hunter_char.id) == km0 + 40
        res = WORLD.handle(tok, "/除凶")
        assert res["ok"] and "你未接令" in res["text"], res
        print("✓ 双端除凶：server 接令与引擎同单，结算恰一次，二次触发零入账")
    finally:
        _kill(hunter_char)
        _kill(victim)


# ---------------- 诺言：server 立诺 × 引擎践诺 ----------------

def test_promise_server_make_engine_fulfil_once():
    r = WORLD.join(f"QA2双端诺{_tag()}")
    tok = r["token"]
    promiser = WORLD.get_char(tok)
    npc = WorldClock.create_new_character(f"npc_qa2_de_{_tag()}", f"QA2双端受诺{_tag()}")
    npc.location = LOC_A
    CharacterRepository.save(npc)
    try:
        res = WORLD.handle(tok, f"/许诺 {npc.name} 抵达 {LOC_B}")
        assert res["ok"], res
        plist = PromiseEngine._involving(promiser.id)
        assert len(plist) == 1 and plist[0].status.value == "ACTIVE", plist
        km0 = _merit(promiser.id)
        # 引擎侧（CLI 同路径）：移动达地点后 note_arrival 结算
        me = _get(promiser.id)
        me.location = LOC_B
        CharacterRepository.save(me)
        me = _get(promiser.id)
        line = PromiseEngine.note_arrival(me, LOC_B)
        assert line, "抵达应触发践诺结算"
        CharacterRepository.save(me)
        assert _merit(promiser.id) == km0 + 10, _merit(promiser.id)
        # 重复抵达触发：诺已结清，不得二次入账
        line2 = PromiseEngine.note_arrival(_get(promiser.id), LOC_B)
        assert not line2
        assert _merit(promiser.id) == km0 + 10
        plist = PromiseEngine._involving(promiser.id)
        assert plist[0].status.value == "KEPT", plist
        print("✓ 双端诺言：server 立诺、引擎践诺恰一次 +10，重复触发零入账")
    finally:
        _kill(promiser)
        _kill(npc)


# ---------------- 议政：server 投票 × 引擎改票/投票同仓 ----------------

def test_council_cross_end_single_ballot():
    sect = "青云宗"
    key = f"sect_council:{sect}"
    prior = WorldStateRepository.get(key)
    r1 = WORLD.join(f"QA2双端议甲{_tag()}")
    r2 = WORLD.join(f"QA2双端议乙{_tag()}")
    a, b = WORLD.get_char(r1["token"]), WORLD.get_char(r2["token"])
    try:
        WorldStateRepository.set(key, "")
        t0 = time.time()
        CouncilEngine.advance(sect, now=t0)
        for c in (a, b):
            cc = _get(c.id)
            cc.sect = sect
            cc.sect_rank = "内门弟子"
            CharacterRepository.save(cc)
        res = WORLD.handle(r1["token"], "/投票 支持")
        assert res["ok"], res
        # 引擎侧（CLI 同路径）改票：同仓单条
        out = CouncilEngine.vote(_get(a.id), "反对", now=t0 + 10)
        assert out["success"], out
        out2 = CouncilEngine.vote(_get(b.id), "支持", now=t0 + 20)
        assert out2["success"], out2
        session = CouncilEngine.advance(sect, now=t0 + 30)
        votes = session.get("votes") or {}
        assert votes.get(a.id) == "oppose", votes
        assert votes.get(b.id) == "support", votes
        assert len([k for k in votes if k in (a.id, b.id)]) == 2, votes
        print("✓ 双端议政：server 投票与引擎改票同仓单条，跨端各计一票")
    finally:
        if prior:
            WorldStateRepository.set(key, prior)
        else:
            WorldStateRepository.set(key, "")
        _kill(a)
        _kill(b)


# ---------------- CLI 源码对齐：同引擎入口 ----------------

def test_cli_uses_same_engine_entries():
    src = (Path(__file__).resolve().parent.parent / "cli" / "main.py").read_text(encoding="utf-8")
    for needle in (
        "_hunt.accept(player",            # 除凶接令
        "PromiseEngine.make_promise",     # 立诺
        "PromiseEngine.note_arrival",     # 践诺（移动结算）
        "PromiseEngine.accept(player",    # 应诺
        "CouncilEngine.vote(player",      # 议政投票
        "CouncilEngine.lobby(player",     # 议政游说
        "BountyEngine.settle_on_kill",    # 悬赏击杀结算
    ):
        assert needle in src, f"CLI 未调用同一引擎入口：{needle}"
    print("✓ CLI 对齐：除凶/诺言/议政/悬赏四域 CLI 均调用与 server 相同的引擎入口")
