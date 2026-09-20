"""
坊市：商会货单、寄存金库、玩家挂单撮合
"""
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import (
    ITEM_CATALOG,
    MARKET_DEPOSIT_FEE_RATE,
    MARKET_WITHDRAW_FEE_RATE,
    MARKET_SELL_BACK_RATE,
    MARKET_LISTING_FEE_RATE,
    MARKET_MAX_LISTINGS,
)
from core.models import Character, CharacterStatus


class ListingStatus(str, Enum):
    OPEN = "OPEN"
    SOLD = "SOLD"
    CANCELLED = "CANCELLED"


class MarketListing(BaseModel):
    """玩家寄售挂单（天道契约担保）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    seller_id: str
    seller_name: str
    item_name: str
    kind: str = "material"
    price: int
    status: ListingStatus = ListingStatus.OPEN
    created_at: float = 0.0

    def is_open(self) -> bool:
        return self.status == ListingStatus.OPEN


class MarketEngine:
    """坊市裁决引擎"""

    # ---------------- 商会货单 ----------------
    @staticmethod
    def catalog() -> List[Dict[str, Any]]:
        out = []
        for name, cfg in ITEM_CATALOG.items():
            out.append({
                "name": name,
                "kind": cfg["kind"],
                "price": cfg["price"],
                "desc": cfg["desc"],
            })
        # 高价在后
        out.sort(key=lambda x: x["price"])
        return out

    @staticmethod
    def buy_from_guild(buyer: Character, item_name: str, qty: int = 1) -> Dict[str, Any]:
        cfg = ITEM_CATALOG.get(item_name)
        if not cfg:
            return {"success": False, "message": f"商会并无【{item_name}】此货。输入 /坊市 查看货单。"}
        if qty < 1:
            return {"success": False, "message": "购买数量至少为 1。"}

        unit = cfg["price"]
        total = unit * qty
        if buyer.spirit_stones < total:
            return {
                "success": False,
                "message": f"【{item_name}】单价 {unit} 灵石，买 {qty} 件需 {total}，囊中仅有 {buyer.spirit_stones}。",
            }

        if buyer.status == CharacterStatus.DEAD:
            return {"success": False, "message": "死人不可逛坊市。"}

        buyer.spirit_stones -= total

        applied_msg = ""
        if cfg["kind"] == "array":
            for _ in range(qty):
                if item_name not in buyer.arrays:
                    buyer.arrays.append(item_name)
                else:
                    buyer.inventory.append(item_name)
            applied_msg = f"阵盘已入储物袋（随身阵盘：{'、'.join(buyer.arrays) or '无'}）。"
        elif cfg["kind"] == "pill":
            for _ in range(qty):
                buyer.inventory.append(item_name)
            applied_msg = "丹药收入囊中，可用 /服用 <丹药名>。"
        else:
            for _ in range(qty):
                buyer.inventory.append(item_name)
            applied_msg = "材料已收入囊中，可 /出售 给商会或 /寄售 挂单。"
        shout = ""
        try:
            from core import ai_flavor

            shout = ai_flavor.polish_guild_deal(buyer.name, "购入", item_name, qty, total) or ""
        except Exception:
            shout = ""
        msg = f"【商会成交】购入【{item_name}】×{qty}，付灵石 {total}。\n{applied_msg}"
        if shout:
            msg += f"\n伙计：「{shout}」"
        return {
            "success": True,
            "item_name": item_name,
            "qty": qty,
            "total": total,
            "message": msg,
        }

    @staticmethod
    def sell_to_guild(seller: Character, item_name: str, qty: int = 1) -> Dict[str, Any]:
        cfg = ITEM_CATALOG.get(item_name, {"kind": "material", "price": 20})
        unit_back = max(1, int(cfg["price"] * MARKET_SELL_BACK_RATE))

        # 优先卖随身杂物，其次阵盘
        have_inv = seller.inventory.count(item_name)
        have_arr = seller.arrays.count(item_name) if cfg.get("kind") == "array" else 0
        # 材料/丹药也可从 inventory 卖
        if have_inv + have_arr < qty:
            return {
                "success": False,
                "message": f"随身并无足够的【{item_name}】（有 {have_inv + have_arr} 件）。",
            }

        left = qty
        # 先扣 inventory
        while left > 0 and item_name in seller.inventory:
            seller.inventory.remove(item_name)
            left -= 1
        # 阵盘再扣 arrays
        while left > 0 and item_name in seller.arrays:
            seller.arrays.remove(item_name)
            left -= 1

        gain = unit_back * qty
        seller.spirit_stones += gain
        return {
            "success": True,
            "gain": gain,
            "message": (
                f"【商会回收】售出【{item_name}】×{qty}，得灵石 {gain}"
                f"（回收价约为标价 {int(MARKET_SELL_BACK_RATE * 100)}%）。"
            ),
        }

    @staticmethod
    def use_pill(user: Character, item_name: str) -> Dict[str, Any]:
        cfg = ITEM_CATALOG.get(item_name)
        if not cfg or cfg["kind"] != "pill":
            return {"success": False, "message": f"【{item_name}】不是可服用的丹药。"}
        if item_name not in user.inventory:
            return {"success": False, "message": f"囊中并无【{item_name}】。"}
        if item_name in user.used_pills:
            return {"success": False, "message": f"【{item_name}】本世已服过，再服无益（天道有常）。"}

        user.inventory.remove(item_name)
        user.used_pills.append(item_name)

        if item_name == "筑基丹":
            user.skills.append("筑基丹药力(待渡劫)")
            return {
                "success": True,
                "message": "服下【筑基丹】，药力沉入丹田，下次筑基天劫成功率提升（由突破引擎结算）。",
            }
        # 读货单品阶与倍率；无表则按名称回退
        grade = cfg.get("grade") or "凡品"
        mult = cfg.get("pill_exp_mult")
        if mult is None:
            mult = 0.15 if item_name == "聚气丹" else 0.08
        mult = max(0.0, min(1.0, float(mult)))
        user.pill_exp_mult = max(user.pill_exp_mult, mult)
        user.pill_exp_note = f"{item_name}·{grade}"
        heal = float(cfg.get("heal_lifespan") or 0.0)
        heal_msg = ""
        if heal > 0:
            user.lifespan.add_lifespan(heal)
            heal_msg = f"\n寿元 +{heal:.0f} 岁。"
        return {
            "success": True,
            "message": (
                f"服下【{grade}·{item_name}】，药力沉入丹田。"
                f"{heal_msg}\n下次闭关修为 +{int(mult * 100)}%，出关后药力耗尽。"
            ),
        }

    # ---------------- 坊市寄存（金库） ----------------
    @staticmethod
    def deposit_stones(c: Character, amount: int) -> Dict[str, Any]:
        """随身灵石存入坊市金库：不可被夺、不可被查抄"""
        from core.protection import ProtectionEngine

        ok, reason = ProtectionEngine.can_transfer_assets(c)
        if not ok:
            return {"success": False, "message": reason}

        if amount <= 0:
            return {"success": False, "message": "寄存数量必须为正。"}
        if c.spirit_stones < amount:
            return {"success": False, "message": f"随身仅有 {c.spirit_stones} 灵石，不足寄存 {amount}。"}

        fee = max(0, int(amount * MARKET_DEPOSIT_FEE_RATE))
        # 手续费从存入额外扣还是从存入额里扣？外扣更符合「保管费」
        if c.spirit_stones < amount + fee:
            return {
                "success": False,
                "message": (
                    f"寄存 {amount} 灵石需另付保管费 {fee}"
                    f"（合计 {amount + fee}），囊中仅有 {c.spirit_stones}。"
                ),
            }

        c.spirit_stones -= (amount + fee)
        c.vault_stones += amount
        return {
            "success": True,
            "fee": fee,
            "deposited": amount,
            "message": (
                f"【坊市寄存】存入金库 {amount} 灵石，付保管费 {fee}。\n"
                f"寄存之物受天道契约庇护，杀人夺宝与查抄皆不可及；"
                f"庇护中的随身财货不可再转入（防下线保险库滥用——请在安全时寄存）。\n"
                f"当前金库：{c.vault_stones} 灵石 | 随身：{c.spirit_stones} 灵石"
            ),
        }

    @staticmethod
    def withdraw_stones(c: Character, amount: int) -> Dict[str, Any]:
        from core.protection import ProtectionEngine

        ok, reason = ProtectionEngine.can_transfer_assets(c)
        if not ok:
            return {"success": False, "message": reason}

        if amount <= 0:
            return {"success": False, "message": "取出数量必须为正。"}
        if c.vault_stones < amount:
            return {"success": False, "message": f"金库仅有 {c.vault_stones} 灵石。"}
        fee = max(0, int(amount * MARKET_WITHDRAW_FEE_RATE))
        c.vault_stones -= amount
        c.spirit_stones += (amount - fee)
        return {
            "success": True,
            "fee": fee,
            "withdrawn": amount,
            "message": (
                f"【坊市支取】自金库取出 {amount} 灵石"
                + (f"（手续费 {fee}）" if fee else "")
                + f"。\n当前金库：{c.vault_stones} | 随身：{c.spirit_stones}"
            ),
        }

    # ---------------- 玩家挂单 ----------------
    @staticmethod
    def list_item(
        seller: Character,
        item_name: str,
        price: int,
        kind_hint: str = "",
    ) -> Tuple[Optional[MarketListing], Dict[str, Any]]:
        if price <= 0:
            return None, {"success": False, "message": "挂单价格必须为正。"}

        cfg = ITEM_CATALOG.get(item_name)
        kind = cfg["kind"] if cfg else (kind_hint or "material")

        # 从随身扣除（优先 inventory，阵盘也可挂）
        removed = False
        if item_name in seller.inventory:
            seller.inventory.remove(item_name)
            removed = True
        elif item_name in seller.arrays:
            seller.arrays.remove(item_name)
            removed = True

        if not removed:
            return None, {"success": False, "message": f"随身并无【{item_name}】可挂。"}

        fee = max(1, int(price * MARKET_LISTING_FEE_RATE))
        if seller.spirit_stones < fee:
            # 退回物品
            if kind == "array":
                seller.arrays.append(item_name)
            else:
                seller.inventory.append(item_name)
            return None, {
                "success": False,
                "message": f"挂单手续费 {fee} 灵石不足，已退回货物。",
            }

        seller.spirit_stones -= fee
        listing = MarketListing(
            seller_id=seller.id,
            seller_name=seller.name,
            item_name=item_name,
            kind=kind,
            price=price,
            status=ListingStatus.OPEN,
            created_at=time.time(),
        )
        return listing, {
            "success": True,
            "fee": fee,
            "message": (
                f"【寄售上架】【{item_name}】标价 {price} 灵石，手续费 {fee}。\n"
                f"天道契约担保：成交后货款自动入卖家金库/随身，防跑单。"
            ),
        }

    @staticmethod
    def cancel_listing(
        seller: Character,
        listing: MarketListing,
    ) -> Dict[str, Any]:
        if listing.seller_id != seller.id:
            return {"success": False, "message": "非本人挂单，不可撤回。"}
        if listing.status != ListingStatus.OPEN:
            return {"success": False, "message": f"此单状态为 {listing.status.value}，无法撤回。"}

        listing.status = ListingStatus.CANCELLED
        # 退回货物
        if listing.kind == "array":
            seller.arrays.append(listing.item_name)
        else:
            seller.inventory.append(listing.item_name)
        return {
            "success": True,
            "message": f"【撤单】收回寄售【{listing.item_name}】。",
        }

    @staticmethod
    def buy_listing(buyer: Character, listing: MarketListing) -> Dict[str, Any]:
        if listing.status != ListingStatus.OPEN:
            return {"success": False, "message": "此单已不在售。"}
        if listing.seller_id == buyer.id:
            return {"success": False, "message": "不可买回自己的挂单。"}
        if buyer.spirit_stones < listing.price:
            return {
                "success": False,
                "message": f"标价 {listing.price}，囊中仅有 {buyer.spirit_stones}。",
            }

        buyer.spirit_stones -= listing.price
        listing.status = ListingStatus.SOLD

        if listing.kind == "array":
            buyer.arrays.append(listing.item_name)
        else:
            buyer.inventory.append(listing.item_name)

        return {
            "success": True,
            "price": listing.price,
            "seller_id": listing.seller_id,
            "seller_name": listing.seller_name,
            "message": (
                f"【契约成交】购得【{listing.item_name}】，付 {listing.price} 灵石。\n"
                f"货款将由天道结算给卖家【{listing.seller_name}】。"
            ),
        }

    @staticmethod
    def complete_sale_payment(listing: MarketListing, seller: Optional[Character]) -> Optional[int]:
        """把货款付给卖家（卖家可能已不在场，调用方处理）"""
        if listing.status != ListingStatus.SOLD:
            return None
        if seller is not None:
            seller.spirit_stones += listing.price
        return listing.price

    @staticmethod
    def open_listings(all_listings: List[MarketListing]) -> List[MarketListing]:
        open_ = [l for l in all_listings if l.is_open()]
        open_.sort(key=lambda x: x.price)
        return open_
