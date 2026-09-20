"""
AI 事件提案与数值钳制校验（规则引擎仍是唯一执行权威）
"""
from typing import Any, Dict, Tuple

from config import EVENT_EFFECT_CAPS


class EventValidator:
    """校验并钳制 AI 提出的事件效果"""

    ALLOWED_EFFECT_KEYS = {
        "exp", "stones", "lifespan_years", "sin", "merit", "dao_heart",
        "item", "skill", "blood_mark",
    }

    @staticmethod
    def clamp_effects(effects: Dict[str, Any]) -> Dict[str, Any]:
        caps = EVENT_EFFECT_CAPS
        out: Dict[str, Any] = {}

        if "exp" in effects:
            try:
                v = int(effects["exp"])
            except (TypeError, ValueError):
                v = 0
            out["exp"] = max(-caps["exp"], min(caps["exp"], v))

        if "stones" in effects:
            try:
                v = int(effects["stones"])
            except (TypeError, ValueError):
                v = 0
            if v >= 0:
                out["stones"] = min(caps["stones_gain"], v)
            else:
                out["stones"] = max(-caps["stones_lose"], v)

        if "lifespan_years" in effects:
            try:
                v = float(effects["lifespan_years"])
            except (TypeError, ValueError):
                v = 0.0
            if v >= 0:
                out["lifespan_years"] = min(caps["lifespan_gain"], v)
            else:
                out["lifespan_years"] = max(-caps["lifespan_burn"], v)

        if "sin" in effects:
            try:
                v = int(effects["sin"])
            except (TypeError, ValueError):
                v = 0
            out["sin"] = max(0, min(caps["sin"], v))

        if "merit" in effects:
            try:
                v = int(effects["merit"])
            except (TypeError, ValueError):
                v = 0
            out["merit"] = max(0, min(caps["merit"], v))

        if "dao_heart" in effects:
            try:
                v = int(effects["dao_heart"])
            except (TypeError, ValueError):
                v = 0
            limit = caps["dao_heart"]
            out["dao_heart"] = max(-abs(limit), min(abs(limit), v))

        if effects.get("item"):
            out["item"] = str(effects["item"])[:24]
        if effects.get("skill"):
            out["skill"] = str(effects["skill"])[:24]
        if effects.get("blood_mark"):
            out["blood_mark"] = True

        return out

    @staticmethod
    def validate_event(data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        :return: (是否可用, 说明, 清洗后的事件)
        """
        if not isinstance(data, dict):
            return False, "事件不是对象", {}

        etype = str(data.get("type", "omen")).lower()
        if etype not in ("fortune", "crisis", "omen"):
            etype = "omen"

        title = str(data.get("title", "无名异象")).strip()[:40] or "无名异象"
        narrative = str(data.get("narrative", "")).strip()[:500]
        if not narrative:
            return False, "缺少叙事", {}

        effects = data.get("effects") or {}
        if not isinstance(effects, dict):
            effects = {}
        cleaned = EventValidator.clamp_effects(effects)

        # 至少要有叙事；效果可为空（纯异象）
        return True, "ok", {
            "type": etype,
            "title": title,
            "narrative": narrative,
            "effects": cleaned,
        }
