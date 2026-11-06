"""
典当行（F04）：行囊抵押周转——典当得灵石（当地市价五折）、限期按本金+固定息赎回、
逾期没收转坊市寄售流通。规则权威在此裁决；文案全为本地模板，零 AI 调用。
Spec：docs/compose/spec/pawn.md
"""
from __future__ import annotations

import math
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import (
    ITEM_CATALOG,
    PAWN_INTEREST_RATE,
    PAWN_MAX_TICKETS,
    PAWN_RATE,
    PAWN_SHOP_ID,
    PAWN_SHOP_NAME,
    PAWN_TERM_DAYS,
)
from core.market import MarketEngine, MarketListing, ListingStatus
from core.models import Character, CharacterStatus

PAWN_TERM_SECONDS = PAWN_TERM_DAYS * 86400.0


class PawnStatus(str, Enum):
    OPEN = "OPEN"            # 在当，可赎
    REDEEMED = "REDEEMED"    # 已赎回，了结
    FORFEITED = "FORFEITED"  # 逾期没收，已流入寄售


class PawnTicket(BaseModel):
    """典当票（天道当铺契约）：逐件成票，同名多件互不相干"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    owner_id: str
    owner_name: str
    item_name: str
    kind: str = "material"
    principal: int           # 典当额（成票时按当地市价写死）
    interest: int            # 固定息（成票时写死，赎回 = principal + interest）
    pawned_at: float = 0.0
    due_at: float = 0.0      # pawned_at + PAWN_TERM_SECONDS
    status: PawnStatus = PawnStatus.OPEN

    def is_open(self) -> bool:
        return self.status == PawnStatus.OPEN

    def redeem_cost(self) -> int:
        return self.principal + self.interest


class PawnEngine:
    """典当裁决引擎（价格复用 MarketEngine 单点，不另起价格表）"""

    # ---------------- 估值与利息（纯函数，可复算） ----------------
    @staticmethod
    def pawn_value(item_name: str, location: Optional[str] = None) -> int:
        """典当额 = 当地市价 × PAWN_RATE，下限 1"""
        return max(1, int(MarketEngine.market_price(item_name, location) * PAWN_RATE))

    @staticmethod
    def interest_for(principal: int) -> int:
        """固定息：max(1, ceil(典当额 × 利率))——本金 ≥1 时息 ≥1，赎回恒贵于典当"""
        return max(1, math.ceil(int(principal) * PAWN_INTEREST_RATE))

    # ---------------- 仓储便捷 ----------------
    @staticmethod
    def my_tickets(owner_id: str) -> List[PawnTicket]:
        from storage.db import PawnTicketRepository

        return PawnTicketRepository.list_by_owner(owner_id)

    @staticmethod
    def open_tickets(owner_id: str) -> List[PawnTicket]:
        rows = [t for t in PawnEngine.my_tickets(owner_id) if t.is_open()]
        rows.sort(key=lambda t: t.due_at)
        return rows

    # ---------------- 逾期没收（惰性结算，指令路径触发） ----------------
    @staticmethod
    def settle_expired(
        owner_id: Optional[str] = None,
        now: Optional[float] = None,
        location: Optional[str] = None,
    ) -> List[PawnTicket]:
        """把已到期 OPEN 票没收：物品生成当铺寄售流入坊市。
        寄售价 = 票面赎回价（本金+息，成票时写死，与结算地点无关）——
        票主自买回的成本恒等于赎回，杜绝「等逾期低价买回」的无息赎回与区域价差套利（评审 M1）。
        owner_id=None 表示全量结算（仅测试/GM 用）。
        没收与寄售由本函数内部落库（同 AuctionEngine.settle_expired 惯例）。"""
        from storage.db import MarketListingRepository, PawnTicketRepository

        t = now if now is not None else time.time()
        if owner_id is not None:
            tickets = PawnTicketRepository.list_by_owner(owner_id)
        else:
            tickets = PawnTicketRepository.list_all()
        settled: List[PawnTicket] = []
        for ticket in tickets:
            if not ticket.is_open() or t < ticket.due_at:
                continue
            PawnEngine._forfeit_ticket(ticket, t)
            settled.append(ticket)
        return settled

    @staticmethod
    def _forfeit_ticket(ticket: PawnTicket, t: float) -> None:
        """单票没收落库（逾期结算与死亡没收共用口径）：票 → FORFEITED，
        物品以赎回价挂当铺寄售（卖家为当铺伪主体，买家付款沉淀当铺，不入任何钱包）。"""
        from storage.db import MarketListingRepository, PawnTicketRepository

        ticket.status = PawnStatus.FORFEITED
        listing = MarketListing(
            seller_id=PAWN_SHOP_ID,
            seller_name=PAWN_SHOP_NAME,
            item_name=ticket.item_name,
            kind=ticket.kind,
            price=ticket.redeem_cost(),
            status=ListingStatus.OPEN,
            created_at=t,
        )
        MarketListingRepository.save(listing)
        PawnTicketRepository.save(ticket)

    @staticmethod
    def forfeit_all(owner_id: str, now: Optional[float] = None) -> List[PawnTicket]:
        """死亡 sweep：无条件没收该主全部 OPEN 当票（不论是否到期，逾期口径）。

        本金不另记——典当时本金已付入随身灵石，由死亡归集随身步一并入钱包，
        此处只处理物品侧。返回本次没收的票据。"""
        from storage.db import PawnTicketRepository

        t = now if now is not None else time.time()
        settled: List[PawnTicket] = []
        for ticket in PawnTicketRepository.list_by_owner(owner_id):
            if not ticket.is_open():
                continue
            PawnEngine._forfeit_ticket(ticket, t)
            settled.append(ticket)
        return settled

    # ---------------- 典当 ----------------
    @staticmethod
    def pawn_item(
        char: Character,
        item_name: str,
        now: Optional[float] = None,
    ) -> Tuple[Optional[PawnTicket], Dict[str, Any]]:
        """典当行囊中 1 件物品。成功才改状态（成票由调用方落库）。"""
        if char.status == CharacterStatus.DEAD:
            return None, {"success": False, "message": "死人不可进当铺。"}
        t = now if now is not None else time.time()
        PawnEngine.settle_expired(char.id, now=t, location=char.location)
        item_name = (item_name or "").strip()
        if not item_name:
            return None, {"success": False, "message": "用法：/典当 <物品名>（无参查看当票）"}
        # 著书立说（F11）：亲笔手稿不可典当（保书目绑定一致，只许寄售/赠予；直导入 fail-closed）
        from core.books import BOOK_ITEM

        if item_name == BOOK_ITEM:
            return None, {"success": False, "message": "【亲笔手稿】乃著者心血，当铺不收；可 /寄售 亲笔手稿 <价> 流通。"}
        if item_name not in char.inventory:
            if item_name in char.equipped:
                return None, {
                    "success": False,
                    "message": f"【{item_name}】正穿戴在身，须先 /卸下 放入行囊方可典当。",
                }
            return None, {"success": False, "message": f"行囊中并无【{item_name}】可当。"}
        open_rows = PawnEngine.open_tickets(char.id)
        if len(open_rows) >= PAWN_MAX_TICKETS:
            return None, {
                "success": False,
                "message": f"当票已满（上限 {PAWN_MAX_TICKETS} 张），请先 /赎回 腾挪。",
            }

        principal = PawnEngine.pawn_value(item_name, char.location)
        interest = PawnEngine.interest_for(principal)
        cfg = ITEM_CATALOG.get(item_name)
        ticket = PawnTicket(
            owner_id=char.id,
            owner_name=char.name,
            item_name=item_name,
            kind=cfg["kind"] if cfg else "material",
            principal=principal,
            interest=interest,
            pawned_at=t,
            due_at=t + PAWN_TERM_SECONDS,
            status=PawnStatus.OPEN,
        )
        char.inventory.remove(item_name)
        char.spirit_stones += principal
        return ticket, {
            "success": True,
            "principal": principal,
            "interest": interest,
            "message": (
                f"【天道当铺】收当【{item_name}】，付灵石 {principal}。"
                f"当期 {PAWN_TERM_DAYS} 天，赎回价 {ticket.redeem_cost()} 灵石（本金 {principal} + 息 {interest}），"
                f"逾期不赎则没收流入坊市。票号 {ticket.id}，/典当 查看当票。"
            ),
        }

    # ---------------- 赎回 ----------------
    @staticmethod
    def redeem_item(
        char: Character,
        item_name: str,
        now: Optional[float] = None,
    ) -> Tuple[Optional[PawnTicket], Dict[str, Any]]:
        """赎回该物品最早到期的一张 OPEN 票。灵石不足时票保持 OPEN（到期前可再赎）。"""
        if char.status == CharacterStatus.DEAD:
            return None, {"success": False, "message": "死人不可进当铺。"}
        t = now if now is not None else time.time()
        settled = PawnEngine.settle_expired(char.id, now=t, location=char.location)

        item_name = (item_name or "").strip()
        if not item_name:
            return None, {"success": False, "message": "用法：/赎回 <物品名>"}
        open_rows = [x for x in PawnEngine.open_tickets(char.id) if x.item_name == item_name]
        if not open_rows:
            gone = [x for x in settled if x.item_name == item_name] or [
                x for x in PawnEngine.my_tickets(char.id)
                if x.item_name == item_name and x.status == PawnStatus.FORFEITED
            ]
            if gone:
                return None, {
                    "success": False,
                    "message": f"【{item_name}】的当票已逾期，物品已没收流入坊市寄售（/坊市 可寻）。",
                }
            return None, {"success": False, "message": f"并无【{item_name}】的在当票据。/典当 查看。"}
        ticket = open_rows[0]  # FIFO：最早到期先赎
        cost = ticket.redeem_cost()
        if char.spirit_stones < cost:
            return None, {
                "success": False,
                "message": (
                    f"赎【{item_name}】需 {cost} 灵石（本金 {ticket.principal} + 息 {ticket.interest}），"
                    f"囊中仅有 {char.spirit_stones}。当票到期前仍有效，凑足再来。"
                ),
            }
        char.spirit_stones -= cost
        char.inventory.append(ticket.item_name)
        ticket.status = PawnStatus.REDEEMED
        return ticket, {
            "success": True,
            "cost": cost,
            "message": (
                f"【赎当】付 {cost} 灵石（本金 {ticket.principal} + 息 {ticket.interest}），"
                f"【{ticket.item_name}】已回行囊。票号 {ticket.id} 就此了结。"
            ),
        }

    # ---------------- 查看 ----------------
    @staticmethod
    def panel_text(char: Character, now: Optional[float] = None) -> str:
        """【天道当铺】本人当票一览：OPEN 逐行、FORFEITED 标注没收，REDEEMED 不展示"""
        t = now if now is not None else time.time()
        PawnEngine.settle_expired(char.id, now=t, location=char.location)
        rows = PawnEngine.my_tickets(char.id)
        open_rows = [x for x in rows if x.is_open()]
        open_rows.sort(key=lambda x: x.due_at)
        # 没收记录只展示最近 5 张（防长期游玩后面板被旧账淹没，评审 S4）
        forfeited = [x for x in rows if x.status == PawnStatus.FORFEITED]
        forfeited.sort(key=lambda x: x.pawned_at, reverse=True)
        forfeited = forfeited[:5]
        lines = [
            f"【天道当铺】{char.name} 的当票（典当率五折 · 固定息 {int(PAWN_INTEREST_RATE * 100)}% · 当期 {PAWN_TERM_DAYS} 天）：",
        ]
        if not open_rows and not forfeited:
            lines.append("暂无典当。/典当 <物品名> 可当行囊之物周转，/赎回 <物品名> 按票赎回。")
        for ticket in open_rows:
            left_h = max(0.0, (ticket.due_at - t) / 3600.0)
            lines.append(
                f"  · 【{ticket.item_name}】当 {ticket.principal} 灵石，赎回价 {ticket.redeem_cost()}"
                f"（息 {ticket.interest}），余期 {left_h:.1f} 小时（票号 {ticket.id}）"
            )
        for ticket in forfeited:
            lines.append(
                f"  · 【{ticket.item_name}】已逾期没收，物品已流入坊市寄售（票号 {ticket.id}）"
            )
        return "\n".join(lines)
