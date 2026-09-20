"""
江湖因果账：世界事件唯一写入口与投影源。
规则结算后落账；AI 只可附带 narrative/ref_ids，不得单独建账。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from storage.db import JianghuEventRepository, ChronicleRepository

# 单轮 tick 公共事件预算
TICK_EVENT_BUDGET = 3
BUDGET_WINDOW_SECONDS = 60.0

_budget_state: Dict[str, Any] = {"day_key": None, "window_start": 0.0, "count": 0}


def _budget_ok(now: Optional[float] = None) -> bool:
    t = now or time.time()
    window_key = int(t // BUDGET_WINDOW_SECONDS)
    if _budget_state.get("window_key") != window_key:
        _budget_state["window_key"] = window_key
        _budget_state["count"] = 0
    return int(_budget_state.get("count") or 0) < TICK_EVENT_BUDGET


def _budget_consume() -> None:
    _budget_state["count"] = int(_budget_state.get("count") or 0) + 1


def reset_tick_budget() -> None:
    _budget_state["window_key"] = None
    _budget_state["count"] = 0


def new_event_id() -> str:
    return "ev_" + uuid.uuid4().hex[:12]


def append_event(
    *,
    kind: str,
    actor_ids: Optional[List[str]] = None,
    actor_names: Optional[List[str]] = None,
    target_ids: Optional[List[str]] = None,
    location: str = "",
    summary: str,
    rule_result: Optional[Dict[str, Any]] = None,
    narrative: str = "",
    ref_ids: Optional[List[str]] = None,
    visibility: str = "public",
    source: str = "rule",
    enforce_budget: bool = False,
    now: Optional[float] = None,
) -> Optional[str]:
    """
    写入一条江湖事件。返回 event_id；预算拒绝时返回 None。
    source=ai 时仅允许附加叙事，仍须规则侧调用本函数。
    """
    t = now or time.time()
    if enforce_budget and visibility == "public" and not _budget_ok(t):
        return None
    if enforce_budget and visibility == "public":
        _budget_consume()

    eid = new_event_id()
    actor_ids = [str(x) for x in (actor_ids or []) if x]
    target_ids = [str(x) for x in (target_ids or []) if x]
    ref_ids = [str(x) for x in (ref_ids or []) if x]
    # 引用一律进 known 扩展
    for x in actor_ids + target_ids:
        if x not in ref_ids:
            ref_ids.append(x)

    try:
        season_day = 0
        try:
            from core.season import season_day as _sd
            season_day = int(_sd())
        except Exception:
            season_day = 0
    except Exception:
        season_day = 0

    rec = {
        "id": eid,
        "kind": kind,
        "actor_ids": actor_ids,
        "actor_names": list(actor_names or []),
        "target_ids": target_ids,
        "location": location or "",
        "rule_result": dict(rule_result or {}),
        "narrative": (narrative or "")[:400],
        "summary": (summary or narrative or "")[:200],
        "ref_ids": ref_ids,
        "created_at": t,
        "season_day": season_day,
        "visibility": visibility,
        "source": source,
    }
    JianghuEventRepository.append(rec)

    # 同步角色长期记忆账（可选主当事人）
    try:
        from storage.db import EventLedgerRepository
        from core.memory import record_event  # noqa: F401  # keep import path stable

        main_actor = actor_ids[0] if actor_ids else ""
        main_name = (actor_names[0] if actor_names else "") or main_actor
        EventLedgerRepository.append(
            event_id=eid,
            ts=t,
            type=kind,
            actor_id=main_actor,
            actor_name=main_name,
            summary=rec["summary"],
            target_id=target_ids[0] if target_ids else None,
            location=location or None,
            effects_digest=str((rule_result or {}).get("digest", ""))[:120],
            refs=ref_ids[:8],
        )
    except Exception:
        pass

    # 世界大事记摘要（公开可见）
    if visibility == "public":
        try:
            ChronicleRepository.record(kind, (actor_names[0] if actor_names else "天道"), rec["summary"][:60])
        except Exception:
            pass

    return eid


def list_recent(limit: int = 20, since: Optional[float] = None, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    return JianghuEventRepository.list_recent(limit=limit, since=since, kind=kind)


def events_for_prompt(limit: int = 6) -> List[Dict[str, Any]]:
    """给 FactPack 用的结构化近账"""
    rows = JianghuEventRepository.list_recent(limit=limit)
    return rows


def project_related(character_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    return JianghuEventRepository.query_related(character_id, limit=limit)


def format_event_line(ev: Dict[str, Any]) -> str:
    kinds = {
        "npc_agenda": "议程",
        "collusion": "合谋",
        "kill": "斗法",
        "trade": "成交",
        "bounty": "悬赏",
        "sect": "宗门",
        "player_action": "玩家",
        "lan": "局域网",
        "flee": "遁走",
        "revenge": "复仇",
    }
    k = kinds.get(ev.get("kind", ""), ev.get("kind", ""))
    loc = ev.get("location") or ""
    return f"[{ev.get('id','')[-6:]}] {k}{'·' + loc if loc else ''}：{ev.get('summary') or ev.get('narrative') or ''}"


def format_brief(limit: int = 8) -> str:
    evs = list_recent(limit=limit)
    if not evs:
        return "近日江湖无事，青烟如常。"
    return "\n".join("  " + format_event_line(e) for e in evs)


def format_for_character(character_id: str, limit: int = 6) -> str:
    rel = project_related(character_id, limit=limit)
    if not rel:
        return "与你直接相关的江湖事，近日未见落账。"
    return "\n".join("  " + format_event_line(e) for e in rel)
