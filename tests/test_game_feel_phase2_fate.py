"""game-feel-phase2 线一后端验收（Spec game-feel-phase2）。

覆盖：§2 S4-01~S4-05（幂等键收紧）、§3 FT-*（命途主线）、
§4 VD-*（世仇）、§7 EP-*（评语润色）、§8 UI-* 后端侧。
播种口径沿一期：唯一 uid 后缀 + WorldClock 建角，rng 注入可复算。
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")
os.environ.setdefault("USE_CCSWITCH", "0")

from config import SECONDS_PER_GAME_DAY
from core.clock import WorldClock
from core.goals import GoalEngine
from storage.db import CharacterRepository, init_db

init_db()

LOC = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name="试炼者", uid_prefix="gf2", location=LOC, save=False):
    c = WorldClock.create_new_character(f"{uid_prefix}_{name}_{_tag()}", f"{name}{_tag()}")
    c.location = location
    if save:
        CharacterRepository.save(c)
        return CharacterRepository.get_by_id(c.id)
    return c


def _npc(name="试炼NPC", tier=1, location=LOC, sect=""):
    c = WorldClock.create_new_character(f"npc_gf2_{name}_{_tag()}", f"{name}{_tag()}")
    c.realm.tier = tier
    c.location = location
    c.sect = sect
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


# ================= §2 S-4 幂等键收紧 =================

def test_s4_01_instance_key_allows_parallel_and_dedups_same_instance():
    char = _char("S4甲")
    chk = {"kind": "chain_resolved", "ref": "npc_x"}
    g1 = GoalEngine.add_checked_goal(
        char, source="origin", title="章一", detail="d", check=dict(chk),
        instance="ft_abc:c1")
    g2 = GoalEngine.add_checked_goal(
        char, source="origin", title="章二", detail="d", check=dict(chk),
        instance="ft_abc:c2")
    assert g1["id"] != g2["id"]
    assert g1["status"] == g2["status"] == "active"
    assert g1["check"]["instance"] == "ft_abc:c1"
    n_before = len(char.goals)
    g1b = GoalEngine.add_checked_goal(
        char, source="origin", title="章一重挂", detail="d", check=dict(chk),
        instance="ft_abc:c1")
    assert g1b["id"] == g1["id"], "同 instance 重挂须命中幂等返回既有项"
    assert len(char.goals) == n_before


def test_s4_02_legacy_no_instance_compat():
    char = _char("S4乙")
    legacy_goal = {
        "id": "g_origin_legacy1", "source": "origin", "title": "旧目标",
        "detail": "d", "status": "active", "progress": 0,
        "created_at": time.time(), "tier": "short",
        "check": {"kind": "stones_at_least", "amount": 100}, "deadline_at": 0.0,
    }
    char.goals = [legacy_goal]
    # 无 instance 重挂 → 一期行为：返回既有项不新增
    again = GoalEngine.add_checked_goal(
        char, source="origin", title="新", detail="d",
        check={"kind": "stones_at_least", "amount": 100})
    assert again["id"] == "g_origin_legacy1"
    assert len(char.goals) == 1
    # 带 instance 重挂 → 新增成功且旧项仍 active
    new = GoalEngine.add_checked_goal(
        char, source="origin", title="新二", detail="d",
        check={"kind": "stones_at_least", "amount": 100},
        instance="ft_xyz:c1")
    assert new["id"] != "g_origin_legacy1"
    assert len(char.goals) == 2
    assert char.goals[0]["status"] == "active"


def test_s4_03_missing_ref_no_collision_with_instance():
    char = _char("S4丙")
    chk = {"kind": "npc_attitude_at_least", "npc_id": "npc_1", "value": 10}  # 无 ref 键
    g1 = GoalEngine.add_checked_goal(
        char, source="origin", title="甲", detail="d", check=dict(chk),
        instance="ft_a:c1")
    g2 = GoalEngine.add_checked_goal(
        char, source="origin", title="乙", detail="d", check=dict(chk),
        instance="ft_a:c2")
    assert g1["id"] != g2["id"], "无 ref 目标不得因 ref=None 互撞"
    # 两条均无 ref 且均无 instance → 仍互斥（一期行为）
    char2 = _char("S4丁")
    h1 = GoalEngine.add_checked_goal(
        char2, source="origin", title="甲", detail="d", check=dict(chk))
    h2 = GoalEngine.add_checked_goal(
        char2, source="origin", title="乙", detail="d", check=dict(chk))
    assert h1["id"] == h2["id"] and len(char2.goals) == 1


def test_s4_05_evaluation_does_not_cross_instances():
    char = _char("S4戊")
    char.spirit_stones = 0
    t0 = time.time()
    chk = {"kind": "stones_at_least", "amount": 10 ** 9}
    g1 = GoalEngine.add_checked_goal(
        char, source="origin", title="短限", detail="d", check=dict(chk),
        deadline_days=1, instance="ft_e:c1", now=t0)
    g2 = GoalEngine.add_checked_goal(
        char, source="origin", title="长限", detail="d", check=dict(chk),
        deadline_days=10, instance="ft_e:c2", now=t0)
    flipped = GoalEngine.evaluate_checked_goals(
        char, t0 + 2 * SECONDS_PER_GAME_DAY)
    assert [g["id"] for g in flipped] == [g1["id"]]
    assert g1["status"] == "failed"
    assert g2["status"] == "active", "instance 不参与求值，到期只翻转到期者"


# ================= §3 fate_threads 命途主线 =================

import random as _random

from core.fate_thread import FateThread, FateThreadEngine
from core.legacy import LegacyAccount, LifeTrace, ShadowEntry
from storage.db import FateThreadRepository


def _seeded_roster():
    from core.npc_roster import seed_roster

    seed_roster()
    return {c.user_id: c for c in CharacterRepository.list_all_alive()
            if str(c.user_id).startswith("npc_")}


def _origin_char(name="命途客", account=None, seed=7):
    """建角 + 生成出身（须先 seed_roster），返回 (char, account)。"""
    _seeded_roster()
    char = _char(name, save=True)
    acc = account or LegacyAccount(user_id=char.user_id)
    from core.origin import OriginEngine

    OriginEngine.generate_for_new_life(
        char, acc, rng=_random.Random(seed), now=time.time())
    CharacterRepository.save(char)
    return CharacterRepository.get_by_id(char.id), acc


def _manual_origin_char(name, npc, story_kind="幼年奇遇"):
    """手工出身（old_story 绑 npc、无关系），种子可控走 P5。"""
    char = _char(name, save=True)
    char.origin = {
        "family": "寒门农家", "family_text": "山野寒门之子",
        "signature": f"寒门农家|{story_kind}|{npc.id}|nodebt",
        "birthplace": LOC, "stones_final": 150, "debt": None,
        "relations": [],
        "old_story": {"kind": story_kind, "npc_id": npc.id,
                      "item_ref": "", "summary": "旧事一桩"},
        "path_gates": [], "strength_score": 0,
        "short_goal_id": "", "fate_goal_id": "", "fate_text": "",
        "generated_at": time.time(), "life_no": 1,
    }
    CharacterRepository.save(char)
    return CharacterRepository.get_by_id(char.id)


def test_ft01_new_char_thread_built_and_visible():
    char, acc = _origin_char("FT一")
    thread = FateThreadEngine.ensure_thread(char, acc)
    assert thread is not None and thread.status == "active"
    rows = FateThreadRepository.list_by_player(char.id)
    assert len(rows) == 1
    assert len(thread.chapters) == 6
    assert thread.chapters[0]["status"] == "active"
    assert all(ch["status"] == "locked" for ch in thread.chapters[1:])
    sd = FateThreadEngine.thread_status_dict(char)
    assert sd["title"] == thread.title
    assert sd["chapters"][0]["goal_text"]
    assert sd["final_proposition"]["text"]


def test_ft02_seed_shadow_beats_blood_feud():
    roster = _seeded_roster()
    npc_shadow = roster["npc_qy_08"]
    npc_chain = roster["npc_qy_07"]
    char = _char("FT二影", save=True)
    # 本世 xue 链（P3 候选）
    from core.karma_chains import KarmaChain
    from storage.db import KarmaChainRepository

    KarmaChainRepository.save(KarmaChain(
        id=f"kc_ft02_{_tag()}", kind="xue", polarity=-1,
        player_id=char.id, player_name=char.name,
        counterparty_id=npc_chain.id, counterparty_name=npc_chain.name,
        status="fermenting", created_at=time.time()))
    acc = LegacyAccount(user_id=char.user_id)
    acc.traces = [LifeTrace(
        life_no=1, character_id="old_ft02", name="前人", realm="练气",
        cause="寿尽",
        shadow=[ShadowEntry(npc_id=npc_shadow.id, npc_name=npc_shadow.name,
                            value=-80)])]
    thread = FateThreadEngine.ensure_thread(char, acc)
    assert thread.seed_source == "karma_shadow", "影子（P2）须优先于血仇（P3）"
    assert thread.antagonist_npc_id == npc_shadow.id


def test_ft02_seed_blood_feud_and_origin_fallback():
    roster = _seeded_roster()
    npc_chain = roster["npc_qy_07"]
    char = _char("FT二血", save=True)
    from core.karma_chains import KarmaChain
    from storage.db import KarmaChainRepository

    KarmaChainRepository.save(KarmaChain(
        id=f"kc_ft02b_{_tag()}", kind="xue", polarity=-1,
        player_id=char.id, player_name=char.name,
        counterparty_id=npc_chain.id, counterparty_name=npc_chain.name,
        status="latent", created_at=time.time()))
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    assert thread.seed_source == "blood_feud"
    assert thread.seed_ref.startswith("kc_ft02b_")
    # P5 出身兜底
    npc = _npc("FT二出身目标")
    char2 = _manual_origin_char("FT二出身", npc)
    t2 = FateThreadEngine.ensure_thread(char2, LegacyAccount(user_id=char2.user_id))
    assert t2.seed_source == "origin"
    assert t2.patron_npc_id == npc.id


def test_ft02_seed_sect_via_directive(monkeypatch):
    char = _char("FT二宗", save=True)
    char.sect = "青云宗"
    CharacterRepository.save(char)
    char = CharacterRepository.get_by_id(char.id)
    monkeypatch.setattr(
        "core.world_director.active_directives",
        lambda *a, **k: [{
            "id": "dir_ft02", "type": "sect_tension",
            "effects": {"sect_a": "青云宗", "sect_b": "万剑仙门"},
            "updated_at": time.time(),
        }])
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    assert thread.seed_source == "sect"
    assert thread.seed_ref == "dir_ft02"


def test_ft02_unfinished_two_homes():
    roster = _seeded_roster()
    npc = roster["npc_qy_08"]
    # 可重绑（foe 在世）→ 占种子位，命题另行定盘
    char = _manual_origin_char("FT二未竟", npc)
    acc = LegacyAccount(user_id=char.user_id)
    acc.traces = [LifeTrace(
        life_no=1, character_id="old_ft02u", name="前人", realm="练气",
        cause="寿尽",
        unfinished_prop={
            "kind": "foe_reckoning", "text": "未竟测试文案·讨个说法",
            "check": {"kind": "npc_attitude_at_least", "npc_id": npc.id,
                      "value": 0}})]
    thread = FateThreadEngine.ensure_thread(char, acc)
    assert thread.seed_source == "unfinished"
    assert thread.final_proposition["text"] != "未竟测试文案·讨个说法", \
        "未竟占种子位时命题不得双挂同一未竟"
    # 不可重绑（debt_clear 而本世无债）→ 种子顺延，不占种子位
    char2 = _manual_origin_char("FT二未竟乙", npc)
    acc2 = LegacyAccount(user_id=char2.user_id)
    acc2.traces = [LifeTrace(
        life_no=1, character_id="old_ft02v", name="前人", realm="练气",
        cause="寿尽",
        unfinished_prop={
            "kind": "debt_clear", "text": "未竟测试文案·还债",
            "check": {"kind": "promise_settled", "ref": "no_such_promise"}})]
    t2 = FateThreadEngine.ensure_thread(char2, acc2)
    assert t2.seed_source != "unfinished"


# --- SUPERSEDED 契约记录（不得静默改写，留痕）---
# 旧测试名：test_ft03_chapter_done_via_visit_and_next_activated
# 旧语义：「到访即成」——visit_location 章只要 ref ∈ visited 且目标 NPC 在场即 done。
# 取代依据：Martinez 2026-11-10 亲口拍板路线 (b)——带 npc_id 的「去见某人」类章节
# 必须真正与目标 NPC 交谈一轮才完成。见 docs/compose/spec/playability-block1.md
# 「决策记录」与 B1-4 修订、game-feel-phase2.md §3.5 修订注记。
# 新测试名如实反映新语义：test_ft03_chapter_done_via_talk_and_next_activated。
def test_ft03_chapter_done_via_talk_and_next_activated():
    npc = _npc("FT三向导", location="万剑仙门峰")
    char = _manual_origin_char("FT三", npc)
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    assert thread.chapters[0]["check"]["kind"] == "visit_location"
    # 复测再修（B1-4）：到访 ≠ 完成——须先走到向导面前，再与之交谈一轮
    char.location = "万剑仙门峰"
    CharacterRepository.save(char)
    res = FateThreadEngine.record_visit(char, "万剑仙门峰")
    th = res["thread"]
    assert th.chapters[0]["status"] == "active"
    from core import npc_chat

    opened = npc_chat.open_session(CharacterRepository.get_by_id(char.id), npc)
    assert opened.get("success") is True, opened
    said = npc_chat.player_say(CharacterRepository.get_by_id(char.id), "幸会，道友")
    assert said.get("success") is True, said
    npc_chat.apply_npc_reply(char.id, "回礼，道友请坐。", True)
    # 注意：evaluate_for 原地改传入的 char（章节派生新目标挂在其 goals 上），
    # 须传内存中的 char 而非新取对象，否则章节 1 的目标只落在丢弃对象上；
    # 线已由 evaluate_for 回存，char 须调用方回存。
    res3 = FateThreadEngine.evaluate_for(char)
    if res3.get("changed"):
        CharacterRepository.save(char)
    th = res3["thread"]
    assert th.chapters[0]["status"] == "done"
    assert th.chapters[1]["status"] == "active"
    inst = (th.chapters[1]["check"] or {}).get("instance")
    assert inst == f"{th.id}:c1"
    goal = next(g for g in char.goals if g.get("id") == th.chapters[1]["goal_id"])
    assert goal["source"] == "thread"
    assert (goal.get("check") or {}).get("instance") == inst


def test_ft03b_talked_evidence_survives_session_switch():
    """M4 回归：谈 A（未挂断/未落摘要）后切去与 B 开会话，单槽被覆盖，
    A 的交谈证据不得消失——A 章求值仍可成（旧实现只认单槽+摘要会误判）。"""
    npc_a = _npc("FT三乙向导甲")
    npc_b = _npc("FT三乙向导乙")
    char = _manual_origin_char("FT三乙", npc_a)
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    assert thread.chapters[0]["check"]["kind"] == "visit_location"
    assert thread.chapters[0]["check"]["npc_id"] == npc_a.id
    char.location = LOC
    CharacterRepository.save(char)
    FateThreadEngine.record_visit(char, LOC)
    from core import npc_chat

    # 与 A 谈一轮（不挂断、不落摘要）
    opened = npc_chat.open_session(CharacterRepository.get_by_id(char.id), npc_a)
    assert opened.get("success") is True, opened
    said = npc_chat.player_say(CharacterRepository.get_by_id(char.id), "幸会，道友")
    assert said.get("success") is True, said
    npc_chat.apply_npc_reply(char.id, "回礼，道友请坐。", True)
    assert npc_chat.has_talked_pair(char.id, npc_a.id) is True
    # 切去与 B 开会话：单槽被 B 覆盖，A 的会话记录不再是当前槽
    opened_b = npc_chat.open_session(CharacterRepository.get_by_id(char.id), npc_b)
    assert opened_b.get("success") is True, opened_b
    said_b = npc_chat.player_say(CharacterRepository.get_by_id(char.id), "道友安好")
    assert said_b.get("success") is True, said_b
    npc_chat.apply_npc_reply(char.id, "安好，请坐。", True)
    slot = (npc_chat._load_all() or {}).get(char.id) or {}
    assert slot.get("npc_id") == npc_b.id, "前置条件：单槽已切到 B"
    # 证据仍在：按对标记命中，求值 A 章可成
    char_now = CharacterRepository.get_by_id(char.id)
    assert GoalEngine._talked_with_npc(char_now, npc_a) is True
    res = FateThreadEngine.evaluate_for(char_now)
    if res.get("changed"):
        CharacterRepository.save(char_now)
    th = res["thread"]
    assert th.chapters[0]["status"] == "done", th.chapters[0]
    assert th.chapters[1]["status"] == "active"


def test_ft04_death_seal_and_next_life_seed():
    from core.legacy import LegacyEngine

    npc = _npc("FT四向导")
    char = _manual_origin_char("FT四", npc)
    acc = LegacyAccount(user_id=char.user_id)
    thread = FateThreadEngine.ensure_thread(char, acc)
    assert thread.status == "active"
    res = LegacyEngine.settle_death(acc, char, death_cause="寿尽坐化")
    trace = res["trace"]
    assert trace.fate_summary.startswith("命途「")
    sealed = FateThreadRepository.get_by_id(thread.id)
    assert sealed.status in ("completed", "broken", "inherited")
    assert sealed.unfinished_note or sealed.status == "completed"
    if sealed.status != "completed":
        assert trace.unfinished_prop.get("text") == sealed.unfinished_note
    # 转世新角：未竟（stand_firm 映射）可重绑 → 新线种子 unfinished
    char2 = _manual_origin_char("FT四世", npc)
    acc.total_lives = 1
    t2 = FateThreadEngine.ensure_thread(char2, acc)
    assert t2.seed_source == "unfinished"


def test_ft05_thread_module_produces_no_numbers():
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent.joinpath(
        "core/fate_thread.py").read_text(encoding="utf-8")
    for banned in ("spirit_stones", "deduct_currency", "add_lifespan",
                   "wallet", "add_exp", "sin_value", "merit_value"):
        assert banned not in src, f"fate_thread 不得触碰数值入口：{banned}"
    # 对照：evaluate 前后角色数值逐项不变（active 与 shelved 两组同口径）
    for shelve in (False, True):
        npc = _npc("FT五向导")
        char = _manual_origin_char("FT五", npc)
        FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
        if shelve:
            FateThreadEngine.shelve_thread(char)
        before = (char.spirit_stones, char.realm.current_exp,
                  char.karma.sin_value, char.karma.merit_value,
                  char.karma.dao_heart)
        FateThreadEngine.evaluate_for(char, time.time())
        after = (char.spirit_stones, char.realm.current_exp,
                 char.karma.sin_value, char.karma.merit_value,
                 char.karma.dao_heart)
        assert before == after


# SUPERSEDED 注记（ft06）：旧断言要点——visit_location 仅凭 visited 命中 + NPC 在场即 done；
# 已按新契约改写（须交谈一轮）。取代依据：Martinez 2026-11-10 路线 (b) 决策，见 playability-block1.md 决策记录。
def test_ft06_new_check_kinds_and_climax_order():
    from core.karma_chains import KarmaChain
    from core.promises import Promise, PromiseStatus
    from storage.db import KarmaChainRepository, PromiseRepository

    npc = _npc("FT六人")
    char = _char("FT六", save=True)
    # visit_location：visited 命中 + NPC 在场
    thread = FateThread(
        id=f"ft_manual_{_tag()}", player_id=char.id, user_id=char.user_id,
        status="active", visited=[LOC], created_at=time.time())
    FateThreadRepository.save(thread)
    g = GoalEngine.add_checked_goal(
        char, source="thread", title="访", detail="d",
        check={"kind": "visit_location", "ref": LOC, "npc_id": npc.id},
        instance=f"{thread.id}:c0")
    # 复测再修（B1-4）：带 npc_id 的 visit 章须与目标交谈一轮才成
    from core import npc_chat

    _opened = npc_chat.open_session(char, npc)
    assert _opened.get("success") is True, _opened
    _said = npc_chat.player_say(CharacterRepository.get_by_id(char.id), "幸会，道友")
    assert _said.get("success") is True, _said
    npc_chat.apply_npc_reply(char.id, "回礼，道友请坐。", True)
    GoalEngine.evaluate_checked_goals(char, time.time())
    assert g["status"] == "done"
    g2 = GoalEngine.add_checked_goal(
        char, source="thread", title="访负", detail="d",
        check={"kind": "visit_location", "ref": "万剑仙门峰", "npc_id": npc.id},
        instance=f"{thread.id}:c1")
    GoalEngine.evaluate_checked_goals(char, time.time())
    assert g2["status"] == "active"
    # promise_kept_count 正/负例
    PromiseRepository.save(Promise(
        promiser_id=char.id, promiser_name=char.name,
        promisee_id=npc.id, promisee_name=npc.name, promisee_is_npc=True,
        kind="gift", desc="诺", status=PromiseStatus.KEPT,
        created_at=time.time()))
    g3 = GoalEngine.add_checked_goal(
        char, source="thread", title="诺一", detail="d",
        check={"kind": "promise_kept_count", "count": 1},
        instance=f"{thread.id}:c2")
    g4 = GoalEngine.add_checked_goal(
        char, source="thread", title="诺二", detail="d",
        check={"kind": "promise_kept_count", "count": 2},
        instance=f"{thread.id}:c3")
    GoalEngine.evaluate_checked_goals(char, time.time())
    assert g3["status"] == "done" and g4["status"] == "active"
    # chain_resolved 正/负例
    KarmaChainRepository.save(KarmaChain(
        id=f"kc_ft06_{_tag()}", kind="en", polarity=1,
        player_id=char.id, player_name=char.name,
        counterparty_id=npc.id, counterparty_name=npc.name,
        status="resolved", created_at=time.time()))
    g5 = GoalEngine.add_checked_goal(
        char, source="thread", title="链", detail="d",
        check={"kind": "chain_resolved", "npc_id": npc.id, "outcome": "any"},
        instance=f"{thread.id}:c4")
    GoalEngine.evaluate_checked_goals(char, time.time())
    assert g5["status"] == "done"
    # thread_climax：idx4 done 后命题才翻（顺序断言）
    th2 = FateThread(
        id=f"ft_climax_{_tag()}", player_id=char.id, user_id=char.user_id,
        status="active", created_at=time.time(),
        chapters=[{"idx": i, "status": "locked"} for i in range(6)])
    FateThreadRepository.save(th2)
    g6 = GoalEngine.add_checked_goal(
        char, source="fate", title="命题", detail="d",
        check={"kind": "thread_climax", "ref": th2.id})
    GoalEngine.evaluate_checked_goals(char, time.time())
    assert g6["status"] == "active", "idx4 未 done 时 thread_climax 须 pending"
    th2.chapters[4]["status"] = "done"
    FateThreadRepository.save(th2)
    GoalEngine.evaluate_checked_goals(char, time.time())
    assert g6["status"] == "done"


def test_ft07_window_reroute():
    npc = _npc("FT七向导")
    char = _manual_origin_char("FT七", npc)
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    goal = next(g for g in char.goals if g.get("id") == thread.chapters[0]["goal_id"])
    goal["deadline_at"] = time.time() - 10
    res = FateThreadEngine.evaluate_for(char, time.time())
    th = res["thread"]
    assert th.chapters[0]["status"] == "failed"
    assert th.chapters[1]["status"] == "active"
    assert "改道" in (th.chapters[1].get("summary") or "")
    assert th.unfinished_note
    assert th.status == "active", "单章失败主线不 broken"


def test_ft08_shelve_and_resume_deadline_shift():
    npc = _npc("FT八向导")
    char = _manual_origin_char("FT八", npc)
    t0 = time.time()
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id), now=t0)
    goal = next(g for g in char.goals if g.get("id") == thread.chapters[0]["goal_id"])
    old_deadline = float(goal["deadline_at"])
    assert old_deadline > t0
    assert FateThreadEngine.shelve_thread(char, now=t0 + 10)["success"]
    # 越过原 deadline 求值：章节不 failed（线级 + goals 求值器双口径）
    res = FateThreadEngine.evaluate_for(char, old_deadline + 100)
    assert res["thread"].chapters[0]["status"] == "active"
    GoalEngine.evaluate_checked_goals(char, old_deadline + 100)
    assert goal["status"] == "active"
    out = FateThreadEngine.resume_thread(char, now=t0 + 10 + 500)
    assert out["success"]
    assert abs(float(goal["deadline_at"]) - (old_deadline + 500)) < 1.0


def test_ft08b_shelved_thread_skips_e4_attitude_eval():
    """评审 M-1：搁置中的主线，其 npc_attitude_at_least 章节目标在 E4
    （evaluate_attitude_goals）同样跳过求值；恢复后正常翻转。"""
    from core.npc_mind import shift_attitude

    npc = _npc("M一向导")
    char = _manual_origin_char("M一", npc)
    thread = FateThreadEngine.ensure_thread(
        char, LegacyAccount(user_id=char.user_id))
    goal = {
        "id": "m1_goal", "source": "thread", "status": "active",
        "title": "M1 态度章节",
        "check": {"kind": "npc_attitude_at_least", "npc_id": npc.id,
                  "value": 10, "instance": f"{thread.id}:c9"},
        "deadline_at": 0,
    }
    char.goals = list(char.goals or []) + [goal]
    CharacterRepository.save(char)
    shift_attitude(npc, char.id, 20, "M1 测试")
    CharacterRepository.save(npc)
    assert FateThreadEngine.shelve_thread(char)["success"]
    flipped = GoalEngine.evaluate_attitude_goals(char)
    assert all(g.get("id") != "m1_goal" for g in flipped), \
        "搁置期 E4 不得翻转主线章节目标"
    assert goal["status"] == "active"
    assert FateThreadEngine.resume_thread(char)["success"]
    flipped = GoalEngine.evaluate_attitude_goals(char)
    assert any(g.get("id") == "m1_goal" for g in flipped)
    assert goal["status"] == "done"


def test_ft09_ensure_idempotent_and_origin_copy():
    char, acc = _origin_char("FT九")
    t1 = FateThreadEngine.ensure_thread(char, acc)
    t2 = FateThreadEngine.ensure_thread(char, acc)
    assert t1.id == t2.id
    assert len(FateThreadRepository.list_by_player(char.id)) == 1
    assert t1.origin == (char.origin or {})
    # 老角色（origin 空）：thread.origin == {}
    char2 = _char("FT九老", save=True)
    t3 = FateThreadEngine.ensure_thread(char2, LegacyAccount(user_id=char2.user_id))
    assert t3.origin == {}


def test_ft10_signature_antirepeat():
    npc = _npc("FT十向导")
    char1 = _manual_origin_char("FT十甲", npc)
    t1 = FateThreadEngine.ensure_thread(char1, LegacyAccount(user_id=char1.user_id))
    char2 = _manual_origin_char("FT十乙", npc)
    char2.user_id = char1.user_id  # 同账户第二世（不同角色 id）
    t2 = FateThreadEngine.ensure_thread(char2, LegacyAccount(user_id=char1.user_id))
    kinds1 = [c["kind"] for c in t1.chapters]
    kinds2 = [c["kind"] for c in t2.chapters]
    assert kinds1 != kinds2 or t2.signature_forced, \
        "同账户同种子同对手须轮换 kind 序列或诚实标记 signature_forced"


def test_ft11_validate_seed_hint():
    roster = _seeded_roster()
    uid = "npc_qy_01"
    out = FateThreadEngine.validate_seed_hint({
        "seed_source": "sect", "npc_id": uid, "location": LOC,
        "chapter_kind": "visit", "stones": 999, "exp": 5})
    assert out == {"seed_source": "sect", "npc_id": uid,
                   "location": LOC, "chapter_kind": "visit"}
    assert FateThreadEngine.validate_seed_hint({"npc_id": "npc_no_such"}) is None
    assert FateThreadEngine.validate_seed_hint({"location": "不存在之地"}) is None
    assert FateThreadEngine.validate_seed_hint({"seed_source": "bogus"}) is None
    assert roster  # 花名册已播种（npc_id 在册判定前提）


def test_ft12_no_tick_scan():
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent.joinpath(
        "core/fate_thread.py").read_text(encoding="utf-8")
    for banned in ("Timer(", "sleep(", "while True", "schedule"):
        assert banned not in src
    # 负例：未经任何 T 点，时间流逝不改变章节状态
    npc = _npc("FT十二向导")
    char = _manual_origin_char("FT十二", npc)
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    again = FateThreadRepository.get_by_id(thread.id)
    assert again.chapters[0]["status"] == "active"
    assert again.current_chapter == 0


# ================= §4 世仇 =================

def _trace_with(old_id, shadow=None):
    return LifeTrace(
        life_no=1, character_id=old_id, name="前人", realm="练气",
        cause="寿尽", shadow=shadow or [])


def _vd_account(old_id, shadow=None):
    acc = LegacyAccount(user_id=f"vd_user_{_tag()}")
    acc.traces = [_trace_with(old_id, shadow)]
    return acc


def _save_xue_chain(old_id, npc, status="resolved"):
    from core.karma_chains import KarmaChain
    from storage.db import KarmaChainRepository

    cid = f"kc_vd_{_tag()}"
    KarmaChainRepository.save(KarmaChain(
        id=cid, kind="xue", polarity=-1, player_id=old_id,
        player_name="前人", counterparty_id=npc.id,
        counterparty_name=npc.name, status=status, created_at=time.time()))
    return cid


def test_vd01_three_sources():
    roster = _seeded_roster()
    low = roster["npc_qy_08"]  # tier1 青云宗
    # 来源 1：上世 xue 链
    old1 = f"old_vd1_{_tag()}"
    _save_xue_chain(old1, low)
    acc = _vd_account(old1)
    new_char = _char("VD一甲", save=True)
    got = FateThreadEngine.select_vendetta(acc, new_char)
    assert got and got["npc_id"] == low.id
    # 来源 2：KarmaLink 仇孤儿行
    from core.bounty import KarmaLink
    from storage.db import KarmaLinkRepository

    old2 = f"old_vd2_{_tag()}"
    KarmaLinkRepository.save(KarmaLink(
        a_id=old2, a_name="前人", b_id=low.id, b_name=low.name,
        link_type="仇", strength=5, created_at=time.time()))
    acc2 = _vd_account(old2)
    got2 = FateThreadEngine.select_vendetta(acc2, _char("VD一乙", save=True))
    assert got2 and got2["npc_id"] == low.id
    # 来源 3：负值影子
    old3 = f"old_vd3_{_tag()}"
    acc3 = _vd_account(old3, shadow=[ShadowEntry(
        npc_id=low.id, npc_name=low.name, value=-60)])
    got3 = FateThreadEngine.select_vendetta(acc3, _char("VD一丙", save=True))
    assert got3 and got3["npc_id"] == low.id


def test_vd01_vd02_planting_three_way_consistency():
    roster = _seeded_roster()
    low = roster["npc_qy_08"]
    old = f"old_vdp_{_tag()}"
    _save_xue_chain(old, low)
    acc = _vd_account(old)
    acc.user_id = f"vd_plant_{_tag()}"
    new_char = _char("VD植入", save=True)
    acc.user_id = new_char.user_id
    vendetta = FateThreadEngine.select_vendetta(acc, new_char)
    assert vendetta and vendetta["npc_id"] == low.id
    from core.origin import OriginEngine

    pkg = OriginEngine.generate_for_new_life(
        new_char, acc, rng=_random.Random(11), vendetta=vendetta)
    CharacterRepository.save(new_char)  # generate 不落盘 char，调用方统一 save
    rel = next((r for r in pkg["relations"] if r.get("vendetta")), None)
    assert rel is not None and rel["npc_id"] == low.id
    # 三处一致：态度账 ∈ [-45,-30] / KarmaLink 仇边对端 / thread.seed_ref
    from core.npc_mind import attitude_toward
    from storage.db import KarmaLinkRepository

    npc_now = CharacterRepository.get_by_id(low.id)
    val = attitude_toward(npc_now, new_char.id)["value"]
    assert -45 <= val <= -30, f"世仇态度须在深半区，实际 {val}"
    links = [l for l in KarmaLinkRepository.list_all()
             if l.link_type == "仇" and l.involves(new_char.id)
             and l.involves(low.id)]
    assert links and "世仇" in (links[0].note or "")
    fresh = CharacterRepository.get_by_id(new_char.id)
    thread = FateThreadEngine.ensure_thread(fresh, acc)
    assert thread.seed_source == "vendetta"
    assert thread.seed_ref == low.id


def test_vd03_degrade_dead_and_overtier_and_none():
    roster = _seeded_roster()
    # 仇源已死 → 同门降级（青云宗 tier 升序首位 npc_qy_06）
    dead_npc = _npc("VD三死者", tier=1, sect="青云宗")
    from core.models import CharacterStatus as _CS

    dead_npc.status = _CS.DEAD
    CharacterRepository.save(dead_npc)
    dead_npc = CharacterRepository.get_by_id(dead_npc.id)
    old = f"old_vd3_{_tag()}"
    _save_xue_chain(old, dead_npc)
    acc = _vd_account(old)
    got = FateThreadEngine.select_vendetta(acc, _char("VD三甲", save=True))
    expect = roster["npc_qy_06"]
    assert got and got["npc_id"] == expect.id
    assert got["for_name"] == dead_npc.name
    # 仇源超界（化神 tier5 在世）→ 不植本人，改植同门低阶（npc_wj_06 tier1）
    boss = roster["npc_wj_01"]
    old2 = f"old_vd3b_{_tag()}"
    _save_xue_chain(old2, boss)
    acc2 = _vd_account(old2)
    got2 = FateThreadEngine.select_vendetta(acc2, _char("VD三乙", save=True))
    assert got2 and got2["npc_id"] == roster["npc_wj_06"].id
    assert got2["for_name"] == boss.name
    # 全空 → None + origin 无 vendetta 条目
    acc3 = _vd_account(f"old_vd3c_{_tag()}")
    assert FateThreadEngine.select_vendetta(acc3, _char("VD三丙", save=True)) is None


def test_vd04_bounds_over_batch():
    roster = _seeded_roster()
    low = roster["npc_qy_08"]
    for i in range(50):
        old = f"old_vd4_{i}_{_tag()}"
        _save_xue_chain(old, low)
        acc = _vd_account(old)
        new_char = _char(f"VD四{i}", save=True)
        got = FateThreadEngine.select_vendetta(acc, new_char)
        assert got is not None
        npc = CharacterRepository.get_by_id(got["npc_id"])
        assert npc.realm.tier <= new_char.realm.tier + 1
    # 全量 generate 抽查 3 次：relations ≤4、foe 值域不破
    for i in range(3):
        old = f"old_vd4g_{i}_{_tag()}"
        _save_xue_chain(old, low)
        acc = _vd_account(old)
        new_char = _char(f"VD四生{i}", save=True)
        acc.user_id = new_char.user_id
        vendetta = FateThreadEngine.select_vendetta(acc, new_char)
        from core.origin import OriginEngine

        pkg = OriginEngine.generate_for_new_life(
            new_char, acc, rng=_random.Random(100 + i), vendetta=vendetta)
        assert len(pkg["relations"]) <= 4
        rel = next(r for r in pkg["relations"] if r.get("vendetta"))
        assert -45 <= rel["init_value"] <= -30


def test_vd05_shadow_covered_candidate_not_double_shifted():
    roster = _seeded_roster()
    low = roster["npc_qy_08"]
    old = f"old_vd5_{_tag()}"
    _save_xue_chain(old, low)
    # 影子覆盖同一人（-80 → 施加 -25）
    acc = _vd_account(old, shadow=[ShadowEntry(
        npc_id=low.id, npc_name=low.name, value=-80)])
    new_char = _char("VD五", save=True)
    acc.user_id = new_char.user_id
    got = FateThreadEngine.select_vendetta(acc, new_char)
    assert got and got["npc_id"] != low.id, "覆盖者同人须顺延/降级同门"
    # 全流程：先施加影子，再生成出身——影子 NPC 态度以影子值为准
    from core.inheritance import apply_karma_shadow
    from core.npc_mind import attitude_toward
    from core.origin import OriginEngine

    apply_karma_shadow(acc, new_char, retention=0.4, cap=25)
    npc_now = CharacterRepository.get_by_id(low.id)
    assert attitude_toward(npc_now, new_char.id)["value"] == -25
    OriginEngine.generate_for_new_life(
        new_char, acc, rng=_random.Random(5), vendetta=got)
    npc_now = CharacterRepository.get_by_id(low.id)
    assert attitude_toward(npc_now, new_char.id)["value"] == -25, \
        "origin 不得对影子覆盖者再叠加 shift_attitude"


# ================= §7 评语 AI 润色 =================

def _polish_account(monkeypatch, data=None, exc=None, record=None):
    import ai.router

    acc = LegacyAccount(user_id=f"ep_user_{_tag()}")
    trace = LifeTrace(
        life_no=1, character_id=f"ep_char_{_tag()}", name="前人",
        realm="练气二层", cause="寿尽坐化",
        fate_summary="出身寒门农家，父辈旧债起；终局命题「活过四十载」成；",
        unfinished_prop={"kind": "stand_firm", "text": "未竟",
                         "check": {"kind": "stones_at_least", "value": 1}},
    )
    from core.legacy import LegacyEngine as _LE

    head = "寒门农家出身，父辈旧债缠身。"
    line = "此生虽短，道心未折。"
    tail = _LE._EPITAPH_TAIL[_LE._cause_category("寿尽坐化")]
    trace.epitaph_head = head
    trace.epitaph_line = line
    trace.epitaph_tail = tail
    trace.life_epitaph = head + line + tail
    acc.traces = [trace]

    def fake_invoke(scene, payload, tier=None, **kw):
        if record is not None:
            record.append((scene, payload))
        if exc is not None:
            raise exc
        return {"ok": True, "data": data or {"line": "一生蹉跎，终见天光。"}, "tier_used": "cheap"}

    monkeypatch.setattr(ai.router, "invoke", fake_invoke)
    return acc, trace


def test_ep01_polish_success_replaces_line_only(monkeypatch):
    from core.legacy import LegacyEngine

    acc, trace = _polish_account(monkeypatch)
    old_head, old_tail = trace.epitaph_head, trace.epitaph_tail
    assert LegacyEngine.try_polish_epitaph(acc) is True
    assert trace.epitaph_line == "一生蹉跎，终见天光。"
    assert trace.epitaph_head == old_head and trace.epitaph_tail == old_tail
    assert trace.life_epitaph == old_head + "一生蹉跎，终见天光。" + old_tail
    assert trace.epitaph_polish == "done"


def test_ep02_polish_rejects_numbers_and_failure_keeps_text(monkeypatch):
    from core.legacy import LegacyEngine

    acc, trace = _polish_account(monkeypatch, data={"line": "第3世终成大道。"})
    original = trace.life_epitaph
    assert LegacyEngine.try_polish_epitaph(acc) is False
    assert trace.life_epitaph == original
    assert trace.epitaph_polish == "failed"
    # 异常路径同样逐字保留
    acc2, trace2 = _polish_account(monkeypatch, exc=RuntimeError("relay down"))
    original2 = trace2.life_epitaph
    assert LegacyEngine.try_polish_epitaph(acc2) is False
    assert trace2.life_epitaph == original2
    assert trace2.epitaph_polish == "failed"


def test_ep03_polish_payload_whitelist(monkeypatch):
    from core.legacy import LegacyEngine

    record = []
    acc, _trace = _polish_account(monkeypatch, record=record)
    assert LegacyEngine.try_polish_epitaph(acc) is True
    assert len(record) == 1
    scene, payload = record[0]
    assert scene == "epitaph_polish"
    assert set(payload.keys()) == {
        "family_text", "proposition_kind", "proposition_done",
        "realm_name", "cause_category", "old_story_kind"}
    for v in payload.values():
        assert isinstance(v, (str, bool)), f"payload 不得含数值：{v!r}"


def test_ep04_old_trace_skipped_and_call_sites():
    import pathlib

    from core.legacy import LegacyEngine

    acc = LegacyAccount(user_id=f"ep_old_{_tag()}")
    acc.traces = [LifeTrace(
        life_no=1, character_id=f"ep_old_char_{_tag()}", name="老前人",
        realm="练气", cause="寿尽", life_epitaph="老评语。")]
    assert LegacyEngine.try_polish_epitaph(acc) is False
    assert acc.traces[-1].epitaph_polish == "skipped"
    root = pathlib.Path(__file__).resolve().parent.parent
    legacy_src = (root / "core/legacy.py").read_text(encoding="utf-8")
    settle_seg = legacy_src.split("def settle_death")[1].split("\n    @")[0]
    assert "try_polish" not in settle_seg, "settle_death 本体不得同步调润色"
    briefing_src = (root / "core/briefing.py").read_text(encoding="utf-8")
    assert "try_polish" not in briefing_src, "登录路径不得调用润色"
    world_src = (root / "server/world.py").read_text(encoding="utf-8")
    assert world_src.count("_schedule_epitaph_polish") == 2, \
        "润色调度只许 _settle_if_needed 锁外一处（定义 + 调用各一）"


# ================= §8 后端呈现契约 =================

def _world_join(name):
    import server.world as world_mod

    W = world_mod.WORLD
    uid = f"ui_user_{_tag()}"
    snap = W.join(name, user_id=uid)
    return W, snap["token"], uid


def test_ui01_status_dict_thread_shape():
    import server.world as world_mod

    W = world_mod.WORLD
    char = _char("UI一", save=True)
    sd = W._status_dict(char)
    assert set(sd["fate"].keys()) >= {"boons", "pending", "power_bonus"}
    assert sd["fate"]["thread"] is None
    assert "location_image" in sd
    FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    sd2 = W._status_dict(char)
    th = sd2["fate"]["thread"]
    assert th is not None
    for key in ("id", "title", "status", "seed_source", "seed_ref",
                "antagonist", "patron", "final_proposition",
                "current_chapter", "current_target", "chapters", "shelvable", "origin_present"):
        assert key in th, key
    assert set(th["final_proposition"].keys()) == {"text", "status"}
    # B1-4（playability-block1）：chapters 透传章内 check（存在时才带），故键集多 "check"。
    assert set(th["chapters"][0].keys()) == {
        "idx", "group", "kind", "tier", "title", "goal_text",
        "status", "deadline_at", "check"}


# SUPERSEDED 注记（ui02）：旧断言要点——仅预置 visited 即可在 build_entry 内派生 fate_chapter；
# 已按新契约改写（带 npc_id 时须先交谈一轮，否则求值 pending、不出 fate_chapter）。
# 取代依据：Martinez 2026-11-10 路线 (b) 决策，见 playability-block1.md 决策记录。
def test_ui02_entry_fate_and_drama_hooks(monkeypatch):
    from core.briefing import build_entry

    npc = _npc("UI二向导")
    char = _manual_origin_char("UI二", npc)
    thread = FateThreadEngine.ensure_thread(char, LegacyAccount(user_id=char.user_id))
    # 预置 visited（不求值）：章节派生须发生在 build_entry 内才成 queue 项
    thread.visited = [LOC]
    FateThreadRepository.save(thread)
    # 复测再修（B1-4）：带 npc_id 的 visit 章须与向导交谈一轮才成，否则
    # build_entry 内求值仍 pending，不出 fate_chapter 项
    from core import npc_chat

    _opened = npc_chat.open_session(char, npc)
    assert _opened.get("success") is True, _opened
    _said = npc_chat.player_say(CharacterRepository.get_by_id(char.id), "幸会，道友")
    assert _said.get("success") is True, _said
    npc_chat.apply_npc_reply(char.id, "回礼，道友请坐。", True)
    entry = build_entry(char, since=0.0, now=time.time(), allow_proactive=False)
    kinds = [q.get("kind") for q in entry["queue"]]
    assert "fate_chapter" in kinds
    assert entry["lines"]["fate"].startswith("命途「")
    assert sum(1 for q in entry["queue"] if q.get("highlight")) <= 3
    # 戏剧接线口：假引擎返回事件 → queue 含 drama 项
    import core.npc_proactive as np_mod

    class _FakeDrama:
        @staticmethod
        def evaluate(player, *, trigger, now):
            return [{
                "id": "drama_ui02", "type": "chain_mature", "npc_id": npc.id,
                "npc_name": npc.name, "chain_id": "", "promise_id": "",
                "text": "有人找上门来。", "source": "test",
                "options": [{"key": "fight", "label": "应战"}],
                "created_at": now, "expires_at": now + 100,
            }]

    monkeypatch.setattr(np_mod, "DramaEngine", _FakeDrama, raising=False)
    entry2 = build_entry(char, since=0.0, now=time.time(), allow_proactive=True)
    drama = [q for q in entry2["queue"] if q.get("kind") == "drama"]
    assert drama and drama[0]["target"] == {"command": "/回应 drama_ui02"}
    assert drama[0]["options"] == [{"key": "fight", "label": "应战"}]
    # shelved 线：queue 不出 fate_chapter，lines.fate 标注搁置
    FateThreadEngine.shelve_thread(char)
    entry3 = build_entry(char, since=0.0, now=time.time(), allow_proactive=False)
    assert not [q for q in entry3["queue"] if q.get("kind") == "fate_chapter"]
    assert "已搁置" in entry3["lines"]["fate"]
    # 无线老角色：一期 entry 核心键齐备、无 fate_chapter/drama 项
    char3 = _char("UI二老", save=True)
    entry4 = build_entry(char3, since=0.0, now=time.time(), allow_proactive=False)
    assert {"version", "lines", "queue", "highlight"} <= set(entry4.keys())
    assert not [q for q in entry4["queue"]
                if q.get("kind") in ("fate_chapter", "drama")]


def test_ui03_chat_open_old_account():
    from core.karma_chains import KarmaChain, KarmaChainEngine
    from core.promises import Promise, PromiseStatus
    from storage.db import KarmaChainRepository, PromiseRepository

    W, token, _uid = _world_join("UI三")
    me = next(c for c in CharacterRepository.list_all_alive()
              if c.user_id == _uid)
    npc = _npc("UI三债主", location=me.location)
    PromiseRepository.save(Promise(
        promiser_id=me.id, promiser_name=me.name,
        promisee_id=npc.id, promisee_name=npc.name, promisee_is_npc=True,
        kind="debt", desc="借债未还", status=PromiseStatus.ACTIVE,
        created_at=time.time()))
    KarmaChainRepository.save(KarmaChain(
        id=f"kc_ui03_{_tag()}", kind="en", polarity=1,
        player_id=me.id, player_name=me.name,
        counterparty_id=npc.id, counterparty_name=npc.name,
        status="fermenting", created_at=time.time()))
    from core.npc_mind import shift_attitude

    shift_attitude(npc, me.id, -5, reason="UI三测试旧怨")
    CharacterRepository.save(npc)
    res = W.handle(token, f"/交谈 {npc.name}")
    assert res.get("ok"), res
    oa = res.get("old_account")
    assert oa is not None
    assert oa["open_promises"] == 1
    assert oa["fermenting_chains"] == KarmaChainEngine.status_summary(me)["fermenting"]
    assert oa["fermenting_chains"] >= 1
    assert oa["chains_with_npc"] == 1
    assert oa["last_relation"] and "UI三测试旧怨" in oa["last_relation"]


def test_ui04_fate_commands_via_handle():
    W, token, _uid = _world_join("UI四")
    res = W.handle(token, "/命途")
    assert res.get("ok"), res
    assert "命途" in (res.get("text") or "")
    assert res.get("fate_thread") and res["fate_thread"]["title"]
    res2 = W.handle(token, "/命途 搁置")
    assert res2.get("ok"), res2
    res3 = W.handle(token, "/命途 续")
    assert res3.get("ok"), res3
    res4 = W.handle(token, "/回应")
    assert res4.get("ok"), res4  # 引擎未就位：列空、ok=True
    res5 = W.handle(token, "/回应 some_id fight")
    assert res5.get("ok") is False  # 引擎未就位时带参零落账
    # 命令目录计数（集成岗收口，§8.4）：/命途 /回应 两条主命令已补登。
    # 计数口径记账：Spec §8.4 名义计数作 100→102，但 catalog_json 实测
    # 基线在一期交付时即为 106 条主命令（all_entries 按主命令去重、别名
    # 不另计行，与名义口径差 6 条既有命令）；目录侧断言以实测口径落：
    # 106 + 2 = 108，且两条新命令的主命令与别名均可检索。
    from core.command_catalog import catalog_json

    _cj = catalog_json()
    # B1-5（playability-block1）：新增 /修炼 主命令，实测计数 108→109。
    assert _cj["count"] == 109
    _cmds = {e["cmd"] for e in _cj["commands"]}
    assert "/命途" in _cmds and "/回应" in _cmds


def test_ui04_cli_dispatch_same_engine_source():
    """§8.4 CLI 分发（集成岗收口）：cli/main.py 交互循环不可直接驱动，
    按仓内先例（test_karma_chains_ui）以同引擎源码对齐断言钉住——
    /命途 面板与 server 同源（FateThreadEngine.panel_text）、搁置/续同
    引擎、/回应 同 DramaEngine 且 fight 经 resolve_ambush 斗法入口。"""
    import pathlib

    cli_src = pathlib.Path(__file__).resolve().parent.parent.joinpath(
        "cli", "main.py").read_text(encoding="utf-8")
    assert 'action in ["/命途", "/fate_thread"]' in cli_src
    assert "FateThreadEngine.panel_text(player)" in cli_src
    assert "FateThreadEngine.shelve_thread(player)" in cli_src
    assert "FateThreadEngine.resume_thread(player)" in cli_src
    assert 'action in ["/回应", "/respond_drama"]' in cli_src
    assert "DramaEngine.panel_text(player)" in cli_src
    assert "DramaEngine.respond(" in cli_src
    assert "CombatFateEngine.resolve_ambush" in cli_src


def test_ui05_location_image_key():
    import server.world as world_mod

    W = world_mod.WORLD
    char = _char("UI五", save=True)
    sd = W._status_dict(char)
    assert isinstance(sd["location_image"], str)
