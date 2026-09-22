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
    """使用藏宝图挖宝（Core-V2 桥接层）"""

    @staticmethod
    def dig(
        c: Character,
        now: Optional[float] = None,
        choice_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from core.treasure_system import TreasureEngine
        return TreasureEngine.dig(c, now=now, choice_id=choice_id)



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
