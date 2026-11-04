"""QA 第二轮 · 重点 7 数值极端与钳制 + 未定 ① 实测取证。

- 价格下限遍历：全目录 × 全地点市价 ≥ 1；版图折扣 max(1, int(×0.95)) 在 1/2/3 价位不破 1；
- 巨额灵石：10^15 级寄售成交走纯 int 路径，买卖双方 delta 精确无浮点漂移；
- 影响力衰减长尾：20 个半衰期后 < 0.5 剪除、主导消散；未来时间戳不负衰减；
- 飞升榜层级支配：score_of 全域遍历——低层上限 < 高层下限（边距 300），
  NaN/inf/脏值输入一律净化为有限分；
- 炼体寿元守卫：0→10 层累计增寿恰 = TOTAL_CAP(10 年)，death_timestamp 恰推进同值，
  满层再炼拒绝（守卫在边界不越 cap）；
- 未定 ① 取证：跨区 NPC 专柜卖出——实测最优毛利包络 + 同 NPC 连卖 20 次单价恒定
  （无资金池/无防刷分档，与商会 sell 的 TRADE_REG_TIERS 分档形成对照）。
"""
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import ITEM_CATALOG, MARKET_SELL_BACK_RATE, SECONDS_PER_GAME_YEAR, WORLD_LOCATIONS
from core.ascension import score_of
from core.atlas import AtlasEngine
from core.body_soul import (
    BODY_LIFESPAN_PER_LEVEL,
    BODY_LIFESPAN_TOTAL_CAP,
    BodySoulEngine,
)
from core.clock import WorldClock
from core.market import MarketEngine
from core.models import CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"
ITEM = "妖兽内丹"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, stones=500, items=(), user=None, location=LOC_A):
    c = WorldClock.create_new_character(user or f"qa2_{name}_{_tag()}", f"QA2{name}{_tag()}")
    c.location = location
    c.spirit_stones = stones
    for it in items:
        c.inventory.append(it)
    CharacterRepository.save(c)
    return c


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _cleanup(*chars):
    for c in chars:
        if c is None:
            continue
        live = _get(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


# ---------------- 价格下限遍历 ----------------

def test_price_floors_traversal():
    for item in ITEM_CATALOG:
        for loc in WORLD_LOCATIONS:
            p = MarketEngine.market_price(item, loc)
            assert p >= 1, (item, loc, p)
            s = MarketEngine.sell_unit_base(item, loc)
            assert s >= 1, (item, loc, s)
    print(f"✓ 价格下限遍历：{len(ITEM_CATALOG)} 物品 × {len(WORLD_LOCATIONS)} 地点市价/回收基准均 ≥ 1")


def test_atlas_discount_floor():
    region = MarketEngine.region_of(LOC_A)
    key = f"sect_atlas:{region}"
    prior = WorldStateRepository.get(key)
    sect = "青云宗"
    try:
        WorldStateRepository.set(key, {"inf": {sect: 100.0}, "ts": time.time()})
        assert AtlasEngine.dominant_sect(region) == sect
        for unit, want in ((1, 1), (2, 1), (3, 2), (20, 19), (100, 95)):
            got = AtlasEngine.discount_unit(unit, sect, region)
            assert got == want, (unit, got, want)
        assert AtlasEngine.discount_unit(100, "万剑仙门", region) == 100
        print("✓ 版图折扣下限：1→1、2→1、3→2、20→19、100→95，不破 1 不为 0")
    finally:
        if prior:
            WorldStateRepository.set(key, prior)
        else:
            WorldStateRepository.delete(key)


# ---------------- 巨额灵石 int 精度 ----------------

def test_huge_stones_exact_int():
    big = 10**15
    seller = _char("巨售", stones=big, items=[ITEM])  # 须备足上架手续费（标价 10%）
    buyer = _char("巨买", stones=big + 7)
    try:
        obj = _get(seller.id)
        listing, res = MarketEngine.list_item(obj, ITEM, big)
        assert res["success"], res
        from storage.db import MarketListingRepository
        MarketListingRepository.save(listing)
        CharacterRepository.save(obj)
        lst = next(l for l in MarketListingRepository.list_all() if l.id == listing.id)
        b = _get(buyer.id)
        res2 = MarketEngine.buy_listing(b, lst)
        assert res2["success"], res2
        assert b.spirit_stones == 7, b.spirit_stones
        CharacterRepository.save(b)
        MarketListingRepository.save(lst)
        s_obj = _get(seller.id)
        s_before = s_obj.spirit_stones
        paid = MarketEngine.complete_sale_payment(lst, s_obj)
        assert paid == big
        assert s_obj.spirit_stones - s_before == big, s_obj.spirit_stones
        print("✓ 巨额灵石：10^15 寄售成交买卖 delta 精确（纯 int 路径）")
    finally:
        _cleanup(seller, buyer)


# ---------------- 影响力衰减长尾 ----------------

def test_atlas_decay_tail():
    region = MarketEngine.region_of(LOC_A)
    key = f"sect_atlas:{region}"
    prior = WorldStateRepository.get(key)
    sect = "青云宗"
    now = time.time()
    try:
        WorldStateRepository.set(key, {"inf": {sect: 100.0}, "ts": now - 140 * 86400})
        assert AtlasEngine.influence_map(region, now=now) == {}
        assert AtlasEngine.dominant_sect(region, now=now) is None
        WorldStateRepository.set(key, {"inf": {sect: 100.0}, "ts": now - 6 * 86400})
        m = AtlasEngine.influence_map(region, now=now)
        assert abs(m[sect] - 100 * 0.5 ** (6 / 7)) < 0.01, m
        WorldStateRepository.set(key, {"inf": {sect: 100.0}, "ts": now + 10 * 86400})
        m2 = AtlasEngine.influence_map(region, now=now)
        assert m2[sect] == 100.0, m2
        print("✓ 衰减长尾：140 天剪除消散、6 天 ≈55.2、未来戳钳 1.0 不放大")
    finally:
        if prior:
            WorldStateRepository.set(key, prior)
        else:
            WorldStateRepository.delete(key)


# ---------------- 飞升榜层级支配 ----------------

def test_ascension_tier_dominance_and_sanitize():
    for tier in range(0, 5):
        hi = score_of(tier, 3, 25, 300)
        lo = score_of(tier + 1, 0, 0, 0)
        assert hi < lo, (tier, hi, lo)
    for bad in (float("nan"), float("inf"), float("-inf"), "x", None):
        s = score_of(2, 1, bad, bad)
        assert math.isfinite(s), (bad, s)
    s = score_of(5, 3, 10**9, 10**9)
    assert math.isfinite(s) and s > score_of(4, 3, 25, 300)
    print("✓ 飞升榜：层级支配全域成立（边距 300），NaN/inf/脏值净化为有限分")


# ---------------- 炼体寿元守卫 ----------------

def test_body_soul_lifespan_cap_boundary():
    c = _char("体界", stones=100000, items=[ITEM] * 22)
    try:
        obj = _get(c.id)
        before_death = time.time() + 3600
        obj.lifespan.death_timestamp = before_death
        CharacterRepository.save(obj)
        me = _get(c.id)
        res = BodySoulEngine.train_body(me, times=10)
        assert res["success"], res
        CharacterRepository.save(me)
        assert me.body_level == 10
        gained_years = (me.lifespan.death_timestamp - before_death) / SECONDS_PER_GAME_YEAR
        assert abs(gained_years - BODY_LIFESPAN_TOTAL_CAP) < 1e-6, gained_years
        assert abs(BODY_LIFESPAN_TOTAL_CAP - BODY_LIFESPAN_PER_LEVEL * 10) < 1e-9
        res2 = BodySoulEngine.train_body(_get(c.id), times=1)
        assert not res2["success"], res2
        print(f"✓ 炼体守卫：0→10 层增寿恰 {gained_years:.1f} 年 = TOTAL_CAP，满层零再发")
    finally:
        _cleanup(c)


# ---------------- 未定 ①：跨区专柜毛利 + 无限重复取证 ----------------

def test_npc_shop_cross_region_margin_unbounded():
    from core.npc_mind import ensure_mind
    from core.trade import NPC_PRICE_FRIENDLY_SELL, NpcShopEngine
    from storage.db import NpcMindRepository

    best = None
    for item, cfg in ITEM_CATALOG.items():
        base = cfg["price"]
        for lo_loc in WORLD_LOCATIONS:
            buy = MarketEngine.market_price(item, lo_loc)
            if buy <= 0:
                continue
            for hi_loc in WORLD_LOCATIONS:
                local = MarketEngine.market_price(item, hi_loc)
                unit = max(1, min(int(base * MARKET_SELL_BACK_RATE * NPC_PRICE_FRIENDLY_SELL),
                                  int(local * MARKET_SELL_BACK_RATE * NPC_PRICE_FRIENDLY_SELL)))
                margin = unit / buy
                if best is None or margin > best[0]:
                    best = (margin, item, lo_loc, hi_loc, buy, unit)
    margin, item, lo_loc, hi_loc, buy_unit, sell_unit = best
    print(f"  最优跨区对：【{item}】{lo_loc} 买 {buy_unit} → {hi_loc} 专柜卖 {sell_unit}，毛利 ×{margin:.2f}")
    assert margin > 1.0, f"跨区毛利应 > 1（真实包络 ≈1.03），实测 {margin:.2f}"

    npc = _char("专柜掌柜", stones=0, location=hi_loc, user=f"npc_qa2_shop_{_tag()}")
    player = _char("跑商", stones=100000, location=lo_loc)
    try:
        n = _get(npc.id)
        n.sect_rank = "坊市掌柜"
        CharacterRepository.save(n)
        ensure_mind(_get(npc.id))
        NpcMindRepository.upsert(
            npc.id, personality="市侩圆滑",
            attitudes={player.id: {"value": 50, "label": "friendly"}},
        )
        p_obj = _get(player.id)
        res = MarketEngine.buy_from_guild(p_obj, item, 20)
        assert res["success"], res
        CharacterRepository.save(p_obj)
        me = _get(player.id)
        cost = 100000 - me.spirit_stones
        assert cost == buy_unit * 20, (cost, buy_unit)
        me.location = hi_loc
        CharacterRepository.save(me)
        gains = []
        for _ in range(20):
            p2 = _get(player.id)
            r = NpcShopEngine.sell(p2, _get(npc.id).name, item, 1)
            assert r["success"], r
            gains.append(r["gain"])
            CharacterRepository.save(p2)
        assert len(set(gains)) == 1 and gains[0] == sell_unit, gains
        total = sum(gains)
        assert total > cost, (total, cost)
        print(f"✓ 未定①取证：连卖 20 次单价恒 {sell_unit}（无资金池/无分档），"
              f"总毛利 {total}/{cost} = ×{total / cost:.2f} 可无限重复")
    finally:
        _cleanup(npc, player)


def test_npc_sell_true_envelope_scan():
    """专柜卖价真实包络（双项 min 口径）全域扫描：修正第一轮单项公式的高估。

    第一轮 test_qa_cross_economy 的 npc_sells 只取当地锚一项，漏了 trade.py
    sell() 中 min(标价×0.5×mult, 当地锚) 的标价项——高价区被高估，
    其「实测 1.41–1.43」为测试公式伪影。真实包络 = 0.55/(0.55×0.97) ≈ 1.031
    （加取整余量 ≤1.05），与本轮端到端实测 ×1.03 吻合。
    """
    from core.trade import NPC_PRICE_FRIENDLY_SELL
    from datetime import date, timedelta

    regions = MarketEngine.all_regions()
    days = [(date(2026, 11, 4) + timedelta(days=i)).isoformat() for i in range(30)]
    worst = 0.0
    worst_desc = ""
    for item, cfg in ITEM_CATALOG.items():
        base = cfg["price"]
        base_term = int(base * MARKET_SELL_BACK_RATE * NPC_PRICE_FRIENDLY_SELL)
        for day in days:
            prices = {r: MarketEngine._price_for_region(item, r, day) for r in regions}
            min_buy = min(prices.values())
            if min_buy <= 0:
                continue
            for r in regions:
                local_term = int(prices[r] * MARKET_SELL_BACK_RATE * NPC_PRICE_FRIENDLY_SELL)
                unit = max(1, min(base_term, local_term))
                ratio = unit / min_buy
                if ratio > worst:
                    worst, worst_desc = ratio, f"{item}@{r}@{day} unit={unit} min_buy={min_buy}"
    print(f"  专柜真实包络最坏值 ×{worst:.3f}（{worst_desc}）")
    assert worst <= 1.05, f"真实包络超 1.05：{worst:.3f} {worst_desc}"
    print("✓ 专柜真实包络 ≤ ×1.05（理论 1.031+取整），第一轮 1.43 包络为单项公式伪影")
