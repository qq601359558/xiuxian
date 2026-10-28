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
from core.items import ItemEntity, ItemFactory
from core.character_integrity import CharacterIntegrity, CharacterIntegrityError


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
    item_entity: Optional[ItemEntity] = None  # Core-V2 实体道具（保留词缀与宝图专属元数据）

    def is_open(self) -> bool:
        return self.status == ListingStatus.OPEN


class MarketEngine:
    """坊市裁决引擎"""

    # ---------------- 商会货单 ----------------
    @staticmethod
    def catalog() -> List[Dict[str, Any]]:
        out = []
        for name, cfg in ITEM_CATALOG.items():
            if cfg.get("kind") == "map" or cfg.get("npc_sell") is False:
                continue  # 天地机缘之物，商会无从兜售
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
        if cfg.get("kind") == "map" or cfg.get("npc_sell") is False:
            return {"success": False, "message": "此乃天地造化机缘之物，商会无从兜售，需亲自探险发掘或于玩家处求购。"}
        if qty < 1:
            return {"success": False, "message": "购买数量至少为 1。"}

        unit = cfg["price"]
        # M4：坊市恐慌买价
        try:
            from core.player_echo import market_buy_mult

            unit = max(1, int(round(unit * market_buy_mult())))
        except Exception:
            pass
        total = unit * qty
        try:
            CharacterIntegrity.assert_alive(buyer)
            CharacterIntegrity.assert_bag_space(buyer, qty)
            CharacterIntegrity.assert_currency(buyer, total)
        except CharacterIntegrityError as e:
            return {"success": False, "message": str(e)}

        CharacterIntegrity.deduct_currency(buyer, total)

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
        # M4：恐慌压回收价
        try:
            from core.player_echo import market_sell_mult

            unit_back = max(1, int(round(unit_back * market_sell_mult())))
        except Exception:
            pass

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
        raw_name = (item_name or "").strip()
        if not raw_name:
            return {"success": False, "message": "用法：/服用 <丹药名>"}

        from core.items import ItemKind

        # 1. 检索道具实体（Core-V2 一等公民）
        entity = user.find_item(raw_name)
        target_name = entity.name if entity else raw_name

        # 2. 若实体未找到，在 legacy inventory 中做模糊匹配
        if not entity:
            if target_name not in user.inventory:
                for x in user.inventory:
                    if target_name in x or x in target_name:
                        target_name = x
                        entity = user.find_item(target_name)
                        break

        # 3. 校验囊中是否持有
        if not entity and target_name not in user.inventory:
            return {"success": False, "message": f"囊中并无【{raw_name}】。"}

        cfg = ITEM_CATALOG.get(target_name) or {}

        # 装备防护拦截：若道具本身是法宝装备或已佩戴在身，坚决禁止当丹药服食
        if (entity and entity.kind == ItemKind.EQUIP) or cfg.get("kind") == "equip":
            return {"success": False, "message": f"【{target_name}】乃护道法宝，不可服食入腹！"}
        if target_name in getattr(user, "equipped", []):
            return {"success": False, "message": f"【{target_name}】已佩戴在身，不可服食！"}

        is_entity_pill = entity is not None and entity.kind in (ItemKind.PILL, ItemKind.CONSUMABLE)
        is_cfg_pill = cfg.get("kind") == "pill"
        is_name_pill = any(w in target_name for w in ("丹", "露", "丸", "液", "散", "膏", "琼浆", "灵酿"))

        if not is_entity_pill and not is_cfg_pill and not is_name_pill:
            return {"success": False, "message": f"【{target_name}】不是可服用的丹药或灵露。"}

        # 4. 特殊进阶大丹限服规则（如聚气丹、玄元聚气丹、九转凝灵丹防重复嗑药）
        one_time_pills = {"聚气丹", "玄元聚气丹", "九转凝灵丹"}
        if target_name in one_time_pills and target_name in user.used_pills:
            return {"success": False, "message": f"【{target_name}】本世已服过，再服无益（天道有常）。"}

        # 5. 原子扣减道具实体与行囊记录
        if entity:
            user.remove_item_entity(entity.uid)
        else:
            if target_name in user.inventory:
                user.inventory.remove(target_name)
        user.used_pills.append(target_name)

        tier = entity.tier if entity else (cfg.get("tier") or 1)
        grade = (entity.tier_name if entity else None) or cfg.get("grade") or (
            ["凡品", "人品", "地品", "天品", "仙品"][min(4, max(0, tier - 1))]
        )

        # 6. 特殊丹药药效专精
        if target_name == "筑基丹":
            user.skills.append("筑基丹药力(待渡劫)")
            return {
                "success": True,
                "message": "服下【筑基丹】，药力沉入丹田，下次筑基天劫成功率提升（由突破引擎结算）。",
            }

        # 玄冰玉露：直增真元 + 温养道心 + 闭关加成
        if "玄冰玉露" in target_name:
            exp_gain = 250 + tier * 50
            user.realm.current_exp = min(user.realm.max_exp, user.realm.current_exp + exp_gain)
            user.karma.dao_heart = min(100, user.karma.dao_heart + 5)
            mult = max(user.pill_exp_mult, 0.20)
            user.pill_exp_mult = mult
            user.pill_exp_note = f"{target_name}·{grade}"
            return {
                "success": True,
                "message": (
                    f"服下【{grade}·{target_name}】，清寒玉露涤荡周身经脉！\n"
                    f"直增真元 +{exp_gain}，道心澄澈 +5，下次闭关修为 +{int(mult * 100)}%。"
                ),
            }

        # 九转还魂真丹：大补寿元 + 极品真元 + 护持道心
        if "九转还魂真丹" in target_name:
            exp_gain = 350 + tier * 50
            user.realm.current_exp = min(user.realm.max_exp, user.realm.current_exp + exp_gain)
            user.lifespan.add_lifespan(3.0)
            user.karma.dao_heart = min(100, user.karma.dao_heart + 10)
            mult = max(user.pill_exp_mult, 0.35)
            user.pill_exp_mult = mult
            user.pill_exp_note = f"{target_name}·{grade}"
            return {
                "success": True,
                "message": (
                    f"【金丹入腹 · 逆转天数】服下【{grade}·{target_name}】，纯阳仙力直冲华盖！\n"
                    f"寿元温养 +3 岁，真元充盈 +{exp_gain}，道心固化 +10，下次闭关修为 +{int(mult * 100)}%。"
                ),
            }

        # 7. 通用丹药与灵液药力化纳
        mult = cfg.get("pill_exp_mult")
        if mult is None:
            mult = 0.10 * tier if entity else (0.15 if target_name == "聚气丹" else 0.08)
        mult = max(0.0, min(1.0, float(mult)))
        user.pill_exp_mult = max(user.pill_exp_mult, mult)
        user.pill_exp_note = f"{target_name}·{grade}"

        heal = float(cfg.get("heal_lifespan") or 0.0)
        if heal <= 0 and tier >= 4:
            heal = 1.0 * (tier - 3)
        heal_msg = ""
        if heal > 0:
            user.lifespan.add_lifespan(heal)
            heal_msg = f"\n寿元 +{heal:.0f} 岁。"

        direct_exp = int(cfg.get("direct_exp") or (40 * tier if entity else 0))
        if direct_exp > 0:
            user.realm.current_exp = min(user.realm.max_exp, user.realm.current_exp + direct_exp)

        return {
            "success": True,
            "message": (
                f"服下【{grade}·{target_name}】，药力沉入丹田。"
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

        fee = max(0, int(amount * MARKET_DEPOSIT_FEE_RATE))
        total_need = amount + fee
        try:
            CharacterIntegrity.assert_alive(c)
            CharacterIntegrity.assert_currency(c, total_need)
        except CharacterIntegrityError as e:
            return {
                "success": False,
                "message": f"寄存 {amount} 灵石需另付保管费 {fee}（合计 {total_need}），{e}",
            }

        CharacterIntegrity.deduct_currency(c, total_need)
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

        # 从随身扣除（优先从实体道具库移除，再扣 inventory / arrays）
        removed = False
        entity = seller.remove_item_entity(item_name)
        if entity:
            removed = True
            if getattr(entity, "kind", None) and getattr(entity.kind, "value", "") == "treasure_map":
                kind = "map"
        elif item_name in seller.inventory:
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
            if entity:
                seller.add_item_entity(entity)
            elif kind == "array":
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
            item_entity=entity,
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
        if hasattr(seller, "is_bag_full") and seller.is_bag_full():
            return {"success": False, "message": f"百宝纳戒乾坤已满（{getattr(seller, 'MAX_BAG_SLOTS', 64)}/{getattr(seller, 'MAX_BAG_SLOTS', 64)}），请先腾挪纳戒空间再行撤回！"}

        listing.status = ListingStatus.CANCELLED
        # 退回货物（实体优先）
        if listing.item_entity:
            seller.add_item_entity(listing.item_entity)
        elif listing.kind == "array":
            seller.arrays.append(listing.item_name)
        else:
            if "藏宝图" in listing.item_name:
                seller.add_item_entity(ItemFactory.from_legacy_name(listing.item_name))
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
        try:
            CharacterIntegrity.assert_alive(buyer)
            CharacterIntegrity.assert_bag_space(buyer, 1)
            CharacterIntegrity.assert_currency(buyer, listing.price)
        except CharacterIntegrityError as e:
            return {"success": False, "message": str(e)}

        CharacterIntegrity.deduct_currency(buyer, listing.price)
        listing.status = ListingStatus.SOLD

        if listing.item_entity:
            buyer.add_item_entity(listing.item_entity)
        elif "藏宝图" in listing.item_name:
            buyer.add_item_entity(ItemFactory.from_legacy_name(listing.item_name))
        elif listing.kind == "array":
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
    def complete_sale_payment(
        listing: MarketListing,
        seller: Optional[Character],
        to_stall_earnings: bool = False,
    ) -> Optional[int]:
        """把货款付给卖家（卖家可能已不在场，调用方处理）"""
        if listing.status != ListingStatus.SOLD:
            return None
        if seller is not None:
            if to_stall_earnings:
                seller.stall_earnings = getattr(seller, "stall_earnings", 0) + listing.price
            else:
                seller.spirit_stones += listing.price
        return listing.price

    @staticmethod
    def open_listings(all_listings: List[MarketListing]) -> List[MarketListing]:
        open_ = [l for l in all_listings if l.is_open()]
        open_.sort(key=lambda x: x.price)
        return open_
