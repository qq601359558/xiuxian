"""
坊市四通道：当面交易 · NPC 专柜 · 拍卖行（寄售仍在 market.py）
规则权威：价格/可否交易/落槌全由规则裁决。
"""
from __future__ import annotations

import random
import time
import uuid
import zlib
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import (
    ITEM_CATALOG,
    WORLD_LOCATIONS,
    TRADE_TIMEOUT_MIN,
    AUCTION_DURATION_MIN,
    AUCTION_MIN_INCREMENT,
    AUCTION_SETTLE_FEE_RATE,
    AUCTION_MAX_LOTS,
    AUCTION_NPC_BID_CHANCE,
    AUCTION_NPC_CAP_MULT,
    AUCTION_SYSTEM_INTERVAL_SECONDS,
    AUCTION_SYSTEM_LEAD_SECONDS,
    AUCTION_SYSTEM_START_RATE,
    AUCTION_HOUSE_ID,
    AUCTION_HOUSE_NAME,
    AUCTION_SYSTEM_ITEMS,
    NPC_PRICE_FRIENDLY_BUY,
    NPC_PRICE_NEUTRAL_BUY,
    NPC_PRICE_HOSTILE_BUY,
    NPC_PRICE_FRIENDLY_SELL,
    NPC_PRICE_NEUTRAL_SELL,
    NPC_PRICE_HOSTILE_SELL,
    NPC_ATTITUDE_FRIENDLY,
    NPC_ATTITUDE_HOSTILE,
)
from core.models import Character, CharacterStatus


# ==================== 公共门禁 ====================

def can_use_market(c: Character, now: Optional[float] = None) -> Tuple[bool, str]:
    """能否参与坊市资产转移（当面/NPC/拍卖/寄售共用）"""
    t = now if now is not None else time.time()
    if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
        return False, "身死道消，不可交易。"
    if c.status == CharacterStatus.MEDITATING:
        return False, "六识封闭，闭关中不可交易；请先 /出关。"
    from core.protection import ProtectionEngine

    ok, reason = ProtectionEngine.can_transfer_assets(c)
    if not ok:
        return False, reason
    return True, ""


def _take_item(c: Character, item_name: str, qty: int = 1) -> bool:
    """从随身 inventory（或阵盘 arrays）扣 qty 件；不足返回 False 且不改动。"""
    have_inv = c.inventory.count(item_name)
    have_arr = c.arrays.count(item_name)
    if have_inv + have_arr < qty:
        return False
    left = qty
    while left > 0 and item_name in c.inventory:
        c.inventory.remove(item_name)
        left -= 1
    while left > 0 and item_name in c.arrays:
        c.arrays.remove(item_name)
        left -= 1
    return True


def _give_item(c: Character, item_name: str, qty: int = 1, kind: str = "material") -> None:
    if kind == "array":
        for _ in range(qty):
            if item_name not in c.arrays:
                c.arrays.append(item_name)
            else:
                c.inventory.append(item_name)
    else:
        for _ in range(qty):
            c.inventory.append(item_name)


def _find_by_id_or_user(char_id: str, user_id: str = "") -> Optional[Character]:
    """优先按 id；失败再按 user_id（转世/冲突改号时兜底）。"""
    from storage.db import CharacterRepository

    if char_id:
        c = CharacterRepository.get_by_id(char_id)
        if c:
            return c
    if user_id:
        return CharacterRepository.get_by_user_id(user_id)
    return None


# ==================== 玩家当面交易 ====================

class TradeStatus(str, Enum):
    OPEN = "OPEN"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TradeSession(BaseModel):
    """进程内当面交易会话"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    a_id: str
    a_name: str
    b_id: str
    b_name: str
    a_stones: int = 0
    b_stones: int = 0
    a_items: List[str] = Field(default_factory=list)
    b_items: List[str] = Field(default_factory=list)
    a_ok: bool = False
    b_ok: bool = False
    location: str = ""
    created_at: float = 0.0
    status: TradeStatus = TradeStatus.OPEN

    def side_of(self, user_id: str) -> str:
        if user_id == self.a_id:
            return "a"
        if user_id == self.b_id:
            return "b"
        return ""

    def summary(self) -> str:
        a_items = "、".join(self.a_items) or "无"
        b_items = "、".join(self.b_items) or "无"
        return (
            f"【当面交易】{self.a_name} ↔ {self.b_name}（地点：{self.location}）\n"
            f"· {self.a_name} 出：灵石 {self.a_stones} | {a_items}  "
            f"{'✓已同意' if self.a_ok else '…待同意'}\n"
            f"· {self.b_name} 出：灵石 {self.b_stones} | {b_items}  "
            f"{'✓已同意' if self.b_ok else '…待同意'}\n"
            f"改报价会清除双方同意；/交易同意 双方皆确认后成交；/交易拒绝 取消。"
        )


# 进程内会话表：session_id -> TradeSession；user_id -> session_id
_trade_sessions: Dict[str, TradeSession] = {}
_trade_by_user: Dict[str, str] = {}


def _session_for(user_id: str) -> Optional[TradeSession]:
    sid = _trade_by_user.get(user_id)
    if not sid:
        return None
    s = _trade_sessions.get(sid)
    if not s or s.status != TradeStatus.OPEN:
        _trade_by_user.pop(user_id, None)
        return None
    return s


def _expire_stale(now: Optional[float] = None) -> None:
    t = now if now is not None else time.time()
    timeout = TRADE_TIMEOUT_MIN * 60.0
    for sid, s in list(_trade_sessions.items()):
        if s.status != TradeStatus.OPEN:
            continue
        if t - s.created_at >= timeout:
            _cancel_session(s, reason="超时自动取消")


def _cancel_session(s: TradeSession, reason: str = "已取消") -> Dict[str, Any]:
    from storage.db import CharacterRepository

    s.status = TradeStatus.CANCELLED
    a = CharacterRepository.get_by_id(s.a_id)
    b = CharacterRepository.get_by_id(s.b_id)
    lines = [f"【交易取消】{reason}"]
    updated: Dict[str, Character] = {}
    if a:
        a.spirit_stones += s.a_stones
        for it in s.a_items:
            a.inventory.append(it)
        if s.a_stones or s.a_items:
            lines.append(f"{s.a_name} 已退回灵石 {s.a_stones} 与 {len(s.a_items)} 件货物。")
        CharacterRepository.save(a)
        updated[a.id] = a
    if b:
        b.spirit_stones += s.b_stones
        for it in s.b_items:
            b.inventory.append(it)
        if s.b_stones or s.b_items:
            lines.append(f"{s.b_name} 已退回灵石 {s.b_stones} 与 {len(s.b_items)} 件货物。")
        CharacterRepository.save(b)
        updated[b.id] = b
    _trade_by_user.pop(s.a_id, None)
    _trade_by_user.pop(s.b_id, None)
    _trade_sessions.pop(s.id, None)
    return {"success": True, "message": "\n".join(lines), "updated": updated}


class TradeEngine:
    """玩家当面交易"""

    @staticmethod
    def open_trade(a: Character, b_name: str, now: Optional[float] = None) -> Dict[str, Any]:
        _expire_stale(now)
        t = now if now is not None else time.time()
        ok_a, reason_a = can_use_market(a, t)
        if not ok_a:
            return {"success": False, "message": reason_a}
        if _session_for(a.id):
            return {"success": False, "message": "你已有进行中的当面交易，请先 /交易拒绝 或完成。"}

        from storage.db import CharacterRepository

        b = CharacterRepository.find_alive_by_name(b_name)
        if not b:
            return {"success": False, "message": f"未寻得修士【{b_name}】。"}
        if b.id == a.id:
            return {"success": False, "message": "不可与自己交易。"}
        ok_b, reason_b = can_use_market(b, t)
        if not ok_b:
            return {"success": False, "message": f"【{b.name}】无法交易：{reason_b}"}
        if _session_for(b.id):
            return {"success": False, "message": f"【{b.name}】已有进行中的交易。"}
        if a.location != b.location:
            return {
                "success": False,
                "message": f"当面交易须同地：你在【{a.location}】，对方在【{b.location}】。",
            }
        loc = WORLD_LOCATIONS.get(a.location) or {}
        if not loc.get("is_safe", False):
            return {
                "success": False,
                "message": f"【{a.location}】非安全区，不可当面交易（防野外洗赃）。请赴坊市/宗门驻地。",
            }

        s = TradeSession(
            a_id=a.id,
            a_name=a.name,
            b_id=b.id,
            b_name=b.name,
            location=a.location,
            created_at=t,
        )
        _trade_sessions[s.id] = s
        _trade_by_user[a.id] = s.id
        _trade_by_user[b.id] = s.id
        return {
            "success": True,
            "session": s,
            "message": (
                f"【当面交易】已向【{b.name}】发起。\n"
                f"双方用 /交易出 <灵石> [物品…] 报价，/交易 查看，/交易同意 成交。"
            ),
        }

    @staticmethod
    def set_offer(
        c: Character,
        stones: int,
        items: Optional[List[str]] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        _expire_stale(now)
        s = _session_for(c.id)
        if not s:
            return {"success": False, "message": "当前无进行中的当面交易。"}
        if stones < 0:
            return {"success": False, "message": "灵石不可为负。"}
        items = items or []

        # 先退回旧锁定，再扣新的（避免中途失败丢货）
        TradeEngine._unlock_side(c, s)

        if stones > c.spirit_stones:
            return {"success": False, "message": f"随身仅有 {c.spirit_stones} 灵石，不足 {stones}。"}
        take_map: Dict[str, int] = {}
        for it in items:
            take_map[it] = take_map.get(it, 0) + 1
        for it, n in take_map.items():
            if c.inventory.count(it) < n:
                return {"success": False, "message": f"随身【{it}】不足 {n} 件，报价未生效。"}
        for it, n in take_map.items():
            for _ in range(n):
                c.inventory.remove(it)

        c.spirit_stones -= stones
        side = s.side_of(c.id)
        if side == "a":
            s.a_stones = stones
            s.a_items = list(items)
            s.a_ok = False
        else:
            s.b_stones = stones
            s.b_items = list(items)
            s.b_ok = False
        # 改一方报价即清除双方同意
        s.a_ok = False
        s.b_ok = False
        return {"success": True, "message": s.summary(), "session": s}

    @staticmethod
    def _unlock_side(c: Character, s: TradeSession) -> None:
        side = s.side_of(c.id)
        if side == "a":
            c.spirit_stones += s.a_stones
            for it in s.a_items:
                c.inventory.append(it)
            s.a_stones = 0
            s.a_items = []
            s.a_ok = False
        elif side == "b":
            c.spirit_stones += s.b_stones
            for it in s.b_items:
                c.inventory.append(it)
            s.b_stones = 0
            s.b_items = []
            s.b_ok = False

    @staticmethod
    def view(c: Character) -> Dict[str, Any]:
        _expire_stale()
        s = _session_for(c.id)
        if not s:
            return {"success": False, "message": "当前无进行中的当面交易。"}
        return {"success": True, "message": s.summary(), "session": s}

    @staticmethod
    def accept(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        _expire_stale(now)
        s = _session_for(c.id)
        if not s:
            return {"success": False, "message": "当前无进行中的当面交易。"}
        side = s.side_of(c.id)
        if side == "a":
            s.a_ok = True
        else:
            s.b_ok = True
        if not (s.a_ok and s.b_ok):
            return {
                "success": True,
                "message": f"你已同意，等待对方…\n{s.summary()}",
                "session": s,
            }
        return TradeEngine._execute(s)

    @staticmethod
    def _execute(s: TradeSession) -> Dict[str, Any]:
        from storage.db import CharacterRepository, ChronicleRepository

        a = CharacterRepository.get_by_id(s.a_id)
        b = CharacterRepository.get_by_id(s.b_id)
        if not a or not b:
            return _cancel_session(s, reason="对方已不在世")
        # 再验前置（防同意后对方闭关/离地）
        for c in (a, b):
            ok, reason = can_use_market(c)
            if not ok:
                return _cancel_session(s, reason=reason)
        if a.location != b.location or b.location != s.location:
            return _cancel_session(s, reason="交易中地点变化")
        loc = WORLD_LOCATIONS.get(s.location) or {}
        if not loc.get("is_safe", False):
            return _cancel_session(s, reason="所在地点已非安全区")

        # 原子交换（锁定物仍在会话里，不在双方 inventory）
        a_stones, b_stones = s.a_stones, s.b_stones
        a_items, b_items = list(s.a_items), list(s.b_items)
        a.spirit_stones += b_stones
        b.spirit_stones += a_stones
        for it in b_items:
            a.inventory.append(it)
        for it in a_items:
            b.inventory.append(it)
        s.a_stones, s.b_stones = 0, 0
        s.a_items, s.b_items = [], []
        s.status = TradeStatus.DONE
        CharacterRepository.save(a)
        CharacterRepository.save(b)
        _trade_by_user.pop(a.id, None)
        _trade_by_user.pop(b.id, None)
        _trade_sessions.pop(s.id, None)
        tip = ""
        try:
            ChronicleRepository.record(
                "TRADE",
                f"{a.name}/{b.name}",
                f"当面成交于【{s.location}】",
            )
            from core import rumors

            rumors.note_trade(a.name, b.name, s.location)
            try:
                from core import ai_flavor

                tip = ai_flavor.polish_face_trade(
                    a.name, b.name, a_stones, b_stones,
                    "、".join(a_items) or "", "、".join(b_items) or "", s.location,
                ) or ""
            except Exception:
                tip = ""
            try:
                from config import CHANNEL_TRADE_MIN_SUM
                from core.world_channel import WorldChannel

                total = a_stones + b_stones
                if total >= CHANNEL_TRADE_MIN_SUM:
                    WorldChannel.post(
                        "trade",
                        f"【坊市】{a.name} 与 {b.name} 当面交割，合计逾 {total} 灵石。",
                        level="major",
                        actor=a.name,
                        location=s.location,
                    )
            except Exception:
                pass
        except Exception:
            tip = ""
        msg = (
            f"【契约成交】{a.name} ↔ {b.name} 于【{s.location}】当面交割完毕。\n"
            f"灵石与货物已互换，天道为证。"
        )
        if tip:
            msg += f"\n「{tip}」"
        return {
            "success": True,
            "updated": {a.id: a, b.id: b},
            "message": msg,
            "session": s,
        }

    @staticmethod
    def reject(c: Character) -> Dict[str, Any]:
        s = _session_for(c.id)
        if not s:
            return {"success": False, "message": "当前无进行中的当面交易。"}
        return _cancel_session(s, reason=f"【{c.name}】拒绝交易")

    @staticmethod
    def active_for_debug() -> Dict[str, TradeSession]:
        return dict(_trade_sessions)


# ==================== NPC 专柜 ====================

def _npc_role_text(npc: Character) -> str:
    text = f"{npc.sect or ''} {npc.sect_rank or ''}"
    try:
        from core.npc_roster import ROSTER

        for row in ROSTER:
            if row.get("name") == npc.name:
                text += " " + (row.get("rank") or "") + " " + (row.get("note") or "")
                break
    except Exception:
        pass
    return text


def npc_shop_kinds(npc: Character) -> List[str]:
    """按职分裁剪可售 kind"""
    t = _npc_role_text(npc)
    if any(k in t for k in ("丹", "药", "掌柜")):
        return ["pill"]
    if any(k in t for k in ("铁", "剑", "匠", "兵")):
        return ["equip"]
    if any(k in t for k in ("阵",)):
        return ["array"]
    if any(k in t for k in ("商", "市", "货", "会长", "执事", "牙人", "镖")):
        return ["pill", "equip", "material", "map"]
    # 兜底：杂货
    return ["material", "pill"]


def npc_accepts_sell(npc: Character) -> bool:
    t = _npc_role_text(npc)
    return any(k in t for k in ("商", "市", "掌柜", "会长", "执事", "牙人", "货", "铁", "匠"))


def attitude_buy_mult(npc: Character, player_id: str) -> Tuple[float, str]:
    from core.npc_mind import attitude_toward

    att = attitude_toward(npc, player_id)
    v = int(att.get("value") or 0)
    if v >= NPC_ATTITUDE_FRIENDLY:
        return NPC_PRICE_FRIENDLY_BUY, "交好折扣"
    if v <= NPC_ATTITUDE_HOSTILE:
        return NPC_PRICE_HOSTILE_BUY, "敌意加价"
    return NPC_PRICE_NEUTRAL_BUY, "市价"


def attitude_sell_mult(npc: Character, player_id: str) -> Tuple[float, str]:
    from core.npc_mind import attitude_toward

    att = attitude_toward(npc, player_id)
    v = int(att.get("value") or 0)
    if v >= NPC_ATTITUDE_FRIENDLY:
        return NPC_PRICE_FRIENDLY_SELL, "交好优价"
    if v <= NPC_ATTITUDE_HOSTILE:
        return NPC_PRICE_HOSTILE_SELL, "敌意压价"
    return NPC_PRICE_NEUTRAL_SELL, "市价"


class NpcShopEngine:
    """同地 NPC 职分专柜"""

    @staticmethod
    def _resolve(player: Character, npc_name: str) -> Tuple[Optional[Character], str]:
        from storage.db import CharacterRepository

        npc = CharacterRepository.find_alive_by_name(npc_name)
        if not npc:
            # 宽松匹配
            for c in CharacterRepository.list_all_alive():
                if npc_name and (npc_name in c.name or c.name in npc_name):
                    npc = c
                    break
        if not npc:
            return None, f"未寻得【{npc_name}】。"
        if npc.id == player.id:
            return None, "不可与自己买卖。"
        if npc.status == CharacterStatus.DEAD or npc.lifespan.is_dead():
            return None, f"【{npc.name}】已坐化。"
        if npc.location != player.location:
            return None, f"【{npc.name}】不在【{player.location}】，无法当面交易。"
        return npc, ""

    @staticmethod
    def catalog(player: Character, npc_name: str) -> Dict[str, Any]:
        npc, err = NpcShopEngine._resolve(player, npc_name)
        if not npc:
            return {"success": False, "message": err}
        kinds = npc_shop_kinds(npc)
        mult, mult_note = attitude_buy_mult(npc, player.id)
        lines = [
            f"【专柜】{npc.name} · {npc.sect or '散修'}·{npc.sect_rank or ''} "
            f"（{mult_note} ×{mult:.2f}）"
        ]
        rows = []
        for name, cfg in ITEM_CATALOG.items():
            if cfg.get("kind") not in kinds:
                continue
            price = max(1, int(cfg["price"] * mult))
            rows.append((price, name, cfg))
        rows.sort(key=lambda x: x[0])
        for price, name, cfg in rows[:20]:
            lines.append(f"· {name}（{cfg['kind']}）— {price} 灵石  {cfg.get('desc','')[:24]}")
        if not npc_accepts_sell(npc):
            lines.append("此柜只售不收。")
        else:
            sm, snote = attitude_sell_mult(npc, player.id)
            lines.append(f"回收：/npc卖 <货名> [数量]（{snote} ×{sm:.2f}，按商会回收价再乘）")
        return {"success": True, "message": "\n".join(lines), "npc": npc}

    @staticmethod
    def buy(player: Character, npc_name: str, item_name: str, qty: int = 1) -> Dict[str, Any]:
        ok, reason = can_use_market(player)
        if not ok:
            return {"success": False, "message": reason}
        npc, err = NpcShopEngine._resolve(player, npc_name)
        if not npc:
            return {"success": False, "message": err}
        cfg = ITEM_CATALOG.get(item_name)
        if not cfg:
            for k in ITEM_CATALOG:
                if item_name and (item_name in k or k in item_name):
                    item_name = k
                    cfg = ITEM_CATALOG[k]
                    break
        if not cfg:
            return {"success": False, "message": f"【{npc.name}】并无此货。可 /npc货单 {npc.name}。"}
        kinds = npc_shop_kinds(npc)
        if cfg.get("kind") not in kinds:
            return {
                "success": False,
                "message": f"【{npc.name}】职分不售此货（本行：{'/'.join(kinds)}）。",
            }
        if qty < 1:
            return {"success": False, "message": "数量至少为 1。"}
        mult, _ = attitude_buy_mult(npc, player.id)
        unit = max(1, int(cfg["price"] * mult))
        total = unit * qty
        if player.spirit_stones < total:
            return {
                "success": False,
                "message": f"【{item_name}】单价 {unit}，共需 {total}，囊中仅有 {player.spirit_stones}。",
            }
        player.spirit_stones -= total
        _give_item(player, item_name, qty, cfg.get("kind", "material"))
        line_extra = ""
        try:
            from core import ai_flavor
            from core.npc_personas import persona_prompt_block

            line_extra = ai_flavor.polish_npc_sell(
                npc.name,
                player.name,
                item_name,
                int(cfg["price"]),
                mult,
                loc=player.location,
                persona=persona_prompt_block(npc),
            )
        except Exception:
            line_extra = ""
        msg = (
            f"【专柜成交】自【{npc.name}】购入【{item_name}】×{qty}，付 {total} 灵石。"
        )
        if line_extra:
            msg += f"\n「{line_extra}」"
        return {
            "success": True,
            "message": msg,
            "total": total,
            "unit": unit,
        }

    @staticmethod
    def sell(player: Character, npc_name: str, item_name: str, qty: int = 1) -> Dict[str, Any]:
        ok, reason = can_use_market(player)
        if not ok:
            return {"success": False, "message": reason}
        npc, err = NpcShopEngine._resolve(player, npc_name)
        if not npc:
            return {"success": False, "message": err}
        if not npc_accepts_sell(npc):
            return {"success": False, "message": f"【{npc.name}】只售不收。"}
        cfg = ITEM_CATALOG.get(item_name, {"kind": "material", "price": 20})
        if not _take_item(player, item_name, qty):
            return {"success": False, "message": f"随身并无足够的【{item_name}】。"}
        from config import MARKET_SELL_BACK_RATE

        mult, _ = attitude_sell_mult(npc, player.id)
        unit = max(1, int(cfg.get("price", 20) * MARKET_SELL_BACK_RATE * mult))
        gain = unit * qty
        player.spirit_stones += gain
        return {
            "success": True,
            "message": f"【专柜回收】售与【{npc.name}】【{item_name}】×{qty}，得灵石 {gain}。",
            "gain": gain,
        }


# ==================== 拍卖行 ====================

class AuctionStatus(str, Enum):
    PENDING = "PENDING"  # 待开场（F05 系统场次；玩家上拍直接 OPEN）
    OPEN = "OPEN"
    SOLD = "SOLD"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class AuctionLot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    seller_id: str
    seller_user_id: str = ""
    seller_name: str
    item_name: str
    kind: str = "material"
    start_price: int
    buyout_price: Optional[int] = None
    current_bid: int = 0
    leader_id: Optional[str] = None
    leader_user_id: Optional[str] = None
    leader_name: Optional[str] = None
    bid_count: int = 0
    ends_at: float = 0.0
    created_at: float = 0.0
    status: AuctionStatus = AuctionStatus.OPEN
    # F05：系统场次待开场与来源（旧档无此二字段，默认值自动兼容；零改表）
    starts_at: float = 0.0
    source: str = "player"  # player=玩家上拍 / system=天道宝库系统场次

    def is_open(self) -> bool:
        return self.status == AuctionStatus.OPEN

    def remaining_min(self, now: Optional[float] = None) -> float:
        t = now if now is not None else time.time()
        return max(0.0, (self.ends_at - t) / 60.0)

    def board_line(self, now: Optional[float] = None) -> str:
        bid = self.current_bid if self.bid_count else self.start_price
        buyout = f" | 一口价 {self.buyout_price}" if self.buyout_price else ""
        leader = self.leader_name or "（暂无）"
        return (
            f"#{self.id} 【{self.item_name}】当前 {bid} 灵石（起拍 {self.start_price}{buyout}）"
            f" | 领先 {leader} | 余 {self.remaining_min(now):.0f} 分 | 挂单人 {self.seller_name}"
        )

    def pending_line(self, now: Optional[float] = None) -> str:
        t = now if now is not None else time.time()
        mins = max(0.0, (self.starts_at - t) / 60.0)
        buyout = f" | 一口价 {self.buyout_price}" if self.buyout_price else ""
        return (
            f"#{self.id} 【{self.item_name}】起拍 {self.start_price}{buyout}"
            f" | {mins:.0f} 分后开场 | 挂单人 {self.seller_name}"
        )


class AuctionEngine:
    @staticmethod
    def _load_open() -> List[AuctionLot]:
        from storage.db import AuctionLotRepository

        lots = AuctionLotRepository.list_all()
        return [l for l in lots if l.is_open()]

    @staticmethod
    def settle_expired(now: Optional[float] = None) -> List[str]:
        """结算到期拍卖；返回可读摘要列表"""
        t = now if now is not None else time.time()
        notes: List[str] = []
        from storage.db import AuctionLotRepository, CharacterRepository, ChronicleRepository

        for lot in AuctionLotRepository.list_all():
            if lot.status != AuctionStatus.OPEN:
                continue
            if t < lot.ends_at:
                continue
            if lot.bid_count <= 0:
                lot.status = AuctionStatus.EXPIRED
                if lot.source == "system":
                    # F05 系统场次：流拍即宝库收回，物品消散，不回任何人行囊
                    AuctionLotRepository.save(lot)
                    notes.append(
                        f"【流拍】#{lot.id}【{lot.item_name}】无人应价，{AUCTION_HOUSE_NAME}收回，拍品消散于虚空。"
                    )
                else:
                    seller = _find_by_id_or_user(lot.seller_id, lot.seller_user_id)
                    if seller:
                        _give_item(seller, lot.item_name, 1, lot.kind)
                        CharacterRepository.save(seller)
                    AuctionLotRepository.save(lot)
                    notes.append(
                        f"【流拍】#{lot.id}【{lot.item_name}】无人应价，"
                        + (f"已退回【{lot.seller_name}】。" if seller else "但挂单人已不在，拍品消散于虚空。")
                    )
            else:
                lot.status = AuctionStatus.SOLD
                fee = max(0, int(lot.current_bid * AUCTION_SETTLE_FEE_RATE))
                net = lot.current_bid - fee
                seller = _find_by_id_or_user(lot.seller_id, lot.seller_user_id)
                leader = _find_by_id_or_user(lot.leader_id or "", lot.leader_user_id or "")
                if lot.source == "system":
                    # F05 系统场次：卖家为宝库伪主体，成交款全额沉淀（不付款、不抽成拆分）
                    fee = 0
                    net = 0
                elif seller:
                    seller.spirit_stones += net
                    CharacterRepository.save(seller)
                if leader:
                    _give_item(leader, lot.item_name, 1, lot.kind)
                    CharacterRepository.save(leader)
                AuctionLotRepository.save(lot)
                if lot.source == "system":
                    notes.append(
                        f"【落槌】#{lot.id}【{lot.item_name}】以 {lot.current_bid} 灵石归【{lot.leader_name}】"
                        f"（系统场次，成交款全额归天道沉淀）。"
                    )
                else:
                    notes.append(
                        f"【落槌】#{lot.id}【{lot.item_name}】以 {lot.current_bid} 灵石归【{lot.leader_name}】，"
                        f"卖家实收 {net}（手续费 {fee}）。"
                        + ("" if seller and leader else "（有当事人不在世，账目已尽天道所能）")
                    )
                try:
                    from core import ai_flavor

                    shout = ai_flavor.polish_auction_settle(
                        lot.item_name, lot.leader_name or "", lot.current_bid, lot.seller_name, "落槌"
                    )
                    if shout:
                        notes[-1] += f"\n司仪：「{shout}」"
                except Exception:
                    pass
            try:
                ChronicleRepository.record("AUCTION", lot.seller_name, notes[-1][:80])
                from core import rumors

                if lot.status == AuctionStatus.SOLD and lot.leader_name:
                    rumors.note_auction(lot.leader_name, lot.item_name, lot.current_bid)
                    try:
                        from config import CHANNEL_AUCTION_MIN_PRICE
                        from core.world_channel import WorldChannel

                        if lot.current_bid >= CHANNEL_AUCTION_MIN_PRICE:
                            WorldChannel.post(
                                "auction",
                                f"【落槌】{lot.item_name} 归 {lot.leader_name}，{lot.current_bid} 灵石。",
                                level="major",
                                actor=lot.leader_name,
                            )
                    except Exception:
                        pass
            except Exception:
                pass
        return notes

    # ---------- F05：状态机推进（惰性） ----------

    @staticmethod
    def advance(
        now: Optional[float] = None,
        rng: Optional[Any] = None,
        react: bool = False,
    ) -> List[str]:
        """惰性推进拍卖状态机：系统场次排期 → 待开场晋升 → 到期结算 →（react 时）NPC 跟价。

        所有指令入口都先调本函数（react=False 只做排期/晋升/结算，保既有路径行为不变）；
        看板与世界 tick 以 react=True 调用，NPC 才会在推进点跟价。不新造常驻线程。
        返回本次推进产生的摘要行（晋升/落槌/流拍/跟价）。
        """
        t = now if now is not None else time.time()
        notes: List[str] = []
        notes += AuctionEngine._seed_system_lot(t)
        notes += AuctionEngine._promote_pending(t)
        notes += AuctionEngine.settle_expired(t)
        if react:
            for lot in AuctionEngine._load_open():
                if t < lot.ends_at:
                    res = AuctionEngine.npc_maybe_bid(lot, now=t, rng=rng)
                    if res and res.get("success"):
                        notes.append(res["message_note"])
        return notes

    @staticmethod
    def _seed_system_lot(t: float) -> List[str]:
        """系统场次排期：到期且无在场系统拍品时，生成一张 PENDING 宝库拍品（惰性）"""
        from storage.db import AuctionLotRepository, WorldStateRepository

        lots = AuctionLotRepository.list_all()
        if any(
            l.source == "system" and l.status in (AuctionStatus.PENDING, AuctionStatus.OPEN)
            for l in lots
        ):
            return []
        next_at = WorldStateRepository.get("auction_next_system_at")
        if next_at is None:
            # 首次：只立排期，不立即生成（避免任意一次调用凭空开场）
            WorldStateRepository.set(
                "auction_next_system_at", t + AUCTION_SYSTEM_INTERVAL_SECONDS
            )
            return []
        if t < float(next_at):
            return []
        seq = int(WorldStateRepository.get("auction_system_seq", 0) or 0)
        item = AUCTION_SYSTEM_ITEMS[seq % len(AUCTION_SYSTEM_ITEMS)]
        from core.market import MarketEngine

        price = MarketEngine.market_price(item)
        start = max(10, int(price * AUCTION_SYSTEM_START_RATE))
        buyout = max(start + 1, int(price * 1.25))
        cfg = ITEM_CATALOG.get(item) or {}
        lot = AuctionLot(
            seller_id=AUCTION_HOUSE_ID,
            seller_user_id="",
            seller_name=AUCTION_HOUSE_NAME,
            item_name=item,
            kind=cfg.get("kind", "material"),
            start_price=start,
            buyout_price=buyout,
            current_bid=0,
            ends_at=0.0,
            created_at=t,
            starts_at=t + AUCTION_SYSTEM_LEAD_SECONDS,
            status=AuctionStatus.PENDING,
            source="system",
        )
        AuctionLotRepository.save(lot)
        WorldStateRepository.set("auction_next_system_at", t + AUCTION_SYSTEM_INTERVAL_SECONDS)
        WorldStateRepository.set("auction_system_seq", seq + 1)
        return [
            f"【拍卖预告】{AUCTION_HOUSE_NAME}将于 {AUCTION_SYSTEM_LEAD_SECONDS // 60} 分钟后"
            f"开场拍【{item}】，起拍 {start} 灵石（一口价 {buyout}）。"
        ]

    @staticmethod
    def _promote_pending(t: float) -> List[str]:
        """PENDING 待开场 → OPEN 竞拍中（ends_at 以 starts_at 为锚，久未查看也可能晋升即到期）"""
        from storage.db import AuctionLotRepository

        notes: List[str] = []
        for lot in AuctionLotRepository.list_all():
            if lot.status == AuctionStatus.PENDING and t >= lot.starts_at:
                lot.status = AuctionStatus.OPEN
                lot.ends_at = lot.starts_at + AUCTION_DURATION_MIN * 60.0
                AuctionLotRepository.save(lot)
                notes.append(
                    f"【开场】#{lot.id}【{lot.item_name}】竞拍开始，起拍 {lot.start_price} 灵石，"
                    f"{AUCTION_DURATION_MIN} 分钟后落槌。"
                )
        return notes

    @staticmethod
    def open_lots(now: Optional[float] = None) -> List[AuctionLot]:
        """当前可出价的 OPEN 拍品（供 /出价 无编号时解析）"""
        AuctionEngine.advance(now=now, react=False)
        t = now if now is not None else time.time()
        return [l for l in AuctionEngine._load_open() if t < l.ends_at]

    # ---------- F05：NPC 规则跟价 ----------

    @staticmethod
    def floor_price(lot: AuctionLot) -> int:
        """当前合法最低出价：无出价=起拍价；有出价=现价 + max(最低加价, 5%) 步长"""
        if not lot.bid_count:
            return lot.start_price
        step = max(AUCTION_MIN_INCREMENT, int(lot.current_bid * 0.05))
        return lot.current_bid + step

    @staticmethod
    def _apply_bid(lot: AuctionLot, bidder: Character, amount: int) -> Optional[str]:
        """出价落账单点（玩家 bid 与 NPC 跟价共用）：退上一领先者 → 扣款 → 更新领先 → 落库。

        调用方须已完成全部校验（状态/地板价/余额/身份）。返回上一领先者名（无则 None）。
        """
        from storage.db import AuctionLotRepository, CharacterRepository

        prev_name = lot.leader_name
        if lot.leader_id and lot.bid_count > 0:
            prev = CharacterRepository.get_by_id(lot.leader_id)
            if prev:
                prev.spirit_stones += lot.current_bid
                CharacterRepository.save(prev)
        bidder.spirit_stones -= amount
        lot.current_bid = amount
        lot.leader_id = bidder.id
        lot.leader_user_id = bidder.user_id
        lot.leader_name = bidder.name
        lot.bid_count += 1
        AuctionLotRepository.save(lot)
        CharacterRepository.save(bidder)
        return prev_name

    @staticmethod
    def npc_cap(lot: AuctionLot, npc: Character) -> int:
        """NPC 对该拍品的出价上限：min(自身灵石, 市价 × CAP 倍率 × 确定性意愿系数)。

        意愿系数由 crc32(lot:npc) 导出 ∈ [0.85, 1.24]，同场同 NPC 恒定，不随刷新漂移 → 不会无限抬价。
        """
        from core.market import MarketEngine

        base = MarketEngine.market_price(lot.item_name)
        will = 0.85 + (zlib.crc32(f"{lot.id}:{npc.id}".encode("utf-8")) % 40) / 100.0
        return min(int(npc.spirit_stones), int(base * AUCTION_NPC_CAP_MULT * will))

    @staticmethod
    def npc_maybe_bid(
        lot: AuctionLot,
        now: Optional[float] = None,
        rng: Optional[Any] = None,
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """一名 NPC 按规则跟价一口（纯规则，不调 AI；走 NPC 真实灵石账）。

        触发概率 AUCTION_NPC_BID_CHANCE（force=True 跳过概率门，供测试/定向推进）；
        出价恒为合法地板价（达一口价则直接落槌）；无合格 NPC 或上限不够地板价时返回 None。
        """
        t = now if now is not None else time.time()
        if lot.status != AuctionStatus.OPEN or t >= lot.ends_at:
            return None
        r = rng if rng is not None else random
        if not force and r.random() > AUCTION_NPC_BID_CHANCE:
            return None
        floor = AuctionEngine.floor_price(lot)
        from core.npc_mind import _is_npc
        from storage.db import CharacterRepository

        cands: List[Character] = []
        for c in CharacterRepository.list_all_alive():
            if not _is_npc(c):
                continue
            if c.id == lot.seller_id or c.id == lot.leader_id:
                continue
            if AuctionEngine.npc_cap(lot, c) >= floor:
                cands.append(c)
        if not cands:
            return None
        npc = r.choice(cands)
        amount = floor
        if lot.buyout_price and amount >= lot.buyout_price:
            amount = lot.buyout_price
            AuctionEngine._apply_bid(lot, npc, amount)
            AuctionEngine._settle_buyout(lot, npc)
            return {
                "success": True,
                "npc": npc,
                "amount": amount,
                "buyout": True,
                "message_note": (
                    f"【NPC 落槌】{npc.name} 以一口价 {amount} 灵石拍下 #{lot.id}【{lot.item_name}】。"
                ),
            }
        AuctionEngine._apply_bid(lot, npc, amount)
        return {
            "success": True,
            "npc": npc,
            "amount": amount,
            "buyout": False,
            "message_note": (
                f"【NPC 跟价】{npc.name} 出价 {amount} 灵石，暂领先 #{lot.id}【{lot.item_name}】。"
            ),
        }

    @staticmethod
    def board(now: Optional[float] = None, rng: Optional[Any] = None) -> Dict[str, Any]:
        notes = AuctionEngine.advance(now=now, rng=rng, react=True)
        t = now if now is not None else time.time()
        from storage.db import AuctionLotRepository

        all_lots = AuctionLotRepository.list_all()
        pending = sorted(
            [l for l in all_lots if l.status == AuctionStatus.PENDING],
            key=lambda x: x.starts_at,
        )
        lots = [l for l in AuctionEngine._load_open() if t < l.ends_at]
        lots.sort(key=lambda x: x.ends_at)
        lines = [
            "【拍卖行】限时竞价；/拍 <编号> <出价> · /出价 <金额>（单场直拍）"
            " · /一口 <编号> · /上拍 <货> <底价> [一口价]"
        ]
        for n in notes:
            lines.append("· " + n)
        if not pending and not lots:
            lines.append("（当前无进行中的拍品）")
        if pending:
            lines.append("— 待开场 —")
            for l in pending:
                lines.append("· " + l.pending_line(t))
        if lots:
            lines.append("— 竞拍中 —")
            for l in lots:
                lines.append("· " + l.board_line(t))
        return {"success": True, "message": "\n".join(lines), "lots": lots}

    @staticmethod
    def list_item(
        seller: Character,
        item_name: str,
        start_price: int,
        buyout_price: Optional[int] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        AuctionEngine.advance(now=now, react=False)
        t = now if now is not None else time.time()
        ok, reason = can_use_market(seller, t)
        if not ok:
            return {"success": False, "message": reason}
        if start_price <= 0:
            return {"success": False, "message": "起拍价必须为正。"}
        if buyout_price is not None and buyout_price < start_price:
            return {"success": False, "message": "一口价不可低于起拍价。"}
        from storage.db import AuctionLotRepository, CharacterRepository

        open_n = sum(1 for l in AuctionLotRepository.list_all() if l.is_open() and l.seller_id == seller.id)
        if open_n >= AUCTION_MAX_LOTS:
            return {"success": False, "message": f"同时上拍上限 {AUCTION_MAX_LOTS}，请先 /撤拍。"}

        cfg = ITEM_CATALOG.get(item_name)
        kind = cfg["kind"] if cfg else "material"
        if not _take_item(seller, item_name, 1):
            return {"success": False, "message": f"随身并无【{item_name}】可上拍。"}

        lot = AuctionLot(
            seller_id=seller.id,
            seller_user_id=seller.user_id,
            seller_name=seller.name,
            item_name=item_name,
            kind=kind,
            start_price=start_price,
            buyout_price=buyout_price,
            current_bid=0,
            ends_at=t + AUCTION_DURATION_MIN * 60.0,
            created_at=t,
            status=AuctionStatus.OPEN,
        )
        AuctionLotRepository.save(lot)
        CharacterRepository.save(seller)
        buy_s = f"，一口价 {buyout_price}" if buyout_price else ""
        return {
            "success": True,
            "lot": lot,
            "message": (
                f"【上拍成功】#{lot.id}【{item_name}】起拍 {start_price}{buy_s}，"
                f"{AUCTION_DURATION_MIN} 分钟后落槌。"
            ),
        }

    @staticmethod
    def cancel(seller: Character, lot_id: str) -> Dict[str, Any]:
        AuctionEngine.advance(react=False)
        from storage.db import AuctionLotRepository, CharacterRepository

        lot = AuctionEngine._find(lot_id)
        if not lot:
            return {"success": False, "message": "拍品编号不存在。"}
        if lot.seller_id != seller.id:
            return {"success": False, "message": "非本人拍品。"}
        if lot.status != AuctionStatus.OPEN:
            return {"success": False, "message": "此拍品已结束。"}
        if lot.bid_count > 0:
            return {"success": False, "message": "已有出价，不可撤拍。"}
        lot.status = AuctionStatus.CANCELLED
        seller.inventory.append(lot.item_name)
        AuctionLotRepository.save(lot)
        CharacterRepository.save(seller)
        return {"success": True, "message": f"【撤拍】收回【{lot.item_name}】。"}

    @staticmethod
    def bid(buyer: Character, lot_id: str, amount: int, now: Optional[float] = None) -> Dict[str, Any]:
        AuctionEngine.advance(now=now, react=False)
        t = now if now is not None else time.time()
        ok, reason = can_use_market(buyer, t)
        if not ok:
            return {"success": False, "message": reason}
        lot = AuctionEngine._find(lot_id)
        if not lot:
            return {"success": False, "message": "拍品编号不存在。"}
        if lot.status == AuctionStatus.PENDING:
            return {"success": False, "message": "此拍品尚未开场，请看 /拍卖行 的待开场预告。"}
        if lot.status != AuctionStatus.OPEN or t >= lot.ends_at:
            return {"success": False, "message": "此拍品已结束。"}
        if lot.seller_id == buyer.id:
            return {"success": False, "message": "不可拍自己的货。"}
        if lot.leader_id == buyer.id:
            return {"success": False, "message": "你已是领先者。"}

        floor = AuctionEngine.floor_price(lot)
        if amount < floor:
            return {
                "success": False,
                "message": f"出价须 ≥ {floor}（当前 {lot.current_bid or lot.start_price}，步长规则见 /拍卖行）。",
            }
        if buyer.spirit_stones < amount:
            return {"success": False, "message": f"囊中仅有 {buyer.spirit_stones} 灵石。"}

        # 落账单点（退上一领先者 → 扣款 → 更新领先 → 落库），与 NPC 跟价共用
        AuctionEngine._apply_bid(lot, buyer, amount)

        # 一口价落槌
        if lot.buyout_price and amount >= lot.buyout_price:
            return AuctionEngine._settle_buyout(lot, buyer)

        shout = ""
        try:
            from core import ai_flavor

            shout = ai_flavor.polish_auction_bid(
                buyer.name, lot.item_name, amount, prev_leader="", buyout=lot.buyout_price or 0
            ) or ""
        except Exception:
            shout = ""
        msg = (
            f"【竞价】你以 {amount} 灵石领先 #{lot.id}【{lot.item_name}】。"
            f"若被超价将自动退回。"
        )
        if shout:
            msg += f"\n司仪：「{shout}」"
        return {
            "success": True,
            "message": msg,
            "lot": lot,
        }

    @staticmethod
    def buyout(buyer: Character, lot_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        AuctionEngine.advance(now=now, react=False)
        t = now if now is not None else time.time()
        ok, reason = can_use_market(buyer, t)
        if not ok:
            return {"success": False, "message": reason}
        lot = AuctionEngine._find(lot_id)
        if not lot:
            return {"success": False, "message": "拍品编号不存在。"}
        if lot.status == AuctionStatus.PENDING:
            return {"success": False, "message": "此拍品尚未开场，请看 /拍卖行 的待开场预告。"}
        if lot.status != AuctionStatus.OPEN or t >= lot.ends_at:
            return {"success": False, "message": "此拍品已结束。"}
        if not lot.buyout_price:
            return {"success": False, "message": "此拍未设一口价。"}
        if lot.seller_id == buyer.id:
            return {"success": False, "message": "不可买自己的货。"}

        from storage.db import CharacterRepository

        price = lot.buyout_price
        # 先算买方净支付（若自己是领先者，退回已出价后再比一口价）
        effective = price
        if lot.leader_id == buyer.id and lot.bid_count > 0:
            effective = price - lot.current_bid
        if buyer.spirit_stones < effective:
            return {
                "success": False,
                "message": f"一口价 {price}，需再付 {effective}，囊中仅有 {buyer.spirit_stones}。",
            }

        # 退款原领先者（校验通过后再动账）
        if lot.leader_id and lot.bid_count > 0:
            if lot.leader_id == buyer.id:
                buyer.spirit_stones += lot.current_bid
            else:
                prev = CharacterRepository.get_by_id(lot.leader_id)
                if prev:
                    prev.spirit_stones += lot.current_bid
                    CharacterRepository.save(prev)
        buyer.spirit_stones -= price
        lot.current_bid = price
        lot.leader_id = buyer.id
        lot.leader_user_id = buyer.user_id
        lot.leader_name = buyer.name
        lot.bid_count += 1
        return AuctionEngine._settle_buyout(lot, buyer)

    @staticmethod
    def _settle_buyout(lot: AuctionLot, buyer: Character) -> Dict[str, Any]:
        from storage.db import AuctionLotRepository, CharacterRepository, ChronicleRepository

        lot.status = AuctionStatus.SOLD
        fee = max(0, int(lot.current_bid * AUCTION_SETTLE_FEE_RATE))
        net = lot.current_bid - fee
        seller = _find_by_id_or_user(lot.seller_id, lot.seller_user_id)
        if seller:
            seller.spirit_stones += net
            CharacterRepository.save(seller)
        _give_item(buyer, lot.item_name, 1, lot.kind)
        AuctionLotRepository.save(lot)
        CharacterRepository.save(buyer)
        try:
            ChronicleRepository.record(
                "AUCTION",
                buyer.name,
                f"一口价购得#{lot.id}【{lot.item_name}】{lot.current_bid}灵石",
            )
        except Exception:
            pass
        shout = ""
        try:
            from core import ai_flavor

            shout = ai_flavor.polish_auction_settle(
                lot.item_name, buyer.name, lot.current_bid, lot.seller_name, "一口价成交"
            ) or ""
        except Exception:
            shout = ""
        msg = (
            f"【一口价成交】#{lot.id}【{lot.item_name}】以 {lot.current_bid} 灵石归你。"
            f"卖家实收 {net}。"
        )
        if shout:
            msg += f"\n司仪：「{shout}」"
        return {
            "success": True,
            "message": msg,
            "lot": lot,
        }

    @staticmethod
    def _find(lot_id: str) -> Optional[AuctionLot]:
        from storage.db import AuctionLotRepository

        lid = (lot_id or "").lstrip("#")
        for l in AuctionLotRepository.list_all():
            if l.id == lid:
                return l
        return None
