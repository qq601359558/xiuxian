"""
坊间传闻池：规则写入、可被 NPC 复述；AI 宁少而准
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from storage.db import WorldStateRepository

_KEY = "rumor_pool"
_MAX = 40
_TTL_DAYS = 7.0


def _load() -> List[Dict[str, Any]]:
    try:
        data = WorldStateRepository.get(_KEY) or []
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def _save(pool: List[Dict[str, Any]]) -> None:
    try:
        WorldStateRepository.set(_KEY, pool)
    except Exception:
        pass


def _purge(pool: List[Dict[str, Any]], now: float) -> List[Dict[str, Any]]:
    cutoff = now - _TTL_DAYS * 86400.0
    out = [r for r in pool if float(r.get("created_at") or 0) >= cutoff]
    return out[-_MAX:]


def add_rumor(
    text: str,
    origin: str = "",
    tags: Optional[List[str]] = None,
    truth: float = 0.9,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    t = now if now is not None else time.time()
    pool = _purge(_load(), t)
    item = {
        "id": uuid.uuid4().hex[:6],
        "text": (text or "").strip()[:120],
        "origin": origin[:40],
        "tags": tags or [],
        "created_at": t,
        "truth": max(0.0, min(1.0, float(truth))),
        "heat": 1,
    }
    if not item["text"]:
        return item
    pool.append(item)
    _save(pool[-_MAX:])
    return item


def list_rumors(limit: int = 8, now: Optional[float] = None) -> List[Dict[str, Any]]:
    t = now if now is not None else time.time()
    pool = _purge(_load(), t)
    pool.sort(key=lambda r: (int(r.get("heat") or 0), float(r.get("created_at") or 0)), reverse=True)
    return pool[: max(1, min(30, limit))]


def format_rumor_board(limit: int = 8) -> str:
    rows = list_rumors(limit)
    if not rows:
        return "【坊间传闻】近日风平浪静，并无值得一听的闲话。"
    lines = ["【坊间传闻】道听途说，未必为真："]
    for i, r in enumerate(rows, 1):
        truth = float(r.get("truth") or 0.5)
        mark = "较可信" if truth >= 0.8 else "半真半假" if truth >= 0.5 else "多半是谣"
        lines.append(f"{i}. {r.get('text','')}（{mark}·{r.get('origin') or '无名'}）")
    return "\n".join(lines)


def pick_for_npc(n: int = 1, min_truth: float = 0.0) -> List[Dict[str, Any]]:
    """给 NPC 对话注入用：取热门，引用后 heat+1"""
    rows = [r for r in list_rumors(12) if float(r.get("truth") or 0) >= min_truth]
    if not rows:
        return []
    picked = rows[: max(1, n)]
    pool = _load()
    ids = {p["id"] for p in picked}
    for r in pool:
        if r.get("id") in ids:
            r["heat"] = int(r.get("heat") or 0) + 1
    _save(pool)
    return picked


def note_kill(killer: str, victim: str, location: str) -> None:
    add_rumor(
        f"据说【{killer}】在{location}斩了【{victim}】，血溅三尺。",
        origin=location,
        tags=["kill", killer, victim],
        truth=0.95,
    )


def note_trade(a: str, b: str, location: str, detail: str = "") -> None:
    add_rumor(
        f"坊市有人见【{a}】与【{b}】当面交割，{detail or '袖中灵石往来'}。",
        origin=location,
        tags=["trade", a, b],
        truth=0.85,
    )


def note_auction(winner: str, item: str, price: int) -> None:
    add_rumor(
        f"拍卖行落槌：【{item}】以 {price} 灵石归了【{winner}】，有人眼红。",
        origin="拍卖行",
        tags=["auction", winner, item],
        truth=0.9,
    )


def note_apocalypse(season_no: int) -> None:
    add_rumor(
        f"第 {season_no} 纪元天地大劫已至，未飞升者皆应劫转世。",
        origin="天道",
        tags=["apocalypse"],
        truth=1.0,
    )


def note_collusion(a: str, b: str, kind: str, location: str) -> None:
    flavor = {
        "密谈": f"有人见【{a}】与【{b}】在{location}角落密谈，不知谋划什么。",
        "寻仇未遂": f"【{a}】似在{location}寻【{b}】晦气，最终却各自散去。",
        "结伴而行": f"【{a}】与【{b}】在{location}结伴而行，神色亲近。",
        "分赃不均": f"风闻【{a}】与【{b}】因分赃在{location}不欢而散。",
    }.get(kind, f"【{a}】与【{b}】在{location}有所交集。")
    add_rumor(flavor, origin=location, tags=["npc", kind, a, b], truth=0.65)


_AMBIENT_DAY_KEY = "ambient_rumor_day"
_AMBIENT_MAX_PER_DAY = 5


def maybe_ambient_tick(chance: float = 0.15, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """零 AI 环境闲话：抽 content_pack 模板填地名/人名"""
    import random

    t = now if now is not None else time.time()
    if random.random() > max(0.0, min(1.0, chance)):
        return None
    day = time.strftime("%Y-%m-%d", time.localtime(t))
    try:
        rec = WorldStateRepository.get(_AMBIENT_DAY_KEY) or {}
        if rec.get("day") != day:
            rec = {"day": day, "n": 0}
        if int(rec.get("n") or 0) >= _AMBIENT_MAX_PER_DAY:
            return None
    except Exception:
        rec = {"day": day, "n": 0}

    from core.content_pack import AMBIENT_RUMORS
    from config import WORLD_LOCATIONS
    from storage.db import CharacterRepository

    if not AMBIENT_RUMORS:
        return None
    names = []
    try:
        names = [c.name for c in CharacterRepository.list_all_alive()[:30]]
    except Exception:
        names = []
    if len(names) < 2:
        names = ["某散修", "某道友", "某掌柜"]
    a, b = random.sample(names, 2)
    loc = random.choice(list(WORLD_LOCATIONS.keys()) or ["青云坊市客栈"])
    text = random.choice(AMBIENT_RUMORS).format(loc=loc, a=a, b=b)
    # AI 扭曲成更像闲话（可选）
    try:
        from core import ai_flavor

        if random.random() < 0.35:
            text = ai_flavor.twist_rumor(text) or text
    except Exception:
        pass
    item = add_rumor(text, origin=loc, tags=["ambient"], truth=random.uniform(0.5, 0.75), now=t)
    rec["n"] = int(rec.get("n") or 0) + 1
    try:
        WorldStateRepository.set(_AMBIENT_DAY_KEY, rec)
    except Exception:
        pass
    return item
