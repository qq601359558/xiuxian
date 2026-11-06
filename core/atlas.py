"""
宗门势力版图（F09）：各宗门在各区域的影响力。

只认既有事实累积——成员完成探险/委托交付/除凶结算（引擎钩子）、本宗议政通过；
惰性半衰期衰减（读时折算、写时结算，不新造线程），版图可易主。
唯一硬效果：主导宗门成员在该区域向商会购货享九五折（market 成交点修饰，市价单点不动）。
状态走 world_state 专属 KV：sect_atlas:{region}（本引擎独占写）、sect_atlas_cap:{char_id}（日上限）。
零 AI 调用；一切数值在本模块常量。
"""
import time
from datetime import date as _date
from typing import Any, Dict, List, Optional

from config import SECTS_CONFIG
from core.models import Character, CharacterStatus
from storage.db import WorldStateRepository

# ---------------- 常量（灰度校准，见 spec/atlas.md） ----------------
ATLAS_POINTS = {"explore": 4, "quest": 6, "hunt": 10}  # 单次活动原始分
ATLAS_POINTS_COUNCIL = 10          # 议政通过：落本宗总坛区域（组织级，不占个人上限）
ATLAS_DAILY_CAP_PLAYER = 30        # 玩家每区域每日原始分上限
ATLAS_DAILY_CAP_NPC = 10           # NPC 每区域每日原始分上限（另有权重折算）
ATLAS_NPC_WEIGHT = 0.5             # NPC 入账权重（防 tick 自然膨胀）
ATLAS_DOMINANCE_THRESHOLD = 100.0  # 主导门槛（衰减后影响力）
ATLAS_DISCOUNT_RATE = 0.05         # 主导成员购货折扣
ATLAS_DECAY_HALF_LIFE_DAYS = 7.0   # 影响力半衰期（现实天）
ATLAS_PRUNE_BELOW = 0.5            # 折算后低于此值视为消散
ATLAS_THRESHOLD_TOLERANCE = 0.01   # 门槛比较容差：衰减为连续量，恰达门槛者读时已微亏，不得丢主导
ATLAS_STATE_PREFIX = "sect_atlas:"
ATLAS_CAP_PREFIX = "sect_atlas_cap:"

_EPS = 1e-9


def _is_npc(c: Character) -> bool:
    return str(c.user_id).startswith(("npc_", "ai_npc_"))


def _day_str(ts: Optional[float] = None) -> str:
    """日期口径：缺省本地今日；注入时刻时按该时刻的本地日期（与衰减时刻对齐）"""
    if ts is not None:
        from datetime import datetime

        return datetime.fromtimestamp(ts).date().isoformat()
    return _date.today().isoformat()


def _region_of(location: Optional[str]) -> str:
    """地点 → 区域：经 F03 价格单点 MarketEngine.region_of（惰性导入免环）"""
    from core.market import MarketEngine

    return MarketEngine.region_of(location)


def _all_regions() -> List[str]:
    from core.market import MarketEngine

    return MarketEngine.all_regions()


class AtlasEngine:
    """势力版图裁决引擎（规则单点）"""

    # ---------------- 存储与衰减 ----------------
    @staticmethod
    def _read_raw(region: str) -> Dict[str, Any]:
        """读区域 KV 并消毒形状；损坏/缺失一律降级为空（不炸主流程）"""
        try:
            raw = WorldStateRepository.get(ATLAS_STATE_PREFIX + str(region))
        except Exception:
            return {}
        if not isinstance(raw, dict) or not isinstance(raw.get("inf"), dict):
            return {}
        inf: Dict[str, float] = {}
        for sect, val in raw["inf"].items():
            if sect in SECTS_CONFIG:
                try:
                    inf[str(sect)] = float(val)
                except (TypeError, ValueError):
                    continue
        try:
            ts = float(raw.get("ts") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        if ts <= 0:
            # 无有效时间戳的存量视为损坏（本引擎写入恒带 ts）：降级为空表，
            # 否则 _decay_factor 对 ts<=0 恒 1.0 会让这批影响力永不衰减
            return {}
        return {"inf": inf, "ts": ts}

    @staticmethod
    def _decay_factor(ts: float, now: float) -> float:
        if ts <= 0 or now <= ts:
            return 1.0
        days = (now - ts) / 86400.0
        return 0.5 ** (days / ATLAS_DECAY_HALF_LIFE_DAYS)

    @staticmethod
    def influence_map(region: str, now: Optional[float] = None) -> Dict[str, float]:
        """区域影响力（衰减折算后，纯读不写盘）；低于剪除线者视为消散"""
        t = now if now is not None else time.time()
        raw = AtlasEngine._read_raw(region)
        if not raw:
            return {}
        f = AtlasEngine._decay_factor(float(raw.get("ts") or 0.0), t)
        out: Dict[str, float] = {}
        for sect, val in (raw.get("inf") or {}).items():
            v = float(val) * f
            if v >= ATLAS_PRUNE_BELOW:
                out[sect] = v
        return out

    @staticmethod
    def _write_region(region: str, inf: Dict[str, float], now: float) -> None:
        """本引擎专属键的整值写回（写前已在调用处完成衰减结算，故非覆盖他人数据）"""
        clean = {
            str(s): float(v) for s, v in inf.items() if s in SECTS_CONFIG and v > 0
        }
        WorldStateRepository.set(
            ATLAS_STATE_PREFIX + str(region), {"inf": clean, "ts": float(now)}
        )

    @staticmethod
    def region_map(now: Optional[float] = None) -> Dict[str, Dict[str, float]]:
        return {r: AtlasEngine.influence_map(r, now) for r in _all_regions()}

    # ---------------- 主导判定 ----------------
    @staticmethod
    def dominant_sect(region: str, now: Optional[float] = None) -> Optional[str]:
        """主导 = 衰减后影响力 ≥ 门槛且严格独占最高；并列最高 → 无主"""
        inf = AtlasEngine.influence_map(region, now)
        if not inf:
            return None
        top = max(inf.values())
        # 门槛比较带容差：恰达 100 的影响力经衰减折算会有微亏，不得因此丢主导
        if top < ATLAS_DOMINANCE_THRESHOLD - ATLAS_THRESHOLD_TOLERANCE:
            return None
        leaders = [s for s, v in inf.items() if abs(v - top) <= _EPS]
        if len(leaders) != 1:
            return None
        return leaders[0]

    # ---------------- 每日上限（角色+区域+日期，trade_reg 先例） ----------------
    @staticmethod
    def _cap_used(char_id: str, region: str, ts: Optional[float] = None) -> int:
        try:
            st = WorldStateRepository.get(ATLAS_CAP_PREFIX + str(char_id))
            if not isinstance(st, dict) or st.get("date") != _day_str(ts):
                return 0
            vol = st.get("vol")
            if not isinstance(vol, dict):
                return 0
            return int(vol.get(region) or 0)
        except Exception:
            return 0

    @staticmethod
    def _cap_record(char_id: str, region: str, raw_points: int, ts: Optional[float] = None) -> None:
        if raw_points <= 0:
            return
        try:
            key = ATLAS_CAP_PREFIX + str(char_id)
            st = WorldStateRepository.get(key)
            vol: Dict[str, int] = {}
            if (
                isinstance(st, dict)
                and st.get("date") == _day_str(ts)
                and isinstance(st.get("vol"), dict)
            ):
                vol = dict(st["vol"])
            vol[region] = int(vol.get(region) or 0) + int(raw_points)
            WorldStateRepository.set(key, {"date": _day_str(ts), "vol": vol})
        except Exception:
            pass  # 记量失败降级（与 trade_reg 同口径，不阻断主流程）

    # ---------------- 计分入口（钩子） ----------------
    @staticmethod
    def record_activity(
        char: Optional[Character],
        kind: str,
        location: Optional[str] = None,
        now: Optional[float] = None,
    ) -> float:
        """成员活动结算计分；返回实际入账影响力（0 = 未计）。异常全吞，永不阻断主结算。"""
        try:
            if char is None:
                return 0.0
            sect = char.sect
            if not sect or sect not in SECTS_CONFIG:
                return 0.0
            base = ATLAS_POINTS.get(kind)
            if not base:
                return 0.0
            t = now if now is not None else time.time()
            if char.status == CharacterStatus.DEAD or char.lifespan.is_dead(t):
                return 0.0
            region = _region_of(location if location is not None else char.location)
            npc = _is_npc(char)
            cap = ATLAS_DAILY_CAP_NPC if npc else ATLAS_DAILY_CAP_PLAYER
            used = AtlasEngine._cap_used(char.id, region, t)
            allowed = min(int(base), max(0, cap - used))
            if allowed <= 0:
                return 0.0
            gain = allowed * (ATLAS_NPC_WEIGHT if npc else 1.0)
            inf = AtlasEngine.influence_map(region, t)
            inf[sect] = inf.get(sect, 0.0) + gain
            AtlasEngine._write_region(region, inf, t)
            AtlasEngine._cap_record(char.id, region, allowed, t)
            return float(gain)
        except Exception:
            return 0.0

    @staticmethod
    def record_council(sect: str, now: Optional[float] = None) -> float:
        """议政通过计分：落本宗总坛区域，组织级、不占个人上限。
        now 缺省取真实墙钟——调用方（议政结算）不得透传其注入的逻辑时刻。"""
        try:
            if sect not in SECTS_CONFIG:
                return 0.0
            t = now if now is not None else time.time()
            region = _region_of(SECTS_CONFIG[sect].get("headquarters"))
            inf = AtlasEngine.influence_map(region, t)
            inf[sect] = inf.get(sect, 0.0) + float(ATLAS_POINTS_COUNCIL)
            AtlasEngine._write_region(region, inf, t)
            return float(ATLAS_POINTS_COUNCIL)
        except Exception:
            return 0.0

    # ---------------- 价格效果（market 成交点调用） ----------------
    @staticmethod
    def discount_unit(
        unit_price: int, sect: Optional[str], region: str, now: Optional[float] = None
    ) -> int:
        """主导宗门成员成交单价：F03 市价 ×(1-折扣)，下限 1；非主导/异常原价返回"""
        try:
            unit = int(unit_price)
            if not sect or sect not in SECTS_CONFIG:
                return unit
            if AtlasEngine.dominant_sect(region, now) == sect:
                return max(1, int(unit * (1.0 - ATLAS_DISCOUNT_RATE)))
            return unit
        except Exception:
            return int(unit_price)

    # ---------------- 查询面板 ----------------
    @staticmethod
    def _resolve_region(arg: str) -> Optional[str]:
        arg = (arg or "").strip()
        if not arg:
            return None
        regions = _all_regions()
        if arg in regions:
            return arg
        for r in regions:
            if arg in r or r in arg:
                return r
        # 地点名 → 归区（region_of 对未知地点回退基准区，故须先验地点存在）
        from config import WORLD_LOCATIONS

        if arg in WORLD_LOCATIONS:
            return _region_of(arg)
        return None

    @staticmethod
    def panel_text(
        char: Optional[Character],
        region_arg: Optional[str] = None,
        now: Optional[float] = None,
    ) -> str:
        t = now if now is not None else time.time()
        my_sect = char.sect if char is not None else None
        if region_arg:
            region = AtlasEngine._resolve_region(region_arg)
            if region is None:
                return (
                    f"【天下版图】未闻【{region_arg}】之地。可查区域："
                    + "、".join(_all_regions())
                    + "（或任一地点名）。"
                )
            return AtlasEngine._region_text(region, my_sect, t)
        lines = [
            "【天下版图】宗门声威所及之地（影响力逾百且独占鳌头者主导一方；声威随日衰减，七日半衰）",
        ]
        if my_sect:
            lines.append(f"本宗：【{my_sect}】——主导区域内向商会购货享九五折。")
        else:
            lines.append("你乃散修，无宗门声威可仗；入宗后活动自会为本宗扬名。")
        for region in _all_regions():
            inf = AtlasEngine.influence_map(region, t)
            dom = AtlasEngine.dominant_sect(region, t)
            mine = inf.get(my_sect) if my_sect else None
            mine_txt = f"{mine:.1f}" if mine else "—"
            if dom:
                dom_txt = f"主导【{dom}】{inf.get(dom, 0.0):.1f}"
            elif inf:
                lead = max(inf.items(), key=lambda kv: kv[1])
                dom_txt = (
                    f"无主（最高【{lead[0]}】{lead[1]:.1f}，"
                    f"未逾门槛 {ATLAS_DOMINANCE_THRESHOLD:.0f}）"
                )
            else:
                dom_txt = "无主（尚无宗门声威）"
            lines.append(f"◆ {region}：{dom_txt} · 本宗 {mine_txt}")
            if dom and my_sect and dom == my_sect:
                lines.append("　　声威所及，此地散修慕名投宗者众。")
        lines.append("用法：/版图 <区域或地点> 看区域明细排名。")
        return "\n".join(lines)

    @staticmethod
    def _region_text(region: str, my_sect: Optional[str], now: float) -> str:
        inf = AtlasEngine.influence_map(region, now)
        dom = AtlasEngine.dominant_sect(region, now)
        lines = [
            f"【版图 · {region}】主导门槛 {ATLAS_DOMINANCE_THRESHOLD:.0f}（影响力随日衰减）"
        ]
        if not inf:
            lines.append("此地尚无宗门声威——处女地，先到先得。")
        else:
            rows = sorted(inf.items(), key=lambda kv: (-kv[1], kv[0]))
            for i, (sect, val) in enumerate(rows, 1):
                tags = []
                if sect == dom:
                    tags.append("主导")
                if sect == my_sect:
                    tags.append("本宗")
                tag_txt = f"（{'·'.join(tags)}）" if tags else ""
                lines.append(f"{i}. 【{sect}】{val:.1f}{tag_txt}")
        if dom:
            lines.append(
                f"【{dom}】主导此地：其门人在此向商会购货享九五折"
                + ("；声威所及，散修慕名投宗者众。" if dom == my_sect else "。")
            )
        else:
            lines.append("此地暂无主导宗门：购货无版图折扣。")
        return "\n".join(lines)
