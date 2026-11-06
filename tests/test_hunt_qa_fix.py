"""QA 修复回归：QA-01 业力消解逐值对账 + QA-02 洗清结算裁定与边界。

- QA-01：settle_kill 业力总消解恰 20（add_merit 账本语义），sin<20 钳制、
  20–40 区间与旧双路的差异即修复点本身，逐值对账钉死。
- QA-02：OPEN 令 + 目标洗清 → 结算走 DISSOLVED，主诛者除凶旧赏不发
  （裁定见 docs/compose/spec/hunt.md）；血煞未清（仍 is_marked）与
  combat_fate 式「先置 DEAD 再结算」均不得误伤正常 SETTLED；
  无令实体兼容路径不复核、旧口径逐值不变（spec 验收 6 的边界钉死）。
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
from core.models import CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, loc=LOC_A, sin=0):
    c = WorldClock.create_new_character(f"qfix_{name}_{_tag()}", f"QF{name}{_tag()}")
    c.location = loc
    if sin:
        c.karma.add_sin(sin)
    CharacterRepository.save(c)
    return c


def _cleanup(*chars):
    ids = {c.id for c in chars if c}
    if ids:
        orders = hunt._load_orders()
        for tid in list(orders.keys()):
            if tid in ids:
                orders.pop(tid, None)
        hunt._save_orders(orders)
        d = hunt._load()
        for hid in list(d.keys()):
            rec = d[hid]
            tid = rec.get("target_id") if isinstance(rec, dict) else rec
            if hid in ids or tid in ids:
                d.pop(hid, None)
        hunt._save(d)
    for c in chars:
        if c is None:
            continue
        live = CharacterRepository.get_by_id(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


def _merit(cid):
    return CharacterRepository.get_by_id(cid).karma.merit_value


def _sin(cid):
    return CharacterRepository.get_by_id(cid).karma.sin_value


def _wash(char_id):
    v = CharacterRepository.get_by_id(char_id)
    v.karma.sin_value = 0
    v.karma.blood_mark_until = 0.0
    CharacterRepository.save(v)


# ---------------- QA-02 裁定：洗清击杀，主诛者旧赏不发 ----------------

def test_washed_kill_no_killer_reward_and_dissolved():
    victim = _char("裁凶", sin=120)
    killer = _char("裁主诛", sin=50)
    assist = _char("裁协剿")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(killer.id), victim.name)["success"]
        assert hunt.accept(CharacterRepository.get_by_id(assist.id), victim.name)["success"]
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_OPEN
        _wash(victim.id)
        assert not hunt.is_marked(CharacterRepository.get_by_id(victim.id))
        k_m0, k_s0, a_m0 = _merit(killer.id), _sin(killer.id), _merit(assist.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None and res.get("dissolved") is True, res
        assert res["merit"] == 0 and res["sin_reduced"] == 0 and res["assists"] == [], res
        # 裁定：旧赏是「除凶」之赏，目标已非凶犯——主诛者功德 +0、业力不消解
        assert _merit(killer.id) == k_m0, f"洗清后主诛者不应得除凶功德，实际 +{_merit(killer.id) - k_m0}"
        assert _sin(killer.id) == k_s0, "洗清后主诛者业力不应经除凶通道消解"
        assert _merit(assist.id) == a_m0
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_DISSOLVED
        d = hunt._load()
        assert all(
            (rec.get("target_id") if isinstance(rec, dict) else rec) != victim.id
            for rec in d.values()
        ), "DISSOLVED 须清全部猎手记录"
        # 幂等：猎手记录已弹，二次结算返回 None、零发放
        res2 = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res2 is None and _merit(killer.id) == k_m0 and _merit(assist.id) == a_m0
        print("✓ QA-02 裁定：洗清击杀 DISSOLVED、主诛旧赏不发、记录全清、二次结算 None")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- QA-01：业力总消解逐值对账 ----------------

def test_sin_reduction_matches_spec_across_values():
    """spec：击杀者功德 +40 / 业力总消解恰 20（sin 不足时钳到 0）。
    旧双路在 sin<20 时与新口径同为全清（钳制一致）；20–40 区间旧为全清、
    新恰 −20；≥40 旧 −40、新 −20——逐值钉死新口径。"""
    victim = _char("账值凶", sin=200)
    hunters = []
    try:
        for s0 in (0, 5, 10, 19, 20, 21, 30, 39, 40, 41, 100):
            h = _char(f"值猎{s0}", sin=s0)
            hunters.append(h)
            assert hunt.accept(CharacterRepository.get_by_id(h.id), victim.name)["success"]
            m0 = _merit(h.id)
            assert _sin(h.id) == s0
            res = hunt.settle_kill(
                CharacterRepository.get_by_id(h.id),
                CharacterRepository.get_by_id(victim.id),
            )
            assert res is not None and res["merit"] == 40 and res["sin_reduced"] == 20, res
            assert _merit(h.id) == m0 + 40
            expect = max(0, s0 - 20)
            assert _sin(h.id) == expect, (
                f"sin={s0}：总消解应恰 20（钳制后落 {expect}），实际 {_sin(h.id)}"
            )
        print("✓ QA-01 逐值对账：sin∈{0,5,10,19,20,21,30,39,40,41,100} 总消解恰 20/钳制一致")
    finally:
        _cleanup(victim, *hunters)


# ---------------- 边界：血煞未清仍属凶犯，不得误判洗清 ----------------

def test_blood_mark_only_target_still_settles():
    victim = _char("煞凶", sin=120)
    killer = _char("煞主诛")
    assist = _char("煞协剿")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(killer.id), victim.name)["success"]
        assert hunt.accept(CharacterRepository.get_by_id(assist.id), victim.name)["success"]
        # 只清业力、血煞未到期：is_marked 仍为真（血煞或业力其一即可）
        v = CharacterRepository.get_by_id(victim.id)
        v.karma.sin_value = 0
        CharacterRepository.save(v)
        assert hunt.is_marked(CharacterRepository.get_by_id(victim.id))
        k0, a0 = _merit(killer.id), _merit(assist.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None and not res.get("dissolved"), res
        assert _merit(killer.id) == k0 + 40 and _merit(assist.id) == a0 + hunt.ASSIST_MERIT
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_SETTLED
        print("✓ 边界：仅清业力、血煞未消 → 仍按 SETTLED 结算")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- 边界：combat_fate 先置 DEAD 再结算（本次击杀致死） ----------------

def test_dead_but_marked_target_settles_normally():
    """combat_fate 先把 defender 置 DEAD 再调 settle_kill：DEAD 是本次击杀的
    正常结果，结算点不得据此判消散——仍 SETTLED、旧赏与协剿照发。"""
    victim = _char("死凶", sin=200)
    killer = _char("死主诛")
    assist = _char("死协剿")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(killer.id), victim.name)["success"]
        assert hunt.accept(CharacterRepository.get_by_id(assist.id), victim.name)["success"]
        v = CharacterRepository.get_by_id(victim.id)
        v.status = CharacterStatus.DEAD  # 模拟 combat_fate 击杀后、结算前的状态
        CharacterRepository.save(v)
        k0, a0 = _merit(killer.id), _merit(assist.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None and not res.get("dissolved"), res
        assert _merit(killer.id) == k0 + 40 and _merit(assist.id) == a0 + hunt.ASSIST_MERIT
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_SETTLED
        print("✓ 边界：先置 DEAD（本次击杀致死）不误判消散，SETTLED 照常")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- 边界：仅业力达阈（无血煞）同样是凶犯 ----------------

def test_sin_only_marked_target_settles():
    """is_marked 是 OR 口径：仅业力 ≥80、血煞未沾，亦不得误判洗清。"""
    victim = _char("业凶")
    v = CharacterRepository.get_by_id(victim.id)
    v.karma.sin_value = 120
    v.karma.blood_mark_until = 0.0
    CharacterRepository.save(v)
    killer = _char("业主诛")
    assist = _char("业协剿")
    try:
        assert hunt.is_marked(CharacterRepository.get_by_id(victim.id))
        assert hunt.accept(CharacterRepository.get_by_id(killer.id), victim.name)["success"]
        assert hunt.accept(CharacterRepository.get_by_id(assist.id), victim.name)["success"]
        k0, a0 = _merit(killer.id), _merit(assist.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None and not res.get("dissolved"), res
        assert _merit(killer.id) == k0 + 40 and _merit(assist.id) == a0 + hunt.ASSIST_MERIT
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_SETTLED
        print("✓ 边界：仅业力达阈（无血煞）→ SETTLED 照常")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- 边界：过期与洗清同时成立 → 过期优先（与 sweep 同序） ----------------

def test_expired_and_washed_order_expires_first():
    """复核顺序与 _sweep_orders 一致：过期优先于洗清——走 EXPIRED、
    主诛旧赏照发（M3 口径）、协剿不发，不走 DISSOLVED。"""
    victim = _char("双终凶", sin=200)
    killer = _char("双终主诛")
    assist = _char("双终协剿")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(killer.id), victim.name)["success"]
        assert hunt.accept(CharacterRepository.get_by_id(assist.id), victim.name)["success"]
        _wash(victim.id)
        orders = hunt._load_orders()
        orders[victim.id]["expires_at"] = time.time() - 10
        orders[victim.id]["issued_at"] = time.time() - 200000
        hunt._save_orders(orders)
        k0, a0 = _merit(killer.id), _merit(assist.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None and not res.get("dissolved"), res
        assert res["merit"] == 40 and res["assists"] == [], res
        assert _merit(killer.id) == k0 + 40 and _merit(assist.id) == a0
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_EXPIRED
        print("✓ 边界：过期+洗清同时成立 → EXPIRED 优先、旧赏照发、无协剿")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- 边界：无令实体兼容路径不复核（spec 验收 6） ----------------

def test_legacy_no_order_path_not_rechecked():
    """直写 hunts KV、无令实体：洗清复核只属令层，此路径旧口径逐值不变。"""
    victim = _char("旧凶", sin=120)
    killer = _char("旧猎")
    prior = WorldStateRepository.get(hunt._HUNT_KEY)
    try:
        orders = hunt._load_orders()
        orders.pop(victim.id, None)
        hunt._save_orders(orders)
        state = dict(prior or {})
        state[killer.id] = {"target_id": victim.id, "expires_at": time.time() + 3600}
        WorldStateRepository.set(hunt._HUNT_KEY, state)
        _wash(victim.id)  # 即便目标已洗清：无令路径不复核（兼容口径）
        m0 = _merit(killer.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None and res["merit"] == 40 and res["assists"] == [], res
        assert _merit(killer.id) == m0 + 40
        print("✓ 边界：无令实体兼容路径不复核、旧口径逐值不变")
    finally:
        if prior is None:
            WorldStateRepository.delete(hunt._HUNT_KEY)
        else:
            WorldStateRepository.set(hunt._HUNT_KEY, prior)
        _cleanup(victim, killer)
