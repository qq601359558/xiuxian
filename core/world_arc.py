"""
M2 世界弧：预兆 → 升级 → 决算

- 导师指令可「升格」为世界弧（不是单发播报）
- 阶段由墙钟与导师 tick 推进；决算写传说/大事记
- 世界修饰由活跃弧与导师指令共同推导（规则消费，AI 不改胜负数）
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from config import (
    DIRECTIVE_TO_ARC,
    SEASON_WARN_DAYS,
    SECRET_REALMS,
    WORLD_ARC_ESCALATE_SEC,
    WORLD_ARC_MAX_ACTIVE,
    WORLD_ARC_PROPHESY_SEC,
    WORLD_ARC_TYPES,
    WORLD_LOCATIONS,
)
from storage.db import ChronicleRepository, WorldStateRepository
from core.world_channel import WorldChannel

_KEY = "world_arcs"

STAGES = ("prophesy", "escalate", "climax")
STAGE_CN = {"prophesy": "预兆", "escalate": "升级", "climax": "决算"}


def _now(now: Optional[float] = None) -> float:
    return now if now is not None else time.time()


def _load() -> Dict[str, Any]:
    try:
        data = WorldStateRepository.get(_KEY) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("arcs", [])
    data.setdefault("history", [])
    data.setdefault("stats", {"spawned": 0, "advanced": 0, "climaxed": 0})
    if not isinstance(data.get("stats"), dict):
        data["stats"] = {"spawned": 0, "advanced": 0, "climaxed": 0}
    return data


def _save(state: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, state)
    except Exception:
        pass


def _push_hist(state: Dict[str, Any], line: str, limit: int = 30) -> None:
    h = list(state.get("history") or [])
    h.append(line[:140])
    state["history"] = h[-limit:]


def _season_no() -> int:
    try:
        from core.season import season_info

        return int(season_info().get("season_number") or 0)
    except Exception:
        return 0


def _stage_duration(stage: str) -> float:
    # 运行时读 config，便于测试/部署调窗
    import config as cfg

    if stage == "prophesy":
        return float(getattr(cfg, "WORLD_ARC_PROPHESY_SEC", WORLD_ARC_PROPHESY_SEC))
    if stage == "escalate":
        return float(getattr(cfg, "WORLD_ARC_ESCALATE_SEC", WORLD_ARC_ESCALATE_SEC))
    return 0.0


def _next_stage(stage: str) -> Optional[str]:
    try:
        i = STAGES.index(stage)
    except ValueError:
        return None
    return STAGES[i + 1] if i + 1 < len(STAGES) else None


def _post(text: str, level: str, location: str = "", kind: str = "arc") -> None:
    try:
        WorldChannel.post(
            kind,
            text[:160],
            level=level,
            actor="world_arc",
            location=location or "",
            skip_limit=True,
        )
    except Exception:
        pass


def _chronicle(actor: str, text: str) -> None:
    try:
        ChronicleRepository.record("天道弧", actor, text[:200])
    except Exception:
        pass


def _clamp_loc(loc: str) -> str:
    loc = (loc or "").strip()[:40]
    if loc and loc not in WORLD_LOCATIONS and loc not in SECRET_REALMS:
        return ""
    return loc


def spawn_from_directive(
    directive: Dict[str, Any],
    *,
    now: Optional[float] = None,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """导师指令升格为世界弧；同 kind+location 已有活跃弧则跳过"""
    if not isinstance(directive, dict):
        return None
    dtype = str(directive.get("type") or "")
    kind = DIRECTIVE_TO_ARC.get(dtype)
    if not kind or kind not in WORLD_ARC_TYPES:
        return None
    t = _now(now)
    state = _load()
    prune_arcs(state, t)
    loc = _clamp_loc(str(directive.get("location") or "") or str((directive.get("effects") or {}).get("location") or ""))
    effects = dict(directive.get("effects") or {})
    if not force:
        for a in state.get("arcs") or []:
            if a.get("kind") == kind and (a.get("location") or "") == loc and a.get("status") == "active":
                return None
        if len(state.get("arcs") or []) >= WORLD_ARC_MAX_ACTIVE:
            return None
    title = str(directive.get("title") or "天道异动")[:40]
    narrative = str(directive.get("narrative") or "")[:160]
    arc_id = f"a_{uuid.uuid4().hex[:8]}"
    arc = {
        "id": arc_id,
        "kind": kind,
        "source_directive": str(directive.get("id") or ""),
        "title": title,
        "location": loc,
        "stage": "prophesy",
        "status": "active",
        "season": _season_no(),
        "created_at": t,
        "updated_at": t,
        "stage_deadline": t + _stage_duration("prophesy"),
        "prophesy_text": narrative,
        "escalate_text": "",
        "climax_text": "",
        "effects": {
            "realm_id": str(effects.get("realm_id") or ""),
            "sect_a": str(effects.get("sect_a") or ""),
            "sect_b": str(effects.get("sect_b") or ""),
            "whisper": str(effects.get("whisper") or ""),
        },
        "flags": [],
        "log": [f"预兆：{title}"],
    }
    # 预兆落账
    _post(f"【世界弧·预兆】{title}：{narrative}" + (f" @{loc}" if loc else ""), "major", loc)
    _chronicle("预兆", f"{title}（{kind}）" + (f"@{loc}" if loc else ""))
    # 可拒机缘
    try:
        from core.goals import GoalEngine
        from core.models import CharacterStatus
        from storage.db import CharacterRepository

        for c in CharacterRepository.list_all_alive():
            uid = str(getattr(c, "user_id", "") or "")
            if uid.startswith("npc_") or uid.startswith("ai_npc_"):
                continue
            if c.status == CharacterStatus.DEAD:
                continue
            GoalEngine.add_opportunity(
                c,
                f"世弧·{title}",
                f"世间异动：{narrative}" + (f"（可前往 {loc}）" if loc else ""),
            )
            CharacterRepository.save(c)
            break  # 预兆只提示一人即可，决算再广播
    except Exception:
        pass
    state.setdefault("arcs", []).append(arc)
    state["stats"]["spawned"] = int(state["stats"].get("spawned") or 0) + 1
    _push_hist(state, f"{int(t)}|spawn|{kind}|{title}|{arc_id}")
    _save(state)
    return arc


def prune_arcs(state: Dict[str, Any], now: float) -> None:
    """到期未推进的弧强制决算；已完成弧移出 active"""
    keep = []
    max_age = _stage_duration("prophesy") + _stage_duration("escalate") + 300.0
    for a in state.get("arcs") or []:
        if not isinstance(a, dict) or a.get("status") != "active":
            continue
        created = float(a.get("created_at") or now)
        deadline = float(a.get("stage_deadline") or 0)
        overdue = (deadline > 0 and now > deadline + max_age) or (now - created > max_age + 60)
        if overdue:
            settled = _settle_climax(a, now=now, reason="超时决算，异象自散")
            if settled:
                state["stats"]["climaxed"] = int(state["stats"].get("climaxed") or 0) + 1
                _push_hist(
                    state,
                    f"{int(now)}|climax_timeout|{a.get('kind')}|{a.get('title')}|{a.get('id')}",
                )
            continue
        keep.append(a)
    state["arcs"] = keep


def active_arcs(now: Optional[float] = None) -> List[Dict[str, Any]]:
    t = _now(now)
    state = _load()
    prune_arcs(state, t)
    _save(state)
    return [a for a in state.get("arcs") or [] if a.get("status") == "active"]


def arc_modifiers(now: Optional[float] = None) -> Dict[str, Any]:
    """活跃弧贡献的世界修饰（与 director.world_modifiers 叠加）"""
    arcs = active_arcs(now)
    heat_locs: Dict[str, float] = {}
    blood_locs: List[str] = []
    sects: List[Tuple[str, str]] = []
    realms: List[str] = []
    calamity = False
    hunt_heat = 1.0
    for a in arcs:
        stage = a.get("stage")
        loc = a.get("location") or ""
        kind = a.get("kind")
        boost = 1.2 if stage == "prophesy" else (1.45 if stage == "escalate" else 1.3)
        if loc:
            heat_locs[loc] = max(heat_locs.get(loc, 1.0), boost)
        if kind == "blood_feud":
            hunt_heat = max(hunt_heat, 1.25 if stage == "prophesy" else 1.5)
            if loc:
                blood_locs.append(loc)
        elif kind == "sect_crisis":
            sa = (a.get("effects") or {}).get("sect_a") or ""
            sb = (a.get("effects") or {}).get("sect_b") or ""
            if sa and sb:
                sects.append((sa, sb))
        elif kind == "realm_storm":
            rid = (a.get("effects") or {}).get("realm_id") or ""
            if rid:
                realms.append(rid)
        elif kind == "calamity_arc":
            calamity = True
            hunt_heat = max(hunt_heat, 1.2)
    return {
        "heat_by_location": heat_locs,
        "blood_tide_locations": blood_locs,
        "sect_tensions": sects,
        "realm_pressure_ids": realms,
        "calamity_forecast": calamity,
        "hunt_heat": hunt_heat,
        "active_arc_kinds": [a.get("kind") for a in arcs],
        "n_arcs": len(arcs),
    }


def advance_arc(
    arc_id: str,
    *,
    now: Optional[float] = None,
    force: bool = False,
    narrative_hint: str = "",
) -> Dict[str, Any]:
    """推进一格：prophesy→escalate→climax。force=导师/指令强制"""
    t = _now(now)
    state = _load()
    prune_arcs(state, t)
    target = None
    for a in state.get("arcs") or []:
        if a.get("id") == arc_id and a.get("status") == "active":
            target = a
            break
    if not target:
        return {"ok": False, "error": "弧不存在或已结束"}
    deadline = float(target.get("stage_deadline") or 0)
    if not force and deadline > 0 and t < deadline:
        return {
            "ok": False,
            "skipped": "not_due",
            "message": f"【{target.get('title')}】尚未至下一阶段",
        }
    stage = target.get("stage")
    nxt = _next_stage(stage)
    if not nxt:
        return {"ok": False, "error": "已是终局"}
    loc = target.get("location") or ""
    title = target.get("title") or "天道异动"
    kind = target.get("kind")
    if nxt == "escalate":
        text = narrative_hint or _escalate_text(kind, title, loc, target)
        target["stage"] = "escalate"
        target["escalate_text"] = text
        target["stage_deadline"] = t + _stage_duration("escalate")
        target["updated_at"] = t
        target["log"].append(f"升级：{text[:40]}")
        # 升级：秘境潮强制开启；血煞加强
        if kind == "realm_storm":
            rid = (target.get("effects") or {}).get("realm_id") or ""
            if rid:
                try:
                    from core.secret_realm import director_force_open

                    if director_force_open(rid, now=t):
                        target["flags"].append(f"realm_open:{rid}")
                except Exception:
                    pass
        if kind == "blood_feud" and loc:
            target["flags"].append(f"heat:{loc}")
        _post(f"【世界弧·升级】{title}：{text}" + (f" @{loc}" if loc else ""), "major", loc)
        _chronicle("升级", f"{title}：{text[:80]}")
        state["stats"]["advanced"] = int(state["stats"].get("advanced") or 0) + 1
        _push_hist(state, f"{int(t)}|escalate|{kind}|{title}|{arc_id}")
        _save(state)
        return {"ok": True, "stage": "escalate", "arc": target, "text": text}
    # climax
    settled = _settle_climax(target, now=t, reason=narrative_hint or "成熟")
    if settled:
        # 从 active 移除
        state["arcs"] = [a for a in state.get("arcs") or [] if a.get("id") != arc_id]
        state["stats"]["climaxed"] = int(state["stats"].get("climaxed") or 0) + 1
        _push_hist(state, f"{int(t)}|climax|{kind}|{title}|{arc_id}")
        _save(state)
        return {"ok": True, "stage": "climax", "arc": settled, "text": settled.get("climax_text")}
    return {"ok": False, "error": "决算失败"}


def _escalate_text(kind: str, title: str, loc: str, arc: Dict[str, Any]) -> str:
    eff = arc.get("effects") or {}
    if kind == "blood_feud":
        return f"血气在{loc or '各处'}凝而不散，除凶与寻仇者皆被牵引，杀劫渐近。"
    if kind == "realm_storm":
        rid = eff.get("realm_id") or "秘境"
        return f"【{rid}】禁制剧烈波动，灵机与凶险同时外泄，入口附近人影渐多。"
    if kind == "sect_crisis":
        return f"【{eff.get('sect_a')}】与【{eff.get('sect_b')}】门下气氛剑拔弩张，坊间已有龃龉传闻。"
    if kind == "calamity_arc":
        return "天象愈发晦暗，大劫阴影压向此界，闭关与夺宝之议皆染焦躁。"
    return f"【{title}】异象扩大，世间修士皆有所感。"


def _settle_climax(arc: Dict[str, Any], *, now: Optional[float], reason: str = "") -> Optional[Dict[str, Any]]:
    t = _now(now)
    kind = arc.get("kind")
    title = arc.get("title") or "天道异动"
    loc = arc.get("location") or ""
    eff = arc.get("effects") or {}
    climax = reason if reason and len(reason) > 8 else ""
    if not climax:
        climax = _climax_text(kind, title, loc, eff)
    arc["stage"] = "climax"
    arc["status"] = "done"
    arc["climax_text"] = climax
    arc["updated_at"] = t
    arc["stage_deadline"] = 0
    arc["log"].append(f"决算：{climax[:40]}")
    level = "epic" if kind == "calamity_arc" else "major"
    _post(f"【世界弧·决算】{title}：{climax}" + (f" @{loc}" if loc else ""), level, loc)
    _chronicle("决算", f"{title}：{climax[:100]}")
    # 传说回流
    try:
        from core.legends import add_legend
        from core.season import season_info

        season = int(season_info(t).get("season_number") or 0)
        add_legend(
            title=title,
            text=f"{climax[:100]}",
            season=season,
            tags=["world_arc", kind],
            actor="天道",
            weight=3 if kind == "calamity_arc" else 2,
            now=t,
        )
    except Exception:
        pass
    return arc


def _climax_text(kind: str, title: str, loc: str, eff: Dict[str, Any]) -> str:
    if kind == "blood_feud":
        return f"{loc or '野外'}血煞潮暂歇，坊间清点伤亡，除凶榜名次或有更迭。"
    if kind == "realm_storm":
        rid = eff.get("realm_id") or "秘境"
        return f"【{rid}】风暴过后，机缘与尸骨并存，史笔记下此役。"
    if kind == "sect_crisis":
        return (
            f"【{eff.get('sect_a') or '甲宗'}】与【{eff.get('sect_b') or '乙宗'}】"
            "对峙暂告段落，表面平复，暗流仍在。"
        )
    if kind == "calamity_arc":
        return "大劫预兆如潮水退去一寸，然天道无常，纪元之末终须一决。"
    return f"【{title}】异象散去，世间重归短暂平静。"


def tick_world(*, now: Optional[float] = None, max_advance: int = 3) -> List[Dict[str, Any]]:
    """世界 tick：到期弧自动推进"""
    t = _now(now)
    state = _load()
    prune_arcs(state, t)
    _save(state)
    acted = []
    for a in list(state.get("arcs") or []):
        if a.get("status") != "active":
            continue
        if len(acted) >= max_advance:
            break
        deadline = float(a.get("stage_deadline") or 0)
        if deadline > 0 and t >= deadline:
            res = advance_arc(a["id"], now=t, force=True)
            if res.get("ok"):
                acted.append(res)
    return acted


def agenda_bias_from_arcs(npc: Any, now: Optional[float] = None) -> Optional[Dict[str, str]]:
    """世界弧对 NPC 议程的偏置（与导演指令偏置兼容，本函数可单独测）"""
    if npc is None:
        return None
    loc = getattr(npc, "location", "") or ""
    sect = getattr(npc, "sect", "") or ""
    for a in active_arcs(now):
        stage = a.get("stage")
        if a.get("status") != "active":
            continue
        if a.get("kind") == "blood_feud" and loc and a.get("location") == loc:
            return {
                "agenda_type": "patrol" if stage == "prophesy" else "revenge",
                "note": f"世界弧·{STAGE_CN.get(stage, stage)}：{a.get('title')}",
            }
        if a.get("kind") == "sect_crisis":
            sa = (a.get("effects") or {}).get("sect_a") or ""
            sb = (a.get("effects") or {}).get("sect_b") or ""
            if sect and sect in (sa, sb):
                return {
                    "agenda_type": "patrol" if stage == "prophesy" else "social",
                    "note": f"世界弧·宗门危机：{a.get('title')}",
                }
        if a.get("kind") == "calamity_arc" and stage == "escalate":
            return {"agenda_type": "survive", "note": f"世界弧·大劫阴影：{a.get('title')}"}
        if a.get("kind") == "realm_storm" and loc and a.get("location") == loc:
            return {"agenda_type": "treasure", "note": f"世界弧·秘境风暴：{a.get('title')}"}
    return None


def format_arc_board(now: Optional[float] = None) -> str:
    t = _now(now)
    arcs = active_arcs(t)
    state = _load()
    lines = ["【世界弧】预兆 → 升级 → 决算（AI/导师驱动 · 规则落账）"]
    st = state.get("stats") or {}
    lines.append(
        f"累计：起弧 {st.get('spawned', 0)} · 升级 {st.get('advanced', 0)} · 决算 {st.get('climaxed', 0)}"
    )
    if not arcs:
        lines.append("  · 世间暂无进行中的世界弧")
    for i, a in enumerate(arcs[:6], 1):
        stage = a.get("stage")
        loc = f" @{a.get('location')}" if a.get("location") else ""
        left = max(0, int(float(a.get("stage_deadline") or 0) - t))
        lines.append(
            f"  {i}. [{STAGE_CN.get(stage, stage)}] {a.get('kind')} · {a.get('title')}{loc} · 下阶段约 {left}s"
        )
        last = (a.get("log") or [""])[-1]
        if last:
            lines.append(f"     {last}")
    hist = list(state.get("history") or [])[-4:]
    if hist:
        lines.append("近史：")
        for h in reversed(hist):
            lines.append(f"  · {h}")
    mods = arc_modifiers(t)
    if mods.get("n_arcs"):
        lines.append(
            f"弧修饰：热度地={list(mods.get('heat_by_location') or {})} · 除凶热度×{mods.get('hunt_heat', 1.0):.2f}"
        )
    return "\n".join(lines)


def handle_arc_command(parts: List[str], *, now: Optional[float] = None) -> Dict[str, Any]:
    """ /世界弧 | /弧 [推进 <id>] """
    t = _now(now)
    sub = (parts[1].strip() if len(parts) > 1 else "").lower()
    if sub in ("推进", "advance", "进") and len(parts) >= 3:
        arc_id = parts[2].strip()
        res = advance_arc(arc_id, now=t, force=True)
        return {
            "ok": res.get("ok", False),
            "text": (res.get("text") or res.get("message") or res.get("error") or "")
            + "\n\n"
            + format_arc_board(t),
            "arc": res,
        }
    return {"ok": True, "text": format_arc_board(t)}


def absorb_director_cycle(
    directives: List[Dict[str, Any]],
    *,
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """导师本轮落账指令 → 尝试起弧"""
    spawned = []
    for d in directives or []:
        arc = spawn_from_directive(d, now=now)
        if arc:
            spawned.append(arc)
    return spawned
