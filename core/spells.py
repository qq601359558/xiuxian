"""
修仙五行神通与半即时连携战斗引擎
提供气血(HP)、真元(MP)、护盾(Shield)、五行神通克制与法宝必杀机制
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character


# ==============================================================================
# 五行基础神通字典
# ==============================================================================
SPELL_CATALOG: Dict[str, Dict[str, Any]] = {
    "metal_sword": {
        "key": "metal_sword",
        "name": "太乙破虚剑气",
        "element": "metal",
        "element_cn": "金",
        "cost_mp": 15,
        "cooldown": 1,
        "base_mult": 1.6,
        "desc": "凝聚庚金剑芒破空斩击。造成 160% 破甲杀伤；若敌方身负护盾，额外造成 50% 破盾斩击！",
    },
    "wood_heal": {
        "key": "wood_heal",
        "name": "青帝长生引",
        "element": "wood",
        "element_cn": "木",
        "cost_mp": 20,
        "cooldown": 2,
        "heal_pct": 0.30,
        "desc": "引动乙木长生之气化入肉身，恢复 30% 最大气血，并驱散一层负面负累。",
    },
    "water_freeze": {
        "key": "water_freeze",
        "name": "玄冰寒煞魄",
        "element": "water",
        "element_cn": "水",
        "cost_mp": 18,
        "cooldown": 2,
        "base_mult": 1.2,
        "desc": "以玄阴真水凝聚寒煞，造成 120% 冰霜伤害，并冻结目标神魂（下回合无法出手）。",
    },
    "fire_blast": {
        "key": "fire_blast",
        "name": "九幽地煞火",
        "element": "fire",
        "element_cn": "火",
        "cost_mp": 20,
        "cooldown": 1,
        "base_mult": 1.4,
        "burn_dot": 2,
        "desc": "催动地心煞火焚天煮海，造成 140% 火伤并施加灼烧；若目标处于冻结状态，将触发【真火爆燃】造成双倍额外暴击！",
    },
    "earth_shield": {
        "key": "earth_shield",
        "name": "不动明王罡",
        "element": "earth",
        "element_cn": "土",
        "cost_mp": 20,
        "cooldown": 3,
        "shield_pct": 0.35,
        "reflect_pct": 0.20,
        "desc": "借大地戊土灵脉化为明王护体罡气，生成相当于自身 35% 气血的坚固灵盾，并反震 20% 伤害。",
    },
}


# ==============================================================================
# 战斗实体类
# ==============================================================================
@dataclass
class CombatEntity:
    id: str
    name: str
    realm: str
    tier: int
    max_hp: int
    hp: int
    max_mp: int
    mp: int
    attack: int
    defense: int
    shield: int = 0
    speed: int = 100
    status_effects: Dict[str, int] = field(default_factory=dict)  # {"burn": 2, "freeze": 1}
    cooldowns: Dict[str, int] = field(default_factory=dict)       # {"metal_sword": 0}
    treasure_used: bool = False
    equipped_weapon: str = ""
    is_player: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "realm": self.realm,
            "tier": self.tier,
            "max_hp": self.max_hp,
            "hp": self.hp,
            "max_mp": self.max_mp,
            "mp": self.mp,
            "shield": self.shield,
            "attack": self.attack,
            "defense": self.defense,
            "status_effects": dict(self.status_effects),
            "cooldowns": dict(self.cooldowns),
            "treasure_used": self.treasure_used,
            "equipped_weapon": self.equipped_weapon,
            "is_player": self.is_player,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CombatEntity:
        return cls(
            id=d["id"],
            name=d["name"],
            realm=d.get("realm", "练气一层"),
            tier=int(d.get("tier", 1)),
            max_hp=int(d.get("max_hp", 100)),
            hp=int(d.get("hp", 100)),
            max_mp=int(d.get("max_mp", 50)),
            mp=int(d.get("mp", 50)),
            shield=int(d.get("shield", 0)),
            attack=int(d.get("attack", 20)),
            defense=int(d.get("defense", 5)),
            speed=int(d.get("speed", 100)),
            status_effects=dict(d.get("status_effects", {})),
            cooldowns=dict(d.get("cooldowns", {})),
            treasure_used=bool(d.get("treasure_used", False)),
            equipped_weapon=str(d.get("equipped_weapon", "")),
            is_player=bool(d.get("is_player", False)),
        )


# ==============================================================================
# 从 Character 生成玩家战斗实体
# ==============================================================================
def create_player_entity(char: Character, boons: Optional[List[str]] = None) -> CombatEntity:
    tier = getattr(char.realm, "tier", 1)
    sub = getattr(char.realm, "sub_tier", 1)
    # 基础血量真元：境界为主
    tier_base_hp = int(120 * (1.8 ** (tier - 1))) + sub * 25
    tier_base_mp = int(60 * (1.5 ** (tier - 1))) + sub * 15
    tier_base_atk = int(25 * (1.7 ** (tier - 1))) + sub * 8
    tier_base_def = int(8 * (1.6 ** (tier - 1))) + sub * 3

    # 装备加成
    weapon_name = ""
    try:
        from core.loot_equip import EquipEngine
        from storage.db import ItemEntityRepository

        equipped = EquipEngine.get_equipped(char)
        if equipped:
            for slot, ent_id in equipped.items():
                ent = ItemEntityRepository.get(ent_id)
                if not ent:
                    continue
                attrs = getattr(ent, "affixes", {}) or {}
                tier_base_atk += int(attrs.get("attack", 0))
                tier_base_def += int(attrs.get("defense", 0))
                tier_base_hp += int(attrs.get("hp", 0))
                tier_base_mp += int(attrs.get("mp", 0))
                if slot in ("weapon", "main_weapon"):
                    weapon_name = ent.name
    except Exception:
        pass

    # 局内道韵 (Dao Boons) 加成
    boon_list = boons or []
    if "pure_yang" in boon_list:  # 纯阳真火
        tier_base_atk = int(tier_base_atk * 1.25)
    if "iron_wall" in boon_list:  # 厚土金汤
        tier_base_hp = int(tier_base_hp * 1.30)
        tier_base_def = int(tier_base_def * 1.25)
    if "spirit_well" in boon_list:  # 灵泉洗髓
        tier_base_mp = int(tier_base_mp * 1.40)

    # 灵根加成
    root_eff = getattr(char.spiritual_root, "efficiency", 1.0)
    tier_base_atk = int(tier_base_atk * (0.9 + root_eff * 0.2))

    return CombatEntity(
        id=char.id,
        name=char.name,
        realm=char.realm.name,
        tier=tier,
        max_hp=tier_base_hp,
        hp=tier_base_hp,
        max_mp=tier_base_mp,
        mp=tier_base_mp,
        attack=tier_base_atk,
        defense=tier_base_def,
        equipped_weapon=weapon_name or "流光本命木剑",
        is_player=True,
    )


# ==============================================================================
# 怪物战斗实体生成
# ==============================================================================
def create_monster_entity(m_dict: Dict[str, Any], floor: int) -> CombatEntity:
    base_hp = int(m_dict.get("base_hp", 100) * (1 + (floor - 1) * 0.45))
    base_atk = int(m_dict.get("base_atk", 20) * (1 + (floor - 1) * 0.35))
    base_def = int(m_dict.get("base_def", 5) * (1 + (floor - 1) * 0.30))
    tier = int(m_dict.get("tier", 1))

    return CombatEntity(
        id=m_dict.get("id", f"mon_f{floor}_{random.randint(100, 999)}"),
        name=m_dict.get("name", "嗜血妖狼"),
        realm=m_dict.get("realm", "一阶妖兽"),
        tier=tier,
        max_hp=base_hp,
        hp=base_hp,
        max_mp=50 + floor * 10,
        mp=50 + floor * 10,
        attack=base_atk,
        defense=base_def,
        speed=int(m_dict.get("speed", 95)),
        is_player=False,
    )


# ==============================================================================
# 神通半即时战斗裁决引擎
# ==============================================================================
class SpellCombatEngine:
    """神通出招与连携结算引擎"""

    @classmethod
    def apply_damage(cls, target: CombatEntity, raw_dmg: int, element: str = "") -> Tuple[int, int, bool]:
        """
        计算实际承受伤害，优先扣除护盾
        :return: (实际扣除血量, 扣除护盾值, 是否破盾)
        """
        # 防御免伤系数
        mitigation = target.defense / (target.defense + 100)
        net_dmg = max(1, int(raw_dmg * (1 - mitigation)))

        shield_absorbed = 0
        shield_broken = False
        if target.shield > 0:
            if target.shield >= net_dmg:
                target.shield -= net_dmg
                shield_absorbed = net_dmg
                hp_loss = 0
            else:
                hp_loss = net_dmg - target.shield
                shield_absorbed = target.shield
                target.shield = 0
                shield_broken = True
        else:
            hp_loss = net_dmg

        target.hp = max(0, target.hp - hp_loss)
        return hp_loss, shield_absorbed, shield_broken

    @classmethod
    def step_round(
        cls,
        player: CombatEntity,
        monster: CombatEntity,
        action: str,  # "attack" | "spell" | "treasure"
        spell_key: Optional[str] = None,
        boons: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        执行单个动作步进并返回本回合日志与实体状态
        """
        logs: List[str] = []
        boon_list = boons or []
        is_combat_ended = False
        winner = None

        # 1. 玩家出招阶段
        if player.hp <= 0:
            return {"ended": True, "winner": "monster", "logs": ["修士气血亏空，无力再战！"]}

        # 冷却缩减检查
        for k in list(player.cooldowns.keys()):
            if player.cooldowns[k] > 0:
                player.cooldowns[k] -= 1

        if action == "spell" and spell_key in SPELL_CATALOG:
            spell = SPELL_CATALOG[spell_key]
            # 校验 MP
            if player.mp < spell["cost_mp"]:
                action = "attack"
                logs.append(f"【真元不济】真元不足以催动【{spell['name']}】，转为普通剑气攻伐！")
            elif player.cooldowns.get(spell_key, 0) > 0:
                action = "attack"
                logs.append(f"【法诀调息】神通【{spell['name']}】尚在气机调息中，转为普通剑气攻伐！")
            else:
                # 扣除 MP
                player.mp -= spell["cost_mp"]
                player.cooldowns[spell_key] = spell["cooldown"]

                if spell_key == "metal_sword":
                    mult = spell["base_mult"]
                    if "sword_heart" in boon_list:  # 剑心通明道韵
                        mult += 0.4
                    raw_dmg = int(player.attack * mult)
                    if monster.shield > 0:
                        raw_dmg = int(raw_dmg * 1.5)
                        logs.append(f"⚡【金光破障】你指尖剑芒吞吐，施展【{spell['name']}】！剑锋引动庚金锐气，对敌方护盾造成 1.5 倍破甲暴击！")
                    else:
                        logs.append(f"⚡【庚金断岳】你引动太白金精，施展【{spell['name']}】破空激射！")
                    
                    hp_loss, shield_loss, broken = cls.apply_damage(monster, raw_dmg, "metal")
                    logs.append(f"  ↳ 对【{monster.name}】造成了 {hp_loss + shield_loss} 点锐金杀伤" + ("（护盾碎裂！）" if broken else ""))

                elif spell_key == "wood_heal":
                    heal_amt = int(player.max_hp * spell["heal_pct"])
                    if "spirit_well" in boon_list:
                        heal_amt = int(heal_amt * 1.3)
                    player.hp = min(player.max_hp, player.hp + heal_amt)
                    # 驱散一层异常
                    dispelled = ""
                    if player.status_effects:
                        k = next(iter(player.status_effects.keys()))
                        del player.status_effects[k]
                        dispelled = f"，驱散了身负的【{k}】异状"
                    logs.append(f"🌿【乙木回生】你运转【{spell['name']}】，青色生机流转经脉，气血恢复 +{heal_amt}{dispelled}！")

                elif spell_key == "water_freeze":
                    raw_dmg = int(player.attack * spell["base_mult"])
                    monster.status_effects["freeze"] = 1  # 冻结 1 回合（跳过下一次反击）
                    monster.status_effects["chill"] = 2   # 寒煞持续 2 回合
                    hp_loss, shield_loss, broken = cls.apply_damage(monster, raw_dmg, "water")
                    logs.append(f"❄️【玄煞凝晶】你拂袖引出【{spell['name']}】，极寒水汽化为千百玄冰冰魄！造成 {hp_loss + shield_loss} 点冰霜伤害，并将其神魂【冻结】！")

                elif spell_key == "fire_blast":
                    mult = spell["base_mult"]
                    # 连携检查：若目标冻结或身负寒煞，触发真火爆燃
                    is_combo = False
                    if monster.status_effects.get("freeze", 0) > 0 or monster.status_effects.get("chill", 0) > 0:
                        mult *= 2.2
                        is_combo = True
                        if "freeze" in monster.status_effects:
                            del monster.status_effects["freeze"]
                        if "chill" in monster.status_effects:
                            del monster.status_effects["chill"]
                    if "pure_yang" in boon_list:
                        mult += 0.35
                    raw_dmg = int(player.attack * mult)
                    monster.status_effects["burn"] = 2  # 灼烧 2 回合
                    hp_loss, shield_loss, broken = cls.apply_damage(monster, raw_dmg, "fire")
                    if is_combo:
                        logs.append(f"💥【水火连携 · 阴阳爆燃】你引动【{spell['name']}】烈焰点燃坚冰，冰火相激引发天地逆冲暴响！暴击重创造成 {hp_loss + shield_loss} 点毁灭杀伤！")
                    else:
                        logs.append(f"🔥【地煞焚荒】你掐诀祭出【{spell['name']}】，幽蓝冥火缠绕目标，造成 {hp_loss + shield_loss} 点火焰伤害并施加【灼烧】！")

                elif spell_key == "earth_shield":
                    shield_val = int(player.max_hp * spell["shield_pct"])
                    if "iron_wall" in boon_list:
                        shield_val = int(shield_val * 1.4)
                    player.shield += shield_val
                    player.status_effects["reflect"] = 2
                    logs.append(f"🛡️【不动明王】你脚踏坤位，引动【{spell['name']}】！周身凝聚起 {shield_val} 点厚土灵盾，并开启真元反震！")

        elif action == "treasure":
            if player.treasure_used:
                logs.append("【法宝温养中】本场斗法已然祭炼过法宝大招，神念匮乏无法再施！转为普攻！")
                action = "attack"
            elif player.mp < 25:
                logs.append("【真元枯竭】真元不足以激发法宝真灵，转为普攻！")
                action = "attack"
            else:
                player.mp -= 25
                player.treasure_used = True
                weapon = player.equipped_weapon or "通微飞剑"
                raw_dmg = int(player.attack * 2.8)
                hp_loss, shield_loss, broken = cls.apply_damage(monster, raw_dmg, "treasure")
                monster.status_effects["stun"] = 1
                logs.append(f"🌟【法宝神威 · 绝地天通】你祭出本命灵器【{weapon}】！器灵苏醒，天地失色！一击洞穿虚空，对【{monster.name}】轰出 {hp_loss + shield_loss} 点崩天真实伤害，使其陷入震慑眩晕！")

        if action == "attack":
            crit = random.random() < 0.20
            mult = 1.6 if crit else 1.0
            raw_dmg = int(player.attack * mult)
            hp_loss, shield_loss, broken = cls.apply_damage(monster, raw_dmg)
            crit_str = "【会心一击】" if crit else ""
            logs.append(f"🗡️{crit_str}你手捏剑指，催动随身飞剑劈出一记凌厉剑气，对【{monster.name}】造成 {hp_loss + shield_loss} 点伤害。")

        # 检查怪物是否被斩杀
        if monster.hp <= 0:
            logs.append(f"🎉【妖煞溃散】妖兽【{monster.name}】发出一声哀鸣，轰然倒地，生机断绝！")
            return {
                "ended": True,
                "winner": "player",
                "player": player.to_dict(),
                "monster": monster.to_dict(),
                "logs": logs,
            }

        # 2. 回合末异常状态结算 (怪物身上)
        if monster.status_effects.get("burn", 0) > 0:
            burn_dmg = max(5, int(player.attack * 0.25))
            monster.hp = max(0, monster.hp - burn_dmg)
            monster.status_effects["burn"] -= 1
            if monster.status_effects["burn"] <= 0:
                del monster.status_effects["burn"]
            logs.append(f"  ↳ 地煞灼烧侵蚀，【{monster.name}】受到 {burn_dmg} 点真火灼烧伤害！")

        if monster.hp <= 0:
            logs.append(f"🎉【地火燃烬】妖兽【{monster.name}】在烈焰中化为灰烬！")
            return {
                "ended": True,
                "winner": "player",
                "player": player.to_dict(),
                "monster": monster.to_dict(),
                "logs": logs,
            }

        # 3. 怪物反击阶段
        # 检查怪物是否受控 (freeze / stun)
        if monster.status_effects.get("freeze", 0) > 0:
            del monster.status_effects["freeze"]
            logs.append(f"❄️【寒煞缚身】妖兽【{monster.name}】周身凝霜，神魂僵直，本回合动弹不得！")
        elif monster.status_effects.get("stun", 0) > 0:
            del monster.status_effects["stun"]
            logs.append(f"💫【法宝震慑】妖兽【{monster.name}】被法宝神威镇压，浑浑噩噩，无法反击！")
        else:
            # 怪物出手
            m_atk = monster.attack
            # 怪物特异出招（随机普攻或妖兽狂暴）
            is_frenzy = random.random() < 0.25
            if is_frenzy:
                m_dmg = int(m_atk * 1.45)
                logs.append(f"🩸【凶性大发】妖兽【{monster.name}】双目猩红，猛然扑杀而至！")
            else:
                m_dmg = m_atk
                logs.append(f"🐾 妖兽【{monster.name}】探出利爪，撕裂罡风拍向你的护体气机！")

            p_loss, p_shield_loss, p_broken = cls.apply_damage(player, m_dmg)
            logs.append(f"  ↳ 你承受了 {p_loss + p_shield_loss} 点伤害" + ("（厚土灵盾破裂！）" if p_broken else ""))

            # 反震判定
            if player.status_effects.get("reflect", 0) > 0:
                refl_dmg = int(m_dmg * 0.20)
                monster.hp = max(0, monster.hp - refl_dmg)
                logs.append(f"  ↳ 明王反震！厚土宝罡激荡反震，反伤【{monster.name}】 {refl_dmg} 点伤害！")

        # 4. 回合末异常状态结算 (玩家身上)
        if player.status_effects.get("reflect", 0) > 0:
            player.status_effects["reflect"] -= 1
            if player.status_effects["reflect"] <= 0:
                del player.status_effects["reflect"]

        if monster.status_effects.get("chill", 0) > 0:
            monster.status_effects["chill"] -= 1
            if monster.status_effects["chill"] <= 0:
                del monster.status_effects["chill"]

        # 自然每回合回蓝一缕 (5 MP)
        player.mp = min(player.max_mp, player.mp + 5)

        # 检查玩家生死
        if player.hp <= 0:
            logs.append(f"💀【生机耗尽】你气血枯竭，眼前一黑，护身灵光彻底暗淡！")
            return {
                "ended": True,
                "winner": "monster",
                "player": player.to_dict(),
                "monster": monster.to_dict(),
                "logs": logs,
            }

        return {
            "ended": False,
            "winner": None,
            "player": player.to_dict(),
            "monster": monster.to_dict(),
            "logs": logs,
        }
