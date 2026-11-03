"""F09 宗门势力版图：计分钩子/日上限/NPC 口径/衰减易主/主导判定/价格折扣与 F03 共存/议政钩子/面板/双端/旧档兼容"""
import os
import random
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import TRADE_HUB_REGION
from core.clock import WorldClock
from core.models import CharacterStatus, QuestChain, QuestRing
from core.atlas import (
    AtlasEngine,
    ATLAS_POINTS,
    ATLAS_POINTS_COUNCIL,
    ATLAS_DAILY_CAP_PLAYER,
    ATLAS_DAILY_CAP_NPC,
    ATLAS_NPC_WEIGHT,
    ATLAS_DOMINANCE_THRESHOLD,
    ATLAS_DISCOUNT_RATE,
)
from core.market import MarketEngine
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

QY = "青云宗"
WJ = "万剑仙门"
JY = "九幽天魔宗"
HUB = TRADE_HUB_REGION          # 东荒·青州
YUE = "中土·万岳"
STAR = "海外·乱星海"
HUB_LOC = "青云坊市客栈"
YUE_LOC = "万剑仙门峰"
STAR_LOC = "万星古岛"

_MADE_IDS = []


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _char(name="版图客", sect=None, npc=False, location=HUB_LOC, stones=100000):
    prefix = "npc_atlas_" if npc else "atlas_"
    c = WorldClock.create_new_character(f"{prefix}{_uniq(name)}", _uniq(name))
    c.sect = sect
    if sect:
        c.sect_rank = "内门弟子"
    c.location = location
    c.spirit_stones = stones
    _MADE_IDS.append(c.id)
    return c


def _set_region(region, inf, ts=None):
    WorldStateRepository.set(
        f"sect_atlas:{region}",
        {"inf": dict(inf), "ts": ts if ts is not None else time.time()},
    )


def _inf(region, sect, now=None):
    return AtlasEngine.influence_map(region, now).get(sect, 0.0)


@pytest.fixture(autouse=True, scope="module")
def _leave_no_trace():
    """零残留（F08 教训）：自造角色置死、本引擎区域 KV 保存/还原（不抹存量）、恢复随机流"""
    state = random.getstate()
    saved_regions = {}
    for region in (HUB, YUE, "西陲·幽冥渊", STAR):
        saved_regions[region] = WorldStateRepository.get(f"sect_atlas:{region}")
    yield
    random.setstate(state)
    try:
        for cid in _MADE_IDS:
            c = CharacterRepository.get_by_id(cid)
            if c is not None:
                c.status = CharacterStatus.DEAD
                CharacterRepository.save(c)
            WorldStateRepository.delete(f"sect_atlas_cap:{cid}")
        for region, v in saved_regions.items():
            if v is None:
                WorldStateRepository.delete(f"sect_atlas:{region}")
            else:
                WorldStateRepository.set(f"sect_atlas:{region}", v)
    except Exception:
        pass


# ---------------- 计分：玩家口径与钩子 ----------------

def test_record_activity_player_points_and_kinds():
    c = _char("计分客", sect=QY)
    before = _inf(HUB, QY)
    before_star = _inf(STAR, QY)
    assert AtlasEngine.record_activity(c, "explore") == ATLAS_POINTS["explore"]
    assert AtlasEngine.record_activity(c, "quest") == ATLAS_POINTS["quest"]
    assert AtlasEngine.record_activity(c, "hunt", location=STAR_LOC) == ATLAS_POINTS["hunt"]
    assert _inf(HUB, QY) == pytest.approx(before + ATLAS_POINTS["explore"] + ATLAS_POINTS["quest"])
    assert _inf(STAR, QY) == pytest.approx(before_star + ATLAS_POINTS["hunt"])
    # 散修不计分、未知 kind 不计分
    free = _char("散修客", sect=None)
    assert AtlasEngine.record_activity(free, "explore") == 0.0
    assert AtlasEngine.record_activity(c, "dance") == 0.0
    print("✓ 计分：三类活动按常量入账对应区域；散修/未知类型零计分")


def test_daily_cap_partial_and_full():
    c = _char("上限客", sect=QY, location=YUE_LOC)
    got = 0.0
    got += AtlasEngine.record_activity(c, "hunt", location=YUE_LOC)    # 10
    got += AtlasEngine.record_activity(c, "hunt", location=YUE_LOC)    # 10
    got += AtlasEngine.record_activity(c, "quest", location=YUE_LOC)   # 6 → 26
    got += AtlasEngine.record_activity(c, "hunt", location=YUE_LOC)    # 部分获准 4 → 30
    assert got == pytest.approx(ATLAS_DAILY_CAP_PLAYER)
    assert AtlasEngine.record_activity(c, "explore", location=YUE_LOC) == 0.0  # 已满
    # 换区域独立计额
    assert AtlasEngine.record_activity(c, "explore", location=HUB_LOC) == ATLAS_POINTS["explore"]
    print("✓ 日上限：同区域封顶 30、部分获准按剩余额度、跨区域独立计额")


def test_npc_weight_and_cap():
    n = _char("巡山兽仆", sect=QY, npc=True, location=YUE_LOC)
    assert AtlasEngine.record_activity(n, "explore", location=YUE_LOC) == pytest.approx(
        ATLAS_POINTS["explore"] * ATLAS_NPC_WEIGHT
    )
    n2 = _char("巡山兽仆二", sect=QY, npc=True, location=YUE_LOC)
    # NPC 日上限 10 原始分：hunt 10 分一次吃满，入账 10×0.5
    assert AtlasEngine.record_activity(n2, "hunt", location=YUE_LOC) == pytest.approx(
        ATLAS_DAILY_CAP_NPC * ATLAS_NPC_WEIGHT
    )
    assert AtlasEngine.record_activity(n2, "explore", location=YUE_LOC) == 0.0
    print("✓ NPC 口径：权重 0.5、日上限 10 原始分（入账至多 5）")


def test_explore_hook_real_chain():
    """真实 AdventureEngine.explore 成功 → 本宗落点区域 +4（骰面 mock 钉死成功）"""
    import core.adventure as adv

    c = _char("探险客", sect=QY, location=HUB_LOC)
    before = _inf(HUB, QY)
    with mock.patch.object(random, "random", lambda: 0.0):
        res = adv.AdventureEngine.explore(c, "野外", use_ai=False)
    assert res["success"] and res["combat_success"], res.get("message")
    assert _inf(HUB, QY) == pytest.approx(before + ATLAS_POINTS["explore"])
    print("✓ 真实链路：探险成功经钩子为本宗 +4")


def test_quest_hook_real_chain():
    """真实 QuestEngine.deliver：推进一环 +6、全环达成再 +6（同一钩子点恰计两次交付）"""
    from core.quests import QuestEngine

    npc = _char("委托翁", npc=True, location=HUB_LOC)
    CharacterRepository.save(npc)
    c = _char("跑腿客", sect=QY, location=HUB_LOC)
    now = time.time()

    def ring():
        return QuestRing(
            kind="deliver", desc="送信",
            deliver_npc_id=npc.id, deliver_npc_name=npc.name,
        )

    c.active_quest = QuestChain(
        publisher_id=npc.id, publisher_name=npc.name,
        rings=[ring(), ring()], ring_index=0,
        accepted_at=now, expires_at=now + 86400, reward_stones=60, reward_merit=5,
    )
    before = _inf(HUB, QY)
    r1 = QuestEngine.deliver(c)
    assert r1["success"] and r1.get("advanced"), r1.get("message")
    r2 = QuestEngine.deliver(c)
    assert r2["success"] and r2.get("completed"), r2.get("message")
    assert _inf(HUB, QY) == pytest.approx(before + 2 * ATLAS_POINTS["quest"])
    print("✓ 真实链路：委托两环交付经钩子各 +6，无重复计数")


def test_hunt_hook_real_settle():
    """真实 hunt.settle_kill：除凶结算 → 猎手本宗在事发（victim）区域 +10"""
    from core import hunt

    hunter = _char("除凶客", sect=QY, location=STAR_LOC)
    victim = _char("血煞徒", sect=None, location=STAR_LOC)
    CharacterRepository.save(hunter)
    prior = WorldStateRepository.get("hunts")
    state = dict(prior) if isinstance(prior, dict) else {}
    state[hunter.id] = {"target_id": victim.id, "expires_at": time.time() + 3600}
    WorldStateRepository.set("hunts", state)
    try:
        before = _inf(STAR, QY)
        res = hunt.settle_kill(hunter, victim)
        assert res and res.get("merit") == 40
        assert _inf(STAR, QY) == pytest.approx(before + ATLAS_POINTS["hunt"])
        # 重入幂等：记录已被 settle_kill 弹出，第二次调用返回 None 且不重复计分
        assert hunt.settle_kill(hunter, victim) is None
        assert _inf(STAR, QY) == pytest.approx(before + ATLAS_POINTS["hunt"])
    finally:
        if prior is None:
            WorldStateRepository.delete("hunts")
        else:
            WorldStateRepository.set("hunts", prior)
    print("✓ 真实链路：除凶结算经钩子按事发区域 +10（状态已还原）")


# ---------------- 衰减 / 主导判定 ----------------

def test_decay_prune_and_turnover():
    T = time.time()
    _set_region(YUE, {QY: 260.0, WJ: 190.0}, ts=T - 10 * 86400)
    m = AtlasEngine.influence_map(YUE, now=T)
    assert m[QY] == pytest.approx(260.0 * 0.5 ** (10 / 7), rel=0.02)
    assert AtlasEngine.dominant_sect(YUE, now=T) is None  # 双双跌破门槛
    # 万剑门人当日奋起（原始分吃满 30）→ 反超并逾门槛，易主
    c = _char("奋起客", sect=WJ, location=YUE_LOC)
    for kind in ("hunt", "quest", "hunt", "explore"):
        AtlasEngine.record_activity(c, kind, location=YUE_LOC, now=T)
    assert AtlasEngine.dominant_sect(YUE, now=T) == WJ
    # 剪除：微值衰减后 < 0.5 视为消散
    _set_region(STAR, {QY: 0.6}, ts=T - 30 * 86400)
    assert AtlasEngine.influence_map(STAR, now=T) == {}
    print("✓ 衰减：七日半衰可复算、跌破门槛无主、活动可易主、微值剪除")


def test_dominance_threshold_and_tie():
    _set_region(STAR, {QY: ATLAS_DOMINANCE_THRESHOLD - 0.1})
    assert AtlasEngine.dominant_sect(STAR) is None
    _set_region(STAR, {QY: ATLAS_DOMINANCE_THRESHOLD})
    assert AtlasEngine.dominant_sect(STAR) == QY
    _set_region(STAR, {QY: 150.0, WJ: 150.0})
    assert AtlasEngine.dominant_sect(STAR) is None  # 并列无主
    _set_region(STAR, {QY: 150.0, WJ: 149.0})
    assert AtlasEngine.dominant_sect(STAR) == QY
    print("✓ 主导判定：门槛 100、并列无主、独占最高者胜")


# ---------------- 价格效果（与 F03 共存） ----------------

def test_price_discount_real_clamp_and_no_arbitrage():
    _set_region(HUB, {QY: 150.0})
    member = _char("主客", sect=QY, location=HUB_LOC)
    unit = MarketEngine.market_price("聚气丹", HUB_LOC)
    assert unit == 40  # F03 基准区锚点不动
    res = MarketEngine.buy_from_guild(member, "聚气丹", 1)
    assert res["success"], res.get("message")
    assert member.spirit_stones == 100000 - int(unit * (1 - ATLAS_DISCOUNT_RATE))  # 38
    assert "九五折" in res["message"]
    # 下限钳制：单价 1 折后不得为 0
    assert AtlasEngine.discount_unit(1, QY, HUB) == 1
    # 同区买售无套利：全货单折后买价 > 同区回收价
    for row in MarketEngine.catalog(HUB_LOC):
        disc = AtlasEngine.discount_unit(row["price"], QY, HUB)
        assert disc > MarketEngine.sell_unit_base(row["name"], HUB_LOC), row["name"]
    # 回收不享折扣：主导成员售货仍按旧口径
    member.inventory.append("聚气丹")
    gain_before = member.spirit_stones
    res = MarketEngine.sell_to_guild(member, "聚气丹", 1)
    assert res["success"] and member.spirit_stones - gain_before == MarketEngine.sell_unit_base("聚气丹", HUB_LOC)
    print("✓ 价格：主导成员九五折真实落账、下限钳 1、全货同区买售无套利、回收不打折")


def test_price_discount_stacks_on_f03_regional_price():
    _set_region(YUE, {QY: 150.0})
    member = _char("行商主客", sect=QY, location=YUE_LOC)
    regional = MarketEngine.market_price("青锋剑", YUE_LOC)  # F03 区域市价（含产地系数/波动）
    res = MarketEngine.buy_from_guild(member, "青锋剑", 1)
    assert res["success"], res.get("message")
    expected = int(regional * (1 - ATLAS_DISCOUNT_RATE))
    assert member.spirit_stones == 100000 - expected
    assert expected < regional
    print("✓ 价格叠加：折扣作用于 F03 区域市价之上（市价 %d → 成交 %d）" % (regional, expected))


def test_price_unchanged_without_dominance():
    _set_region(HUB, {})  # 旧档口径：无版图数据
    member = _char("平客", sect=QY, location=HUB_LOC)
    res = MarketEngine.buy_from_guild(member, "聚气丹", 1)
    assert res["success"] and member.spirit_stones == 100000 - 40
    assert "九五折" not in res["message"]
    # 有版图但非本宗主导 → 无折扣
    _set_region(HUB, {WJ: 150.0})
    res = MarketEngine.buy_from_guild(member, "聚气丹", 1)
    assert res["success"] and member.spirit_stones == 100000 - 80
    print("✓ 价格不变：无主导/他宗主导时与旧口径逐字一致（锚点 40）")


# ---------------- 议政钩子 ----------------

def test_council_hook_pass_fail_and_idempotent():
    from core.council import CouncilEngine

    T0 = 1_900_000_000.0
    keys = [f"sect_council:{WJ}", f"sect_state:{WJ}", f"sect_council:{JY}", f"sect_state:{JY}"]
    saved = {k: WorldStateRepository.get(k) for k in keys}
    for k in keys:
        WorldStateRepository.delete(k)
    try:
        before = _inf(YUE, WJ)
        s = CouncilEngine.advance(WJ, now=T0)
        s["votes"] = {f"atlas_fake_{i}": "support" for i in range(30)}
        s = CouncilEngine.settle(WJ, s, now=T0 + 10)
        assert s["result"]["passed"]
        assert _inf(YUE, WJ) == pytest.approx(before + ATLAS_POINTS_COUNCIL)
        # 幂等：同会话重复结算不再加分
        CouncilEngine.settle(WJ, s, now=T0 + 20)
        assert _inf(YUE, WJ) == pytest.approx(before + ATLAS_POINTS_COUNCIL)
        # 否决不加分（九幽天魔宗总坛在西陲·幽冥渊）
        before_jy = _inf("西陲·幽冥渊", JY)
        s2 = CouncilEngine.advance(JY, now=T0)
        s2["votes"] = {f"atlas_fake_{i}": "oppose" for i in range(30)}
        s2 = CouncilEngine.settle(JY, s2, now=T0 + 10)
        assert not s2["result"]["passed"]
        assert _inf("西陲·幽冥渊", JY) == pytest.approx(before_jy)
    finally:
        for k, v in saved.items():
            if v is None:
                WorldStateRepository.delete(k)
            else:
                WorldStateRepository.set(k, v)
    print("✓ 议政钩子：通过 +10 落总坛区域、否决不加、重复结算不重复加（KV 已还原）")


def test_council_hook_two_snapshots_settle_once():
    """评审建议：两份未结算的独立快照先后 settle —— KV 复查守卫使版图只 +10 一次"""
    import copy

    from core.council import CouncilEngine

    T0 = 1_900_000_000.0
    keys = [f"sect_council:{WJ}", f"sect_state:{WJ}"]
    saved = {k: WorldStateRepository.get(k) for k in keys}
    for k in keys:
        WorldStateRepository.delete(k)
    try:
        before = _inf(YUE, WJ)
        s1 = CouncilEngine.advance(WJ, now=T0)
        s1["votes"] = {f"atlas_fake_{i}": "support" for i in range(30)}
        s2 = copy.deepcopy(s1)  # 第二份未结算快照（模拟跨进程/重复触发）
        CouncilEngine.settle(WJ, s1, now=T0 + 10)
        CouncilEngine.settle(WJ, s2, now=T0 + 20)
        assert _inf(YUE, WJ) == pytest.approx(before + ATLAS_POINTS_COUNCIL)
    finally:
        for k, v in saved.items():
            if v is None:
                WorldStateRepository.delete(k)
            else:
                WorldStateRepository.set(k, v)
    print("✓ 议政幂等（双快照）：两份未结算快照先后结算，版图恰 +10 一次")


def test_corrupt_kv_without_ts_degrades_empty():
    """评审建议：inf 存在但 ts 缺失/损坏的存量降级为空表（永不衰减的僵尸影响力不成立）"""
    WorldStateRepository.set(f"sect_atlas:{STAR}", {"inf": {QY: 500.0}})
    assert AtlasEngine.influence_map(STAR) == {}
    assert AtlasEngine.dominant_sect(STAR) is None
    print("✓ 损坏 KV：无时间戳的影响力存量降级为空，不成僵尸版图")


def test_npc_shop_sell_no_arbitrage_with_discount():
    """评审必须修回归：产地区「商会折后买入 → 交好专柜回收」闭环必须亏钱。
    专柜回收已按当地商会回收口径封顶（core/trade.py 区域锚）。"""
    from core.npc_mind import ensure_mind
    from core.trade import NpcShopEngine
    from storage.db import NpcMindRepository

    _set_region(YUE, {QY: 150.0})
    npc = _char("洗剑池掌柜", npc=True, location="洗剑池洞天")
    npc.sect_rank = "洗剑池执事"
    CharacterRepository.save(npc)
    player = _char("套利客", sect=QY, location="洗剑池洞天")
    ensure_mind(npc)
    NpcMindRepository.upsert(
        npc.id, personality="市侩圆滑",
        attitudes={player.id: {"value": 50, "label": "friendly"}},
    )
    # 闭环：商会折后买入青锋剑（产地万岳）→ 立即售与交好专柜
    res = MarketEngine.buy_from_guild(player, "青锋剑", 1)
    assert res["success"] and "九五折" in res["message"], res.get("message")
    cost = 100000 - player.spirit_stones
    res = NpcShopEngine.sell(player, npc.name, "青锋剑", 1)
    assert res["success"], res.get("message")
    expected_cap = int(
        MarketEngine.market_price("青锋剑", "洗剑池洞天") * 0.5 * 1.10
    )
    assert res["gain"] == expected_cap
    assert res["gain"] < cost, f"套利未封：买入 {cost} → 专柜回收 {res['gain']}"
    print(f"✓ 专柜套利已封：产地折后买入 {cost} → 交好专柜回收 {res['gain']}（必亏）")


def test_npc_sell_channel_traversal_no_arbitrage():
    """全货 × 14 日波动遍历：任一货物在其产地区，折后买价恒 > 交好专柜回收价（封顶后）"""
    from config import ITEM_CATALOG, TRADE_ITEM_ORIGIN, WORLD_LOCATIONS

    loc_by_region = {}
    for loc, cfg in WORLD_LOCATIONS.items():
        loc_by_region.setdefault(cfg.get("region"), loc)
    from datetime import date, timedelta

    base_day = date(2026, 1, 5)
    for item, cfg in ITEM_CATALOG.items():
        origin = TRADE_ITEM_ORIGIN.get(item)
        if not origin:
            continue
        loc = loc_by_region[origin]
        _set_region(origin, {QY: 150.0})
        for d in range(14):
            day = (base_day + timedelta(days=d)).isoformat()
            regional = MarketEngine.market_price(item, loc, day=day)
            buy = AtlasEngine.discount_unit(regional, QY, origin)
            npc_unit = max(
                1,
                min(
                    int(cfg["price"] * 0.5 * 1.10),
                    int(regional * 0.5 * 1.10),
                ),
            )
            assert buy > npc_unit, (item, day, buy, npc_unit)
    print("✓ 遍历：21 货 × 14 日，产地折后买价恒高于交好专柜回收（无套利日）")


# ---------------- 面板与双端 ----------------

def test_panel_text_full_detail_unknown_and_recruit():
    _set_region(HUB, {QY: 150.0, WJ: 60.0})
    member = _char("观图客", sect=QY)
    txt = AtlasEngine.panel_text(member)
    assert "天下版图" in txt and HUB in txt and YUE in txt and STAR in txt
    assert "主导【青云宗】" in txt and "慕名投宗者众" in txt  # 本宗主导 → 招募展示
    detail = AtlasEngine.panel_text(member, YUE_LOC)  # 地点名归区
    assert f"版图 · {YUE}" in detail
    detail2 = AtlasEngine.panel_text(member, HUB)
    assert "1. 【青云宗】" in detail2 and "主导" in detail2 and "本宗" in detail2
    assert "未闻" in AtlasEngine.panel_text(member, "不存在之地")
    free = _char("观图散修", sect=None)
    assert "散修" in AtlasEngine.panel_text(free)
    print("✓ 面板：全图/明细（区域名与地点名）/未知区域/散修视角/招募展示")


def test_server_handle_and_meditation_whitelist():
    _set_region(HUB, {QY: 150.0})
    r = WORLD.join(f"版图服客{_uniq('')}", user_id=f"atlas_{_uniq('srv')}")
    tok = r["token"]
    char = WORLD.get_char(tok)
    _MADE_IDS.append(char.id)
    char.sect = QY
    char.sect_rank = "内门弟子"
    char.location = HUB_LOC
    CharacterRepository.save(char)
    res = WORLD.handle(tok, "/版图")
    assert res["ok"] and "天下版图" in res["text"], res
    res = WORLD.handle(tok, f"/版图 {YUE}")
    assert res["ok"] and f"版图 · {YUE}" in res["text"], res
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    res = WORLD.handle(tok, "/版图")
    assert res["ok"], res  # 只读观照：闭关放行（与 /行情 同口径）
    print("✓ 双端：server handle /版图 与区域明细通路；闭关白名单放行")
