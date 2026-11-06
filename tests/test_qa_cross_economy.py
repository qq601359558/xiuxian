"""QA 审计 · 域1 灵石经济守恒与价格叠序 + 域5 议政×版图组合（探索性测试，失败即缺陷证据）"""
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import ITEM_CATALOG, MARKET_SELL_BACK_RATE, NPC_PRICE_FRIENDLY_BUY, NPC_PRICE_FRIENDLY_SELL
from core import pawn as pawn_mod
from core.atlas import AtlasEngine
from core.council import CouncilEngine
from core.clock import WorldClock
from core.market import MarketEngine
from core.models import CharacterStatus
from core.season_theme import SeasonThemeEngine
from storage.db import (
    CharacterRepository,
    MarketListingRepository,
    PawnTicketRepository,
    WorldStateRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

HUB_LOC = "青云坊市客栈"  # 东荒·青州（基准区）


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, sect=None, location=HUB_LOC, stones=100000):
    c = WorldClock.create_new_character(f"qa_{name}_{_tag()}", f"QA{name}{_tag()}")
    c.sect = sect
    c.location = location
    c.spirit_stones = stones
    CharacterRepository.save(c)
    return c


def _kill(*chars):
    for c in chars:
        if c is None:
            continue
        live = CharacterRepository.get_by_id(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


def _days():
    base = date(2026, 1, 5)
    return [(base + timedelta(days=i)).isoformat() for i in range(0, 400, 3)]


# ---------------- 域1.1 天象价系数恰乘一次（金风/静默日，含基准区） ----------------

def test_theme_price_applied_exactly_once():
    regions = MarketEngine.all_regions()
    gold_day = silent_day = None
    for i in range(620):  # ≥7 个纪元（84 天/纪元）才保证六主题全覆盖
        d = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        m = SeasonThemeEngine.price_mult_for_day(d)
        if m == 1.05 and gold_day is None:
            gold_day = d
        if m == 1.0 and silent_day is None:
            silent_day = d
        if gold_day and silent_day:
            break
    assert gold_day and silent_day, "620 天内应同时存在金风日与中性日"
    for item, cfg in ITEM_CATALOG.items():
        base = cfg["price"]
        for region in regions:
            f_gold = MarketEngine.regional_factor(item, region, gold_day)
            exp_gold = max(1, int(round(base * f_gold * 1.05)))
            got_gold = MarketEngine._price_for_region(item, region, gold_day)
            assert got_gold == exp_gold, f"{item}@{region} 金风日 期望{exp_gold} 实际{got_gold}"
            f_sil = MarketEngine.regional_factor(item, region, silent_day)
            exp_sil = max(1, int(round(base * f_sil * 1.0)))
            got_sil = MarketEngine._price_for_region(item, region, silent_day)
            assert got_sil == exp_sil, f"{item}@{region} 中性日 期望{exp_sil} 实际{got_sil}"
    # 基准区中性日 = 标价逐字（F03 锚点）
    for item, cfg in ITEM_CATALOG.items():
        assert MarketEngine._price_for_region(item, "东荒·青州", silent_day) == cfg["price"]


# ---------------- 域1.2 全通道套利遍历 ----------------

def test_no_cross_channel_arbitrage_beyond_spec_margin():
    """买入通道：商会市价（各区）/ NPC专柜交好买价(0.9×标价，区域无关)。
    卖出通道：商会回收首档 / NPC专柜交好回收（F09 区域锚封顶 = 市价×0.5×1.10）。
    断言：同区同日卖价 < 买价（无同地套利）；跨区毛利不得超出 spec 公式包络：
    商会路线 =(1.35×1.03)/(0.55×0.97)×0.5 ≈ 1.303；专柜交好再 ×1.10 ≈ 1.433。
    （首轮审计曾以 1.40 为界误报：漏算日波动双端叠乘与好感溢价，实测 1.41–1.43
    恰在包络内——见报告「按设计/未定」对该毛利量级的设计观察。）"""
    regions = MarketEngine.all_regions()
    violations = []
    for item, cfg in ITEM_CATALOG.items():
        base = cfg["price"]
        npc_buy = max(1, int(base * NPC_PRICE_FRIENDLY_BUY))
        for day in _days():
            prices = {r: MarketEngine._price_for_region(item, r, day) for r in regions}
            sells = {r: MarketEngine._sell_unit_for_region(item, r, day) for r in regions}
            npc_sells = {r: int(prices[r] * MARKET_SELL_BACK_RATE * NPC_PRICE_FRIENDLY_SELL) for r in regions}
            for r in regions:
                if sells[r] >= prices[r]:
                    violations.append(f"同区商会套利 {item}@{r}@{day} 买{prices[r]} 卖{sells[r]}")
                if npc_sells[r] >= prices[r]:
                    violations.append(f"同区专柜套利 {item}@{r}@{day} 买{prices[r]} 专柜卖{npc_sells[r]}")
                if sells[r] >= npc_buy:
                    violations.append(f"专柜买→商会卖套利 {item}@{r}@{day} 专柜买{npc_buy} 商会卖{sells[r]}")
                if npc_sells[r] >= npc_buy:
                    violations.append(f"专柜买→专柜卖套利 {item}@{r}@{day} 专柜买{npc_buy} 专柜卖{npc_sells[r]}")
            # 跨区：卖价 vs 最低买价不得超出 spec 公式包络（+2 灵石取整余量）
            min_buy = min(prices.values())
            if max(sells.values()) > min_buy * 1.32 + 2:
                violations.append(
                    f"跨区商会毛利超包络 {item}@{day} 最低买{min_buy} 商会最高卖{max(sells.values())} "
                    f"比{max(sells.values()) / max(1, min_buy):.2f}（包络≈1.303）"
                )
            max_sell = max(max(sells.values()), max(npc_sells.values()))
            if max_sell > min_buy * 1.44 + 2:
                violations.append(
                    f"跨区毛利超包络 {item}@{day} 最低买{min_buy} 最高卖{max_sell} 比{max_sell / max(1, min_buy):.2f}（包络≈1.433）"
                )
    assert not violations, "\n".join(violations[:20])


# ---------------- 域1.3 版图折扣成交位序逐值 ----------------

def test_atlas_discount_composition_on_real_buy():
    region = "东荒·青州"
    sect = "青云宗"
    key = f"sect_atlas:{region}"
    old = WorldStateRepository.get(key)
    WorldStateRepository.set(key, {"inf": {sect: 200.0}, "ts": time.time()})
    member = _char("版图买家", sect=sect)
    guest = _char("无折买家", sect=None)
    try:
        item = "聚气丹"
        unit = MarketEngine.market_price(item, member.location)
        exp_unit = max(1, int(unit * 0.95))
        before = member.spirit_stones
        res = MarketEngine.buy_from_guild(member, item, 3)
        assert res["success"], res
        paid = before - member.spirit_stones
        assert paid == exp_unit * 3, f"主导成员成交 期望单价{exp_unit}×3={exp_unit * 3} 实际付{paid}（市价{unit}）"
        before2 = guest.spirit_stones
        res2 = MarketEngine.buy_from_guild(guest, item, 3)
        assert res2["success"], res2
        assert before2 - guest.spirit_stones == unit * 3, "非主导者应付全市价"
    finally:
        if old is None:
            WorldStateRepository.delete(key)
        else:
            WorldStateRepository.set(key, old)
        _kill(member, guest)


# ---------------- 域6.2 典当没收幂等（不重复生成寄售） ----------------

def test_pawn_forfeit_settle_idempotent():
    c = _char("当票客", stones=0)
    c.inventory.append("聚气丹")
    CharacterRepository.save(c)
    ticket = None
    ids_before = {l.id for l in MarketListingRepository.list_all()}
    try:
        ticket, res = pawn_mod.PawnEngine.pawn_item(c, "聚气丹")
        assert ticket is not None, res
        ticket.due_at = time.time() - 10
        PawnTicketRepository.save(ticket)
        pawn_mod.PawnEngine.settle_expired(c.id)
        pawn_mod.PawnEngine.settle_expired(c.id)
        pawn_mod.PawnEngine.settle_expired(c.id)
        listings = [
            l for l in MarketListingRepository.list_all()
            if l.id not in ids_before and l.seller_id == "pawn_shop"
        ]
        assert len(listings) == 1, f"没收寄售应恰 1 条，实际 {len(listings)} 条（重复生成=经济重复供给）"
        assert listings[0].price == ticket.principal + ticket.interest, "没收寄售价应为票面赎回价"
    finally:
        # 零残留：直删本测试新建的寄售行与当票行（仓储无 delete API，按 id 精确删自造数据）
        import sqlite3
        from storage.db import DB_PATH
        new_ids = [l.id for l in MarketListingRepository.list_all() if l.id not in ids_before]
        conn = sqlite3.connect(DB_PATH)
        for lid in new_ids:
            conn.execute("DELETE FROM market_listings WHERE id = ?", (lid,))
        if ticket is not None:
            conn.execute("DELETE FROM pawn_tickets WHERE id = ?", (ticket.id,))
        conn.commit()
        conn.close()
        _kill(c)


# ---------------- 域5.1 议政结算 × 版图钩子组合一致性 ----------------

def test_council_settle_cross_consistency_with_atlas():
    sect = "青云宗"
    hq_region = MarketEngine.region_of("青云宗外门山门")
    t0 = 1_900_000_000.0 + (os.getpid() % 1000) * 100000.0  # 确定性逻辑时钟（与 F08 测试同法）
    keys = (f"sect_council:{sect}", f"sect_state:{sect}", f"sect_atlas:{hq_region}")
    saved = {k: WorldStateRepository.get(k) for k in keys}
    member = _char("议政员", sect=sect)
    try:
        # 零残留隔离：清空议政会话/宗门状态（镜像 tests/test_council.py 的 _reset），毕后恢复原 KV
        WorldStateRepository.set(keys[0], None)
        WorldStateRepository.set(keys[1], None)
        CouncilEngine.advance(sect, now=t0)
        state_before = CouncilEngine.get_sect_state(sect)
        inf_before = AtlasEngine.influence_map(hq_region).get(sect, 0.0)
        # 记票：成员投支持（结果由长老立场+票数决定，断言以 result 快照为准做交叉对账）
        CouncilEngine.vote(member, "support", now=t0)
        settled = CouncilEngine.advance(sect, now=t0 + 7201 + 1)
        if not settled.get("settled"):
            settled = CouncilEngine.settle(sect, CouncilEngine._load_session(sect), now=t0 + 7202)
        result = settled.get("result") or {}
        state_after = CouncilEngine.get_sect_state(sect)
        effects = result.get("effects") or {}
        for dim in ("vault", "prestige", "morale"):
            exp_delta = effects.get(dim, 0)
            got_delta = state_after[dim] - state_before[dim]
            # 状态已触上下限时实际差值可小于名义效果（钳制），但方向与封顶必须一致
            if exp_delta > 0:
                assert 0 <= got_delta <= exp_delta, f"{dim} 期望增量≤{exp_delta} 实际{got_delta}"
            elif exp_delta < 0:
                assert exp_delta <= got_delta <= 0, f"{dim} 期望增量≥{exp_delta} 实际{got_delta}"
            else:
                assert got_delta == 0, f"{dim} 无效果应不变，实际{got_delta}"
        inf_after = AtlasEngine.influence_map(hq_region).get(sect, 0.0)
        if result.get("passed"):
            assert abs((inf_after - inf_before) - 10.0) < 0.1, f"议政通过版图应 +10，实际差 {inf_after - inf_before}"
        else:
            assert abs(inf_after - inf_before) < 0.1, f"议政否决版图应 +0，实际差 {inf_after - inf_before}"
        # 重复结算（新快照对象）不得二次落账
        again = CouncilEngine.settle(sect, dict(settled), now=t0 + 7300)
        state_again = CouncilEngine.get_sect_state(sect)
        assert state_again == state_after, "重复 settle 不得二次改 sect_state"
        inf_again = AtlasEngine.influence_map(hq_region).get(sect, 0.0)
        assert abs(inf_again - inf_after) < 0.1, "重复 settle 不得二次加版图"
    finally:
        for k, v in saved.items():
            if v is None:
                WorldStateRepository.delete(k)
            else:
                WorldStateRepository.set(k, v)
        _kill(member)
