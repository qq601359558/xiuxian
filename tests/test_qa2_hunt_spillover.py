"""QA 第二轮 · 重点 1：QA-01/QA-02 修复外溢核查。

- 两类凶犯（仅业力达阈 / 仅血煞标记）在「仍标记」时 SETTLED 逐值、
  「洗清」时 DISSOLVED 逐值（QA-02 复核不误伤、不漏判）。
- combat_fate 式先置 DEAD 再 settle_kill 的正常路径不得被洗清复核误判。
- 过期 + 洗清同时成立时按 spec「过期优先」（与 _sweep_orders 同序）。
- 反悬赏清理在 SETTLED / DISSOLVED 两路后是否完整（双向条目）。
- 同一击杀：悬赏板（CLI 口径 settle_on_kill）与除凶同杀分账逐笔对账；
  同一角色多功德来源（诺言/除凶/悬赏）连续入账，业力消解逐笔恰为
  add_merit 账本语义 v//2 一次（QA-01 的推广形式）。
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
from core.bounty import BountyEngine
from core.clock import WorldClock
from core.models import CharacterStatus
from core.promises import PromiseEngine
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, loc=LOC_A, sin=0, stones=0):
    c = WorldClock.create_new_character(f"qa2_{name}_{_tag()}", f"QA2{name}{_tag()}")
    c.location = loc
    if sin:
        c.karma.add_sin(sin)
    if stones:
        c.spirit_stones += stones
    CharacterRepository.save(c)
    return c


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _merit(cid):
    return _get(cid).karma.merit_value


def _sin(cid):
    return _get(cid).karma.sin_value


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
        cd = WorldStateRepository.get(hunt._COUNTER_KEY) or {}
        for k in list(cd.keys()):
            rec = cd[k] or {}
            if k in ids or rec.get("target_id") in ids or rec.get("hunter_id") in ids:
                cd.pop(k, None)
        WorldStateRepository.set(hunt._COUNTER_KEY, cd)
    for c in chars:
        if c is None:
            continue
        live = _get(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


def _sin_only(char_id, sin=120):
    """仅业力达阈型凶犯：业力 >= 80、无血煞标记。"""
    v = _get(char_id)
    v.karma.sin_value = sin
    v.karma.blood_mark_until = 0.0
    CharacterRepository.save(v)
    assert hunt.is_marked(_get(char_id))
    return v


def _blood_only(char_id, sin=30):
    """仅血煞标记型凶犯：业力 < 80、血煞未清。"""
    v = _get(char_id)
    v.karma.sin_value = sin
    v.karma.blood_mark_until = time.time() + 86400.0
    CharacterRepository.save(v)
    assert hunt.is_marked(_get(char_id))
    return v


def _accept(killer, assist, victim):
    assert hunt.accept(_get(killer.id), victim.name)["success"]
    if assist is not None:
        assert hunt.accept(_get(assist.id), victim.name)["success"]
    assert hunt.get_order(victim.id)["status"] == hunt.ORDER_OPEN


# ---------------- 两类凶犯：仍标记 → SETTLED 逐值 ----------------

def test_sin_only_marked_settles_normally():
    victim = _sin_only(_char("罪业凶").id, sin=120)
    killer = _char("罪主诛", sin=50)
    assist = _char("罪协剿")
    try:
        _accept(killer, assist, victim)
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is not True, res
        assert res["merit"] == 40 and res["sin_reduced"] == 20, res
        assert _merit(killer.id) == 40 and _sin(killer.id) == 30  # 50 - 20 恰一次
        assert _merit(assist.id) == 15
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_SETTLED
        print("✓ 仅业力型凶犯（仍标记）：SETTLED、主诛 +40/−20、协剿 +15")
    finally:
        _cleanup(victim, killer, assist)


def test_blood_only_marked_settles_normally():
    victim = _blood_only(_char("血煞凶").id, sin=30)
    killer = _char("血主诛", sin=50)
    assist = _char("血协剿")
    try:
        _accept(killer, assist, victim)
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is not True, res
        assert _merit(killer.id) == 40 and _sin(killer.id) == 30
        assert _merit(assist.id) == 15
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_SETTLED
        print("✓ 仅血煞型凶犯（仍标记）：SETTLED 逐值一致")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- 两类凶犯：洗清 → DISSOLVED 逐值 ----------------

def test_sin_only_washed_dissolves():
    victim = _sin_only(_char("罪洗").id, sin=80)  # 恰在阈值上：仍标记
    killer = _char("罪洗主", sin=50)
    assist = _char("罪洗协")
    try:
        _accept(killer, assist, victim)
        v = _get(victim.id)
        v.karma.sin_value = 79  # 跌破阈值 = 洗清
        CharacterRepository.save(v)
        assert not hunt.is_marked(_get(victim.id))
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is True, res
        assert _merit(killer.id) == 0 and _sin(killer.id) == 50
        assert _merit(assist.id) == 0
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_DISSOLVED
        print("✓ 仅业力型洗清（80→79）：DISSOLVED、零发放")
    finally:
        _cleanup(victim, killer, assist)


def test_blood_only_washed_dissolves():
    victim = _blood_only(_char("血洗").id, sin=30)
    killer = _char("血洗主", sin=50)
    assist = _char("血洗协")
    try:
        _accept(killer, assist, victim)
        v = _get(victim.id)
        v.karma.blood_mark_until = 1.0  # 血煞已过期 = 洗清（业力仍 <80）
        CharacterRepository.save(v)
        assert not hunt.is_marked(_get(victim.id))
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is True, res
        assert _merit(killer.id) == 0 and _merit(assist.id) == 0
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_DISSOLVED
        print("✓ 仅血煞型洗清（标记过期）：DISSOLVED、零发放")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- combat_fate 先置 DEAD 的正常路径 ----------------

def test_dead_first_still_marked_settles():
    """combat_fate 先把 defender 置 DEAD 再调 settle_kill：DEAD 是本次击杀
    的正常结果，仍标记时必须走 SETTLED，不得被洗清复核误判为消散。"""
    victim = _sin_only(_char("先死").id, sin=120)
    killer = _char("先死主", sin=50)
    assist = _char("先死协")
    try:
        _accept(killer, assist, victim)
        v = _get(victim.id)
        v.status = CharacterStatus.DEAD  # 模拟 combat_fate 击杀点先置 DEAD
        v.lifespan.death_timestamp = 0.0
        CharacterRepository.save(v)
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is not True, res
        assert res["merit"] == 40 and _merit(assist.id) == 15
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_SETTLED
        print("✓ 先置 DEAD + 仍标记：SETTLED 正常（combat_fate 路径不误伤）")
    finally:
        _cleanup(victim, killer, assist)


def test_expired_beats_washed_at_settle():
    """过期 + 洗清同时成立：spec 裁定过期优先（与 sweep 同序），走 EXPIRED、
    主诛旧赏照发、协剿不发。"""
    victim = _sin_only(_char("期洗").id, sin=120)
    killer = _char("期洗主", sin=50)
    assist = _char("期洗协")
    try:
        _accept(killer, assist, victim)
        orders = hunt._load_orders()
        orders[victim.id]["expires_at"] = time.time() - 10.0
        hunt._save_orders(orders)
        v = _get(victim.id)
        v.karma.sin_value = 0
        v.karma.blood_mark_until = 0.0
        CharacterRepository.save(v)
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is not True, res
        assert res["merit"] == 40 and res["assists"] == [], res
        assert _merit(killer.id) == 40 and _sin(killer.id) == 30
        assert _merit(assist.id) == 0
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_EXPIRED
        print("✓ 过期+洗清：EXPIRED 优先、旧赏照发、协剿不发")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- 反悬赏清理完整性（SETTLED / DISSOLVED 两路） ----------------

def _place_counter(victim, killer, assist):
    _accept(killer, assist, victim)
    v = _get(victim.id)
    v.spirit_stones += 200
    CharacterRepository.save(v)
    res = hunt.place_counter(_get(victim.id))
    assert res["success"], res
    cd = WorldStateRepository.get(hunt._COUNTER_KEY) or {}
    mine = {k: r for k, r in cd.items() if (r or {}).get("target_id") == victim.id}
    assert mine, "反悬赏应已登记（target=被害者）"
    return mine


def test_counter_cleanup_after_settled_kill():
    victim = _sin_only(_char("反结").id, sin=120)
    killer = _char("反结主")
    assist = _char("反结协")
    try:
        _place_counter(victim, killer, assist)
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is not True, res
        cd = WorldStateRepository.get(hunt._COUNTER_KEY) or {}
        residue = {
            k: r for k, r in cd.items()
            if (r or {}).get("target_id") == victim.id or (r or {}).get("hunter_id") == victim.id
        }
        assert not residue, f"凶犯已死，其生前反悬赏条目应清理，残留：{residue}"
        print("✓ SETTLED 后反悬赏双向条目全清")
    finally:
        _cleanup(victim, killer, assist)


def test_counter_cleanup_after_washed_kill():
    victim = _sin_only(_char("反洗").id, sin=120)
    killer = _char("反洗主")
    assist = _char("反洗协")
    try:
        _place_counter(victim, killer, assist)
        v = _get(victim.id)
        v.karma.sin_value = 0
        v.karma.blood_mark_until = 0.0
        CharacterRepository.save(v)
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is True, res
        cd = WorldStateRepository.get(hunt._COUNTER_KEY) or {}
        residue = {
            k: r for k, r in cd.items()
            if (r or {}).get("target_id") == victim.id or (r or {}).get("hunter_id") == victim.id
        }
        assert not residue, f"洗清消散后反悬赏条目应清理，残留：{residue}"
        # 残留条目不得被误触发：被害者已死，settle_hunter_slain 不应凭空发功德
        out = hunt.settle_hunter_slain(_get(assist.id), _get(victim.id))
        assert out is None
        print("✓ DISSOLVED 后反悬赏双向条目全清且不可误触发")
    finally:
        _cleanup(victim, killer, assist)


# ---------------- 同杀分账：悬赏板 × 除凶逐笔对账 ----------------

def test_bounty_and_hunt_same_kill_accounting():
    """同一击杀两通道：除凶（功德+40/业力恰 −20）+ 悬赏板（灵石玩家出资、
    功德 +BOUNTY_HUNTER_MERIT=15、账本语义消解 7）。逐笔断言，防重复消解/发钱。
    注：hunt.md 对照表记「悬赏功德 20/令」与 config 常量 15 矛盾（常量自首版
    入库未变），本用例按代码常量断言，文档矛盾另列 QA2-02。"""
    victim = _sin_only(_char("双账").id, sin=120)
    killer = _char("双账主", sin=100)
    issuer = _char("双账主顾", stones=1000)
    try:
        from storage.db import BountyRepository

        placed = BountyEngine.place_bounty(_get(issuer.id), _get(victim.id), 200)
        assert placed["success"], placed
        bounty = placed["bounty"]
        BountyRepository.save(bounty)  # 引擎不落库，调用方落库（双端同口径）
        claimed = BountyEngine.claim_bounty(_get(killer.id), bounty)
        assert claimed["success"], claimed
        BountyRepository.save(bounty)
        assert hunt.accept(_get(killer.id), victim.name)["success"]
        ks0, km0 = _get(killer.id).spirit_stones, _merit(killer.id)
        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res["merit"] == 40, res
        assert _merit(killer.id) == km0 + 40
        assert _sin(killer.id) == 80, f"除凶后业力应恰 100-20=80，实际 {_sin(killer.id)}"
        open_bs = BountyRepository.list_open_for_target(victim.id)
        killer_obj = _get(killer.id)
        pay = BountyEngine.settle_on_kill(killer_obj, _get(victim.id), open_bs)
        # settle_on_kill 为「调用方落库」口径（cli/main.py 同款：save_many + save 角色）
        BountyRepository.save_many(open_bs)
        CharacterRepository.save(killer_obj)
        assert pay and pay.get("success", True), pay
        k = _get(killer.id)
        assert k.spirit_stones == ks0 + 200, f"悬赏灵石应恰 +200（玩家出资），实际 {k.spirit_stones - ks0}"
        assert _merit(killer.id) == km0 + 55, "功德 = 除凶 40 + 悬赏 15（BOUNTY_HUNTER_MERIT）"
        assert _sin(killer.id) == 73, (
            f"悬赏 add_merit(15) 账本消解 7：80→73，实际 {_sin(killer.id)}（多消解即双计）"
        )
        # 幂等：二次结算两通道均零发放
        pay2 = BountyEngine.settle_on_kill(_get(killer.id), _get(victim.id), open_bs)
        assert not pay2 or not pay2.get("paid")
        assert _get(killer.id).spirit_stones == ks0 + 200
        print("✓ 同杀分账：除凶 +40/−20、悬赏 +200 石/+15 功德/−7 业力，逐笔恰一次")
    finally:
        _cleanup(victim, killer, issuer)


# ---------------- 多来源连续入账逐笔对账（QA-01 推广） ----------------

def test_multi_source_merit_sequence_ledger():
    """同一角色连续三源入账：诺言践诺 +10 → 除凶 +40 → 悬赏 +15。
    每笔 add_merit 的业力消解恰 v//2 一次：sin 100 → 95 → 75 → 68。"""
    hero = _char("连账", sin=100)
    npc = WorldClock.create_new_character(f"npc_qa2_诺友_{_tag()}", f"QA2诺友{_tag()}")
    npc.location = LOC_A
    CharacterRepository.save(npc)
    victim = _sin_only(_char("连账凶").id, sin=120)
    issuer = _char("连账主顾", stones=1000)
    try:
        loc = "青云宗外门山门"
        made = PromiseEngine.make_promise(_get(hero.id), _get(npc.id), "arrive", loc)
        assert made["success"], made
        note = PromiseEngine.note_arrival(_get(hero.id), loc)
        assert note, "抵达事实应践诺"
        assert _merit(hero.id) == 10 and _sin(hero.id) == 95, (
            f"践诺后 merit/sin 应为 10/95，实际 {_merit(hero.id)}/{_sin(hero.id)}"
        )
        from storage.db import BountyRepository

        placed = BountyEngine.place_bounty(_get(issuer.id), _get(victim.id), 200)
        assert placed["success"], placed
        BountyRepository.save(placed["bounty"])
        claimed = BountyEngine.claim_bounty(_get(hero.id), placed["bounty"])
        assert claimed["success"], claimed
        BountyRepository.save(placed["bounty"])
        assert hunt.accept(_get(hero.id), victim.name)["success"]
        res = hunt.settle_kill(_get(hero.id), _get(victim.id))
        assert res is not None and res["merit"] == 40, res
        assert _merit(hero.id) == 50 and _sin(hero.id) == 75, (
            f"除凶后应为 50/75，实际 {_merit(hero.id)}/{_sin(hero.id)}"
        )
        open_bs = BountyRepository.list_open_for_target(victim.id)
        hero_obj = _get(hero.id)
        pay = BountyEngine.settle_on_kill(hero_obj, _get(victim.id), open_bs)
        BountyRepository.save_many(open_bs)
        CharacterRepository.save(hero_obj)
        assert pay, pay
        assert _merit(hero.id) == 65 and _sin(hero.id) == 68, (
            f"悬赏后应为 65/68，实际 {_merit(hero.id)}/{_sin(hero.id)}"
        )
        print("✓ 多源连续入账：诺言/除凶/悬赏逐笔消解恰一次（100→95→75→68）")
    finally:
        _cleanup(hero, npc, victim, issuer)
