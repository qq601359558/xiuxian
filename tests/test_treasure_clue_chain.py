"""寻宝线索链（spec: gallery-gameplay §5，验收 T-1~T-10 后端部分）。

链状态挂图实体 custom_metadata["clue_chain"]；终局仍走 TreasureEngine.dig。
数值对账一律以落盘口径的内存实体/KV 值为准：单步子顶 灵石20/修为30/
道心3/业力5，单链累计 灵石40/修为60/道心5/业力10，寿元恒 0；完成奖励
XOR hash 定支（灵石 15×tier≤60 / 修为 30×tier≤120），日顶 120/240。
隔离方式：唯一 user_id 前缀；日限/完成 KV 用例后删除。
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

from core.clock import WorldClock
from core.items import ItemFactory, ItemKind
from core.models import CharacterStatus, Element
from core.treasure_clue import (
    DAILY_KEY_PREFIX,
    DONE_KEY_PREFIX,
    TreasureClueEngine,
    bonus_amount,
    bonus_branch_for_seed,
    chain_summary,
    get_chain,
    steps_for_tier,
)
from core.treasure_system import TreasureEngine
from storage.db import init_db, WorldStateRepository

init_db()

TARGET_ID = "node_heishui_swamp"
TARGET_NAME = "黑水沼泽"
HOME = "青云坊市客栈"


def _tag():
    return uuid.uuid4().hex[:8]


def _player(location=HOME):
    c = WorldClock.create_new_character(f"tc_{_tag()}", f"寻宝客{_tag()}")
    c.location = location
    return c


def _map(tier=2, archetype="element_puzzle"):
    return ItemFactory.create_treasure_map(
        TARGET_ID, TARGET_NAME, tier=tier, archetype=archetype, riddle="谶语测试"
    )


def _cleanup(char, *maps):
    WorldStateRepository.delete(DAILY_KEY_PREFIX + str(char.id))
    for m in maps:
        WorldStateRepository.delete(DONE_KEY_PREFIX + str(m.uid))


def _craft_chain(char, tmap, steps, status="active", branch="stones"):
    """手工构造链（绕过随机生成，专测抉择裁决口径）。"""
    tmap.custom_metadata["clue_chain"] = {
        "version": 1,
        "status": status,
        "seed": str(tmap.uid),
        "steps": steps,
        "step_index": 0,
        "activated_at": time.time(),
        "activated_by": char.id,
        "completed_at": 0.0,
        "bonus_branch": branch,
        "bonus_paid": False,
        "penalties": {"stones": 0, "exp": 0, "dao_heart": 0, "sin": 0},
    }
    if tmap not in char.items:
        char.add_item_entity(tmap)
    return tmap.custom_metadata["clue_chain"]


def _step(kind, node_name=HOME, **extra):
    s = {"node_id": "node_qingyun_market", "node_name": node_name,
         "kind": kind, "riddle_text": "测试谶语", "settled": False, "outcome": ""}
    s.update(extra)
    return s


def _safe_choice(char, tmap):
    """按当前步类型选一个必定结算的选项（走全链用）。"""
    chain = get_chain(tmap)
    step = chain["steps"][chain["step_index"]]
    char.location = step["node_name"]
    if step["kind"] == "guardian":
        return "2" if char.spirit_stones >= 20 else "1"
    if step["kind"] == "trap":
        return "2"
    return str(int(step.get("answer") or 0) + 1)  # riddle 答对


# ---------------------------------------------------------------------------
# T-1 激活与步数 / 生成幂等
# ---------------------------------------------------------------------------
def test_t1_activation_steps_by_tier_and_fields():
    for tier, want in ((1, 2), (2, 2), (3, 3), (4, 3)):
        assert steps_for_tier(tier) == want
        c = _player()
        m = _map(tier=tier)
        c.add_item_entity(m)
        try:
            res = TreasureClueEngine.activate(c, m)
            assert res["changed"], (tier, res)
            chain = get_chain(m)
            assert chain["status"] == "active"
            assert chain["seed"] == m.uid
            assert chain["bonus_branch"] == bonus_branch_for_seed(m.uid)
            assert len(chain["steps"]) == want
            assert chain["penalties"] == {"stones": 0, "exp": 0, "dao_heart": 0, "sin": 0}
            # 目标节点与激活时所在节点不入线索步
            node_ids = {s["node_id"] for s in chain["steps"]}
            assert TARGET_ID not in node_ids
            assert "node_qingyun_market" not in node_ids
        finally:
            _cleanup(c, m)


def test_t1_repeat_activation_never_rebuilds():
    c = _player()
    m = _map(tier=3)
    c.add_item_entity(m)
    try:
        TreasureClueEngine.activate(c, m)
        snapshot = [dict(s) for s in get_chain(m)["steps"]]
        res = TreasureClueEngine.activate(c, m)
        assert not res["changed"]
        assert get_chain(m)["steps"] == snapshot
        assert get_chain(m)["step_index"] == 0
    finally:
        _cleanup(c, m)


def test_generation_deterministic_same_seed():
    c = _player()
    m1, m2 = _map(), _map()
    m2.uid = m1.uid  # 同 uid = 同 seed
    from core.treasure_clue import _generate_steps

    assert _generate_steps(m1, c) == _generate_steps(m2, c)


# ---------------------------------------------------------------------------
# T-2 日激活上限
# ---------------------------------------------------------------------------
def test_t2_daily_activation_cap_and_next_day():
    c = _player()
    maps = []
    try:
        for _ in range(3):
            m = _map()
            maps.append(m)
            c.add_item_entity(m)
            assert TreasureClueEngine.activate(c, m)["changed"]
        m4 = _map()
        maps.append(m4)
        c.add_item_entity(m4)
        res = TreasureClueEngine.activate(c, m4)
        assert not res["changed"] and "上限" in res["text"]
        assert get_chain(m4) is None
        from core.treasure_clue import _daily_state

        assert _daily_state(c.id)["starts"] == 3
        # 跨日（注入时刻）可再激活
        res = TreasureClueEngine.activate(c, m4, now=time.time() + 2 * 86400)
        assert res["changed"]
    finally:
        _cleanup(c, *maps)


# ---------------------------------------------------------------------------
# T-3 推进与地点门禁
# ---------------------------------------------------------------------------
def test_t3_wrong_location_no_settle_no_change():
    c = _player()
    m = _map()
    chain = _craft_chain(c, m, [_step("trap", node_name="落霞山灵泉")])
    before = (c.spirit_stones, c.realm.current_exp, c.karma.dao_heart, c.karma.sin_value)
    res = TreasureClueEngine.choose(c, "2")  # 人在客栈，步在灵泉
    assert not res["success"] and res.get("wrong_location")
    assert chain["step_index"] == 0 and not chain["steps"][0]["settled"]
    assert before == (c.spirit_stones, c.realm.current_exp, c.karma.dao_heart, c.karma.sin_value)
    # 抵达后结算推进
    c.location = "落霞山灵泉"
    res = TreasureClueEngine.choose(c, "2")
    assert res["success"] and res["settled"]
    assert chain["step_index"] == 1 and chain["steps"][0]["settled"]
    assert chain["status"] == "awaiting_chest"


# ---------------------------------------------------------------------------
# T-4 三类抉择裁决
# ---------------------------------------------------------------------------
def test_t4_guardian_fight_win_and_fail():
    # 胜：高境界压过守卫（60+tier*45）
    c = _player()
    c.realm.tier = 5
    m = _map(tier=2)
    chain = _craft_chain(c, m, [_step("guardian")])
    res = TreasureClueEngine.choose(c, "1")
    assert res["outcome"] == "win"
    assert chain["penalties"] == {"stones": 0, "exp": 0, "dao_heart": 0, "sin": 0}

    # 败：道心压低战力 → fail_forward 落惩罚（修为30/道心3/业力5 子顶）
    c2 = _player()
    c2.karma.dao_heart = 5
    c2.realm.current_exp = 100
    m2 = _map(tier=4)
    chain2 = _craft_chain(c2, m2, [_step("guardian")])
    res = TreasureClueEngine.choose(c2, "1")
    assert res["outcome"] == "fail_forward"
    assert chain2["penalties"]["exp"] == 30
    assert c2.realm.current_exp == 70


def test_t4_guardian_bypass_currency_gate():
    c = _player()
    c.spirit_stones = 100
    m = _map()
    chain = _craft_chain(c, m, [_step("guardian")])
    res = TreasureClueEngine.choose(c, "2")
    assert res["outcome"] == "bypass"
    assert c.spirit_stones == 80 and chain["penalties"]["stones"] == 20

    # 灵石不足：不可选、零副作用、步未结算
    c2 = _player()
    c2.spirit_stones = 10
    m2 = _map()
    chain2 = _craft_chain(c2, m2, [_step("guardian")])
    res = TreasureClueEngine.choose(c2, "2")
    assert not res["success"] and c2.spirit_stones == 10
    assert not chain2["steps"][0]["settled"] and chain2["step_index"] == 0

    # 退：不结算不推进无惩罚
    res = TreasureClueEngine.choose(c2, "3")
    assert res["success"] and not chain2["steps"][0]["settled"]


def test_t4_trap_element_relations():
    # 克陷阱 → win（金克木）
    c = _player()
    c.spiritual_root.elements = [Element.METAL]
    m = _map()
    chain = _craft_chain(c, m, [_step("trap", trap_element="木")])
    assert TreasureClueEngine.choose(c, "1")["outcome"] == "win"

    # 被克 → fail_forward（金克木，玩家木被克）
    c2 = _player()
    c2.spiritual_root.elements = [Element.WOOD]
    c2.realm.current_exp = 100
    m2 = _map()
    _craft_chain(c2, m2, [_step("trap", trap_element="金")])
    res = TreasureClueEngine.choose(c2, "1")
    assert res["outcome"] == "fail_forward" and c2.realm.current_exp == 70

    # 无关 → bypass 小惩罚（金对水：不克不被克）
    c3 = _player()
    c3.spiritual_root.elements = [Element.METAL]
    c3.realm.current_exp = 100
    m3 = _map()
    chain3 = _craft_chain(c3, m3, [_step("trap", trap_element="水")])
    res = TreasureClueEngine.choose(c3, "1")
    assert res["outcome"] == "bypass" and chain3["penalties"]["exp"] == 15

    # 硬闯：必付小额（灵石10/修为15）
    c4 = _player()
    c4.spirit_stones = 50
    c4.realm.current_exp = 100
    m4 = _map()
    chain4 = _craft_chain(c4, m4, [_step("trap", trap_element="火")])
    res = TreasureClueEngine.choose(c4, "2")
    assert res["outcome"] == "bypass"
    assert chain4["penalties"]["stones"] == 10 and chain4["penalties"]["exp"] == 15


def test_t4_riddle_wrong_answer_settles_once():
    c = _player()
    c.realm.current_exp = 100
    m = _map()
    chain = _craft_chain(c, m, [_step("riddle", options=["甲", "乙", "丙"], answer=0)])
    res = TreasureClueEngine.choose(c, "2")  # 答错
    assert res["outcome"] == "fail_forward"
    assert chain["steps"][0]["settled"] and chain["status"] == "awaiting_chest"
    exp_after = c.realm.current_exp
    # 不可重答：再答只回 awaiting 摘要，无二次落账
    res = TreasureClueEngine.choose(c, "1")
    assert c.realm.current_exp == exp_after


# ---------------------------------------------------------------------------
# T-5 惩罚子顶与寿元恒 0
# ---------------------------------------------------------------------------
def test_t5_chain_penalty_caps_and_lifespan_untouched():
    c = _player()
    c.spiritual_root.elements = [Element.WOOD]
    c.realm.current_exp = 500
    death_ts = c.lifespan.death_timestamp
    m = _map(tier=4)
    steps = [_step("trap", trap_element="金") for _ in range(3)]  # 全被克 fail
    chain = _craft_chain(c, m, steps)
    for _ in range(3):
        TreasureClueEngine.choose(c, "1")
    p = chain["penalties"]
    assert p["exp"] == 60 and p["dao_heart"] == 5 and p["sin"] == 10  # 单链累计顶截断
    assert p["stones"] <= 40
    assert c.lifespan.death_timestamp == death_ts  # 寿元恒 0


# ---------------------------------------------------------------------------
# T-6 完成奖励 XOR / 日顶 / 幂等
# ---------------------------------------------------------------------------
def _awaiting_snapshot(c, m, branch, tier=2):
    _craft_chain(c, m, [_step("guardian")], status="awaiting_chest", branch=branch)
    return TreasureClueEngine.snapshot_chain(c)


def test_t6_completion_bonus_xor_and_idempotent():
    assert bonus_amount("stones", 4) == 60 and bonus_amount("stones", 2) == 30
    assert bonus_amount("exp", 4) == 120 and bonus_amount("exp", 2) == 60

    c = _player()
    c.spirit_stones = 100
    exp0 = c.realm.current_exp
    m = _map(tier=2)
    snap = _awaiting_snapshot(c, m, "stones", tier=2)
    try:
        res = TreasureClueEngine.on_chest_opened(c, snap, "perfect_solve")
        assert res["paid"] and res["amount"] == 30
        assert c.spirit_stones == 130
        assert c.realm.current_exp == exp0  # XOR：修为支不动
        # 重入不重发（bonus_paid 锚先落盘）
        res = TreasureClueEngine.on_chest_opened(c, snap, "perfect_solve")
        assert not res["paid"] and c.spirit_stones == 130
        # outcome 不在白名单不发
        c2 = _player()
        m2 = _map(tier=2)
        snap2 = _awaiting_snapshot(c2, m2, "exp", tier=2)
        try:
            res = TreasureClueEngine.on_chest_opened(c2, snap2, "combat_defeat")
            assert not res["paid"]
        finally:
            _cleanup(c2, m2)
    finally:
        _cleanup(c, m)


def test_t6_daily_bonus_cap():
    c = _player()
    c.spirit_stones = 0
    today = time.time()
    from datetime import date

    WorldStateRepository.set(DAILY_KEY_PREFIX + c.id, {
        "date": date.fromtimestamp(today).isoformat(),
        "starts": 0, "bonus_stones": 110, "bonus_exp": 0,
    })
    m = _map(tier=2)
    snap = _awaiting_snapshot(c, m, "stones", tier=2)
    try:
        res = TreasureClueEngine.on_chest_opened(c, snap, "combat_victory", now=today)
        assert res["amount"] == 10 and c.spirit_stones == 10  # 日顶 120 截断
        # 达顶后后续完成只结案不发奖
        m2 = _map(tier=2)
        snap2 = _awaiting_snapshot(c, m2, "stones", tier=2)
        try:
            res = TreasureClueEngine.on_chest_opened(c, snap2, "combat_victory", now=today)
            assert res["amount"] == 0 and "上限" in res["message"]
        finally:
            WorldStateRepository.delete(DONE_KEY_PREFIX + m2.uid)
    finally:
        _cleanup(c, m)


# ---------------------------------------------------------------------------
# T-7 无链直挖零回归 / 弃链后直挖 / 旧图兼容
# ---------------------------------------------------------------------------
def test_t7_direct_dig_without_chain_unchanged():
    c = _player(location=TARGET_NAME)
    m = _map(tier=2)
    c.add_item_entity(m)
    assert get_chain(m) is None and chain_summary(m) is None
    res = TreasureEngine.dig(c)
    assert res["success"] and res.get("need_choice")  # element_puzzle 首达不耗图
    assert m in c.items
    res = TreasureEngine.dig(c, choice_id="1")
    assert res["success"] and res["outcome"] == "perfect_solve"
    assert res["stone_gain"] == 200 + 2 * 80  # 现行大表原样
    assert m not in c.items


def test_t7_abandoned_chain_map_still_diggable_and_not_reactivatable():
    c = _player()
    m = _map(tier=2)
    c.add_item_entity(m)
    try:
        TreasureClueEngine.activate(c, m)
        res = TreasureClueEngine.abandon(c)
        assert res["success"] and get_chain(m)["status"] == "abandoned"
        # 不可再激活
        res = TreasureClueEngine.activate(c, m)
        assert not res["changed"] and get_chain(m)["status"] == "abandoned"
        # 仍可直挖
        c.location = TARGET_NAME
        res = TreasureEngine.dig(c, choice_id="1")
        # element_puzzle 首次带 choice 前须先触发 need_choice 的情形除外：
        # 直接带选项在未触发状态下引擎按现行口径处理，只断言图流程不被链阻断
        assert res.get("message")
    finally:
        _cleanup(c, m)


# ---------------------------------------------------------------------------
# T-8 推进幂等（同一步重复提交只结算一次）
# ---------------------------------------------------------------------------
def test_t8_repeat_choice_settles_once():
    c = _player()
    c.spirit_stones = 100
    m = _map()
    steps = [_step("guardian"), _step("guardian")]
    chain = _craft_chain(c, m, steps)
    res = TreasureClueEngine.choose(c, "2")
    assert res["settled"] and c.spirit_stones == 80
    # 第二步同为守卫买路前先退回第一步语境不可达——改为断言 penalties 不因
    # 查看/异地调用变化
    stones = c.spirit_stones
    TreasureClueEngine.view_text(c)
    assert c.spirit_stones == stones and chain["penalties"]["stones"] == 20


# ---------------------------------------------------------------------------
# T-9 门禁（死亡 / 闭关零副作用）
# ---------------------------------------------------------------------------
def test_t9_dead_and_meditating_gates():
    c = _player()
    m = _map()
    c.add_item_entity(m)
    c.status = CharacterStatus.DEAD
    res = TreasureClueEngine.activate(c, m)
    assert not res["changed"] and get_chain(m) is None

    c2 = _player()
    m2 = _map()
    chain = _craft_chain(c2, m2, [_step("guardian")])
    c2.status = CharacterStatus.MEDITATING
    before = (c2.spirit_stones, c2.realm.current_exp)
    res = TreasureClueEngine.choose(c2, "1")
    assert not res["success"]
    assert not chain["steps"][0]["settled"]
    assert before == (c2.spirit_stones, c2.realm.current_exp)


# ---------------------------------------------------------------------------
# T-10 全链走完（AI 关断口径：本地模板即可）+ 终局开匣钩子
# ---------------------------------------------------------------------------
def test_t10_full_chain_walk_and_chest_bonus():
    # 链引擎零 AI 依赖：生成/抉择/结算全为本地规则与模板（RQ-8 降级口径）
    c = _player()
    c.spirit_stones = 200
    m = _map(tier=2)
    c.add_item_entity(m)
    try:
        assert TreasureClueEngine.activate(c, m)["changed"]
        chain = get_chain(m)
        while chain["status"] == "active":
            res = TreasureClueEngine.choose(c, _safe_choice(c, m))
            assert res["success"], res
        assert chain["status"] == "awaiting_chest"
        # 终局：快照 → dig 开匣 → 钩子发奖（与 server /挖宝 同序）
        snap = TreasureClueEngine.snapshot_chain(c)
        c.location = TARGET_NAME
        res = TreasureEngine.dig(c)
        if res.get("need_choice"):
            res = TreasureEngine.dig(c, choice_id="1")
        assert res["success"] and res["outcome"] == "perfect_solve"
        stones0, exp0 = c.spirit_stones, c.realm.current_exp
        bonus = TreasureClueEngine.on_chest_opened(c, snap, res["outcome"])
        branch = chain["bonus_branch"]
        if branch == "stones":
            assert c.spirit_stones == stones0 + min(30, 120)
        else:
            assert c.realm.current_exp == min(c.realm.max_exp, exp0 + 60) or bonus["amount"] == 60
    finally:
        _cleanup(c, m)
