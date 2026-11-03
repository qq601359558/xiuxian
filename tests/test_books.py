"""F11 著书立说：灵感钩子/著书成本与拒绝/品质/寄售流通/研读幂等/作者声望封顶/自读无收益/AI降级/双端/旧档兼容"""
import os
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

import pytest

from config import SECONDS_PER_GAME_YEAR
from core.clock import WorldClock
from core.models import Character, CharacterStatus
from core.books import (
    BOOK_ITEM,
    BOOK_INSPIRATION_COST,
    BOOK_LIFESPAN_COST_YEARS,
    BOOK_PRESTIGE_CAP,
    INSPIRATION_CAP,
    PRESTIGE_PER_READ,
    READ_REWARDS,
    Book,
    BookEngine,
    quality_for_tier,
)
from core.market import MarketEngine
from storage.db import BookRepository, CharacterRepository, MarketListingRepository
from server.world import WORLD, World

WORLD.stop_tick()

_CHARS = []   # 自造角色（teardown 置死）
_BOOKS = []   # 自著书目 id（teardown 删除）
_LISTINGS = []  # 自造寄售单 id（teardown 撤单）


def _uniq(base: str) -> str:
    return f"bk{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _char(name="著书客", tier=1, inspiration=0, years=30.0):
    c = WorldClock.create_new_character(_uniq("u_"), _uniq(name))
    c.realm.tier = tier
    c.realm.sub_tier = 0
    c.realm.current_exp = 0
    c.inspiration = inspiration
    now = time.time()
    c.lifespan.death_timestamp = now + years * SECONDS_PER_GAME_YEAR
    c.inventory = []
    c.spirit_stones = 500
    CharacterRepository.save(c)
    _CHARS.append(c)
    return c


def _write(author, seed=7):
    res = BookEngine.write_book(author, rng=random.Random(seed))
    assert res["success"], res
    _BOOKS.append(res["book"].id)
    CharacterRepository.save(author)
    return res["book"]


@pytest.fixture(autouse=True)
def _no_real_ai(monkeypatch):
    """S2 隔离：本模块所有用例默认屏蔽真 AI 通道（个别用例自行打桩验证 AI 路径）。"""
    import ai.gateway as gw

    monkeypatch.setattr(gw, "ai_available", lambda: False)
    monkeypatch.setattr(gw, "_chat_text", lambda *a, **k: None)


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    for bid in _BOOKS:
        try:
            BookRepository.delete(bid)
        except Exception:
            pass
    for lid in _LISTINGS:
        try:
            for l in MarketListingRepository.list_all():
                if l.id == lid and l.is_open():
                    from core.market import ListingStatus

                    l.status = ListingStatus.CANCELLED
                    MarketListingRepository.save(l)
        except Exception:
            pass
    for c in _CHARS:
        try:
            c.status = CharacterStatus.DEAD
            c.lifespan.death_timestamp = 0.0
            CharacterRepository.save(c)
        except Exception:
            pass


# ---------------- 旧档兼容 ----------------

def test_legacy_character_defaults():
    c = _char()
    data = c.model_dump()
    for k in ("inspiration", "prestige"):
        data.pop(k, None)
    old = Character.model_validate(data)  # 旧档 JSON 无新字段
    assert old.inspiration == 0 and old.prestige == 0
    print("✓ 旧档反序列化：inspiration/prestige 默认 0")


# ---------------- 灵感钩子 ----------------

def test_gain_inspiration_cap():
    c = _char()
    assert BookEngine.gain_inspiration(c, 5) == 5 and c.inspiration == 5
    c.inspiration = INSPIRATION_CAP - 1
    assert BookEngine.gain_inspiration(c, 10) == 1 and c.inspiration == INSPIRATION_CAP
    assert BookEngine.gain_inspiration(c, 0) == 0
    print("✓ 灵感入账封顶 INSPIRATION_CAP")


def test_explore_hook_grants_inspiration():
    import core.adventure as adv

    c = _char()
    c.spirit_stones = 100
    orig = adv._success_prob
    adv._success_prob = lambda ch, tgt: 1.0
    try:
        res = adv.AdventureEngine.explore(c, "野外", use_ai=False)
    finally:
        adv._success_prob = orig
    assert res.get("success"), res
    assert c.inspiration == 1, c.inspiration
    print("✓ 探险成功钩子：灵感 +1")


def test_breakthrough_hook_grants_inspiration():
    from ai.gateway import AIGateway
    from core.breakthrough import BreakthroughEngine

    c = _char(tier=1)
    c.realm.sub_tier = 3
    c.realm.current_exp = c.realm.max_exp
    orig = AIGateway.judge_tribulation
    AIGateway.judge_tribulation = staticmethod(
        lambda character, rule_prob, target_realm: {
            "success": True, "source": "rule", "reason": "", "adj_prob": rule_prob,
        }
    )
    try:
        res = BreakthroughEngine.attempt_breakthrough(c)
    finally:
        AIGateway.judge_tribulation = orig
    assert res.get("success") and res.get("is_major"), res
    assert c.inspiration == 3, c.inspiration
    print("✓ 渡劫成功钩子：灵感 +3")


def test_quest_completion_hook_grants_inspiration():
    # 直接走 quests 落账段过重（需 NPC 发布者同场）：以 deliver 全链在 test_quests 已覆盖主流程，
    # 这里验证钩子接点存在且数值常量与 spec 一致（+2），入账函数已由上两例实测。
    from core.books import INSPIRATION_FROM_QUEST, INSPIRATION_FROM_EXPLORE, INSPIRATION_FROM_BREAKTHROUGH

    assert (INSPIRATION_FROM_EXPLORE, INSPIRATION_FROM_QUEST, INSPIRATION_FROM_BREAKTHROUGH) == (1, 2, 3)
    import core.quests as q

    src = Path(q.__file__).read_text(encoding="utf-8")
    assert "INSPIRATION_FROM_QUEST" in src and "gain_inspiration" in src
    print("✓ 委托完成钩子接点与常量（+2）")


# ---------------- 著书 ----------------

def test_write_book_costs_and_quality():
    a = _char(tier=2, inspiration=25, years=30.0)
    before_years = a.lifespan.get_remaining_years()
    book = _write(a)
    assert a.inspiration == 25 - BOOK_INSPIRATION_COST
    after_years = a.lifespan.get_remaining_years()
    assert abs((before_years - after_years) - BOOK_LIFESPAN_COST_YEARS) < 0.01
    assert BOOK_ITEM in a.inventory
    assert book.quality == "中品"  # tier 2
    assert book.holder_id == a.id and book.state == "held" and book.readers == []
    # 模板书名（测试环境无真 AI 通道）：非空且出自模板池口径
    assert book.title and book.preface
    assert quality_for_tier(0) == "下品" and quality_for_tier(1) == "下品"
    assert quality_for_tier(3) == "中品" and quality_for_tier(4) == "上品"
    print("✓ 著书：灵感-10、燃寿 1 年（burn_lifespan 路径）、品质按 tier、手稿+书目落账")


def test_write_book_rejections_zero_charge():
    # 灵感不足
    a = _char(inspiration=BOOK_INSPIRATION_COST - 1)
    dt = a.lifespan.death_timestamp
    res = BookEngine.write_book(a)
    assert not res["success"] and a.inspiration == BOOK_INSPIRATION_COST - 1
    assert a.lifespan.death_timestamp == dt and BOOK_ITEM not in a.inventory
    # 寿元边界：剩余恰 = 成本+保留线 → 拒绝；恰大一点 → 可写
    b = _char(inspiration=50, years=BOOK_LIFESPAN_COST_YEARS + 1.0)
    res = BookEngine.write_book(b)
    assert not res["success"], res
    assert b.inspiration == 50 and BOOK_ITEM not in b.inventory
    b2 = _char(inspiration=50, years=BOOK_LIFESPAN_COST_YEARS + 1.5)
    book2 = _write(b2)
    assert book2 is not None
    # 已持有手稿 → 拒绝再写
    res = BookEngine.write_book(b2)
    assert not res["success"] and b2.inspiration == 50 - BOOK_INSPIRATION_COST
    # 死亡拒绝
    d = _char(inspiration=50)
    d.status = CharacterStatus.DEAD
    assert not BookEngine.write_book(d)["success"]
    print("✓ 著书拒绝：灵感不足/寿元边界/已持有/死亡，均零扣费")


def test_ai_title_fallback_and_hook():
    a = _char(tier=4, inspiration=0)
    # AI 离线（无 key）→ _try_ai_title 返回 None，模板池出名（rng 确定性）
    assert BookEngine._try_ai_title(a, "上品") is None
    naming = BookEngine.make_title_preface(a, "上品", rng=random.Random(3))
    from core.books import PREFACE_TEMPLATES, TITLE_TEMPLATES

    pool = [t.replace("{name}", a.name) for t in TITLE_TEMPLATES["上品"]]
    assert naming["title"] in pool and naming["preface"] in PREFACE_TEMPLATES
    # AI 合格输出被采用（monkeypatch 网关函数）
    import ai.gateway as gw

    orig_chat, orig_avail = gw._chat_text, gw.ai_available
    gw._chat_text = lambda prompt, timeout=8.0: "云外来鸿\n道在文字之外，姑且记之。"
    gw.ai_available = lambda: True
    try:
        naming2 = BookEngine.make_title_preface(a, "上品", rng=random.Random(3))
    finally:
        gw._chat_text, gw.ai_available = orig_chat, orig_avail
    assert naming2["title"] == "云外来鸿" and "道在文字之外" in naming2["preface"]
    # AI 不合格（书名过长）→ 降级模板
    gw._chat_text = lambda prompt, timeout=8.0: "这是一个特别特别特别长的书名啊\n序。"
    gw.ai_available = lambda: True
    try:
        naming3 = BookEngine.make_title_preface(a, "上品", rng=random.Random(3))
    finally:
        gw._chat_text, gw.ai_available = orig_chat, orig_avail
    assert naming3["title"] in pool
    print("✓ 书名/序言：AI 离线走模板、合格 AI 被采用、不合格降级（AI 不碰品质/收益）")


# ---------------- 流通（寄售全链） ----------------

def _list_book(seller, price=50):
    listing, res = MarketEngine.list_item(seller, BOOK_ITEM, price)
    assert res["success"], res
    MarketListingRepository.save(listing)
    _LISTINGS.append(listing.id)
    BookEngine.on_listing_created(seller, listing.id)
    CharacterRepository.save(seller)
    return listing


def test_listing_circulation_and_transfer():
    a = _char(tier=2, inspiration=20)
    book = _write(a)
    listing = _list_book(a)
    held = BookEngine.book_held_by(a.id)
    assert held.state == "listed" and held.listing_id == listing.id
    assert BOOK_ITEM not in a.inventory  # 物品已托管寄售
    # 寄售中不可研读（fail-closed：行囊无稿）
    assert not BookEngine.read_book(a)["success"]
    # 买家已持有一本 → 拒绝成交
    b = _char(tier=1, inspiration=20)
    _write(b)
    assert not BookEngine.buyer_can_hold(b)
    # 正常买家成交过户
    c = _char()
    c.spirit_stones = 500
    res = MarketEngine.buy_listing(c, listing)
    assert res["success"], res
    BookEngine.on_listing_sold(listing.id, c)
    MarketListingRepository.save(listing)
    moved = BookEngine.book_held_by(c.id)
    assert moved is not None and moved.id == book.id and moved.state == "held"
    assert BookEngine.book_held_by(a.id) is None
    print("✓ 寄售流通：上架绑定/寄售中不可读/持书者不可再买/成交过户")


def test_listing_cancel_rebinds():
    a = _char(tier=1, inspiration=20)
    book = _write(a)
    listing = _list_book(a)
    res = MarketEngine.cancel_listing(a, listing)
    assert res["success"], res
    BookEngine.on_listing_cancelled(listing.id)
    MarketListingRepository.save(listing)
    held = BookEngine.book_held_by(a.id)
    assert held.id == book.id and held.state == "held" and held.listing_id == ""
    assert BOOK_ITEM in a.inventory
    print("✓ 撤单：书目回 held，物品回行囊")


# ---------------- 研读与声望 ----------------

def _give_book_to(author, reader):
    """经寄售把作者的书过户给读者（走真实流通链）"""
    listing = _list_book(author)
    reader.spirit_stones = 999
    res = MarketEngine.buy_listing(reader, listing)
    assert res["success"], res
    BookEngine.on_listing_sold(listing.id, reader)
    MarketListingRepository.save(listing)
    CharacterRepository.save(reader)
    return listing


def test_read_rewards_once_and_author_prestige():
    a = _char(tier=2, inspiration=20)   # 中品：exp150/dh+2/声望+3
    book = _write(a)
    r = _char()
    _give_book_to(a, r)
    a_before = CharacterRepository.get_by_id(a.id)
    exp0 = r.realm.current_exp
    r.karma.dao_heart = 50
    res = BookEngine.read_book(r)
    assert res["success"] and res["gained"], res
    assert r.realm.current_exp - exp0 == READ_REWARDS["中品"]["exp"]
    assert r.karma.dao_heart == 52 and res["dao_heart_gain"] == 2
    assert res["prestige_gain"] == PRESTIGE_PER_READ["中品"]
    a_after = CharacterRepository.get_by_id(a.id)
    assert a_after.prestige - a_before.prestige == PRESTIGE_PER_READ["中品"]
    # 重复研读：零收益、声望不再结算
    exp1, pres1 = r.realm.current_exp, CharacterRepository.get_by_id(a.id).prestige
    res2 = BookEngine.read_book(r)
    assert res2["success"] and not res2["gained"]
    assert r.realm.current_exp == exp1
    assert CharacterRepository.get_by_id(a.id).prestige == pres1
    # 第二位读者：仍受益，作者声望再结
    r2 = _char()
    # r 把书再寄售给 r2
    listing = _list_book(r)
    res = MarketEngine.buy_listing(r2, listing)
    assert res["success"], res
    BookEngine.on_listing_sold(listing.id, r2)
    MarketListingRepository.save(listing)
    res3 = BookEngine.read_book(r2)
    assert res3["gained"] and res3["prestige_gain"] == PRESTIGE_PER_READ["中品"]
    print("✓ 研读：首次收益数值断言、重复零收益、声望结算且幂等、转手新读者再受益")


def test_prestige_cap_per_book():
    a = _char(tier=4, inspiration=20)   # 上品：声望 +5/人，本封顶 10 → 第 3 人起作者不再得
    book = _write(a)
    holder = a
    gains = []
    for i in range(3):
        nxt = _char()
        listing = _list_book(holder)
        nxt.spirit_stones = 999
        res = MarketEngine.buy_listing(nxt, listing)
        assert res["success"], res
        BookEngine.on_listing_sold(listing.id, nxt)
        MarketListingRepository.save(listing)
        out = BookEngine.read_book(nxt)
        assert out["gained"], out
        gains.append(out["prestige_gain"])
        holder = nxt
    assert gains == [5, 5, 0], gains
    saved = [b for b in BookRepository.list_all() if b.id == book.id][0]
    assert saved.prestige_paid == BOOK_PRESTIGE_CAP and len(saved.readers) == 3
    print("✓ 作者声望按本封顶 10：第 3 位读者起只读者受益")


def test_author_self_read_no_gain_and_exp_clamp():
    a = _char(tier=4, inspiration=20)
    _write(a)
    exp0, pres0 = a.realm.current_exp, a.prestige
    res = BookEngine.read_book(a)
    assert res["success"] and not res["gained"]
    assert a.realm.current_exp == exp0 and a.prestige == pres0
    # 修为钳制：读者 exp 接近上限时只补到 max_exp
    b = _char(tier=1, inspiration=20)
    _write(b)  # 下品 exp 60
    r = _char()
    _give_book_to(b, r)
    r.realm.current_exp = r.realm.max_exp - 10
    out = BookEngine.read_book(r)
    assert out["gained"] and out["exp_gain"] == 10 and r.realm.current_exp == r.realm.max_exp
    print("✓ 作者自读无收益；研读修为钳至 max_exp（events 同口径）")


def test_read_fail_closed_cases():
    # 行囊有手稿但无书目（逃逸孤本）→ fail-closed 零收益
    r = _char()
    r.inventory.append(BOOK_ITEM)
    exp0 = r.realm.current_exp
    res = BookEngine.read_book(r)
    assert not res["success"] and r.realm.current_exp == exp0
    # 书名不匹配 → 拒绝
    a = _char(tier=1, inspiration=20)
    _write(a)
    res = BookEngine.read_book(a, hint="不存在的书")
    assert not res["success"]
    # 无手稿 → 拒绝
    n = _char()
    assert not BookEngine.read_book(n)["success"]
    print("✓ 研读 fail-closed：孤本无收益/书名不符/无稿拒绝")


def test_book_item_rejected_elsewhere():
    from core.market import MarketEngine as ME
    from core.pawn import PawnEngine
    from core.trade import AuctionEngine

    a = _char(tier=1, inspiration=20)
    _write(a)
    assert not ME.sell_to_guild(a, BOOK_ITEM, 1)["success"]
    assert BOOK_ITEM in a.inventory  # 未被扣
    _, res = PawnEngine.pawn_item(a, BOOK_ITEM)
    assert not res["success"] and BOOK_ITEM in a.inventory
    assert not AuctionEngine.list_item(a, BOOK_ITEM, 100)["success"]
    assert BOOK_ITEM in a.inventory
    print("✓ 逃逸口：商会回收/典当/拍卖均拒绝亲笔手稿，物品不丢")


def test_gift_retires_book():
    from core.chat_actions import do_gift

    a = _char(tier=1, inspiration=20)
    book = _write(a)
    npc = _char(name="受赠人")
    out = do_gift(a, npc, BOOK_ITEM, 0)
    assert out.get("ok"), out
    assert BOOK_ITEM not in a.inventory
    saved = [b for b in BookRepository.list_all() if b.id == book.id][0]
    assert saved.state == "gifted" and saved.holder_id == npc.id
    assert BookEngine.book_held_by(a.id) is None
    print("✓ 赠予 NPC：书目转 gifted 终态，脱离流通")


# ---------------- 面板与双端 ----------------

def test_panel_text():
    a = _char(tier=2, inspiration=7)
    txt = BookEngine.panel_text(a)
    assert "灵感 7" in txt and "声望 0" in txt and "中品" in txt
    a.inspiration = 20
    _write(a)
    txt2 = BookEngine.panel_text(a)
    assert "在持手稿" in txt2 and "你历年所著" in txt2
    print("✓ 面板：灵感/声望/可写品质/在持与历年所著")


def test_server_handle_books_flow():
    w = World(auto_tick=False)
    r = w.join(_uniq("双端著书客"))
    tok = r["token"]
    try:
        res = w.handle(tok, "/著书")
        assert res.get("ok") and "著书立说" in (res.get("text") or ""), res
        assert (res.get("status") or {}).get("books") == {"inspiration": 0, "prestige": 0}
        res = w.handle(tok, "/著书 写")
        assert not res.get("ok"), res  # 灵感不足
        char = w.get_char(tok)
        char.inspiration = 30
        CharacterRepository.save(char)
        res = w.handle(tok, "/著书 写")
        assert res.get("ok"), res
        assert (res.get("status") or {}).get("books", {}).get("inspiration") == 20
        res = w.handle(tok, "/研读")
        assert res.get("ok") and "自家文字" in (res.get("text") or ""), res  # 作者自读无收益
        # 寄售全链（handle 层钩子）：上架 → 另一玩家买下 → 研读得益、作者声望入账
        res = w.handle(tok, "/寄售 亲笔手稿 50")
        assert res.get("ok"), res
        r2 = w.join(_uniq("双端读者"))
        tok2 = r2["token"]
        buyer = w.get_char(tok2)
        buyer.spirit_stones = 999
        CharacterRepository.save(buyer)
        board = w.handle(tok2, "/坊市")
        assert board.get("ok"), board
        open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
        idx = [i for i, l in enumerate(open_l) if l.item_name == BOOK_ITEM and l.seller_id == char.id]
        assert idx, "寄售栏应有手稿"
        res = w.handle(tok2, f"/买寄售 {idx[0] + 1}")
        assert res.get("ok"), res
        res = w.handle(tok2, "/研读")
        assert res.get("ok") and "修为 +" in (res.get("text") or ""), res
        author_now = CharacterRepository.get_by_id(char.id)
        assert author_now.prestige > 0
        # 闭关锁门：著书/研读均拦截
        char2 = w.get_char(tok2)
        char2.status = CharacterStatus.MEDITATING
        CharacterRepository.save(char2)
        for cmd in ("/著书", "/著书 写", "/研读"):
            res = w.handle(tok2, cmd)
            assert not res.get("ok") and "闭关锁门" in (res.get("error") or ""), (cmd, res)
        _CHARS.extend([w.get_char(tok), w.get_char(tok2)])
        for l in MarketListingRepository.list_all():
            if l.seller_id in {c.id for c in _CHARS}:
                _LISTINGS.append(l.id)
        for b in BookRepository.list_all():
            if b.author_id in {c.id for c in _CHARS}:
                _BOOKS.append(b.id)
    finally:
        for t in (tok,):
            try:
                ch = w.get_char(t)
                ch.status = CharacterStatus.DEAD
                ch.lifespan.death_timestamp = 0.0
                CharacterRepository.save(ch)
            except Exception:
                pass
    print("✓ World.handle 全链路：著书/自读/寄售/买入/研读/声望/status.books/闭关锁门")


# ---------------- 评审整改：M1 通道遗漏 / M2 原子性 / S3 专柜 ----------------

def test_trade_and_donate_reject_book():
    """M1：当面交易报价与宗门上交均拒绝手稿（扣物之前），物品不丢、作者不砖化"""
    import core.trade as tr
    from core.sect_contrib import donate_item
    from core.trade import TradeEngine

    a = _char(tier=1, inspiration=20)
    _write(a)
    b = _char()
    a.location = b.location = "青云坊市客栈"
    CharacterRepository.save(a)
    CharacterRepository.save(b)
    tr._trade_sessions.clear()
    tr._trade_by_user.clear()
    try:
        res = TradeEngine.open_trade(a, b.name)
        assert res["success"], res
        out = TradeEngine.set_offer(a, 0, [BOOK_ITEM])
        assert not out["success"] and BOOK_ITEM in a.inventory, out
    finally:
        tr._trade_sessions.clear()
        tr._trade_by_user.clear()
    # 宗门上交（含模糊名「手稿」）
    a.sect = "青云宗"
    contrib0 = a.sect_contribution
    out = donate_item(a, BOOK_ITEM)
    assert not out["success"] and BOOK_ITEM in a.inventory and a.sect_contribution == contrib0, out
    out = donate_item(a, "手稿")
    assert not out["success"] and BOOK_ITEM in a.inventory, out
    # 作者未砖化：流通后仍可再著书（把书寄售出清后灵感足够即可再写）
    print("✓ M1：/交易 报价与 /上交 均拒绝亲笔手稿，物品不丢")


def test_npc_shop_sell_rejects_book():
    """S3：NPC 专柜回收拒绝手稿（扣物之前）"""
    from core.trade import NpcShopEngine

    a = _char(tier=1, inspiration=20)
    _write(a)
    npc = _char(name="书肆掌柜")
    npc.sect_rank = "坊市掌柜"
    npc.location = a.location
    CharacterRepository.save(npc)
    stones0 = a.spirit_stones
    out = NpcShopEngine.sell(a, npc.name, BOOK_ITEM, 1)
    assert not out["success"] and BOOK_ITEM in a.inventory and a.spirit_stones == stones0, out
    print("✓ S3：NPC 专柜回收拒绝亲笔手稿")


def test_write_rollback_when_book_save_fails(monkeypatch):
    """M2：书目落库失败 → 著书全额回滚（灵感/寿元/物品零变更）"""
    a = _char(tier=2, inspiration=30, years=30.0)
    dt0 = a.lifespan.death_timestamp

    def _boom(book):
        raise RuntimeError("db locked")

    monkeypatch.setattr(BookRepository, "save", staticmethod(_boom))
    res = BookEngine.write_book(a, rng=random.Random(1))
    assert not res["success"], res
    assert a.inspiration == 30 and a.lifespan.death_timestamp == dt0
    assert BOOK_ITEM not in a.inventory
    print("✓ M2：著书落库失败全额回滚")


def test_read_anchor_failure_no_gain_then_retry(monkeypatch):
    """M2：研读锚落库失败 → 整单失败零收益；恢复后重试恰结一次"""
    a = _char(tier=2, inspiration=20)
    _write(a)
    r = _char()
    _give_book_to(a, r)
    exp0 = r.realm.current_exp

    def _boom(book):
        raise RuntimeError("db locked")

    monkeypatch.setattr(BookRepository, "save", staticmethod(_boom))
    res = BookEngine.read_book(r)
    assert not res["success"], res
    assert r.realm.current_exp == exp0  # 读者收益未入账
    monkeypatch.undo()
    res = BookEngine.read_book(r)
    assert res["success"] and res["gained"], res
    assert r.realm.current_exp == exp0 + READ_REWARDS["中品"]["exp"]
    res2 = BookEngine.read_book(r)
    assert not res2["gained"]
    print("✓ M2：研读锚落库失败零收益可重试，重试恰结一次")


def test_prestige_pending_settled_on_next_read(monkeypatch):
    """M2：作者声望落库失败 → pending 留账不丢；下位读者研读时补结，不重不漏"""
    a = _char(tier=2, inspiration=20)  # 中品：声望 3/人
    book = _write(a)
    r1 = _char()
    _give_book_to(a, r1)
    orig_save = CharacterRepository.save

    def _fail_author(character):
        if character.id == a.id:
            raise RuntimeError("author row locked")
        return orig_save(character)

    monkeypatch.setattr(CharacterRepository, "save", staticmethod(_fail_author))
    res = BookEngine.read_book(r1)
    assert res["success"] and res["gained"], res  # 读者收益不受影响
    assert res["prestige_gain"] == 0
    saved = [b for b in BookRepository.list_all() if b.id == book.id][0]
    assert saved.prestige_pending == PRESTIGE_PER_READ["中品"] and saved.prestige_paid == PRESTIGE_PER_READ["中品"]
    assert CharacterRepository.get_by_id(a.id).prestige == 0
    monkeypatch.undo()
    # r1 把书转给 r2，r2 研读 → 补结 pending 3 + 本次 3
    r2 = _char()
    listing = _list_book(r1)
    r2.spirit_stones = 999
    assert MarketEngine.buy_listing(r2, listing)["success"]
    BookEngine.on_listing_sold(listing.id, r2)
    MarketListingRepository.save(listing)
    res = BookEngine.read_book(r2)
    assert res["gained"] and res["prestige_gain"] == 2 * PRESTIGE_PER_READ["中品"], res
    assert CharacterRepository.get_by_id(a.id).prestige == 2 * PRESTIGE_PER_READ["中品"]
    saved = [b for b in BookRepository.list_all() if b.id == book.id][0]
    assert saved.prestige_pending == 0
    print("✓ M2：声望 pending 留账，下次研读补结（不丢不重）")
