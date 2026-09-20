"""
藏宝图挖宝 + 装备穿戴
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from config import ITEM_CATALOG, ADVENTURE_HERBS, ADVENTURE_PILLS
from core.models import Character, CharacterStatus
from core.combat import CombatEngine


def _is_equip(name: str) -> bool:
    cfg = ITEM_CATALOG.get(name) or {}
    return cfg.get("kind") == "equip"


class DigEngine:
    """使用藏宝图挖宝"""

    @staticmethod
    def dig(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，无宝可挖。"}
        if c.status == CharacterStatus.MEDITATING:
            return {"success": False, "message": "闭关中不可外出挖宝，请先 /出关。"}
        if "藏宝图" not in c.inventory:
            return {"success": False, "message": "行囊中并无藏宝图。可外出探险拾取或坊市购入。"}

        c.inventory.remove("藏宝图")
        # 规则骰
        r = random.random()
        if r < 0.45:
            stones = random.randint(80, 400 + c.realm.tier * 80)
            exp = random.randint(50, 200 + c.realm.tier * 40)
            c.spirit_stones += stones
            c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp)
            extra = ""
            if random.random() < 0.35:
                from config import DIG_RARE_PILLS
                # 主要凡品，小概率人/地品
                r2 = random.random()
                if r2 < 0.7:
                    pill = random.choice(ADVENTURE_PILLS)
                elif r2 < 0.95:
                    pill = "玄元聚气丹"
                else:
                    pill = random.choice(DIG_RARE_PILLS)
                c.inventory.append(pill)
                extra = f"，另得【{pill}】"
            return {
                "success": True,
                "outcome": "fortune",
                "message": (
                    f"【挖宝功成】循图至幽谷，掘出上古玉匣：灵石 +{stones}，修为 +{exp}{extra}。"
                ),
                "stones": stones,
                "exp": exp,
            }
        if r < 0.75:
            return {
                "success": True,
                "outcome": "empty",
                "message": "【空图】掘地三尺，唯余黄土。藏宝图作废。",
            }
        # 杀劫
        loss_exp = int(c.realm.current_exp * 0.1) + 15
        burn = round(random.uniform(0.3, 1.2), 2)
        c.realm.current_exp = max(0, c.realm.current_exp - loss_exp)
        c.lifespan.burn_lifespan(burn)
        return {
            "success": True,
            "outcome": "trap",
            "message": (
                f"【杀劫】图上标注竟是上古杀阵！破阵逃出，修为 -{loss_exp}，燃寿 {burn} 岁。"
            ),
            "exp": -loss_exp,
            "lifespan": -burn,
        }


class EquipEngine:
    SLOT_CN = {"weapon": "武器", "armor": "护甲", "trinket": "饰品"}

    @staticmethod
    def equip(c: Character, item_name: str) -> Dict[str, Any]:
        name = (item_name or "").strip()
        if not name:
            return {"success": False, "message": "用法：/穿戴 <装备名>（先 /道身 或 /坊市 看）"}
        if name not in c.inventory:
            for x in c.inventory:
                if name in x or x in name:
                    name = x
                    break
        if name not in c.inventory:
            return {"success": False, "message": f"行囊中无【{item_name}】。"}
        cfg = ITEM_CATALOG.get(name) or {}
        if cfg.get("kind") != "equip":
            return {"success": False, "message": f"【{name}】不是可穿戴的装备。"}
        if name in c.equipped:
            return {"success": False, "message": f"【{name}】已在身上。"}
        slot = cfg.get("slot") or "trinket"
        grade = cfg.get("grade") or "凡品"
        bonus = float(cfg.get("power_bonus") or 0.03)
        # 同槽替换
        replaced = []
        keep = []
        for eq in c.equipped:
            eq_cfg = ITEM_CATALOG.get(eq) or {}
            if (eq_cfg.get("slot") or "trinket") == slot:
                replaced.append(eq)
                c.inventory.append(eq)
            else:
                keep.append(eq)
        c.equipped = keep
        c.inventory.remove(name)
        c.equipped.append(name)
        slot_cn = EquipEngine.SLOT_CN.get(slot, slot)
        msg = f"【穿戴】{grade}·{name}（{slot_cn}），战力 +{int(bonus*100)}%。"
        if replaced:
            msg += f" 已替换卸下：{'、'.join(replaced)}。"
        return {"success": True, "message": msg, "slot": slot, "grade": grade}

    @staticmethod
    def unequip(c: Character, item_name: str) -> Dict[str, Any]:
        name = (item_name or "").strip()
        if name not in c.equipped:
            for x in c.equipped:
                if name in x or x in name:
                    name = x
                    break
        if name not in c.equipped:
            return {"success": False, "message": "身上并无此物。"}
        c.equipped.remove(name)
        c.inventory.append(name)
        return {"success": True, "message": f"【卸下】收起【{name}】。"}

    @staticmethod
    def power_bonus(c: Character) -> float:
        """按品阶累加，上限 +20%"""
        total = 0.0
        for eq in getattr(c, "equipped", None) or []:
            cfg = ITEM_CATALOG.get(eq) or {}
            total += float(cfg.get("power_bonus") or 0.03)
        return 1.0 + min(0.20, total)


def art_combat_bonus(c: Character) -> float:
    """功法神通对战力系数，最高 +20%"""
    best = 1.0
    for a in getattr(c, "custom_arts", None) or []:
        for sp in a.get("spells") or []:
            try:
                best = max(best, float(sp.get("multiplier") or 1.0))
            except Exception:
                continue
    return 1.0 + min(0.20, (best - 1.0) * 0.15)
