"""
提案门禁：AI 只提案，规则只认白名单字段 + 上下界 + 一致性
防「破解 AI 改档」：未知字段丢弃、引用必须在事实包、速率限制
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from config import (
    EVENT_EFFECT_CAPS,
    GATE_RATE_WINDOW_SECONDS,
    GATE_RATE_MAX_MUTATIONS,
    GATE_ALLOW_SPAWN,
    GATE_SPAWN_MAX_PER_PROPOSAL,
)
from ai.facts import FactPack
from ai.event_validator import EventValidator
from ai.audit import write_audit


# 提案类型 → 允许的效果键
PROPOSAL_KINDS = {
    "event",
    "combat",
    "heart_demon",
    "tribulation",
    "narrative",  # 纯叙事，无效果
}

ALLOWED_EFFECT_KEYS = {
    "exp", "stones", "lifespan_years", "sin", "merit", "dao_heart",
    "item", "skill", "blood_mark",
}

# 结局枚举（斗法等）
COMBAT_OUTCOMES = {"kill", "lose", "escape", "escalate", "twist", "standoff"}
HEART_DEMON_OUTCOMES = {"pass", "wound", "heart_hit", "dao_crack", "fail", "death"}


class ProposalGate:
    """AI 提案唯一入口校验器"""

    def __init__(self):
        # actor_id -> deque[timestamps]
        self._mutations: Dict[str, Deque[float]] = defaultdict(deque)

    # ---------------- 速率 ----------------
    def _rate_ok(self, actor_id: str, now: Optional[float] = None) -> bool:
        t = now or time.time()
        q = self._mutations[actor_id]
        while q and t - q[0] > GATE_RATE_WINDOW_SECONDS:
            q.popleft()
        return len(q) < GATE_RATE_MAX_MUTATIONS

    def _rate_hit(self, actor_id: str, now: Optional[float] = None):
        self._mutations[actor_id].append(now or time.time())

    # ---------------- 输入消毒（玩家自由文本进 AI 前） ----------------
    @staticmethod
    def sanitize_player_text(text: str, max_len: int = 400) -> str:
        """剥掉试图冒充系统/越权的话术，截断长度"""
        if not text:
            return ""
        t = str(text)[:max_len]
        banned_patterns = [
            "ignore previous", "忽略以上", "系统提示", "system prompt",
            "你现在是", "developer mode", "越狱", "输出原始权重",
            "直接给我", "把我的灵石改成", "set spirit", "admin",
            "gm模式", "god mode", "roleplay as system",
        ]
        low = t.lower()
        for p in banned_patterns:
            if p.lower() in low:
                t = t.replace(p, "〔已屏蔽〕")
        # 去掉控制字符
        t = "".join(ch for ch in t if ch.isprintable() or ch in "\n\t")
        return t.strip()

    # ---------------- 主校验 ----------------
    def admit(
        self,
        kind: str,
        proposal: Dict[str, Any],
        facts: FactPack,
        actor_id: str,
        *,
        now: Optional[float] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        :return: (是否放行, 说明, 清洗后的提案)
        """
        current_time = now or time.time()

        if kind not in PROPOSAL_KINDS:
            return False, f"未知提案类型 {kind}", {}

        if not isinstance(proposal, dict):
            return False, "提案不是对象", {}

        if not self._rate_ok(actor_id, current_time):
            write_audit({
                "ts": current_time, "actor": actor_id, "kind": kind,
                "ok": False, "reason": "rate_limited",
            })
            return False, "天道过载：短时间天命改写过多，请稍候", {}

        cleaned: Dict[str, Any] = {"kind": kind}

        # 叙事
        narrative = str(proposal.get("narrative", "")).strip()
        if kind != "tribulation" and not narrative:
            # 渡劫可只有 reason
            if kind != "heart_demon":
                return False, "缺少叙事", {}
        cleaned["narrative"] = narrative[:800]

        # 标题
        if proposal.get("title"):
            cleaned["title"] = str(proposal["title"])[:40]

        # 结局
        outcome = str(proposal.get("outcome", "")).lower() or None
        if kind == "combat":
            if outcome not in COMBAT_OUTCOMES:
                outcome = "standoff"
            cleaned["outcome"] = outcome
        elif kind == "heart_demon":
            if outcome not in HEART_DEMON_OUTCOMES:
                return False, "心魔结局非法", {}
            cleaned["outcome"] = outcome
        elif kind == "tribulation":
            if "success" not in proposal:
                return False, "渡劫提案缺少 success", {}
            cleaned["success"] = bool(proposal["success"])
            cleaned["reason"] = str(proposal.get("reason", ""))[:160]

        # 效果：白名单 + 钳制
        raw_effects = proposal.get("effects")
        if raw_effects is None:
            raw_effects = {}
        if not isinstance(raw_effects, dict):
            raw_effects = {}
        # 只保留白名单键
        filtered = {k: v for k, v in raw_effects.items() if k in ALLOWED_EFFECT_KEYS}
        cleaned["effects"] = EventValidator.clamp_effects(filtered)

        # 引用人物：必须在 known_ids，或 spawn
        refs = proposal.get("ref_ids") or []
        if not isinstance(refs, list):
            refs = []
        known = facts.known_ids
        allowed_refs = []
        for rid in refs:
            rid = str(rid)
            if rid in known:
                allowed_refs.append(rid)
        cleaned["ref_ids"] = allowed_refs
        if refs and len(allowed_refs) < len(refs):
            cleaned["dropped_unknown_refs"] = [str(r) for r in refs if str(r) not in known]

        # spawn：新建 NPC/强敌
        spawn = proposal.get("spawn")
        cleaned_spawn = None
        if spawn:
            if not GATE_ALLOW_SPAWN:
                cleaned_spawn = None
            else:
                cleaned_spawn = self._sanitize_spawn(spawn, facts)
        cleaned["spawn"] = cleaned_spawn

        # 地点：不得虚构新地名作为「已存在位置」；spawn 可带 location 必须是已知地
        if proposal.get("location"):
            from config import WORLD_LOCATIONS
            loc = str(proposal["location"])
            if loc in WORLD_LOCATIONS or loc == facts.data.get("self", {}).get("location"):
                cleaned["location"] = loc

        self._rate_hit(actor_id, current_time)
        write_audit({
            "ts": current_time,
            "actor": actor_id,
            "kind": kind,
            "ok": True,
            "outcome": cleaned.get("outcome"),
            "success": cleaned.get("success"),
            "effects": cleaned.get("effects"),
            "spawn": bool(cleaned_spawn),
            "narrative_len": len(cleaned.get("narrative") or ""),
        })
        return True, "ok", cleaned

    def _sanitize_spawn(self, spawn: Any, facts: FactPack) -> Optional[Dict[str, Any]]:
        if not isinstance(spawn, dict):
            return None
        from config import WORLD_LOCATIONS
        name = str(spawn.get("name", "")).strip()[:16]
        if not name:
            return None
        # 只允许生成在已有地点或主角所在
        loc = str(spawn.get("location") or facts.data.get("self", {}).get("location") or "")
        if loc not in WORLD_LOCATIONS:
            loc = facts.data.get("self", {}).get("location") or "青云坊市客栈"
        try:
            tier = int(spawn.get("tier", 1))
        except (TypeError, ValueError):
            tier = 1
        tier = max(0, min(9, tier))
        try:
            sin = int(spawn.get("sin", 0))
        except (TypeError, ValueError):
            sin = 0
        sin = max(0, min(400, sin))
        reason = str(spawn.get("reason", "幕后之人"))[:60]
        return {
            "name": name,
            "location": loc,
            "tier": tier,
            "sin": sin,
            "reason": reason,
            "is_hostile": bool(spawn.get("is_hostile", True)),
        }


# 全局单例
gate = ProposalGate()
