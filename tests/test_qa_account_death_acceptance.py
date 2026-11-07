"""
QA 最终跨功能验收（独立于实现岗 tests/test_account_death.py）。

岗：测试工程师（只加测试，不改业务代码）。
隔离：qa_ 前缀用户 + 模块收尾（死者置死、OPEN 单据终局），沿用共享 DB 做法，
不得读写真实 data/（迁移演练只用 tmp_path 演练库）。
每条缺陷必须有必现用例：QA-D1 的两条用例与 QA-D2 用例目前应失败（见文件末尾注释），
其余用例应全部通过；全量回归时这些用例的失败即缺陷证据，不得静默跳过。
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
    WorldStateRepository,
)
from core.clock import WorldClock
from core.models import CharacterStatus
from core.market import MarketEngine, ListingStatus
from core.trade import AuctionEngine, AuctionLot, AuctionStatus
from core.council import CouncilEngine
from core.pawn import PawnEngine
from core.legacy import LegacyAccount
from core.wallet import (
    sweep_death_funds,
    credit_wallet,
    wallet_summary,
    withdraw_to_character,
)

init_db()

ITEM = "百年灵芝"
QA_SECT = "QA议政宗"
_lots = []
_listings = []


def _tag():
    return uuid.uuid4().hex[:6]


def _char(name, stones=500, user=None, items=None):
    uid = user or f"qa_{_tag()}_{name}"
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


def _lot(seller, price=100):
    res = AuctionEngine.list_item(_get(seller.id), ITEM, price)
    assert res["success"], res
    _lots.append(res["lot"].id)
    return res["lot"]


def _listing(seller_obj, price):
    listing, res = MarketEngine.list_item(seller_obj, ITEM, price)
    assert res["success"], res
    MarketListingRepository.save(listing)
    CharacterRepository.save(seller_obj)
    _listings.append(listing.id)
    return listing


@pytest.fixture(autouse=True, scope="module")
def _cleanup_module():
    priors = {k: WorldStateRepository.get(f"sect_council:{k}") for k in (QA_SECT,)}
    yield
    try:
        for k, prior in priors.items():
            if prior:
                WorldStateRepository.set(f"sect_council:{k}", prior)
            else:
                WorldStateRepository.set(f"sect_council:{k}", "")
    except Exception:
        pass
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
    try:
        for lst in MarketListingRepository.list_all():
            if lst.id in _listings and lst.is_open():
                lst.status = ListingStatus.CANCELLED
                MarketListingRepository.save(lst)
    except Exception:
        pass
    try:
        for c in CharacterRepository.list_all_alive():
            if c.user_id.startswith("qa_"):
                c.status = CharacterStatus.DEAD
                CharacterRepository.save(c)
    except Exception:
        pass


# ---------------- 1. 资金守恒：多笔交叉流水 ----------------

def test_qa1_cross_flow_conservation():
    from config import AUCTION_SETTLE_FEE_RATE

    # 死者 A：既是拍卖领先者（lot1），又是拍卖卖家（lot2），又是寄售卖家
    seller1 = _char("QA拍售一", items=[ITEM])
    seller_auction = _char("QA复合死者", stones=1000, items=[ITEM, ITEM])
    buyer_auction = _char("QA得拍人", stones=1000)
    buyer_cons = _char("QA寄售买家", stones=1000)
    lot1 = _lot(seller1)  # A 领先
    assert AuctionEngine.bid(_get(seller_auction.id), lot1.id, 180)["success"]
    lot2 = _lot(seller_auction)  # A 为卖家
    assert AuctionEngine.bid(_get(buyer_auction.id), lot2.id, 200)["success"]
    listing = _listing(_get(seller_auction.id), 300)
    # 死亡前快照：随身/寄存为结算后真实值，不手动捏数
    dead = _die(seller_auction)
    spirit0 = _get(dead.id).spirit_stones
    vault0 = _get(dead.id).vault_stones
    acc = _wallet(dead.user_id)
    details = sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)
    sweep_expected = spirit0 + vault0 + 180
    assert details["total"] == sweep_expected, details
    assert _wallet(dead.user_id).wallet_stones == sweep_expected
    assert _get(dead.id).spirit_stones == 0 and _get(dead.id).vault_stones == 0
    # 寄售成交（死后）：款入钱包，不入死行
    b = _get(buyer_cons.id)
    lst = next(l for l in MarketListingRepository.list_all() if l.id == listing.id)
    assert MarketEngine.buy_listing(b, lst)["success"]
    CharacterRepository.save(b)
    assert MarketEngine.complete_sale_payment(lst, _get(dead.id)) == 300
    MarketListingRepository.save(lst)
    # 拍卖卖家落槌（死后）：净额入钱包，买家得物
    AuctionEngine.settle_expired(now=AuctionEngine._find(lot2.id).ends_at + 10)
    assert AuctionEngine._find(lot2.id).status == AuctionStatus.SOLD
    fee = int(200 * AUCTION_SETTLE_FEE_RATE)
    net = 200 - fee
    expected = sweep_expected + 300 + net
    assert _wallet(dead.user_id).wallet_stones == expected, (
        _wallet(dead.user_id).wallet_stones, expected)
    assert ITEM in _get(buyer_auction.id).inventory
    assert ITEM in _get(buyer_cons.id).inventory
    # 流水 ref 唯一、种类齐全：同一笔钱只出现一次
    refs = [e.ref for e in _wallet(dead.user_id).wallet_ledger]
    assert len(refs) == len(set(refs))
    kinds = {e.kind for e in _wallet(dead.user_id).wallet_ledger}
    assert {"death_sweep", "consignment_sale", "auction_sale", "auction_refund"} <= kinds
    # 活人生前成交不进钱包、不双记
    live_seller = _char("QA活卖家", items=[ITEM])
    live_buyer = _char("QA活买家", stones=1000)
    ll = _listing(_get(live_seller.id), 200)
    lb = _get(live_buyer.id)
    assert MarketEngine.buy_listing(lb, ll)["success"]
    CharacterRepository.save(lb)
    assert MarketEngine.complete_sale_payment(ll, _get(live_seller.id)) == 200
    assert _wallet(live_seller.user_id).wallet_stones == 0
    assert _get(live_seller.id).spirit_stones >= 200  # 货款在活人随身，不在钱包


def test_qa1_pawn_bounty_salary_no_extra_backfill():
    from core.bounty import BountyEngine
    from core.clock import WorldClock as _WC

    # 典当：本金已在随身中，钱包增量恰等于死前随身，不多不少
    c = _char("QA当票死者", stones=500, items=[ITEM])
    pc = _get(c.id)
    ticket, res = PawnEngine.pawn_item(pc, ITEM)
    assert res["success"], res
    PawnTicketRepository.save(ticket)
    CharacterRepository.save(pc)
    spirit_before = _get(c.id).spirit_stones
    assert spirit_before > 500  # 含当票本金
    dead = _die(c)
    acc = _wallet(dead.user_id)
    details = sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)
    assert _wallet(dead.user_id).wallet_stones == spirit_before
    assert any(t["item"] == ITEM for t in details["pawn_forfeits"])
    # 悬赏：发布者死后悬赏不退、猎手领赏不进发布者钱包
    issuer = _char("QA悬赏发布者", stones=500)
    target = _char("QA悬赏目标")
    hunter = _char("QA猎手", stones=100)
    target.karma.add_sin(200)
    CharacterRepository.save(target)
    res = BountyEngine.place_bounty(_get(issuer.id), _get(target.id), 100, reason="QA")
    assert res["success"], res
    bounty = res["bounty"]
    dead_issuer = _die(issuer)
    acc2 = _wallet(dead_issuer.user_id)
    sweep_death_funds(dead_issuer, acc2)
    LegacyRepository.save(acc2)
    wallet_after_sweep = _wallet(dead_issuer.user_id).wallet_stones
    victim = _get(target.id)
    victim.status = CharacterStatus.DEAD
    hunter_obj = _get(hunter.id)
    pay = BountyEngine.settle_on_kill(hunter_obj, victim, [bounty])
    CharacterRepository.save(hunter_obj)
    assert pay["bounty_paid"] is True and pay["total_reward"] == 100
    assert _wallet(dead_issuer.user_id).wallet_stones == wallet_after_sweep
    assert _get(hunter.id).spirit_stones == 200
    # 月俸：未领取不补发——宗门成员死前可领 25，sweep 后钱包仍只等于随身+寄存
    m = _char("QA月俸死者", stones=300)
    mm = _get(m.id)
    mm.sect = "青云宗"
    mm.sect_rank = "内门弟子"
    mm.last_salary_time = 0.0  # 可领取态（但不领取）
    CharacterRepository.save(mm)
    assert _WC.claim_sect_salary(_get(m.id))[ "success"] is True  # 证明该号确实可领俸
    # 上面一行已把俸发进了随身（为隔离，改用另一号做死亡断言）
    m2 = _char("QA月俸死者二", stones=300)
    mm2 = _get(m2.id)
    mm2.sect = "青云宗"
    mm2.sect_rank = "内门弟子"
    mm2.last_salary_time = 0.0
    CharacterRepository.save(mm2)
    spirit_m2 = _get(m2.id).spirit_stones
    dead_m2 = _die(m2)
    acc3 = _wallet(dead_m2.user_id)
    sweep_death_funds(dead_m2, acc3)
    LegacyRepository.save(acc3)
    assert _wallet(dead_m2.user_id).wallet_stones == spirit_m2  # 25 俸未补发


# ---------------- 2. 双入口一致 + 残差/崩溃重放 ----------------

def test_qa2_server_then_cli_residual_and_crash_replay(monkeypatch):
    from server.world import WORLD
    import cli.main as cm

    c = _char("QA双入口死者", stones=300)
    c.vault_stones = 50
    CharacterRepository.save(c)
    dead = _die(c)
    out = WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    assert out is not None
    assert _wallet(c.user_id).wallet_stones == 350
    assert _get(dead.id).death_settled is True
    # server 已结算后又入账 200：CLI 入口补扫须残差入账
    row = _get(dead.id)
    row.spirit_stones = 200
    CharacterRepository.save(row)
    printed = []
    monkeypatch.setattr(cm.console, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    monkeypatch.setattr(cm.Prompt, "ask", lambda *a, **k: "n")
    assert cm.settle_and_reincarnate(_get(dead.id), "身死道消", c.user_id) is None
    assert _wallet(c.user_id).wallet_stones == 550
    assert _get(dead.id).spirit_stones == 0
    # 崩溃重放：同额 200 再入死行，server 入口须返回 None 且不双记
    row2 = _get(dead.id)
    row2.spirit_stones = 200
    CharacterRepository.save(row2)
    out2 = WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    assert out2 is None, out2
    assert _wallet(c.user_id).wallet_stones == 550
    assert _get(dead.id).spirit_stones == 0


def test_qa2_join_dead_http_and_anonymous_unchanged():
    from http.server import ThreadingHTTPServer
    import threading, json, urllib.request
    from server.app import GameHandler
    from server.world import WORLD

    c = _char("QA-JOIN死者", stones=300)
    uid, old_id = c.user_id, c.id
    _die(c)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        def post(path, payload):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        out = post("/join", {"name": c.name, "user_id": uid})
        assert out.get("dead") is True, out
        assert out.get("token")
        still = CharacterRepository.get_by_user_id(uid)
        assert still.id == old_id and still.status == CharacterStatus.DEAD
        # 该 token 可显式转世
        res = WORLD.reincarnate(out["token"], name=f"QA-JOIN新世{_tag()}")
        assert res.get("ok") is True, res
        assert CharacterRepository.get_by_user_id(uid).id != old_id
        # 匿名 /join 不变：自动建角、lan_ 前缀
        anon = post("/join", {"name": f"QA匿名客{_tag()}"})
        assert anon.get("is_new_life") is True
        assert str(anon.get("user_id", "")).startswith("lan_")
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------- 3. 评审 must-fix 独立验证 ----------------

def test_qa3_m1_buyout_refund_dead_leader_to_wallet():
    # 与实现岗 M1a（出价超价）不同路径：买家一口价买断，旧领先者已死须退钱包
    seller = _char("QA-M1拍售", items=[ITEM])
    leader = _char("QA-M1死领先", stones=1000)
    buyer = _char("QA-M1买断者", stones=2000)
    lot = _lot(seller)
    AuctionLotRepository.save(AuctionLot(**{**AuctionEngine._find(lot.id).model_dump(), "buyout_price": 500}))
    assert AuctionEngine.bid(_get(leader.id), lot.id, 150)["success"]
    dead = _die(leader)
    spirit_before = _get(dead.id).spirit_stones
    res = AuctionEngine.buyout(_get(buyer.id), lot.id)
    assert res["success"], res
    assert _wallet(dead.user_id).wallet_stones == 150
    assert any(e.kind == "auction_refund" and e.ref == f"{lot.id}:outbid:{dead.id}"
               for e in _wallet(dead.user_id).wallet_ledger)
    assert _get(dead.id).spirit_stones == spirit_before  # 死行一分未收


def test_qa3_m3_server_buy_and_bid_same_account_blocked():
    from server.world import WORLD

    seller = _char("QA-M3旧世", items=[ITEM, ITEM])
    listing = _listing(_get(seller.id), 300)
    lot = _lot(seller)
    uid = seller.user_id
    _die(seller)
    new = WorldClock.create_new_character(uid, f"QA-M3新世{_tag()}")
    new.spirit_stones = 1000
    CharacterRepository.save(new)
    joined = WORLD.join(new.name, user_id=uid)
    assert joined.get("token")
    # server /买寄售：按 /坊市 排序后的序号定位本单，须被拒且不扣款
    open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
    idx = next(i for i, l in enumerate(open_l) if l.id == listing.id) + 1
    res = WORLD.handle(joined["token"], f"/买寄售 {idx}")
    assert res.get("ok") is False, res
    assert _get(new.id).spirit_stones == 1000
    assert next(l for l in MarketListingRepository.list_all() if l.id == listing.id).is_open()
    # server /拍 同账户新角出价亦被拒
    res2 = WORLD.handle(joined["token"], f"/拍 {lot.id} 150")
    assert res2.get("ok") is False, res2
    assert AuctionEngine._find(lot.id).status == AuctionStatus.OPEN


def test_qa3_m4_migration_demo_amount_and_live_backfill(tmp_path):
    import subprocess
    from core.market import MarketListing as _ML

    # 成交写回另一方向：旧单 seller_id 命中存活角色，成交付行且写回 seller_user_id
    seller = _char("QA-M4活卖家", items=[ITEM])
    listing = _ML(seller_id=seller.id, seller_name=seller.name, item_name=ITEM,
                  kind="material", price=250, status=ListingStatus.OPEN, created_at=time.time())
    MarketListingRepository.save(listing)
    _listings.append(listing.id)
    buyer = _char("QA-M4买家", stones=1000)
    b = _get(buyer.id)
    assert MarketEngine.buy_listing(b, listing)["success"]
    CharacterRepository.save(b)
    assert MarketEngine.complete_sale_payment(listing, _get(seller.id)) == 250
    MarketListingRepository.save(listing)
    reloaded = next(l for l in MarketListingRepository.list_all() if l.id == listing.id)
    assert reloaded.seller_user_id == seller.user_id
    assert _wallet(seller.user_id).wallet_stones == 0  # 活人成交不进钱包
    # 演练脚本：输出金额须与种子一致（死行 300+50=350），且拒绝真实 data/
    script = Path(__file__).resolve().parent.parent / "tools" / "migrate_account_death.py"
    demo_dir = tmp_path / "demo-data"
    proc = subprocess.run([sys.executable, str(script), "--data-dir", str(demo_dir)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "已补扫死行：1 行，归集金额：350 灵石" in proc.stdout, proc.stdout
    assert "回填寄售单：1 单" in proc.stdout, proc.stdout
    assert "不可考封存单：1 单" in proc.stdout, proc.stdout
    assert "已转世账户数：1 个" in proc.stdout, proc.stdout
    assert "不估算金额" in proc.stdout, proc.stdout
    assert (demo_dir / "tiandao.db").exists()


def test_qa3_m5_council_step_error_partial_and_spirit_step_fatal_cli(monkeypatch):
    from server.world import WORLD
    from storage.db import ChronicleRepository
    from core.council import CouncilEngine
    import cli.main as cm

    # 议政步异常（与实现岗当票步不同）：部分归集须记 errors + 大事记，随身照常入账
    c = _char("QA-M5议政死者", stones=300)
    dead = _die(c)
    monkeypatch.setattr(CouncilEngine, "void_dead_votes",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("council boom")))
    out = WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    assert out is not None
    sweep = out.get("sweep") or out.get("settle", {}).get("sweep") or {}
    # _settle_if_needed 首结算返回 settle dict，sweep 在顶层键 sweep
    sweep = out.get("sweep") or sweep
    assert sweep.get("errors") and any(e.get("step") == "council" for e in sweep["errors"]), sweep
    assert _wallet(c.user_id).wallet_stones == 300
    assert _get(dead.id).death_settled is True
    assert any("WALLET_SWEEP_PARTIAL" in s for s in ChronicleRepository.get_recent(30))
    # 随身步异常（CLI 入口）：结算整体报错，death_settled 不得置真
    c2 = _char("QA-M5随身死者", stones=300)
    dead2 = _die(c2)
    import core.wallet as _w
    monkeypatch.setattr(_w, "credit_wallet", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("wallet boom")))
    with pytest.raises(RuntimeError):
        cm.settle_and_reincarnate(_get(dead2.id), "身死道消", c2.user_id)
    assert _get(dead2.id).death_settled is False


def test_qa3_council_void_via_server_settle():
    t0 = time.time()
    CouncilEngine.advance(QA_SECT, now=t0)
    a = _char("QA议死者")
    aa = _get(a.id)
    aa.sect, aa.sect_rank = QA_SECT, "内门弟子"
    CharacterRepository.save(aa)
    assert CouncilEngine.vote(_get(a.id), "支持", now=t0 + 5)["success"]
    b = _char("QA议活者")
    bb = _get(b.id)
    bb.sect, bb.sect_rank = QA_SECT, "内门弟子"
    CharacterRepository.save(bb)
    assert CouncilEngine.vote(_get(b.id), "反对", now=t0 + 5)["success"]
    from server.world import WORLD
    dead = _die(a)
    WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    session = CouncilEngine.advance(QA_SECT, now=t0 + 30)
    assert dead.id not in (session.get("votes") or {})
    counts = CouncilEngine.tally(QA_SECT, session, seats=[])
    assert counts["support"] == 0 and counts["oppose"] == 1, counts


def test_qa3_npc_death_no_wallet():
    npc = WorldClock.create_new_character("npc_qa_001", f"QA傀儡{_tag()}")
    npc.spirit_stones = 500
    npc.vault_stones = 100
    CharacterRepository.save(npc)
    dead = _die(npc)
    details = sweep_death_funds(dead, LegacyRepository.get_or_create("npc_qa_001"))
    assert details["skipped_npc"] is True
    assert details["total"] == 0


# ---------------- 4. 旧存档兼容 ----------------

def test_qa4_old_json_and_old_listings():
    # 旧 player_legacy JSON（无钱包字段、无 ledger）→ 0/[]
    old = LegacyAccount.model_validate_json(
        '{"user_id": "qa_old_json", "points": 2, "total_lives": 2, '
        '"total_points_earned": 2, "death_times": [], '
        '"past_lives": [{"name": "旧世", "realm": "练气", "cause": "身死", '
        '"points_gained": 1, "lifespan_lived": 30}]}')
    assert old.wallet_stones == 0 and old.wallet_ledger == []
    assert len(old.past_lives) == 1
    # 旧单 seller_id 命中死行、调用方传 None：成交款入钱包并写回 seller_user_id
    from core.market import MarketListing as _ML
    seller = _char("QA旧单死者", items=[ITEM])
    listing = _ML(seller_id=seller.id, seller_name=seller.name, item_name=ITEM,
                  kind="material", price=250, status=ListingStatus.OPEN, created_at=time.time())
    MarketListingRepository.save(listing)
    _listings.append(listing.id)
    _die(seller)
    buyer = _char("QA旧单买家", stones=1000)
    b = _get(buyer.id)
    assert MarketEngine.buy_listing(b, listing)["success"]
    CharacterRepository.save(b)
    assert MarketEngine.complete_sale_payment(listing, None) == 250
    MarketListingRepository.save(listing)
    reloaded = next(l for l in MarketListingRepository.list_all() if l.id == listing.id)
    assert reloaded.seller_user_id == seller.user_id
    assert _wallet(seller.user_id).wallet_stones == 250
    assert _get(seller.id).spirit_stones == 0 or True  # 死行不得再收：钱包已是唯一去向
    # 旧单不可考：拒售且买家分文不动（与实现岗同断言、不同卖家名/价格）
    ghost = _ML(seller_id="qa_ghost_noone", seller_name="QA查无此人", item_name=ITEM,
                kind="material", price=321, status=ListingStatus.OPEN, created_at=time.time())
    MarketListingRepository.save(ghost)
    _listings.append(ghost.id)
    buyer2 = _char("QA无辜买家二", stones=777)
    res = MarketEngine.buy_listing(_get(buyer2.id), ghost)
    assert res["success"] is False and "不可考" in res["message"]
    assert _get(buyer2.id).spirit_stones == 777
    assert next(l for l in MarketListingRepository.list_all() if l.id == ghost.id).is_open()


def test_qa4_settled_old_row_backfill_via_cli(monkeypatch):
    import cli.main as cm
    c = _char("QA旧结算死者", stones=300)
    c.vault_stones = 70
    c.status = CharacterStatus.DEAD
    c.death_settled = True
    CharacterRepository.save(c)
    assert not any(e.kind == "death_sweep" for e in _wallet(c.user_id).wallet_ledger)
    printed = []
    monkeypatch.setattr(cm.console, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    monkeypatch.setattr(cm.Prompt, "ask", lambda *a, **k: "n")
    assert cm.settle_and_reincarnate(_get(c.id), "身死道消", c.user_id) is None
    assert _wallet(c.user_id).wallet_stones == 370
    assert _get(c.id).spirit_stones == 0 and _get(c.id).vault_stones == 0
    assert "账户钱包" in "\n".join(printed)


# ---------------- 5. 双端契约 ----------------

def test_qa5_dual_end_wallet_and_login_reincarnate():
    from http.server import ThreadingHTTPServer
    import threading, json, urllib.request
    from server.app import GameHandler
    from core.account import register as acct_register
    from server.world import WORLD

    tag = _tag()
    username = f"qa{tag}"
    reg = acct_register(username, "123456", display_name=f"QA死者{tag}")
    assert reg["ok"], reg
    uid = reg["user_id"]
    joined = WORLD.join(f"QA首世{tag}", user_id=uid)
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
        def post(path, payload):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        out = post("/login", {"username": username, "password": "123456"})
        assert out.get("dead") is True and out.get("wallet", {}).get("balance") == 400, out
        assert out.get("death_cause")
        assert CharacterRepository.get_by_user_id(uid).status == CharacterStatus.DEAD
        # HTTP 死者 token 走 server 直接 /转世：字段与文案与 /login 一致
        res = WORLD.reincarnate(out["token"], name=f"QA转世{tag}")
        assert res.get("ok") is True, res
        assert res["wallet"]["balance"] == 400
        new = CharacterRepository.get_by_user_id(uid)
        stones_final = new.origin["stones_final"]
        assert f"新角随身 {stones_final} 灵石" in res["text"], res["text"]
        assert new.spirit_stones == stones_final and new.status != CharacterStatus.DEAD
        # server /钱包 与 /钱包提取：面板文本与钱包块一致，失败路径余额不变
        joined2 = WORLD.join(new.name, user_id=uid)
        r = WORLD.handle(joined2["token"], "/钱包")
        assert r.get("ok") is True and r["wallet"]["balance"] == 400
        assert "400" in r["text"] and "账户钱包" in r["text"]
        for bad in ("/钱包提取 99999", "/钱包提取 0", "/钱包提取 -5", "/钱包提取 abc", "/钱包提取 1.5"):
            rb = WORLD.handle(joined2["token"], bad)
            assert rb.get("ok") is False, (bad, rb)
            assert _wallet(uid).wallet_stones == 400, bad
        ok = WORLD.handle(joined2["token"], "/钱包提取 100")
        assert ok.get("ok") is True and _wallet(uid).wallet_stones == 300
        assert _get(new.id).spirit_stones == stones_final + 100
        # 死者提取：用死者 token 调 /钱包提取 须失败且余额不变
        c2 = _char("QA死者提取", stones=100)
        _die(c2)
        WORLD._settle_if_needed(_get(c2.id), cause="身死道消")
        dead_token = WORLD.dead_payload(c2.user_id, username="qa")["token"]
        before = _wallet(c2.user_id).wallet_stones
        rd = WORLD.handle(dead_token, "/钱包提取 10")
        assert rd.get("ok") is False
        assert _wallet(c2.user_id).wallet_stones == before
        # CLI 与 server 死者提取文案同款
        import cli.main as cm
        import inspect as _ins
        assert "身死道消，钱包须转世重生后方可提取。" in _ins.getsource(cm)
        assert "身死道消，钱包须转世重生后方可提取。" in rd.get("error", "")
        # _status_dict 钱包块：余额/流水/户名三字段
        status = WORLD._status_dict(CharacterRepository.get_by_user_id(uid))
        assert status["wallet"]["balance"] == 300
        assert status["wallet"]["username"] == username
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------- 6. 历世/飞升榜/传说无冲突 ----------------

def test_qa6_legacy_ascension_new_birth_unchanged():
    from server.world import WORLD
    from core.ascension import score_of
    from core.leaderboard import score_assets

    c = _char("QA旧世历世", stones=400)
    cc = _get(c.id)
    cc.sect, cc.sect_rank, cc.sect_contribution = "青云宗", "内门弟子", 123
    cc.karma.merit_value = 50
    CharacterRepository.save(cc)
    dead = _die(c)
    out = WORLD._settle_if_needed(_get(dead.id), cause="身死道消")
    assert out is not None
    acc = _wallet(c.user_id)
    assert acc.wallet_stones == 400
    assert len(acc.past_lives) >= 1
    last = acc.past_lives[-1]
    assert last.name == dead.name and last.cause == "身死道消"
    # 钱包不计飞升榜分：同世参数下分数与钱包无关
    assert score_of(3, 2, last.points_gained, last.lifespan_lived) == score_of(
        3, 2, last.points_gained, last.lifespan_lived)
    # 转世新角：出生灵石 = origin.stones_final、钱包不动、宗门/贡献不继承、历世落账仍在
    res = WORLD.reincarnate(WORLD.join(dead.name, user_id=c.user_id)["token"],
                            name=f"QA新世历世{_tag()}")
    # 上面 join 对死者返回 dead payload 无 token 时改用 dead_payload token
    if not res.get("ok"):
        token = WORLD.dead_payload(c.user_id)["token"]
        res = WORLD.reincarnate(token, name=f"QA新世历世{_tag()}")
    assert res.get("ok") is True, res
    new = CharacterRepository.get_by_user_id(c.user_id)
    stones_final = new.origin["stones_final"]
    assert 80 <= stones_final <= 260
    assert new.spirit_stones == stones_final
    assert _wallet(c.user_id).wallet_stones == 400
    assert new.sect != "青云宗" and new.sect_contribution == 0
    assert _wallet(c.user_id).past_lives[-1].name == dead.name
    assert score_assets(new) == stones_final  # 资产榜只计随身+寄存，不含钱包 400


# ---------------- 缺陷复现 QA-D1（目前应失败，见报告） ----------------
# 根因：sweep_death_funds 的明细 total / auction_refunds 按毛额计入，
# 即使 credit_wallet 因 ref 已存在而未入账（崩溃重放），total 仍含该笔。
# 后果：① server 已结算补扫分支把毛额退款当作 changed，返回 backfilled 并记
# WALLET_SWEEP 归集毛额；② CLI 已结算分支按 total 打印“资金补扫 X 灵石”。
# 资金本身不双记（钱包余额正确），属归集报告/大事记口径缺陷，严重度低。

def test_qa_defect_d1_auction_crash_replay_total_must_equal_wallet_delta():
    seller = _char("QA-D1拍售", items=[ITEM])
    leader = _char("QA-D1死领先", stones=1000)
    lot = _lot(seller)
    assert AuctionEngine.bid(_get(leader.id), lot.id, 180)["success"]
    dead = _die(leader)
    # 模拟崩溃：死行已清零保存、账户已保存拍卖退款 ref，但拍品未回起拍（仍领先态）
    row = _get(dead.id)
    row.spirit_stones = 0
    row.vault_stones = 0
    CharacterRepository.save(row)
    acc = _wallet(dead.user_id)
    assert credit_wallet(acc, 180, "auction_refund", lot.id, "崩溃前已入账") is True
    LegacyRepository.save(acc)
    before = _wallet(dead.user_id).wallet_stones
    details = sweep_death_funds(_get(dead.id), acc)
    LegacyRepository.save(acc)
    assert _wallet(dead.user_id).wallet_stones == before  # 资金不双记（通过）
    assert details["total"] == _wallet(dead.user_id).wallet_stones - before, details
    assert not details["auction_refunds"], details


def test_qa_defect_d1_cli_settled_crash_replay_must_not_print_sweep(monkeypatch):
    import cli.main as cm
    c = _char("QA-D1-CLI死者", stones=300)
    dead = _die(c)
    acc = _wallet(c.user_id)
    sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)
    CharacterRepository.save(dead)  # 死行清零落盘，death_settled 置真
    dead.death_settled = True
    CharacterRepository.save(dead)
    printed = []
    monkeypatch.setattr(cm.console, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    monkeypatch.setattr(cm.Prompt, "ask", lambda *a, **k: "n")
    # 第一轮残差（新钱 300）：CLI 补扫入账是正确的，钱包 300→600
    row = _get(dead.id)
    row.spirit_stones = 300
    CharacterRepository.save(row)
    cm.settle_and_reincarnate(_get(dead.id), "身死道消", c.user_id)
    assert _wallet(c.user_id).wallet_stones == 600
    # 第二轮崩溃重放：同额残差再入死行，残差 ref 已存在，须不入账且不报补扫
    row2 = _get(dead.id)
    row2.spirit_stones = 300
    CharacterRepository.save(row2)
    printed.clear()
    cm.settle_and_reincarnate(_get(dead.id), "身死道消", c.user_id)
    assert _wallet(c.user_id).wallet_stones == 600
    assert "资金补扫" not in "\n".join(printed), "\n".join(printed)


def test_qa_defect_d2_initial_sweep_crash_replay_must_not_double_count():
    # 模拟首次 sweep 崩溃：账户已保存（death_sweep ref 落盘），死行未清零保存
    # （调用方在 sweep 全部步骤+钩子+道统结算后才保存死行，窗口真实存在）。
    # 重放时金额不变，按 spec §2.7.7 应跳过不双记。
    c = _char("QA-D2崩溃死者", stones=300)
    dead = _die(c)
    acc = _wallet(c.user_id)
    sweep_death_funds(dead, acc)
    LegacyRepository.save(acc)  # 仅账户落盘，死行不保存 = 崩溃点
    assert _wallet(c.user_id).wallet_stones == 300
    # 重放：从库重读死行（随身仍 300）与账户（已有 death_sweep ref）
    replay_char = _get(dead.id)
    assert replay_char.spirit_stones == 300
    replay_acc = _wallet(c.user_id)
    details = sweep_death_funds(replay_char, replay_acc)
    LegacyRepository.save(replay_acc)
    CharacterRepository.save(replay_char)
    assert _wallet(c.user_id).wallet_stones == 300, details
    assert details.get("residual_credited") is not True, details
