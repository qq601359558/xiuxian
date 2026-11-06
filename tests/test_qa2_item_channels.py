"""QA 第二轮 · 重点 2：同一物品多通道状态互斥。

一件物品同时只能在一个通道中：典当 / 寄售 / 拍卖 / 装备 / 手稿绑定态。
各通道入口都应以「物品已离开行囊」为互斥基础逐一核查，并补成交侧复核：
- 任一通道占用后，其余通道再取同一件必须失败且零状态变更；
- 手稿在唯一合法通道（寄售）流通时，作者不得另起新篇（防双手稿），
  买家已持书时不得再买（绑定钩子在 handler 层，本文件走引擎+钩子同款序列）。
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
from core.loot_equip import EquipEngine
from core.market import MarketEngine
from core.models import CharacterStatus
from core.pawn import PawnEngine
from core.trade import AuctionEngine
from storage.db import (
    AuctionLotRepository,
    CharacterRepository,
    MarketListingRepository,
    PawnTicketRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"
ITEM = "妖兽内丹"
WEAPON = "青锋剑"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, stones=500, items=()):
    c = WorldClock.create_new_character(f"qa2_{name}_{_tag()}", f"QA2{name}{_tag()}")
    c.location = LOC_A
    c.spirit_stones += stones
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


def _pawn(char):
    obj = _get(char.id)
    ticket, res = PawnEngine.pawn_item(obj, ITEM)
    assert res["success"], res
    PawnTicketRepository.save(ticket)
    CharacterRepository.save(obj)
    return ticket


def _list_consignment(char, price=100):
    obj = _get(char.id)
    listing, res = MarketEngine.list_item(obj, ITEM, price)
    assert res["success"], res
    MarketListingRepository.save(listing)
    CharacterRepository.save(obj)
    return listing


def _list_auction(char, price=100):
    res = AuctionEngine.list_item(_get(char.id), ITEM, price)
    assert res["success"], res
    return res["lot"]


# ---------------- 典当占用 → 其余通道全拒 ----------------

def test_pawned_item_blocked_everywhere():
    c = _char("当占", items=[ITEM])
    try:
        _pawn(c)
        live = _get(c.id)
        assert ITEM not in live.inventory
        listing, res = MarketEngine.list_item(live, ITEM, 100)
        assert listing is None and not res["success"], res
        res2 = AuctionEngine.list_item(_get(c.id), ITEM, 100)
        assert not res2["success"], res2
        res3 = EquipEngine.equip(_get(c.id), ITEM)
        assert not res3["success"], res3
        # 零状态变更：仍只有 1 张票、无挂单无拍品
        assert len(PawnEngine.open_tickets(c.id)) == 1
        assert not [l for l in MarketListingRepository.list_all() if l.seller_id == c.id]
        assert not [l for l in AuctionLotRepository.list_all() if l.seller_id == c.id]
        print("✓ 典当中物品：寄售/拍卖/装备全拒且零变更")
    finally:
        _cleanup(c)


# ---------------- 寄售占用 → 其余通道全拒 ----------------

def test_consigned_item_blocked_everywhere():
    c = _char("寄占", items=[ITEM])
    try:
        _list_consignment(c)
        ticket, res = PawnEngine.pawn_item(_get(c.id), ITEM)
        assert ticket is None and not res["success"], res
        res2 = AuctionEngine.list_item(_get(c.id), ITEM, 100)
        assert not res2["success"], res2
        res3 = MarketEngine.sell_to_guild(_get(c.id), ITEM, 1)
        assert not res3["success"], res3
        assert len([l for l in MarketListingRepository.list_all()
                    if l.seller_id == c.id and l.is_open()]) == 1
        print("✓ 寄售中物品：典当/拍卖/商会回收全拒")
    finally:
        _cleanup(c)


# ---------------- 拍卖占用 → 其余通道全拒 ----------------

def test_auctioned_item_blocked_everywhere():
    c = _char("拍占", items=[ITEM])
    try:
        _list_auction(c)
        ticket, res = PawnEngine.pawn_item(_get(c.id), ITEM)
        assert ticket is None and not res["success"], res
        listing, res2 = MarketEngine.list_item(_get(c.id), ITEM, 100)
        assert listing is None and not res2["success"], res2
        assert len([l for l in AuctionLotRepository.list_all()
                    if l.seller_id == c.id and l.is_open()]) == 1
        print("✓ 拍卖中物品：典当/寄售全拒")
    finally:
        _cleanup(c)


# ---------------- 装备占用 → 其余通道全拒 ----------------

def test_equipped_item_blocked_everywhere():
    c = _char("装占", items=[WEAPON])
    try:
        obj = _get(c.id)
        res = EquipEngine.equip(obj, WEAPON)
        assert res["success"], res
        CharacterRepository.save(obj)
        live = _get(c.id)
        assert WEAPON not in live.inventory and WEAPON in str(live.equipped)
        ticket, resp = PawnEngine.pawn_item(_get(c.id), WEAPON)
        assert ticket is None and not resp["success"] and "卸下" in resp["message"], resp
        listing, res2 = MarketEngine.list_item(_get(c.id), WEAPON, 100)
        assert listing is None and not res2["success"], res2
        res3 = AuctionEngine.list_item(_get(c.id), WEAPON, 100)
        assert not res3["success"], res3
        # 卸下回行囊后通道恢复可用（状态机可逆）
        obj = _get(c.id)
        res4 = EquipEngine.unequip(obj, WEAPON)
        assert res4["success"], res4
        CharacterRepository.save(obj)
        ticket, resp2 = PawnEngine.pawn_item(_get(c.id), WEAPON)
        assert resp2["success"], resp2
        print("✓ 装备中物品：典当（明示先卸下）/寄售/拍卖全拒；卸下后恢复")
    finally:
        _cleanup(c)


# ---------------- 双件同名：一件入通道不误伤另一件 ----------------

def test_two_copies_one_channelled_other_free():
    c = _char("双件", items=[ITEM, ITEM])
    try:
        _pawn(c)  # 当掉第 1 件
        live = _get(c.id)
        assert live.inventory.count(ITEM) == 1
        listing, res = MarketEngine.list_item(live, ITEM, 100)  # 第 2 件可寄售
        assert res["success"], res
        MarketListingRepository.save(listing)
        CharacterRepository.save(live)
        live = _get(c.id)
        assert live.inventory.count(ITEM) == 0
        assert len(PawnEngine.open_tickets(c.id)) == 1
        print("✓ 同名两件：一件典当、一件寄售，计数精确不串扰")
    finally:
        _cleanup(c)


# ---------------- 手稿：寄售中不得另起新篇 ----------------

def test_manuscript_listed_blocks_second_book():
    author = _char("稿主", stones=0)
    try:
        a = _get(author.id)
        a.inspiration = 30
        CharacterRepository.save(a)
        obj = _get(author.id)
        res = BookEngine.write_book(obj)
        assert res["success"], res
        CharacterRepository.save(obj)
        assert BOOK_ITEM in _get(author.id).inventory
        # 走 handler 同款序列：寄售上架 + 书目绑定钩子
        obj = _get(author.id)
        listing, lres = MarketEngine.list_item(obj, BOOK_ITEM, 100)
        assert lres["success"], lres
        MarketListingRepository.save(listing)
        CharacterRepository.save(obj)
        BookEngine.on_listing_created(_get(author.id), listing.id)
        book = BookEngine.book_held_by(author.id)
        assert book is not None and book.state == "listed", book
        # 灵感仍足、寿元仍足，唯一拦截理由应是「已有一部手稿未流通」
        a = _get(author.id)
        a.inspiration = 30
        CharacterRepository.save(a)
        res2 = BookEngine.write_book(_get(author.id))
        assert not res2["success"] and "已有一部手稿" in res2["message"], res2
        assert BookEngine.book_held_by(author.id).id == book.id
        print("✓ 手稿寄售中：作者不得另起新篇（书目绑定按 holder 判定，非行囊）")
    finally:
        _cleanup(author)


def test_manuscript_channels_rejected():
    """手稿除寄售/赠予外全通道拒绝（典当/拍卖/专柜/商会/当面交易口径已钉，
    本轮复核典当与拍卖两处引擎层 fail-closed）。"""
    author = _char("稿拒", stones=0)
    try:
        a = _get(author.id)
        a.inspiration = 30
        CharacterRepository.save(a)
        obj = _get(author.id)
        res = BookEngine.write_book(obj)
        assert res["success"], res
        CharacterRepository.save(obj)
        ticket, resp = PawnEngine.pawn_item(_get(author.id), BOOK_ITEM)
        assert ticket is None and not resp["success"], resp
        res2 = AuctionEngine.list_item(_get(author.id), BOOK_ITEM, 100)
        assert not res2["success"], res2
        res3 = MarketEngine.sell_to_guild(_get(author.id), BOOK_ITEM, 1)
        assert not res3["success"], res3
        assert BOOK_ITEM in _get(author.id).inventory  # 全拒后手稿仍在行囊
        print("✓ 手稿：典当/拍卖/商会回收引擎层全拒，手稿不脱手")
    finally:
        _cleanup(author)
