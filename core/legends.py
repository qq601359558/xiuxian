"""
纪元传说库：跨大劫存活的史笔条目
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config import LEGEND_MAX
from storage.db import WorldStateRepository

_KEY = "legends"


class Legend(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:6])
    season: int = 0
    title: str = ""
    text: str = ""
    tags: List[str] = Field(default_factory=list)
    actor: str = ""
    created_at: float = 0.0
    weight: int = 1


def _load() -> List[Dict[str, Any]]:
    try:
        data = WorldStateRepository.get(_KEY) or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(pool: List[Dict[str, Any]]) -> None:
    try:
        WorldStateRepository.set(_KEY, pool[-LEGEND_MAX:])
    except Exception:
        pass


def add_legend(
    title: str,
    text: str,
    season: int = 0,
    tags: Optional[List[str]] = None,
    actor: str = "",
    weight: int = 1,
    now: Optional[float] = None,
) -> Legend:
    t = now if now is not None else time.time()
    item = Legend(
        season=int(season or 0),
        title=(title or "")[:40],
        text=(text or "")[:120],
        tags=tags or [],
        actor=actor[:40],
        created_at=t,
        weight=max(1, int(weight)),
    )
    pool = _load()
    pool.append(item.model_dump())
    _save(pool)
    return item


def list_legends(season: Optional[int] = None, limit: int = 15) -> List[Legend]:
    pool = _load()
    if season is not None:
        pool = [x for x in pool if int(x.get("season") or 0) == int(season)]
    pool.sort(key=lambda x: (int(x.get("weight") or 0), float(x.get("created_at") or 0)), reverse=True)
    out = []
    for x in pool[: max(1, min(40, limit))]:
        try:
            out.append(Legend.model_validate(x))
        except Exception:
            continue
    return out


def format_legends(season: Optional[int] = None, limit: int = 12) -> str:
    rows = list_legends(season=season, limit=limit)
    head = f"第 {season} 纪元" if season is not None else "近纪"
    if not rows:
        return f"【传说】{head}暂无史笔。大劫之后自有记载。"
    lines = [f"【传说 · {head}】"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r.text}（第{r.season}纪）")
    return "\n".join(lines)


def pick_for_npc_prompt(limit: int = 1) -> str:
    """给 NPC 对话注入一行史载；引用不升 weight（省写）"""
    rows = list_legends(limit=max(1, limit))
    if not rows:
        return ""
    return "；".join(r.text for r in rows[:limit])


def write_apocalypse_legends(season_no: int, now: Optional[float] = None) -> List[Legend]:
    """大劫结算时写总述 + 高光人物"""
    t = now if now is not None else time.time()
    written: List[Legend] = []
    try:
        from storage.db import CharacterRepository
        from core.models import CharacterStatus

        alive = [c for c in CharacterRepository.list_all_alive() if c.status != CharacterStatus.DEAD]
        top = sorted(alive, key=lambda c: (-c.realm.tier, -c.karma.sin_value))[:3]
        top_s = "、".join(f"{c.name}·{c.realm.name}" for c in top) or "无人"
        written.append(
            add_legend(
                title=f"第{season_no}纪元终",
                text=f"第{season_no}纪元天地大劫已至，未飞升者应劫转世；尚在者：{top_s}。",
                season=season_no,
                tags=["apocalypse"],
                actor="天道",
                weight=5,
                now=t,
            )
        )
        for c in top[:2]:
            if c.realm.tier >= 3:
                written.append(
                    add_legend(
                        title=f"{c.name}高光",
                        text=f"【{c.name}】于第{season_no}纪元臻 {c.realm.name}，名动一方。",
                        season=season_no,
                        tags=["player", "highlight"],
                        actor=c.name,
                        weight=3,
                        now=t,
                    )
                )
    except Exception:
        pass
    return written
