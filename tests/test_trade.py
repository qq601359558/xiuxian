"""F03 区域价差跑商：区域价/确定性/波动/套利封顶/防刷回归/边界/双端链路"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import (
    TRADE_HUB_REGION,
    TRADE_ORIGIN_FACTOR,
    TRADE_DISTANCE_FACTORS,
    TRADE_DAILY_FLUCTUATION,
    MARKET_SELL_BACK_RATE,
)
from core.clock import WorldClock
from core.market import MarketEngine
from server.world import WORLD

WORLD.stop_tick()

HUB_LOC = "青云坊市客栈"        # 东荒·青州（基准区）
ORIGIN_LOC = "万剑仙门峰"       # 中土·万岳（青锋剑产地）
FAR_LOC = "万星古岛"           # 海外·乱星海（距万岳 3）


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _char(name="行商", stones=100000):
    c = WorldClock.create_new_character(f"trade_{_uniq(name)}", _uniq(name))
    c.spirit_stones = stones
    return c


def test_hub_anchor_prices_unchanged():
    """基准区（青州）价格与旧口径逐字一致：既有锚点的回归红线"""
    assert MarketEngine.region_of(HUB_LOC) == TRADE_HUB_REGION
    assert MarketEngine.regional_factor("青锋剑", TRADE_HUB_REGION) == 1.0
    assert MarketEngine.market_price("聚气丹", HUB_LOC) == 40
    assert MarketEngine.market_price("一阶青木迷踪阵", HUB_LOC) == 120
    assert MarketEngine.sell_unit_base("妖兽内丹", HUB_LOC) == 40
    c = _char("锚点客")
    res = MarketEngine.buy_from_guild(c, "聚气丹", 1)
    assert res["success"] and c.spirit_stones == 100000 - 40
    c.inventory.append("妖兽内丹")
    res = MarketEngine.sell_to_guild(c, "妖兽内丹", 1)
    assert res["success"] and res["gain"] == 40
    # 无地点 catalog 与旧行为一致（标价、无区域字段）
    row = [g for g in MarketEngine.catalog() if g["name"] == "聚气丹"][0]
    assert row["price"] == 40 and "factor" not in row
    print("✓ 基准区锚点：青州买/卖价与旧口径逐字一致")


def test_regional_price_differences_and_determinism():
    """产地价 < 基准价 < 远方价；同日同货同区价格确定性一致"""
    p_origin = MarketEngine.market_price("青锋剑", ORIGIN_LOC)
    p_hub = MarketEngine.market_price("青锋剑", HUB_LOC)
    p_far = MarketEngine.market_price("青锋剑", FAR_LOC)
    assert p_origin < p_hub == 220 < p_far, (p_origin, p_hub, p_far)
    # 确定性：反复调用、显式传同一天，结果恒同
    day = "2026-01-15"
    a = MarketEngine.market_price("青锋剑", FAR_LOC, day=day)
    b = MarketEngine.market_price("青锋剑", FAR_LOC, day=day)
    assert a == b
    f1 = MarketEngine.regional_factor("青锋剑", "海外·乱星海", day)
    f2 = MarketEngine.regional_factor("青锋剑", "海外·乱星海", day)
    assert f1 == f2
    # 妖兽内丹：产地幽冥渊 < 青州
    assert MarketEngine.market_price("妖兽内丹", "黑风绝渊") < 80
    print(f"✓ 区域价差与确定性：青锋剑 产地{p_origin} < 基准{p_hub} < 远方{p_far}")


def test_daily_fluctuation_varies_and_bounded():
    """非基准区价格按日波动且幅度封顶；基准区恒稳"""
    from datetime import date, timedelta

    base = TRADE_DISTANCE_FACTORS[3]
    seen = set()
    start = date(2026, 3, 1)
    for d in range(60):
        day = (start + timedelta(days=d)).isoformat()
        f = MarketEngine.regional_factor("青锋剑", "海外·乱星海", day)
        assert base * (1 - TRADE_DAILY_FLUCTUATION) - 1e-9 <= f <= base * (1 + TRADE_DAILY_FLUCTUATION) + 1e-9
        seen.add(round(f, 4))
        assert MarketEngine.regional_factor("青锋剑", TRADE_HUB_REGION, day) == 1.0
    assert len(seen) >= 2, "60 天内波动应出现多个不同系数"
    print(f"✓ 每日波动：60 天出现 {len(seen)} 种系数，幅度 ≤ ±{int(TRADE_DAILY_FLUCTUATION * 100)}%")


def test_worst_day_margin_bounded():
    """遍历 90 天：距离 3 路线单程毛利的最坏日也被封顶（结构 22.7% + 双边波动 + 取整）"""
    from datetime import date, timedelta

    start = date(2026, 1, 1)
    worst = 0.0
    for d in range(90):
        day = (start + timedelta(days=d)).isoformat()
        buy = MarketEngine.market_price("青锋剑", ORIGIN_LOC, day=day)
        sell = MarketEngine.sell_unit_base("青锋剑", FAR_LOC, day=day)
        worst = max(worst, sell / buy - 1.0)
    assert 0.15 < worst <= 0.33, worst
    print(f"✓ 最坏日毛利 {worst:.1%}（≤33% 封顶内）")


def test_trade_loop_profit_within_cap():
    """低买高卖闭环获利；单程毛利率受结构封顶（常数层 + 含波动最坏情形）"""
    # 常数层封顶：距离 3 路线结构毛利 ≤ 25%
    structural = TRADE_DISTANCE_FACTORS[3] * MARKET_SELL_BACK_RATE / TRADE_ORIGIN_FACTOR - 1.0
    assert structural <= 0.25, structural
    c = _char("跑商客")
    c.location = ORIGIN_LOC
    buy_unit = MarketEngine.market_price("青锋剑", ORIGIN_LOC)
    s0 = c.spirit_stones
    res = MarketEngine.buy_from_guild(c, "青锋剑", 5)
    assert res["success"], res
    assert c.spirit_stones == s0 - buy_unit * 5
    c.location = FAR_LOC
    s1 = c.spirit_stones
    res = MarketEngine.sell_to_guild(c, "青锋剑", 5)
    assert res["success"], res
    profit = c.spirit_stones - s1 - 0  # 卖出所得
    gain = res["gain"]
    assert gain > buy_unit * 5, (gain, buy_unit)  # 卖出所得 > 买入成本 → 获利
    margin = gain / (buy_unit * 5) - 1.0
    assert 0 < margin <= 0.35, margin  # 含波动与取整的最坏情形上限
    assert profit == gain
    print(f"✓ 跑商闭环：买入 {buy_unit}/件 → 远方回收共 {gain}，单程毛利率 {margin:.1%}（封顶内）")


def test_hub_goods_not_arbitrageable():
    """基准区货物结构性不可套利：青州买入、任何区域回收都不赚"""
    c = _char("倒药客")
    res = MarketEngine.buy_from_guild(c, "百年灵芝", 3)  # 青州 55/件
    assert res["success"]
    for loc in (ORIGIN_LOC, "黑风绝渊", FAR_LOC):
        c2 = _char("倒药客乙")
        c2.location = loc
        c2.inventory.append("百年灵芝")
        r = MarketEngine.sell_to_guild(c2, "百年灵芝", 1)
        assert r["gain"] < 55, (loc, r["gain"])
    print("✓ 基准区消费品不可套利（回收恒低于青州买入价）")


def test_anti_farming_regression():
    """同货同日大量出售：分档压价、总收益被压；换个角色不受影响（单角色口径）"""
    c = _char("刷商")
    c.inventory.extend(["妖兽内丹"] * 40)
    gains = []
    for _ in range(4):
        res = MarketEngine.sell_to_guild(c, "妖兽内丹", 10)
        assert res["success"], res
        gains.append(res["gain"])
    # 青州 unit_back=40：四档应为 400 / 320 / 240 / 180
    assert gains == [400, 320, 240, 180], gains
    assert sum(gains) < 40 * 40  # 远低于无回归的 1600
    # 继续卖只剩最低档
    c.inventory.extend(["妖兽内丹"] * 5)
    res = MarketEngine.sell_to_guild(c, "妖兽内丹", 5)
    assert res["gain"] == 5 * 18
    # 单角色口径：新角色同日同货仍是全价
    c2 = _char("新商")
    c2.inventory.append("妖兽内丹")
    res = MarketEngine.sell_to_guild(c2, "妖兽内丹", 1)
    assert res["gain"] == 40
    print(f"✓ 防刷回归：四档收益 {gains} 递减，单角色隔离")


def test_bulk_sale_crosses_tiers():
    """单次大额出售逐件跨档计价（不是整批按某一档）"""
    c = _char("大宗商")
    c.inventory.extend(["妖兽内丹"] * 25)
    res = MarketEngine.sell_to_guild(c, "妖兽内丹", 25)
    assert res["success"]
    # 逐件：10×40 + 10×32 + 5×24 = 840
    assert res["gain"] == 840, res["gain"]
    assert res["decayed"] is True and res["avg_unit"] == 840 // 25
    print("✓ 单次大额出售逐件跨档：25 件 gain=840")


def test_sell_qty_validation_no_pollution():
    """qty≤0 出售被拒且不污染收购量状态（评审必须修项）"""
    c = _char("守规商")
    c.inventory.append("妖兽内丹")
    for bad in (0, -5):
        res = MarketEngine.sell_to_guild(c, "妖兽内丹", bad)
        assert not res["success"], (bad, res)
    assert MarketEngine._reg_volume(c.id, "妖兽内丹") == 0
    res = MarketEngine.sell_to_guild(c, "妖兽内丹", 1)
    assert res["success"] and res["gain"] == 40  # 全价档未被负量污染
    print("✓ qty≤0 被拒且不污染收购量")


def test_regression_resets_next_day():
    """收购量状态跨日自动重置：昨日爆量不影响今日全价"""
    from datetime import date, timedelta

    from config import TRADE_REG_STATE_PREFIX
    from storage.db import WorldStateRepository

    c = _char("隔日商")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    WorldStateRepository.set(
        TRADE_REG_STATE_PREFIX + str(c.id),
        {"date": yesterday, "vol": {"妖兽内丹": 999}},
    )
    assert MarketEngine._reg_volume(c.id, "妖兽内丹") == 0
    c.inventory.append("妖兽内丹")
    res = MarketEngine.sell_to_guild(c, "妖兽内丹", 1)
    assert res["success"] and res["gain"] == 40
    print("✓ 收购量跨日重置")


def test_alias_locations_and_unknown_item():
    """别名地点与本体同区同价；无目录货物按默认价回收"""
    assert MarketEngine.market_price("青锋剑", "落霞山灵泉(野外)") == MarketEngine.market_price("青锋剑", "落霞山灵泉")
    assert MarketEngine.sell_unit_base("妖兽内丹", "黑风绝渊(大凶)") == MarketEngine.sell_unit_base("妖兽内丹", "黑风绝渊")
    c = _char("拾荒商")
    c.inventory.append("无名残片")
    res = MarketEngine.sell_to_guild(c, "无名残片", 1)
    assert res["success"] and res["gain"] == 10  # 默认价 20 × 50%
    print("✓ 别名地点同价、无目录货物默认价回收")


def test_insufficient_and_no_goods():
    """灵石不足（按当地价报错）/ 无货出售 / 无此货"""
    c = _char("穷商", stones=10)
    c.location = FAR_LOC
    far_price = MarketEngine.market_price("青锋剑", FAR_LOC)
    res = MarketEngine.buy_from_guild(c, "青锋剑", 1)
    assert not res["success"] and str(far_price) in res["message"]
    assert c.spirit_stones == 10  # 失败不扣款
    res = MarketEngine.sell_to_guild(c, "青锋剑", 1)
    assert not res["success"]
    res = MarketEngine.buy_from_guild(c, "不存在的货", 1)
    assert not res["success"]
    print("✓ 边界：灵石不足按当地价报错且不扣款、无货出售被拒")


def test_unknown_location_falls_back_to_hub():
    """未知地点回退基准区系数，不炸"""
    assert MarketEngine.region_of("查无此地") == TRADE_HUB_REGION
    assert MarketEngine.market_price("聚气丹", "查无此地") == 40
    print("✓ 未知地点回退基准区")


def test_world_handle_trade_chain():
    """LAN 全链路：/行情 → /go 产地 → /购买 → 异地 /出售 获利 → /坊市 区域价"""
    from storage.db import init_db, CharacterRepository
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    r = w.join(_uniq("链路行商"))
    tok = r["token"]
    char = w.get_char(tok)
    char.spirit_stones = 100000
    CharacterRepository.save(char)

    res = w.handle(tok, "/行情")
    assert res.get("ok") and "天下行情" in res["text"] and "中土·万岳" in res["text"]

    res = w.handle(tok, "/go 万剑仙门峰")
    assert res.get("ok"), res
    char = w.get_char(tok)
    assert char.location == ORIGIN_LOC

    buy_unit = MarketEngine.market_price("青锋剑", ORIGIN_LOC)
    s0 = char.spirit_stones
    res = w.handle(tok, "/购买 青锋剑 2")
    assert res.get("ok"), res
    char = w.get_char(tok)
    assert char.spirit_stones == s0 - buy_unit * 2  # /go 事件不改灵石的通常情形外以市价为准核对差额
    assert char.inventory.count("青锋剑") >= 2

    # 直接迁置远方（避免二次 /go 事件干扰金额断言），走 handle 出售
    char.location = FAR_LOC
    CharacterRepository.save(char)
    s1 = char.spirit_stones
    res = w.handle(tok, "/出售 青锋剑 2")
    assert res.get("ok"), res
    char = w.get_char(tok)
    assert char.spirit_stones > s1 + buy_unit * 2  # 回收所得高于买入成本 → 获利

    res = w.handle(tok, "/坊市")
    assert res.get("ok") and "海外·乱星海" in res["text"] and "/行情" in res["text"]
    print("✓ World.handle 全链路：行情/go/购买/异地出售获利/坊市区域价")


def test_meditation_trade_view_only():
    """闭关中：/行情 只读放行，/购买 仍被门禁拦截"""
    from storage.db import init_db, CharacterRepository
    from server.world import World
    from core.models import CharacterStatus

    init_db()
    w = World(auto_tick=False)
    r = w.join(_uniq("闭关行商"))
    tok = r["token"]
    char = w.get_char(tok)
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    assert w.handle(tok, "/行情").get("ok")
    for cmd in ("/购买 聚气丹", "/出售 聚气丹"):
        res = w.handle(tok, cmd)
        assert not res.get("ok") and "闭关锁门" in (res.get("error") or ""), (cmd, res)
    print("✓ 闭关门禁：行情可观照、购买/出售被拦")
