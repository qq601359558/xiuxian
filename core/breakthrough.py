"""
突破、天劫与生死反噬判定引擎
"""
import random
from typing import Dict, Any
from config import (
    BASE_BREAKTHROUGH_PROB,
    BREAKTHROUGH_LIFESPAN_GAIN,
    REALM_NAMES
)
from core.models import Character, CharacterStatus
from core.character_integrity import CharacterIntegrity, CharacterIntegrityError


class BreakthroughEngine:
    """天劫破境裁决引擎"""

    @staticmethod
    def attempt_breakthrough(
        character: Character,
        use_pill: bool = False,
        pill_bonus: float = 0.20,
        heart_mod: float = 0.0,
    ) -> Dict[str, Any]:
        """
        发起境界突破
        :param character: 修士实体
        :param use_pill: 是否使用破境丹药 (如筑基丹、金元丹)
        :param pill_bonus: 丹药加成
        :param heart_mod: 心魔回合对天劫成功率的修正（-0.15~0.15）
        """
        # 1. 基础状态校验
        try:
            CharacterIntegrity.assert_alive(character)
            CharacterIntegrity.assert_idle(character, action="/突破")
        except CharacterIntegrityError as e:
            return {
                "success": False,
                "is_fatal": character.status == CharacterStatus.DEAD,
                "message": str(e),
            }

        if not character.realm.is_full:
            return {
                "success": False,
                "is_fatal": False,
                "message": f"修为尚未圆满（当前 {character.realm.current_exp}/{character.realm.max_exp}），不可强行引动天劫！"
            }

        curr_tier = character.realm.tier
        curr_sub_tier = character.realm.sub_tier

        # 2. 判断是【小阶晋升】还是【大境界天劫】
        if curr_sub_tier < 3:
            # 小阶突破（初 -> 中 -> 后 -> 圆满）
            # 小阶突破中正平和，无雷劫，不加寿元
            character.realm.sub_tier += 1
            character.realm.current_exp = 0
            new_realm_name = character.realm.name
            return {
                "success": True,
                "is_major": False,
                "is_fatal": False,
                "new_realm": new_realm_name,
                "lifespan_gained": 0.0,
                "message": f"【灵犀顿悟】真元贯通经脉，顺畅晋阶为【{new_realm_name}】！（小阶晋升不增寿元）"
            }

        # 3. 此时为【大境界破境天劫】(如 练气圆满 -> 筑基)
        target_tier = curr_tier + 1
        base_prob = BASE_BREAKTHROUGH_PROB.get(target_tier, 0.10)

        # 丹药准备度加成
        prep_bonus = pill_bonus if use_pill else 0.0
        # 背包中筑基丹药力（坊市购入并服用后写入 skills 标记）
        if "筑基丹药力(待渡劫)" in character.skills:
            prep_bonus = max(prep_bonus, pill_bonus)
            character.skills.remove("筑基丹药力(待渡劫)")

        # 因果业力惩罚 (杀人越多，天劫越狂暴，最高扣 40% 成功率)
        sin = character.karma.sin_value
        karma_penalty = min(0.40, sin * 0.0005)

        # 道心心魔扣减 (道心低于 80 开始滋生心魔)
        dao_heart = character.karma.dao_heart
        heart_penalty = max(0.0, (80 - dao_heart) * 0.005)

        # 功德护体加成
        merit = character.karma.merit_value
        merit_bonus = min(0.15, merit * 0.002)

        # 综合计算最终成功率 (锁定在 5% ~ 95% 之间)
        final_prob = base_prob + prep_bonus - karma_penalty - heart_penalty + merit_bonus
        final_prob += max(-0.15, min(0.15, float(heart_mod or 0.0)))
        final_prob = max(0.05, min(0.95, final_prob))

        target_name = REALM_NAMES[target_tier] if target_tier < len(REALM_NAMES) else "超脱真仙"

        # AI 天命判定（规则概率为先验；无 API 时降级规则骰）
        from ai.gateway import AIGateway
        judgment = AIGateway.judge_tribulation(character, final_prob, target_name)
        is_success = bool(judgment["success"])
        judge_source = judgment.get("source", "rule")
        judge_reason = judgment.get("reason", "")
        roll = judgment.get("adj_prob", final_prob)

        if is_success:
            # 渡劫成功！
            character.realm.tier = target_tier
            character.realm.sub_tier = 0
            character.realm.current_exp = 0

            # 随机增寿
            gain_range = BREAKTHROUGH_LIFESPAN_GAIN.get(target_tier, (20, 40))
            lifespan_gain = round(random.uniform(gain_range[0], gain_range[1]), 1)
            character.lifespan.add_lifespan(lifespan_gain)

            judge_line = f"\n[天命判词·{judge_source}] {judge_reason}" if judge_reason else ""
            try:
                from core.world_channel import WorldChannel

                if character.realm.tier >= 2:  # 筑基+
                    WorldChannel.post(
                        "breakthrough",
                        f"【雷音】{character.name} 渡劫功成，晋 {character.realm.name}。",
                        level="major",
                        actor=character.name,
                        location=character.location,
                    )
            except Exception:
                pass
            return {
                "success": True,
                "is_major": True,
                "is_fatal": False,
                "roll": round(float(roll) * 100, 1),
                "prob_pct": round(final_prob * 100, 1),
                "judge_source": judge_source,
                "judge_reason": judge_reason,
                "new_realm": character.realm.name,
                "lifespan_gained": lifespan_gain,
                "message": (
                    f"【紫霄天劫 · 逆天功成】\n"
                    f"九霄雷云汇聚，劫雷轰然劈落！道友凭借浑厚根基硬抗雷劫，金光淬体！\n"
                    f"成功突破至【{character.realm.name}】！\n"
                    f"天道赐福：寿元暴涨 +{lifespan_gain} 岁！{judge_line}"
                )
            }
        else:
            # 渡劫失败！天劫反噬判定
            fail_roll = random.randint(1, 100)
            character.realm.current_exp = int(character.realm.max_exp * 0.3) # 损失大部分修为
            judge_line = f"\n[天命判词·{judge_source}] {judge_reason}" if judge_reason else ""

            def _post_fail(tag: str):
                try:
                    from core.world_channel import WorldChannel

                    WorldChannel.post(
                        "tribulation",
                        f"【天劫】{character.name} {tag}，于 {character.location}。",
                        level="major",
                        actor=character.name,
                        location=character.location,
                    )
                except Exception:
                    pass

            if fail_roll <= 15:
                # 1. 身死道消 (15%)
                character.status = CharacterStatus.DEAD
                character.death_cause = "渡劫天劫反噬，身死道消"
                character.lifespan.death_timestamp = 0.0
                _post_fail("天劫反噬，身死道消")
                return {
                    "success": False,
                    "is_major": True,
                    "is_fatal": True,
                    "fail_tier": "DEATH",
                    "prob_pct": round(final_prob * 100, 1),
                    "judge_source": judge_source,
                    "judge_reason": judge_reason,
                    "message": (
                        f"【天劫反噬 · 身死道消】\n"
                        f"黑煞劫雷狂暴贯顶！护体罡气寸寸碎裂，肉身当场灰飞湮灭，真灵散入天地……\n"
                        f"道友此世修仙道途终结，尸骨化作黄土。{judge_line}"
                    )
                }
            elif fail_roll <= 40:
                # 2. 道基崩溃 (25%): 永久减寿命 10~25 岁
                lost_years = round(random.uniform(10.0, 25.0), 1)
                character.lifespan.burn_lifespan(lost_years)

                # 寿元枯竭自愈与生死判定
                if character.lifespan.is_dead():
                    character.status = CharacterStatus.DEAD
                    character.death_cause = "天劫雷火焚脉，寿元耗尽坐化"
                    _post_fail("道基崩溃，寿尽道消")
                    return {
                        "success": False,
                        "is_major": True,
                        "is_fatal": True,
                        "fail_tier": "DEATH",
                        "prob_pct": round(final_prob * 100, 1),
                        "judge_source": judge_source,
                        "judge_reason": judge_reason,
                        "message": (
                            f"【雷火焚脉 · 寿尽道消】\n"
                            f"雷劫入体撕裂丹田，寿元被强行削去 {lost_years} 岁！\n"
                            f"道友阳寿彻底耗尽，当场坐化解体，真灵归于天地……{judge_line}"
                        ),
                    }

                # 境界跌落一阶
                character.realm.sub_tier = max(0, character.realm.sub_tier - 1)
                _post_fail("道基崩溃，境界跌落")
                return {
                    "success": False,
                    "is_major": True,
                    "is_fatal": False,
                    "fail_tier": "BASE_COLLAPSE",
                    "prob_pct": round(final_prob * 100, 1),
                    "judge_source": judge_source,
                    "judge_reason": judge_reason,
                    "message": (
                        f"【雷火焚脉 · 道基崩溃】\n"
                        f"雷劫入体撕裂丹田，肉身受创过巨！寿元被天道强行削去 {lost_years} 岁！\n"
                        f"境界跌落至【{character.realm.name}】，大限骤然逼近！{judge_line}"
                    )
                }
            elif fail_roll <= 65:
                # 3. 走火入魔 (25%): 道心跌落
                character.karma.dao_heart = max(0, character.karma.dao_heart - 25)
                return {
                    "success": False,
                    "is_major": True,
                    "is_fatal": False,
                    "fail_tier": "HEART_DEMON",
                    "prob_pct": round(final_prob * 100, 1),
                    "judge_source": judge_source,
                    "judge_reason": judge_reason,
                    "message": (
                        f"【心魔乘隙 · 走火入魔】\n"
                        f"雷劫轰击之时心魔幻境侵入识海！道友道心动摇，狂喷精血！\n"
                        f"道心值重挫 -25 点，神识恍惚，短时间内难以再聚真元！{judge_line}"
                    )
                }
            else:
                # 4. 经脉震荡受创 (35%)
                return {
                    "success": False,
                    "is_major": True,
                    "is_fatal": False,
                    "fail_tier": "WOUNDED",
                    "prob_pct": round(final_prob * 100, 1),
                    "judge_source": judge_source,
                    "judge_reason": judge_reason,
                    "message": (
                        f"【神雷震体 · 侥幸逃生】\n"
                        f"渡劫功败垂成，狂暴雷火震伤奇经八脉，修为损耗大半！\n"
                        f"虽保全性命与道基，但需好生调养静修方可再图突破。{judge_line}"
                    )
                }
