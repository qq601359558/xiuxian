"""
纪元天象主题（F13）：每纪元一个主题，对全服施加恰好一项小幅规则修正。

设计要点（docs/compose/spec/season-theme.md）：
- 主题 = 纪元编号的纯函数（轮转表取模），跨进程/玩家推导一致，零落库；
- 三通道单点接入：闭关灵气（settle_meditation 连乘链末端）、坊市价格
  （MarketEngine._price_for_region）、世界事件权重（EventEngine.pick_type）；
- 未被当前主题选中的通道恒为中性；调用方对本模块异常一律回退中性，
  本模块的播报路径内部亦不抛错给查询路径。
- 第 1 纪元刻意落在静默纪元（全中性），保证上线首纪元旧行为逐值不变。
"""
from __future__ import annotations

import time
from datetime import date as _date
from datetime import datetime as _datetime
from typing import Any, Dict, Optional

from config import EVENT_WEIGHTS
from core.season import season_info

# ---------------- 常量（规则定死，AI 不参与） ----------------
# 灵气/价格通道倍率封顶 [0.95, 1.05]；事件权重单类倍率 1.25（仅相对占比）
SEASON_THEME_QI_UP = 1.05
SEASON_THEME_QI_DOWN = 0.95
SEASON_THEME_PRICE_UP = 1.05
SEASON_THEME_EVENT_WEIGHT_MULT = 1.25

# 轮转表：theme = ROTATION[season_number % len(ROTATION)]
# ⚠ 约束：表项只可追加/整体换版，禁止改动既有下标对应的主题，
# 否则历史纪元的主题推导会漂移。六主题互不相同 ⇒ 相邻纪元主题必不同。
# 下标 1 = 静默纪元：第 1 纪元（season_number=1）落于此，全中性。
SEASON_THEME_ROTATION = [
    {
        "key": "blood_moon",
        "name": "血月纪元",
        "channel": "events",
        "event_type": "crisis",
        "desc": "血月当空，凶煞滋盛，行路危机更频。",
        "effect_text": "世界事件「危机」权重 ×1.25",
        "announce": "血月升空，煞气漫野——本纪元危机更频，诸道友行路珍重。",
    },
    {
        "key": "silence",
        "name": "静默纪元",
        "channel": "none",
        "desc": "天象沉静，天地无言，本纪元无天象加身。",
        "effect_text": "无天象修正",
        "announce": "天象沉静如水——本纪元无象加身，修行一如往常。",
    },
    {
        "key": "spirit_rain",
        "name": "灵雨纪元",
        "channel": "meditation",
        "mult": SEASON_THEME_QI_UP,
        "desc": "灵雨绵绵，万物吐纳皆沾润泽。",
        "effect_text": "闭关修为产出 ×1.05",
        "announce": "灵雨初降，润泽苍生——本纪元闭关吐纳修为 +5%。",
    },
    {
        "key": "red_glow",
        "name": "赤霞纪元",
        "channel": "events",
        "event_type": "fortune",
        "desc": "赤霞漫天，机缘频现于山野市井之间。",
        "effect_text": "世界事件「机缘」权重 ×1.25",
        "announce": "赤霞漫天，机缘频现——本纪元行路多遇机缘。",
    },
    {
        "key": "golden_wind",
        "name": "金风纪元",
        "channel": "price",
        "mult": SEASON_THEME_PRICE_UP,
        "desc": "金风送爽，商货增值，坊市物价整体微扬。",
        "effect_text": "坊市市价 ×1.05（买卖同源）",
        "announce": "金风起兮商货贵——本纪元坊市市价整体上浮 5%。",
    },
    {
        "key": "cold_tide",
        "name": "寒潮纪元",
        "channel": "meditation",
        "mult": SEASON_THEME_QI_DOWN,
        "desc": "寒潮封山，灵机凝滞，吐纳事倍功半。",
        "effect_text": "闭关修为产出 ×0.95",
        "announce": "寒潮压境，灵机凝滞——本纪元闭关吐纳修为 -5%。",
    },
]

ANNOUNCED_KEY = "season_theme_announced"


class SeasonThemeEngine:
    """纪元天象：纯函数推导 + 三通道修正 + 面板/播报"""

    # ---------------- 推导 ----------------
    @staticmethod
    def theme_for_season(season_number: int) -> Dict[str, Any]:
        """纪元编号 → 主题（纯函数，同号恒同主题）"""
        try:
            n = int(season_number)
        except (TypeError, ValueError):
            n = 1
        # 返回浅拷贝：防调用方误写返回 dict 污染全进程轮转表
        return dict(SEASON_THEME_ROTATION[n % len(SEASON_THEME_ROTATION)])

    @staticmethod
    def theme_at(now: Optional[float] = None) -> Dict[str, Any]:
        info = season_info(now)
        theme = SeasonThemeEngine.theme_for_season(info["season_number"])
        return {"season": info, "theme": theme}

    @staticmethod
    def current_theme(now: Optional[float] = None) -> Dict[str, Any]:
        return SeasonThemeEngine.theme_at(now)["theme"]

    # ---------------- 三通道修正（未选中恒中性） ----------------
    @staticmethod
    def meditation_mult(now: Optional[float] = None) -> float:
        theme = SeasonThemeEngine.current_theme(now)
        if theme.get("channel") == "meditation":
            return float(theme.get("mult") or 1.0)
        return 1.0

    @staticmethod
    def price_mult(now: Optional[float] = None) -> float:
        theme = SeasonThemeEngine.current_theme(now)
        if theme.get("channel") == "price":
            return float(theme.get("mult") or 1.0)
        return 1.0

    @staticmethod
    def price_mult_for_day(day: Optional[str] = None) -> float:
        """按日期锚定：取该日期正午所属纪元的主题价系数（day=None → 今天）"""
        try:
            if day:
                d = _date.fromisoformat(str(day)[:10])
            else:
                d = _date.today()
            ts = _datetime(d.year, d.month, d.day, 12, 0, 0).timestamp()
        except Exception:
            ts = time.time()
        return SeasonThemeEngine.price_mult(ts)

    @staticmethod
    def event_weights(now: Optional[float] = None) -> Dict[str, float]:
        """返回修正后的权重副本（不改 config 原表）；中性时与原表逐值相等"""
        weights = dict(EVENT_WEIGHTS)
        theme = SeasonThemeEngine.current_theme(now)
        if theme.get("channel") == "events":
            etype = theme.get("event_type")
            if etype in weights:
                weights[etype] = float(weights[etype]) * SEASON_THEME_EVENT_WEIGHT_MULT
        return weights

    # ---------------- 可见性 ----------------
    @staticmethod
    def summary(now: Optional[float] = None) -> Dict[str, Any]:
        """status 透出用摘要（纯加法字段 season_theme 的值）"""
        ctx = SeasonThemeEngine.theme_at(now)
        theme = ctx["theme"]
        return {
            "name": theme["name"],
            "key": theme["key"],
            "effect": theme["effect_text"],
            "season_number": ctx["season"]["season_number"],
        }

    @staticmethod
    def panel_text(now: Optional[float] = None) -> str:
        ctx = SeasonThemeEngine.theme_at(now)
        info, theme = ctx["season"], ctx["theme"]
        lines = [
            f"【天象】第 {info['season_number']} 纪元 · {theme['name']}",
            theme["desc"],
            f"天象修正：{theme['effect_text']}",
            f"本纪元余约 {info['remain_real_days']:.1f} 天（共 {info['total_days']} 天），换季则天象轮转。",
        ]
        return "\n".join(lines)

    # ---------------- 开季播报（惰性、幂等） ----------------
    @staticmethod
    def ensure_announced(now: Optional[float] = None) -> bool:
        """当前纪元尚未播报过则经世情通道播报一次；已播报返回 False。
        标记存 world_state（已播报的最大纪元号），重复触发不重播。
        任何存储/通道异常都降级为「未播报」而不抛错。"""
        try:
            from storage.db import WorldStateRepository

            info = season_info(now)
            season_no = int(info["season_number"])
            announced = WorldStateRepository.get(ANNOUNCED_KEY, 0)
            try:
                announced = int(announced or 0)
            except (TypeError, ValueError):
                announced = 0
            if season_no <= announced:
                return False
            theme = SeasonThemeEngine.theme_for_season(season_no)
            # 先写标记、后发播报（宁漏勿重）：防存储故障/双进程并发首查时重播刷屏；
            # 标记已写而消息落库失败则该纪元漏播一次（表象损失，/天象 随时可查）
            WorldStateRepository.set(ANNOUNCED_KEY, season_no)
            from core.world_channel import WorldChannel

            WorldChannel.post(
                "season_theme",
                f"【天象】第 {season_no} 纪元 · {theme['name']}：{theme['announce']}",
                level="epic",
                actor="天道",
                now=now,
                skip_limit=True,
            )
            return True
        except Exception:
            return False
