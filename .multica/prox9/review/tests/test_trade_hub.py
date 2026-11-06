"""
坊市四通道：当面交易 · NPC 专柜 · 拍卖行
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, AuctionLotRepository
from core.clock import WorldClock
from core.trade import (
    TradeEngine,
    NpcShopEngine,
    AuctionEngine,
    AuctionStatus,
    npc_shop_kinds,
)
from core.models import CharacterStatus


def _char(name: str, stones: int = 500, loc: str = "青云坊市客栈"):
    c = WorldClock.create_new_character(f"t_{name}", name)
    c.spirit_stones = stones
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def _clear_trade_state():
    import core.trade as tr

    tr._trade_sessions.clear()
    tr._trade_by_user.clear()


def test_face_trade_same_safe_ok():
    init_db()
    _clear_trade_state()
    a = _char("甲", stones=200)
    b = _char("乙", stones=50)
    a.inventory.append("百年灵芝")
    CharacterRepository.save(a)

    res = TradeEngine.open_trade(a, "乙")
    assert res["success"] is True, res

    res2 = TradeEngine.set_offer(a, 100, ["百年灵芝"])
    assert res2["success"] is True, res2
    assert a.spirit_stones == 100
    assert "百年灵芝" not in a.inventory
    CharacterRepository.save(a)

    b = CharacterRepository.get_by_id(b.id)
    res3 = TradeEngine.set_offer(b, 50, [])
    assert res3["success"] is True, res3
    CharacterRepository.save(b)

    assert TradeEngine.accept(CharacterRepository.get_by_id(a.id))["success"] is True
    res4 = TradeEngine.accept(CharacterRepository.get_by_id(b.id))
    assert res4["success"] is True, res4

    a = CharacterRepository.get_by_id(a.id)
    b = CharacterRepository.get_by_id(b.id)
    # A 出 100+灵芝，B 出 50 → A 余 100+50，B 得 100 + 灵芝
    assert a.spirit_stones == 100 + 50
    assert b.spirit_stones == 100
    assert "百年灵芝" in b.inventory
    print("✓ 当面交易同地安全区成交")


def test_face_trade_reject_unsafe_and_remote():
    _clear_trade_state()
    a = _char("野外甲", loc="落霞山灵泉(野外)")
    b = _char("野外乙", loc="落霞山灵泉(野外)")
    res = TradeEngine.open_trade(a, "野外乙")
    assert res["success"] is False
    assert "安全" in res["message"] or "安全区" in res["message"]

    c = _char("远客", loc="青云坊市客栈")
    d = _char("近邻", loc="青云宗外门山门")
    res2 = TradeEngine.open_trade(c, "近邻")
    assert res2["success"] is False
    assert "同地" in res2["message"]
    print("✓ 野外与异地被拒")


def test_face_trade_meditating_blocked():
    _clear_trade_state()
    a = _char("闭关甲")
    b = _char("闭关乙")
    a.status = CharacterStatus.MEDITATING
    res = TradeEngine.open_trade(a, "闭关乙")
    assert res["success"] is False
    print("✓ 闭关不可交易")


def test_face_trade_reject_returns_locked():
    _clear_trade_state()
    a = _char("退甲", stones=300)
    b = _char("退乙")
    a.inventory.append("聚气丹")
    CharacterRepository.save(a)
    TradeEngine.open_trade(a, "退乙")
    TradeEngine.set_offer(a, 100, ["聚气丹"])
    assert a.spirit_stones == 200
    CharacterRepository.save(a)
    res = TradeEngine.reject(CharacterRepository.get_by_id(a.id))
    assert res["success"] is True
    a = CharacterRepository.get_by_id(a.id)
    assert a.spirit_stones == 300
    assert "聚气丹" in a.inventory
    print("✓ 拒绝退回锁定物")


def test_npc_shop_pill_clerk():
    _clear_trade_state()
    p = _char("丹客", stones=400)
    # 柳三娘是丹铺掌柜，在坊市
    npc = CharacterRepository.get_by_name("柳三娘")
    if npc is None:
        npc = WorldClock.create_new_character("npc_liu", "柳三娘")
        npc.sect = "四海散修商会"
        npc.sect_rank = "丹铺掌柜"
        npc.location = p.location
        CharacterRepository.save(npc)
    else:
        npc.location = p.location
        CharacterRepository.save(npc)

    kinds = npc_shop_kinds(npc)
    assert "pill" in kinds

    res = NpcShopEngine.buy(p, "柳三娘", "聚气丹", 1)
    assert res["success"] is True, res
    assert "聚气丹" in p.inventory
    assert p.spirit_stones < 400

    res2 = NpcShopEngine.buy(p, "柳三娘", "青锋剑", 1)
    assert res2["success"] is False  # 丹铺不卖剑
    print("✓ NPC 丹铺职分过滤与购买")


def test_npc_shop_remote_refused():
    p = _char("异地客", loc="青云坊市客栈")
    n = _char("他地商", loc="乱星海黑市")
    n.sect_rank = "丹铺掌柜"
    CharacterRepository.save(n)
    res = NpcShopEngine.buy(p, "他地商", "聚气丹", 1)
    assert res["success"] is False
    print("✓ 异地 NPC 拒买")


def test_auction_bid_refund_and_settle():
    init_db()
    seller = _char("拍主", stones=100)
    buyer = _char("竞客", stones=500)
    rival = _char("抬价客", stones=500)
    seller.inventory.append("百年灵芝")

    res = AuctionEngine.list_item(seller, "百年灵芝", 50, buyout_price=200, now=time.time())
    assert res["success"] is True, res
    lot = res["lot"]

    r1 = AuctionEngine.bid(rival, lot.id, 60, now=time.time())
    assert r1["success"] is True, r1
    assert rival.spirit_stones == 500 - 60

    r2 = AuctionEngine.bid(buyer, lot.id, 70, now=time.time())
    assert r2["success"] is True, r2
    # 超价自动退回（从库重载校验）
    rival_db = CharacterRepository.get_by_id(rival.id)
    assert rival_db.spirit_stones == 500
    assert buyer.spirit_stones == 500 - 70

    # 有出价不可撤
    assert AuctionEngine.cancel(seller, lot.id)["success"] is False

    # 一口价
    buyer = CharacterRepository.get_by_id(buyer.id)
    r3 = AuctionEngine.buyout(buyer, lot.id, now=time.time())
    assert r3["success"] is True, r3
    buyer = CharacterRepository.get_by_id(buyer.id)
    seller = CharacterRepository.get_by_id(seller.id)
    assert "百年灵芝" in buyer.inventory
    # seller 实收 200 - 5% = 190
    assert seller.spirit_stones == 100 + 190
    print("✓ 竞价超价退款 + 一口价落槌")


def test_auction_expire_no_bid():
    init_db()
    seller = _char("流拍主", stones=10)
    seller.inventory.append("回春露")
    CharacterRepository.save(seller)
    now = time.time()
    res = AuctionEngine.list_item(seller, "回春露", 30, now=now)
    assert res["success"] is True
    lot = res["lot"]
    # 直接改 ends_at 到过去
    from storage.db import AuctionLotRepository

    lot.ends_at = now - 1
    AuctionLotRepository.save(lot)
    notes = AuctionEngine.settle_expired(now=now)
    assert any("流拍" in n for n in notes)
    seller = CharacterRepository.get_by_id(seller.id)
    assert "回春露" in seller.inventory
    print("✓ 无人应价流拍退回")


def test_auction_expire_with_bid():
    init_db()
    seller = _char("落槌主", stones=10)
    buyer = _char("中标客", stones=300)
    seller.inventory.append("青锋剑")
    CharacterRepository.save(seller)
    now = time.time()
    res = AuctionEngine.list_item(seller, "青锋剑", 100, now=now)
    lot = res["lot"]
    rb = AuctionEngine.bid(buyer, lot.id, 100, now=now)
    assert rb["success"] is True
    lot = rb["lot"]  # 含 leader
    lot.ends_at = now - 1
    AuctionLotRepository.save(lot)
    notes = AuctionEngine.settle_expired(now=now)
    assert any("落槌" in n for n in notes)
    buyer = CharacterRepository.get_by_id(buyer.id)
    seller = CharacterRepository.get_by_id(seller.id)
    assert "青锋剑" in buyer.inventory
    assert seller.spirit_stones == 10 + 95  # 100 - 5%
    print("✓ 到期落槌成交")


def test_buyout_insufficient_no_side_effect():
    """一口价灵石不足：不得先退领先者再落空（critical 回归）"""
    init_db()
    _clear_trade_state()
    seller = _char("穷买家主", stones=10)
    leader = _char("领先客", stones=200)
    poor = _char("穷一口", stones=50)
    seller.inventory.append("百年灵芝")
    CharacterRepository.save(seller)
    now = time.time()
    res = AuctionEngine.list_item(seller, "百年灵芝", 50, buyout_price=300, now=now)
    lot = res["lot"]
    assert AuctionEngine.bid(leader, lot.id, 50, now=now)["success"] is True

    r = AuctionEngine.buyout(poor, lot.id, now=now)
    assert r["success"] is False
    # 领先者未被白退，拍品仍 OPEN
    leader_db = CharacterRepository.get_by_id(leader.id)
    assert leader_db.spirit_stones == 200 - 50
    from core.trade import AuctionStatus as AS

    lot2 = AuctionEngine._find(lot.id)
    assert lot2.status == AS.OPEN
    print("✓ 一口价不足不产生副作用")


def test_trade_change_offer_clears_accept():
    _clear_trade_state()
    a = _char("改甲", stones=200)
    b = _char("改乙", stones=100)
    TradeEngine.open_trade(a, "改乙")
    TradeEngine.set_offer(a, 50, [])
    CharacterRepository.save(a)
    TradeEngine.set_offer(CharacterRepository.get_by_id(b.id), 40, [])
    CharacterRepository.save(CharacterRepository.get_by_id(b.id))
    TradeEngine.accept(CharacterRepository.get_by_id(a.id))
    # 乙改价 → 双方同意清空
    TradeEngine.set_offer(CharacterRepository.get_by_id(b.id), 60, [])
    import core.trade as tr

    s = tr._session_for(a.id)
    assert s.a_ok is False and s.b_ok is False
    print("✓ 改报价清除双方同意")


def test_trade_timeout_refund():
    _clear_trade_state()
    a = _char("超时甲", stones=100)
    b = _char("超时乙")
    TradeEngine.open_trade(a, "超时乙")
    TradeEngine.set_offer(a, 80, [])
    CharacterRepository.save(a)
    import core.trade as tr
    from config import TRADE_TIMEOUT_MIN

    s = tr._session_for(a.id)
    s.created_at = time.time() - (TRADE_TIMEOUT_MIN * 60 + 5)
    TradeEngine.view(a)
    a = CharacterRepository.get_by_id(a.id)
    assert a.spirit_stones == 100
    print("✓ 超时自动退回")


def test_auction_cancel_no_bid():
    init_db()
    seller = _char("可撤主", stones=10)
    seller.inventory.append("回春露")
    CharacterRepository.save(seller)
    res = AuctionEngine.list_item(seller, "回春露", 20, now=time.time())
    lot = res["lot"]
    r = AuctionEngine.cancel(CharacterRepository.get_by_id(seller.id), lot.id)
    assert r["success"] is True
    seller = CharacterRepository.get_by_id(seller.id)
    assert "回春露" in seller.inventory
    print("✓ 无出价可撤拍")


def test_npc_attitude_price():
    from core.trade import attitude_buy_mult
    from core.npc_mind import ensure_mind
    from storage.db import NpcMindRepository

    p = _char("态度客", stones=400)
    n = _char("态度商", stones=100)
    n.sect_rank = "丹铺掌柜"
    n.location = p.location
    CharacterRepository.save(n)
    ensure_mind(n)
    NpcMindRepository.upsert(
        n.id,
        personality="市侩圆滑",
        attitudes={p.id: {"value": 50, "label": "friendly"}},
    )
    mult, note = attitude_buy_mult(CharacterRepository.get_by_id(n.id), p.id)
    assert mult == 0.90
    assert "交好" in note
    res = NpcShopEngine.buy(p, "态度商", "聚气丹", 1)
    assert res["success"] is True
    # 40 * 0.9 = 36
    assert p.spirit_stones == 400 - 36
    print("✓ 态度交好折扣生效")


if __name__ == "__main__":
    test_face_trade_same_safe_ok()
    test_face_trade_reject_unsafe_and_remote()
    test_face_trade_meditating_blocked()
    test_face_trade_reject_returns_locked()
    test_npc_shop_pill_clerk()
    test_npc_shop_remote_refused()
    test_auction_bid_refund_and_settle()
    test_auction_expire_no_bid()
    test_auction_expire_with_bid()
    test_buyout_insufficient_no_side_effect()
    test_trade_change_offer_clears_accept()
    test_trade_timeout_refund()
    test_auction_cancel_no_bid()
    test_npc_attitude_price()
    print("\n✅ 坊市四通道测试通过")
