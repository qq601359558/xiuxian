"""QA 第二轮 · 重点 5：死亡瞬间组合（第一轮未定 ② 的行为取证）。

逐项钉住当前行为（资金/物品去向精确断言），供未定清单再裁定引用：
- 寄售在售者死亡后被买入：货款落入死者角色行（不丢失不重复）；
- 拍卖死者出价被超价：冻款退回死者角色行；死者领先到落槌：拍品入死者行囊、卖家照常实收；
- 拍卖卖家死亡后流拍：拍品退回死者行囊；
- 议政已投票者死亡：其票在结算时仍被计入（tally 无存活复核）；
- 书稿持有人死亡：书目仍挂在死者名下（无死亡钩子），新世角色无书；
- 转世归属：同 user 新角色不继承洞府/灵田/灵宠/灵石（字段全默认）。
以上各域 spec 均无死亡后状态条款——行为本身不判缺陷，作未定再裁定证据。
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

from core.books import BOOK_ITEM, BookEngine
from core.clock import WorldClock
from core.council import CouncilEngine
from core.market import MarketEngine
from core.models import CharacterStatus
from core.trade import AuctionEngine
from storage.db import (
    AuctionLotRepository,
    CharacterRepository,
    MarketListingRepository,
    WorldStateRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"
ITEM = "妖兽内丹"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, stones=500, items=(), user=None):
    c = WorldClock.create_new_character(user or f"qa2_{name}_{_tag()}", f"QA2{name}{_tag()}")
    c.location = LOC_A
    c.spirit_stones += stones
    for it in items:
        c.inventory.append(it)
    CharacterRepository.save(c)
    return c


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _listing(lid):
    return next(l for l in MarketListingRepository.list_all() if l.id == lid)


def _lot(lid):
    return next(l for l in AuctionLotRepository.list_all() if l.id == lid)


def _die(c):
    live = _get(c.id)
    live.status = CharacterStatus.DEAD
    CharacterRepository.save(live)


def _cleanup(*chars):
    for c in chars:
        if c is None:
            continue
        live = _get(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


# ---------------- 寄售：死者卖单成交，货款去向 ----------------

def test_consignment_dead_seller_proceeds():
    seller = _char("死售", items=[ITEM])
    buyer = _char("买家", stones=1000)
    try:
        obj = _get(seller.id)
        listing, res = MarketEngine.list_item(obj, ITEM, 300)
        assert res["success"], res
        MarketListingRepository.save(listing)
        CharacterRepository.save(obj)
        _die(seller)
        dead_before = _get(seller.id).spirit_stones
        b = _get(buyer.id)
        lst = _listing(listing.id)
        res2 = MarketEngine.buy_listing(b, lst)
        assert res2["success"], res2
        CharacterRepository.save(b)
        MarketListingRepository.save(lst)
        seller_obj = _get(seller.id)
        paid = MarketEngine.complete_sale_payment(lst, seller_obj)
        assert paid == 300
        CharacterRepository.save(seller_obj)
        assert ITEM in _get(buyer.id).inventory
        # account-death 裁定 1（原“未定②取证”已定案）：死者卖单成交款入账户钱包，不入死行
        from storage.db import LegacyRepository as _LR

        _acc = _LR.get_or_create(seller.user_id)
        assert _acc.wallet_stones >= 300
        assert any(e.kind == "consignment_sale" and e.ref == listing.id for e in _acc.wallet_ledger)
        assert _get(seller.id).spirit_stones == dead_before, (
            "货款 +300 入账户钱包，死者角色行分文不动"
        )
        print("✓ 寄售死亡组合：死者卖单仍可成交，货款 +300 入账户钱包（account-death 裁定 1）")
    finally:
        _cleanup(seller, buyer)


# ---------------- 拍卖：死者出价两路 ----------------

def _make_lot(seller, price=100):
    res = AuctionEngine.list_item(_get(seller.id), ITEM, price)
    assert res["success"], res
    return res["lot"]


def test_auction_dead_bidder_outbid_refund():
    seller = _char("拍售", items=[ITEM])
    a = _char("死价", stones=1000)
    b = _char("活价", stones=1000)
    try:
        lot = _make_lot(seller)
        res = AuctionEngine.bid(_get(a.id), lot.id, 150)
        assert res["success"], res
        a_after_bid = _get(a.id).spirit_stones
        _die(a)
        res2 = AuctionEngine.bid(_get(b.id), lot.id, 200)
        assert res2["success"], res2
        # 评审 M1a（原“未定②取证”已定案）：上一领先者已死，超价退款直接入其账户钱包，不退死行
        from storage.db import LegacyRepository as _LR

        _acc = _LR.get_or_create(a.user_id)
        assert _acc.wallet_stones == 150
        assert any(e.kind == "auction_refund" for e in _acc.wallet_ledger)
        assert _get(a.id).spirit_stones == a_after_bid, (
            "死者被超价：冻款 150 入账户钱包，死者角色行分文不动"
        )
        print("✓ 拍卖死亡组合（超价路）：死者冻款全额退入账户钱包（评审 M1a）")
    finally:
        _cleanup(seller, a, b)


def test_auction_dead_leader_wins_item_to_dead_row():
    seller = _char("拍售乙", items=[ITEM])
    a = _char("死魁", stones=1000)
    try:
        lot = _make_lot(seller)
        res = AuctionEngine.bid(_get(a.id), lot.id, 150)
        assert res["success"], res
        _die(a)
        s_before = _get(seller.id).spirit_stones
        lot_now = _lot(lot.id)
        AuctionEngine.settle_expired(now=lot_now.ends_at + 10)
        lot_done = _lot(lot.id)
        # account-death 裁定 2 兜底（原“未定②取证”已定案）：漏扫的死者领先单落槌时
        # 冻款退钱包、拍品还卖家、单据按流拍计，无钱物双得
        assert lot_done.status.value == "EXPIRED", lot_done
        from storage.db import LegacyRepository as _LR

        assert _LR.get_or_create(a.user_id).wallet_stones == 150
        assert ITEM not in _get(a.id).inventory, "死者不得钱物双得，拍品不交付死者"
        assert ITEM in _get(seller.id).inventory, "拍品按流拍退回卖家"
        assert _get(seller.id).spirit_stones == s_before, "未成交，卖家无实收"
        print("✓ 拍卖死亡组合（落槌兜底）：死者冻款退钱包、拍品还卖家、单据 EXPIRED（account-death 裁定 2）")
    finally:
        _cleanup(seller, a)


def test_auction_dead_seller_no_bid_item_returned():
    seller = _char("拍售丙", items=[ITEM])
    try:
        lot = _make_lot(seller)
        _die(seller)
        AuctionEngine.settle_expired(now=_lot(lot.id).ends_at + 10)
        lot_done = _lot(lot.id)
        assert lot_done.status.value == "EXPIRED", lot_done
        # account-death 裁定 2（原“未定②取证”已定案）：卖家已死，流拍拍品消散，不回死行／新角
        assert ITEM not in _get(seller.id).inventory, "卖家已死，流拍拍品消散"
        print("✓ 拍卖死亡组合（流拍路）：卖家已死，拍品消散（account-death 裁定 2）")
    finally:
        _cleanup(seller)


# ---------------- 议政：死者票计入 ----------------

def test_council_dead_voter_ballot_counted():
    sect = "青云宗"
    key = f"sect_council:{sect}"
    prior = WorldStateRepository.get(key)
    a = _char("议死")
    b = _char("议活")
    try:
        WorldStateRepository.set(key, "")
        t0 = time.time()
        CouncilEngine.advance(sect, now=t0)
        for c, side in ((a, "支持"), (b, "反对")):
            cc = _get(c.id)
            cc.sect = sect
            cc.sect_rank = "内门弟子"
            CharacterRepository.save(cc)
            out = CouncilEngine.vote(_get(c.id), side, now=t0 + 5)
            assert out["success"], out
        _die(a)  # a 投票后身死
        session = CouncilEngine.advance(sect, now=t0 + 30)
        counts = CouncilEngine.tally(sect, session, seats=[])
        assert counts["support"] == 1 and counts["oppose"] == 1, counts
        print("✓ 议政死亡组合：死者已投票在 tally 中仍计入（1 支持 vs 1 反对，未定②取证）")
    finally:
        if prior:
            WorldStateRepository.set(key, prior)
        else:
            WorldStateRepository.set(key, "")
        _cleanup(a, b)


# ---------------- 书稿：持有人死亡 ----------------

def test_manuscript_holder_death_strands_book():
    author = _char("稿者", stones=0)
    holder = _char("持者", stones=1000)
    try:
        a = _get(author.id)
        a.inspiration = 30
        CharacterRepository.save(a)
        obj = _get(author.id)
        res = BookEngine.write_book(obj)
        assert res["success"], res
        CharacterRepository.save(obj)
        book = BookEngine.book_held_by(author.id)
        obj = _get(author.id)
        listing, lres = MarketEngine.list_item(obj, BOOK_ITEM, 100)
        assert lres["success"], lres
        MarketListingRepository.save(listing)
        CharacterRepository.save(obj)
        BookEngine.on_listing_created(_get(author.id), listing.id)
        h = _get(holder.id)
        assert BookEngine.buyer_can_hold(h)
        res2 = MarketEngine.buy_listing(h, _listing(listing.id))
        assert res2["success"], res2
        CharacterRepository.save(h)
        MarketListingRepository.save(_listing(listing.id))
        BookEngine.on_listing_sold(listing.id, _get(holder.id))
        book = BookEngine.book_held_by(holder.id)
        assert book is not None and book.state == "held", book
        _die(holder)
        book2 = BookEngine._repo().get_by_id(book.id) if hasattr(BookEngine._repo(), "get_by_id") else None
        stranded = BookEngine.book_held_by(holder.id)
        assert stranded is not None and stranded.id == book.id, (
            "持有人死亡后书目仍挂其名下（无死亡钩子，现状取证）"
        )
        print("✓ 书稿死亡组合：书目滞留死者名下、无回收钩子（现状取证）")
    finally:
        _cleanup(author, holder)


# ---------------- 转世：新角色零继承 ----------------

def test_reincarnation_inherits_nothing():
    user = f"qa2_转世_{_tag()}"
    first = _char("前世", stones=777, user=user)
    try:
        obj = _get(first.id)
        obj.cave_level = 3
        from core.models import FarmPlot
        obj.farm_plots = [FarmPlot(crop="聚灵草种子", planted_at=1.0, matures_at=2.0)]
        CharacterRepository.save(obj)
        _die(first)
        second = WorldClock.create_new_character(user, f"QA2来世{_tag()}")
        assert second.id != first.id
        assert second.cave_level == 0
        assert all(not p.crop for p in (second.farm_plots or []))
        assert not second.pets if hasattr(second, "pets") else True
        assert second.spirit_stones < 777, "新世灵石为初始值，不继承前世 777+"
        assert _get(first.id).spirit_stones >= 777  # 前世行资产原地封存
        print(f"✓ 转世归属：新角色洞府/灵田/灵石全默认（初始 {second.spirit_stones}），前世资产封存旧行")
        _cleanup(second)
    finally:
        _cleanup(first)
