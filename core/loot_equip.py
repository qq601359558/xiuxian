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
    SLOT_CN = {"weapon": "本命法宝", "armor": "防身道袍", "trinket": "道心灵佩"}

    @staticmethod
    def equip(c: Character, item_name: str) -> Dict[str, Any]:
        raw_name = (item_name or "").strip()
        if not raw_name:
            return {"success": False, "message": "用法：/穿戴 <装备名>（可先通过 /道身 或纳戒查看）"}

        from core.items import ItemKind, ItemFactory

        # 优先在 Core-V2 实体列表中寻找
        entity = c.find_item(raw_name)
        name = entity.name if entity else raw_name

        # 若实体未找到，则在 legacy inventory 中做模糊匹配
        if not entity:
            if name not in c.inventory:
                for x in c.inventory:
                    if name in x or x in name:
                        name = x
                        entity = c.find_item(name)
                        break

        # 检查是否在身上的已装备列表中
        if name in c.equipped:
            return {"success": False, "message": f"法宝【{name}】已佩戴在身。"}

        # 核实背包是否持有该道具
        if not entity and name not in c.inventory:
            return {"success": False, "message": f"百宝纳戒中并无【{raw_name}】。"}

        cfg = ITEM_CATALOG.get(name) or {}
        is_entity_equip = entity is not None and entity.kind == ItemKind.EQUIP
        is_name_equip = any(w in name for w in ("剑", "戈", "刃", "枪", "甲", "袍", "衣", "佩", "珠", "符", "戒", "宝"))
        if not is_entity_equip and cfg.get("kind") != "equip" and not is_name_equip:
            return {"success": False, "message": f"【{name}】非护道法宝，不可佩戴入体。"}

        # 若缺失实体则补齐，确保 Core-V2 一等公民地位
        if entity is None:
            entity = ItemFactory.from_legacy_name(name)
            c.items.append(entity)

        # 识别槽位
        slot = entity.slot or cfg.get("slot")
        if not slot:
            if any(w in name for w in ("甲", "袍", "衣")):
                slot = "armor"
            elif any(w in name for w in ("佩", "珠", "符", "戒")):
                slot = "trinket"
            else:
                slot = "weapon"
        entity.slot = slot

        grade = entity.tier_name if entity else (cfg.get("grade") or "凡品")
        bonus = float(cfg.get("power_bonus") or (0.05 * (entity.tier if entity else 1)))

        # 同槽替换逻辑：确保旧装备实体完好保留在 c.items，并回退至 c.inventory
        replaced: List[str] = []
        keep: List[str] = []
        for eq in c.equipped:
            eq_entity = c.find_item(eq)
            eq_cfg = ITEM_CATALOG.get(eq) or {}
            eq_slot = (eq_entity.slot if eq_entity and eq_entity.slot else None) or eq_cfg.get("slot")
            if not eq_slot:
                if any(w in eq for w in ("甲", "袍", "衣")):
                    eq_slot = "armor"
                elif any(w in eq for w in ("佩", "珠", "符", "戒")):
                    eq_slot = "trinket"
                else:
                    eq_slot = "weapon"

            if eq_slot == slot:
                replaced.append(eq)
                # 确保卸下的法宝实体依然安好在 c.items 中
                if eq_entity is None:
                    eq_entity = ItemFactory.from_legacy_name(eq)
                    c.items.append(eq_entity)
                if eq not in c.inventory:
                    c.inventory.append(eq)
            else:
                keep.append(eq)

        c.equipped = keep
        while name in c.inventory:
            c.inventory.remove(name)
        c.equipped.append(name)

        slot_cn = EquipEngine.SLOT_CN.get(slot, slot)
        msg = f"【法宝入体】佩戴{grade}·【{name}】（{slot_cn}），周天战力提升 {int(bonus*100)}%。"
        if entity and entity.affixes:
            msg += f" 激发护道词缀：{'、'.join(a.name for a in entity.affixes)}。"
        if replaced:
            msg += f" 道身法宝同槽替换，原法宝【{'、'.join(replaced)}】已妥善纳归百宝纳戒。"
        return {"success": True, "message": msg, "slot": slot, "grade": grade}

    @staticmethod
    def unequip(c: Character, item_name: str) -> Dict[str, Any]:
        raw_name = (item_name or "").strip()
        if not raw_name:
            return {"success": False, "message": "用法：/卸下 <装备名>"}

        target = None
        if raw_name in c.equipped:
            target = raw_name
        else:
            for x in c.equipped:
                if raw_name in x or x in raw_name:
                    target = x
                    break
        if not target:
            return {"success": False, "message": f"道身之上并无佩戴【{raw_name}】。"}

        c.equipped.remove(target)
        # 确保卸下的法宝实体完好留存
        entity = c.find_item(target)
        if entity is None:
            from core.items import ItemFactory
            entity = ItemFactory.from_legacy_name(target)
            c.add_item_entity(entity)
        if target not in c.inventory:
            c.inventory.append(target)

        return {"success": True, "message": f"【卸下法宝】收敛道韵，已将【{target}】从身上卸下，妥善纳归百宝纳戒。"}

    @staticmethod
    def power_bonus(c: Character) -> float:
        """按品阶与实体词缀累加，上限 +30%"""
        total = 0.0
        for eq in getattr(c, "equipped", None) or []:
            entity = c.find_item(eq)
            if entity and entity.kind == ItemKind.EQUIP:
                total += 0.05 * entity.tier
                for aff in getattr(entity, "affixes", []):
                    if getattr(aff, "stat_key", "") in ("power", "pierce"):
                        total += getattr(aff, "value", 0.0)
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
