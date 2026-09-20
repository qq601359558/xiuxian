"""
世界事件引擎：机缘 / 危机 / 异象
AI 提案 + 规则钳制执行；无 API 时走本地模板
"""
import random
import time
from typing import Any, Dict, Optional

from config import (
    EVENT_TRIGGER_CHANCE,
    EVENT_WEIGHTS,
    WORLD_LOCATIONS,
    ITEM_CATALOG,
)
from core.models import Character, CharacterStatus
from ai.gateway import AIGateway, ai_ready
from ai.event_validator import EventValidator


class EventEngine:
    """随机事件裁决与落地"""

    @staticmethod
    def should_trigger(chance: float = EVENT_TRIGGER_CHANCE, rng: Optional[random.Random] = None) -> bool:
        r = rng or random
        return r.random() < chance

    @staticmethod
    def pick_type(rng: Optional[random.Random] = None) -> str:
        r = rng or random
        types = list(EVENT_WEIGHTS.keys())
        weights = [EVENT_WEIGHTS[t] for t in types]
        return r.choices(types, weights=weights, k=1)[0]

    @staticmethod
    def _local_event(character: Character, etype: str) -> Dict[str, Any]:
        """无 AI 时的本地因果模板"""
        loc = character.location
        rem = character.lifespan.get_remaining_years()
        name = character.name
        tier = character.realm.name

        if etype == "fortune":
            pool = [
                {
                    "type": "fortune",
                    "title": "古洞残卷",
                    "narrative": f"行至{loc}附近，崖壁藤蔓后隐有古洞。{name}拂尘探入，得残破玉简一卷，神识沉入顿感真元活泼。",
                    "effects": {"exp": random.randint(80, 220)},
                },
                {
                    "type": "fortune",
                    "title": "灵泉偶遇",
                    "narrative": f"山风送来异香，{name}循迹至无主灵泉，掬水饮之，经脉温润，道基微固。",
                    "effects": {"exp": random.randint(40, 120), "merit": 0},
                },
                {
                    "type": "fortune",
                    "title": "散修遗蜕",
                    "narrative": f"荒径旁见无名修士坐化遗蜕，{name}躬身敛骨，其储物袋中尚余灵石若干。",
                    "effects": {"stones": random.randint(30, 90), "merit": 5},
                },
                {
                    "type": "fortune",
                    "title": "剑冢共鸣",
                    "narrative": f"路过残破剑冢，一柄锈剑轻鸣。{name}驻足片刻，剑意入体，杀伐之念更利。",
                    "effects": {"exp": random.randint(60, 160), "dao_heart": -3},
                },
            ]
        elif etype == "crisis":
            pool = [
                {
                    "type": "crisis",
                    "title": "妖兽扑杀",
                    "narrative": f"林间腥风骤起，一头妖兽扑向{name}！仓促接战，虽将其惊走，却被利爪撕开护体罡气。",
                    "effects": {"lifespan_years": -round(random.uniform(0.5, 2.0), 1), "exp": random.randint(20, 60)},
                },
                {
                    "type": "crisis",
                    "title": "劫修拦路",
                    "narrative": f"三名蒙面劫修在{loc}外围截住{name}，强索买路钱。{name}不愿多造杀孽，破财消灾。",
                    "effects": {"stones": -random.randint(40, 120)},
                },
                {
                    "type": "crisis",
                    "title": "心绪不宁",
                    "narrative": f"夜半吐纳，{name}忽见幻象：寿元灯焰明灭不定。惊醒后冷汗涔涔，道心微挫。",
                    "effects": {"dao_heart": -random.randint(3, 10)},
                },
                {
                    "type": "crisis",
                    "title": "血煞反噬",
                    "narrative": f"旧伤复发，{name}体内残余杀气冲撞识海，若不收敛，恐成日后心魔之种。",
                    "effects": {"sin": min(15, max(0, character.karma.sin_value // 10)), "dao_heart": -5},
                },
            ]
        else:
            pool = [
                {
                    "type": "omen",
                    "title": "天象示警",
                    "narrative": f"西方天际赤霞如血，{loc}上空鸦群盘旋不去。市井传言：近日或有腥风。",
                    "effects": {},
                },
                {
                    "type": "omen",
                    "title": "灵脉低语",
                    "narrative": f"地脉微颤，{name}隐约听见灵石矿脉深处的嗡鸣，似有古物将醒。",
                    "effects": {},
                },
                {
                    "type": "omen",
                    "title": "大限临近",
                    "narrative": (
                        f"铜镜中{name}鬓角霜色更重。剩余寿元仅约 {rem:.1f} 岁，光阴如刀。"
                        if rem < 30 else
                        f"晨起照镜，{name}神色如常，唯目光更深。{tier}之路，仍长。"
                    ),
                    "effects": {},
                },
            ]

        ev = random.choice(pool)
        ok, _msg, cleaned = EventValidator.validate_event(ev)
        return cleaned if ok else {
            "type": etype, "title": "无事发生", "narrative": "风平浪静，无事。", "effects": {}
        }

    @staticmethod
    def apply_effects(character: Character, effects: Dict[str, Any]) -> str:
        """执行已钳制的效果，返回一句结果摘要"""
        notes = []

        if effects.get("exp"):
            exp = int(effects["exp"])
            before = character.realm.current_exp
            character.realm.current_exp = max(
                0, min(character.realm.max_exp, character.realm.current_exp + exp)
            )
            delta = character.realm.current_exp - before
            if delta:
                notes.append(f"修为{delta:+d}")

        if effects.get("stones"):
            st = int(effects["stones"])
            character.spirit_stones = max(0, character.spirit_stones + st)
            notes.append(f"灵石{st:+d}")

        if effects.get("lifespan_years"):
            ly = float(effects["lifespan_years"])
            if ly > 0:
                character.lifespan.add_lifespan(ly)
                notes.append(f"寿元+{ly:.1f}")
            elif ly < 0:
                character.lifespan.burn_lifespan(-ly)
                notes.append(f"寿元{ly:.1f}")

        if effects.get("sin"):
            character.karma.add_sin(int(effects["sin"]))
            try:
                from core.player_echo import record_player_sin

                record_player_sin(character, int(effects["sin"]), reason="事件业力")
            except Exception:
                pass
            notes.append(f"业力+{int(effects['sin'])}")

        if effects.get("merit"):
            character.karma.add_merit(int(effects["merit"]))
            notes.append(f"功德+{int(effects['merit'])}")

        if effects.get("dao_heart"):
            dh = int(effects["dao_heart"])
            character.karma.dao_heart = max(0, min(100, character.karma.dao_heart + dh))
            notes.append(f"道心{dh:+d}")

        if effects.get("item"):
            item = str(effects["item"])
            # 限制只能发目录内或简单名
            if item in ITEM_CATALOG:
                if ITEM_CATALOG[item]["kind"] == "array":
                    character.arrays.append(item)
                else:
                    character.inventory.append(item)
                notes.append(f"获得【{item}】")
            else:
                character.inventory.append(item[:16])
                notes.append(f"获得【{item[:16]}】")

        if effects.get("skill"):
            sk = str(effects["skill"])[:16]
            if sk not in character.skills:
                character.skills.append(sk)
                notes.append(f"习得【{sk}】")

        return "；".join(notes) if notes else "无实质增减"

    @staticmethod
    def fire(
        character: Character,
        etype: Optional[str] = None,
        context: str = "",
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        触发一则世界事件。
        :return: 事件结果 dict 或 None（未触发）
        """
        if character.status == CharacterStatus.DEAD:
            return None
        if not force and not EventEngine.should_trigger():
            return None
        # 正式模式：无 AI 则不出世界事件（避免套话污染叙事）
        if not ai_ready() and not force:
            return None

        chosen_type = etype or EventEngine.pick_type()
        event = AIGateway.generate_world_event(character, chosen_type, context)
        source = "ai"
        if not event:
            if not ai_ready():
                return None
            event = EventEngine._local_event(character, chosen_type)
            source = "local"

        # 再钳一次（AI 路径已在 gateway 钳过，本地路径也过一遍）
        ok, _msg, cleaned = EventValidator.validate_event(event)
        if not ok:
            cleaned = EventEngine._local_event(character, chosen_type)
            source = "local"

        summary = EventEngine.apply_effects(character, cleaned["effects"])
        return {
            "source": source,
            "type": cleaned["type"],
            "title": cleaned["title"],
            "narrative": cleaned["narrative"],
            "effects_summary": summary,
            "effects": cleaned["effects"],
            "at": time.time(),
        }
