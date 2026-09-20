"""
NPC 主动互动：玩家到达某地时，同场 NPC 可能先开口
由态度/性格驱动；经门禁；可 shift 态度
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository
from core.npc_mind import (
    ensure_mind,
    attitude_toward,
    shift_attitude,
    ATTITUDE_LABELS,
    _is_npc,
)
from core.memory import record_event, ensure_bio
from core.here import list_here
from ai.gate import gate
from ai.gateway import ai_ready
from ai.audit import write_audit
from config import NPC_PROACTIVE_AI_BUDGET_PER_TICK, NPC_PROACTIVE_LOCAL_ONLY_AFTER
from server.log import log_event
from storage.db import WorldStateRepository

# 进程内 AI 开口预算（每窗口重置）；权威在 world_state
_BUDGET_KEY = "npc_proactive_ai_budget"
_ai_budget_used = 0
_budget_window_start = 0.0
_AI_BUDGET_WINDOW = 300.0  # 5 分钟窗口
_budget_loaded = False


def _ensure_budget_loaded() -> None:
    global _ai_budget_used, _budget_window_start, _budget_loaded
    if _budget_loaded:
        return
    try:
        data = WorldStateRepository.get(_BUDGET_KEY) or {}
        _ai_budget_used = int(data.get("used") or 0)
        _budget_window_start = float(data.get("window_start") or 0.0)
    except Exception:
        pass
    _budget_loaded = True


def _persist_budget() -> None:
    try:
        WorldStateRepository.set(
            _BUDGET_KEY,
            {"used": _ai_budget_used, "window_start": _budget_window_start},
        )
    except Exception:
        pass


def _consume_ai_budget() -> bool:
    """返回是否允许再调一次 AI；超预算则 False"""
    global _ai_budget_used, _budget_window_start
    _ensure_budget_loaded()
    now = time.time()
    if now - _budget_window_start > _AI_BUDGET_WINDOW:
        _budget_window_start = now
        _ai_budget_used = 0
        _persist_budget()
    if _ai_budget_used >= NPC_PROACTIVE_AI_BUDGET_PER_TICK:
        return False
    _ai_budget_used += 1
    _persist_budget()
    return True


# 主动开口概率（按态度）
PROACTIVE_CHANCE = {
    "hostile": 0.55,
    "wary": 0.35,
    "neutral": 0.22,
    "friendly": 0.40,
    "ally": 0.50,
}


def _local_opening(npc: Character, player: Character, att_label: str, personality: str) -> Dict[str, Any]:
    if att_label == "hostile":
        return {
            "line": f"{npc.name}目光一冷，手按兵刃：「{player.name}，你还敢来？」",
            "delta": 0,
        }
    if att_label == "ally":
        return {
            "line": f"{npc.name}拱手：「{player.name}道友，正要找你。」",
            "delta": 0,
        }
    if "贪" in (personality or ""):
        return {"line": f"{npc.name}搓了搓手指：「道友可是有买卖？」", "delta": 1}
    if "谨慎" in (personality or ""):
        return {"line": f"{npc.name}后退半步，打量你一眼，不语。", "delta": -1}
    if "豪爽" in (personality or ""):
        return {"line": f"{npc.name}朗声：「{player.name}！来得正好，坐。」", "delta": 2}
    if "记仇" in (personality or ""):
        return {"line": f"{npc.name}皮笑肉不笑：「哟，稀客。」", "delta": -1}
    return {"line": f"{npc.name}微微颔首：「{player.name}道友。」", "delta": 0}


class NpcProactiveEngine:
    """玩家进入场景时，可能被 NPC 主动搭话"""

    COOLDOWN_SECONDS = 90.0
    _last: Dict[str, float] = {}  # player_id -> ts

    @staticmethod
    def maybe_engage(
        player: Character,
        chance_scale: float = 1.0,
        max_speakers: int = 1,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        返回主动互动列表（可能为空）。
        每玩家冷却，避免刷屏。
        """
        if player.status == CharacterStatus.DEAD:
            return []
        now = time.time()
        last = NpcProactiveEngine._last.get(player.id, 0)
        if not force and (now - last) < NpcProactiveEngine.COOLDOWN_SECONDS:
            return []

        others = [c for c in list_here(player) if c.get("is_npc")]
        if not others:
            return []

        # 按态度优先：敌对/亲近更爱开口
        def prio(item):
            order = {"hostile": 0, "ally": 1, "friendly": 2, "wary": 3, "neutral": 4}
            return order.get(item.get("attitude") or "neutral", 5)

        others.sort(key=prio)

        results: List[Dict[str, Any]] = []
        for info in others:
            if len(results) >= max_speakers:
                break
            att = info.get("attitude") or "neutral"
            p = (PROACTIVE_CHANCE.get(att, 0.2)) * chance_scale
            if not force and random.random() > p:
                continue

            npc = CharacterRepository.get_by_name(info.get("name") or "")
            if not npc or npc.id == player.id:
                continue
            if npc.location != player.location:
                continue

            mind = ensure_mind(npc)
            personality = mind.get("personality") or ""
            ensure_bio(npc)
            att_cn = ATTITUDE_LABELS.get(att, "中立")

            opening = None
            source = "local"
            use_ai = ai_ready() and _consume_ai_budget()
            if use_ai:
                try:
                    from core.npc_personas import persona_prompt_block

                    persona_blk = persona_prompt_block(npc)
                except Exception:
                    persona_blk = ""
                data = None
                try:
                    from ai.router import invoke as ai_invoke

                    result = ai_invoke(
                        "npc_proactive",
                        payload={
                            "name": npc.name,
                            "realm": npc.realm.name,
                            "personality": personality,
                            "persona": persona_blk,
                            "player": player.name,
                            "att_cn": att_cn,
                            "location": npc.location,
                        },
                        actor_id=npc.id,
                    )
                    if result.get("ok"):
                        data = result.get("data")
                except Exception:
                    data = None
                if data and data.get("line"):
                    opening = {
                        "line": str(data["line"])[:200],
                        "delta": max(-5, min(5, int(data.get("delta") or 0))),
                    }
                    source = "ai"
                else:
                    log_event("GATE", "npc_proactive_ai_empty", npc=npc.name)
            elif ai_ready() and NPC_PROACTIVE_LOCAL_ONLY_AFTER:
                # 超预算：本地模板，记一笔
                log_event("GATE", "npc_proactive_budget_skip", npc=npc.name)
            if not opening:
                opening = _local_opening(npc, player, att, personality)

            if opening.get("delta"):
                att = shift_attitude(npc, player.id, opening["delta"], reason="主动搭话")
            else:
                att = attitude_toward(npc, player.id)

            eid = record_event(
                type="TALK",
                actor=npc,
                target=player,
                summary=f"{npc.name}主动搭话：{opening['line'][:40]}",
                location=npc.location,
            )
            write_audit({
                "ts": now, "actor": npc.id, "kind": "npc_proactive",
                "source": source, "event_id": eid,
            })

            results.append({
                "npc": npc.name,
                "personality": personality,
                "attitude": att.get("label", att),
                "attitude_cn": ATTITUDE_LABELS.get(att.get("label", att) if isinstance(att, dict) else att, att_cn),
                "line": opening["line"],
                "delta": opening.get("delta", 0),
                "source": source,
                "text": f"【{npc.name}·{personality}】{opening['line']}",
            })

        if results:
            NpcProactiveEngine._last[player.id] = now
        return results

    @staticmethod
    def reset_cooldown(player_id: str):
        NpcProactiveEngine._last.pop(player_id, None)
