"""
F05 拍卖专场：状态机（待开场/系统场次）· NPC 规则跟价 · 资金守恒 · 双端链路
Spec：docs/compose/spec/auction.md
CLI 侧说明：cli/main.py 是交互循环不可直接 handle 调用，CLI 对齐以源码动作表断言钉住，
实际流程与 server 共用同一 AuctionEngine（引擎用例即 CLI 的落账路径）。
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from storage.db import (
    init_db,
    CharacterRepository,
    AuctionLotRepository,
    WorldStateRepository,
)
from core.clock import WorldClock
from core.trade import AuctionEngine, AuctionLot, AuctionStatus
from core.models import CharacterStatus
import config


class _PickRng:
    """确定性 rng 桩：random()->0.0（必过概率门）；choice 优先挑指定 id 的候选"""

    def __init__(self, pick_id=None):
        self.pick_id = pick_id

    def random(self):
        return 0.0

    def choice(self, seq):
        if self.pick_id:
            for x in seq:
                if getattr(x, "id", None) == self.pick_id:
                    return x
        return seq[0]


def _char(name: str, stones: int = 500, npc: bool = False):
    uid = f"npc_auc_{name}" if npc else f"auc_{name}"
    c = WorldClock.create_new_character(uid, name)
    c.spirit_stones = stones
    c.location = "青云坊市客栈"
    c.born_at = time.time() - 80 * 3600.0  # 越过新手资产转移保护期（can_use_market）
    CharacterRepository.save(c)
    return c


def _stones(char_id: str) -> int:
    return CharacterRepository.get_by_id(char_id).spirit_stones


def _total(ids) -> int:
    return sum(_stones(i) for i in ids)


def _disable_system_seed():
    """把系统场次排期推到远未来，避免本文件其他用例被系统拍品干扰"""
    WorldStateRepository.set("auction_next_system_at", time.time() + 3650 * 86400)


def _clear_all_lots():
    """把库内全部未终局拍品推向终局（PENDING 撤场、OPEN 到期结算），隔离用例间残留"""
    now = time.time()
    for lot in AuctionLotRepository.list_all():
        if lot.status == AuctionStatus.PENDING:
            lot.status = AuctionStatus.CANCELLED
            AuctionLotRepository.save(lot)
        elif lot.status == AuctionStatus.OPEN:
            lot.ends_at = now - 1
            AuctionLotRepository.save(lot)
    AuctionEngine.settle_expired(now=now)


def test_system_lot_full_lifecycle():
    """系统场次：排期生成 PENDING → 未开场拒拍 → 晋升 OPEN → 玩家竞价 → 成交全额沉淀"""
    init_db()
    _clear_all_lots()
    now = time.time()
    seq = int(WorldStateRepository.get("auction_system_seq", 0) or 0)
    expect_item = config.AUCTION_SYSTEM_ITEMS[seq % len(config.AUCTION_SYSTEM_ITEMS)]
    WorldStateRepository.set("auction_next_system_at", now - 1)
    notes = AuctionEngine.advance(now=now, react=False)
    assert any("拍卖预告" in n for n in notes), notes
    pend = [l for l in AuctionLotRepository.list_all()
            if l.source == "system" and l.status == AuctionStatus.PENDING]
    assert len(pend) == 1, pend
    lot = pend[0]
    assert lot.item_name == expect_item and lot.seller_id == config.AUCTION_HOUSE_ID
    assert abs(lot.starts_at - (now + config.AUCTION_SYSTEM_LEAD_SECONDS)) < 2

    buyer = _char("系统场买家", stones=100000)
    # 待开场不可出价
    r = AuctionEngine.bid(buyer, lot.id, lot.start_price, now=now)
    assert r["success"] is False and "尚未开场" in r["message"], r
    assert _stones(buyer.id) == 100000

    # 晋升（重复 advance 幂等：只晋升一次，ends_at 不漂移）
    t_open = lot.starts_at + 1
    n1 = AuctionEngine.advance(now=t_open, react=False)
    assert any("开场" in n for n in n1), n1
    lot = AuctionEngine._find(lot.id)
    assert lot.status == AuctionStatus.OPEN
    assert abs(lot.ends_at - (lot.starts_at + config.AUCTION_DURATION_MIN * 60)) < 2
    ends_at = lot.ends_at
    AuctionEngine.advance(now=t_open + 1, react=False)
    assert AuctionEngine._find(lot.id).ends_at == ends_at

    # 看板呈现待开场/竞拍中两段（此处至少竞拍中含本件）
    board = AuctionEngine.board(now=t_open + 2, rng=_PickRng())
    assert "竞拍中" in board["message"] and lot.item_name in board["message"]

    # 玩家出价并到期成交：成交款全额沉淀 → 买家 Δ = -成交价，得物
    # （看板 react 可能已引来 NPC 跟价，须按库内新鲜状态算地板价）
    lot = AuctionEngine._find(lot.id)
    bid_amt = AuctionEngine.floor_price(lot)
    r = AuctionEngine.bid(buyer, lot.id, bid_amt, now=t_open + 3)
    assert r["success"] is True, r
    AuctionEngine.advance(now=lot.ends_at + 1, react=False)
    lot = AuctionEngine._find(lot.id)
    assert lot.status == AuctionStatus.SOLD
    buyer = CharacterRepository.get_by_id(buyer.id)
    assert lot.item_name in buyer.inventory
    assert buyer.spirit_stones == 100000 - bid_amt  # 全额沉淀，无卖家收款
    print("✓ 系统场次全生命周期：PENDING→OPEN→SOLD，成交款全额沉淀")


def test_system_lot_expire_vanishes():
    """系统拍品流拍：物品消散（不回任何人行囊），灵石零变动"""
    init_db()
    _clear_all_lots()
    now = time.time()
    WorldStateRepository.set("auction_next_system_at", now - 1)
    AuctionEngine.advance(now=now, react=False)
    pend = [l for l in AuctionLotRepository.list_all()
            if l.source == "system" and l.status == AuctionStatus.PENDING]
    assert pend, "应已生成系统拍品"
    lot = pend[0]
    watcher = _char("流拍旁观者", stones=777)
    AuctionEngine.advance(now=lot.starts_at + 1, react=False)
    lot = AuctionEngine._find(lot.id)
    assert lot.status == AuctionStatus.OPEN
    notes = AuctionEngine.advance(now=lot.ends_at + 1, react=False)
    assert any("流拍" in n and "收回" in n for n in notes), notes
    lot = AuctionEngine._find(lot.id)
    assert lot.status == AuctionStatus.EXPIRED
    assert lot.item_name not in CharacterRepository.get_by_id(watcher.id).inventory
    assert _stones(watcher.id) == 777
    print("✓ 系统拍品流拍消散，灵石零变动")


def test_player_lot_conservation_and_idempotent_settle():
    """玩家场成交守恒：全场 Δ = -佣金；重复推进/连查不重复发钱发物"""
    init_db()
    _disable_system_seed()
    seller = _char("守恒卖家", stones=100)
    buyer = _char("守恒买家", stones=500)
    rival = _char("守恒 rival", stones=500)
    ids = [seller.id, buyer.id, rival.id]
    seller.inventory.append("青锋剑")
    CharacterRepository.save(seller)
    now = time.time()
    total0 = _total(ids)
    res = AuctionEngine.list_item(seller, "青锋剑", 100, now=now)
    assert res["success"] is True, res
    lot = res["lot"]
    assert AuctionEngine.bid(buyer, lot.id, 100, now=now)["success"] is True
    assert AuctionEngine.bid(rival, lot.id, 150, now=now)["success"] is True
    # 出价阶段守恒：冻结 150 在场内，其余已退
    assert _total(ids) == total0 - 150
    lot = AuctionEngine._find(lot.id)
    lot.ends_at = now - 1
    AuctionLotRepository.save(lot)
    AuctionEngine.settle_expired(now=now)
    fee = int(150 * config.AUCTION_SETTLE_FEE_RATE)  # 7
    assert _total(ids) == total0 - fee, (_total(ids), total0, fee)
    rival = CharacterRepository.get_by_id(rival.id)
    assert "青锋剑" in rival.inventory
    assert _stones(seller.id) == 100 + 150 - fee
    # 幂等：再结算 + 连查两次看板，总额与物品不再变化
    AuctionEngine.settle_expired(now=now)
    AuctionEngine.board(now=now, rng=_PickRng())
    AuctionEngine.board(now=now, rng=_PickRng())
    assert _total(ids) == total0 - fee
    assert CharacterRepository.get_by_id(rival.id).inventory.count("青锋剑") == 1
    print("✓ 玩家场守恒 Δ=-佣金，结算幂等")


def test_bid_validation():
    """出价校验：低于地板价 / 余额不足 / 自拍自买 / 已是领先者 / 不存在编号"""
    init_db()
    _disable_system_seed()
    seller = _char("校验卖家", stones=100)
    rich = _char("校验富客", stones=1000)
    poor = _char("校验穷客", stones=60)
    seller.inventory.append("回春露")
    CharacterRepository.save(seller)
    now = time.time()
    lot = AuctionEngine.list_item(seller, "回春露", 50, now=now)["lot"]
    assert AuctionEngine.bid(rich, lot.id, 49, now=now)["success"] is False  # 低于起拍
    assert AuctionEngine.bid(seller, lot.id, 50, now=now)["success"] is False  # 自拍自买
    assert AuctionEngine.bid(poor, lot.id, 100, now=now)["success"] is False  # 余额不足
    assert AuctionEngine.bid(rich, "不存在的编号", 50, now=now)["success"] is False
    assert AuctionEngine.bid(rich, lot.id, 50, now=now)["success"] is True
    assert AuctionEngine.bid(rich, lot.id, 60, now=now)["success"] is False  # 已是领先者
    floor = AuctionEngine.floor_price(AuctionEngine._find(lot.id))
    assert floor == 50 + max(config.AUCTION_MIN_INCREMENT, int(50 * 0.05))
    assert AuctionEngine.bid(poor, lot.id, floor - 1, now=now)["success"] is False  # 低于加价地板
    # 失败出价零落账
    assert _stones(poor.id) == 60 and _stones(seller.id) == 100
    print("✓ 出价校验全项（地板价/余额/自拍/领先者/不存在）")


def test_npc_follow_bid_and_refund():
    """NPC 跟价：force 触发走真实账扣款；被玩家超价后自动退款"""
    init_db()
    _disable_system_seed()
    seller = _char("NPC场卖家", stones=100)
    npc = _char("竞价散人", stones=1000, npc=True)
    player = _char("NPC场玩家", stones=1000)
    seller.inventory.append("百年灵芝")
    CharacterRepository.save(seller)
    now = time.time()
    lot = AuctionEngine.list_item(seller, "百年灵芝", 50, now=now)["lot"]
    res = AuctionEngine.npc_maybe_bid(lot, now=now, rng=_PickRng(npc.id), force=True)
    assert res and res["success"] is True, res
    assert res["npc"].id == npc.id and res["amount"] == 50
    assert _stones(npc.id) == 1000 - 50
    lot = AuctionEngine._find(lot.id)
    assert lot.leader_id == npc.id
    # 玩家超价 → NPC 全额退款
    assert AuctionEngine.bid(player, lot.id, 60, now=now)["success"] is True
    assert _stones(npc.id) == 1000
    assert _stones(player.id) == 1000 - 60
    print("✓ NPC 跟价扣款 + 被超价退款")


def test_npc_cap_never_exceeds():
    """NPC 估值上限：cap ≤ 市价×CAP倍率×意愿顶 且 ≤ 自身灵石；地板价高于 cap 时绝不跟价"""
    init_db()
    _disable_system_seed()
    from core.market import MarketEngine

    npc = _char("富甲NPC", stones=10_000_000, npc=True)
    seller = _char("上限卖家", stones=100)
    seller.inventory.append("聚气丹")
    CharacterRepository.save(seller)
    now = time.time()
    lot = AuctionEngine.list_item(seller, "聚气丹", 50, now=now)["lot"]
    base = MarketEngine.market_price("聚气丹")
    cap = AuctionEngine.npc_cap(lot, CharacterRepository.get_by_id(npc.id))
    assert 0 < cap <= int(base * config.AUCTION_NPC_CAP_MULT * 1.24) + 1, (cap, base)
    # 高价拍品：地板价远超 cap → NPC 不跟（玩家哄抬不出 NPC 的钱）
    seller2 = _char("天价卖家", stones=100)
    seller2.inventory.append("聚气丹")
    CharacterRepository.save(seller2)
    lot2 = AuctionEngine.list_item(seller2, "聚气丹", cap + 5000, now=now)["lot"]
    res = AuctionEngine.npc_maybe_bid(lot2, now=now, rng=_PickRng(npc.id), force=True)
    assert res is None
    assert AuctionEngine._find(lot2.id).bid_count == 0
    print("✓ NPC 估值上限硬约束，天价拍品不跟价")


def test_npc_buyout_settles():
    """NPC 达一口价直接落槌：得物、卖家按一口价扣佣收款"""
    init_db()
    _disable_system_seed()
    seller = _char("一口卖家", stones=100)
    npc = _char("一口NPC", stones=1000, npc=True)
    # 青锋剑市价 220：NPC cap 下限 int(220×1.3×0.85)=243 > 80，一口价必达（与 crc 意愿无关）
    seller.inventory.append("青锋剑")
    CharacterRepository.save(seller)
    now = time.time()
    lot = AuctionEngine.list_item(seller, "青锋剑", 80, buyout_price=80, now=now)["lot"]
    res = AuctionEngine.npc_maybe_bid(lot, now=now, rng=_PickRng(npc.id), force=True)
    assert res and res.get("buyout") is True, res
    lot = AuctionEngine._find(lot.id)
    assert lot.status == AuctionStatus.SOLD
    assert "青锋剑" in CharacterRepository.get_by_id(npc.id).inventory
    fee = int(80 * config.AUCTION_SETTLE_FEE_RATE)
    assert _stones(seller.id) == 100 + 80 - fee
    assert _stones(npc.id) == 1000 - 80
    print("✓ NPC 一口价落槌结算")


def test_floor_price_steps():
    """地板价口径：无出价=起拍价；有出价=现价+max(1, 5%)"""
    lot = AuctionLot(seller_id="s", seller_name="卖家", item_name="聚气丹", start_price=50)
    assert AuctionEngine.floor_price(lot) == 50
    lot.bid_count = 1
    lot.current_bid = 200
    assert AuctionEngine.floor_price(lot) == 210
    lot.current_bid = 10
    assert AuctionEngine.floor_price(lot) == 11  # 5% 不足 1 时取最低加价 1
    print("✓ 地板价步长口径")


def test_old_lot_json_compat():
    """旧档兼容：无 starts_at/source 字段的旧 lot JSON 可读、按 player 口径正常结算"""
    init_db()
    _disable_system_seed()
    seller = _char("旧档卖家", stones=100)
    buyer = _char("旧档买家", stones=500)
    seller.inventory.append("青锋剑")
    CharacterRepository.save(seller)
    now = time.time()
    lot = AuctionEngine.list_item(seller, "青锋剑", 100, now=now)["lot"]
    data = lot.model_dump()
    data.pop("starts_at")
    data.pop("source")
    import json as _json

    old = AuctionLot.model_validate(_json.loads(_json.dumps(data)))
    assert old.starts_at == 0.0 and old.source == "player"
    assert AuctionEngine.bid(buyer, lot.id, 100, now=now)["success"] is True
    lot = AuctionEngine._find(lot.id)
    lot.ends_at = now - 1
    AuctionLotRepository.save(lot)
    AuctionEngine.settle_expired(now=now)
    assert "青锋剑" in CharacterRepository.get_by_id(buyer.id).inventory
    print("✓ 旧档 lot JSON 兼容（新字段默认值）")


def test_world_handle_chain_and_meditation_lock():
    """server 双端链路：/拍卖 看板 → /出价 单场直拍 → 多场报错 → /出价 编号 金额；闭关锁门"""
    init_db()
    _clear_all_lots()
    _disable_system_seed()
    from server.world import World

    w = World(auto_tick=False)
    import uuid as _uuid

    suffix = _uuid.uuid4().hex[:6]  # join 按道号取角，同名会取回上轮残留状态（闭关等），须每轮唯一
    r1 = w.join(f"链路卖家{suffix}")
    r2 = w.join(f"链路买家{suffix}")
    seller = w.get_char(r1["token"])
    buyer = w.get_char(r2["token"])
    for c, stones in ((seller, 100), (buyer, 5000)):
        c.born_at = time.time() - 80 * 3600.0
        c.spirit_stones = stones
        CharacterRepository.save(c)
    seller.inventory.append("青锋剑")
    CharacterRepository.save(seller)

    res = w.handle(r1["token"], "/上拍 青锋剑 100")
    assert res.get("ok"), res
    res = w.handle(r2["token"], "/拍卖")
    assert res.get("ok") and "青锋剑" in res["text"], res
    # 单场直拍（无编号）
    res = w.handle(r2["token"], "/出价 120")
    assert res.get("ok"), res
    # 第二件上场后，无编号出价报错；带编号可拍
    seller.inventory.append("回春露")
    CharacterRepository.save(seller)
    res = w.handle(r1["token"], "/上拍 回春露 50")
    assert res.get("ok"), res
    res = w.handle(r2["token"], "/出价 60")
    assert not res.get("ok") and "多件拍品" in (res.get("error") or ""), res
    lots = AuctionEngine.open_lots()
    target = [l for l in lots if l.item_name == "回春露"][0]
    res = w.handle(r2["token"], f"/出价 {target.id} 60")
    assert res.get("ok"), res
    # 卖家不可自拍
    res = w.handle(r1["token"], f"/拍 {target.id} 70")
    assert not res.get("ok"), res
    # 闭关锁门：拍卖全系指令不在白名单（与 server 既有口径一致）
    buyer = w.get_char(r2["token"])
    buyer.status = CharacterStatus.MEDITATING
    CharacterRepository.save(buyer)
    for cmd in ("/拍卖", f"/拍 {target.id} 80", "/上拍 聚气丹 10"):
        res = w.handle(r2["token"], cmd)
        assert not res.get("ok") and "闭关锁门" in (res.get("error") or ""), (cmd, res)
    print("✓ World.handle 全链路：看板/单场直拍/多场报错/编号出价/自拍拒/闭关锁门")


def test_cli_source_parity():
    """CLI 对齐源码断言：cli/main.py 含全部拍卖动作分支（与 server 同名同义）"""
    root = Path(__file__).resolve().parent.parent
    cli = (root / "cli" / "main.py").read_text(encoding="utf-8")
    for token in ('"/拍卖行", "/拍卖", "auction"', '"/上拍", "auction_list"',
                  '"/拍", "/出价", "bid"', '"/一口", "buyout"', '"/撤拍", "auction_cancel"'):
        assert token in cli, token
    world = (root / "server" / "world.py").read_text(encoding="utf-8")
    assert '"/auction", "/拍卖行", "/拍卖"' in world and '"/bid", "/拍", "/出价"' in world
    print("✓ CLI/server 拍卖指令动作表对齐")
