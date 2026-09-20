"""
斗法天命落账：AI 提案 → 规则执行（含 escalate spawn）
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from config import (
    KARMA_KILL_SAME_TIER,
    KARMA_KILL_LOWER_TIER,
    WORLD_LOCATIONS,
)
from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.events import EventEngine
from core.clock import WorldClock
from storage.db import CharacterRepository
from ai.gateway import AIGateway, ai_ready, ai_block_reason
from ai.facts import build_fact_pack
from ai.gate import gate


def _spawn_from_proposal(spawn: Dict[str, Any], user_id_prefix: str = "ai_npc") -> Character:
    """按门禁清洗后的 spawn 字典造一名 NPC（入世界表）"""
    now = time.time()
    c = WorldClock.create_new_character(
        f"{user_id_prefix}_{spawn['name']}_{int(now)%100000}",
        spawn["name"],
    )
    c.realm.tier = max(0, min(9, int(spawn.get("tier", 1))))
    c.spirit_stones = 100 + c.realm.tier * 80
    if spawn.get("sin"):
        c.karma.add_sin(int(spawn["sin"]))
    c.location = spawn.get("location") or c.location
    return c


class CombatFateEngine:
    """AI 天命斗法（保留规则护栏）"""

    @staticmethod
    def resolve_ambush(
        attacker: Character,
        defender: Character,
        *,
        use_ai: bool = True,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        由 AI（或降级）给出结局提案，再执行效果。
        kill：目标死亡 + 夺宝（沿用规则夺宝比例）
        escalate：生成幕后人物并返回
        """
        # 硬前置：安全区/已死
        def_loc = WORLD_LOCATIONS.get(defender.location, {"is_safe": True})
        if defender.status == CharacterStatus.DEAD:
            return {"success": False, "message": "对方已坐化陨落。"}
        if def_loc.get("is_safe", False):
            return {
                "success": False,
                "message": f"【天道庇护】{defender.name} 身处【{defender.location}】安全大阵之内，不可动武！",
            }
        if attacker.status == CharacterStatus.DEAD:
            return {"success": False, "message": "已死之身不可动手。"}
        # 新手庇护：对称设计，双方任一在庇护中不可动手
        now = time.time()
        if defender.is_newbie_protected(now):
            return {
                "success": False,
                "message": (
                    f"【天道庇护·新手】{defender.name} 入世未满 72 小时，"
                    f"尚在新手庇护期内，不可被攻击。"
                ),
            }
        if attacker.is_newbie_protected(now):
            return {
                "success": False,
                "message": (
                    f"【天道庇护·新手】{attacker.name} 尚在新手庇护期内，"
                    f"不可主动伤人（对称设计）。"
                ),
            }
        # 离线归隐庇护：双方任一在庇护中不可动手
        from core.protection import ProtectionEngine
        ok_d, reason_d = ProtectionEngine.can_be_attacked(defender, now)
        if not ok_d:
            return {"success": False, "message": reason_d}
        ok_a, reason_a = ProtectionEngine.can_be_attacked(attacker, now)
        if not ok_a and "归隐" in (reason_a or ""):
            return {"success": False, "message": reason_a}
        if not ai_ready():
            return {"success": False, "message": ai_block_reason()}

        from core.combat import CombatEngine
        att_p = CombatEngine.calculate_power(attacker)
        def_p = CombatEngine.calculate_power(defender)
        rule_hint = att_p / max(1.0, att_p + def_p)

        ProtectionEngine.mark_combat(attacker)
        ProtectionEngine.mark_combat(defender)

        # 围剿 + 结拜加成
        try:
            from core.hunt import siege_multiplier, settle_kill

            siege = siege_multiplier(attacker, defender)
        except Exception:
            siege = 1.0
            settle_kill = None
        try:
            from core.social_bonds import combat_sworn_bonus, sworn_defense_bonus

            from storage.db import CharacterRepository as CR

            bonus = 0.0
            for o in CR.list_all_alive():
                if o.id in (attacker.id, defender.id):
                    continue
                if o.location == attacker.location and combat_sworn_bonus(attacker, o) > 0:
                    bonus = max(bonus, combat_sworn_bonus(attacker, o))
            # 被攻击者结拜兄弟同场：防守侧加成（降低 attacker rule_hint）
            def_bonus = sworn_defense_bonus(attacker, defender)
            sworn_mult = (1.0 + bonus) * (1.0 - def_bonus) if def_bonus else (1.0 + bonus)
        except Exception:
            sworn_mult = 1.0

        facts = build_fact_pack(attacker, others=[defender])
        proposal = AIGateway.judge_combat(
            attacker, defender, rule_hint=min(0.95, rule_hint * siege * sworn_mult), facts=facts, context=context
        ) if use_ai else {"outcome": "standoff", "narrative": "双方对峙。", "effects": {}, "source": "off"}

        outcome = proposal.get("outcome", "standoff")
        narrative = proposal.get("narrative", "")
        effects = proposal.get("effects") or {}
        summary = EventEngine.apply_effects(attacker, effects)
        spawned = None
        report_lines = [narrative, f"（因果落账：{summary}）"]

        # 非击杀结局也入江湖账（与 NPC 对称可见）
        if outcome != "kill":
            try:
                import core.jianghu as jianghu

                jianghu.append_event(
                    kind="combat",
                    actor_ids=[attacker.id],
                    actor_names=[attacker.name],
                    target_ids=[defender.id],
                    location=attacker.location,
                    summary=f"{attacker.name} 与 {defender.name} 于 {attacker.location} 斗法：{outcome}",
                    rule_result={"outcome": outcome, "effects": effects},
                    narrative=(narrative or "")[:200],
                    ref_ids=[attacker.id, defender.id],
                    source="rule",
                )
            except Exception:
                pass

        if outcome == "kill":
            defender.status = CharacterStatus.DEAD
            defender.lifespan.death_timestamp = 0.0
            defender.death_cause = defender.death_cause or "斗法被杀"
            loot_pct = random.uniform(0.60, 0.80)
            looted = int(defender.spirit_stones * loot_pct)
            defender.spirit_stones -= looted
            attacker.spirit_stones += looted
            if defender.karma.is_blood_marked():
                attacker.karma.add_merit(60)
                report_lines.append("【代天除凶】功德金光护体。")
            else:
                gain_sin = KARMA_KILL_SAME_TIER if defender.realm.tier >= attacker.realm.tier else KARMA_KILL_LOWER_TIER
                attacker.karma.add_sin(gain_sin)
                report_lines.append(f"【杀人夺宝】夺走 {looted} 灵石，业力 +{gain_sin}。")
            try:
                if settle_kill:
                    hr = settle_kill(attacker, defender)
                    if hr:
                        report_lines.append(f"【除凶令】功德 +{hr.get('merit')}，业力 -{hr.get('sin_reduced')}。")
                from core.hunt import settle_hunter_slain

                chs = settle_hunter_slain(defender, attacker)
                if chs:
                    report_lines.append(f"【反悬赏】你反杀猎人，功德 +{chs.get('merit')}。")
            except Exception:
                pass
            report_lines.append(f"【道途终局】{defender.name} 身死道消。")
            try:
                from core.memory import record_event
                record_event(
                    type="KILL",
                    actor=attacker,
                    target=defender,
                    summary=f"{attacker.name} 斩杀 {defender.name} 于 {attacker.location}",
                    location=attacker.location,
                    effects_digest=f"夺灵石{looted}",
                )
                from core.npc_mind import on_kill_update_attitudes
                on_kill_update_attitudes(attacker, defender)
                from core import rumors
                from core.collusion import ensure_link

                rumors.note_kill(attacker.name, defender.name, attacker.location)
                ensure_link(attacker, defender, "仇", note=f"斩杀于{attacker.location}")
                try:
                    from core.jianghu_sim import JianghuSimulator

                    casc = JianghuSimulator.cascade_kill(
                        attacker, defender, location=attacker.location, loot=looted
                    )
                    if casc:
                        report_lines.extend([f"【涟漪】{x}" for x in casc[:4]])
                except Exception:
                    try:
                        import core.jianghu as jianghu

                        jianghu.append_event(
                            kind="kill",
                            actor_ids=[attacker.id],
                            actor_names=[attacker.name],
                            target_ids=[defender.id],
                            location=attacker.location,
                            summary=f"{attacker.name} 于 {attacker.location} 斩 {defender.name}",
                            rule_result={"looted": looted, "outcome": "kill"},
                            narrative=narrative[:200],
                            ref_ids=[attacker.id, defender.id],
                            source="rule",
                        )
                    except Exception:
                        pass
                # 同宗 NPC 对凶手记仇边
                for c in CharacterRepository.list_all_alive():
                    if c.id in (attacker.id, defender.id):
                        continue
                    if c.sect and c.sect == defender.sect:
                        ensure_link(c, attacker, "仇", note=f"同门{defender.name}被斩")
                try:
                    from config import CHANNEL_KILL_MIN_TIER
                    from core.world_channel import WorldChannel

                    if defender.realm.tier >= CHANNEL_KILL_MIN_TIER or defender.karma.is_blood_marked():
                        WorldChannel.post(
                            "kill",
                            f"【血雨】{attacker.name} 于 {attacker.location} 斩 {defender.name}，天机显影。",
                            level="major",
                            actor=attacker.name,
                            location=attacker.location,
                        )
                except Exception:
                    pass
            except Exception:
                pass

        elif outcome == "escalate" and proposal.get("spawn"):
            spawn_cfg = proposal["spawn"]
            spawned = _spawn_from_proposal(spawn_cfg)
            report_lines.append(
                f"【幕后现身】【{spawned.name}】（{spawned.realm.name}）自暗处踏出：{spawn_cfg.get('reason','')}！"
            )

        elif outcome == "lose":
            attacker.realm.current_exp = max(0, attacker.realm.current_exp - int(attacker.realm.max_exp * 0.15))
            report_lines.append(f"{attacker.name} 经脉受损，修为略挫。")

        elif outcome == "escape":
            report_lines.append(f"{defender.name} 见机极快，血遁远去。")

        ProtectionEngine.clear_combat(attacker)
        ProtectionEngine.clear_combat(defender)

        return {
            "success": True,
            "outcome": outcome,
            "narrative": narrative,
            "report": "\n".join(report_lines),
            "effects_summary": summary,
            "target_died": outcome == "kill",
            "spawned": spawned,
            "source": proposal.get("source", "local"),
            "proposal": proposal,
        }
