"""F15 除凶令状态机收尾：发布/接令上限/追凶情报/协剿分账/单通道对账/幂等/终态/弃令/双端/旧档兼容"""
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
from core.market import MarketEngine
from core.models import CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "落霞山灵泉"          # region 东荒·青州
LOC_B = "万剑仙门峰"          # region 中土·万岳
REGION_A = "东荒·青州"
REGION_B = "中土·万岳"


def _tag() -> str:
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, loc=LOC_A, sin=0, tier=2):
    c = WorldClock.create_new_character(f"hx_{name}_{_tag()}", f"{name}{_tag()}")
    c.location = loc
    c.realm.tier = tier
    c.born_at = time.time() - 80 * 3600.0
    if sin:
        c.karma.add_sin(sin)
    CharacterRepository.save(c)
    return c


def _cleanup(*chars):
    """零残留：清自造角色相关的令/猎手记录，角色处决。"""
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


def _merit(char_id):
    return CharacterRepository.get_by_id(char_id).karma.merit_value


def _sin(char_id):
    return CharacterRepository.get_by_id(char_id).karma.sin_value


# ---------------- 发布：阈值与去重 ----------------

def test_issue_threshold_and_dedup():
    marked = _char("阈值凶", sin=120)
    clean = _char("清白客", sin=0)
    try:
        assert hunt.is_marked(CharacterRepository.get_by_id(marked.id))
        assert not hunt.is_marked(CharacterRepository.get_by_id(clean.id))
        assert hunt.ensure_order(CharacterRepository.get_by_id(clean.id)) is None
        o1 = hunt.ensure_order(CharacterRepository.get_by_id(marked.id))
        assert o1 and o1["status"] == hunt.ORDER_OPEN
        o2 = hunt.ensure_order(CharacterRepository.get_by_id(marked.id))
        assert o2["order_id"] == o1["order_id"], "同凶犯不得重复发令"
        board = hunt.format_board()
        assert marked.name in board
        o3 = hunt.get_order(marked.id)
        assert o3["order_id"] == o1["order_id"]
        print("✓ 发令阈值与去重")
    finally:
        _cleanup(marked, clean)


# ---------------- 接令：令侧登记与上限 ----------------

def test_accept_registers_and_cap():
    target = _char("满员凶", sin=150)
    hunters = [_char(f"接令{i}") for i in range(hunt.ORDER_MAX_HUNTERS + 1)]
    try:
        for h in hunters[: hunt.ORDER_MAX_HUNTERS]:
            r = hunt.accept(CharacterRepository.get_by_id(h.id), target.name)
            assert r["success"], r
        order = hunt.get_order(target.id)
        assert len(order["hunters"]) == hunt.ORDER_MAX_HUNTERS
        r6 = hunt.accept(CharacterRepository.get_by_id(hunters[-1].id), target.name)
        assert r6["success"] is False and "已满" in r6["message"], r6
        # 已在令中者重复接令不占新位
        r = hunt.accept(CharacterRepository.get_by_id(hunters[0].id), target.name)
        assert r["success"], r
        assert len(hunt.get_order(target.id)["hunters"]) == hunt.ORDER_MAX_HUNTERS
        print("✓ 接令登记与 5 人上限")
    finally:
        _cleanup(target, *hunters)


def test_abandon_unregisters_order_stays_open():
    target = _char("弃令凶", sin=150)
    a = _char("弃令甲")
    b = _char("弃令乙")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(a.id), target.name)["success"]
        assert hunt.accept(CharacterRepository.get_by_id(b.id), target.name)["success"]
        r = hunt.abandon(CharacterRepository.get_by_id(a.id))
        assert r["success"]
        order = hunt.get_order(target.id)
        assert order["status"] == hunt.ORDER_OPEN
        assert a.id not in order["hunters"] and b.id in order["hunters"]
        print("✓ 弃令摘除登记、令不终结")
    finally:
        _cleanup(target, a, b)


# ---------------- 追凶：区域快照与刷新间隔 ----------------

def test_track_region_snapshot_and_refresh():
    target = _char("行踪凶", loc=LOC_A, sin=150)
    h = _char("追凶客", loc=LOC_A)
    try:
        assert hunt.accept(CharacterRepository.get_by_id(h.id), target.name)["success"]
        t0 = time.time()
        r = hunt.track(CharacterRepository.get_by_id(h.id), now=t0)
        assert r["success"], r
        assert r["region"] == REGION_A == MarketEngine.region_of(LOC_A)
        assert LOC_A not in r["message"], "追凶不得泄精确地点"
        # 凶犯迁往异区，刷新间隔内仍是旧快照
        tv = CharacterRepository.get_by_id(target.id)
        tv.location = LOC_B
        CharacterRepository.save(tv)
        r2 = hunt.track(CharacterRepository.get_by_id(h.id), now=t0 + 100)
        assert r2["region"] == REGION_A, r2
        # 过间隔刷新为新区
        r3 = hunt.track(CharacterRepository.get_by_id(h.id), now=t0 + hunt.TRACK_REFRESH_SECONDS + 10)
        assert r3["region"] == REGION_B, r3
        print("✓ 追凶区域快照与刷新间隔")
    finally:
        _cleanup(target, h)


def test_track_requires_accept():
    h = _char("无令客")
    try:
        r = hunt.track(CharacterRepository.get_by_id(h.id))
        assert r["success"] is False and "未接" in r["message"]
        print("✓ 追凶须先接令")
    finally:
        _cleanup(h)


# ---------------- 结算：分账数值 + 幂等 + 单通道 ----------------

def test_settle_split_and_idempotent():
    target = _char("围剿凶", loc=LOC_A, sin=200)
    killer = _char("主诛者", loc=LOC_A)
    assist = _char("协剿者", loc=LOC_A)
    away = _char("远方令友", loc=LOC_B)
    bystander = _char("同场路人", loc=LOC_A)
    for h in (killer, assist, away):
        assert hunt.accept(CharacterRepository.get_by_id(h.id), target.name)["success"]
    k0, a0, w0, b0 = (_merit(x.id) for x in (killer, assist, away, bystander))
    ks0, ts0 = killer.spirit_stones, target.spirit_stones
    try:
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(target.id),
        )
        assert res is not None and res["merit"] == 40 and res["sin_reduced"] == 20, res
        assert [a["name"] for a in res["assists"]] == [assist.name], res
        # 数值断言：主诛 +40、同场协剿 +15、远方与路人 0；除凶通道不发灵石
        assert _merit(killer.id) == k0 + 40
        assert _merit(assist.id) == a0 + hunt.ASSIST_MERIT
        assert _merit(away.id) == w0 and _merit(bystander.id) == b0
        assert CharacterRepository.get_by_id(killer.id).spirit_stones == ks0
        assert CharacterRepository.get_by_id(assist.id).spirit_stones >= 0
        # 令终态 + 全部猎手记录清除
        assert hunt.get_order(target.id)["status"] == hunt.ORDER_SETTLED
        d = hunt._load()
        assert all(
            (rec.get("target_id") if isinstance(rec, dict) else rec) != target.id
            for rec in d.values()
        )
        # 幂等：二次结算零发放
        res2 = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(target.id),
        )
        assert res2 is None
        assert _merit(killer.id) == k0 + 40 and _merit(assist.id) == a0 + hunt.ASSIST_MERIT
        print("✓ 围剿分账数值/令终态/结算幂等")
    finally:
        _cleanup(target, killer, assist, away, bystander)


def test_settle_without_order_legacy_compat():
    """直写 hunts KV（无令实体，test_atlas 同款路径）：旧口径逐值一致、无协剿。"""
    target = _char("旧路凶", sin=200)
    killer = _char("旧路猎手")
    prior = WorldStateRepository.get(hunt._HUNT_KEY)
    try:
        state = dict(prior or {})
        state[killer.id] = {"target_id": target.id, "expires_at": time.time() + 3600}
        WorldStateRepository.set(hunt._HUNT_KEY, state)
        # 确保无令实体
        orders = hunt._load_orders()
        orders.pop(target.id, None)
        hunt._save_orders(orders)
        m0 = _merit(killer.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(target.id),
        )
        assert res is not None and res["merit"] == 40 and res["assists"] == [], res
        assert _merit(killer.id) == m0 + 40
        print("✓ 无令实体兼容路径")
    finally:
        if prior is None:
            WorldStateRepository.delete(hunt._HUNT_KEY)
        else:
            WorldStateRepository.set(hunt._HUNT_KEY, prior)
        _cleanup(target, killer)


def test_bounty_channel_independent_no_double_pay():
    """同一击杀：悬赏板（玩家出资灵石）与除凶令（功德）各走各账，互不重复发钱。"""
    issuer = _char("苦主", sin=0)
    issuer.spirit_stones = 2000
    CharacterRepository.save(issuer)
    target = _char("双账凶", sin=200)
    killer = _char("双账猎手")
    try:
        placed = BountyEngine.place_bounty(
            CharacterRepository.get_by_id(issuer.id),
            CharacterRepository.get_by_id(target.id),
            300,
        )
        assert placed["success"], placed
        bounty = placed["bounty"]
        assert hunt.accept(CharacterRepository.get_by_id(killer.id), target.name)["success"]
        s0, m0 = killer.spirit_stones, _merit(killer.id)
        k_obj = CharacterRepository.get_by_id(killer.id)
        pay = BountyEngine.settle_on_kill(
            k_obj,
            CharacterRepository.get_by_id(target.id),
            [bounty],
        )
        assert pay["bounty_paid"] and pay["total_reward"] == 300, pay
        CharacterRepository.save(k_obj)  # 悬赏引擎只改对象，落库归调用方（CLI 同口径）
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(target.id),
        )
        assert res is not None
        k = CharacterRepository.get_by_id(killer.id)
        # 灵石只来自悬赏板 300（除凶不发灵石）；悬赏二次结算零重复
        assert k.spirit_stones == s0 + 300, k.spirit_stones
        pay2 = BountyEngine.settle_on_kill(k, CharacterRepository.get_by_id(target.id), [bounty])
        assert pay2["total_reward"] == 0
        assert CharacterRepository.get_by_id(killer.id).spirit_stones == s0 + 300
        assert _merit(killer.id) > m0  # 功德两通道各自记账（既有口径）
        print("✓ 悬赏/除凶双通道对账：一杀不二领灵石")
    finally:
        _cleanup(issuer, target, killer)


# ---------------- 终态：过期 / 洗清 / 已死 ----------------

def _force_order_expiry(target_id):
    orders = hunt._load_orders()
    orders[target_id]["expires_at"] = time.time() - 10
    orders[target_id]["issued_at"] = time.time() - 200000
    hunt._save_orders(orders)


def test_order_expired_clears_hunters():
    target = _char("过期凶", sin=150)
    h = _char("过期猎手")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(h.id), target.name)["success"]
        _force_order_expiry(target.id)
        # 凶犯仍标记中：过期旧令关闭并立即重发新令，旧猎手记录已清
        r = hunt.track(CharacterRepository.get_by_id(h.id), now=time.time())
        assert r["success"] is False, r
        assert hunt._load().get(h.id) is None
        o = hunt.get_order(target.id)
        assert o["status"] == hunt.ORDER_OPEN and o["hunters"] == {}
        print("✓ 令过期：旧记录清、新令重发")
    finally:
        _cleanup(target, h)


def test_order_dissolved_when_washed():
    target = _char("洗清凶", sin=150)
    h = _char("洗清猎手")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(h.id), target.name)["success"]
        tv = CharacterRepository.get_by_id(target.id)
        tv.karma.sin_value = 0
        tv.karma.blood_mark_until = 0.0
        CharacterRepository.save(tv)
        o = hunt.ensure_order(CharacterRepository.get_by_id(target.id))
        assert o["status"] == hunt.ORDER_DISSOLVED, o
        assert hunt._load().get(h.id) is None
        assert hunt.my_target(CharacterRepository.get_by_id(h.id)) is None
        print("✓ 凶犯洗清：令消散、猎手记录清")
    finally:
        _cleanup(target, h)


def test_order_dissolved_when_target_dead_elsewhere():
    target = _char("横死凶", sin=150)
    h = _char("横死猎手")
    try:
        assert hunt.accept(CharacterRepository.get_by_id(h.id), target.name)["success"]
        tv = CharacterRepository.get_by_id(target.id)
        tv.status = CharacterStatus.DEAD
        CharacterRepository.save(tv)
        r = hunt.track(CharacterRepository.get_by_id(h.id))
        assert r["success"] is False and "作废" in r["message"], r
        assert hunt._load().get(h.id) is None
        assert hunt.get_order(target.id)["status"] == hunt.ORDER_DISSOLVED
        print("✓ 凶犯横死：令消散、无悬挂")
    finally:
        _cleanup(target, h)


# ---------------- 旧档兼容：无 hunt_orders KV ----------------

def test_no_orders_kv_legacy_flow():
    prior = WorldStateRepository.get(hunt._ORDER_KEY)
    target = _char("旧档凶", sin=150)
    h = _char("旧档猎手")
    try:
        WorldStateRepository.delete(hunt._ORDER_KEY)
        board = hunt.format_board()
        assert target.name in board
        r = hunt.accept(CharacterRepository.get_by_id(h.id), target.name)
        assert r["success"], r
        print("✓ 无令 KV 旧档：看板/接令照常（惰性建令）")
    finally:
        _cleanup(target, h)
        if prior is None:
            WorldStateRepository.delete(hunt._ORDER_KEY)
        else:
            WorldStateRepository.set(hunt._ORDER_KEY, prior)


# ---------------- server 双端 handle + 闭关锁门 ----------------

def test_server_handle_flow_and_meditation_lock():
    r = WORLD.join(f"除凶服客{_tag()}")
    tok = r["token"]
    char = WORLD.get_char(tok)
    target = _char("服内凶", loc=char.location, sin=200)
    try:
        res = WORLD.handle(tok, "/除凶")
        assert res["ok"] and target.name in res["text"], res
        res = WORLD.handle(tok, f"/接令 {target.name}")
        assert res["ok"], res
        assert hunt.get_order(target.id)["hunters"].get(char.id) is not None
        res = WORLD.handle(tok, "/追凶")
        assert res["ok"] and "情报区域" in res["text"], res
        res = WORLD.handle(tok, "/弃令")
        assert res["ok"], res
        assert char.id not in (hunt.get_order(target.id)["hunters"] or {})
        # 闭关锁门：四指令均不在白名单（对齐 F07）
        char = WORLD.get_char(tok)
        char.status = CharacterStatus.MEDITATING
        CharacterRepository.save(char)
        for cmd in ("/除凶", f"/接令 {target.name}", "/追凶", "/弃令"):
            res = WORLD.handle(tok, cmd)
            assert res["ok"] is False and "闭关锁门" in (res.get("error") or ""), (cmd, res)
        char = WORLD.get_char(tok)
        char.status = CharacterStatus.IDLE
        CharacterRepository.save(char)
        print("✓ server handle：除凶/接令/追凶/弃令 + 闭关锁门")
    finally:
        live = WORLD.get_char(tok)
        _cleanup(live, target)


def test_cli_source_parity():
    """CLI 源码对齐（仓库先例口径）：四指令 handler 与帮助行齐备。"""
    src = (Path(__file__).resolve().parent.parent / "cli" / "main.py").read_text(encoding="utf-8")
    for token in ('"/除凶"', '"/接令"', '"/追凶"', '"/弃令"', "_hunt.accept", "_hunt.track", "_hunt.abandon", "_hunt.format_board"):
        assert token in src, token
    print("✓ CLI 源码对齐：四指令同引擎")
