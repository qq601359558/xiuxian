"""
野外神识探查、伏击斗法与杀人夺宝引擎
"""
import random
from typing import List, Dict, Any, Optional
from config import (
    KARMA_KILL_SAME_TIER,
    KARMA_KILL_LOWER_TIER
)
from core.models import Character, CharacterStatus, status_cn
from core.character_integrity import CharacterIntegrity, CharacterIntegrityError


class CombatEngine:
    """斗法与黑暗森林法则裁决引擎"""

    @staticmethod
    def scan_surroundings(scanner: Character, targets: List[Character]) -> List[Dict[str, Any]]:
        """
        神识外放探查方圆周遭
        :return: 扫描结果列表 (根据神识差值做信息脱敏)
        """
        results = []
        # 探查者神识强度: 境界基数*100 + 灵根修正
        s_sense = scanner.realm.tier * 100 + scanner.realm.sub_tier * 25
        if scanner.spiritual_root.root_type.value in ["HEAVEN", "MUTANT"]:
            s_sense += 30

        for target in targets:
            if target.id == scanner.id or target.status == CharacterStatus.DEAD:
                continue

            # 被探查者敛息隐匿强度
            c_hide = target.realm.tier * 60
            if target.stealth_active:
                c_hide += 100 # 开启敛息术

            delta = s_sense - c_hide

            if delta < 0:
                # 完全无法探测到目标
                continue
            elif delta < 40:
                # 模糊灵压光点
                results.append({
                    "target_id": target.id,
                    "clarity": "VAGUE",
                    "description": "【未知灵压】东北方位隐隐有微弱灵力波动，虚实难辨，疑似有修士或妖兽伏行。"
                })
            elif delta < 120:
                # 识破境界与血煞
                marked_str = "【头顶血煞狼烟】" if target.karma.is_blood_marked() else ""
                results.append({
                    "target_id": target.id,
                    "name": target.name,
                    "clarity": "REALM",
                    "description": f"【修士行迹】发现散修【{target.name}】，境界约为【{target.realm.name}】{marked_str}。"
                })
            else:
                # 神识穿透！彻底洞悉
                marked_str = " (背负血债·天理难容)" if target.karma.is_blood_marked() else ""
                results.append({
                    "target_id": target.id,
                    "name": target.name,
                    "clarity": "FULL",
                    "realm": target.realm.name,
                    "stones": target.spirit_stones,
                    "sin": target.karma.sin_value,
                    "description": (
                        f"【神识穿透】清晰洞悉修士【{target.name}】！\n"
                        f"  · 境界：{target.realm.name} | 状态：{status_cn(target.status)}\n"
                        f"  · 储物袋灵光：约有 {target.spirit_stones} 块随身灵石\n"
                        f"  · 因果底细：业力 {target.karma.sin_value}{marked_str}"
                    )
                })

        return results

    @staticmethod
    def calculate_power(c: Character) -> float:
        """计算即时综合斗法战力指数"""
        # 境界绝对压制：大境界呈指数级增强
        tier_factor = (3.5 ** c.realm.tier) * 100
        sub_factor = c.realm.sub_tier * (tier_factor * 0.2)
        root_factor = c.spiritual_root.efficiency * 50
        dao_factor = (c.karma.dao_heart / 100.0)
        power = (tier_factor + sub_factor + root_factor) * dao_factor
        if c.sect == "万剑仙门":
            power *= 1.2 # 万剑仙门杀伐战力提升 20%
        try:
            from core.loot_equip import EquipEngine, art_combat_bonus
            power *= EquipEngine.power_bonus(c)
            power *= art_combat_bonus(c)
        except Exception:
            pass
        return power

    @staticmethod
    def execute_ambush(attacker: Character, defender: Character) -> Dict[str, Any]:
        """
        发起伏击/斗法
        :return: 战斗战报与生死财货清算
        """
        try:
            CharacterIntegrity.assert_alive(attacker)
            CharacterIntegrity.assert_alive(defender)
            CharacterIntegrity.assert_idle(attacker, action="/斗法")
        except CharacterIntegrityError as e:
            return {"success": False, "message": str(e)}

        if defender.status == CharacterStatus.CAPTURED:
            return {"success": False, "message": "对方已身陷囹圄被擒，不可再行斗法。"}

        # 计算战力
        att_power = CombatEngine.calculate_power(attacker)
        def_power = CombatEngine.calculate_power(defender)
        # M3：敌对宗门交手进攻方加成（规则）
        try:
            from core.faction import hostile_power_bonus

            att_power *= hostile_power_bonus(
                getattr(attacker, "sect", "") or "",
                getattr(defender, "sect", "") or "",
            )
        except Exception:
            pass

        # 偷袭先手加成
        if attacker.stealth_active:
            att_power *= 1.3
            attacker.stealth_active = False # 破隐

        # 胜负概率计算 (Logistic 曲线)
        ratio = att_power / max(1.0, (att_power + def_power))
        roll = random.random()
        attacker_wins = roll < ratio

        # 安全区校验
        from config import WORLD_LOCATIONS
        def_loc = WORLD_LOCATIONS.get(defender.location, {"is_safe": True})
        if def_loc.get("is_safe", False):
            return {
                "success": False,
                "message": f"【天道庇护】{defender.name} 身处【{defender.location}】安全大阵庇护之内，绝灵之地不可动武！"
            }

        # 归隐庇护（新手庇护由 combat_fate / 上层裁决，保留裸露闭关可被伏击）
        from core.protection import protection_active
        if protection_active(defender):
            return {
                "success": False,
                "message": f"【天道庇护·归隐】{defender.name} 已闭关归隐，不可被攻击。"
            }

        # 闭关修士攻防判定
        if defender.status == CharacterStatus.MEDITATING:
            # 分支 1: 有大阵守护
            if defender.meditation.array and defender.meditation.array.is_active:
                arr = defender.meditation.array
                damage = int(att_power * 1.2)
                arr.current_durability -= damage

                if arr.current_durability > 0:
                    # 大阵防御成功，反震攻击者
                    attacker.realm.current_exp = max(0, attacker.realm.current_exp - arr.counter_damage)
                    return {
                        "winner_id": defender.id,
                        "loser_id": attacker.id,
                        "target_died": False,
                        "blood_escaped": False,
                        "looted_stones": 0,
                        "report": (
                            f"【大阵坚固 · 杀机受阻】\n"
                            f"{attacker.name} 祭出法宝狂轰 {defender.name} 的洞府大阵【{arr.name}】！\n"
                            f"阵法金光暴涨，硬生生抗下猛攻（结界剩余耐久：{arr.current_durability}/{arr.max_durability}）！\n"
                            f"杀阵神光反震，{attacker.name} 气血翻涌，震伤败退！"
                        )
                    }
                else:
                    # 大阵被轰碎！触发方案 B：留一线生机·替死血遁
                    arr.is_active = False
                    loot_pct = 0.60
                    looted_stones = int(defender.spirit_stones * loot_pct)
                    defender.spirit_stones -= looted_stones
                    attacker.spirit_stones += looted_stones

                    # 沾染业力
                    attacker.karma.add_sin(KARMA_KILL_SAME_TIER)

                    # 方案 B：肉身自卫替死血遁，挪移至坊市安全区，扣除1年寿命，保住性命！
                    burn_years = 1.0
                    defender.lifespan.burn_lifespan(burn_years)
                    defender.meditation.is_active = False
                    if defender.lifespan.is_dead():
                        defender.status = CharacterStatus.DEAD
                        defender.death_cause = f"洞府大阵被【{attacker.name}】轰碎，燃寿枯竭道消"
                        return {
                            "winner_id": attacker.id,
                            "loser_id": defender.id,
                            "target_died": True,
                            "blood_escaped": False,
                            "looted_stones": looted_stones,
                            "report": (
                                f"【大阵爆碎 · 燃寿道消】\n"
                                f"{attacker.name} 施展极招彻底轰碎了 {defender.name} 的【{arr.name}】！\n"
                                f"危急关头，{defender.name} 试图燃寿替死血遁，然寿元已近枯竭，血气溃散，当场坐化陨落！"
                            ),
                        }

                    defender.status = CharacterStatus.IDLE
                    old_loc = defender.location
                    defender.location = "青云坊市客栈"

                    return {
                        "winner_id": attacker.id,
                        "loser_id": defender.id,
                        "target_died": False,
                        "blood_escaped": True,
                        "looted_stones": looted_stones,
                        "report": (
                            f"【大阵爆碎 · 洞府被破】\n"
                            f"{attacker.name} 施展极招彻底轰碎了 {defender.name} 的【{arr.name}】！\n"
                            f"洞府崩塌，{attacker.name} 卷走洞内散落的 {looted_stones} 块灵石！\n"
                            f"【天道生机 · 替死血遁】\n"
                            f"危急关头，{defender.name} 体内本命替命玉符自燃，消耗 1 岁真寿化作血遁狂飙！\n"
                            f"肉身自【{old_loc}】随机挪移至【青云坊市客栈】，虽被洗劫且元气大伤，然侥幸保全性命！"
                        ),
                    }
            else:
                # 分支 2: 荒野裸露闭关无阵盘（方案 B 严苛受创惩罚）
                loot_pct = 0.85
                looted_stones = int(defender.spirit_stones * loot_pct)
                defender.spirit_stones -= looted_stones
                attacker.spirit_stones += looted_stones

                attacker.karma.add_sin(KARMA_KILL_SAME_TIER)

                # 燃烧 3 岁寿元逃命
                burn_years = 3.0
                defender.lifespan.burn_lifespan(burn_years)
                defender.meditation.is_active = False

                if defender.lifespan.is_dead():
                    defender.status = CharacterStatus.DEAD
                    defender.death_cause = f"荒野闭关遭【{attacker.name}】伏击，燃寿枯竭道消"
                    return {
                        "winner_id": attacker.id,
                        "loser_id": defender.id,
                        "target_died": True,
                        "blood_escaped": False,
                        "looted_stones": looted_stones,
                        "report": (
                            f"【荒野裸闭 · 燃寿道消】\n"
                            f"{defender.name} 露天闭关遭 {attacker.name} 致命突袭！\n"
                            f"试图强行燃寿血遁，怎奈所剩阳寿不足三载，道体崩解，当场坐化陨落！"
                        ),
                    }

                # 道基受创跌境
                if defender.realm.sub_tier > 0:
                    defender.realm.sub_tier -= 1
                    defender.realm.current_exp = 0
                    realm_loss_msg = f"道基惨遭震断，境界跌落至【{defender.realm.name}】！"
                else:
                    defender.realm.current_exp = defender.realm.current_exp // 2
                    realm_loss_msg = "道基震荡，体内元气溃散大半！"

                defender.status = CharacterStatus.IDLE
                old_loc = defender.location
                defender.location = "青云坊市客栈"

                return {
                    "winner_id": attacker.id,
                    "loser_id": defender.id,
                    "target_died": False,
                    "blood_escaped": True,
                    "looted_stones": looted_stones,
                    "report": (
                        f"【荒野裸闭 · 惨遭灭顶】\n"
                        f"{defender.name} 竟在凶险野外【{old_loc}】露天闭关无阵护持，六识闭塞！\n"
                        f"{attacker.name} 凌空暴起，万道杀机直灌其天灵盖！\n"
                        f"【无阵庇护 · 肉身崩裂】\n"
                        f"毫无防备的 {defender.name} 护体罡气瞬间崩解，储物袋被强行夺走 {looted_stones} 块灵石！\n"
                        f"【惨烈血遁 · 燃寿三载】\n"
                        f"绝命之际，本命精血被迫逆行自焚，狂燃 {burn_years:.1f} 岁阳寿强行化作血光破空！\n"
                        f"· {realm_loss_msg}\n"
                        f"· 残躯狼狈跌落回【青云坊市客栈】，保得残命，元气大伤！"
                    )
                }


        report = []
        report.append(f"【绝岭伏击】{attacker.name} 携雷霆杀机暴起突袭 {defender.name}！")
        report.append(f"  · {attacker.name} 战力评估：{int(att_power)} | {defender.name} 战力评估：{int(def_power)}")

        if attacker_wins:
            report.append(f"【剑光纵横】{attacker.name} 祭出道法死死压制，{defender.name} 护体罡气崩溃，狂喷鲜血！")
            
            # 败者尝试发动保命底牌：燃寿血遁术
            def_rem_years = defender.lifespan.get_remaining_years()
            if def_rem_years > 5.0 and random.random() < 0.60:
                # 触发血遁逃生！
                burn_years = 3.0
                defender.lifespan.burn_lifespan(burn_years)
                report.append(
                    f"【绝境燃寿 · 血遁逃生】\n"
                    f"生死一瞬之间，{defender.name} 悍然捏碎心脉，自燃 {burn_years} 年真寿化作冲天血虹！\n"
                    f"血光撕裂虚空，瞬间遁逃至八十里外，虽侥幸留得一命，然大限暴跌！"
                )
                return {
                    "winner_id": attacker.id,
                    "loser_id": defender.id,
                    "target_died": False,
                    "blood_escaped": True,
                    "looted_stones": 0,
                    "report": "\n".join(report)
                }
            else:
                # 斩杀成功！身死道消
                defender.status = CharacterStatus.DEAD
                defender.lifespan.death_timestamp = 0.0 # 寿元断绝

                # 搜刮未绑定随身灵石 (掉落 60% ~ 80%)
                loot_pct = random.uniform(0.60, 0.80)
                looted_stones = int(defender.spirit_stones * loot_pct)
                defender.spirit_stones -= looted_stones
                attacker.spirit_stones += looted_stones

                # 天道因果业力结算
                if defender.karma.is_blood_marked():
                    # 斩杀红名凶人：代天行道，免业力，得功德！
                    attacker.karma.add_merit(60)
                    report.append(f"【代天除凶】{defender.name} 背负血债，{attacker.name} 行替天之道将其诛杀，天降功德金光护体！")
                else:
                    # 滥杀修士：业力暴涨，沾染血煞
                    gain_sin = KARMA_KILL_SAME_TIER if defender.realm.tier >= attacker.realm.tier else KARMA_KILL_LOWER_TIER
                    attacker.karma.add_sin(gain_sin)
                    report.append(f"【杀人夺宝】{attacker.name} 斩灭同道，夺走储物袋中 {looted_stones} 块灵石！\n业力暴涨 +{gain_sin}，天道血煞附体，已被天地铭刻！")

                report.append(f"【道途终局】{defender.name} 身死道消，储物袋被破开，尸骨坠入荒野……")
                return {
                    "winner_id": attacker.id,
                    "loser_id": defender.id,
                    "target_died": True,
                    "blood_escaped": False,
                    "looted_stones": looted_stones,
                    "report": "\n".join(report)
                }
        else:
            # 伏击反杀！
            report.append(f"【惊天反杀】{defender.name} 根基深厚，识破杀机祭出本命灵宝，逆转局势重创 {attacker.name}！")
            # 攻击者重伤仓皇逃遁
            attacker.realm.current_exp = max(0, attacker.realm.current_exp - int(attacker.realm.max_exp * 0.2))
            report.append(f"{attacker.name} 伏击失败，经脉受损，仓皇遁入山林！")
            return {
                "winner_id": defender.id,
                "loser_id": attacker.id,
                "target_died": False,
                "blood_escaped": False,
                "looted_stones": 0,
                "report": "\n".join(report)
            }
