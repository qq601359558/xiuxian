"""
藏宝图挖宝 + 装备穿戴
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import ITEM_CATALOG, ADVENTURE_HERBS, ADVENTURE_PILLS
from core.models import Character, CharacterStatus
from core.combat import CombatEngine
from core.items import ItemKind



def _is_equip(name: str) -> bool:
    cfg = ITEM_CATALOG.get(name) or {}
    return cfg.get("kind") == "equip"


class DigEngine:
    """使用藏宝图挖宝（Core-V2 桥接层与自然奇遇支持）"""

    @staticmethod
    def dig(
        c: Character,
        now: Optional[float] = None,
        choice_id: Optional[str] = None,
        force_legacy: bool = False,
    ) -> Dict[str, Any]:
        if not force_legacy:
            from core.treasure_system import TreasureEngine

            res = TreasureEngine.dig(c, now=now, choice_id=choice_id)
            if res.get("success") or res.get("wrong_location") or res.get("need_choice"):
                return res
            if "藏宝图" not in c.inventory:
                return res

        t = now if now is not None else time.time()
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，无宝可挖。"}
        if c.status == CharacterStatus.MEDITATING:
            return {"success": False, "message": "闭关中不可外出挖宝，请先 /出关。"}
        if "藏宝图" not in c.inventory:
            return {"success": False, "message": "行囊中并无藏宝图。可外出探险拾取或坊市购入。"}

        c.inventory.remove("藏宝图")
        is_first_dig = not bool(getattr(c, "first_dig_omen_done", False))
        if is_first_dig:
            c.first_dig_omen_done = True

        # 首次使用藏宝图：必得掘宝机缘 + 100% 触发奇遇
        r = 0.10 if is_first_dig else random.random()
        if r < 0.45:
            stones = random.randint(80, 400 + c.realm.tier * 80)
            exp = random.randint(50, 200 + c.realm.tier * 40)
            c.spirit_stones += stones
            c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp)
            extra = ""
            if is_first_dig or random.random() < 0.35:
                from config import DIG_RARE_PILLS

                r2 = random.random()
                if r2 < 0.7:
                    pill = random.choice(ADVENTURE_PILLS)
                elif r2 < 0.95:
                    pill = "玄元聚气丹"
                else:
                    pill = random.choice(DIG_RARE_PILLS)
                c.inventory.append(pill)
                extra = f"，另得【{pill}】"
            res: Dict[str, Any] = {
                "success": True,
                "outcome": "fortune",
                "message": (
                    f"【挖宝功成】循图至幽谷，掘出上古玉匣：灵石 +{stones}，修为 +{exp}{extra}。"
                ),
                "stones": stones,
                "exp": exp,
            }
        elif r < 0.75:
            res = {
                "success": True,
                "outcome": "empty",
                "message": "【空图】掘地三尺，唯余黄土。藏宝图作废。",
            }
        else:
            loss_exp = int(c.realm.current_exp * 0.1) + 15
            burn = round(random.uniform(0.3, 1.2), 2)
            c.realm.current_exp = max(0, c.realm.current_exp - loss_exp)
            c.lifespan.burn_lifespan(burn)
            res = {
                "success": True,
                "outcome": "trap",
                "message": (
                    f"【险境】图上标注竟是古修残留禁制！破禁脱身，修为 -{loss_exp}，燃寿 {burn} 岁。"
                ),
                "exp": -loss_exp,
                "lifespan": -burn,
            }

        # 奇遇检定：本世首次挖宝 100% 触发；后续按 omen_chance()（生产 1% / 测试 30%）触发
        try:
            from core.omen_scene import maybe_trigger_natural_omen

            omen = maybe_trigger_natural_omen(c, context="按图挖宝", force=is_first_dig)
            if omen and omen.get("triggered"):
                res["omen_triggered"] = True
                res["first_dig_omen"] = is_first_dig
                res["omen_inline"] = bool(omen.get("omen_inline", True))
                res["omen_title"] = omen.get("omen_title") or omen.get("title")
                res["omen_choices"] = omen.get("omen_choices") or []
                res["message"] = res["message"] + "\n\n" + (omen.get("text") or "")
        except Exception:
            pass
        return res



class EquipEngine:
    SLOT_CN = {
        "weapon": "攻伐兵刃",
        "armor": "防身道袍",
        "trinket": "道心灵佩",
        "boots": "飞遁灵靴",
        "flying_treasure": "御空法宝",
    }

    @staticmethod
    def _detect_slot(name: str, cfg: Dict[str, Any], entity: Optional[Any] = None) -> str:
        slot = (entity.slot if entity and entity.slot else None) or cfg.get("slot")
        if slot:
            return slot
        if any(w in name for w in ("甲", "袍", "衣", "铠", "护腕")):
            return "armor"
        elif any(w in name for w in ("靴", "履", "鞋")):
            return "boots"
        elif any(w in name for w in ("舟", "梭", "鸢", "车", "舰", "翼")):
            return "flying_treasure"
        elif any(w in name for w in ("佩", "珠", "符", "戒", "镜", "锁", "坠")):
            return "trinket"
        return "weapon"

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
        is_name_equip = any(w in name for w in ("剑", "戈", "刃", "枪", "刺", "甲", "袍", "衣", "佩", "珠", "符", "戒", "宝", "靴", "履", "舟", "梭", "鸢", "幡", "铠", "镜", "锁", "坠"))
        if not is_entity_equip and cfg.get("kind") != "equip" and not is_name_equip:
            return {"success": False, "message": f"【{name}】非护道法宝，不可佩戴入体。"}

        # 核验佩戴门槛（境界/因果门槛）
        can_equip, reason = EquipEngine.check_equip_requirements(c, name)
        if not can_equip:
            return {"success": False, "message": reason}

        # 若缺失实体则补齐，确保 Core-V2 一等公民地位
        if entity is None:
            entity = ItemFactory.from_legacy_name(name)
            c.items.append(entity)

        # 识别槽位
        slot = EquipEngine._detect_slot(name, cfg, entity)
        entity.slot = slot

        grade = entity.tier_name if entity else (cfg.get("grade") or "凡品")
        bonus = float(cfg.get("power_bonus") or (0.05 * (entity.tier if entity else 1)))

        # 同槽替换逻辑：确保旧装备实体完好保留在 c.items，并回退至 c.inventory
        replaced: List[str] = []
        keep: List[str] = []
        for eq in c.equipped:
            eq_entity = c.find_item(eq)
            eq_cfg = ITEM_CATALOG.get(eq) or {}
            eq_slot = EquipEngine._detect_slot(eq, eq_cfg, eq_entity)

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

        # 结构化同步至 Character.equip_slots
        if hasattr(c, "equip_slots") and c.equip_slots is not None:
            if hasattr(c.equip_slots, slot):
                setattr(c.equip_slots, slot, name)

        EquipEngine.sync_character_stats(c)

        slot_cn = EquipEngine.SLOT_CN.get(slot, slot)
        msg = f"【法宝入体】佩戴{grade}·【{name}】（{slot_cn}），周天战力提升 {int(bonus*100)}%。"
        if entity and entity.affixes:
            msg += f" 激发护道词缀：{'、'.join(a.name for a in entity.affixes)}。"
        active_sets = EquipEngine.get_active_sets(c)
        if active_sets:
            msg += f" 激活天道套装羁绊：{'、'.join(s['name'] for s in active_sets)}。"
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

        # 结构化解除 Character.equip_slots 槽位绑定
        if hasattr(c, "equip_slots") and c.equip_slots is not None:
            for s in ("weapon", "armor", "trinket", "boots", "flying_treasure"):
                if getattr(c.equip_slots, s, None) == target:
                    setattr(c.equip_slots, s, None)

        EquipEngine.sync_character_stats(c)

        return {"success": True, "message": f"【卸下法宝】收敛道韵，已将【{target}】从身上卸下，妥善纳归百宝纳戒。"}

    @staticmethod
    def check_equip_requirements(c: Character, item_name: str) -> Tuple[bool, str]:
        """
        核验法宝佩戴境界门槛、灵根属性亲和与道心因果要求
        """
        from config import ITEM_CATALOG
        cfg = ITEM_CATALOG.get(item_name) or {}
        req_realm = cfg.get("req_realm_tier") or cfg.get("tier", 1)
        char_tier = getattr(c.realm, "tier", 1)

        # 境界门槛（允许越一阶驾驭，越两阶及以上法力反噬不可驾驭）
        if req_realm > char_tier + 1:
            tier_names = {1: "练气", 2: "筑基", 3: "金丹", 4: "元婴", 5: "化神"}
            req_name = tier_names.get(req_realm, f"{req_realm}阶")
            cur_name = tier_names.get(char_tier, f"{char_tier}阶")
            return False, f"【境界悬殊】此法宝乃{req_name}期护道法宝，你当前仅为{cur_name}期，强行祭炼恐遭器灵噬主爆体！"

        # 道心因果校验
        req_dao = cfg.get("req_dao_heart") or {}
        if "negative" in req_dao:
            sin = getattr(c.karma, "sin_value", 0)
            dao = getattr(c.karma, "dao_heart", 50)
            if sin < req_dao["negative"] and dao > (100 - req_dao["negative"]):
                return False, "【魔性抗拒】此法宝乃阴煞魔兵，非杀伐果决、背负煞气之修难以御使！"

        return True, ""

    @staticmethod
    def get_active_sets(c: Character) -> List[Dict[str, Any]]:
        """计算道身当前激发的所有天道装备套装羁绊"""
        from core.catalogs import SET_BONUSES
        from config import ITEM_CATALOG

        set_counts: Dict[str, int] = {}
        for eq in getattr(c, "equipped", []) or []:
            cfg = ITEM_CATALOG.get(eq) or {}
            s_name = cfg.get("set_name")
            if s_name:
                set_counts[s_name] = set_counts.get(s_name, 0) + 1

        active_bonuses: List[Dict[str, Any]] = []
        for s_name, count in set_counts.items():
            set_def = SET_BONUSES.get(s_name)
            if not set_def:
                continue
            thresholds = set_def.get("thresholds", {})
            for t_count in sorted(thresholds.keys()):
                if count >= t_count:
                    b_data = dict(thresholds[t_count])
                    b_data["set_name"] = s_name
                    b_data["count"] = count
                    b_data["threshold"] = t_count
                    active_bonuses.append(b_data)
        return active_bonuses

    @staticmethod
    def get_active_passives(c: Character) -> List[Dict[str, Any]]:
        """汇总道身当前生效的法宝被动词缀与心法"""
        from config import ITEM_CATALOG
        passives: List[Dict[str, Any]] = []
        for eq in getattr(c, "equipped", []) or []:
            cfg = ITEM_CATALOG.get(eq) or {}
            for p in cfg.get("passive_skills", []):
                passives.append(dict(p))
            entity = c.find_item(eq)
            if entity:
                for aff in getattr(entity, "affixes", []):
                    passives.append({"id": getattr(aff, "stat_key", ""), "name": aff.name, "value": getattr(aff, "value", 0.0), "desc": aff.desc})
        return passives

    @staticmethod
    def get_active_spells(c: Character) -> List[Dict[str, Any]]:
        """汇总道身当前装备附带的主动本命神通"""
        from config import ITEM_CATALOG
        spells: List[Dict[str, Any]] = []
        for eq in getattr(c, "equipped", []) or []:
            cfg = ITEM_CATALOG.get(eq) or {}
            for sp in cfg.get("active_spells", []):
                spells.append(dict(sp))
        return spells

    @staticmethod
    def power_bonus(c: Character) -> float:
        """按品阶、实体词缀与套装加成累加"""
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
        for b in EquipEngine.get_active_sets(c):
            total += float(b.get("power_bonus", 0.0))
        return 1.0 + total

    @staticmethod
    def get_total_stats(c: Character) -> Dict[str, Any]:
        """汇总道身所佩戴所有装备与套装属性加成"""
        totals: Dict[str, Any] = {
            "phys_atk": 0, "spell_atk": 0, "phys_def": 0, "spell_def": 0,
            "speed": 0, "max_hp": 0, "max_mp": 0, "crit_rate": 0.0, "crit_damage": 0.0,
            "divine_sense": 0, "sense_range": 0, "illusion_resist": 0.0
        }
        for eq in getattr(c, "equipped", None) or []:
            cfg = ITEM_CATALOG.get(eq) or {}
            stats = cfg.get("stats") or {}
            for k in totals:
                totals[k] += stats.get(k, 0)
        # 累加套装羁绊属性
        for b in EquipEngine.get_active_sets(c):
            b_stats = b.get("stats", {})
            for k in totals:
                totals[k] += b_stats.get(k, 0)
        return totals

    @staticmethod
    def sync_character_stats(c: Character) -> None:
        """根据境界基础属性与装备/套装属性，同步 Character.combat 与 Character.soul"""
        if not hasattr(c, "combat") or c.combat is None:
            return
        t = getattr(c.realm, "tier", 1)
        sub = getattr(c.realm, "sub_tier", 1)

        base_hp = 100 + t * 150 + sub * 40
        base_mp = 50 + t * 80 + sub * 20
        base_patk = 10 + t * 15 + sub * 5
        base_satk = 15 + t * 25 + sub * 8
        base_pdef = 8 + t * 12 + sub * 4
        base_sdef = 8 + t * 15 + sub * 5
        base_speed = 10 + t * 5 + sub * 2
        base_crate = 0.05
        base_cdmg = 1.50
        base_sense = 20 + t * 30 + sub * 10
        base_range = 50 + t * 60 + sub * 20
        base_ill = 0.05 + t * 0.05

        eq_stats = EquipEngine.get_total_stats(c)

        c.combat.max_hp = base_hp + int(eq_stats.get("max_hp", 0))
        c.combat.current_hp = min(c.combat.current_hp, c.combat.max_hp) if c.combat.current_hp > 0 else c.combat.max_hp
        c.combat.max_mp = base_mp + int(eq_stats.get("max_mp", 0))
        c.combat.current_mp = min(c.combat.current_mp, c.combat.max_mp) if c.combat.current_mp > 0 else c.combat.max_mp
        c.combat.phys_atk = base_patk + int(eq_stats.get("phys_atk", 0))
        c.combat.spell_atk = base_satk + int(eq_stats.get("spell_atk", 0))
        c.combat.phys_def = base_pdef + int(eq_stats.get("phys_def", 0))
        c.combat.spell_def = base_sdef + int(eq_stats.get("spell_def", 0))
        c.combat.speed = base_speed + int(eq_stats.get("speed", 0))
        c.combat.crit_rate = round(base_crate + float(eq_stats.get("crit_rate", 0.0)), 4)
        c.combat.crit_damage = round(base_cdmg + float(eq_stats.get("crit_damage", 0.0)), 4)

        if hasattr(c, "soul") and c.soul is not None:
            c.soul.divine_sense = base_sense + int(eq_stats.get("divine_sense", 0))
            c.soul.sense_range = base_range + int(eq_stats.get("sense_range", 0))
            c.soul.illusion_resist = round(base_ill + float(eq_stats.get("illusion_resist", 0.0)), 4)




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
