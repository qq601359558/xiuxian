"""
坊市：商会货单、寄存金库、玩家挂单撮合
F03：商会官价按区域浮动（产地/距离系数 + 每日波动），价格计算单点收敛于本引擎。
"""
import hashlib
import time
import uuid
from datetime import date as _date
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
    WORLD_LOCATIONS,
    TRADE_HUB_REGION,
    TRADE_ORIGIN_FACTOR,
    TRADE_DISTANCE_FACTORS,
    TRADE_DAILY_FLUCTUATION,
    TRADE_ITEM_ORIGIN,
    TRADE_REGION_DISTANCE,
    TRADE_REG_TIERS,
    TRADE_REG_STATE_PREFIX,
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

    # ---------------- 区域价格（F03 跑商，单点收敛） ----------------
    @staticmethod
    def region_of(location: Optional[str]) -> str:
        """地点 → 区域；未知地点回退基准区（系数 1.00，不炸）"""
        cfg = WORLD_LOCATIONS.get(location or "") or {}
        return cfg.get("region") or TRADE_HUB_REGION

    @staticmethod
    def _day_str(day: Optional[str] = None) -> str:
        return day or _date.today().isoformat()

    @staticmethod
    def regional_factor(item_name: str, region: str, day: Optional[str] = None) -> float:
        """区域系数（纯函数，同日同货同区必一致）：
        基准区恒 1.00；产地 TRADE_ORIGIN_FACTOR；其余按距产地距离查表；
        非基准区再乘 (日期,区域,货物) 种子决定的每日小幅波动。"""
        if region == TRADE_HUB_REGION:
            return 1.0
        origin = TRADE_ITEM_ORIGIN.get(item_name)
        if not origin:
            return 1.0
        if region == origin:
            factor = TRADE_ORIGIN_FACTOR
        else:
            dist = TRADE_REGION_DISTANCE.get(frozenset((origin, region)))
            factor = TRADE_DISTANCE_FACTORS.get(dist, 1.0) if dist is not None else 1.0
        # 每日波动：md5 种子 → [-1, 1]，全服一致可复现，零存储
        day = MarketEngine._day_str(day)
        seed = hashlib.md5(f"{day}|{region}|{item_name}".encode("utf-8")).hexdigest()
        ratio = (int(seed[:8], 16) % 2001) / 1000.0 - 1.0
        return factor * (1.0 + ratio * TRADE_DAILY_FLUCTUATION)

    @staticmethod
    def _price_for_region(item_name: str, region: str, day: Optional[str] = None) -> int:
        """区域市价（价格公式唯一实现点）：标价 × 区域系数 × 天象价系数，四舍五入，下限 1
        位序（F03→F13→F09）：区域价在此收敛；纪元天象（F13）按 day 所属纪元推导，
        非金风纪元恒 ×1.0；F09 主导折扣在成交点对本市价再乘，不进本函数。"""
        cfg = ITEM_CATALOG.get(item_name)
        base = cfg["price"] if cfg else 20
        try:
            from core.season_theme import SeasonThemeEngine

            theme_mult = SeasonThemeEngine.price_mult_for_day(day)
        except Exception:
            theme_mult = 1.0
        return max(
            1,
            int(round(base * MarketEngine.regional_factor(item_name, region, day) * theme_mult)),
        )

    @staticmethod
    def _sell_unit_for_region(item_name: str, region: str, day: Optional[str] = None) -> int:
        return max(1, int(MarketEngine._price_for_region(item_name, region, day) * MARKET_SELL_BACK_RATE))

    @staticmethod
    def market_price(item_name: str, location: Optional[str] = None, day: Optional[str] = None) -> int:
        """当地市价（商会卖出价）"""
        return MarketEngine._price_for_region(item_name, MarketEngine.region_of(location), day)

    @staticmethod
    def sell_unit_base(item_name: str, location: Optional[str] = None, day: Optional[str] = None) -> int:
        """当地回收单价基准：市价 × 回收率（未含防刷分档压价）"""
        return MarketEngine._sell_unit_for_region(item_name, MarketEngine.region_of(location), day)

    # ---------------- 防刷：同货同日收购量回归 ----------------
    @staticmethod
    def _reg_mult(cum_qty: int) -> float:
        """第 cum_qty 件（1 起）适用的回收价系数，按 TRADE_REG_TIERS 分档"""
        for cap, mult in TRADE_REG_TIERS:
            if cum_qty <= cap:
                return mult
        return TRADE_REG_TIERS[-1][1]

    @staticmethod
    def _reg_state(char_id: str) -> Dict[str, Any]:
        """读当日收购量状态；读失败/形状损坏/跨日一律降级为空（不阻断交易）"""
        try:
            from storage.db import WorldStateRepository

            st = WorldStateRepository.get(TRADE_REG_STATE_PREFIX + str(char_id))
            if not isinstance(st, dict) or st.get("date") != MarketEngine._day_str():
                return {}
            if not isinstance(st.get("vol"), dict):
                return {}
            return st
        except Exception:
            return {}

    @staticmethod
    def _reg_volume(char_id: str, item_name: str) -> int:
        try:
            return int((MarketEngine._reg_state(char_id).get("vol") or {}).get(item_name) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _reg_record(char_id: str, item_name: str, qty: int) -> None:
        if qty <= 0:
            return
        try:
            from storage.db import WorldStateRepository

            key = TRADE_REG_STATE_PREFIX + str(char_id)
            st = MarketEngine._reg_state(char_id)
            vol = dict(st.get("vol") or {})
            vol[item_name] = int(vol.get(item_name) or 0) + qty
            WorldStateRepository.set(key, {"date": MarketEngine._day_str(), "vol": vol})
        except Exception:
            pass  # 状态写失败降级为无回归，不阻断交易

    # ---------------- 商会货单 ----------------
    @staticmethod
    def _rows_for_region(region: Optional[str], day: Optional[str] = None) -> List[Dict[str, Any]]:
        """货单行；region 为 None 时是标价原样，否则附区域市价字段"""
        out = []
        for name, cfg in ITEM_CATALOG.items():
            row = {
                "name": name,
                "kind": cfg["kind"],
                "price": cfg["price"],
                "desc": cfg["desc"],
            }
            if region is not None:
                factor = MarketEngine.regional_factor(name, region, day)
                row.update({
                    "price": MarketEngine._price_for_region(name, region, day),
                    "base_price": cfg["price"],
                    "origin": TRADE_ITEM_ORIGIN.get(name, ""),
                    "factor": round(factor, 3),
                    "sell_price": MarketEngine._sell_unit_for_region(name, region, day),
                })
            out.append(row)
        out.sort(key=lambda x: x["price"])
        return out

    @staticmethod
    def catalog(location: Optional[str] = None) -> List[Dict[str, Any]]:
        """货单；不传地点与旧行为一致（标价），传地点时 price 为当地市价"""
        if location is None:
            return MarketEngine._rows_for_region(None)
        return MarketEngine._rows_for_region(MarketEngine.region_of(location))

    @staticmethod
    def all_regions() -> List[str]:
        """全部区域（基准区在首），按 WORLD_LOCATIONS 出现顺序"""
        regions: List[str] = []
        for cfg in WORLD_LOCATIONS.values():
            r = cfg.get("region")
            if r and r not in regions:
                regions.append(r)
        if TRADE_HUB_REGION in regions:
            regions.remove(TRADE_HUB_REGION)
            regions.insert(0, TRADE_HUB_REGION)
        return regions

    @staticmethod
    def trade_board(location: Optional[str] = None, day: Optional[str] = None) -> str:
        """【天下行情】文本：逐区域产地货与贵货官价 + 跑商路线提示（本地模板，零 AI）"""
        day = MarketEngine._day_str(day)
        cur_region = MarketEngine.region_of(location) if location else None
        lines = [
            f"【天下行情】{day} · 商会官价（买入 / 回收，回收为市价五折）",
            f"基准区【{TRADE_HUB_REGION}】标价为纲：产地贱、远方贵，每日微澜。",
        ]
        for region in MarketEngine.all_regions():
            mark = "（你在此）" if region == cur_region else ""
            lines.append(f"◆ {region}{mark}")
            rows = MarketEngine._rows_for_region(region, day)
            origin_rows = [g for g in rows if g.get("origin") == region]
            shown = {g["name"] for g in origin_rows}
            for g in origin_rows:
                pct = (g["factor"] - 1.0) * 100
                lines.append(f"  · {g['name']} 买{g['price']} / 回收{g['sell_price']} 【产地 {pct:+.0f}%】")
            imports = [g for g in rows if g["name"] not in shown]
            imports.sort(key=lambda x: -x["factor"])
            for g in imports[:2]:
                pct = (g["factor"] - 1.0) * 100
                lines.append(
                    f"  · {g['name']} 买{g['price']} / 回收{g['sell_price']}"
                    f"（产{g['origin']}，价系数 {g['factor']:.2f}，{pct:+.0f}%）"
                )
        lines.append("跑商路线（产地贱买 → 远方高价回收，单程毛利已被商会五折与收购配额封顶）：")
        samples: Dict[str, str] = {}
        for name, origin in TRADE_ITEM_ORIGIN.items():
            samples.setdefault(origin, name)
        for origin, sample in samples.items():
            if origin == TRADE_HUB_REGION:
                continue
            dests = [
                r for r in MarketEngine.all_regions()
                if r != origin and frozenset((origin, r)) in TRADE_REGION_DISTANCE
            ]
            if not dests:
                continue
            dest = max(dests, key=lambda r: TRADE_REGION_DISTANCE[frozenset((origin, r))])
            sell = TRADE_DISTANCE_FACTORS[TRADE_REGION_DISTANCE[frozenset((origin, dest))]] * MARKET_SELL_BACK_RATE
            margin = sell / TRADE_ORIGIN_FACTOR - 1.0
            if margin > 0:
                lines.append(f"  · {origin} 产【{sample}】→ 运往【{dest}】回收，毛利约 {int(margin * 100)}%")
        lines.append("注：同一修士同货同日收购逾额，商会将分档压价（行情回归），莫想一日刷空商会。")
        return "\n".join(lines)

    @staticmethod
    def buy_from_guild(buyer: Character, item_name: str, qty: int = 1) -> Dict[str, Any]:
        cfg = ITEM_CATALOG.get(item_name)
        if not cfg:
            return {"success": False, "message": f"商会并无【{item_name}】此货。输入 /坊市 查看货单。"}
        if qty < 1:
            return {"success": False, "message": "购买数量至少为 1。"}

        # F03：按买家所在地市价计价（基准区即标价）
        unit = MarketEngine.market_price(item_name, buyer.location)
        region = MarketEngine.region_of(buyer.location)
        # F09 版图：主导宗门成员在本区域购货九五折——成交点修饰（市价单点不动，
        # 与卖出侧防刷分档同例）；判定异常降级原价，绝不阻断交易
        atlas_unit = unit
        try:
            from core.atlas import AtlasEngine

            atlas_unit = AtlasEngine.discount_unit(unit, buyer.sect, region)
        except Exception:
            atlas_unit = unit
        total = atlas_unit * qty
        if buyer.spirit_stones < total:
            return {
                "success": False,
                "message": f"【{item_name}】单价 {atlas_unit} 灵石，买 {qty} 件需 {total}，囊中仅有 {buyer.spirit_stones}。",
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
        # F09：主导折扣注脚（无折扣时消息与旧版逐字一致）
        if atlas_unit < unit:
            msg += f"\n（本宗【{buyer.sect}】主导{region}，商会买价九五折：单价 {atlas_unit} 灵石。）"
        # F03：非基准价时注明当地行情（基准区消息与旧版逐字一致）
        factor = MarketEngine.regional_factor(item_name, region)
        if abs(factor - 1.0) > 1e-9:
            origin = TRADE_ITEM_ORIGIN.get(item_name, "")
            tag = "产地直供价" if origin == region else f"产地 {origin}"
            msg += f"\n（{region}市价 {unit} 灵石/件，{tag}；基准区标价 {cfg['price']}。）"
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
        if qty < 1:
            return {"success": False, "message": "出售数量至少为 1。"}
        # 著书立说（F11）：亲笔手稿只许寄售流通/赠予，商会不回收（保书目绑定一致；直导入 fail-closed）
        from core.books import BOOK_ITEM

        if item_name == BOOK_ITEM:
            return {"success": False, "message": "【亲笔手稿】乃著者心血，商会不敢贱收；可 /寄售 亲笔手稿 <价> 付坊市流通。"}
        cfg = ITEM_CATALOG.get(item_name, {"kind": "material", "price": 20})
        # F03：回收基准价 = 当地市价 × 回收率（基准区即旧口径 标价×50%）
        region = MarketEngine.region_of(seller.location)
        unit_back = MarketEngine.sell_unit_base(item_name, seller.location)

        # 优先卖随身杂物，其次阵盘
        have_inv = seller.inventory.count(item_name)
        have_arr = seller.arrays.count(item_name) if cfg.get("kind") == "array" else 0
        # 材料/丹药也可从 inventory 卖
        if have_inv + have_arr < qty:
            return {
                "success": False,
                "message": f"随身并无足够的【{item_name}】（有 {have_inv + have_arr} 件）。",
            }

        # F03 防刷：先计价（读当日已收购量、分档逐件），后扣货记量——计价异常不伤库存
        vol0 = MarketEngine._reg_volume(seller.id, item_name)
        gain = 0
        decayed = False
        for i in range(qty):
            mult = MarketEngine._reg_mult(vol0 + i + 1)
            if mult < 1.0:
                decayed = True
            gain += max(1, int(unit_back * mult))

        left = qty
        # 先扣 inventory
        while left > 0 and item_name in seller.inventory:
            seller.inventory.remove(item_name)
            left -= 1
        # 阵盘再扣 arrays
        while left > 0 and item_name in seller.arrays:
            seller.arrays.remove(item_name)
            left -= 1

        MarketEngine._reg_record(seller.id, item_name, qty)
        seller.spirit_stones += gain
        msg = (
            f"【商会回收】售出【{item_name}】×{qty}，得灵石 {gain}"
            f"（回收价约为标价 {int(MARKET_SELL_BACK_RATE * 100)}%）。"
        )
        if region != TRADE_HUB_REGION:
            msg = (
                f"【商会回收】售出【{item_name}】×{qty}，得灵石 {gain}"
                f"（{region}市价 {MarketEngine.market_price(item_name, seller.location)} 灵石，回收五折）。"
            )
        if decayed:
            msg += "\n（商会今日收购此货渐饱，回收价已分档下浮——行情回归。）"
        return {
            "success": True,
            "gain": gain,
            "unit_back": unit_back,
            "avg_unit": gain // qty,
            "decayed": decayed,
            "message": msg,
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
