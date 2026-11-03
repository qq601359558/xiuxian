"""
灵田/洞府经营（F06）：开辟洞府 → 播种 → 墙钟生长 → 收获；洞府等级给闭关小幅加成
规则权威：成本、生长时长、产量、加成全部在此裁决；叙事只用本地模板，不依赖 AI。
Spec：docs/compose/spec/farm.md
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import WORLD_LOCATIONS
from core.models import Character, CharacterStatus, FarmPlot

# ==================== 常量（对照坊市物价校准，见 spec 校准表） ====================
CAVE_MAX_LEVEL = 3                # 洞府等级封顶
CAVE_OPEN_COST = 300              # 开辟（至 1 级）灵石：聚气丹价 40 的 7.5 倍，中前期目标
CAVE_UPGRADE_COST = {2: 500, 3: 900}   # 升至该等级的灵石成本（递增）
CAVE_PLOTS_PER_LEVEL = 2          # 地块数 = 等级 × 2（2/4/6）
CAVE_MEDITATION_BONUS = {1: 0.02, 2: 0.04, 3: 0.05}   # 闭关修为加成（表驱动，硬顶 +5%）
CAVE_WITHER_SECONDS = 86400       # 成熟后 24h 起过熟：产量 -1（下限 1），不枯死

# 作物表：种子名 → 产出物 / 生长秒 / 产量区间（种子与产出物条目在 config.ITEM_CATALOG）
FARM_CROPS: Dict[str, Dict[str, Any]] = {
    "灵谷种子": {"output": "灵谷", "grow_seconds": 1800, "yield_min": 2, "yield_max": 3},
    "聚灵草种子": {"output": "聚灵草", "grow_seconds": 3600, "yield_min": 2, "yield_max": 3},
    "灵芝种子": {"output": "百年灵芝", "grow_seconds": 14400, "yield_min": 1, "yield_max": 2},
}


def plots_capacity(c: Character) -> int:
    """地块总数（由洞府等级推导）"""
    lv = max(0, min(CAVE_MAX_LEVEL, int(getattr(c, "cave_level", 0) or 0)))
    return lv * CAVE_PLOTS_PER_LEVEL


def meditation_mult(c: Character) -> float:
    """闭关洞府加成乘子：无洞府恒 1.0（旧行为）；有洞府 1 + 表值（硬顶 +5%）"""
    lv = int(getattr(c, "cave_level", 0) or 0)
    if lv <= 0:
        return 1.0
    return 1.0 + CAVE_MEDITATION_BONUS.get(min(lv, CAVE_MAX_LEVEL), 0.0)


def _plots(c: Character) -> List[FarmPlot]:
    """地块列表惰性对齐到当前容量：只补空地块，永不截断（等级不下降，已有作物必保留）"""
    cap = plots_capacity(c)
    plots = list(getattr(c, "farm_plots", None) or [])
    while len(plots) < cap:
        plots.append(FarmPlot())
    c.farm_plots = plots
    return plots


def split_sow_args(tokens: List[str]) -> Tuple[str, int]:
    """/播种 参数解析（双端共用）：末 token 为正整数时拆作数量，其余整体为种子名"""
    toks = [t for t in (tokens or []) if t != ""]
    if len(toks) >= 2 and toks[-1].isdigit() and int(toks[-1]) > 0:
        return " ".join(toks[:-1]), int(toks[-1])
    return " ".join(toks), 1


def _fmt_duration(seconds: float) -> str:
    s = int(max(0, seconds))
    if s >= 3600:
        return f"{s // 3600} 小时 {s % 3600 // 60} 分"
    if s >= 60:
        return f"{s // 60} 分 {s % 60} 秒"
    return f"{s} 秒"


def _manage_block(c: Character) -> str:
    """管理类指令的统一门禁（查看不走此门）：死亡/闭关均拒绝"""
    if c.status == CharacterStatus.DEAD:
        return "身死道消，洞府灵田已随旧世荒废。"
    if c.status == CharacterStatus.MEDITATING:
        return "【闭关锁门】入定之中六识封闭，不可打理灵田；可 /出关 后再试（/洞府 查看不受限）。"
    return ""


class FarmEngine:
    """洞府灵田规则单点：双端（server/cli）共用，成功才由上层落库"""

    # ---------------- 开辟 / 升级 ----------------
    @staticmethod
    def open_cave(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        block = _manage_block(c)
        if block:
            return {"success": False, "message": block}
        if int(getattr(c, "cave_level", 0) or 0) >= 1:
            return {"success": False, "message": f"道友已有 {c.cave_level} 级洞府，无需重复开辟。可用 /升级洞府 提升。"}
        loc = WORLD_LOCATIONS.get(c.location, {})
        if not loc.get("is_safe"):
            return {
                "success": False,
                "message": f"【{c.location}】并非安全之地，灵脉不稳、易招觊觎，不可在此开辟洞府。请先 /前往 坊市或宗门驻地。",
            }
        if c.spirit_stones < CAVE_OPEN_COST:
            return {
                "success": False,
                "message": f"开辟洞府需 {CAVE_OPEN_COST} 灵石（布阵、固脉、立府），囊中仅有 {c.spirit_stones}。",
            }
        c.spirit_stones -= CAVE_OPEN_COST
        c.cave_level = 1
        plots = _plots(c)
        bonus = int(CAVE_MEDITATION_BONUS[1] * 100)
        return {
            "success": True,
            "message": (
                f"【开辟洞府】于【{c.location}】引脉结庐，洞府初成（1 级），付灵石 {CAVE_OPEN_COST}。\n"
                f"· 灵田 {len(plots)} 块，可 /播种 <种子名> 耕作（种子在 /坊市 有售）。\n"
                f"· 洞府清气养神：今后闭关修为 +{bonus}%。"
            ),
        }

    @staticmethod
    def upgrade_cave(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        block = _manage_block(c)
        if block:
            return {"success": False, "message": block}
        lv = int(getattr(c, "cave_level", 0) or 0)
        if lv <= 0:
            return {"success": False, "message": "尚无洞府，请先身处安全区 /开辟。"}
        if lv >= CAVE_MAX_LEVEL:
            return {"success": False, "message": f"洞府已臻 {CAVE_MAX_LEVEL} 级圆满，无可再升。"}
        cost = CAVE_UPGRADE_COST[lv + 1]
        if c.spirit_stones < cost:
            return {
                "success": False,
                "message": f"升级至 {lv + 1} 级洞府需 {cost} 灵石（扩田、固阵），囊中仅有 {c.spirit_stones}。",
            }
        c.spirit_stones -= cost
        c.cave_level = lv + 1
        plots = _plots(c)
        bonus = int(CAVE_MEDITATION_BONUS[c.cave_level] * 100)
        return {
            "success": True,
            "message": (
                f"【洞府升级】洞府升至 {c.cave_level} 级，付灵石 {cost}。\n"
                f"· 灵田扩至 {len(plots)} 块（原有作物不受影响）。\n"
                f"· 闭关修为加成升至 +{bonus}%。"
            ),
        }

    # ---------------- 播种 ----------------
    @staticmethod
    def sow(c: Character, seed_hint: str, count: int = 1,
            now: Optional[float] = None) -> Dict[str, Any]:
        block = _manage_block(c)
        if block:
            return {"success": False, "message": block}
        if int(getattr(c, "cave_level", 0) or 0) <= 0:
            return {"success": False, "message": "尚无洞府灵田，请先身处安全区 /开辟。"}
        hint = (seed_hint or "").strip()
        if not hint:
            return {"success": False, "message": "用法：/播种 <种子名> [数量]（种子在 /坊市 购买后入囊）"}
        inv = list(getattr(c, "inventory", None) or [])
        exact = [n for n in inv if n == hint]
        fuzzy = [n for n in inv if hint in n]
        candidates = exact or fuzzy
        if not candidates:
            return {"success": False, "message": f"行囊中并无【{hint}】。灵田种子可在 /坊市 购买（灵谷种子/聚灵草种子/灵芝种子）。"}
        seed_name = next((n for n in candidates if n in FARM_CROPS), None)
        if seed_name is None:
            return {
                "success": False,
                "message": f"【{candidates[0]}】不是可播种的种子。可播种：{'、'.join(FARM_CROPS)}。",
            }
        plots = _plots(c)
        empty = [p for p in plots if not p.crop]
        have = inv.count(seed_name)
        want = max(1, int(count or 1))
        n = min(want, have, len(empty))
        if n <= 0:
            return {"success": False, "message": "灵田已无空地，请先 /收获 已成熟作物，或 /升级洞府 扩田。"}
        t = time.time() if now is None else now
        cfg = FARM_CROPS[seed_name]
        for p in empty[:n]:
            p.crop = seed_name
            p.planted_at = t
            p.matures_at = t + cfg["grow_seconds"]
            c.inventory.remove(seed_name)
        msg = (
            f"【播种】在 {n} 块灵田播下【{seed_name}】，约 {_fmt_duration(cfg['grow_seconds'])} 后可收【{cfg['output']}】。"
        )
        if n < want:
            reason = "种子不足" if have < want else "空地不足"
            msg += f"\n· 只播了 {n}/{want} 块（{reason}），余者待补。"
        return {"success": True, "message": msg, "sown": n}

    # ---------------- 收获 ----------------
    @staticmethod
    def harvest(c: Character, now: Optional[float] = None,
                rng: Optional[random.Random] = None) -> Dict[str, Any]:
        block = _manage_block(c)
        if block:
            return {"success": False, "message": block}
        if int(getattr(c, "cave_level", 0) or 0) <= 0:
            return {"success": False, "message": "尚无洞府灵田，请先身处安全区 /开辟。"}
        t = time.time() if now is None else now
        r = rng or random
        plots = _plots(c)
        mature = [p for p in plots if p.crop and p.matures_at <= t]
        if not mature:
            growing = [p for p in plots if p.crop]
            if not growing:
                return {"success": False, "message": "田中空空，并无作物可收。先 /播种 吧。"}
            nearest = min(p.matures_at for p in growing)
            return {
                "success": False,
                "message": f"尚无成熟作物，最早一茬还需 {_fmt_duration(nearest - t)}。可用 /洞府 查看长势。",
            }
        gained: Dict[str, int] = {}
        notes: List[str] = []
        for p in mature:
            cfg = FARM_CROPS.get(p.crop) or {}
            out = cfg.get("output") or p.crop
            n = int(r.randint(int(cfg.get("yield_min", 1)), int(cfg.get("yield_max", 1))))
            overripe = t > p.matures_at + CAVE_WITHER_SECONDS
            if overripe:
                n = max(1, n - 1)
                notes.append(f"【{out}】过熟减产")
            for _ in range(n):
                c.inventory.append(out)
            gained[out] = gained.get(out, 0) + n
            p.crop = ""
            p.planted_at = 0.0
            p.matures_at = 0.0
        parts = "、".join(f"{name}×{num}" for name, num in gained.items())
        msg = f"【收获】灵田收成：{parts}，已入行囊。"
        if notes:
            msg += "\n· " + "；".join(notes) + "（成熟后 24 小时未收，过熟减产 1）。"
        return {"success": True, "message": msg, "gained": gained}

    # ---------------- 死亡 ----------------
    @staticmethod
    def on_owner_death(c: Character) -> None:
        """主人坐化：田中作物尽数荒废（地块清空）；等级保留在旧世记录上仅作遗容"""
        for p in list(getattr(c, "farm_plots", None) or []):
            p.crop = ""
            p.planted_at = 0.0
            p.matures_at = 0.0

    # ---------------- 面板 / 摘要 ----------------
    @staticmethod
    def cave_summary(c: Character, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """_status_dict 摘要（纯新增字段用）：无洞府返回 None"""
        lv = int(getattr(c, "cave_level", 0) or 0)
        if lv <= 0:
            return None
        t = time.time() if now is None else now
        plots = list(getattr(c, "farm_plots", None) or [])
        used = [p for p in plots if p.crop]
        return {
            "level": lv,
            "plots_total": plots_capacity(c),
            "plots_used": len(used),
            "mature": len([p for p in used if p.matures_at <= t]),
        }

    @staticmethod
    def panel_text(c: Character, now: Optional[float] = None) -> str:
        t = time.time() if now is None else now
        lv = int(getattr(c, "cave_level", 0) or 0)
        if lv <= 0:
            loc = WORLD_LOCATIONS.get(c.location, {})
            here = "此地正是安全区，可直接 /开辟" if loc.get("is_safe") else "此地非安全区，须先 /前往 坊市或宗门驻地"
            return (
                "【洞府灵田】尚未开辟洞府。\n"
                f"· 开辟需 {CAVE_OPEN_COST} 灵石（身处安全区时 /开辟）；{here}。\n"
                "· 洞府内设灵田种灵草，等级越高田越多，闭关也越快（最高 +5%）。"
            )
        plots = _plots(c)
        bonus = int(CAVE_MEDITATION_BONUS.get(min(lv, CAVE_MAX_LEVEL), 0) * 100)
        lines = []
        if c.status == CharacterStatus.DEAD:
            lines.append("【洞府灵田】主人已坐化，洞府灵田随旧世荒废（遗容）。")
        lines.append(f"【洞府灵田】{lv} 级洞府 · 灵田 {len(plots)} 块 · 闭关修为 +{bonus}%")
        if lv < CAVE_MAX_LEVEL:
            lines.append(f"· 升级至 {lv + 1} 级需 {CAVE_UPGRADE_COST[lv + 1]} 灵石（/升级洞府）：灵田 {CAVE_PLOTS_PER_LEVEL * (lv + 1)} 块。")
        else:
            lines.append("· 洞府已臻圆满。")
        for i, p in enumerate(plots, 1):
            if not p.crop:
                lines.append(f"· 田 {i}：空闲（/播种 <种子名>）")
                continue
            cfg = FARM_CROPS.get(p.crop) or {}
            out = cfg.get("output") or p.crop
            if p.matures_at <= t:
                if t > p.matures_at + CAVE_WITHER_SECONDS:
                    lines.append(f"· 田 {i}：【{out}】已成熟 · 过熟（再不收将减产，/收获）")
                else:
                    lines.append(f"· 田 {i}：【{out}】已成熟（/收获）")
            else:
                lines.append(f"· 田 {i}：【{out}】生长中，余 {_fmt_duration(p.matures_at - t)}")
        return "\n".join(lines)
