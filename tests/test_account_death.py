"""
账户层死亡资金归集与死后建角（account-death-rework）
Spec：docs/compose/spec/account-death-rework.md §4 T1–T12
隔离方式：沿用既有共享 DB 做法（见 test_auction.py / test_council.py），
用 ad_ 前缀用户 + 模块收尾（死者置死、OPEN 单据终局、议政 KV 恢复）。
"""
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

import pytest

from storage.db import (
    init_db,
    CharacterRepository,
    LegacyRepository,
    MarketListingRepository,
    AuctionLotRepository,
    PawnTicketRepository,
    BookRepository,
    WorldStateRepository,
)
from core.clock import WorldClock
from core.models import CharacterStatus
from core.market import MarketEngine, ListingStatus
from core.trade import AuctionEngine, AuctionLot, AuctionStatus, TradeSession
from core.council import CouncilEngine
from core.pawn import PawnEngine
from core.legacy import LegacyAccount
from core.wallet import sweep_death_funds, credit_wallet, wallet_summary, withdraw_to_character

init_db()

ITEM = "百年灵芝"
SECT = "AD议政宗"
SECT_A = "AD议政甲"
SECT_B = "AD议政乙"
SECT_C = "AD议政丙"
_lots = []
_listings = []


def _tag():
    return uuid.uuid4().hex[:6]


def _char(name, stones=500, user=None, items=None):
    uid = user or f"ad_{_tag()}_{name}"
    c = WorldClock.create_new_character(uid, f"{name}{_tag()}")
    c.spirit_stones = stones
    c.location = "青云坊市客栈"
    c.born_at = time.time() - 80 * 3600.0
    for it in (items or []):
        c.inventory.append(it)
    CharacterRepository.save(c)
    return c


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _wallet(uid):
    return LegacyRepository.get_or_create(uid)


def _die(c):
    live = _get(c.id)
    live.status = CharacterStatus.DEAD
    CharacterRepository.save(live)
    return live


@pytest.fixture(autouse=True, scope="module")
def _cleanup_module():
    priors = {k: WorldStateRepository.get(f"sect_council:{k}") for k in (SECT, SECT_A, SECT_B, SECT_C)}
    yield
    # 议政 KV 恢复
    try:
        for k, prior in priors.items():
            if prior:
                WorldStateRepository.set(f"sect_council:{k}", prior)
            else:
                WorldStateRepository.set(f"sect_council:{k}", "")
    except Exception:
        pass
    # 本模块 OPEN 拍品到期结算（卖家/领先者按新规则落账，不留 OPEN 残留）
    try:
        now = time.time()
        for lid in _lots:
            lot = AuctionEngine._find(lid)
            if lot is not None and lot.status == AuctionStatus.OPEN:
                lot.ends_at = now - 1
                AuctionLotRepository.save(lot)
        AuctionEngine.settle_expired(now=now)
    except Exception:
        pass
    # 本模块 OPEN 寄售单直接终局（拒售封存单亦然，仅测试库清理）
    try:
        for lst in MarketListingRepository.list_all():
            if lst.id in _listings and lst.is_open():
                lst.status = ListingStatus.CANCELLED
                MarketListingRepository.save(lst)
    except Exception:
        pass
    # 本模块角色全部置死，退出 list_all_alive 口径
    try:
        for c in CharacterRepository.list_all_alive():
            if c.user_id.startswith("ad_"):
                c.status = CharacterStatus.DEAD
                CharacterRepository.save(c)
    except Exception:
        pass


# ---------------- T1 钱包模型 ----------------

def test_wallet_roundtrip():
    uid = f"ad_wallet_{_tag()}"
    acc = LegacyAccount(user_id=uid)
    assert acc.wallet_stones == 0 and acc.wallet_ledger == []
    acc.wallet_stones = 123
    credit_wallet(acc, 45, "death_sweep", "ref-1", "随身 45")
    LegacyRepository.save(acc)
    again = LegacyRepository.get_or_create(uid)
    assert again.wallet_stones == 168
    assert len(again.wallet_ledger) == 1
    assert again.wallet_ledger[0].ref == "ref-1"
    assert again.wallet_ledger[0].amount == 45


def test_wallet_legacy_json_compat():
    old = LegacyAccount.model_validate_json(
        '{"user_id": "ad_old", "points": 3, "total_lives": 1, '
        '"total_points_earned": 3, "death_times": [], "past_lives": []}'
    )
    assert old.wallet_stones == 0 and old.wallet_ledger == []


def test_wallet_withdraw_conservation():
    uid = f"ad_wd_{_tag()}"
    acc = _wallet(uid)
    acc.wallet_stones = 200
    LegacyRepository.save(acc)
    c = _char("提款人", stones=150, user=uid)
    acc = _wallet(uid)
    res = withdraw_to_character(acc, c, 80)
    assert res["success"], res
    LegacyRepository.save(acc)
    CharacterRepository.save(c)
    assert _wallet(uid).wallet_stones == 120
    assert _get(c.id).spirit_stones == 230
    assert any(e.kind == "wallet_withdraw" and e.amount == -80 for e in _wallet(uid).wallet_ledger)
    bad = withdraw_to_character(_wallet(uid), _get(c.id), 999)
    assert bad["success"] is False
    assert _wallet(uid).wallet_stones == 120
    bad2 = withdraw_to_character(_wallet(uid), _get(c.id), 0)
    assert bad2["success"] is False


# ---------------- T2 死亡归集 ----------------

def test_death_sweep_moves_stones_and_zeroes_dead_row():
    c = _char(" sweep者", stones=400)
    c.vault_stones = 250
    CharacterRepository.save(c)
    dead = _die(c)
    acc = _wallet(dead.user_id)
    details = sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)
    assert details["spirit"] == 400 and details["vault"] == 250
    assert _wallet(dead.user_id).wallet_stones == 650
    fresh = _get(dead.id)
    assert fresh.spirit_stones == 0 and fresh.vault_stones == 0
    kinds = [e.kind for e in _wallet(dead.user_id).wallet_ledger]
    assert "death_sweep" in kinds


def test_death_sweep_idempotent():
    c = _char("幂等者", stones=300)
    CharacterRepository.save(c)
    dead = _die(c)
    acc = _wallet(dead.user_id)
    sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)
    before = _wallet(dead.user_id).wallet_stones
    dead2 = _get(dead.id)
    acc2 = _wallet(dead.user_id)
    sweep_death_funds(dead2, acc2)
    LegacyRepository.save(acc2)
    CharacterRepository.save(dead2)
    assert _wallet(dead.user_id).wallet_stones == before
    assert _get(dead.id).spirit_stones == 0


def test_migration_backfill_settled_dead_row():
    """§5.2：已死未转世、death_settled 已真、钱包无 death_sweep 流水 → 补扫。"""
    from server.world import WORLD

    c = _char("补扫者", stones=300)
    c.vault_stones = 50
    c.status = CharacterStatus.DEAD
    c.death_settled = True
    CharacterRepository.save(c)
    assert not any(e.kind == "death_sweep" for e in _wallet(c.user_id).wallet_ledger)
    out = WORLD._settle_if_needed(_get(c.id), cause="身死道消")
    assert out is not None and out.get("backfilled") is True
    assert _wallet(c.user_id).wallet_stones == 350
    assert _get(c.id).spirit_stones == 0 and _get(c.id).vault_stones == 0
    out2 = WORLD._settle_if_needed(_get(c.id), cause="身死道消")
    assert _wallet(c.user_id).wallet_stones == 350, out2


# ---------------- T3/T4/T5 拍卖 ----------------

def _make_lot(seller, price=100):
    res = AuctionEngine.list_item(_get(seller.id), ITEM, price)
    assert res["success"], res
    _lots.append(res["lot"].id)
    return res["lot"]


def test_auction_leader_death_refunds_and_reopens():
    seller = _char("拍售主", items=[ITEM])
    leader = _char("领先死者", stones=1000)
    third = _char("后来者", stones=1000)
    lot = _make_lot(seller)
    res = AuctionEngine.bid(_get(leader.id), lot.id, 150)
    assert res["success"], res
    dead = _die(leader)
    acc = _wallet(dead.user_id)
    details = sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)
    assert any(d["lot_id"] == lot.id and d["amount"] == 150 for d in details["auction_refunds"])
    assert _wallet(dead.user_id).wallet_stones >= 150
    lot_now = AuctionEngine._find(lot.id)
    assert lot_now.leader_id is None and lot_now.current_bid == lot_now.start_price
    assert lot_now.bid_count == 0
    res2 = AuctionEngine.bid(_get(third.id), lot.id, lot_now.start_price)
    assert res2["success"], res2
    assert AuctionEngine._find(lot.id).leader_id == third.id


def test_auction_seller_death_settle_pays_wallet():
    from config import AUCTION_SETTLE_FEE_RATE

    # 到期落槌路
    seller = _char("死卖家", items=[ITEM])
    buyer = _char("得拍者", stones=1000)
    lot = _make_lot(seller)
    assert AuctionEngine.bid(_get(buyer.id), lot.id, 200)["success"]
    _die(seller)
    AuctionEngine.settle_expired(now=AuctionEngine._find(lot.id).ends_at + 10)
    done = AuctionEngine._find(lot.id)
    assert done.status == AuctionStatus.SOLD
    fee = int(200 * AUCTION_SETTLE_FEE_RATE)
    assert _wallet(seller.user_id).wallet_stones == 200 - fee
    assert any(e.kind == "auction_sale" and e.ref == lot.id for e in _wallet(seller.user_id).wallet_ledger)
    assert ITEM in _get(buyer.id).inventory
    # 一口价路
    seller2 = _char("死卖家二", items=[ITEM])
    buyer2 = _char("得拍者二", stones=1000)
    lot2 = _make_lot(seller2)
    AuctionLotRepository.save(AuctionLot(**{**AuctionEngine._find(lot2.id).model_dump(), "buyout_price": 300}))
    _die(seller2)
    res = AuctionEngine.buyout(_get(buyer2.id), lot2.id)
    assert res["success"], res
    fee2 = int(300 * AUCTION_SETTLE_FEE_RATE)
    assert _wallet(seller2.user_id).wallet_stones == 300 - fee2
    assert ITEM in _get(buyer2.id).inventory


def test_auction_settle_dead_leader_fallback():
    # 漏扫：领先者已死但未走 sweep，落槌时退钱＋物还卖家、单据 EXPIRED
    seller = _char("落槌卖家", items=[ITEM])
    leader = _char("漏扫领先", stones=1000)
    lot = _make_lot(seller)
    assert AuctionEngine.bid(_get(leader.id), lot.id, 180)["success"]
    _die(leader)
    AuctionEngine.settle_expired(now=AuctionEngine._find(lot.id).ends_at + 10)
    done = AuctionEngine._find(lot.id)
    assert done.status == AuctionStatus.EXPIRED
    assert _wallet(leader.user_id).wallet_stones == 180
    assert ITEM in _get(seller.id).inventory
    # 卖家亦死 → 拍品消散
    seller2 = _char("双死卖家", items=[ITEM])
    leader2 = _char("漏扫领先二", stones=1000)
    lot2 = _make_lot(seller2)
    assert AuctionEngine.bid(_get(leader2.id), lot2.id, 180)["success"]
    _die(leader2)
    _die(seller2)
    AuctionEngine.settle_expired(now=AuctionEngine._find(lot2.id).ends_at + 10)
    done2 = AuctionEngine._find(lot2.id)
    assert done2.status == AuctionStatus.EXPIRED
    assert _wallet(leader2.user_id).wallet_stones == 180
    assert ITEM not in _get(seller2.id).inventory


# ---------------- T6/T7 寄售 ----------------

def _list_item(seller_obj, price):
    listing, res = MarketEngine.list_item(seller_obj, ITEM, price)
    assert res["success"], res
    MarketListingRepository.save(listing)
    CharacterRepository.save(seller_obj)
    _listings.append(listing.id)
    return listing


def test_consignment_seller_death_sale_pays_wallet():
    seller = _char("寄售死者", items=[ITEM])
    buyer = _char("寄售买家", stones=1000)
    listing = _list_item(_get(seller.id), 300)
    assert listing.seller_user_id == seller.user_id
    dead_before = _get(seller.id).spirit_stones
    _die(seller)
    b = _get(buyer.id)
    lst = next(l for l in MarketListingRepository.list_all() if l.id == listing.id)
    res = MarketEngine.buy_listing(b, lst)
    assert res["success"], res
    CharacterRepository.save(b)
    paid = MarketEngine.complete_sale_payment(lst, _get(seller.id))
    MarketListingRepository.save(lst)
    assert paid == 300
    assert _wallet(seller.user_id).wallet_stones == 300
    assert any(e.kind == "consignment_sale" and e.ref == listing.id for e in _wallet(seller.user_id).wallet_ledger)
    assert ITEM in _get(buyer.id).inventory
    assert _get(buyer.id).spirit_stones == 1000 - 300
    assert _get(seller.id).spirit_stones == dead_before  # 成交款入钱包，死行不得再收钱


def test_consignment_legacy_unresolvable_refused_without_charge():
    from core.market import MarketListing as _ML

    listing = _ML(
        seller_id="ghost_seller_id",
        seller_name="查无此人道号",
        item_name=ITEM,
        kind="material",
        price=200,
        status=ListingStatus.OPEN,
        created_at=time.time(),
    )
    assert listing.seller_user_id == ""
    MarketListingRepository.save(listing)
    _listings.append(listing.id)
    buyer = _char("无辜买家", stones=1000)
    b = _get(buyer.id)
    res = MarketEngine.buy_listing(b, listing)
    assert res["success"] is False
    assert "不可考" in res["message"]
    assert _get(buyer.id).spirit_stones == 1000
    assert next(l for l in MarketListingRepository.list_all() if l.id == listing.id).is_open()


def test_consignment_legacy_backfilled_pays_wallet():
    from core.market import MarketListing as _ML

    seller = _char("旧单死者", items=[ITEM])
    # 旧单：无 seller_user_id，但 seller_id 命中死行 → 回填放行，款入钱包
    listing = _ML(
        seller_id=seller.id,
        seller_name=seller.name,
        item_name=ITEM,
        kind="material",
        price=250,
        status=ListingStatus.OPEN,
        created_at=time.time(),
    )
    MarketListingRepository.save(listing)
    _listings.append(listing.id)
    _die(seller)
    buyer = _char("旧单买家", stones=1000)
    b = _get(buyer.id)
    res = MarketEngine.buy_listing(b, listing)
    assert res["success"], res
    CharacterRepository.save(b)
    paid = MarketEngine.complete_sale_payment(listing, _get(seller.id))
    MarketListingRepository.save(listing)
    assert paid == 250
    assert _wallet(seller.user_id).wallet_stones == 250


# ---------------- T8 议政 ----------------

def _sect_char(name, side=None, t0=None, sect=SECT):
    c = _char(name)
    cc = _get(c.id)
    cc.sect = sect
    cc.sect_rank = "内门弟子"
    CharacterRepository.save(cc)
    if side is not None:
        out = CouncilEngine.vote(_get(c.id), side, now=t0)
        assert out["success"], out
    return c


def test_council_dead_vote_voided():
    t0 = time.time()
    CouncilEngine.advance(SECT_A, now=t0)
    a = _sect_char("议死者", "支持", t0 + 5, sect=SECT_A)
    _sect_char("议活者", "反对", t0 + 5, sect=SECT_A)
    dead = _die(a)
    sweep_death_funds(dead, _wallet(dead.user_id))
    session = CouncilEngine.advance(SECT_A, now=t0 + 30)
    assert dead.id not in (session.get("votes") or {})
    counts = CouncilEngine.tally(SECT_A, session, seats=[])
    assert counts["support"] == 0 and counts["oppose"] == 1, counts


def test_council_no_double_vote_after_rebirth():
    t0 = time.time()
    CouncilEngine.advance(SECT_B, now=t0)
    a = _sect_char("重生议者", "支持", t0 + 5, sect=SECT_B)
    dead = _die(a)
    sweep_death_funds(dead, _wallet(dead.user_id))
    # 同账户新角（新 id）入宗再投：全场只应有一张玩家票
    new = WorldClock.create_new_character(a.user_id, f"重生议者{_tag()}")
    new.sect = SECT_B
    new.sect_rank = "内门弟子"
    new.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(new)
    out = CouncilEngine.vote(_get(new.id), "支持", now=t0 + 10)
    assert out["success"], out
    session = CouncilEngine.advance(SECT_B, now=t0 + 30)
    counts = CouncilEngine.tally(SECT_B, session, seats=[])
    assert counts["support"] == 1 and counts["oppose"] == 0, counts


def test_council_settled_snapshot_immutable():
    t0 = time.time()
    CouncilEngine.advance(SECT_C, now=t0)
    a = _sect_char("已结算议者", "支持", t0 + 5, sect=SECT_C)
    session = CouncilEngine.advance(SECT_C, now=t0 + 7201)
    assert session.get("settled") is True
    result_before = dict(session.get("result") or {})
    assert result_before, session
    dead = _die(a)
    sweep_death_funds(dead, _wallet(dead.user_id))
    session2 = CouncilEngine._load_session(SECT_C)
    assert (session2.get("result") or {}) == result_before
    assert dead.id in (session2.get("votes") or {})


# ---------------- T9 典当 ----------------

def test_pawn_death_forfeits_without_double_count():
    c = _char("当票死者", stones=500, items=[ITEM])
    pc = _get(c.id)
    ticket, res = PawnEngine.pawn_item(pc, ITEM)
    assert res["success"], res
    PawnTicketRepository.save(ticket)
    CharacterRepository.save(pc)
    principal = ticket.principal
    dead = _die(c)
    # 死前随身 = 500 + 本金；寄存 0
    spirit_before = _get(dead.id).spirit_stones
    assert spirit_before == 500 + principal
    acc = _wallet(dead.user_id)
    details = sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)
    assert _wallet(dead.user_id).wallet_stones == spirit_before
    assert any(t["item"] == ITEM for t in details["pawn_forfeits"])
    tickets = PawnTicketRepository.list_by_owner(dead.id)
    assert all(t.status.value == "FORFEITED" for t in tickets if t.id == ticket.id)
    # 当铺寄售已生成（卖家为当铺，买家可正常买，不触发不可考拒售）
    shop_lots = [l for l in MarketListingRepository.list_all()
                 if l.seller_id == "pawn_shop" and l.item_name == ITEM and l.is_open()]
    assert shop_lots, "当票没收后当铺寄售应存在"


# ---------------- T10 无资金残留 ----------------

def test_no_funds_leak_on_death():
    from core.trade import _trade_sessions, _trade_by_user

    seller = _char("守恒卖家", items=[ITEM])
    dead = _char("守恒死者", stones=700)
    live = _char("守恒活人", stones=400)
    lot = _make_lot(seller)
    assert AuctionEngine.bid(_get(dead.id), lot.id, 200)["success"]
    # 当面交易会话：死者锁定 50 灵石＋1 件货，活人锁定 30 灵石
    dead_live = _get(dead.id)
    dead_live.inventory.append(ITEM)
    dead_live.spirit_stones -= 50
    live_live = _get(live.id)
    live_live.spirit_stones -= 30
    CharacterRepository.save(dead_live)
    CharacterRepository.save(live_live)
    sess = TradeSession(
        a_id=dead.id, a_name=dead.name, b_id=live.id, b_name=live.name,
        a_stones=50, a_items=[ITEM], b_stones=30, b_items=[],
        location="青云坊市客栈", created_at=time.time(),
    )
    _trade_sessions[sess.id] = sess
    _trade_by_user[dead.id] = sess.id
    _trade_by_user[live.id] = sess.id
    wallet0 = _wallet(dead.user_id).wallet_stones
    # 守恒口径：钱包＋死者随身＋寄存＋拍卖冻结＋交易锁定（死者侧）＋活人随身
    dead_now = _get(dead.id)
    total_before = (
        wallet0 + dead_now.spirit_stones + dead_now.vault_stones
        + 200 + 50 + _get(live.id).spirit_stones + 30  # 活人锁定在会话中的 30
    )
    dead2 = _die(dead)
    acc = _wallet(dead.user_id)
    sweep_death_funds(dead2, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead2)
    total_after = _wallet(dead.user_id).wallet_stones + _get(live.id).spirit_stones
    assert total_after == total_before, (total_before, total_after)
    assert sess.id not in _trade_sessions
    assert _get(live.id).spirit_stones == 400  # 活人锁定 30 已退回
    assert _get(dead.id).spirit_stones == 0


def test_books_pending_prestige_not_paid_to_new_life():
    from core.books import Book, BookEngine

    author = _char("著书旧世", stones=0)
    old_id = author.id
    book = Book(author_id=old_id, author_name=author.name, title="旧世残卷",
                holder_id=old_id, holder_name=author.name, state="held",
                prestige_pending=10)
    BookRepository.save(book)
    # 转世：同账户新角（新 id）覆写旧行
    new = WorldClock.create_new_character(author.user_id, f"著书新世{_tag()}")
    CharacterRepository.save(new)
    settled = BookEngine._settle_pending_prestige(book)
    assert settled == 0
    assert book.prestige_pending == 0
    assert _get(new.id).prestige == 0


# ---------------- T11 Web 登录 ----------------

def _http_post(port, path, payload):
    import json
    import urllib.request

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_web_login_dead_no_auto_rebirth_and_explicit_reincarnate():
    from http.server import ThreadingHTTPServer
    import threading
    from server.app import GameHandler
    from core.account import register as acct_register

    tag = _tag()
    username = f"ad{tag}"
    reg = acct_register(username, "123456", display_name=f"死者{tag}")
    assert reg["ok"], reg
    uid = reg["user_id"]
    # 首世：用 join 建角（模拟注册后首世），再置死并放钱
    from server.world import WORLD

    joined = WORLD.join(f"首世{tag}", user_id=uid)
    assert joined.get("token")
    c = CharacterRepository.get_by_user_id(uid)
    c.spirit_stones = 300
    c.vault_stones = 100
    CharacterRepository.save(c)
    _die(c)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        out = _http_post(port, "/login", {"username": username, "password": "123456"})
        assert out.get("dead") is True, out
        assert out.get("wallet", {}).get("balance") == 400, out
        assert out.get("death_cause")
        assert out.get("token")
        still = CharacterRepository.get_by_user_id(uid)
        assert still.status == CharacterStatus.DEAD, "登录死者不得自动建角"
        # 显式 /转世
        out2 = _http_post(port, "/action", {"token": out["token"], "command": "/转世 重生道号"})
        assert out2.get("ok") is True, out2
        assert out2.get("wallet", {}).get("balance") == 400, out2
        new = CharacterRepository.get_by_user_id(uid)
        assert new.status != CharacterStatus.DEAD
        stones_final = new.origin["stones_final"]
        assert 80 <= stones_final <= 260
        assert new.spirit_stones == stones_final  # 出身灵石（Spec §3.5），钱包不自动划转
        # 新账号经 /register 仍自动建首世
        out3 = _http_post(port, "/register", {"username": f"ad{tag}z", "password": "123456"})
        assert out3.get("ok") is True, out3
        assert out3.get("is_new_life") is True, out3
        r3 = acct_register(f"ad{tag}y", "123456", display_name=f"新修{tag}")
        assert r3["ok"], r3
        j3 = WORLD.join(f"新修{tag}", user_id=r3["user_id"])
        assert j3.get("is_new_life") is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_web_status_wallet_block():
    from server.world import WORLD

    c = _char("钱包展示者", stones=150)
    acc = _wallet(c.user_id)
    acc.wallet_stones = 77
    credit_wallet(acc, 5, "death_sweep", "w-ref", "测试")
    LegacyRepository.save(acc)
    joined = WORLD.join(c.name, user_id=c.user_id)
    status = WORLD._status_dict(CharacterRepository.get_by_user_id(c.user_id))
    assert status["wallet"]["balance"] >= 77
    assert len(status["wallet"]["entries"]) >= 1
    # /钱包 与 /钱包提取 命令
    res = WORLD.handle(joined["token"], "/钱包")
    assert res.get("ok") is True and "82" in res.get("text", "")
    res2 = WORLD.handle(joined["token"], "/钱包提取 27")
    assert res2.get("ok") is True, res2
    assert _wallet(c.user_id).wallet_stones == 55
    res3 = WORLD.handle(joined["token"], "/钱包提取 99999")
    assert res3.get("ok") is False


# ---------------- T12 CLI ----------------

def test_cli_death_settlement_and_rebirth_guidance(monkeypatch):
    import cli.main as cm

    c = _char("CLI死者", stones=300)
    c.vault_stones = 60
    CharacterRepository.save(c)
    dead = _die(c)
    printed = []
    monkeypatch.setattr(cm.console, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    answers = iter(["y", "CLI新道号", ""])
    monkeypatch.setattr(cm.Prompt, "ask", lambda *a, **k: next(answers))
    new = cm.settle_and_reincarnate(_get(dead.id), "身死道消", c.user_id)
    assert new is not None
    stones_final = new.origin["stones_final"]
    assert 80 <= stones_final <= 260
    assert new.spirit_stones == stones_final
    assert _wallet(c.user_id).wallet_stones == 360
    blob = "\n".join(printed)
    assert "360" in blob, blob
    assert "/钱包提取" in blob, blob


def test_cli_reincarnate_gate_still_blocks(monkeypatch):
    import cli.main as cm

    c = _char("CLI门挡者", stones=200)
    CharacterRepository.save(c)
    dead = _die(c)
    acc = _wallet(c.user_id)
    now = time.time()
    acc.death_times = [now] * 12
    LegacyRepository.save(acc)
    called = []
    monkeypatch.setattr(cm.Prompt, "ask", lambda *a, **k: called.append(1) or "y")
    out = cm.settle_and_reincarnate(_get(dead.id), "身死道消", c.user_id)
    assert out is None
    assert called == [], "轮回门挡下时不得询问转世"
    assert _wallet(c.user_id).wallet_stones == 200  # 结算先行，钱已归集


def test_cli_wallet_commands_present():
    import inspect

    import cli.main as cm

    src = inspect.getsource(cm)
    assert "/钱包" in src and "/钱包提取" in src


# ---------------- 评审修复（must-fix / should-fix 回归） ----------------

def test_m1a_outbid_refund_dead_leader_goes_to_wallet_not_dead_row():
    seller = _char("M1拍售主", items=[ITEM])
    leader = _char("M1死领先", stones=1000)
    third = _char("M1后来者", stones=1000)
    lot = _make_lot(seller)
    assert AuctionEngine.bid(_get(leader.id), lot.id, 150)["success"]
    dead = _die(leader)
    spirit_before = _get(dead.id).spirit_stones  # 出价后 850，死行不得再收退款
    res = AuctionEngine.bid(_get(third.id), lot.id, 200)
    assert res["success"], res
    assert _wallet(dead.user_id).wallet_stones == 150
    assert _get(dead.id).spirit_stones == spirit_before


def test_m1c_sweep_after_death_new_money_residual_on_relogin_and_crash_replay():
    from server.world import WORLD

    c = _char("M1残差者", stones=300)
    dead = _die(c)
    acc = _wallet(dead.user_id)
    sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    # 模拟“旧规则已结算行”：death_settled 置真，后续 server 入口走补扫分支
    dead.death_settled = True
    CharacterRepository.save(dead)
    assert _wallet(dead.user_id).wallet_stones == 300
    # sweep 后又落入死行的钱（模拟旧付款路径漏网）：server 补扫须残差入账，不得清零丢弃
    row = _get(dead.id)
    row.spirit_stones = 200
    CharacterRepository.save(row)
    out = WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    assert out is not None and out.get("backfilled") is True, out
    assert _wallet(dead.user_id).wallet_stones == 500, out
    assert _get(dead.id).spirit_stones == 0
    # 崩溃重放模拟：残差已入账（账户已保存）但死行未清零 → 再扫不得双记，只清零
    row2 = _get(dead.id)
    row2.spirit_stones = 200
    CharacterRepository.save(row2)
    # 注意：此时残差 ref 已存在（金额相同），重放应跳过入账
    out2 = WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    assert _wallet(dead.user_id).wallet_stones == 500, out2
    assert _get(dead.id).spirit_stones == 0


def test_m2_join_with_dead_user_id_returns_dead_payload_no_new_row():
    from server.world import WORLD

    c = _char("M2死者", stones=300)
    old_id = c.id
    uid = c.user_id
    _die(c)
    out = WORLD.join(c.name, user_id=uid)
    assert out.get("dead") is True, out
    assert out.get("token")
    still = CharacterRepository.get_by_user_id(uid)
    assert still.id == old_id and still.status == CharacterStatus.DEAD
    # 该 token 可显式 /转世
    res = WORLD.reincarnate(out["token"], name="M2新世")
    assert res.get("ok") is True or "name" in res, res
    assert CharacterRepository.get_by_user_id(uid).id != old_id
    # 匿名 /join 保持自动建角（道号加唯一后缀，避开共享库按名续玩旧角）
    anon = WORLD.join(f"M2匿名客{_tag()}", user_id=None)
    assert anon.get("is_new_life") is True
    assert str(anon.get("user_id", "")).startswith("lan_")


def test_m3_consignment_same_account_new_char_cannot_buy_old_listing():
    seller = _char("M3寄售旧世", items=[ITEM])
    listing = _list_item(_get(seller.id), 300)
    uid = seller.user_id
    _die(seller)
    new = WorldClock.create_new_character(uid, f"M3寄售新世{_tag()}")
    new.spirit_stones = 1000
    CharacterRepository.save(new)
    buyer = _get(new.id)
    lst = next(l for l in MarketListingRepository.list_all() if l.id == listing.id)
    res = MarketEngine.buy_listing(buyer, lst)
    assert res["success"] is False, res
    assert _get(new.id).spirit_stones == 1000
    assert next(l for l in MarketListingRepository.list_all() if l.id == listing.id).is_open()


def test_m3_auction_same_account_new_char_cannot_bid_or_buyout():
    seller = _char("M3拍卖旧世", items=[ITEM])
    lot = _make_lot(seller)
    AuctionLotRepository.save(AuctionLot(**{**AuctionEngine._find(lot.id).model_dump(), "buyout_price": 500}))
    uid = seller.user_id
    _die(seller)
    new = WorldClock.create_new_character(uid, f"M3拍卖新世{_tag()}")
    new.spirit_stones = 1000
    CharacterRepository.save(new)
    buyer = _get(new.id)
    res = AuctionEngine.bid(buyer, lot.id, 150)
    assert res["success"] is False, res
    res2 = AuctionEngine.buyout(buyer, lot.id)
    assert res2["success"] is False, res2
    assert AuctionEngine._find(lot.id).status == AuctionStatus.OPEN


def test_m4_migration_script_demo_and_backfill_on_sale(tmp_path, monkeypatch):
    import json
    import subprocess

    # 成交写回：旧单无 seller_user_id，seller_id 命中死行 → 成交后 DB 旧单带 seller_user_id
    seller = _char("M4旧单死者", items=[ITEM])
    from core.market import MarketListing as _ML

    listing = _ML(
        seller_id=seller.id, seller_name=seller.name, item_name=ITEM,
        kind="material", price=250, status=ListingStatus.OPEN, created_at=time.time(),
    )
    MarketListingRepository.save(listing)
    _listings.append(listing.id)
    _die(seller)
    buyer = _char("M4旧单买家", stones=1000)
    res = MarketEngine.buy_listing(_get(buyer.id), listing)
    assert res["success"], res
    CharacterRepository.save(_get(buyer.id))
    MarketEngine.complete_sale_payment(listing, _get(seller.id))
    MarketListingRepository.save(listing)
    reloaded = next(l for l in MarketListingRepository.list_all() if l.id == listing.id)
    assert reloaded.seller_user_id == seller.user_id
    # 演练脚本：只跑临时数据目录
    script = Path(__file__).resolve().parent.parent / "tools" / "migrate_account_death.py"
    assert script.exists(), "tools/migrate_account_death.py 缺失"
    demo_dir = tmp_path / "demo-data"
    proc = subprocess.run(
        [sys.executable, str(script), "--data-dir", str(demo_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "回填寄售单：1" in proc.stdout, proc.stdout
    assert "不可考封存单：1" in proc.stdout, proc.stdout
    assert "已转世账户数：1" in proc.stdout, proc.stdout
    assert "不得凭空" in proc.stdout or "不估算金额" in proc.stdout, proc.stdout
    assert (demo_dir / "tiandao.db").exists()
    # 拒绝真实数据目录
    real_data = Path(__file__).resolve().parent.parent / "data"
    proc2 = subprocess.run(
        [sys.executable, str(script), "--data-dir", str(real_data)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc2.returncode != 0, proc2.stdout + proc2.stderr


def test_m5_sweep_partial_errors_and_death_settled_semantics(monkeypatch):
    from server.world import WORLD
    from storage.db import ChronicleRepository
    from core.pawn import PawnEngine

    c = _char("M5部分死者", stones=300)
    dead = _die(c)
    monkeypatch.setattr(PawnEngine, "forfeit_all", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pawn boom")))
    out = WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    assert out is not None, out
    sweep = out.get("sweep") or {}
    assert sweep.get("errors"), sweep
    assert any(e.get("step") == "pawn" for e in sweep["errors"]), sweep
    assert _get(dead.id).death_settled is True
    recents = ChronicleRepository.get_recent(30)
    assert any("WALLET_SWEEP_PARTIAL" in s for s in recents), recents
    # 随身归集步异常须上传：death_settled 不得被置真
    c2 = _char("M5随身死者", stones=300)
    dead2 = _die(c2)
    import core.wallet as _w

    def _boom(*a, **k):
        raise RuntimeError("wallet boom")

    monkeypatch.setattr(_w, "credit_wallet", _boom)
    with pytest.raises(RuntimeError):
        WORLD._settle_if_needed(_get(dead2.id), cause="身死道消")
    assert _get(dead2.id).death_settled is False


def test_s1_sweep_total_includes_auction_refunds():
    seller = _char("S1拍售主", items=[ITEM])
    leader = _char("S1领先死者", stones=1000)
    lot = _make_lot(seller)
    assert AuctionEngine.bid(_get(leader.id), lot.id, 150)["success"]
    dead = _die(leader)
    acc = _wallet(dead.user_id)
    details = sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)
    refunds = sum(r["amount"] for r in details["auction_refunds"])
    assert details["total"] == details["spirit"] + details["vault"] + refunds
    assert _wallet(dead.user_id).wallet_stones == details["total"]


def test_s2_in_game_death_response_carries_sweep_and_death_cause(monkeypatch):
    from server.world import WORLD, BreakthroughEngine

    c = _char("S2渡劫者", stones=300)
    cc = _get(c.id)
    cc.realm.current_exp = cc.realm.max_exp
    CharacterRepository.save(cc)
    joined = WORLD.join(cc.name, user_id=cc.user_id)
    monkeypatch.setattr(
        BreakthroughEngine, "attempt_breakthrough",
        lambda *a, **k: {"is_fatal": True, "success": False, "message": "渡劫陨落"},
    )
    out = WORLD.handle(joined["token"], "/突破")
    assert out.get("death") is True, out
    assert out.get("sweep") is not None, out
    assert out.get("death_cause") == "渡劫陨落", out


def test_s3_s4_sweep_and_dead_payload_consignment_count_and_lifespan():
    from server.world import WORLD

    seller = _char("S34死者", stones=300, items=[ITEM, ITEM])
    _list_item(_get(seller.id), 100)
    # 第二单：再挂一件（需补货）
    s2 = _get(seller.id)
    s2.inventory.append(ITEM)
    CharacterRepository.save(s2)
    _list_item(_get(seller.id), 120)
    dead = _die(seller)
    acc = _wallet(dead.user_id)
    details = sweep_death_funds(dead, acc)
    assert details.get("consignment_open_count") == 2, details
    payload = WORLD.dead_payload(dead.user_id, username="s34")
    assert payload is not None and payload.get("dead") is True
    assert payload.get("consignment_open_count") == 2, payload
    lived = (payload.get("legacy") or {}).get("lifespan_lived")
    assert lived is not None and lived > 0, payload
    assert "享寿" in (Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(encoding="utf-8")


def test_s5_cli_settled_branch_prints_wallet_panel(monkeypatch):
    import cli.main as cm

    c = _char("S5已结算者", stones=0)
    dead = _die(c)
    dead.death_settled = True
    CharacterRepository.save(dead)
    acc = _wallet(c.user_id)
    acc.wallet_stones = 123
    LegacyRepository.save(acc)
    printed = []
    monkeypatch.setattr(cm.console, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    monkeypatch.setattr(cm.Prompt, "ask", lambda *a, **k: "n")
    out = cm.settle_and_reincarnate(_get(dead.id), "身死道消", c.user_id)
    assert out is None
    blob = "\n".join(printed)
    assert "账户钱包" in blob and "123" in blob, blob


def test_s6_auction_settle_duplicate_vs_failure(monkeypatch):
    from config import AUCTION_SETTLE_FEE_RATE
    from storage.db import ChronicleRepository
    from core.wallet import credit_wallet as _cw

    # duplicate：卖家钱包已有同 lot.id 的 auction_sale 流水 → 视为已付，不双记、不告警
    seller = _char("S6死卖家", items=[ITEM])
    buyer = _char("S6得拍者", stones=1000)
    lot = _make_lot(seller)
    assert AuctionEngine.bid(_get(buyer.id), lot.id, 200)["success"]
    acc = _wallet(seller.user_id)
    _cw(acc, 999, "auction_sale", lot.id, "预置已付")
    LegacyRepository.save(acc)
    _die(seller)
    notes = AuctionEngine.settle_expired(now=AuctionEngine._find(lot.id).ends_at + 10)
    assert AuctionEngine._find(lot.id).status == AuctionStatus.SOLD
    assert _wallet(seller.user_id).wallet_stones == 999
    assert not any("落账失败" in n for n in notes), notes
    # failure：钱包落账返回失败 → 大事记/告警，不得静默
    seller2 = _char("S6死卖家二", items=[ITEM])
    buyer2 = _char("S6得拍者二", stones=1000)
    lot2 = _make_lot(seller2)
    assert AuctionEngine.bid(_get(buyer2.id), lot2.id, 200)["success"]
    _die(seller2)
    import core.trade as _t

    monkeypatch.setattr(_t, "_credit_wallet_amount", lambda *a, **k: "failed")
    notes2 = AuctionEngine.settle_expired(now=AuctionEngine._find(lot2.id).ends_at + 10)
    assert AuctionEngine._find(lot2.id).status == AuctionStatus.SOLD
    assert ITEM in _get(buyer2.id).inventory
    assert any("落账失败" in n for n in notes2), notes2
    recents = ChronicleRepository.get_recent(30)
    assert any("AUCTION_PAY_FAIL" in s for s in recents), recents


def test_s9_lan_anonymous_user_also_walks_wallet():
    from server.world import WORLD

    anon = WORLD.join("S9匿名客", user_id=None)
    uid = anon["user_id"]
    assert str(uid).startswith("lan_")
    c = CharacterRepository.get_by_user_id(uid)
    c.spirit_stones = 400
    c.vault_stones = 60
    CharacterRepository.save(c)
    _die(c)
    WORLD._settle_if_needed(_get(c.id), cause="身死道消")
    acc = LegacyRepository.get_or_create(uid)
    assert acc.wallet_stones == 460
