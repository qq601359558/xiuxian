"""
登录/近况摘要：世间在发生什么 + 与你何干 + 世间目标。
"""
from __future__ import annotations

from typing import Any, Dict

from core.models import Character, CharacterStatus


def briefing(character: Character, *, world_limit: int = 6, me_limit: int = 4) -> Dict[str, Any]:
    import core.jianghu as jianghu
    from core.goals import GoalEngine

    world = jianghu.list_recent(limit=world_limit)
    mine = jianghu.project_related(character.id, limit=me_limit)
    GoalEngine.sync_progress(character)
    goals = GoalEngine.list_for(character)
    active = [g for g in goals if g.get("status") == "active"]
    dead = character.status == CharacterStatus.DEAD or character.lifespan.is_dead()

    world_lines = [jianghu.format_event_line(e) for e in world]
    me_lines = [jianghu.format_event_line(e) for e in mine]
    return {
        "ok": True,
        "dead": dead,
        "location": character.location,
        "world": world_lines,
        "related": me_lines,
        "goals": active,
        "text": format_briefing_text(character, world_lines, me_lines, active, dead),
    }


def format_briefing_text(character, world_lines, me_lines, goals, dead=False) -> str:
    from core.goals import KINDS

    parts = []
    parts.append(f"=== 近况 · {character.name} @ {character.location} ===")
    if dead:
        parts.append("（此身已道消，可转世再入红尘）")
    parts.append("【世间】")
    parts.append("\n".join("  " + (ln or "") for ln in world_lines) if world_lines else "  江湖无事。")
    parts.append("【与你何干】")
    parts.append("\n".join("  " + (ln or "") for ln in me_lines) if me_lines else "  近日暂无与你直接相关的落账。")
    parts.append("【世间目标】")
    if goals:
        for g in goals:
            key = g.get("source") or g.get("type") or ""
            kn = KINDS.get(key, key)
            parts.append(f"  · 【{kn}】{g.get('title')} — {g.get('detail','')}")
    else:
        parts.append("  暂无。")
    return "\n".join(parts)


def format_cli(character: Character) -> str:
    b = briefing(character)
    return b.get("text") or "（无法生成近况）"
