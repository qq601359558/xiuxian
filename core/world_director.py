"""
天道导演 M1：AI 提案世界级走向，规则门禁落账。

原则：
  - AI 决定「世界发生什么类型的事」
  - 数值/胜负/掉落仍由规则权威；提案 effects 过白名单
  - 无 AI 不伪造「天道已裁」
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from config import (
    DIRECTOR_GOAL_FANOUT,
    DIRECTOR_MAX_ACTIVE,
    DIRECTOR_MIN_INTERVAL_SECONDS,
    DIRECTOR_STRIP_EFFECT_KEYS,
    DIRECTOR_TICK_INTERVAL_SECONDS,
    DIRECTOR_TTL_SECONDS,
    DIRECTOR_TYPES,
    SECRET_REALMS,
    SEASON_WARN_DAYS,
    WORLD_LOCATIONS,
    local_ai_allowed,
)
from storage.db import CharacterRepository, WorldStateRepository
from core.models import CharacterStatus
from core.season import season_info
from core.world_channel import WorldChannel
from ai.audit import write_audit
from ai.gateway import ai_block_reason, ai_ready

_KEY = "director"


def _now(now: Optional[float] = None) -> float:
    return now if now is not None else time.time()


def _load() -> Dict[str, Any]:
    try:
        data = WorldStateRepository.get(_KEY) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("last_run_ts", 0.0)
    data.setdefault("last_trigger", "")
    data.setdefault("last_source", "")
    data.setdefault("last_error", "")
    data.setdefault("last_accepted", 0)
    data.setdefault("active", [])
    data.setdefault("history", [])
    data.setdefault("player_events", [])
    data.setdefault("stats", {"runs": 0, "accepted": 0, "rejected": 0, "attempts": 0})
    if not isinstance(data.get("stats"), dict):
        data["stats"] = {"runs": 0, "accepted": 0, "rejected": 0, "attempts": 0}
    data["stats"].setdefault("attempts", 0)
    return data


def _save(state: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, state)
    except Exception:
        pass


def _audit(rec: Dict[str, Any]) -> None:
    try:
        write_audit({"source": "ai.world_director", **rec})
    except Exception:
        pass


def _prune_active(state: Dict[str, Any], now: float) -> None:
    active = []
    expired = []
    for d in state.get("active") or []:
        if not isinstance(d, dict):
            continue
        if float(d.get("expires_at") or 0) >= now:
            active.append(d)
        else:
            expired.append(d)
    if expired:
        for d in expired:
            _push_history(
                state,
                f"{int(now)}|{d.get('type')}|{d.get('title')}|expired|{d.get('id')}",
            )
            # 大事记：导演态势消散，供后续世情/传说引用
            try:
                from storage.db import ChronicleRepository

                ChronicleRepository.record(
                    "天道",
                    "导演",
                    f"【{d.get('title')}】态势渐散（{d.get('type')}）。",
                )
            except Exception:
                pass
        state["active"] = active
        # 读路径 prune 也要落库，否则 history/active 丢失
        try:
            WorldStateRepository.set(_KEY, state)
        except Exception:
            pass
    else:
        state["active"] = active


def _push_history(state: Dict[str, Any], line: str, limit: int = 20) -> None:
    hist = list(state.get("history") or [])
    hist.append(line[:120])
    state["history"] = hist[-limit:]


def gather_world_brief(now: Optional[float] = None) -> Dict[str, Any]:
    """导演事实简报（给 AI / 本地降级共用）"""
    t = _now(now)
    alive_players: List[str] = []
    alive_npcs: List[str] = []
    blood: List[str] = []
    realm_hist: Dict[str, int] = {}
    try:
        for c in CharacterRepository.list_all_alive():
            if c.status == CharacterStatus.DEAD:
                continue
            uid = str(getattr(c, "user_id", "") or "")
            realm_hist[c.realm.name] = realm_hist.get(c.realm.name, 0) + 1
            if c.karma.is_blood_marked() or c.karma.sin_value >= 100:
                blood.append(f"{c.name}({c.realm.name}@{c.location}业力{c.karma.sin_value})")
            if uid.startswith("npc_") or uid.startswith("ai_npc_"):
                alive_npcs.append(c.name)
            else:
                alive_players.append(c.name)
    except Exception:
        pass
    realms = []
    try:
        from core.secret_realm import realm_status

        for r in realm_status(t):
            realms.append(
                f"{r.get('name')}@{r.get('location')} {'开启' if r.get('is_open') else '未开'}"
            )
    except Exception:
        realms = [f"{rid}" for rid in list(SECRET_REALMS.keys())[:6]]
    rumors: List[str] = []
    try:
        from core import rumors as rum

        for r in rum.list_rumors(limit=5) if hasattr(rum, "list_rumors") else []:
            text = r.get("text") if isinstance(r, dict) else str(r)
            if text:
                rumors.append(str(text)[:60])
    except Exception:
        rumors = []
    if not rumors:
        try:
            majors = [
                m.text
                for m in WorldChannel.recent(limit=8)
                if getattr(m, "level", "") in ("major", "epic", "gm")
            ][-4:]
            rumors = majors
        except Exception:
            rumors = []
    info = season_info(t)
    locs = list(WORLD_LOCATIONS.keys())
    brief_text = (
        f"存活玩家{len(alive_players)}人：{'、'.join(alive_players[:8]) or '无'}；"
        f"NPC{len(alive_npcs)}人。\n"
        f"境界分布：{realm_hist or '—'}\n"
        f"血煞/重业：{'；'.join(blood[:6]) or '无'}\n"
        f"秘境：{'；'.join(realms[:6]) or '—'}\n"
        f"近闻：{'；'.join(rumors) or '风平浪静'}\n"
        f"地点库：{'、'.join(locs[:10])}\n"
        f"秘境库：{'、'.join(list(SECRET_REALMS.keys()))}\n"
        f"纪元第 {info.get('season_number')} 天；剩余约 {info.get('remain_real_days')} 天；"
        f"大劫窗口={'是' if info.get('is_final_week') else '否'}"
    )
    return {
        "text": brief_text,
        "players": alive_players,
        "npcs": alive_npcs,
        "blood": blood,
        "realms": realms,
        "rumors": rumors,
        "season": info,
        "locations": locs,
        "secret_realms": list(SECRET_REALMS.keys()),
    }


def _strip_effects(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        key = str(k)
        if key in DIRECTOR_STRIP_EFFECT_KEYS:
            continue
        if key in (
            "goal_title",
            "goal_detail",
            "whisper",
            "realm_id",
            "location",
            "sect_a",
            "sect_b",
        ):
            out[key] = str(v)[:80] if v is not None else ""
        elif key == "force_open":
            out[key] = bool(v)
        else:
            # 未知键：剥离（宁少勿滥）
            continue
    return out


def admit_directive(
    raw: Any,
    *,
    season: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """规则门禁：返回 (ok, reason, cleaned|None)"""
    if not isinstance(raw, dict):
        return False, "not_object", None
    dtype = str(raw.get("type") or "").strip().lower()
    if dtype not in DIRECTOR_TYPES:
        return False, f"illegal_type:{dtype}", None
    if dtype == "calamity_forecast":
        info = season if season is not None else season_info(_now(now))
        in_window = bool(info.get("is_final_week")) or float(
            info.get("remain_real_days") or 0
        ) <= float(SEASON_WARN_DAYS)
        if not in_window:
            return False, "calamity_out_of_window", None
    title = str(raw.get("title") or "").strip()[:40] or "天道有感"
    narrative = str(raw.get("narrative") or "").strip()[:160]
    if not narrative:
        return False, "empty_narrative", None
    location = str(raw.get("location") or "").strip()[:40]
    if location and location not in WORLD_LOCATIONS and location not in SECRET_REALMS:
        location = ""
    effects = _strip_effects(raw.get("effects"))
    if dtype == "secret_realm_pressure":
        rid = str(effects.get("realm_id") or raw.get("realm_id") or "").strip()
        if not rid:
            # 尝试从 narrative/location 模糊匹配简报秘境
            for name in SECRET_REALMS:
                if name in narrative or name in location:
                    rid = name
                    break
        if rid not in SECRET_REALMS:
            return False, "unknown_realm", None
        effects["realm_id"] = rid
        if location not in WORLD_LOCATIONS:
            location = str(SECRET_REALMS.get(rid, {}).get("location") or location or "")
    if dtype == "sect_tension":
        sa = str(effects.get("sect_a") or "").strip()[:20]
        sb = str(effects.get("sect_b") or "").strip()[:20]
        if not sa or not sb:
            return False, "sect_pair_required", None
        effects["sect_a"] = sa
        effects["sect_b"] = sb
    if dtype == "blood_tide":
        loc = str(effects.get("location") or location or "").strip()
        if loc and loc not in WORLD_LOCATIONS:
            loc = ""
        effects["location"] = loc
        location = loc or location
    try:
        priority = int(raw.get("priority") or 1)
    except (TypeError, ValueError):
        priority = 1
    duration = raw.get("duration_sec")
    try:
        duration = float(duration) if duration is not None else DIRECTOR_TTL_SECONDS
    except (TypeError, ValueError):
        duration = DIRECTOR_TTL_SECONDS
    duration = max(300.0, min(float(DIRECTOR_TTL_SECONDS) * 3, float(duration)))
    t = _now(now)
    level = "epic" if dtype == "calamity_forecast" else "major"
    cleaned = {
        "id": f"d_{uuid.uuid4().hex[:8]}",
        "type": dtype,
        "title": title,
        "narrative": narrative,
        "location": location,
        "priority": max(1, min(5, priority)),
        "duration_sec": duration,
        "effects": effects,
        "created_at": t,
        "expires_at": t + duration,
        "channel_level": level,
        "applied": {},
    }
    return True, "", cleaned


def _local_directives(brief: Dict[str, Any], now: float) -> List[Dict[str, Any]]:
    """无真 AI 时的确定性降级（source=local，不冒充天道裁决）"""
    info = brief.get("season") or {}
    raw_list: List[Dict[str, Any]] = []
    open_realms = [r for r in (brief.get("realms") or []) if "开启" in str(r)]
    if open_realms:
        rid = ""
        for name in SECRET_REALMS:
            if any(name in str(x) for x in open_realms):
                rid = name
                break
        if rid:
            raw_list.append(
                {
                    "type": "secret_realm_pressure",
                    "title": "禁制松动",
                    "narrative": f"天象示警：【{rid}】禁制波动，附近灵气紊乱，或有机缘亦有杀劫。",
                    "location": SECRET_REALMS[rid].get("location", ""),
                    "effects": {"realm_id": rid, "force_open": False},
                    "priority": 2,
                }
            )
    if brief.get("blood"):
        raw_list.append(
            {
                "type": "blood_tide",
                "title": "血煞微涨",
                "narrative": "坊间血气浮动，除凶与避祸之议再起，安全区外宜谨慎。",
                "location": "",
                "effects": {"whisper": "血煞异动"},
                "priority": 2,
            }
        )
    if info.get("is_final_week") or float(info.get("remain_real_days") or 0) <= SEASON_WARN_DAYS:
        raw_list.append(
            {
                "type": "calamity_forecast",
                "title": "大劫将至",
                "narrative": "天道示警：纪元终局临近，未安顿道统者宜早做决断。",
                "location": "",
                "effects": {"whisper": "大劫预兆"},
                "priority": 3,
            }
        )
    if not raw_list:
        raw_list.append(
            {
                "type": "omen",
                "title": "灵机一现",
                "narrative": "山雨欲来风满楼，世间看似平静，暗流已在宗门与坊市之间游走。",
                "location": "青云坊市客栈",
                "effects": {
                    "goal_title": "静观天道",
                    "goal_detail": "近日宜多看 /世情 /天道，留意机缘与风声。",
                    "whisper": "风起",
                },
                "priority": 1,
            }
        )
    cleaned: List[Dict[str, Any]] = []
    for raw in raw_list[:DIRECTOR_MAX_ACTIVE]:
        ok, _reason, item = admit_directive(raw, season=info, now=now)
        if ok and item:
            item["source"] = "local"
            cleaned.append(item)
    return cleaned


def _ai_propose(
    brief: Dict[str, Any],
    *,
    force: bool,
    now: float,
) -> Tuple[List[Dict[str, Any]], str, str]:
    """返回 (directives, source, error)"""
    # 测试/降级：local_ai_allowed 且未配置通道 → 本地；配置了通道则优先真 AI
    from config import ai_available

    use_local_first = local_ai_allowed() and not ai_available()
    if use_local_first:
        return _local_directives(brief, now), "local", ""
    if not ai_ready():
        if local_ai_allowed():
            return _local_directives(brief, now), "local", ""
        return [], "error", ai_block_reason() or "AI 通道未配置"
    season = brief.get("season") or {}
    try:
        from ai.router import invoke

        payload = {
            "world_brief": brief.get("text", ""),
            "season_remain_days": float(season.get("remain_real_days") or 0),
            "force": bool(force),
        }
        r = invoke(
            "world_director",
            payload=payload,
            actor_id="world_director",
            timeout=25.0,
        )
        if not r.get("ok"):
            err = str(r.get("error") or "ai_failed")
            if local_ai_allowed():
                return _local_directives(brief, now), "local", err
            return [], "error", err
        data = r.get("data") or {}
        raw_list = data.get("directives") if isinstance(data, dict) else None
        if raw_list is None and isinstance(data, list):
            raw_list = data
        if not isinstance(raw_list, list):
            raw_list = []
        cleaned: List[Dict[str, Any]] = []
        rejected = 0
        for raw in raw_list[:DIRECTOR_MAX_ACTIVE]:
            ok, reason, item = admit_directive(raw, season=season, now=now)
            if ok and item:
                item["source"] = "ai"
                cleaned.append(item)
            else:
                rejected += 1
                _audit(
                    {
                        "event": "reject",
                        "reason": reason,
                        "raw_type": str((raw or {}).get("type") if isinstance(raw, dict) else raw),
                        "source": "ai",
                    }
                )
        if rejected:
            try:
                st = _load()
                st["stats"]["rejected"] = int(st["stats"].get("rejected") or 0) + rejected
                _save(st)
            except Exception:
                pass
        return cleaned, "ai", (f"rejected={rejected}" if rejected and not cleaned else "")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:200]
        if local_ai_allowed():
            return _local_directives(brief, now), "local", err
        return [], "error", err


def active_directives(now: Optional[float] = None) -> List[Dict[str, Any]]:
    """仍存活的导演指令（供 NPC/江湖/战斗等系统读取）"""
    t = _now(now)
    state = _load()
    _prune_active(state, t)
    out = []
    for d in state.get("active") or []:
        if isinstance(d, dict) and float(d.get("expires_at") or 0) >= t:
            out.append(d)
    return out


def world_modifiers(now: Optional[float] = None) -> Dict[str, Any]:
    """
    由活跃指令 + 世界弧推导的世界修饰（规则侧消费，AI 不直接改数）。
    """
    t = _now(now)
    active = active_directives(t)
    blood_locs: List[str] = []
    sects: List[Tuple[str, str]] = []
    realms: List[str] = []
    calamity = False
    for d in active:
        dtype = d.get("type")
        eff = d.get("effects") or {}
        loc = str(eff.get("location") or d.get("location") or "").strip()
        if dtype == "blood_tide":
            if loc:
                blood_locs.append(loc)
        elif dtype == "sect_tension":
            sa = str(eff.get("sect_a") or "").strip()
            sb = str(eff.get("sect_b") or "").strip()
            if sa and sb:
                sects.append((sa, sb))
        elif dtype == "secret_realm_pressure":
            rid = str(eff.get("realm_id") or "").strip()
            if rid:
                realms.append(rid)
        elif dtype == "calamity_forecast":
            calamity = True
    hunt_heat = 1.35 if blood_locs else (1.15 if any(d.get("type") == "blood_tide" for d in active) else 1.0)
    # 叠加 M2 世界弧
    try:
        from core.world_arc import arc_modifiers

        am = arc_modifiers(t)
        for loc in am.get("blood_tide_locations") or []:
            if loc not in blood_locs:
                blood_locs.append(loc)
        for pair in am.get("sect_tensions") or []:
            if pair not in sects:
                sects.append(pair)
        for rid in am.get("realm_pressure_ids") or []:
            if rid not in realms:
                realms.append(rid)
        calamity = calamity or bool(am.get("calamity_forecast"))
        hunt_heat = max(hunt_heat, float(am.get("hunt_heat") or 1.0))
        heat_by_location = dict(am.get("heat_by_location") or {})
    except Exception:
        heat_by_location = {}
    # 指令地点也进 heat
    for loc in blood_locs:
        heat_by_location[loc] = max(heat_by_location.get(loc, 1.0), 1.45)
    return {
        "blood_tide_locations": blood_locs,
        "sect_tensions": sects,
        "realm_pressure_ids": realms,
        "calamity_forecast": calamity,
        "hunt_heat": hunt_heat,
        "heat_by_location": heat_by_location,
        "active_types": [d.get("type") for d in active],
        "n_active": len(active),
    }


def location_heat(location: str, now: Optional[float] = None) -> float:
    """某地点因导演/世界弧态势产生的行动热度（1.0=常态）"""
    if not location:
        return 1.0
    mods = world_modifiers(now)
    by = mods.get("heat_by_location") or {}
    if location in by:
        return float(by[location])
    if location in (mods.get("blood_tide_locations") or []):
        return 1.45
    if mods.get("calamity_forecast"):
        return 1.15
    return 1.0


def agenda_bias_for_npc(npc: Any, now: Optional[float] = None) -> Optional[Dict[str, str]]:
    """
    导师态势 + 世界弧 对 NPC 本 tick 议程的规则偏置。
    只影响「选哪条议程」，结算仍走 JianghuSimulator 规则。
    """
    if npc is None:
        return None
    # 世界弧优先（更具体）
    try:
        from core.world_arc import agenda_bias_from_arcs

        ab = agenda_bias_from_arcs(npc, now=now)
        if ab:
            return ab
    except Exception:
        pass
    mods = world_modifiers(now)
    loc = getattr(npc, "location", "") or ""
    sect = getattr(npc, "sect", "") or ""
    if loc and loc in mods.get("blood_tide_locations"):
        return {
            "agenda_type": "patrol",
            "note": "天道导演·血煞潮：同场戒备，加强巡守",
        }
    for sa, sb in mods.get("sect_tensions") or []:
        if sect and sect in (sa, sb):
            if getattr(npc, "karma", None) is not None and npc.karma.sin_value >= 80:
                return {
                    "agenda_type": "revenge",
                    "note": f"天道导演·宗门紧张（{sa}×{sb}）：借势寻隙",
                }
            return {
                "agenda_type": "patrol",
                "note": f"天道导演·宗门紧张（{sa}×{sb}）：谨守门户",
            }
    if mods.get("calamity_forecast"):
        try:
            if npc.realm and getattr(npc.realm, "is_full", False):
                return {"agenda_type": "seclusion", "note": "天道导演·大劫预兆：闭关冲关"}
        except Exception:
            pass
        return {"agenda_type": "survive", "note": "天道导演·大劫预兆：趋吉避凶"}
    return None


def note_player_event(
    kind: str,
    *,
    character: Any = None,
    location: str = "",
    detail: str = "",
    force_run: bool = False,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """
    玩家/世界重大行为惊动天道：写入导演近事，必要时触发一轮提案。
    kind: kill | blood_mark | sin_spike | breakthrough | manual
    """
    t = _now(now)
    state = _load()
    events = list(state.get("player_events") or [])
    name = getattr(character, "name", "") or ""
    sin = 0
    marked = False
    try:
        if character is not None:
            sin = int(character.karma.sin_value)
            marked = bool(character.karma.is_blood_marked(t))
    except Exception:
        pass
    events.append(
        {
            "kind": kind,
            "who": name,
            "sin": sin,
            "marked": marked,
            "location": location or getattr(character, "location", "") or "",
            "detail": (detail or "")[:80],
            "ts": t,
        }
    )
    state["player_events"] = events[-20:]
    _save(state)

    should = force_run
    trigger = kind
    if not should:
        if kind in ("blood_mark", "sin_spike") or marked or sin >= 120:
            should = True
            trigger = "blood_mark" if marked or sin >= 120 else kind
        elif kind == "kill" and sin >= 80:
            should = True
            trigger = "kill_sin"
        elif kind == "manual":
            should = True
            trigger = "manual"
    if not should:
        return {"ok": False, "skipped": "event_below_threshold", "kind": kind}

    return WorldDirector.run_cycle(trigger=trigger, force=force_run or marked or sin >= 120, now=t)


def apply_directive(d: Dict[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
    """规则侧落账：频道 / 目标 / 秘境开启 / 态势标记（态势由 world_modifiers 消费）"""
    t = _now(now)
    applied: Dict[str, Any] = {"channel": False, "goals": 0, "realm": "", "flags": []}
    dtype = d.get("type")
    effects = d.get("effects") or {}
    title = d.get("title") or "天道有感"
    narrative = d.get("narrative") or ""
    loc = d.get("location") or ""
    level = d.get("channel_level") or "major"
    text = f"【天道导演】{title}：{narrative}"
    if loc:
        text = f"{text} @{loc}"

    # 秘境提前开启
    if dtype == "secret_realm_pressure" and effects.get("force_open"):
        rid = str(effects.get("realm_id") or "")
        try:
            from core.secret_realm import director_force_open

            ok = director_force_open(rid, now=t)
            applied["realm"] = rid if ok else ""
            applied["flags"].append("realm_opened" if ok else "realm_open_failed")
            if ok:
                applied["flags"].append(rid)
        except Exception as e:
            applied["flags"].append(f"realm_err:{type(e).__name__}")

    # 血煞/宗门态势（活跃指令即世界修饰源）
    if dtype == "blood_tide":
        applied["flags"].append("blood_tide")
        if effects.get("location") or loc:
            applied["flags"].append(f"loc:{effects.get('location') or loc}")
    if dtype == "sect_tension":
        applied["flags"].append(
            f"sect:{effects.get('sect_a')}vs{effects.get('sect_b')}"
        )
        # 世情/除凶可感知：宗门紧张时同场 NPC 会偏置（见 agenda_bias_for_npc）
    if dtype == "calamity_forecast":
        applied["flags"].append("calamity_forecast")

    # 机缘目标投射
    if dtype in ("omen", "secret_realm_pressure") and (
        effects.get("goal_title") or dtype == "omen"
    ):
        g_title = str(effects.get("goal_title") or title)[:40]
        g_detail = str(effects.get("goal_detail") or narrative)[:200]
        n = 0
        try:
            from core.goals import GoalEngine

            targets: List[Any] = []
            for c in CharacterRepository.list_all_alive():
                uid = str(getattr(c, "user_id", "") or "")
                if uid.startswith("npc_") or uid.startswith("ai_npc_"):
                    continue
                if c.status == CharacterStatus.DEAD:
                    continue
                targets.append(c)
                if len(targets) >= DIRECTOR_GOAL_FANOUT:
                    break
            for c in targets:
                res = GoalEngine.add_opportunity(c, g_title, g_detail)
                if res.get("success"):
                    n += 1
                    try:
                        CharacterRepository.save(c)
                    except Exception:
                        pass
            applied["goals"] = n
        except Exception as e:
            applied["flags"].append(f"goal_err:{type(e).__name__}")

    # 频道播报（directive 入库不依赖频道限流成功）
    try:
        msg = WorldChannel.post(
            "director",
            text[:160],
            level=level,
            actor=f"director:{dtype}",
            location=loc,
            now=t,
            skip_limit=True,
        )
        applied["channel"] = msg is not None
    except Exception:
        applied["channel"] = False

    _audit(
        {
            "event": "apply",
            "directive_id": d.get("id"),
            "type": dtype,
            "source": d.get("source"),
            "applied": applied,
        }
    )
    return applied


class WorldDirector:
    """世界走向导演：周期/事件触发，AI 提案 + 规则落账"""

    @staticmethod
    def tick_gate_ok(now: Optional[float] = None) -> bool:
        t = _now(now)
        state = _load()
        last = float(state.get("last_run_ts") or 0)
        return (t - last) >= float(DIRECTOR_TICK_INTERVAL_SECONDS)

    @staticmethod
    def run_cycle(
        trigger: str = "timer",
        *,
        force: bool = False,
        now: Optional[float] = None,
        gateway: Any = None,
    ) -> Dict[str, Any]:
        t = _now(now)
        state = _load()
        _prune_active(state, t)

        last = float(state.get("last_run_ts") or 0)
        # 大劫窗口：若尚无 calamity_forecast 活跃指令，放宽 tick 闸（仍尊重最小冷却除非 force）
        try:
            info_now = season_info(t)
            in_calamity_window = bool(info_now.get("is_final_week")) or float(
                info_now.get("remain_real_days") or 0
            ) <= float(SEASON_WARN_DAYS)
        except Exception:
            in_calamity_window = False
        has_calamity_dir = any(
            isinstance(d, dict) and d.get("type") == "calamity_forecast"
            for d in (state.get("active") or [])
        )
        calamity_need = in_calamity_window and not has_calamity_dir

        if not force and (t - last) < float(DIRECTOR_MIN_INTERVAL_SECONDS):
            # 大劫急需且无预兆：允许突破最小冷却
            if not calamity_need:
                state["stats"]["attempts"] = int(state["stats"].get("attempts") or 0) + 1
                state["last_trigger"] = trigger
                state["last_source"] = "skipped"
                state["last_error"] = "cooldown"
                _save(state)
                return {
                    "ok": False,
                    "skipped": "cooldown",
                    "message": f"天道未至再演之时（冷却 {DIRECTOR_MIN_INTERVAL_SECONDS:.0f}s）",
                }

        if not force and trigger == "timer":
            # tick 路径额外墙钟闸；大劫窗口待发预兆时放行
            if (t - last) < float(DIRECTOR_TICK_INTERVAL_SECONDS) and not calamity_need:
                state["stats"]["attempts"] = int(state["stats"].get("attempts") or 0) + 1
                state["last_trigger"] = trigger
                state["last_source"] = "skipped"
                state["last_error"] = "tick_gate"
                _save(state)
                return {"ok": False, "skipped": "tick_gate", "message": "导演 tick 闸未开"}

        if len(state.get("active") or []) >= DIRECTOR_MAX_ACTIVE and not force:
            # 大劫预兆优先：满员时可替换最旧的一条非 calamity
            if not (calamity_need and in_calamity_window):
                state["stats"]["attempts"] = int(state["stats"].get("attempts") or 0) + 1
                state["last_trigger"] = trigger
                state["last_source"] = "skipped"
                state["last_error"] = "max_active"
                _save(state)
                return {"ok": False, "skipped": "max_active", "message": "世间已有足够天道态势"}

        # 进入实际提案阶段才计 runs
        state["stats"]["runs"] = int(state.get("stats", {}).get("runs") or 0) + 1
        state["stats"]["attempts"] = int(state["stats"].get("attempts") or 0) + 1

        brief = gather_world_brief(t)
        if gateway is not None:
            # 测试注入
            try:
                raw = gateway(director_prompt_for_test(brief, force=force))
                data = raw if isinstance(raw, dict) else {}
                raw_list = data.get("directives") or []
                cleaned: List[Dict[str, Any]] = []
                rejected = 0
                for item_raw in raw_list[:DIRECTOR_MAX_ACTIVE]:
                    ok, reason, item = admit_directive(
                        item_raw, season=brief.get("season"), now=t
                    )
                    if ok and item:
                        item["source"] = "ai"
                        cleaned.append(item)
                    else:
                        rejected += 1
                        _audit({"event": "reject", "reason": reason, "source": "ai"})
                state["stats"]["rejected"] = int(state["stats"].get("rejected") or 0) + rejected
                source, error = "ai", (f"rejected={rejected}" if rejected else "")
            except Exception as e:
                cleaned, source, error = [], "error", f"{type(e).__name__}: {e}"[:200]
                if local_ai_allowed():
                    cleaned, source = _local_directives(brief, t), "local"
        else:
            cleaned, source, error = _ai_propose(brief, force=force, now=t)

        if source == "error" and not cleaned:
            state.update(
                {
                    "last_run_ts": t,
                    "last_trigger": trigger,
                    "last_source": "error",
                    "last_error": error or "director_unavailable",
                    "last_accepted": 0,
                }
            )
            _save(state)
            _audit({"event": "run_error", "trigger": trigger, "error": error})
            return {
                "ok": False,
                "error": error or "director_unavailable",
                "message": error or ai_block_reason() or "天道导演暂不可用",
                "source": "error",
            }

        applied_rows = []
        for d in cleaned:
            d.setdefault("source", source)
            d["applied"] = apply_directive(d, now=t)
            applied_rows.append(d)

        state["active"] = (state.get("active") or []) + applied_rows
        _prune_active(state, t)
        if len(state["active"]) > DIRECTOR_MAX_ACTIVE:
            # 大劫预兆优先保留
            cal = [d for d in state["active"] if d.get("type") == "calamity_forecast"]
            others = [d for d in state["active"] if d.get("type") != "calamity_forecast"]
            state["active"] = (others + cal)[-DIRECTOR_MAX_ACTIVE:]
        state["last_run_ts"] = t
        state["last_trigger"] = trigger
        state["last_source"] = source
        state["last_error"] = error or ""
        state["last_accepted"] = len(applied_rows)
        state["stats"]["accepted"] = int(state["stats"].get("accepted") or 0) + len(applied_rows)
        for d in applied_rows:
            _push_history(
                state,
                f"{int(t)}|{d.get('type')}|{d.get('title')}|{d.get('source')}|{d.get('id')}",
            )
        _save(state)
        # M2：导师指令升格世界弧
        arcs_spawned = []
        try:
            from core.world_arc import absorb_director_cycle

            arcs_spawned = absorb_director_cycle(applied_rows, now=t)
        except Exception:
            arcs_spawned = []
        return {
            "ok": True,
            "source": source,
            "trigger": trigger,
            "count": len(applied_rows),
            "directives": applied_rows,
            "arcs_spawned": arcs_spawned,
            "brief_hint": (applied_rows[0].get("title") if applied_rows else "天道沉寂"),
        }

    @staticmethod
    def format_heaven_board(now: Optional[float] = None) -> str:
        t = _now(now)
        state = _load()
        _prune_active(state, t)
        src = state.get("last_source") or "—"
        src_cn = {
            "ai": "服务器 AI",
            "local": "本地降级（非正式）",
            "error": "不可用",
            "skipped": "未触发",
            "": "尚未运行",
        }.get(src, src)
        lines = ["【天道导演】AI 提案 · 规则落账（主导走向，不直接改数值）"]
        lines.append(
            f"上次运行：{_fmt_ts(state.get('last_run_ts'))} · 触发 {state.get('last_trigger') or '—'} "
            f"· 来源 {src_cn}"
        )
        if state.get("last_error"):
            lines.append(f"备注：{state.get('last_error')}")
        stats = state.get("stats") or {}
        lines.append(
            f"累计：提案 {stats.get('runs', 0)} · 尝试 {stats.get('attempts', stats.get('runs', 0))} "
            f"· 落账 {stats.get('accepted', 0)} · 驳回 {stats.get('rejected', 0)}"
        )
        active = state.get("active") or []
        lines.append(f"活跃指令（{len(active)}）：")
        if not active:
            lines.append("  · 世间暂无导演态势（可用 /天道 推演 触发）")
        for i, d in enumerate(active[:8], 1):
            loc = f" @{d.get('location')}" if d.get("location") else ""
            src_d = d.get("source") or ""
            mark = "〔local〕" if src_d == "local" else ""
            lines.append(
                f"  {i}. [{d.get('type')}] {mark}{d.get('title')}{loc} · 剩余约 "
                f"{max(0, int(float(d.get('expires_at') or 0) - t))}s"
            )
            if d.get("narrative"):
                lines.append(f"     {d.get('narrative')}")
            ap = d.get("applied") or {}
            bits = []
            if ap.get("channel"):
                bits.append("已播报")
            if ap.get("goals"):
                bits.append(f"机缘目标×{ap.get('goals')}")
            if ap.get("realm"):
                bits.append(f"秘境:{ap.get('realm')}")
            if bits:
                lines.append(f"     落账：{' · '.join(bits)}")
        hist = list(state.get("history") or [])[-5:]
        if hist:
            lines.append("近史：")
            for h in reversed(hist):
                parts = str(h).split("|")
                if len(parts) >= 4:
                    lines.append(f"  · {parts[2]}（{parts[1]} · {parts[3]}）")
        try:
            mods = world_modifiers(t)
            lines.append(
                "世界修饰："
                f"血煞潮地={mods.get('blood_tide_locations') or '无'} · "
                f"宗门紧张={mods.get('sect_tensions') or '无'} · "
                f"大劫预兆={'是' if mods.get('calamity_forecast') else '否'} · "
                f"除凶热度×{mods.get('hunt_heat', 1.0):.2f}"
            )
        except Exception:
            pass
        pe = list(state.get("player_events") or [])[-3:]
        if pe:
            lines.append("近惊动天道：")
            for e in reversed(pe):
                lines.append(
                    f"  · {e.get('kind')} · {e.get('who') or '—'}"
                    f"{(' @' + e['location']) if e.get('location') else ''}"
                    f" · 业力{e.get('sin', 0)}"
                )
        lines.append("权限边界：AI 只提案态势/目标提示；胜负与掉落仍归规则引擎。")
        return "\n".join(lines)

    @staticmethod
    def schedule_lines(now: Optional[float] = None, limit: int = 3) -> List[str]:
        t = _now(now)
        state = _load()
        _prune_active(state, t)
        rows = []
        for d in (state.get("active") or [])[:limit]:
            loc = f" @{d.get('location')}" if d.get("location") else ""
            rows.append(f"· [{d.get('type')}] {d.get('title')}{loc}")
        return rows


def _fmt_ts(ts: Any) -> str:
    try:
        ts = float(ts or 0)
        if ts <= 0:
            return "从未"
        return time.strftime("%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "—"


# 供测试注入的 prompt 桥（避免 circular 在 run_cycle 内延迟 import 失败）
def director_prompt_for_test(brief: Dict[str, Any], force: bool = False) -> str:
    from ai.play_prompts import director_prompt

    info = brief.get("season") or {}
    return director_prompt(
        brief.get("text", ""),
        season_remain_days=float(info.get("remain_real_days") or 0),
        force=force,
    )


def handle_heaven_command(action: str, parts: List[str]) -> Dict[str, Any]:
    """/天道 面板与推演"""
    sub = (parts[1].strip() if len(parts) > 1 else "").lower()
    if sub in ("推演", "run", "演", "tick"):
        res = WorldDirector.run_cycle(trigger="command", force=True)
        board = WorldDirector.format_heaven_board()
        if res.get("ok"):
            return {
                "ok": True,
                "text": f"天道导演已推演：{res.get('brief_hint', '')}\n\n{board}",
                "director": res,
            }
        return {
            "ok": False,
            "text": f"天道导演未能推演：{res.get('message') or res.get('error')}\n\n{board}",
            "director": res,
        }
    return {"ok": True, "text": WorldDirector.format_heaven_board()}
