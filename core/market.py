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
    seller_user_id: str = ""  # account-death：与 AuctionLot 同口径；旧单默认 ""，见 §5 回填规则
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
            if cfg.get("kind") == "map" or cfg.get("npc_sell") is False:
                continue  # 天地机缘之物，商会无从兜售
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
        if cfg.get("kind") == "map" or cfg.get("npc_sell") is False:
            return {"success": False, "message": "此乃天地造化机缘之物，商会无从兜售，需亲自探险发掘或于玩家处求购。"}
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
        # M4 坊市恐慌（player_echo market_buy_mult）合并裁定不进成交价：
        # 恐慌乘子读全局持久化回响状态，会使 F03 区域价 × F09 宗门折扣的
        # 钉死组合口径随世界累积状态漂移；恐慌信号仍经望气/行情文案展示。
        total = atlas_unit * qty
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
        # M4 恐慌压回收价（market_sell_mult）同买价裁定：不进钉死回收口径。
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

        # 闭关药力未化解拦截：若丹药附带闭关加成且体内已有未消化药力，需先行闭关
        has_exp_mult = cfg.get("pill_exp_mult") is not None or target_name in {"聚气丹", "玄元聚气丹", "九转凝灵丹"}
        if has_exp_mult and getattr(user, "pill_exp_mult", 0.0) > 0.0:
            note = getattr(user, 'pill_exp_note', '') or '灵丹'
            pct = int(user.pill_exp_mult * 100)
            return {
                "success": False,
                "message": f"体内尚有【{note}】未化解之闭关药力（加成 {pct}%），不可叠加大丹，请先行闭关吐纳！"
            }

        # 4. 耐药抗性与软上限衰减计算 (Soft Cap & Resistance Decay)
        max_life_intake = int(cfg.get("max_life_intake", 999))
        decay_rate = float(cfg.get("decay_rate", 0.5))
        min_decay_floor = float(cfg.get("min_decay_floor", 0.2))
        toxicity = int(cfg.get("toxicity", 0))

        if not hasattr(user, "pill_intake_counts") or user.pill_intake_counts is None:
            user.pill_intake_counts = {}

        current_intake = user.pill_intake_counts.get(target_name, 0)
        decay_note = ""
        if current_intake < max_life_intake:
            efficiency = 1.0
        else:
            over = current_intake - max_life_intake + 1
            efficiency = max(min_decay_floor, round(1.0 - over * decay_rate, 2))
            decay_note = (
                f"\n【耐药渐生】此丹本世已服食 {current_intake} 次，肉身经脉渐生抗性，"
                f"药力发挥 {int(efficiency * 100)}%（软上限衰减中，最低保底 {int(min_decay_floor * 100)}%）。"
            )

        # 5. 原子扣减道具实体与行囊记录
        if entity:
            user.remove_item_entity(entity.uid)
        else:
            if target_name in user.inventory:
                user.inventory.remove(target_name)
        user.used_pills.append(target_name)
        user.pill_intake_counts[target_name] = current_intake + 1

        # 丹毒累加 (若丹药含有丹毒)
        if toxicity > 0:
            user.pill_toxicity = getattr(user, "pill_toxicity", 0) + toxicity

        tier = entity.tier if entity else (cfg.get("tier") or 1)
        grade = (entity.tier_name if entity else None) or cfg.get("grade") or (
            ["凡品", "人品", "地品", "天品", "仙品"][min(4, max(0, tier - 1))]
        )

        # 6. 兼容性经典大丹分支保持 (筑基丹、玄冰玉露、九转还魂真丹)
        if target_name == "筑基丹":
            user.skills.append("筑基丹药力(待渡劫)")
            b_bonus = round(float(cfg.get("breakthrough_bonus", 0.35)) * efficiency, 3)
            if not hasattr(user, "pill_breakthrough_prep") or user.pill_breakthrough_prep is None:
                user.pill_breakthrough_prep = {}
            user.pill_breakthrough_prep["2"] = max(user.pill_breakthrough_prep.get("2", 0.0), b_bonus)
            user.pill_breakthrough_prep["rate_bonus"] = max(user.pill_breakthrough_prep.get("rate_bonus", 0.0), b_bonus)
            tox_msg = f"\n当前体内丹毒：{user.pill_toxicity}。" if user.pill_toxicity > 0 else ""
            return {
                "success": True,
                "message": (
                    f"服下【筑基丹】，药力沉入丹田，下次筑基天劫成功率提升 +{int(b_bonus * 100)}%（由突破引擎结算）。"
                    f"{decay_note}{tox_msg}"
                ),
            }

        if "玄冰玉露" in target_name:
            exp_gain = int((250 + tier * 50) * efficiency)
            user.realm.current_exp = min(user.realm.max_exp, user.realm.current_exp + exp_gain)
            user.karma.dao_heart = min(100, user.karma.dao_heart + 5)
            mult = max(user.pill_exp_mult, 0.20 * efficiency)
            user.pill_exp_mult = mult
            user.pill_exp_note = f"{target_name}·{grade}"
            tox_msg = f"\n当前体内丹毒：{user.pill_toxicity}。" if user.pill_toxicity > 0 else ""
            return {
                "success": True,
                "message": (
                    f"服下【{grade}·{target_name}】，清寒玉露涤荡周身经脉！\n"
                    f"直增真元 +{exp_gain}，道心澄澈 +5，下次闭关修为 +{int(mult * 100)}%。"
                    f"{decay_note}{tox_msg}"
                ),
            }

        if "九转还魂真丹" in target_name:
            exp_gain = int((350 + tier * 50) * efficiency)
            user.realm.current_exp = min(user.realm.max_exp, user.realm.current_exp + exp_gain)
            user.lifespan.add_lifespan(3.0 * efficiency)
            user.karma.dao_heart = min(100, user.karma.dao_heart + 10)
            mult = max(user.pill_exp_mult, 0.35 * efficiency)
            user.pill_exp_mult = mult
            user.pill_exp_note = f"{target_name}·{grade}"
            tox_msg = f"\n当前体内丹毒：{user.pill_toxicity}。" if user.pill_toxicity > 0 else ""
            return {
                "success": True,
                "message": (
                    f"【金丹入腹 · 逆转天数】服下【{grade}·{target_name}】，纯阳仙力直冲华盖！\n"
                    f"寿元温养 +{3.0 * efficiency:.1f} 岁，真元充盈 +{exp_gain}，道心固化 +10，下次闭关修为 +{int(mult * 100)}%。"
                    f"{decay_note}{tox_msg}"
                ),
            }

        # 7. 全流派多维度丹药药力化纳
        notes = []

        # (1) 冲关破境 (breakthrough)
        b_rate = float(cfg.get("breakthrough_rate_bonus") or cfg.get("breakthrough_bonus") or 0.0)
        if b_rate > 0:
            scaled_b = round(b_rate * efficiency, 3)
            b_tier = cfg.get("breakthrough_pill_tier", tier)
            if not hasattr(user, "pill_breakthrough_prep") or user.pill_breakthrough_prep is None:
                user.pill_breakthrough_prep = {}
            user.pill_breakthrough_prep[str(b_tier)] = max(user.pill_breakthrough_prep.get(str(b_tier), 0.0), scaled_b)
            user.pill_breakthrough_prep["rate_bonus"] = max(user.pill_breakthrough_prep.get("rate_bonus", 0.0), scaled_b)
            notes.append(f"引动天地气机，下次大境界突破成功率 +{int(scaled_b * 100)}%")

        # (2) 修为进境 (cultivation)
        mult = cfg.get("pill_exp_mult")
        if mult is None and cfg.get("pill_type") == "cultivation":
            mult = 0.10 * tier if entity else (0.15 if target_name == "聚气丹" else 0.08)
        if mult is not None:
            mult_val = max(0.0, min(1.0, float(mult))) * efficiency
            user.pill_exp_mult = max(user.pill_exp_mult, mult_val)
            user.pill_exp_note = f"{target_name}·{grade}"
            notes.append(f"下次闭关修为吸收效率 +{int(mult_val * 100)}%")

        direct_exp = int((cfg.get("direct_exp") or (40 * tier if entity and not cfg.get("direct_exp") else 0)) * efficiency)
        if direct_exp > 0:
            user.realm.current_exp = min(user.realm.max_exp, user.realm.current_exp + direct_exp)
            notes.append(f"直增真元 +{direct_exp}")

        perm_hp = int(cfg.get("permanent_hp_max", 0) * efficiency)
        if perm_hp > 0:
            user.combat.max_hp += perm_hp
            user.combat.current_hp += perm_hp
            notes.append(f"气血上限永久 +{perm_hp}")

        perm_mp = int(cfg.get("permanent_mp_max", 0) * efficiency)
        if perm_mp > 0:
            user.combat.max_mp += perm_mp
            user.combat.current_mp += perm_mp
            notes.append(f"法力上限永久 +{perm_mp}")

        # (3) 斗法回春 (recovery)
        heal_hp_pct = float(cfg.get("heal_hp_pct", 0.0))
        if heal_hp_pct > 0:
            recovered_hp = int(user.combat.max_hp * heal_hp_pct * efficiency)
            user.combat.current_hp = min(user.combat.max_hp, user.combat.current_hp + recovered_hp)
            notes.append(f"气血回复 +{recovered_hp}")

        heal_mp_pct = float(cfg.get("heal_mp_pct", 0.0))
        if heal_mp_pct > 0:
            recovered_mp = int(user.combat.max_mp * heal_mp_pct * efficiency)
            user.combat.current_mp = min(user.combat.max_mp, user.combat.current_mp + recovered_mp)
            notes.append(f"真元回复 +{recovered_mp}")

        # (4) 延寿夺命 (lifespan)
        heal_years = float(cfg.get("heal_lifespan") or cfg.get("add_lifespan_years") or 0.0)
        if heal_years <= 0 and tier >= 4 and cfg.get("pill_type") == "lifespan":
            heal_years = 1.0 * (tier - 3)
        if heal_years > 0:
            scaled_years = heal_years * efficiency
            user.lifespan.add_lifespan(scaled_years)
            notes.append(f"寿元延展 +{scaled_years:.1f} 岁")

        # (5) 神魂淬炼 (soul_purity)
        perm_sense = int(cfg.get("perm_divine_sense", 0) * efficiency)
        if perm_sense > 0:
            user.soul.divine_sense += perm_sense
            notes.append(f"神识强度永久 +{perm_sense}")

        s_range = int(cfg.get("sense_range_bonus", 0) * efficiency)
        if s_range > 0:
            user.soul.sense_range += s_range
            notes.append(f"神识探查半径 +{s_range}米")

        ill_res = float(cfg.get("illusion_resist_bonus", 0.0)) * efficiency
        if ill_res > 0:
            user.soul.illusion_resist = min(0.95, user.soul.illusion_resist + ill_res)
            notes.append(f"心魔与幻阵抵抗率 +{int(ill_res * 100)}%")

        # (6) 灵根洗炼 (root_purify)
        root_b = float(cfg.get("root_efficiency_bonus", 0.0)) * efficiency
        if root_b > 0:
            user.spiritual_root.efficiency = round(user.spiritual_root.efficiency + root_b, 3)
            notes.append(f"灵根吐纳吸收效率永久提升 +{int(root_b * 100)}%（当前: {user.spiritual_root.efficiency:.2f}）")

        # (7) 涤毒清髓 (detox)
        cleanse = int(cfg.get("cleanse_toxicity", 0))
        if cleanse > 0:
            before_tox = getattr(user, "pill_toxicity", 0)
            user.pill_toxicity = max(0, before_tox - cleanse)
            cleansed = before_tox - user.pill_toxicity
            notes.append(f"洗涤肉身，清除体内丹毒 {cleansed} 点（余 {user.pill_toxicity}）")

        add_heart = int(cfg.get("add_dao_heart", 0) or cfg.get("dao_heart_bonus", 0))
        if add_heart > 0:
            user.karma.dao_heart = min(100, user.karma.dao_heart + add_heart)
            notes.append(f"道心纯度 +{add_heart}（当前: {user.karma.dao_heart}）")

        # (8) 战力狂暴 (combat_buff)
        cb = float(cfg.get("combat_power_bonus", 0.0)) * efficiency
        if cb > 0:
            if not hasattr(user, "pill_combat_buffs") or user.pill_combat_buffs is None:
                user.pill_combat_buffs = []
            user.pill_combat_buffs.append({
                "name": target_name,
                "power_bonus": cb,
                "expire_at": time.time() + 1800
            })
            notes.append(f"斗法战力暴涨 +{int(cb * 100)}%（持续半个时辰）")

        effect_summary = ("，".join(notes) + "。") if notes else "药力沉入丹田温养周天。"
        tox_status = f"\n当前体内丹毒：{user.pill_toxicity} 点。" if getattr(user, "pill_toxicity", 0) > 0 else ""

        return {
            "success": True,
            "message": (
                f"服下【{grade}·{target_name}】，药力化入四肢百骸！\n"
                f"{effect_summary}"
                f"{decay_note}"
                f"{tox_status}"
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
    def resolve_sale_route(listing: MarketListing) -> Dict[str, Any]:
        """成交款路由预检（spec §5.3，买前调用，纯读不写盘）：

        - seller_user_id 可用 → 放行（现世角色存活且 id 与单据一致 → 角色行，
          否则 → 该账户钱包）；
        - seller_id 命中现世存活角色 → 角色行；命中死行 → 该行账户钱包；
        - 当铺伪主体（pawn_shop）→ 当铺沉淀（既有口径，付款不入任何钱包）；
        - 三者皆无 → 不可考，拒售。
        返回 {"route": "character"|"wallet"|"shop"|"unresolvable", "user_id": ...}。
        """
        from storage.db import CharacterRepository

        if listing.seller_id == "pawn_shop":
            return {"route": "shop", "user_id": ""}
        if listing.seller_user_id:
            char = CharacterRepository.get_by_user_id(listing.seller_user_id)
            if char is not None and char.id == listing.seller_id and char.status != CharacterStatus.DEAD and not char.lifespan.is_dead():
                return {"route": "character", "user_id": listing.seller_user_id}
            return {"route": "wallet", "user_id": listing.seller_user_id}
        if listing.seller_id:
            char = CharacterRepository.get_by_id(listing.seller_id)
            if char is not None:
                if char.status != CharacterStatus.DEAD and not char.lifespan.is_dead():
                    return {"route": "character", "user_id": char.user_id}
                return {"route": "wallet", "user_id": char.user_id}
        if listing.seller_name:
            char = CharacterRepository.get_by_name(listing.seller_name)
            if char is not None and char.status != CharacterStatus.DEAD and not char.lifespan.is_dead():
                # 仅当卖家名解析到的存活角色与单据 seller_id 一致时才算生前旧口径；
                # id 不一致（转世同名等）不以名兜底，防错付他人。
                if char.id == listing.seller_id:
                    return {"route": "character", "user_id": char.user_id}
        return {"route": "unresolvable", "user_id": ""}

    @staticmethod
    def list_item(
        seller: Character,
        item_name: str,
        price: int,
        kind_hint: str = "",
    ) -> Tuple[Optional[MarketListing], Dict[str, Any]]:
        if price <= 0:
            return None, {"success": False, "message": "挂单价格必须为正。"}
        if not (seller.user_id or ""):
            return None, {"success": False, "message": "卖家无账户标识，无法挂单。"}

        cfg = ITEM_CATALOG.get(item_name)
        kind = cfg["kind"] if cfg else (kind_hint or "material")

        # 已装备封堵（QA2 全渠道口径，与当铺同例）：佩戴中的法宝不得挂单。
        # main 原实现靠「装备不在 inventory」天然封堵；分支实体优先扣除会
        # 把 items 中的佩戴实体直接摘走上架，故在此显式拦截。
        if item_name in (seller.equipped or []):
            return None, {
                "success": False,
                "message": f"【{item_name}】正穿戴在身，须先 /卸下 放入行囊方可挂单。",
            }

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
            seller_user_id=seller.user_id,
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
        # 评审 M3：同账户新角不得买回自己旧世寄售单——卖家 user_id 取单据
        # seller_user_id，或按 seller_id 反查现世／死行；命中即拒绝（物品免费回流
        # 违背 spec §2.4 物品类不保留）。不可考旧单由下方路由预检拒售。
        if buyer.user_id:
            seller_uid = listing.seller_user_id or ""
            if not seller_uid and listing.seller_id:
                from storage.db import CharacterRepository as _CR

                _row = _CR.get_by_id(listing.seller_id)
                if _row is not None:
                    seller_uid = _row.user_id or ""
            if seller_uid and seller_uid == buyer.user_id:
                return {"success": False, "message": "不可买回自己旧世的挂单。"}
        # §5.3 买前路由预检（扣款之前）：不可考旧单拒售，买家分文不动
        route = MarketEngine.resolve_sale_route(listing)
        if route["route"] == "unresolvable":
            return {
                "success": False,
                "message": "此单卖家已不可考，天道暂封此单，买家未扣款。",
            }

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
        """把货款付给卖家（spec 裁定 1：按 seller_user_id 路由）。

        - to_stall_earnings=True 且卖家在场（地摊直售通道）→ 优先入卖家
          stall_earnings，跳过路由（world 摆摊结算三处调用点依赖此语义）；
        - 传入卖家对象存活且 id 与单据一致 → 付角色行（生前成交旧口径，含纯内存测试）；
        - 否则按单据路由：seller_user_id 可用 → 该账户钱包（consignment_sale，
          ref=寄售单 id，幂等）；死行 → 其账户钱包；当铺 → 沉淀（返回标价，不入账）；
        - 路由不可考 → 返回 None，不付款（买前预检本应已拒售，此为第二道防线）。
        调用方负责保存钱包行／卖家行（钱包入账后由本函数即保存账户行）。
        """
        if listing.status != ListingStatus.SOLD:
            return None
        if to_stall_earnings and seller is not None:
            seller.stall_earnings = getattr(seller, "stall_earnings", 0) + listing.price
            return listing.price
        if (
            seller is not None
            and seller.id == listing.seller_id
            and seller.status != CharacterStatus.DEAD
            and not seller.lifespan.is_dead()
        ):
            # 评审 M4：成交时把解析到的 seller_user_id 写回旧单（调用方保存单据时落盘）。
            if not listing.seller_user_id and seller.user_id:
                listing.seller_user_id = seller.user_id
            seller.spirit_stones += listing.price
            return listing.price
        route = MarketEngine.resolve_sale_route(listing)
        # 评审 M4：成交路径把路由解析到的 seller_user_id 持久化写回旧单；
        # resolve_sale_route 本身保持纯读预检，不写盘（写回只在此成交路径）。
        if not listing.seller_user_id and route.get("user_id"):
            listing.seller_user_id = route["user_id"]
            try:
                from storage.db import MarketListingRepository as _MLR

                _MLR.save(listing)
            except Exception:
                pass
        if route["route"] == "shop":
            return listing.price
        if route["route"] == "wallet" and route["user_id"]:
            from core.wallet import credit_wallet, is_npc_user
            from storage.db import LegacyRepository

            if is_npc_user(route["user_id"]):
                return listing.price
            account = LegacyRepository.get_or_create(route["user_id"])
            credit_wallet(
                account,
                listing.price,
                "consignment_sale",
                listing.id,
                f"寄售成交：【{listing.item_name}】{listing.price} 灵石",
            )
            LegacyRepository.save(account)
            return listing.price
        if route["route"] == "character":
            # 路由判定为角色行但调用方未传入匹配对象时，按 id 重读后付款
            from storage.db import CharacterRepository

            target = CharacterRepository.get_by_id(listing.seller_id)
            if target is not None:
                target.spirit_stones += listing.price
                CharacterRepository.save(target)
                return listing.price
        return None

    @staticmethod
    def open_listings(all_listings: List[MarketListing]) -> List[MarketListing]:
        open_ = [l for l in all_listings if l.is_open()]
        open_.sort(key=lambda x: x.price)
        return open_
