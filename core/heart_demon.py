"""
心魔回合：会话状态 + 结果落账（规则执行，AI 只提案）
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.models import Character, CharacterStatus
from core.events import EventEngine
from ai.gateway import AIGateway, ai_ready, ai_block_reason
from ai.gate import gate
from ai.facts import build_fact_pack


class HeartDemonSession(BaseModel):
    """一次问心回合"""
    id: str
    character_id: str
    narrative: str
    options: List[Dict[str, str]] = Field(default_factory=list)
    created_at: float = 0.0
    resolved: bool = False
    result: Optional[Dict[str, Any]] = None


class HeartDemonEngine:
    """心魔：开场 → 玩家选择 → AI 判定 → 规则落账"""

    @staticmethod
    def start(character: Character, facts=None) -> HeartDemonSession:
        if facts is None:
            facts = build_fact_pack(character)
        session_data = AIGateway.generate_heart_demon_session(character, facts=facts)
        return HeartDemonSession(
            id=f"hd_{character.id}_{int(time.time()*1000)%1000000}",
            character_id=character.id,
            narrative=session_data["narrative"],
            options=session_data["options"],
            created_at=time.time(),
        )

    @staticmethod
    def resolve(
        character: Character,
        session: HeartDemonSession,
        choice_id: Optional[str] = None,
        free_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        结算心魔。优先 free_text（其他），否则用 choice_id 匹配选项。
        """
        if session.resolved:
            return {"success": False, "message": "此问心已了结。"}
        if not ai_ready():
            return {"success": False, "message": ai_block_reason(), "is_fatal": False}

        is_free = bool(free_text and free_text.strip())
        if is_free:
            label = gate.sanitize_player_text(free_text)
        else:
            label = choice_id or "yield"
            for opt in session.options:
                if opt.get("id") == choice_id or opt.get("label") == choice_id:
                    label = opt.get("label", choice_id)
                    break

        facts = build_fact_pack(character)
        verdict = AIGateway.judge_heart_demon_choice(
            character, session.narrative, label, is_free_text=is_free, facts=facts
        )

        # 规则落账
        effects = verdict.get("effects") or {}
        summary = EventEngine.apply_effects(character, effects)
        tmod = float(verdict.get("tribulation_mod") or 0.0)
        tmod = max(-0.15, min(0.15, tmod))

        # outcome 兜底
        outcome = verdict.get("outcome")
        if outcome not in ("pass", "wound", "heart_hit", "dao_crack", "fail", "death"):
            outcome = "wound"

        # death 极罕见：仅当 AI 明确 death 且道心极低，才允许；否则降为 fail
        if outcome == "death":
            if character.karma.dao_heart > 20:
                outcome = "fail"
            else:
                character.status = CharacterStatus.DEAD
                character.lifespan.death_timestamp = 0.0
                character.death_cause = character.death_cause or "心魔道消"

        session.resolved = True
        session.result = {
            "outcome": outcome,
            "narrative": verdict.get("narrative", ""),
            "effects_summary": summary,
            "tribulation_mod": tmod,
            "source": verdict.get("source", "local"),
            "choice": label,
            "is_free_text": is_free,
        }
        return {
            "success": True,
            "outcome": outcome,
            "narrative": session.result["narrative"],
            "effects_summary": summary,
            "tribulation_mod": tmod,
            "is_fatal": character.status == CharacterStatus.DEAD,
            "source": session.result["source"],
        }
