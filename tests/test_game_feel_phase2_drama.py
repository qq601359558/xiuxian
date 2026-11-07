"""game-feel-phase2 线一戏剧（Spec §5/§6）后端验收。

覆盖：DR-01~DR-07（五类戏剧/频控/后果对账/AI 全关）、RM-01~RM-04
（传闻写入口）、因果链微调口钳制（§5.3 nudge）。
隔离：共享 DB + 唯一前缀（dr_ 玩家 / npc_dr_ NPC），自造链/诺言/边
在收尾按 id 删除，角色置死。时间口径：1 游戏日 = SECONDS_PER_GAME_DAY。
"""
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

import pytest

from config import SECONDS_PER_GAME_DAY
from core.clock import WorldClock
from core.models import CharacterStatus
from storage.db import (
    init_db,
    CharacterRepository,
    ChronicleRepository,
    EventLedgerRepository,
    KarmaChainRepository,
    KarmaLinkRepository,
    NpcAgendaRepository,
    NpcMindRepository,
    PromiseRepository,
    WorldStateRepository,
)
from core.bounty import KarmaLink
from core.karma_chains import KarmaChain, KarmaChainEngine
from core.npc_mind import shift_attitude, attitude_toward
from core.promises import Promise, PromiseStatus
from core import rumors

init_db()

DAY = SECONDS_PER_GAME_DAY
LOC = "青云坊市客栈"


@pytest.fixture(autouse=True)
def _ai_off(monkeypatch):
    """全文件 AI 全关口径（DR-07）：戏剧走本地模板、后果无缺失。"""
    import core.npc_proactive as np_mod

    monkeypatch.setattr(np_mod, "ai_ready", lambda: False)
    yield


def _tag():
    return uuid.uuid4().hex[:6]


def _player(name="戏客", location=LOC, tier=2):
    c = WorldClock.create_new_character(f"dr_{_tag()}_{name}", f"{name}{_tag()}")
    c.location = location
    c.realm.tier = tier
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


def _npc(name="戏翁", location=LOC, tier=1, sect=None, stones=None):
    c = WorldClock.create_new_character(f"npc_dr_{_tag()}_{name}", f"{name}{_tag()}")
    c.location = location
    c.realm.tier = tier
    c.sect = sect
    if stones is not None:
        c.spirit_stones = stones
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


def _set_att(npc, other_id, value):
    NpcMindRepository.set_attitude(npc.id, other_id, value)


def _att(npc, other_id):
    fresh = CharacterRepository.get_by_id(npc.id)
    return attitude_toward(fresh, other_id)["value"]


def _chain(player, npc, *, kind="chou", polarity=-1, strength=3,
           status="fermenting", now=None, mature_days=5.0, resolved_at=0.0):
    t = now if now is not None else time.time()
    ch = KarmaChain(
        chain_key=f"dr_{_tag()}",
        kind=kind, polarity=polarity,
        player_id=player.id, player_name=player.name,
        counterparty_id=npc.id, counterparty_name=npc.name,
        strength=strength, status=status,
        created_at=t - DAY, ferment_at=t - DAY / 2,
        mature_at=t + mature_days * DAY, deadline_at=t + 30 * DAY,
        resolved_at=resolved_at,
    )
    KarmaChainRepository.save(ch)
    return KarmaChainRepository.get_by_id(ch.id) if hasattr(
        KarmaChainRepository, "get_by_id") else ch


def _get_chain(chain_id):
    for c in KarmaChainRepository.list_all():
        if c.id == chain_id:
            return c
    return None


def _promise(player, npc, *, now=None, status=PromiseStatus.ACTIVE):
    t = now if now is not None else time.time()
    p = Promise(
        promiser_id=player.id, promiser_name=player.name,
        promisee_id=npc.id, promisee_name=npc.name, promisee_is_npc=True,
        kind="quest", desc=f"{player.name}对{npc.name}的未了之诺",
        status=status, created_at=t, deadline=t + 7 * DAY,
    )
    PromiseRepository.save(p)
    return p


def _get_promise(pid):
    for p in PromiseRepository.list_all():
        if p.id == pid:
            return p
    return None


def _cleanup(*chars):
    ids = {c.id for c in chars if c is not None}
    for ch in KarmaChainRepository.list_all():
        if ch.player_id in ids or ch.counterparty_id in ids:
            KarmaChainRepository.delete(ch.id)
    for p in PromiseRepository.list_all():
        if p.promiser_id in ids or p.promisee_id in ids:
            PromiseRepository.delete(p.id)
    # KarmaLinkRepository 无 delete：测试边随角色置死自然失效（id 唯一不复用）
    for c in chars:
        if c is None:
            continue
        try:
            WorldStateRepository.set(f"drama_pending:{c.id}", [])
            WorldStateRepository.set(f"drama_quota:{c.id}", {})
        except Exception:
            pass
        c.status = CharacterStatus.DEAD
        CharacterRepository.save(c)


def _quota(char_id):
    return WorldStateRepository.get(f"drama_quota:{char_id}") or {}


def _rumor_find(substr, tag=None):
    out = []
    for r in rumors.list_rumors(30):
        if substr in (r.get("text") or "") and (tag is None or tag in (r.get("tags") or [])):
            out.append(r)
    return out


# ================= DR-01 频控三闸 =================

def test_dr01_provoke_trigger_and_gates():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("闸客")
    npc = _npc("闸翁")
    _set_att(npc, player.id, -50)  # hostile
    try:
        evs = DramaEngine.evaluate(player, trigger="travel", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "provoke"
        assert evs[0]["npc_id"] == npc.id
        assert evs[0]["id"].startswith("dr_")
        assert evs[0]["expires_at"] - evs[0]["created_at"] == 86400
        assert {o["key"] for o in evs[0]["options"]} == {"fight", "avoid"}
        pend = DramaEngine.list_pending(player, now=now)
        assert len(pend) == 1
        # 同人闸：同 NPC 同游戏日第二次评估不再新建
        evs2 = DramaEngine.evaluate(player, trigger="travel", now=now + 10)
        assert evs2 == []
        assert _quota(player.id).get("count") == 1
    finally:
        _cleanup(player, npc)


def test_dr01_daily_total_cap_three():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("总闸客")
    npcs = [_npc(f"总闸翁{i}") for i in range(4)]
    for n in npcs:
        _set_att(n, player.id, -50)
    try:
        made = []
        for _ in range(4):
            made.extend(DramaEngine.evaluate(player, trigger="travel", now=now))
        assert len(made) == 3, "每现实日计件戏剧 ≤3"
        assert _quota(player.id).get("count") == 3
        assert len(DramaEngine.list_pending(player, now=now)) == 3
    finally:
        _cleanup(player, *npcs)


def test_dr_priority_betrayal_over_provoke():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("优先客")
    npc = _npc("优先翁")
    _set_att(npc, player.id, -50)
    _promise(player, npc, now=now)
    try:
        evs = DramaEngine.evaluate(player, trigger="login", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "betrayal"
    finally:
        _cleanup(player, npc)


# ================= DR-02 挑衅回应 =================

def test_dr02_provoke_fight_enters_fight_dispatch():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("应战客")
    npc = _npc("应战翁")
    _set_att(npc, player.id, -50)
    calls = []
    try:
        ev = DramaEngine.evaluate(player, trigger="travel", now=now)[0]
        res = DramaEngine.respond(
            player, ev["id"], "fight", now=now,
            fight_fn=lambda name: calls.append(name) or {"ok": True, "text": "斗法已开"})
        assert res["success"] is True and res["action"] == "fight"
        assert calls == [npc.name], "fight 必须转调既有斗法入口（同名分发）"
        assert DramaEngine.list_pending(player, now=now) == []
    finally:
        _cleanup(player, npc)


def test_dr02_provoke_avoid_no_numbers_rumor_only():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("避战客")
    npc = _npc("避战翁")
    _set_att(npc, player.id, -50)
    try:
        before = CharacterRepository.get_by_id(player.id)
        snap = (before.spirit_stones, before.realm.current_exp,
                before.karma.merit_value, before.karma.sin_value,
                before.karma.dao_heart, before.lifespan.death_timestamp)
        ev = DramaEngine.evaluate(player, trigger="travel", now=now)[0]
        res = DramaEngine.respond(player, ev["id"], "avoid", now=now)
        assert res["success"] is True
        after = CharacterRepository.get_by_id(player.id)
        assert snap == (after.spirit_stones, after.realm.current_exp,
                        after.karma.merit_value, after.karma.sin_value,
                        after.karma.dao_heart, after.lifespan.death_timestamp)
        hits = _rumor_find(player.name, tag="avoid")
        assert hits and abs(float(hits[0]["truth"]) - 0.85) < 1e-9
        assert npc.name in hits[0]["text"]
    finally:
        _cleanup(player, npc)


# ================= DR-03 示好 =================

def test_dr03_favor_after_en_chain_resolved_transfer():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("受礼客")
    npc = _npc("赠礼翁", stones=50)
    _set_att(npc, player.id, 20)
    _chain(player, npc, kind="en", polarity=1, status="resolved",
           now=now, resolved_at=now - 100)
    p0 = CharacterRepository.get_by_id(player.id).spirit_stones
    n0 = CharacterRepository.get_by_id(npc.id).spirit_stones
    try:
        evs = DramaEngine.evaluate(player, trigger="login", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "favor"
        p1 = CharacterRepository.get_by_id(player.id).spirit_stones
        n1 = CharacterRepository.get_by_id(npc.id).spirit_stones
        assert p1 - p0 == 20 and n0 - n1 == 20, "赠礼为转移对账（min(20, NPC 灵石)）"
        assert _att(npc, player.id) == 23, "示好态度 +3"
        rows = EventLedgerRepository.query_by_type_for_target(
            player.id, type="RELATION", limit=30)
        mine = [r for r in rows if r["actor_id"] == npc.id
                and any("戏剧·示好" in x for x in (r.get("refs") or []))]
        assert mine, "示好须留 RELATION 痕（reason=戏剧·示好）"
        assert _quota(player.id).get("count", 0) == 0, "示好不占总闸额"
        res = DramaEngine.respond(player, evs[0]["id"], "ack", now=now)
        assert res["success"] is True
        assert DramaEngine.list_pending(player, now=now) == []
    finally:
        _cleanup(player, npc)


def test_dr03_favor_via_relation_trace():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("留痕客")
    npc = _npc("留痕翁", stones=0)
    try:
        shift_attitude(npc, player.id, 50, reason="赠礼")  # RELATION after=ally
        evs = DramaEngine.evaluate(player, trigger="login", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "favor"
        assert _quota(player.id).get("favor_consumed_ts"), "RELATION ts 须被消费标记"
        # NPC 灵石为 0：只落态度 +3（50→53），无转移
        assert _att(npc, player.id) == 53
    finally:
        _cleanup(player, npc)


def test_dr03b_origin_relation_does_not_trigger_favor():
    """集成裁决回归：出身植入关系（reason="origin"）不触发示好——
    新角首登不得被出身关系概率性赠礼（qa5 出身灵石对账曾被打破）。"""
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("出身客")
    npc = _npc("出身翁", stones=100)
    stones0 = int(player.spirit_stones or 0)
    try:
        shift_attitude(npc, player.id, 50, reason="origin")  # 同 (b) 形状，唯 reason 不同
        evs = DramaEngine.evaluate(player, trigger="login", now=now)
        assert all(e["type"] != "favor" for e in evs), \
            "出身初始关系不得触发示好"
        assert int(player.spirit_stones or 0) == stones0, "不得发生赠礼转移"
    finally:
        _cleanup(player, npc)


# ================= DR-04 背叛 =================

def test_dr04_betrayal_omen_and_nudge_and_confront_no_settle():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("背诺客")
    npc = _npc("背诺翁")
    _set_att(npc, player.id, -20)
    p = _promise(player, npc, now=now)
    ch = _chain(player, npc, kind="nuo", polarity=-1, status="fermenting",
                now=now, mature_days=5.0)
    try:
        evs = DramaEngine.evaluate(player, trigger="login", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "betrayal"
        assert evs[0]["promise_id"] == p.id
        hits = _rumor_find(npc.name, tag="betrayal")
        assert hits and abs(float(hits[0]["truth"]) - 0.85) < 1e-9, "背叛先兆传闻 truth=0.85"
        after = _get_chain(ch.id)
        expect = now + 3 * DAY
        assert abs(after.mature_at - expect) < 1.0, "nuo 链发酵提前恰 2 游戏日"
        res = DramaEngine.respond(player, evs[0]["id"], "confront", now=now)
        assert res["success"] is True and res["action"] == "talk"
        assert _get_promise(p.id).status == PromiseStatus.ACTIVE, "摊牌不得提前结算诺言"
    finally:
        _cleanup(player, npc)


def test_dr04_betrayal_via_karma_link_edge():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("仇边客")
    npc = _npc("仇边翁")
    _set_att(npc, player.id, 0)  # 态度不满足第一支
    _promise(player, npc, now=now)
    KarmaLinkRepository.save(KarmaLink(
        a_id=player.id, a_name=player.name, b_id=npc.id, b_name=npc.name,
        link_type="仇", strength=3, created_at=now))
    try:
        evs = DramaEngine.evaluate(player, trigger="login", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "betrayal"
    finally:
        _cleanup(player, npc)


# ================= DR-05 牵连 =================

def test_dr05_involvement_mediate_chou_and_en():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("劝和客")
    foe = _npc("结仇翁", sect="青云宗")
    third = _npc("同门翁", sect="青云宗")
    _set_att(third, player.id, 20)
    ch = _chain(player, foe, kind="chou", polarity=-1, strength=3,
                status="fermenting", now=now)
    try:
        # §5.2 优先级：仇链先出挑衅（counterparty），其同人闸消耗后次评出牵连
        first = DramaEngine.evaluate(player, trigger="login", now=now)
        assert len(first) == 1 and first[0]["type"] == "provoke"
        evs = DramaEngine.evaluate(player, trigger="login", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "involvement"
        assert evs[0]["npc_id"] == third.id and evs[0]["chain_id"] == ch.id
        res = DramaEngine.respond(player, evs[0]["id"], "mediate", now=now)
        assert res["success"] is True and res.get("mediated") is True
        assert _get_chain(ch.id).strength == 2, "劝和：chou 链 strength -1"
        assert _att(third, player.id) == 23, "劝和：第三方态度 +3"
    finally:
        _cleanup(player, foe, third)

    # en 链：劝和加速发酵 3 日
    player2 = _player("劝恩客")
    foe2 = _npc("结恩翁", sect="万剑仙门")
    third2 = _npc("同门姥", sect="万剑仙门")
    _set_att(third2, player2.id, 30)
    ch2 = _chain(player2, foe2, kind="en", polarity=1, strength=2,
                 status="fermenting", now=now, mature_days=10.0)
    try:
        ev = DramaEngine.evaluate(player2, trigger="login", now=now)[0]
        assert ev["type"] == "involvement"
        DramaEngine.respond(player2, ev["id"], "mediate", now=now)
        after = _get_chain(ch2.id)
        assert abs(after.mature_at - (now + 7 * DAY)) < 1.0, "劝和：en 链发酵提前 3 日"
    finally:
        _cleanup(player2, foe2, third2)


def test_dr05_involvement_harden_and_mediate_fail():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player = _player("硬顶客")
    foe = _npc("硬仇翁", sect="九幽天魔宗")
    third = _npc("硬同门", sect="九幽天魔宗")
    _set_att(third, player.id, 0)
    ch = _chain(player, foe, kind="chou", polarity=-1, strength=8,
                status="fermenting", now=now)
    try:
        DramaEngine.evaluate(player, trigger="login", now=now)  # 先出挑衅（优先级）
        ev = DramaEngine.evaluate(player, trigger="login", now=now)[0]
        assert ev["type"] == "involvement"
        # 第三方态度 0 <15：劝和不成，零落账
        res = DramaEngine.respond(player, ev["id"], "mediate", now=now)
        assert res["success"] is True and res.get("mediated") is False
        assert _get_chain(ch.id).strength == 8 and _att(third, player.id) == 0
    finally:
        _cleanup(player, foe, third)

    player2 = _player("硬顶客二")
    foe2 = _npc("硬仇翁二", sect="九幽天魔宗")
    third2 = _npc("硬同门二", sect="九幽天魔宗")
    _set_att(third2, player2.id, 5)
    ch2 = _chain(player2, foe2, kind="chou", polarity=-1, strength=8,
                 status="fermenting", now=now)
    try:
        DramaEngine.evaluate(player2, trigger="login", now=now)  # 先出挑衅（优先级）
        ev = DramaEngine.evaluate(player2, trigger="login", now=now)[0]
        assert ev["type"] == "involvement"
        res = DramaEngine.respond(player2, ev["id"], "harden", now=now)
        assert res["success"] is True
        assert _att(third2, player2.id) == 2, "硬顶：第三方态度 -3"
        assert _get_chain(ch2.id).strength == 8, "硬顶：strength 钳顶 8"
    finally:
        _cleanup(player2, foe2, third2)


# ================= DR-06 求助 =================

def _help_setup(now, npc_tier=1, player_tier=2):
    player = _player("求助客", tier=player_tier)
    npc = _npc("求助翁", tier=npc_tier)
    _set_att(npc, player.id, 20)
    NpcAgendaRepository.upsert(
        npc_id=npc.id, npc_name=npc.name, agenda_type="treasure",
        target_hint="", note="寻宝", state="active", last_tick=0.0, progress=0)
    return player, npc


def test_dr06_help_accept_opportunity_goal():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player, npc = _help_setup(now)
    try:
        evs = DramaEngine.evaluate(player, trigger="travel", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "help"
        res = DramaEngine.respond(player, evs[0]["id"], "accept", now=now)
        assert res["success"] is True
        fresh = CharacterRepository.get_by_id(player.id)
        omen = [g for g in (fresh.goals or [])
                if g.get("source") == "omen" and g.get("status") == "active"]
        assert omen and npc.name in (omen[-1].get("title") or "")
    finally:
        _cleanup(player, npc)


def test_dr06_help_decline_attitude_minus2():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player, npc = _help_setup(now)
    try:
        ev = DramaEngine.evaluate(player, trigger="travel", now=now)[0]
        res = DramaEngine.respond(player, ev["id"], "decline", now=now)
        assert res["success"] is True
        assert _att(npc, player.id) == 18, "婉拒：态度恰 -2"
        rows = EventLedgerRepository.query_by_type_for_target(
            player.id, type="RELATION", limit=30)
        mine = [r for r in rows if r["actor_id"] == npc.id
                and any("戏剧·求助被拒" in x for x in (r.get("refs") or []))]
        assert mine
    finally:
        _cleanup(player, npc)


def test_dr06_help_blocked_when_npc_higher_realm():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player, npc = _help_setup(now, npc_tier=5, player_tier=1)
    try:
        assert DramaEngine.evaluate(player, trigger="travel", now=now) == []
    finally:
        _cleanup(player, npc)


# ================= DR-07 AI 全关 + 过期 =================

def test_dr07_all_five_types_local_templates():
    from core.npc_proactive import DramaEngine

    now = time.time()
    made = {}
    # provoke
    p1 = _player("全关甲"); n1 = _npc("全关甲翁"); _set_att(n1, p1.id, -50)
    # betrayal
    p2 = _player("全关乙"); n2 = _npc("全关乙翁"); _set_att(n2, p2.id, -20)
    _promise(p2, n2, now=now)
    # involvement
    p3 = _player("全关丙"); f3 = _npc("全关丙仇", sect="青云宗")
    t3 = _npc("全关丙同", sect="青云宗"); _set_att(t3, p3.id, 0)
    _chain(p3, f3, kind="chou", polarity=-1, status="fermenting", now=now)
    # help
    p4, n4 = _help_setup(now)
    # favor
    p5 = _player("全关戊"); n5 = _npc("全关戊翁", stones=10); _set_att(n5, p5.id, 20)
    _chain(p5, n5, kind="en", polarity=1, status="resolved", now=now,
           resolved_at=now - 50)
    chars = [p1, n1, p2, n2, p3, f3, t3, p4, n4, p5, n5]
    try:
        for pl, key in ((p1, "provoke"), (p2, "betrayal"),
                        (p4, "help"), (p5, "favor")):
            evs = DramaEngine.evaluate(pl, trigger="login", now=now)
            assert len(evs) == 1 and evs[0]["type"] == key, f"{key} AI 全关须触发"
            assert evs[0]["source"] == "local" and evs[0]["text"], f"{key} 须本地模板"
            made[key] = evs[0]
        # 牵连：仇链首评先挑衅（优先级口径），次评出牵连，同样本地模板
        DramaEngine.evaluate(p3, trigger="login", now=now)
        evs = DramaEngine.evaluate(p3, trigger="login", now=now)
        assert len(evs) == 1 and evs[0]["type"] == "involvement"
        assert evs[0]["source"] == "local" and evs[0]["text"]
        made["involvement"] = evs[0]
    finally:
        _cleanup(*chars)


def test_dr07_expired_event_lazy_purge_no_effects():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player, npc = _help_setup(now)
    try:
        ev = DramaEngine.evaluate(player, trigger="travel", now=now)[0]
        pend = WorldStateRepository.get(f"drama_pending:{player.id}")
        pend[0]["expires_at"] = now - 1
        WorldStateRepository.set(f"drama_pending:{player.id}", pend)
        assert DramaEngine.list_pending(player, now=now) == []
        res = DramaEngine.respond(player, ev["id"], "accept", now=now)
        assert res["success"] is False
        fresh = CharacterRepository.get_by_id(player.id)
        assert not [g for g in (fresh.goals or [])
                    if g.get("source") == "omen" and npc.name in (g.get("title") or "")]
        assert _att(npc, player.id) == 20, "过期事件零落账"
    finally:
        _cleanup(player, npc)


def test_dr_respond_invalid_option_zero_effects():
    from core.npc_proactive import DramaEngine

    now = time.time()
    player, npc = _help_setup(now)
    try:
        ev = DramaEngine.evaluate(player, trigger="travel", now=now)[0]
        res = DramaEngine.respond(player, ev["id"], "fight", now=now)
        assert res["success"] is False
        assert len(DramaEngine.list_pending(player, now=now)) == 1, "非法选项不销项"
        res2 = DramaEngine.respond(player, "dr_不存在的", "accept", now=now)
        assert res2["success"] is False
    finally:
        _cleanup(player, npc)


# ================= §5.3 nudge 钳制 =================

def test_nudge_ferment_clamps():
    now = time.time()
    player = _player("微调客")
    npc = _npc("微调翁")
    ch = _chain(player, npc, kind="nuo", polarity=1, status="fermenting",
                now=now, mature_days=10.0)
    ch2 = _chain(player, npc, kind="en", polarity=1, status="fermenting",
                 now=now, mature_days=0.5)
    try:
        assert KarmaChainEngine.nudge_ferment(ch.id, days=-2, now=now) is True
        assert abs(_get_chain(ch.id).mature_at - (now + 8 * DAY)) < 1.0
        # 不得早于 now
        assert KarmaChainEngine.nudge_ferment(ch2.id, days=-3, now=now) is True
        assert abs(_get_chain(ch2.id).mature_at - now) < 1.0
        # days 越界钳制：正值不得延后
        before = _get_chain(ch.id).mature_at
        KarmaChainEngine.nudge_ferment(ch.id, days=2, now=now)
        assert _get_chain(ch.id).mature_at == before
        # Chronicle 留痕含 chain id 与前后值
        recs = ChronicleRepository.get_recent(80)
        assert any(ch.id in s for s in recs), "nudge 须写 Chronicle 留痕"
    finally:
        _cleanup(player, npc)


def test_nudge_strength_clamps():
    now = time.time()
    player = _player("强度客")
    npc = _npc("强度翁")
    ch = _chain(player, npc, kind="chou", polarity=-1, strength=8,
                status="fermenting", now=now)
    try:
        assert KarmaChainEngine.nudge_strength(ch.id, delta=1, now=now) is True
        assert _get_chain(ch.id).strength == 8, "钳顶 8"
        assert KarmaChainEngine.nudge_strength(ch.id, delta=-1, now=now) is True
        assert _get_chain(ch.id).strength == 7
        assert KarmaChainEngine.nudge_strength(ch.id, delta=2, now=now) is False
        assert _get_chain(ch.id).strength == 7, "delta 只许 ±1"
        assert KarmaChainEngine.nudge_strength("不存在的链", delta=1, now=now) is False
    finally:
        _cleanup(player, npc)


def test_nudge_only_called_by_drama_engine():
    """§5.3：nudge 只许 DramaEngine 调用（调用面静态断言）。"""
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for base in ("core", "server"):
        for f in (root / base).rglob("*.py"):
            if f.name in ("karma_chains.py", "npc_proactive.py"):
                continue
            txt = f.read_text(encoding="utf-8", errors="ignore")
            if "nudge_ferment" in txt or "nudge_strength" in txt:
                offenders.append(str(f))
    assert offenders == [], f"nudge 调用面越界：{offenders}"


# ================= RM-01~RM-04 传闻写入口 =================

def test_rm01_breakthrough_rumor_and_pick_and_lore():
    now = time.time()
    player = _player("破境客")
    npc = _npc("听闻翁")
    marker = f"金丹{_tag()}"  # 唯一境界标记，避共享传闻池旧条目串扰
    try:
        # 首调新增、后 7 调去重只 +heat：heat=8 稳居池首（共享池跨轮旧条目
        # 各自 heat 有限，lore 的 _rumor_bits 只取 top-2，须以热度确保命中）
        for _ in range(8):
            rumors.note_breakthrough(player.name, marker, LOC)
        hits = _rumor_find(marker, tag="breakthrough")
        assert len(hits) == 1 and abs(float(hits[0]["truth"]) - 1.0) < 1e-9
        assert player.name in hits[0]["text"]
        assert int(hits[0]["heat"]) >= 8, "重复写入只 +heat（_note_once 去重）"
        picked = rumors.pick_for_npc(12)
        assert any(marker in (r.get("text") or "") for r in picked), \
            "pick_for_npc 函数级须可命中"
        from core.lorebook import lore_prompt_block

        block = lore_prompt_block(player, npc, "")
        assert marker in block, "lore_prompt_block 接线级须含突破传闻"
    finally:
        _cleanup(player, npc)


def test_rm02_chain_resolved_rumor_single_point_both_paths():
    now = time.time()
    # 惰性 advance 路
    p1 = _player("了链客")
    n1 = _npc("了链翁")
    _chain(p1, n1, kind="en", polarity=1, status="fermenting", now=now,
           mature_days=-1.0)
    # tick 路
    p2 = _player("了链客二")
    n2 = _npc("了链翁二")
    _chain(p2, n2, kind="en", polarity=1, status="fermenting", now=now,
           mature_days=-1.0)
    try:
        KarmaChainEngine.advance_for(p1, now)
        KarmaChainEngine.advance_for(p1, now)  # 连调不得重复
        KarmaChainEngine.tick_world(now)
        for pl in (p1, p2):
            hits = _rumor_find(pl.name, tag="chain")
            assert len(hits) == 1, f"{pl.name} 了结传闻须恰一条"
            assert abs(float(hits[0]["truth"]) - 0.9) < 1e-9
    finally:
        _cleanup(p1, n1, p2, n2)


def test_rm03_arc_participation_rumors():
    from core.world_arc import _settle_climax

    names = [f"弧客{_tag()}{i}" for i in range(4)]
    arc = {
        "kind": "omen_arc", "title": f"试弧{_tag()}", "location": LOC,
        "effects": {}, "log": [], "stage": "escalate", "status": "active",
        "participants": [
            {"who": names[0], "choice": "应劫"},
            {"who": names[1], "choice": "避祸"},
            {"who": names[2], "choice": "应劫"},
            {"who": names[3], "choice": "应劫"},
        ],
    }
    _settle_climax(arc, now=time.time())
    for nm in names[:3]:
        hits = _rumor_find(nm, tag="arc")
        assert hits and abs(float(hits[0]["truth"]) - 0.85) < 1e-9
    assert _rumor_find(names[1], tag="arc")[0]["text"].find("避祸") >= 0
    assert _rumor_find(names[3], tag="arc") == [], "前 3 名之外不写参与传闻"


def test_rm04_existing_note_entries_unchanged():
    t = _tag()
    rumors.note_kill(f"斩者{t}", f"殁者{t}", LOC)
    rumors.note_trade(f"买家{t}", f"卖家{t}", LOC)
    rumors.note_auction(f"得主{t}", f"宝物{t}", 99)
    rumors.note_collusion(f"甲{t}", f"乙{t}", "密谈", LOC)
    rumors.note_apocalypse(987654)
    pool = {r["text"]: r for r in rumors.list_rumors(30)}
    kill = [r for txt, r in pool.items() if f"斩者{t}" in txt]
    trade = [r for txt, r in pool.items() if f"买家{t}" in txt]
    auc = [r for txt, r in pool.items() if f"得主{t}" in txt]
    col = [r for txt, r in pool.items() if f"甲{t}" in txt]
    apo = [r for txt, r in pool.items() if "987654" in txt]
    assert kill and abs(kill[0]["truth"] - 0.95) < 1e-9
    assert trade and abs(trade[0]["truth"] - 0.85) < 1e-9
    assert auc and abs(auc[0]["truth"] - 0.9) < 1e-9
    assert col and abs(col[0]["truth"] - 0.65) < 1e-9
    assert apo and abs(apo[0]["truth"] - 1.0) < 1e-9


def test_rm_note_avoid_fight_entry():
    t = _tag()
    rumors.note_avoid_fight(f"避者{t}", f"衅者{t}")
    hits = _rumor_find(f"避者{t}", tag="avoid")
    assert hits and abs(float(hits[0]["truth"]) - 0.85) < 1e-9
    assert "避而不战" in hits[0]["text"]


def test_dr08_pending_drama_relisted_in_entry_without_proactive():
    """截图验收问题 1 销账（briefing ⑤.6）：已生成未回应的戏剧是持久
    状态——allow_proactive=False 的 briefing 刷新版 entry 也必须列出
    待回应项，且与登录版不重复。"""
    from core.npc_proactive import DramaEngine
    from core.briefing import build_entry

    now = time.time()
    player = _player("常驻客")
    npc = _npc("常驻翁")
    _set_att(npc, player.id, -50)
    try:
        evs = DramaEngine.evaluate(player, trigger="travel", now=now)
        assert len(evs) == 1
        dr_id = evs[0]["id"]
        entry = build_entry(player, since=0, allow_proactive=False, now=now)
        items = [q for q in entry["queue"]
                 if q.get("kind") == "drama" and q.get("ref_id") == dr_id]
        assert len(items) == 1, "待回应戏剧未在刷新版 entry 中常驻列出"
        entry2 = build_entry(player, since=0, allow_proactive=True, now=now)
        items2 = [q for q in entry2["queue"]
                  if q.get("kind") == "drama" and q.get("ref_id") == dr_id]
        assert len(items2) == 1, "待回应戏剧在登录版 entry 中重复列出"
    finally:
        _cleanup(player, npc)
