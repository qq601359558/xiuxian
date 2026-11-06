"""F04 典当行：典当/赎回闭环、金额口径、防套现、逾期没收流通、边界、双端链路"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import PAWN_INTEREST_RATE, PAWN_MAX_TICKETS, PAWN_TERM_DAYS
from core.clock import WorldClock
from core.market import MarketEngine
from core.pawn import PAWN_TERM_SECONDS, PawnEngine, PawnStatus
from storage.db import (
    MarketListingRepository,
    PawnTicketRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

HUB_LOC = "青云坊市客栈"  # 基准区：聚气丹市价 40（标价锚点）
T0 = 1_800_000_000.0      # 固定注入时间，验到期确定性


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _char(name="当客", stones=1000, items=()):
    c = WorldClock.create_new_character(f"pawn_{_uniq(name)}", _uniq(name))
    c.spirit_stones = stones
    c.location = HUB_LOC
    for it in items:
        c.inventory.append(it)
    return c


def _pawn(char, item, now=None):
    ticket, res = PawnEngine.pawn_item(char, item, now=now)
    assert res["success"], res
    PawnTicketRepository.save(ticket)
    return ticket


def test_pawn_success_amount_and_removal():
    """典当成功：金额 = 当地市价×0.5（聚气丹 40→20），物品离行囊，票据字段写死"""
    c = _char("当丹客", items=["聚气丹"])
    s0 = c.spirit_stones
    ticket = _pawn(c, "聚气丹", now=T0)
    assert ticket.principal == 20 == PawnEngine.pawn_value("聚气丹", HUB_LOC)
    assert ticket.interest == 2  # ceil(20 × 10%)
    assert ticket.redeem_cost() == 22
    assert ticket.pawned_at == T0 and ticket.due_at == T0 + PAWN_TERM_SECONDS
    assert ticket.due_at - ticket.pawned_at == PAWN_TERM_DAYS * 86400
    assert ticket.status == PawnStatus.OPEN
    assert "聚气丹" not in c.inventory
    assert c.spirit_stones == s0 + 20
    saved = [t for t in PawnTicketRepository.list_by_owner(c.id) if t.id == ticket.id]
    assert saved and saved[0].principal == 20
    print("✓ 典当口径：聚气丹当 20、息 2、赎 22，到期 = 当时 + 3 天（确定性）")


def test_pawn_value_follows_regional_price():
    """估值复用 F03 区域市价单点：异地典当额随 MarketEngine.market_price 走"""
    for loc in ("万剑仙门峰", "万星古岛", "黑风绝渊"):
        expect = max(1, int(MarketEngine.market_price("青锋剑", loc) * 0.5))
        assert PawnEngine.pawn_value("青锋剑", loc) == expect, loc
    print("✓ 典当估值与区域市价单点一致（无第二套价格表）")


def test_pawned_item_unusable():
    """在当物品不可出售/服用/穿戴（各引擎只认行囊，典当已移出）"""
    from core.loot_equip import EquipEngine

    c = _char("锁物客", items=["聚气丹", "青锋剑"])
    _pawn(c, "聚气丹")
    _pawn(c, "青锋剑")
    res = MarketEngine.sell_to_guild(c, "聚气丹", 1)
    assert not res["success"]
    res = MarketEngine.use_pill(c, "聚气丹")
    assert not res["success"]
    res = EquipEngine.equip(c, "青锋剑")
    assert not res["success"]
    print("✓ 在当物品不可出售/服用/穿戴")


def test_redeem_loop_and_anti_arbitrage():
    """赎回闭环：付本金+息、物回行囊、票了结；赎回总额恒大于典当所得（防套现）"""
    c = _char("赎当客", stones=100, items=["聚气丹"])
    ticket = _pawn(c, "聚气丹")
    after_pawn = c.spirit_stones
    assert after_pawn == 120
    t2, res = PawnEngine.redeem_item(c, "聚气丹")
    assert res["success"], res
    PawnTicketRepository.save(t2)
    assert res["cost"] == 22 and res["cost"] > ticket.principal  # 赎价 > 当价
    assert c.spirit_stones == after_pawn - 22 == 98  # 一当一赎净亏利息 2
    assert "聚气丹" in c.inventory
    saved = [t for t in PawnTicketRepository.list_by_owner(c.id) if t.id == ticket.id][0]
    assert saved.status == PawnStatus.REDEEMED
    # 利息下限：再便宜的货赎回也必贵于典当（本金≥1 → 息≥1）
    for principal in (1, 2, 5, 20, 999):
        assert PawnEngine.interest_for(principal) >= 1
        assert principal + PawnEngine.interest_for(principal) > principal
    assert PAWN_INTEREST_RATE > 0
    print("✓ 赎回闭环：当 20 赎 22，净亏利息；利息下限保证恒不可套现")


def test_redeem_insufficient_stones_keeps_ticket():
    """灵石不足：赎回失败、票保持 OPEN、物品不回、灵石不动，到期前可再赎"""
    c = _char("穷赎客", stones=0, items=["聚气丹"])
    ticket = _pawn(c, "聚气丹")  # 当得 20，赎需 22
    assert c.spirit_stones == 20
    t2, res = PawnEngine.redeem_item(c, "聚气丹")
    assert t2 is None and not res["success"] and "仍有效" in res["message"]
    assert c.spirit_stones == 20 and "聚气丹" not in c.inventory
    saved = [t for t in PawnTicketRepository.list_by_owner(c.id) if t.id == ticket.id][0]
    assert saved.status == PawnStatus.OPEN
    c.spirit_stones = 100  # 凑足后可赎
    t2, res = PawnEngine.redeem_item(c, "聚气丹")
    assert res["success"] and "聚气丹" in c.inventory
    print("✓ 灵石不足赎回失败且票仍有效，凑足可再赎")


def test_per_item_tickets_fifo():
    """逐件成票：同名两件两张票；赎回先赎最早到期的一张"""
    c = _char("多票客", stones=10000, items=["聚气丹", "聚气丹"])
    t1 = _pawn(c, "聚气丹", now=T0)
    t2 = _pawn(c, "聚气丹", now=T0 + 3600)
    assert t1.id != t2.id
    assert len(PawnEngine.open_tickets(c.id)) == 2
    done, res = PawnEngine.redeem_item(c, "聚气丹", now=T0 + 7200)
    assert res["success"] and done.id == t1.id  # FIFO
    PawnTicketRepository.save(done)
    left = PawnEngine.open_tickets(c.id)
    assert len(left) == 1 and left[0].id == t2.id
    assert c.inventory.count("聚气丹") == 1
    print("✓ 逐件成票、赎回 FIFO（最早到期先赎）")


def test_expiry_forfeit_flows_to_market():
    """逾期没收：票转 FORFEITED、物品进当铺寄售、他人可买走、查看标注已没收"""
    c = _char("逾期客", stones=100, items=["百年灵芝"])
    ticket = _pawn(c, "百年灵芝", now=T0)
    # 到期前一刻仍可赎（边界：due_at 本身才算到期）
    rows = PawnEngine.settle_expired(c.id, now=T0 + PAWN_TERM_SECONDS - 1, location=HUB_LOC)
    assert rows == []
    # 到期结算没收
    rows = PawnEngine.settle_expired(c.id, now=T0 + PAWN_TERM_SECONDS, location=HUB_LOC)
    assert len(rows) == 1 and rows[0].status == PawnStatus.FORFEITED
    saved = [t for t in PawnTicketRepository.list_by_owner(c.id) if t.id == ticket.id][0]
    assert saved.status == PawnStatus.FORFEITED
    # 物品流入寄售栏，挂单主体为当铺
    mine = [
        l for l in MarketListingRepository.list_all()
        if l.seller_id == "pawn_shop" and l.item_name == "百年灵芝" and l.is_open()
        and l.price == ticket.redeem_cost()  # 按本票赎回价过滤，隔离共享库历史残留
    ]
    assert mine, "没收物应出现在当铺寄售中"
    listing = mine[0]
    # 没收寄售价 = 票面赎回价（本金+息），与结算地点无关（评审 M1 口径）
    assert listing.price == ticket.redeem_cost() == 30  # 百年灵芝 当27 + 息3
    # 他人买走：走既有 buy_listing 通道
    buyer = _char("捡漏客", stones=10000)
    res = MarketEngine.buy_listing(buyer, listing)
    assert res["success"] and "百年灵芝" in buyer.inventory
    # 票主查看：标注已没收
    text = PawnEngine.panel_text(c, now=T0 + PAWN_TERM_SECONDS + 60)
    assert "已逾期没收" in text and "百年灵芝" in text
    # 没收后赎回：明确报已没收
    t2, res = PawnEngine.redeem_item(c, "百年灵芝", now=T0 + PAWN_TERM_SECONDS + 120)
    assert t2 is None and not res["success"]
    print("✓ 逾期没收：转当铺寄售流通、他人可买、查看标注已没收")


def test_redeem_after_expiry_reports_forfeit():
    """到期后才来赎：惰性结算先行，赎回明确失败（不吞票）"""
    c = _char("迟赎客", stones=10000, items=["聚气丹"])
    ticket = _pawn(c, "聚气丹", now=T0)
    t2, res = PawnEngine.redeem_item(c, "聚气丹", now=T0 + PAWN_TERM_SECONDS + 10)
    assert t2 is None and not res["success"] and "已没收" in res["message"]
    saved = [t for t in PawnTicketRepository.list_by_owner(c.id) if t.id == ticket.id][0]
    assert saved.status == PawnStatus.FORFEITED
    assert "聚气丹" not in c.inventory
    print("✓ 到期赎回：先结算没收再明确报错")


def test_equipped_cannot_pawn_and_boundaries():
    """已穿戴不可当（须先卸下）；无此物/无票/死亡/票满边界"""
    from core.models import CharacterStatus

    c = _char("边界客", stones=100, items=["青锋剑"])
    c.inventory.remove("青锋剑")
    c.equipped.append("青锋剑")  # 模拟穿戴后状态（穿戴移出行囊）
    ticket, res = PawnEngine.pawn_item(c, "青锋剑")
    assert ticket is None and not res["success"] and "卸下" in res["message"]
    ticket, res = PawnEngine.pawn_item(c, "不存在的宝物")
    assert ticket is None and not res["success"]
    t2, res = PawnEngine.redeem_item(c, "青锋剑")
    assert t2 is None and not res["success"]
    # 死亡不可典当
    c2 = _char("坐化客", items=["聚气丹"])
    c2.status = CharacterStatus.DEAD
    ticket, res = PawnEngine.pawn_item(c2, "聚气丹")
    assert ticket is None and not res["success"]
    assert "聚气丹" in c2.inventory  # 失败不改状态
    # 票满上限
    c3 = _char("满票客", stones=10000, items=["聚气丹"] * (PAWN_MAX_TICKETS + 1))
    for _ in range(PAWN_MAX_TICKETS):
        _pawn(c3, "聚气丹")
    ticket, res = PawnEngine.pawn_item(c3, "聚气丹")
    assert ticket is None and not res["success"] and "已满" in res["message"]
    print("✓ 边界：已穿戴须卸下、无物/无票、死亡拒当、票满 8 张")


def test_forfeit_buyback_costs_interest_no_arbitrage():
    """评审 M1 回归：没收寄售价恒为票面赎回价——迁低价区触发结算也不能低价买回套利"""
    c = _char("防套客", stones=1000, items=["青锋剑"])
    s0 = c.spirit_stones
    ticket = _pawn(c, "青锋剑", now=T0)  # 基准区：当 110，息 11，赎 121
    assert ticket.principal == 110 and ticket.interest == 11 and ticket.redeem_cost() == 121
    # 票主迁往产地（低价区）再触发没收结算
    c.location = "万剑仙门峰"
    rows = PawnEngine.settle_expired(c.id, now=T0 + PAWN_TERM_SECONDS, location=c.location)
    assert len(rows) == 1
    mine = [
        l for l in MarketListingRepository.list_all()
        if l.seller_id == "pawn_shop" and l.item_name == "青锋剑"
        and l.is_open() and l.price == 121
    ]
    assert mine, "没收寄售价应为赎回价 121 而非当地五折 62"
    listing = mine[0]
    res = MarketEngine.buy_listing(c, listing)
    assert res["success"] and "青锋剑" in c.inventory
    # 一当一买回：净变动 = -利息（与赎回等价），无任何套利空间
    assert c.spirit_stones == s0 - ticket.interest
    print("✓ M1 回归：没收买回价 = 赎回价，跨区触发结算无套利")


def test_forfeit_settle_idempotent_listing():
    """没收幂等：多次结算/查看/赎回尝试后，当铺寄售只生成一条"""
    c = _char("幂等客", stones=100, items=["玄铁护腕"])
    _pawn(c, "玄铁护腕", now=T0)

    def _count():
        return len([
            l for l in MarketListingRepository.list_all()
            if l.seller_id == "pawn_shop" and l.item_name == "玄铁护腕"
        ])

    before = _count()
    late = T0 + PAWN_TERM_SECONDS + 10
    PawnEngine.settle_expired(c.id, now=late, location=HUB_LOC)
    PawnEngine.panel_text(c, now=late + 10)
    PawnEngine.redeem_item(c, "玄铁护腕", now=late + 20)
    assert _count() == before + 1
    print("✓ 没收结算幂等：重复触发不重复上架")


def test_unknown_item_and_value_floor():
    """未知货按市价回退 20 估值（当 10）；全目录×全区域典当额恒 ≥1"""
    from config import ITEM_CATALOG

    c = _char("杂货客", stones=0, items=["无名残片"])
    ticket = _pawn(c, "无名残片")
    assert ticket.principal == 10 and ticket.kind == "material"
    for name in ITEM_CATALOG:
        for loc in ("青云坊市客栈", "万剑仙门峰", "万星古岛", "黑风绝渊"):
            assert PawnEngine.pawn_value(name, loc) >= 1, (name, loc)
    print("✓ 未知货回退估值 10；典当额下限 1 全域成立")


def test_dead_redeem_rejected_panel_allowed():
    """死亡口径补全：赎回拒绝且无副作用；查看当票放行（遗容）"""
    from core.models import CharacterStatus

    c = _char("遗票客", stones=10000, items=["聚气丹"])
    ticket = _pawn(c, "聚气丹", now=T0)
    c.status = CharacterStatus.DEAD
    t2, res = PawnEngine.redeem_item(c, "聚气丹", now=T0 + 60)
    assert t2 is None and not res["success"]
    saved = [t for t in PawnTicketRepository.list_by_owner(c.id) if t.id == ticket.id][0]
    assert saved.status == PawnStatus.OPEN  # 死亡赎回不产生没收等副作用
    text = PawnEngine.panel_text(c, now=T0 + 60)
    assert "聚气丹" in text
    print("✓ 死亡：赎回拒绝无副作用、查看放行")


def test_panel_empty_and_old_save_compat():
    """旧档兼容：从未典当过的角色查看当票正常（新表为空不炸）"""
    c = _char("新客")
    text = PawnEngine.panel_text(c)
    assert "暂无典当" in text
    assert PawnEngine.open_tickets(c.id) == []
    # 角色序列化往返（无新字段，旧结构不变）
    c2 = c.__class__.model_validate_json(c.model_dump_json())
    assert PawnEngine.panel_text(c2)
    print("✓ 旧档兼容：无票查看正常、角色结构无破坏性变更")


def test_world_handle_pawn_chain():
    """LAN 全链路：/典当 查看 → /典当 聚气丹 → /赎回；闭关三令锁门"""
    from storage.db import CharacterRepository
    from server.world import World
    from core.models import CharacterStatus

    w = World(auto_tick=False)
    r = w.join(_uniq("链路当客"))
    tok = r["token"]
    char = w.get_char(tok)
    char.spirit_stones = 500
    char.inventory.append("聚气丹")
    CharacterRepository.save(char)

    res = w.handle(tok, "/典当")
    assert res.get("ok") and "暂无典当" in res["text"], res
    s0 = w.get_char(tok).spirit_stones
    res = w.handle(tok, "/典当 聚气丹")
    assert res.get("ok"), res
    char = w.get_char(tok)
    assert char.spirit_stones == s0 + 20 and "聚气丹" not in char.inventory
    res = w.handle(tok, "/典当")
    assert res.get("ok") and "聚气丹" in res["text"] and "赎回价 22" in res["text"]
    res = w.handle(tok, "/赎回 聚气丹")
    assert res.get("ok"), res
    char = w.get_char(tok)
    assert char.spirit_stones == s0 - 2 and "聚气丹" in char.inventory
    res = w.handle(tok, "/赎回 聚气丹")
    assert not res.get("ok")  # 无票再赎报错

    # 闭关锁门：典当/赎回/查看均不在白名单（与购买/出售同口径）
    char = w.get_char(tok)
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    for cmd in ("/典当", "/典当 聚气丹", "/赎回 聚气丹"):
        res = w.handle(tok, cmd)
        assert not res.get("ok") and "闭关锁门" in (res.get("error") or ""), (cmd, res)
    print("✓ World.handle 全链路：查看/典当/赎回/重复赎回报错/闭关锁门")
