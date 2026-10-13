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
from core.items import ItemKind



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
        from core.items import ItemKind
        entity = c.find_item(name)
        cfg = ITEM_CATALOG.get(name) or {}
        is_entity_equip = entity is not None and entity.kind == ItemKind.EQUIP
        if not is_entity_equip and cfg.get("kind") != "equip":
            return {"success": False, "message": f"【{name}】不是可穿戴的装备。"}
        if name in c.equipped:
            return {"success": False, "message": f"【{name}】已在身上。"}

        slot = (entity.slot if entity and entity.slot else None) or cfg.get("slot") or "weapon"
        grade = (entity.tier_name if entity else None) or cfg.get("grade") or "凡品"
        bonus = float(cfg.get("power_bonus") or (0.05 * (entity.tier if entity else 1)))

        # 同槽替换
        replaced = []
        keep = []
        for eq in c.equipped:
            eq_entity = c.find_item(eq)
            eq_cfg = ITEM_CATALOG.get(eq) or {}
            eq_slot = (eq_entity.slot if eq_entity and eq_entity.slot else None) or eq_cfg.get("slot") or "trinket"
            if eq_slot == slot:
                replaced.append(eq)
                c.inventory.append(eq)
            else:
                keep.append(eq)
        c.equipped = keep
        if name in c.inventory:
            c.inventory.remove(name)
        c.equipped.append(name)
        slot_cn = EquipEngine.SLOT_CN.get(slot, slot)
        msg = f"【穿戴】{grade}·{name}（{slot_cn}），战力 +{int(bonus*100)}%。"
        if entity and entity.affixes:
            msg += f" 激发词缀：{'、'.join(a.name for a in entity.affixes)}。"
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
        if name not in c.inventory:
            c.inventory.append(name)
        return {"success": True, "message": f"【卸下】收起【{name}】。"}

    @staticmethod
    def power_bonus(c: Character) -> float:
        """按品阶与实体词缀累加，上限 +30%"""
        total = 0.0
        for eq in getattr(c, "equipped", None) or []:
            entity = c.find_item(eq)
            if entity and entity.kind == ItemKind.EQUIP:
                total += 0.05 * entity.tier
                for aff in entity.affixes:
                    if aff.stat_key in ("power", "pierce"):
                        total += aff.value
            else:
                cfg = ITEM_CATALOG.get(eq) or {}
                total += float(cfg.get("power_bonus") or 0.03)
        return 1.0 + min(0.30, total)



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
