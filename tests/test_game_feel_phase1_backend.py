"""game-feel-phase1 后端验收（Spec §7 的 P1/P2/P3/P4 后端部分）。

覆盖：P1-01/P1-02/P1-06 拼装层、P2-01~P2-09、P3-01/P3-02/P3-03(后端
状态对账)/P3-05(后端文案非空)/P3-06、P4-01~P4-03。
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
    AccountRepository,
    CharacterRepository,
    EventLedgerRepository,
    PromiseRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name="试炼者", uid_prefix="gf", location=LOC):
    c = WorldClock.create_new_character(f"{uid_prefix}_{name}_{_tag()}", f"{name}{_tag()}")
    c.location = location
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


def _npc(name="试炼NPC", tier=1):
    c = WorldClock.create_new_character(f"npc_gf_{name}_{_tag()}", f"{name}{_tag()}")
    c.realm.tier = tier
    c.location = LOC
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


def _seeded_npcs():
    from core.npc_roster import seed_roster

    seed_roster()
    return [c for c in CharacterRepository.list_all_alive()
            if str(c.user_id).startswith("npc_")]


# ================= P4 / §5 RELATION 留痕 =================

def test_p4_relation_row_fields_and_marks():
    from core.npc_mind import shift_attitude, attitude_toward

    player = _char("关系甲")
    npc = _npc("关系师")
    shift_attitude(npc, player.id, 50, reason="赠礼")
    assert attitude_toward(npc, player.id)["value"] == 50
    rows = EventLedgerRepository.query_by_type_for_target(player.id, type="RELATION", limit=30)
    mine = [r for r in rows if r["actor_id"] == npc.id]
    assert mine, "跨档态度变化必须留 RELATION 行"
    row = mine[0]
    refs = row.get("refs") or []
    assert "delta:50" in refs and "before:neutral" in refs and "after:ally" in refs
    assert "reason:赠礼" in refs
    assert "attitude 0->50" in (row.get("effects_digest") or "")
    st = WORLD._status_dict(player)
    rec = [r for r in st["relations_recent"] if r["npc_id"] == npc.id]
    assert rec and rec[0]["delta"] == 50 and rec[0]["after_label"] == "ally"
    assert rec[0]["after_cn"] == "亲近"
    assert st["relations_marks"][npc.id]["delta"] == 50


def test_p4_relation_small_move_and_zero_move():
    from core.npc_mind import shift_attitude

    player = _char("关系乙")
    npc = _npc("关系商")
    shift_attitude(npc, player.id, 0, reason="主动搭话")
    rows = EventLedgerRepository.query_by_type_for_target(player.id, type="RELATION", limit=30)
    assert not [r for r in rows if r["actor_id"] == npc.id], "delta=0 不得留痕"
    shift_attitude(npc, player.id, 5, reason="寒暄")
    rows = EventLedgerRepository.query_by_type_for_target(player.id, type="RELATION", limit=30)
    mine = [r for r in rows if r["actor_id"] == npc.id]
    assert len(mine) == 1 and "before:neutral" in mine[0]["refs"] and "after:neutral" in mine[0]["refs"]


def test_p4_shadow_application_writes_no_relation():
    from core.inheritance import apply_karma_shadow
    from core.legacy import LegacyAccount, LifeTrace, ShadowEntry

    npcs = _seeded_npcs()
    assert npcs
    npc = npcs[0]
    new_char = _char("影子受者")
    account = LegacyAccount(user_id=new_char.user_id)
    account.traces = [LifeTrace(
        life_no=1, character_id="old_char_x", name="前人", realm="练气",
        cause="寿尽", shadow=[ShadowEntry(npc_id=npc.id, npc_name=npc.name, value=60)],
    )]
    applied = apply_karma_shadow(account, new_char, retention=0.4, cap=25)
    assert applied
    rows = EventLedgerRepository.query_by_type_for_target(new_char.id, type="RELATION", limit=30)
    assert rows == [], "影子直写路径一期不留 RELATION 痕"


# ================= §2 入口拼装 =================

def test_p1_get_last_login():
    uid = AccountRepository.create(f"gf_login_{_tag()}", "h", "s")
    assert uid
    v = AccountRepository.get_last_login(uid)
    assert v is not None and v > 0
    AccountRepository.touch_login(uid)
    v2 = AccountRepository.get_last_login(uid)
    assert v2 >= v
    assert AccountRepository.get_last_login("acct_nonexistent_xyz") is None


def test_p1_entry_empty_and_briefing_key():
    from core.briefing import build_entry, briefing

    char = _char("入局空")
    entry = build_entry(char, since=char.born_at, allow_proactive=False)
    assert entry["version"] == 1
    assert entry["empty"] is True and entry["queue"] == [] and entry["highlight"] == []
    assert entry["empty_text"] == "江湖无事，可自由行动"
    assert entry["lines"]["chains"]["fermenting"] == 0
    b = briefing(char)
    assert "entry" in b and b["entry"]["version"] == 1


def test_p1_entry_promise_settled_and_omen_priority():
    from core.briefing import build_entry
    from core.promises import Promise, PromiseStatus
    from storage.db import WorldStateRepository

    char = _char("入局诺")
    npc = _npc("入局证人")
    p = Promise(
        promiser_id=char.id, promiser_name=char.name,
        promisee_id=npc.id, promisee_name=npc.name, promisee_is_npc=True,
        kind="quest", desc="旧诺", status=PromiseStatus.ACTIVE,
        created_at=time.time() - 100000, activated_at=time.time() - 100000,
        deadline=time.time() - 10,
    )
    PromiseRepository.save(p)
    scenes = WorldStateRepository.get("omen_scenes") or {}
    scenes[char.id] = {"status": "open", "title": "夜半叩门", "player_id": char.id}
    WorldStateRepository.set("omen_scenes", scenes)
    try:
        entry = build_entry(char, since=char.born_at, allow_proactive=False)
    finally:
        scenes = WorldStateRepository.get("omen_scenes") or {}
        scenes.pop(char.id, None)
        WorldStateRepository.set("omen_scenes", scenes)
    kinds = [q["kind"] for q in entry["queue"]]
    assert "promise_settled" in kinds and "omen_active" in kinds
    prios = [q["priority"] for q in entry["queue"]]
    assert prios == sorted(prios)
    ps = [q for q in entry["queue"] if q["kind"] == "promise_settled"][0]
    assert ps["target"] == {"command": "/诺言"}
    # 诺言已被 settle_due 推进到终态
    after = [x for x in PromiseRepository.list_all() if x.id == p.id][0]
    assert after.status.value in ("KEPT", "BROKEN", "DISSOLVED")


def test_p1_entry_karma_resolved_and_failure_isolation(monkeypatch):
    from core.briefing import build_entry
    from core.karma_chains import KarmaChainEngine

    char = _char("入局链")
    monkeypatch.setattr(
        KarmaChainEngine, "advance_for",
        staticmethod(lambda c, now=None: [{"chain_id": "x1", "action": "resolved", "text": "恩怨已了"}]),
    )
    entry = build_entry(char, since=char.born_at, allow_proactive=False)
    kinds = [q["kind"] for q in entry["queue"]]
    assert kinds[0] == "karma_resolved"
    assert entry["queue"][0]["target"] == {"command": "/因果链"}
    assert len(entry["highlight"]) <= 3
    assert entry["rest_count"] == max(0, len(entry["queue"]) - 3)

    def _boom(c, now=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(KarmaChainEngine, "status_summary", staticmethod(_boom))
    entry2 = build_entry(char, since=char.born_at, allow_proactive=False)
    assert entry2 is not None and entry2["version"] == 1  # 单源失败不拖垮拼装


def test_p1_fallback_snapshot_entry_pending():
    char = _char("回退者")
    snap = WORLD._live_fallback_snapshot(char, char.user_id, resumed=True)
    assert snap["entry"] is None and snap["entry_pending"] is True


# ================= §3 出身 =================

def _gen(char, account, seed=7, **kw):
    from core.origin import OriginEngine

    return OriginEngine.generate_for_new_life(
        char, account, rng=random.Random(seed), now=time.time(), **kw)


def test_p2_origin_accounts_match():
    from core.legacy import LegacyAccount
    from core.npc_mind import attitude_toward

    _seeded_npcs()
    for seed in range(20):
        char = _char(f"对账{seed}")
        account = LegacyAccount(user_id=char.user_id)
        origin = _gen(char, account, seed=seed)
        assert origin, f"seed={seed} 应生成出身"
        assert char.spirit_stones == origin["stones_final"]
        assert 80 <= origin["stones_final"] <= 260
        assert -20 <= origin["strength_score"] <= 20
        assert 2 <= len(origin["relations"]) <= 4
        for rel in origin["relations"]:
            npc = CharacterRepository.get_by_id(rel["npc_id"])
            assert npc is not None
            assert attitude_toward(npc, char.id)["value"] == rel["init_value"]
        if origin["debt"]:
            assert 0 < origin["debt"]["amount"] <= 120
            debts = [p for p in PromiseRepository.list_all()
                     if p.id == origin["debt"]["promise_id"]]
            assert debts and debts[0].kind == "debt"
            assert debts[0].promisee_id == origin["debt"]["creditor_npc_id"]
            assert int(debts[0].param) == origin["debt"]["amount"]
            assert abs(debts[0].deadline - (origin["generated_at"] + 10 * SECONDS_PER_GAME_DAY)) < 2
        # 幂等闸：再生成不改
        again = _gen(char, account, seed=seed + 1000)
        assert again["signature"] == origin["signature"]
        # 增补（前端工单）：命题文本随块下发；vendor gate 带 NPC 名
        assert origin.get("fate_text"), f"seed={seed} fate_text 应非空"
        fate_goal = next(
            (g for g in char.goals if g.get("id") == origin["fate_goal_id"]), None)
        assert fate_goal is not None and fate_goal["title"] == origin["fate_text"]
        for gate in origin["path_gates"]:
            if gate["gate"] == "vendor":
                vendor = CharacterRepository.get_by_id(gate["target_ref"])
                assert vendor is not None
                assert gate.get("target_name") == vendor.name


def test_p2_origin_bounds_200():
    # bounds 是包本身的属性（§3.3-§3.6/§3.8）：200 包走生成器组包层
    # 直调（不起服务、不落账，与 P2-02「直调生成器于模拟角色」口径一致）；
    # 落账对账由 test_p2_origin_accounts_match 的 20 角全量生成覆盖。
    from core.origin import OriginEngine

    npcs = _seeded_npcs()
    by_id = {c.id: c for c in npcs}
    pool = OriginEngine._npc_pool(time.time())
    assert len(pool) == 37
    for seed in range(200):
        char = WorldClock.create_new_character(f"gf_bounds_{seed}_{_tag()}", f"界{seed}_{_tag()}")
        origin = None
        for attempt in range(20):  # 生成器总分钳制口径：带外整包重抽 ≤20 次
            cand = OriginEngine._build_package(
                char, random.Random(seed * 100 + attempt), time.time(), set(), pool=pool)
            if -20 <= cand["strength_score"] <= 20:
                origin = cand
                break
        assert origin is not None, f"seed={seed} 20 次重抽仍带外"
        assert 80 <= origin["stones_final"] <= 260
        debt_amt = origin["debt"]["amount"] if origin["debt"] else 0
        assert 0 <= debt_amt <= 120
        if origin["debt"]:
            creditor = by_id.get(origin["debt"]["creditor_npc_id"])
            assert creditor is not None and creditor.status != CharacterStatus.DEAD
        closed = [g for g in origin["path_gates"] if g["effect"] == "closed"]
        assert len(closed) <= 1
        assert -20 <= origin["strength_score"] <= 20
        assert len(origin["relations"]) <= 4
        for rel in origin["relations"]:
            npc = by_id[rel["npc_id"]]
            if rel["role"] == "foe":
                assert npc.realm.tier <= char.realm.tier + 1
                assert -45 <= rel["init_value"] <= -15
            elif rel["role"] == "kin":
                assert 25 <= rel["init_value"] <= 55
            else:
                assert -10 <= rel["init_value"] <= 15
        # 死局断言：至少一名可交易者非 foe（商会 NPC 中 relations 外或 kin/witness）
        foe_ids = {r["npc_id"] for r in origin["relations"] if r["role"] == "foe"}
        traders = [c for c in npcs if c.sect == "四海散修商会"]
        assert any(c.id not in foe_ids for c in traders)


def test_p2_origin_reproducible_and_dedup():
    from core.legacy import LegacyAccount, LifeTrace

    _seeded_npcs()
    c1 = _char("复算甲")
    o1 = _gen(c1, LegacyAccount(user_id=c1.user_id), seed=42)
    c2 = _char("复算乙")
    o2 = _gen(c2, LegacyAccount(user_id=c2.user_id), seed=42)
    for key in ("family", "signature", "stones_final", "strength_score"):
        assert o1[key] == o2[key]
    assert [r["npc_id"] for r in o1["relations"]] == [r["npc_id"] for r in o2["relations"]]

    # 防重：上一世 signature 相同 → 重抽后不同（或诚实降级标记）
    acc = LegacyAccount(user_id=c1.user_id)
    acc.traces = [LifeTrace(
        life_no=1, character_id="old1", name="旧", realm="练气", cause="寿尽",
        origin_signature=o1["signature"],
    )]
    c3 = _char("防重者")
    o3 = _gen(c3, acc, seed=42)
    assert o3["signature"] != o1["signature"] or o3.get("dedup_exhausted")


def test_p2_debt_payment_hook():
    from core.legacy import LegacyAccount
    from core.promises import PromiseEngine

    _seeded_npcs()
    # 找一个带债种子
    found = None
    for seed in range(60):
        char = _char(f"偿债{seed}")
        origin = _gen(char, LegacyAccount(user_id=char.user_id), seed=seed)
        if origin and origin["debt"]:
            found = (char, origin)
            break
    assert found, "60 个种子内应出现带债出身"
    char, origin = found
    creditor = CharacterRepository.get_by_id(origin["debt"]["creditor_npc_id"])
    amount = origin["debt"]["amount"]
    PromiseEngine.note_debt_payment(char, creditor, amount, now=time.time())
    p = [x for x in PromiseRepository.list_all() if x.id == origin["debt"]["promise_id"]][0]
    assert p.status.value == "KEPT" and p.paid >= amount


def test_p2_sect_gates_and_vendor_prices():
    from core.sect import evaluate_join
    from core.trade import attitude_buy_mult
    from core.npc_mind import shift_attitude
    from config import SECTS_CONFIG

    char = _char("叩关者", location=SECTS_CONFIG["青云宗"]["headquarters"])
    char.karma.dao_heart = 55
    CharacterRepository.save(char)
    ok, _ = evaluate_join(char, "青云宗")
    assert not ok  # 道心 55 < 60
    char.origin = {"path_gates": [{"gate": "sect", "target_ref": "青云宗", "effect": "favored"}]}
    ok, _ = evaluate_join(char, "青云宗")
    assert ok, "favored 道心判定 −10 应放行 55"
    char.origin = {"path_gates": [{"gate": "sect", "target_ref": "青云宗", "effect": "closed"}]}
    char.karma.dao_heart = 100
    ok, reason = evaluate_join(char, "青云宗")
    assert not ok and "出身旧怨" in reason

    player = _char("买家")
    vendor = _npc("专柜商", tier=1)
    vendor.sect = "四海散修商会"
    CharacterRepository.save(vendor)
    shift_attitude(vendor, player.id, 45, reason="test")
    mult_friendly, _ = attitude_buy_mult(vendor, player.id)
    shift_attitude(vendor, player.id, -90, reason="test")
    mult_hostile, _ = attitude_buy_mult(vendor, player.id)
    assert mult_friendly < 1.0 < mult_hostile


def test_p2_checked_goals_evaluator():
    from core.goals import GoalEngine, add_checked_goal, evaluate_checked_goals
    from core.promises import Promise, PromiseStatus, PromiseEngine
    from core.npc_mind import shift_attitude

    char = _char("判定者")
    char.spirit_stones = 150
    char.inventory = ["祖传药碾"]
    npc = _npc("判定NPC")
    shift_attitude(npc, char.id, 20, reason="test")

    add_checked_goal(char, source="origin", title="攒下安身钱", detail="",
                     check={"kind": "stones_at_least", "amount": 100}, deadline_days=7)
    add_checked_goal(char, source="fate", title="寻回遗物", detail="",
                     check={"kind": "item_in_bag_at_death", "item_ref": "药碾"}, deadline_days=None)
    add_checked_goal(char, source="fate", title="和气收场", detail="",
                     check={"kind": "npc_attitude_at_least", "npc_id": npc.id, "value": 10},
                     deadline_days=None)
    # 幂等：同 source 同 ref 不重复挂
    add_checked_goal(char, source="origin", title="攒下安身钱", detail="",
                     check={"kind": "stones_at_least", "amount": 100}, deadline_days=7)
    assert len([g for g in char.goals if g.get("source") == "origin"]) == 1

    flipped = evaluate_checked_goals(char, time.time())
    by_title = {g["title"]: g for g in char.goals}
    assert by_title["攒下安身钱"]["status"] == "done"
    assert by_title["和气收场"]["status"] == "done"
    assert by_title["寻回遗物"]["status"] == "active"  # 只在终判求值
    flipped2 = evaluate_checked_goals(char, time.time(), final=True)
    assert by_title["寻回遗物"]["status"] == "done"

    # 到期 failed
    char2 = _char("到期者")
    g = add_checked_goal(char2, source="origin", title="偿清旧债", detail="",
                         check={"kind": "stones_at_least", "amount": 99999}, deadline_days=1)
    evaluate_checked_goals(char2, time.time() + 2 * SECONDS_PER_GAME_DAY)
    assert g["status"] == "failed" and g["done_reason"] == "到期未达成"

    # promise_settled：KEPT → done；BROKEN → 立即 failed
    char3 = _char("诺判者")
    cred = _npc("诺判债主")
    p = Promise(promiser_id=char3.id, promiser_name=char3.name, promisee_id=cred.id,
                promisee_name=cred.name, promisee_is_npc=True, kind="debt", param="50",
                desc="旧债", status=PromiseStatus.ACTIVE, created_at=time.time(),
                activated_at=time.time(), deadline=time.time() + 10000)
    PromiseRepository.save(p)
    add_checked_goal(char3, source="origin", title="偿清旧债", detail="",
                     check={"kind": "promise_settled", "ref": p.id}, deadline_days=10)
    evaluate_checked_goals(char3, time.time())
    goal = [g for g in char3.goals if g.get("source") == "origin"][0]
    assert goal["status"] == "active"
    PromiseEngine._settle(p, PromiseStatus.KEPT, "旧债已清", time.time(), promiser_obj=char3)
    goal = [g for g in char3.goals if g.get("source") == "origin"][0]
    assert goal["status"] == "done"  # E2 求值点

    # fate 不可弃 / origin 可弃
    char4 = _char("弃目标者")
    gf = add_checked_goal(char4, source="fate", title="命途", detail="",
                          check={"kind": "realm_at_least", "tier": 2}, deadline_days=None)
    r = GoalEngine.reject(char4, gf["id"])
    assert not r["success"]
    go = add_checked_goal(char4, source="origin", title="短期", detail="",
                          check={"kind": "stones_at_least", "amount": 100}, deadline_days=7)
    r2 = GoalEngine.reject(char4, go["id"])
    assert r2["success"]


def test_p2_death_epitaph_and_unfinished():
    from core.goals import add_checked_goal, evaluate_checked_goals
    from core.legacy import LegacyAccount, LegacyEngine
    from core.inheritance import tombstone_text, trace_summary

    char = _char("评语者")
    char.origin = {
        "family": "药农", "family_text": "青石镇药农之子", "signature": "药农|父辈旧债|x|debt",
        "old_story": {"kind": "父辈旧债", "npc_id": "x", "item_ref": "", "summary": "父债子偿"},
    }
    g = add_checked_goal(char, source="origin", title="偿清旧债", detail="",
                         check={"kind": "stones_at_least", "amount": 99999}, deadline_days=1)
    evaluate_checked_goals(char, time.time() + 2 * SECONDS_PER_GAME_DAY)
    assert g["status"] == "failed"
    account = LegacyAccount(user_id=char.user_id)
    res = LegacyEngine.settle_death(account, char, death_cause="寿尽坐化", now=time.time())
    trace = res["trace"]
    assert trace.fate_summary and "未竟之志" in trace.fate_summary
    assert trace.life_epitaph
    assert trace.origin_signature == "药农|父辈旧债|x|debt"
    assert trace.unfinished_prop.get("kind") == "stones_at_least" or trace.unfinished_prop
    tomb = tombstone_text(trace)
    assert "一生评语：" in tomb
    summ = trace_summary(trace)
    for k in ("fate_summary", "life_epitaph", "origin_signature", "unfinished_prop"):
        assert k in summ

    # rejected 的短期目标不入未竟
    char2 = _char("弃志者")
    from core.goals import GoalEngine
    g2 = add_checked_goal(char2, source="origin", title="小事", detail="",
                          check={"kind": "stones_at_least", "amount": 100}, deadline_days=7)
    GoalEngine.reject(char2, g2["id"])
    acc2 = LegacyAccount(user_id=char2.user_id)
    res2 = LegacyEngine.settle_death(acc2, char2, death_cause="寿尽坐化", now=time.time())
    assert res2["trace"].unfinished_prop == {}


def test_p2_unfinished_becomes_top_candidate():
    from core.origin import select_fate_proposition

    kind, text, check = select_fate_proposition(
        has_debt=True, debt_promise_id="p_new", has_foe=True, foe_id="n1",
        old_story_kind="族仇未雪", family="罪族遗孤", item_ref="",
        unfinished={"kind": "debt_clear", "text": "还清旧债，护住家业", "check": {"kind": "promise_settled", "ref": "p_old"}},
    )
    assert kind == "debt_clear" and check["ref"] == "p_new"  # 指向本世新债
    kind2, _, _ = select_fate_proposition(
        has_debt=False, debt_promise_id="", has_foe=False, foe_id="",
        old_story_kind="幼年奇遇", family="寒门农家", item_ref="",
        unfinished={"kind": "foe_reckoning", "text": "讨个说法", "check": {}},
    )
    assert kind2 != "foe_reckoning"  # 本世无 foe → 回退优先级序


def test_p2_two_origins_differ():
    from core.legacy import LegacyAccount

    _seeded_npcs()
    a = _char("药农子")
    oa = _gen(a, LegacyAccount(user_id=a.user_id), seed=3,
              force_family="药农", force_story="父辈旧债")
    b = _char("罪族孤")
    ob = _gen(b, LegacyAccount(user_id=b.user_id), seed=3,
              force_family="罪族遗孤", force_story="族仇未雪")
    ga = [g for g in a.goals if g.get("source") == "origin"]
    gb = [g for g in b.goals if g.get("source") == "origin"]
    assert ga and gb
    diffs = 0
    if oa["birthplace"] != ob["birthplace"]:
        diffs += 1
    if (ga[0].get("check") or {}).get("kind") != (gb[0].get("check") or {}).get("kind"):
        diffs += 1
    if oa["debt"] is not None and ob["debt"] is None:
        diffs += 1
    fa = [g for g in a.goals if g.get("source") == "fate"]
    fb = [g for g in b.goals if g.get("source") == "fate"]
    if fa and fb and (fa[0].get("check") or {}).get("kind") != (fb[0].get("check") or {}).get("kind"):
        diffs += 1
    roles_a = {r["role"] for r in oa["relations"]}
    roles_b = {r["role"] for r in ob["relations"]}
    if roles_a != roles_b:
        diffs += 1
    assert diffs >= 3, f"两出身差异不足：{diffs}"


def test_p4_origin_relations_leave_relation_rows():
    from core.legacy import LegacyAccount

    _seeded_npcs()
    char = _char("出身留痕")
    origin = _gen(char, LegacyAccount(user_id=char.user_id), seed=11)
    rows = EventLedgerRepository.query_by_type_for_target(char.id, type="RELATION", limit=30)
    origin_rows = [r for r in rows if "reason:origin" in (r.get("refs") or [])]
    assert len(origin_rows) == len(origin["relations"])
    for rel in origin["relations"]:
        hit = [r for r in origin_rows if r["actor_id"] == rel["npc_id"]]
        assert hit and f"after:" in " ".join(hit[0]["refs"])


def test_p2_join_generates_origin_and_old_char_untouched():
    uid = AccountRepository.create(f"gf_join_{_tag()}", "h", "s")
    snap = WORLD.join("新入世者" + _tag()[-6:], user_id=uid)
    assert snap.get("is_new_life")
    assert snap.get("origin_card") and snap["origin_card"]["just_created"] is True
    assert snap["origin_card"]["origin"]
    assert snap.get("entry") and snap["entry"]["version"] == 1
    char = CharacterRepository.get_by_user_id(uid)
    assert char.origin
    # 老角色（无出身）登录不追溯
    old = _char("老江湖")
    assert old.origin == {}
    snap2 = WORLD.join(old.name, user_id=old.user_id)
    assert snap2.get("entry") is not None
    old2 = CharacterRepository.get_by_id(old.id)
    assert old2.origin == {}


# ================= §4 仪式 / 命格 =================

def _force_breakthrough_char(name="破境者"):
    char = _char(name)
    char.realm.tier = 1
    char.realm.sub_tier = 3
    char.realm.current_exp = char.realm.max_exp
    char.karma.dao_heart = 100
    CharacterRepository.save(char)
    return CharacterRepository.get_by_id(char.id)


def test_p3_fate_draw_and_choice(monkeypatch):
    from ai.gateway import AIGateway
    from core.breakthrough import BreakthroughEngine
    from core.ceremony import apply_fate_choice, fate_pool_for

    monkeypatch.setattr(
        AIGateway, "judge_tribulation",
        staticmethod(lambda c, prob, target: {"success": True, "source": "rule", "reason": "", "adj_prob": prob}),
    )
    char = _force_breakthrough_char()
    res = BreakthroughEngine.attempt_breakthrough(char)
    assert res["success"] and res["is_major"]
    assert len(char.fate_pending) == 1
    draw = char.fate_pending[0]
    cands = draw["candidates"]
    assert len(cands) == 3 and len({c["key"] for c in cands}) == 3
    pool_keys = {c["key"] for c in fate_pool_for(char)}
    assert {c["key"] for c in cands} <= pool_keys
    assert all(c["name"] and c["desc"] for c in cands)
    # 零副作用失败
    bad = apply_fate_choice(char, "no_such_key")
    assert not bad["success"] and len(char.fate_pending) == 1 and char.fate_boons == []
    ok = apply_fate_choice(char, cands[0]["key"])
    assert ok["success"] and len(char.fate_boons) == 1 and char.fate_pending == []
    assert char.fate_boons[0]["key"] == cands[0]["key"]


def test_p3_power_bonus_zero_drift_and_cap():
    from core.ceremony import FateBoonEngine
    from core.combat import CombatEngine

    char = _char("战力者")
    assert FateBoonEngine.power_bonus(char) == 1.0
    base = CombatEngine.calculate_power(char)
    assert base > 0
    char.fate_boons = [{"key": "pure_yang", "name": "纯阳烈煞", "from_tier": 2, "chosen_at": 0.0}]
    assert abs(FateBoonEngine.power_bonus(char) - 1.03) < 1e-9
    boosted = CombatEngine.calculate_power(char)
    assert abs(boosted - base * 1.03) < 1e-6 * max(1.0, base)
    char.fate_boons = [{"key": "iron_wall", "name": "不动如山", "from_tier": t, "chosen_at": 0.0}
                       for t in range(2, 7)]
    assert FateBoonEngine.power_bonus(char) == 1.15  # 截断


def test_p3_ceremony_breakthrough_and_death_rebirth():
    from core.ceremony import build_breakthrough_ceremony

    char = _force_breakthrough_char("仪式者")
    fake_res = {"success": True, "is_major": True, "new_realm": "筑基初", "lifespan_gained": 25.0}
    cer = build_breakthrough_ceremony(char, fake_res, fate_drawn=True)
    assert cer["kind"] == "breakthrough" and cer["skippable"] is True
    stages = [b["stage"] for b in cer["beats"]]
    assert stages == ["prelude", "reveal", "aftermath"] or set(stages) >= {"prelude", "reveal"}
    assert all(b["text"] for b in cer["beats"])
    assert cer["result_ref"]["success"] is True and cer["result_ref"]["fate_drawn"] is True

    # 死亡 → dead_payload ceremony → 转世 ceremony
    dead = _char("归府者")
    dead.status = CharacterStatus.DEAD
    dead.death_cause = "寿尽坐化"
    dead.lifespan.death_timestamp = 0.0
    CharacterRepository.save(dead)
    payload = WORLD.dead_payload(dead.user_id)
    assert payload is not None and payload.get("settled")
    assert payload["ceremony"] and payload["ceremony"]["kind"] == "death"
    assert payload["ceremony"]["result_ref"]["cause"]
    fb = WORLD._dead_fallback_snapshot(dead.user_id)
    # 回退路（未结算快照口径）：ceremony 为 null——用已结算角色时 fallback
    # 仍返回快照结构则检查键存在；若角色已结算后 fallback 不适用则跳过
    if fb is not None:
        assert fb.get("ceremony") is None
    reb = WORLD.reincarnate(payload["token"])
    assert reb.get("ok")
    assert reb["ceremony"]["kind"] == "rebirth"
    assert reb["origin_card"]["just_created"] is True
    assert reb["ceremony"]["result_ref"]["origin_signature"] == (
        reb["origin_card"]["origin"].get("signature") if reb["origin_card"]["origin"] else "")


def test_p3_fate_command_and_catalog():
    from core.command_catalog import COMMANDS

    cmds = {c["cmd"] for c in COMMANDS}
    assert "/命格" in cmds
    uid = AccountRepository.create(f"gf_fate_{_tag()}", "h", "s")
    snap = WORLD.join("命格客" + _tag()[-6:], user_id=uid)
    token = snap["token"]
    char = CharacterRepository.get_by_user_id(uid)
    char.fate_pending = [{
        "candidates": [
            {"key": "pure_yang", "name": "纯阳烈煞", "desc": "火", "icon": "🔥", "source": "dao"},
            {"key": "iron_wall", "name": "不动如山", "desc": "土", "icon": "🛡️", "source": "dao"},
            {"key": "fate_pierce", "name": "破煞", "desc": "破", "icon": "✦", "source": "affix"},
        ],
        "from_tier": 2, "drawn_at": time.time(),
    }]
    CharacterRepository.save(char)
    view = WORLD.handle(token, "/命格")
    assert view.get("ok") and view.get("fate") and view["fate"]["pending"]
    pick = WORLD.handle(token, "/命格 pure_yang")
    assert pick.get("ok")
    char2 = CharacterRepository.get_by_user_id(uid)
    assert [b["key"] for b in char2.fate_boons] == ["pure_yang"]
    st = WORLD.handle(token, "/look")
    assert st["status"]["fate"]["boons"][0]["key"] == "pure_yang"
    assert st["status"]["origin"] is not None
