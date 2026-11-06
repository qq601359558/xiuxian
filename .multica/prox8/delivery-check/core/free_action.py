"""
自由输入：玩家自然语言 → 意图裁决 → 效果落账
AI 高自由叙事，规则门禁管数值与合法性
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from core.events import EventEngine
from core.combat_fate import _spawn_from_proposal
from ai.facts import FactPack, build_fact_pack
from ai.gate import gate
from ai.gateway import AIGateway, ai_ready, ai_block_reason
from ai.audit import write_audit


# 意图白名单（越权直接拒，不进 AI 数值）
INTENT_WHITELIST = {
    "observe",      # 观察/打听
    "travel",       # 赶路
    "social",       # 交谈/示好/结仇
    "fight",        # 攻击/伏击
    "steal",        # 偷窃/摸尸
    "cultivate",    # 吐纳/感悟
    "meditate",     # 闭关（转系统指令）
    "trade",        # 买卖意图（只给叙事引导）
    "bounty",       # 悬赏相关叙事
    "research",     # 探查/推演
    "roleplay",     # 纯扮演无实质
}

# 本地关键词兜底（无 API 时）
_KW = {
    "travel": ["前往", "赶到", "飞往", "赶路", "去往"],
    "fight": ["伏击", "偷袭", "动手杀", "斩杀", "灭杀", "杀掉", "动手", "杀"],
    "steal": ["偷走", "摸尸", "顺走", "窃取", "偷"],
    "social": ["结交", "挑衅", "拜见", "求丹", "攀谈"],
    "cultivate": ["吐纳", "打坐", "感悟", "修炼", "参悟"],
    "observe": ["打听", "观察", "环顾", "环视", "张望"],
    "research": ["推演", "探查", "搜寻", "寻找"],
    "travel_2": ["去", "回"],
}


def _local_intent(text: str) -> str:
    # 长词优先，避免「打听」被「打」误判为 fight
    pairs = []
    for intent, words in _KW.items():
        base = intent.replace("_2", "")
        for w in words:
            pairs.append((len(w), w, base))
    pairs.sort(reverse=True)
    for _ln, w, intent in pairs:
        if w in text:
            return intent
    return "roleplay"


def _local_free_result(character: Character, intent: str, text: str) -> Dict[str, Any]:
    """无 AI 时的本地分叉（仍有戏剧，效果受门禁）"""
    name = character.name
    loc = character.location
    if intent == "travel":
        # 不真正传送，给引导
        return {
            "outcome": "observe",
            "narrative": f"{name}在{loc}盘算路径。若要真正动身，请用 /前往 <地点>。",
            "effects": {},
        }
    if intent == "fight":
        return {
            "outcome": "observe",
            "narrative": f"{name}杀心微动，环顾四周——请用 /斗法 <道号> 指定目标，天道才好落账。",
            "effects": {},
        }
    if intent == "cultivate":
        ev_effects = {"exp": random.randint(5, 25)}
        return {
            "outcome": "cultivate",
            "narrative": f"{name}于{loc}就地吐纳片刻，灵气微润。",
            "effects": ev_effects,
        }
    if intent == "steal":
        if random.random() < 0.4:
            return {
                "outcome": "twist",
                "narrative": f"{name}探手去摸，却被暗桩察觉，讪讪收回，虚惊一场。",
                "effects": {"dao_heart": -1},
            }
        return {
            "outcome": "observe",
            "narrative": f"{name}四下张望，并无合适下手之机。",
            "effects": {},
        }
    if intent == "social":
        return {
            "outcome": "roleplay",
            "narrative": f"{name}在{loc}与人寒暄数句，风闻些许市井碎语，未起波澜。",
            "effects": {},
        }
    return {
        "outcome": "roleplay",
        "narrative": f"{name}低语：「{text[:40]}」——山风过耳，并无回应。",
        "effects": {},
    }


class FreeActionEngine:
    """自由输入裁决"""

    ALLOWED_OUTCOMES = {
        "observe", "travel", "social", "fight", "steal", "cultivate",
        "roleplay", "twist", "fortune", "crisis", "escalate",
    }

    @staticmethod
    def resolve(
        character: Character,
        raw_text: str,
        *,
        facts: Optional[FactPack] = None,
        others: Optional[List[Character]] = None,
    ) -> Dict[str, Any]:
        if character.status == CharacterStatus.DEAD:
            return {"ok": False, "error": "死人不可妄动。"}
        if not ai_ready():
            return {"ok": False, "error": ai_block_reason()}

        cleaned = gate.sanitize_player_text(raw_text)
        if not cleaned:
            return {"ok": False, "error": "空言无物。"}

        if facts is None:
            from core.memory import enrich_facts_with_memory
            facts = enrich_facts_with_memory(character, others=others, kind="free_action")
        elif "memory_block" not in facts.data:
            from core.memory import enrich_facts_with_memory
            facts = enrich_facts_with_memory(character, facts=facts, others=others, kind="free_action")

        proposal = AIGateway.judge_free_action(character, cleaned, facts=facts)
        intent = proposal.get("intent") or _local_intent(cleaned)
        if intent not in INTENT_WHITELIST:
            intent = "roleplay"

        ok, msg, admitted = gate.admit("event", proposal, facts, actor_id=character.id)
        if not ok:
            return {"ok": False, "error": msg}

        outcome = proposal.get("outcome") or intent
        if outcome not in FreeActionEngine.ALLOWED_OUTCOMES:
            outcome = "roleplay"

        narrative = admitted.get("narrative") or proposal.get("narrative") or "无事发生。"
        effects = admitted.get("effects") or {}
        summary = EventEngine.apply_effects(character, effects)

        spawned = None
        if outcome == "escalate" and admitted.get("spawn"):
            spawned = _spawn_from_proposal(admitted["spawn"])

        # 硬拦截：自由文本不得直接完成需要系统指令的强动作
        hard_note = ""
        if intent == "travel" and proposal.get("location"):
            hard_note = "（真正迁跃请用 /前往）"
        if intent == "fight":
            hard_note = "（真正动手请用 /斗法 <道号>）"

        # 落入长期事件账
        from core.memory import record_event, ensure_bio
        ensure_bio(character)
        eid = record_event(
            type="FREE",
            actor=character,
            summary=f"{intent}:{cleaned[:40]} → {narrative[:40]}",
            location=character.location,
            effects_digest=summary,
        )

        write_audit({
            "ts": time.time(),
            "actor": character.id,
            "kind": "free_action",
            "intent": intent,
            "outcome": outcome,
            "effects": effects,
            "text_len": len(cleaned),
            "source": proposal.get("source", "local"),
            "event_id": eid,
        })

        return {
            "ok": True,
            "intent": intent,
            "outcome": outcome,
            "narrative": narrative,
            "effects_summary": summary,
            "spawned": spawned,
            "source": proposal.get("source", "local"),
            "event_id": eid,
            "text": f"【{intent}】{narrative}\n落账：{summary}{hard_note}",
        }
