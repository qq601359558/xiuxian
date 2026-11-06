"""QA2-S3 回归：非接令者击杀路径的反悬赏双向清理覆盖。

缺陷：settle_kill 在击杀者并非该凶犯接令猎人时（无猎手记录，或记录
指向他人）于函数头部提前 return None，反悬赏清理整块被跳过，死者作
target 方向的 counter_hunts 条目残留（QA2-01 清理只覆盖主结算路径）。

修复口径（spec hunt.md「反悬赏清理语义」QA2-S3 裁定）：
- settle_kill 仅由 combat_fate 在 outcome == "kill"（受害者已置 DEAD）
  后调用，故早退路径同样确认受害者已死，须执行与主路径同源的双向
  清理（共用 _clear_counter_hunts）。
- 该路径只清理：不发任何除凶奖励、不动猎手记录、订单终态仍走既有
  惰性 sweep（settle 后订单仍 OPEN，sweep 访问时才 DISSOLVED）。
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


def _char(name, sin=0):
    c = WorldClock.create_new_character(f"q2s3_{name}_{_tag()}", f"Q2S{name}{_tag()}")
    c.location = LOC_A
    if sin:
        c.karma.add_sin(sin)
    CharacterRepository.save(c)
    return c


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _sin_marked(char):
    """只以业力标记（清血煞标记，隔离 sin 口径，与 QA2 既有回归同法）。"""
    c = _get(char.id)
    c.karma.blood_mark_until = 0.0
    CharacterRepository.save(c)
    assert hunt.is_marked(_get(char.id))
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
        live = _get(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


def _kill_via_settle(killer, victim):
    """按 combat_fate 的真实调用口径：先置 DEAD，再调 settle_kill。"""
    v = _get(victim.id)
    v.status = CharacterStatus.DEAD
    CharacterRepository.save(v)
    return hunt.settle_kill(_get(killer.id), _get(victim.id))


def test_non_hunter_kill_clears_counter_all_directions():
    victim = _sin_marked(_char("非接犯", sin=120))
    reg_hunter = _char("非接令")   # 已登记接令的猎人（非击杀者）
    outsider = _char("非接外")     # 击杀者：无任何猎手记录
    third = _char("非接三")
    other = _char("非接路")
    snap = WorldStateRepository.get(hunt._COUNTER_KEY)
    try:
        # 凶犯有 OPEN 令、册上有登记猎人——但下手的是局外人
        assert hunt.accept(_get(reg_hunter.id), _get(victim.id).name)["success"]
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_OPEN

        cd = dict(snap or {})
        # A：死者作 target（键在登记猎人名下）
        cd[reg_hunter.id] = {"target_id": victim.id, "hunter_id": reg_hunter.id, "paid": 50}
        # B：死者作 hunter（键 == victim.id）
        cd[victim.id] = {"target_id": third.id, "hunter_id": victim.id, "paid": 50}
        # C：死者作 hunter 但键在异名下（hunter_id 方向守卫）
        odd_key = f"q2s3_odd_{_tag()}"
        cd[odd_key] = {"target_id": other.id, "hunter_id": victim.id, "paid": 50}
        # D：无关条目与非 dict 脏条目：必须保留
        cd[third.id] = {"target_id": other.id, "hunter_id": third.id, "paid": 50}
        cd["q2s3_dirty"] = "not-a-dict"
        WorldStateRepository.set(hunt._COUNTER_KEY, cd)

        merit_out = _get(outsider.id).karma.merit_value
        merit_reg = _get(reg_hunter.id).karma.merit_value

        res = _kill_via_settle(outsider, victim)
        assert res is None, res  # 非接令路径口径不变：无结算返回

        cd2 = WorldStateRepository.get(hunt._COUNTER_KEY) or {}
        assert reg_hunter.id not in cd2, "死者作 target 的条目应清（A）"
        assert victim.id not in cd2, "死者作 hunter 的条目应清（B）"
        assert odd_key not in cd2, "hunter_id == 死者 的异键条目应清（C）"
        assert cd2.get(third.id, {}).get("target_id") == other.id, "无关条目不得误删（D）"
        assert cd2.get("q2s3_dirty") == "not-a-dict", "脏条目应原样保留且不抛错"

        # 只清理、不发奖：击杀者无除凶功德，登记猎人无协剿功德
        assert _get(outsider.id).karma.merit_value == merit_out, "非接令击杀不得发除凶功德"
        assert _get(reg_hunter.id).karma.merit_value == merit_reg, "早退路径不得发协剿功德"

        # 订单口径与修复前一致：settle 不提前终结，仍 OPEN；
        # 终态由既有惰性 sweep 在访问时推进（目标已死 → DISSOLVED）
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_OPEN, "早退路径不得提前结算订单"
        hunt._sweep_orders()
        assert hunt.get_order(victim.id)["status"] == hunt.ORDER_DISSOLVED
        print("✓ 非接令者击杀：反悬赏三方向全清、无关保留、无发奖、订单惰性口径不变")
    finally:
        if snap is None:
            WorldStateRepository.set(hunt._COUNTER_KEY, {})
        else:
            WorldStateRepository.set(hunt._COUNTER_KEY, snap)
        _cleanup(victim, reg_hunter, outsider, third, other)


def test_other_target_hunter_kills_unmarked_victim():
    """击杀者猎手记录指向他人（tid != victim.id 的另一变体）击杀未标记
    普通角色：清理仍按「死亡」触发、只删死者相关条目，无关条目保留，
    击杀者自己的猎手记录不被早退路径动过。"""
    busy = _char("他令主")          # 击杀者：正接着另一凶犯的令
    real_target = _sin_marked(_char("他令犯", sin=120))
    plain = _char("寻常人")          # 被杀者：未标记普通角色
    third = _char("他令三")
    other = _char("他令路")
    snap = WorldStateRepository.get(hunt._COUNTER_KEY)
    try:
        assert hunt.accept(_get(busy.id), _get(real_target.id).name)["success"]

        cd = dict(snap or {})
        # 死者相关：某人对寻常人挂的反悬赏（target 方向）
        cd[third.id] = {"target_id": plain.id, "hunter_id": third.id, "paid": 50}
        # 无关条目：必须保留
        cd[other.id] = {"target_id": third.id, "hunter_id": other.id, "paid": 50}
        WorldStateRepository.set(hunt._COUNTER_KEY, cd)

        merit_busy = _get(busy.id).karma.merit_value
        res = _kill_via_settle(busy, plain)
        assert res is None, res

        cd2 = WorldStateRepository.get(hunt._COUNTER_KEY) or {}
        assert third.id not in cd2, "死者作 target 的条目应清（清理以死亡为触发，不以标记为前提）"
        assert cd2.get(other.id, {}).get("target_id") == third.id, "无关条目不得误删"
        assert _get(busy.id).karma.merit_value == merit_busy, "早退路径不得发功德"
        # 击杀者指向真凶犯的猎手记录完好（早退路径不动猎手记录）
        tgt = hunt.my_target(_get(busy.id))
        assert tgt is not None and tgt.id == real_target.id, "击杀者原接令记录不应被动"
        print("✓ 记录指向他人者击杀未标记者：死者条目清、无关保留、原接令记录完好")
    finally:
        if snap is None:
            WorldStateRepository.set(hunt._COUNTER_KEY, {})
        else:
            WorldStateRepository.set(hunt._COUNTER_KEY, snap)
        _cleanup(busy, real_target, plain, third, other)
