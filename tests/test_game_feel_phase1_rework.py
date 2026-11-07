"""game-feel-phase1 评审返工验收（Spec §7.5 返工单 MF-1/MF-2/MF-3 + S-2/文案项）。

每条对应返工单一条：先以原 bug 场景构造，修复前红、修复后绿。
"""
import os
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import SECONDS_PER_GAME_DAY
from core.clock import WorldClock
from core.models import CharacterStatus
from storage.db import (
    CharacterRepository,
    KarmaChainRepository,
    PromiseRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name="试炼者", uid_prefix="rw", location=LOC):
    c = WorldClock.create_new_character(f"{uid_prefix}_{name}_{_tag()}", f"{name}{_tag()}")
    c.location = location
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


def _npc(name="试炼NPC", tier=1, location="万剑仙门峰"):
    c = WorldClock.create_new_character(f"npc_rw_{name}_{_tag()}", f"{name}{_tag()}")
    c.realm.tier = tier
    c.location = location
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


# ================= MF-1 入局拼装陈旧覆写 =================

def test_mf1_join_karma_resolution_not_rolled_back():
    """因果链到期 + 诺言到期同一次 join：链兑现落账不得被 join 回存回滚，
    链须为终态，且 ③ 判定式求值须基于兑现后灵石。"""
    from core.goals import add_checked_goal
    from core.karma_chains import KarmaChain, KarmaChainEngine
    from core.promises import Promise, PromiseStatus

    t0 = time.time()
    char = _char("链诺同登")
    char.spirit_stones = 100
    char.karma.merit_value = 0
    char.karma.sin_value = 0
    CharacterRepository.save(char)
    char = CharacterRepository.get_by_id(char.id)

    npc_chain = _npc("链恩人")
    npc_promise = _npc("诺证人")

    # 选一个灵石支的 chain id（branch_for 由 id 哈希定，XOR 支只落一侧）
    chain_id = None
    for i in range(1000):
        cand = KarmaChain(id=f"mf1c{i:04d}")
        if KarmaChainEngine.branch_for(cand) == "stones":
            chain_id = cand.id
            break
    assert chain_id, "应能找到灵石支 chain id"
    chain = KarmaChain(
        id=chain_id,
        chain_key=f"mf1:{char.id}:{npc_chain.id}",
        kind="nuo", polarity=1,
        player_id=char.id, player_name=char.name,
        counterparty_id=npc_chain.id, counterparty_name=npc_chain.name,
        delivery_actor_id=npc_chain.id, delivery_actor_name=npc_chain.name,
        strength=3, status="fermenting",
        origin_summary="践诺余绪",
        created_at=t0, ferment_at=t0 - 10, mature_at=t0 - 10,
        deadline_at=t0 + 7 * SECONDS_PER_GAME_DAY,
    )
    KarmaChainRepository.save(chain)
    expected = KarmaChainEngine.compute_effects(chain, t0)
    stones_gain = int(expected.get("stones_gain") or 0)
    merit_gain = int(expected.get("merit") or 0)
    assert stones_gain > 0 and merit_gain > 0, f"nuo 正向链应含灵石+功德：{expected}"

    # 同一次登录到期的诺言（quest 到期未践 → BROKEN，只落业力不扰灵石/功德断言）
    p = Promise(
        promiser_id=char.id, promiser_name=char.name,
        promisee_id=npc_promise.id, promisee_name=npc_promise.name,
        promisee_is_npc=True, kind="quest", desc="到期旧诺",
        status=PromiseStatus.ACTIVE,
        created_at=t0 - 1000, activated_at=t0 - 1000, deadline=t0 - 10,
    )
    PromiseRepository.save(p)

    # ③ 判定式：门槛在兑现前灵石（100）与兑现后（100+gain）之间——
    # 只有基于兑现后数值求值才会翻 done。
    goal_amount = 100 + stones_gain - 5
    assert 100 < goal_amount <= 100 + stones_gain
    add_checked_goal(
        char, source="origin", title="攒下安身钱", detail="",
        check={"kind": "stones_at_least", "amount": goal_amount},
        deadline_days=10, now=t0)
    CharacterRepository.save(char)

    snap = WORLD.join(char.name, user_id=char.user_id)
    assert snap.get("entry") is not None and not snap.get("lock_fallback")
    kinds = [q["kind"] for q in snap["entry"]["queue"]]
    assert "karma_resolved" in kinds and "promise_settled" in kinds

    after = CharacterRepository.get_by_id(char.id)
    assert after.spirit_stones == 100 + stones_gain, (
        f"链兑现灵石被回滚：期望 {100 + stones_gain}，实际 {after.spirit_stones}")
    assert after.karma.merit_value == merit_gain, (
        f"链兑现功德被回滚：期望 {merit_gain}，实际 {after.karma.merit_value}")
    chain_after = KarmaChainRepository.get(chain.id)
    assert chain_after is not None and chain_after.status == "resolved"
    goal_after = [g for g in after.goals
                  if (g.get("check") or {}).get("kind") == "stones_at_least"]
    assert goal_after and goal_after[0]["status"] == "done", (
        f"③ 求值未基于兑现后灵石：{goal_after}")
    p_after = [x for x in PromiseRepository.list_all() if x.id == p.id][0]
    assert p_after.status.value == "BROKEN"


# ================= MF-2 仪式命格 choices 错位 =================

def test_mf2_ceremony_choices_are_oldest_pending_and_selectable(monkeypatch):
    """已有一抽未选 + 再次突破产生第二抽：仪式 choices 必须 == pending[0]
    （唯一选择函数 apply_fate_choice 的 FIFO 口径），且明示尚有新抽待选；
    经 /命格 选择该 choices 中任一 key 须成功落账。"""
    from ai.gateway import AIGateway
    from core.breakthrough import BreakthroughEngine
    from core.ceremony import build_breakthrough_ceremony, fate_pool_for

    monkeypatch.setattr(
        AIGateway, "judge_tribulation",
        staticmethod(lambda c, prob, target: {
            "success": True, "source": "rule", "reason": "", "adj_prob": prob}),
    )
    char = _char("仪式错位")
    snap = WORLD.join(char.name, user_id=char.user_id)
    token = snap["token"]
    char = CharacterRepository.get_by_id(char.id)
    char.realm.tier = 1
    char.realm.sub_tier = 3
    char.realm.current_exp = char.realm.max_exp
    char.karma.dao_heart = 100
    old_candidates = [dict(c) for c in fate_pool_for(char)[:3]]
    char.fate_pending = [{
        "candidates": old_candidates, "from_tier": 1,
        "drawn_at": time.time() - 100,
    }]
    char.fate_boons = []
    CharacterRepository.save(char)
    char = CharacterRepository.get_by_id(char.id)

    res = BreakthroughEngine.attempt_breakthrough(char)
    assert res["success"] and res["is_major"]
    assert len(char.fate_pending) == 2, "再次突破应产生第二抽"
    CharacterRepository.save(char)

    cer = build_breakthrough_ceremony(char, res, fate_drawn=True)
    aftermath = [b for b in cer["beats"] if b["stage"] == "aftermath"][0]
    assert aftermath["choices"] == char.fate_pending[0]["candidates"], (
        "仪式 choices 必须呈现最老一抽（pending[0]），与 apply_fate_choice 的 FIFO 一致")
    # 明示尚有更新一抽待选（只增字段/文案，既有字段不删改）
    assert cer["result_ref"]["fate_pending_count"] == 2
    assert cer["result_ref"].get("fate_pending_newer_count") == 1
    assert "另有 1 抽" in aftermath["text"]

    key = aftermath["choices"][0]["key"]
    pick = WORLD.handle(token, f"/命格 {key}")
    assert pick.get("ok"), f"仪式 choices 中的 key 经 /命格 应可选：{pick}"
    after = CharacterRepository.get_by_id(char.id)
    assert [b["key"] for b in after.fate_boons] == [key]
    assert len(after.fate_pending) == 1, "只消费最老一抽，新抽仍待选"


# ================= MF-3 未竟之志 kind 映射缺失 =================

def test_mf3_origin_unfinished_maps_to_proposition_kind():
    """P2-07 正例：上世短期目标（origin 源、check=promise_settled）failed →
    未竟之志 kind 须为命题 kind debt_clear（非判定式原名）；下世有债时
    select_fate_proposition 以未竟版本（文案/check）返回 debt_clear 为头号候选。"""
    from core.goals import add_checked_goal, evaluate_checked_goals
    from core.legacy import LegacyAccount, LegacyEngine
    from core.origin import select_fate_proposition

    # 映射表全量（origin 源须与 fate 源共用同一映射）
    cases = {
        "promise_settled": "debt_clear",
        "npc_attitude_at_least": "foe_reckoning",
        "item_in_bag_at_death": "lost_relic",
        "stones_at_least": "family_revive",
        "sect_joined": "sect_inner",
        "realm_at_least": "stand_firm",
    }
    for ck, pk in cases.items():
        goal = {"source": "origin", "check": {"kind": ck}}
        assert LegacyEngine._prop_kind(goal, {}) == pk, f"{ck} 应映射为 {pk}"

    char = _char("未竟债者")
    t0 = time.time()
    g = add_checked_goal(
        char, source="origin", title="偿清旧债", detail="",
        check={"kind": "promise_settled", "ref": "p_old_missing"},
        deadline_days=1, now=t0)
    evaluate_checked_goals(char, t0 + 2 * SECONDS_PER_GAME_DAY)
    assert g["status"] == "failed"
    account = LegacyAccount(user_id=char.user_id)
    res = LegacyEngine.settle_death(account, char, death_cause="寿尽坐化", now=time.time())
    unfinished = res["trace"].unfinished_prop
    assert unfinished.get("kind") == "debt_clear", (
        f"未竟之志 kind 应为命题 kind debt_clear，实际 {unfinished.get('kind')}")

    kind, text, check = select_fate_proposition(
        has_debt=True, debt_promise_id="p_new",
        has_foe=False, foe_id="", foe_name="",
        old_story_kind="", family="药农", item_ref="",
        unfinished=unfinished)
    assert kind == "debt_clear"
    assert text == "偿清旧债", "文案应取未竟版本（上世目标标题）"
    assert check == {"kind": "promise_settled", "ref": "p_new"}, (
        "check 应取未竟判定式、ref 指向本世新债")


def test_mf3_mapped_unfinished_falls_through_when_condition_mismatch():
    """P2-07 负例：未竟映射为 foe_reckoning 但当世无 foe → 不得误命中，
    须正常落到后续优先级（stand_firm）。"""
    from core.goals import add_checked_goal, evaluate_checked_goals
    from core.legacy import LegacyAccount, LegacyEngine
    from core.origin import select_fate_proposition

    char = _char("未竟仇者")
    t0 = time.time()
    g = add_checked_goal(
        char, source="origin", title="讨个说法", detail="",
        check={"kind": "npc_attitude_at_least", "npc_id": "npc_missing_rw", "value": 0},
        deadline_days=1, now=t0)
    evaluate_checked_goals(char, t0 + 2 * SECONDS_PER_GAME_DAY)
    assert g["status"] == "failed"
    account = LegacyAccount(user_id=char.user_id)
    res = LegacyEngine.settle_death(account, char, death_cause="寿尽坐化", now=time.time())
    unfinished = res["trace"].unfinished_prop
    assert unfinished.get("kind") == "foe_reckoning"

    kind, _text, check = select_fate_proposition(
        has_debt=False, debt_promise_id="",
        has_foe=False, foe_id="", foe_name="",
        old_story_kind="幼年奇遇", family="寒门农家", item_ref="",
        unfinished=unfinished)
    assert kind == "stand_firm", f"无 foe 时不得命中 foe_reckoning，实际 {kind}"
    assert check == {"kind": "realm_at_least", "tier": 2}


# ================= S-2 entry.proactive 形状 =================

def test_s2_entry_proactive_single_object_or_none(monkeypatch):
    """有来访时 entry.proactive 为单对象 {text, npc}（取第一条），
    无来访时为 None；queue 里的 npc_visit 项逻辑不动。"""
    from core.briefing import build_entry
    from core.npc_proactive import NpcProactiveEngine

    char = _char("来访形状")
    monkeypatch.setattr(
        NpcProactiveEngine, "maybe_engage",
        staticmethod(lambda c, force=False: [{
            "npc": "来访者甲", "line": "道友别来无恙",
            "text": "【来访者甲】道友别来无恙", "delta": 0,
        }]),
    )
    entry = build_entry(char, since=char.born_at, allow_proactive=True)
    assert isinstance(entry["proactive"], dict), (
        f"proactive 应为单对象 dict，实际 {type(entry['proactive'])}")
    assert entry["proactive"]["npc"] == "来访者甲"
    assert "道友别来无恙" in entry["proactive"]["text"]
    assert any(q["kind"] == "npc_visit" for q in entry["queue"]), (
        "queue 的 npc_visit 项不得受 proactive 形状变更影响")

    monkeypatch.setattr(
        NpcProactiveEngine, "maybe_engage",
        staticmethod(lambda c, force=False: []),
    )
    entry2 = build_entry(char, since=char.born_at, allow_proactive=True)
    assert entry2["proactive"] is None
    entry3 = build_entry(char, since=char.born_at, allow_proactive=False)
    assert entry3["proactive"] is None


# ================= 文案项 转世返回文案动态灵石 =================

def test_reincarnate_text_uses_actual_spirit_stones():
    """转世返回文案须以新角实际 spirit_stones 拼写，不得写死 150。"""
    dead = _char("转世文案")
    dead.status = CharacterStatus.DEAD
    dead.death_cause = "寿尽坐化"
    dead.lifespan.death_timestamp = 0.0
    CharacterRepository.save(dead)
    payload = WORLD.dead_payload(dead.user_id)
    assert payload is not None and payload.get("settled")
    reb = WORLD.reincarnate(payload["token"])
    assert reb.get("ok"), reb
    new_char = CharacterRepository.get_by_user_id(dead.user_id)
    assert new_char is not None and new_char.id != dead.id
    assert f"新角随身 {new_char.spirit_stones} 灵石" in reb["text"], (
        f"文案应含新角实际灵石 {new_char.spirit_stones}：{reb['text']}")
    assert "新角随身 150 灵石不变" not in reb["text"]
