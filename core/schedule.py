"""
世情日程：可点可追
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.models import CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository

_ACTIONS_KEY = "last_schedule"


def _store_actions(user_id: str, actions: List[Dict[str, Any]]) -> None:
    try:
        d = WorldStateRepository.get(_ACTIONS_KEY) or {}
        d[user_id] = {"ts": time.time(), "actions": actions[:30]}
        # 裁剪
        if len(d) > 50:
            items = sorted(d.items(), key=lambda x: -float(x[1].get("ts") or 0))[:50]
            d = dict(items)
        WorldStateRepository.set(_ACTIONS_KEY, d)
    except Exception:
        pass


def _load_actions(user_id: str) -> List[Dict[str, Any]]:
    try:
        d = WorldStateRepository.get(_ACTIONS_KEY) or {}
        rec = d.get(user_id) or {}
        if time.time() - float(rec.get("ts") or 0) > 1800:
            return []
        return rec.get("actions") or []
    except Exception:
        return []


def format_world_schedule(viewer_id: str = "", simple: bool = False) -> Dict[str, Any]:
    from core.npc_agenda import NpcAgendaEngine, agenda_cn, _is_npc
    from core.hunt import is_marked
    from core.secret_realm import realm_status
    from core.world_channel import WorldChannel

    lines = ["【世情】输入 /追 <编号> 可跟进"]
    actions: List[Dict[str, Any]] = []

    if simple:
        try:
            majors = [
                m for m in WorldChannel.recent(limit=30) if m.level in ("major", "epic", "gm")
            ][-3:]
        except Exception:
            majors = []
        lines.append("近闻：")
        if majors:
            for m in majors:
                lines.append(f"· {m.text}")
        else:
            lines.append("  · 风平浪静")
        if viewer_id:
            _store_actions(viewer_id, [])
        return {"text": "\n".join(lines), "actions": actions}

    name_map = {}
    try:
        for c in CharacterRepository.list_all_alive():
            name_map[c.id] = c
    except Exception:
        pass

    # NPC
    try:
        agendas = NpcAgendaEngine.list_agendas()
    except Exception:
        agendas = []
    npc_rows = []
    n_i = 0
    for a in agendas[:40]:
        npc = name_map.get(a.get("npc_id"))
        if not npc or not _is_npc(npc) or npc.status == CharacterStatus.DEAD:
            continue
        n_i += 1
        label = a.get("agenda_cn") or agenda_cn(a.get("agenda_type"))
        npc_rows.append(f"{n_i}. {npc.name} · {label} · {npc.location}")
        actions.append({"kind": "npc", "name": npc.name, "loc": npc.location, "label": label})
        if len(npc_rows) >= 12:
            break
    lines.append(f"NPC 动向（{n_i}）：")
    lines.extend(npc_rows or ["  （暂无）"])

    # 血煞（B 编号）
    marked = []
    try:
        for c in CharacterRepository.list_all_alive():
            if c.status != CharacterStatus.DEAD and is_marked(c):
                marked.append(c)
    except Exception:
        marked = []
    marked.sort(key=lambda x: -x.karma.sin_value)
    lines.append(f"血煞/重业（{len(marked)}）：")
    if marked:
        for i, c in enumerate(marked[:8], 1):
            lines.append(f"B{i}. 【{c.name}】{c.realm.name} 业力{c.karma.sin_value} @ {c.location}")
            actions.append({"kind": "mark", "name": c.name, "loc": c.location, "label": "除凶"})
    else:
        lines.append("  · 天道清朗")

    # 秘境
    try:
        open_r = [r for r in realm_status() if r.get("is_open")]
    except Exception:
        open_r = []
    lines.append(f"秘境开启中（{len(open_r)}）：")
    if open_r:
        for i, r in enumerate(open_r[:6], 1):
            lines.append(f"S{i}. {r.get('name')} @ {r.get('location')}")
            actions.append({"kind": "realm", "name": r.get("name"), "loc": r.get("location"), "label": "秘境"})
    else:
        lines.append("  · 暂无")

    # 近闻
    try:
        majors = [
            m for m in WorldChannel.recent(limit=30) if m.level in ("major", "epic", "gm")
        ][-3:]
    except Exception:
        majors = []
    lines.append("近闻：")
    if majors:
        for m in majors:
            lines.append(f"· {m.text}")
    else:
        lines.append("  · 风平浪静")

    if viewer_id:
        _store_actions(viewer_id, actions)
    return {"text": "\n".join(lines), "actions": actions}


def follow_action(viewer, raw: str) -> Dict[str, Any]:
    """/追 <编号>：支持 3 或 B1 或 S1"""
    raw = (raw or "").strip().upper()
    if not raw:
        return {"success": False, "message": "用法：/追 <编号>，如 /追 1 或 /追 B1"}
    actions = _load_actions(viewer.id)
    kind = "npc"
    num = raw
    if raw.startswith("B"):
        kind = "mark"
        num = raw[1:]
    elif raw.startswith("S"):
        kind = "realm"
        num = raw[1:]
    elif raw.isdigit():
        kind = "npc"
    if not num.isdigit():
        return {"success": False, "message": "编号无效。"}
    idx = int(num) - 1
    bucket = [a for a in actions if a.get("kind") == kind]
    # NPC 用全局 actions 中 kind==npc 的顺序
    if kind == "npc":
        bucket = [a for a in actions if a.get("kind") == "npc"]
    if idx < 0 or idx >= len(bucket):
        return {"success": False, "message": "编号不存在，请先 /世情 刷新。"}
    act = bucket[idx]
    name = act.get("name") or ""
    loc = act.get("loc") or ""

    if kind == "mark":
        from core.hunt import accept, my_target

        if my_target(viewer):
            return {"success": False, "message": "你已有除凶令在身，先 /弃除凶。"}
        res = accept(viewer, name)
        return res

    if kind == "realm":
        if loc and viewer.location != loc:
            return {
                "success": False,
                "message": f"【{name}】入口在 {loc}，请 /go {loc} 后再 /秘境 {name}。",
            }
        return {
            "success": True,
            "message": f"已至秘境【{name}】附近，输入 /秘境 {name} 进入。",
        }

    # NPC
    if loc and viewer.location != loc:
        return {
            "success": False,
            "message": f"【{name}】在 {loc}，请 /go {loc} 后再 /交谈 {name}。",
        }
    return {
        "success": True,
        "message": f"【{name}】就在同场（{act.get('label') or ''}）。可 /交谈 {name}。",
    }
