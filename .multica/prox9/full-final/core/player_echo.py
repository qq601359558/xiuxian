"""
M4 玩家回写：重大玩家行为改写世界结构

- 个人回写档案（击杀/业力/名气/标签）
- 区域危险与恐慌
- 坊市恐慌价（商会买卖倍率）
- 除凶池压力
- 惊动天道导演
规则钳制一切倍率；AI 只叙事/提案。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from config import (
    ECHO_DANGER_HEAT_MAX,
    ECHO_FAME_BREAKTHROUGH,
    ECHO_FAME_KILL,
    ECHO_KILL_WINDOW_SEC,
    ECHO_MARKET_BUY_MAX,
    ECHO_MARKET_SELL_MIN,
    ECHO_REGION_DECAY_PER_TICK,
    ECHO_SIN_SPIKE_THRESHOLD,
    ECHO_STREAK_DIRECTOR_TRIGGER,
    WORLD_LOCATIONS,
)
from storage.db import CharacterRepository, ChronicleRepository, WorldStateRepository
from core.models import CharacterStatus
from core.world_channel import WorldChannel
from ai.audit import write_audit

_KEY = "player_echo"


def _now(now: Optional[float] = None) -> float:
    return now if now is not None else time.time()


def _is_npc(c: Any) -> bool:
    uid = str(getattr(c, "user_id", "") or "")
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def _load() -> Dict[str, Any]:
    try:
        data = WorldStateRepository.get(_KEY) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("echoes", {})
    data.setdefault("region", {})
    data.setdefault("market", {"buy_mult": 1.0, "sell_mult": 1.0, "panic": 0.0, "reason": ""})
    data.setdefault("bounty", {"n_marked": 0, "pool_bonus": 0, "hunt_heat": 1.0})
    data.setdefault("mood", {"blood_index": 0.0, "fear_index": 0.0})
    data.setdefault("log", [])
    data.setdefault(
        "stats",
        {"kills_recorded": 0, "region_updates": 0, "market_shifts": 0, "director_wakes": 0},
    )
    if not isinstance(data.get("stats"), dict):
        data["stats"] = {
            "kills_recorded": 0,
            "region_updates": 0,
            "market_shifts": 0,
            "director_wakes": 0,
        }
    return data


def _save(state: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, state)
    except Exception:
        pass


def _log(state: Dict[str, Any], line: str, limit: int = 40) -> None:
    rows = list(state.get("log") or [])
    rows.append(line[:160])
    state["log"] = rows[-limit:]


def _audit(rec: Dict[str, Any]) -> None:
    try:
        write_audit({"source": "ai.player_echo", **rec})
    except Exception:
        pass


def _ensure_echo(state: Dict[str, Any], character: Any, now: float) -> Dict[str, Any]:
    echoes = state.get("echoes") or {}
    cid = getattr(character, "id", "") or ""
    e = echoes.get(cid) or {
        "id": cid,
        "name": getattr(character, "name", "") or "",
        "kill_streak": [],
        "kill_total": 0,
        "sin_peak": 0,
        "fame": 0,
        "locations": {},
        "labels": [],
        "blood_marked_at": 0.0,
        "last_event_ts": now,
        "updated_at": now,
    }
    e["name"] = getattr(character, "name", "") or e.get("name") or ""
    echoes[cid] = e
    state["echoes"] = echoes
    return e


def _refresh_labels(e: Dict[str, Any], character: Any = None) -> List[str]:
    labels = []
    streak = len(e.get("kill_streak") or [])
    sin = int(e.get("sin_peak") or 0)
    if character is not None:
        try:
            sin = max(sin, int(character.karma.sin_value))
            e["sin_peak"] = sin
        except Exception:
            pass
    marked = False
    if character is not None:
        try:
            marked = bool(character.karma.is_blood_marked())
        except Exception:
            marked = False
    if marked or sin >= 120:
        labels.append("血煞显影")
    elif sin >= 80:
        labels.append("重业缠身")
    if streak >= 3:
        labels.append("连斩凶名")
    elif streak >= 2:
        labels.append("出手凌厉")
    locs = e.get("locations") or {}
    if locs:
        top_loc = max(locs.items(), key=lambda x: x[1])[0]
        if locs[top_loc] >= 3:
            labels.append(f"{top_loc}凶人")
    if int(e.get("fame") or 0) >= 20:
        labels.append("名动一方")
    if int(e.get("fame") or 0) >= 40:
        labels.append("威震东荒")
    e["labels"] = labels[:4]
    return e["labels"]


def _recompute_market_and_mood(state: Dict[str, Any], now: float) -> None:
    region = state.get("region") or {}
    total_kill = 0.0
    total_danger = 0.0
    n = 0
    for r in region.values():
        total_kill += float(r.get("kill_24h") or 0)
        total_danger += float(r.get("danger") or 0)
        n += 1
    avg_danger = total_danger / n if n else 0.0
    blood = max(0.0, min(100.0, avg_danger * 0.7 + total_kill * 6.0))
    fear = max(0.0, min(100.0, blood * 0.85 + float((state.get("bounty") or {}).get("n_marked") or 0) * 8.0))
    panic = max(0.0, min(100.0, fear * 0.9))
    # 商会恐慌：买贵卖贱（钳制）
    buy_mult = max(1.0, min(ECHO_MARKET_BUY_MAX, 1.0 + panic / 200.0))
    sell_mult = max(ECHO_MARKET_SELL_MIN, min(1.0, 1.0 - panic / 280.0))
    market = state.get("market") or {}
    if abs(float(market.get("buy_mult") or 1) - buy_mult) > 0.005 or abs(
        float(market.get("sell_mult") or 1) - sell_mult
    ) > 0.005:
        state["stats"]["market_shifts"] = int(state["stats"].get("market_shifts") or 0) + 1
    reason = ""
    if panic >= 55:
        reason = "血雨腥风，商会坐地起价，回收亦压秤"
    elif panic >= 30:
        reason = "世道不宁，坊市人心惶惶"
    elif panic >= 12:
        reason = "风声渐紧，货价微浮"
    state["market"] = {
        "buy_mult": round(buy_mult, 4),
        "sell_mult": round(sell_mult, 4),
        "panic": round(panic, 2),
        "reason": reason,
        "updated_at": now,
    }
    state["mood"] = {
        "blood_index": round(blood, 2),
        "fear_index": round(fear, 2),
        "updated_at": now,
    }
    # 除凶池：血煞/重业人数
    n_marked = 0
    try:
        from core.hunt import is_marked

        for c in CharacterRepository.list_all_alive():
            if c.status == CharacterStatus.DEAD:
                continue
            if not _is_npc(c) and is_marked(c):
                n_marked += 1
    except Exception:
        n_marked = int((state.get("bounty") or {}).get("n_marked") or 0)
    pool_bonus = max(0, (n_marked - 1) * 5)
    state["bounty"] = {
        "n_marked": n_marked,
        "pool_bonus": pool_bonus,
        "hunt_heat": round(1.0 + min(0.5, n_marked * 0.08 + panic / 200.0), 4),
        "updated_at": now,
    }


def record_player_kill(
    killer: Any,
    victim: Any = None,
    location: str = "",
    *,
    looted: int = 0,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """玩家击杀回写：区域危险↑、名气、连斩、惊动导演"""
    t = _now(now)
    if killer is None or _is_npc(killer):
        return {"ok": False, "reason": "not_player"}
    loc = location or getattr(killer, "location", "") or ""
    state = _load()
    e = _ensure_echo(state, killer, t)
    e["kill_total"] = int(e.get("kill_total") or 0) + 1
    e["fame"] = int(e.get("fame") or 0) + ECHO_FAME_KILL
    streak = list(e.get("kill_streak") or [])
    streak = [x for x in streak if t - float(x) < ECHO_KILL_WINDOW_SEC]
    streak.append(t)
    e["kill_streak"] = streak[-10:]
    e["last_event_ts"] = t
    e["updated_at"] = t
    try:
        e["sin_peak"] = max(int(e.get("sin_peak") or 0), int(killer.karma.sin_value))
    except Exception:
        pass
    if loc:
        locs = dict(e.get("locations") or {})
        locs[loc] = int(locs.get(loc) or 0) + 1
        e["locations"] = locs
    _refresh_labels(e, killer)
    # 区域
    region = state.get("region") or {}
    r = region.get(loc) or {
        "location": loc,
        "danger": 0.0,
        "kill_24h": 0,
        "panic": 0.0,
        "top_actor": "",
        "top_actor_name": "",
        "updated_at": t,
    }
    r["kill_24h"] = int(r.get("kill_24h") or 0) + 1
    r["danger"] = max(0.0, min(100.0, float(r.get("danger") or 0) + 12.0 + (8.0 if looted > 200 else 0)))
    r["panic"] = min(100.0, float(r.get("panic") or 0) + 8.0)
    r["top_actor"] = killer.id
    r["top_actor_name"] = killer.name
    r["updated_at"] = t
    if loc:
        region[loc] = r
    state["region"] = region
    state["stats"]["kills_recorded"] = int(state["stats"].get("kills_recorded") or 0) + 1
    state["stats"]["region_updates"] = int(state["stats"].get("region_updates") or 0) + 1
    _log(
        state,
        f"{int(t)}|kill|{killer.name}|{getattr(victim, 'name', '')}|{loc}|streak={len(e['kill_streak'])}",
    )
    _recompute_market_and_mood(state, t)
    _save(state)
    _audit(
        {
            "event": "kill_echo",
            "killer": killer.name,
            "victim": getattr(victim, "name", ""),
            "location": loc,
            "streak": len(e["kill_streak"]),
        }
    )
    # 世界频道：区域凶名
    try:
        if loc and (r["danger"] >= 35 or len(e["kill_streak"]) >= 2):
            WorldChannel.post(
                "echo",
                f"【望气】{loc} 血气上涌，近闻与【{killer.name}】有关，凶险之象渐显。",
                level="major",
                actor=killer.name,
                location=loc,
            )
    except Exception:
        pass
    # NPC 同场对凶手态度恶化
    try:
        if loc:
            from core.npc_mind import shift_attitude, _is_npc as _inpc

            for c in CharacterRepository.list_all_alive():
                if c.id == killer.id or c.status == CharacterStatus.DEAD:
                    continue
                if c.location != loc or not _inpc(c):
                    continue
                shift_attitude(c, killer.id, -12, reason=f"目击{killer.name}于{loc}行凶")
    except Exception:
        pass
    # 惊动天道
    woke = False
    try:
        if len(e["kill_streak"]) >= ECHO_STREAK_DIRECTOR_TRIGGER or (
            getattr(killer.karma, "sin_value", 0) >= 80
        ):
            from core.world_director import note_player_event, WorldDirector

            note_player_event(
                "kill",
                character=killer,
                location=loc,
                detail=f"回写连斩x{len(e['kill_streak'])}",
                force_run=len(e["kill_streak"]) >= ECHO_STREAK_DIRECTOR_TRIGGER,
                now=t,
            )
            state = _load()
            state["stats"]["director_wakes"] = int(state["stats"].get("director_wakes") or 0) + 1
            _save(state)
            woke = True
    except Exception:
        woke = False
    return {
        "ok": True,
        "streak": len(e["kill_streak"]),
        "region_danger": float(r.get("danger") or 0),
        "labels": e.get("labels") or [],
        "director_wake": woke,
        "market_panic": (state.get("market") or {}).get("panic"),
    }


def record_player_sin(
    character: Any,
    delta: int,
    *,
    reason: str = "",
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """业力飙升回写（由调用方传入本次增量）"""
    t = _now(now)
    if character is None or _is_npc(character):
        return {"ok": False, "reason": "not_player"}
    try:
        sin = int(character.karma.sin_value)
    except Exception:
        sin = 0
    state = _load()
    e = _ensure_echo(state, character, t)
    if sin > int(e.get("sin_peak") or 0):
        e["sin_peak"] = sin
    e["last_event_ts"] = t
    e["updated_at"] = t
    _refresh_labels(e, character)
    loc = getattr(character, "location", "") or ""
    if int(delta) >= ECHO_SIN_SPIKE_THRESHOLD and loc:
        region = state.get("region") or {}
        r = region.get(loc) or {"location": loc, "danger": 0.0, "kill_24h": 0, "panic": 0.0}
        r["danger"] = min(100.0, float(r.get("danger") or 0) + float(delta) * 0.25)
        r["panic"] = min(100.0, float(r.get("panic") or 0) + float(delta) * 0.15)
        r["updated_at"] = t
        region[loc] = r
        state["region"] = region
        _log(state, f"{int(t)}|sin|{character.name}|+{delta}|{loc}|{reason[:30]}")
        try:
            WorldChannel.post(
                "echo",
                f"【望气】{character.name} 业力骤涨（+{delta}），{loc} 隐有血光。",
                level="major",
                actor=character.name,
                location=loc,
            )
        except Exception:
            pass
    _recompute_market_and_mood(state, t)
    _save(state)
    woke = False
    if sin >= 120:
        try:
            from core.world_director import note_player_event

            note_player_event(
                "sin_spike",
                character=character,
                location=loc,
                detail=reason or f"sin={sin}",
                force_run=True,
                now=t,
            )
            woke = True
        except Exception:
            woke = False
    return {"ok": True, "sin": sin, "labels": e.get("labels"), "director_wake": woke}


def record_player_breakthrough(character: Any, realm_name: str = "", now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    if character is None or _is_npc(character):
        return {"ok": False}
    state = _load()
    e = _ensure_echo(state, character, t)
    e["fame"] = int(e.get("fame") or 0) + ECHO_FAME_BREAKTHROUGH
    e["updated_at"] = t
    _refresh_labels(e, character)
    _log(state, f"{int(t)}|breakthrough|{character.name}|{realm_name}")
    _recompute_market_and_mood(state, t)
    _save(state)
    return {"ok": True, "fame": e["fame"], "labels": e.get("labels")}


def record_player_merit(character: Any, amount: int = 1, reason: str = "", now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    if character is None or _is_npc(character):
        return {"ok": False}
    state = _load()
    e = _ensure_echo(state, character, t)
    if amount > 0:
        e["fame"] = int(e.get("fame") or 0) + max(1, amount // 2)
        e["updated_at"] = t
        _refresh_labels(e, character)
        _save(state)
    return {"ok": True, "fame": e.get("fame")}


def get_player_echo(character: Any, now: Optional[float] = None) -> Dict[str, Any]:
    if character is None:
        return {}
    state = _load()
    e = (state.get("echoes") or {}).get(getattr(character, "id", "")) or {}
    _refresh_labels(e, character) if e else None
    return e


def player_echo_text(character: Any, now: Optional[float] = None) -> str:
    t = _now(now)
    e = get_player_echo(character, t)
    loc = getattr(character, "location", "") or ""
    region = region_info(loc, t)
    labels = e.get("labels") or []
    lines = ["【望气·己身】你的行迹在天道上的投影"]
    if labels:
        lines.append(f"凶名/气象：{'、'.join(labels)}")
    else:
        lines.append("凶名/气象：清白无显影（重大行为会改写世界）")
    streak = [x for x in (e.get("kill_streak") or []) if t - float(x) < ECHO_KILL_WINDOW_SEC]
    lines.append(
        f"回写档案：连斩窗 {len(streak)} · 累计斩 {e.get('kill_total', 0)} · "
        f"业力峰 {e.get('sin_peak', 0)} · 名气 {e.get('fame', 0)}"
    )
    if e.get("locations"):
        top = sorted(e["locations"].items(), key=lambda x: -x[1])[:3]
        lines.append("行凶热点：" + "、".join(f"{k}×{v}" for k, v in top))
    if loc:
        lines.append(
            f"所在【{loc}】：危险 {region.get('danger', 0):.0f} · "
            f"近斩 {region.get('kill_24h', 0)} · "
            f"{'凶名所系：' + str(region.get('top_actor_name') or '') if region.get('top_actor_name') else '尚无显凶'}"
        )
    return "\n".join(lines)


def region_info(location: str, now: Optional[float] = None) -> Dict[str, Any]:
    if not location:
        return {}
    state = _load()
    return dict((state.get("region") or {}).get(location) or {})


def region_heat(location: str, now: Optional[float] = None) -> float:
    """区域回写热度 1.0–ECHO_DANGER_HEAT_MAX"""
    info = region_info(location, now)
    danger = float(info.get("danger") or 0)
    if danger <= 0:
        return 1.0
    extra = danger / 100.0 * (ECHO_DANGER_HEAT_MAX - 1.0)
    return max(1.0, min(ECHO_DANGER_HEAT_MAX, 1.0 + extra))


def market_buy_mult(now: Optional[float] = None) -> float:
    return float((_load().get("market") or {}).get("buy_mult") or 1.0)


def market_sell_mult(now: Optional[float] = None) -> float:
    return float((_load().get("market") or {}).get("sell_mult") or 1.0)


def market_panic_text(now: Optional[float] = None) -> str:
    m = _load().get("market") or {}
    panic = float(m.get("panic") or 0)
    reason = m.get("reason") or ""
    if panic < 8:
        return "坊市平稳。"
    return f"坊市恐慌 {panic:.0f}：{reason}（买×{m.get('buy_mult',1)} / 卖×{m.get('sell_mult',1)}）"


def bounty_pressure(now: Optional[float] = None) -> Dict[str, Any]:
    return dict(_load().get("bounty") or {})


def hunt_merit_bonus(now: Optional[float] = None) -> int:
    """除凶成功时额外功德（池压力）"""
    b = bounty_pressure(now)
    return int(min(30, int(b.get("pool_bonus") or 0)))


def echo_modifiers(now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    state = _load()
    region = state.get("region") or {}
    hot = sorted(
        [
            (loc, float(r.get("danger") or 0))
            for loc, r in region.items()
            if float(r.get("danger") or 0) >= 20
        ],
        key=lambda x: -x[1],
    )[:6]
    mood = state.get("mood") or {}
    market = state.get("market") or {}
    bounty = state.get("bounty") or {}
    return {
        "hot_regions": hot,
        "heat_by_location": {loc: region_heat(loc, t) for loc, _d in hot},
        "market_buy_mult": float(market.get("buy_mult") or 1.0),
        "market_sell_mult": float(market.get("sell_mult") or 1.0),
        "market_panic": float(market.get("panic") or 0),
        "market_reason": market.get("reason") or "",
        "blood_index": float(mood.get("blood_index") or 0),
        "fear_index": float(mood.get("fear_index") or 0),
        "bounty": bounty,
        "hunt_heat": float(bounty.get("hunt_heat") or 1.0),
    }


def format_echo_board(now: Optional[float] = None) -> str:
    t = _now(now)
    state = _load()
    _recompute_market_and_mood(state, t)
    _save(state)
    mod = echo_modifiers(t)
    lines = ["【望气·天下】玩家行为如何改写世界（规则回写）"]
    lines.append(
        f"天象：血气 {mod['blood_index']:.0f} · 恐慌 {mod['fear_index']:.0f}"
    )
    lines.append(market_panic_text(t))
    b = mod.get("bounty") or {}
    lines.append(
        f"除凶压力：血煞/重业玩家 {b.get('n_marked', 0)} · 池加成 +{b.get('pool_bonus', 0)} 功德 · 热度×{mod.get('hunt_heat', 1.0):.2f}"
    )
    hot = mod.get("hot_regions") or []
    lines.append(f"凶地（{len(hot)}）：")
    if not hot:
        lines.append("  · 天下暂无显凶之地")
    for loc, danger in hot:
        info = region_info(loc, t)
        lines.append(
            f"  · 【{loc}】危险 {danger:.0f} 近斩{info.get('kill_24h', 0)} "
            f"凶名 {info.get('top_actor_name') or '—'} 热度×{region_heat(loc, t):.2f}"
        )
    # 名气榜（回写）
    rows = sorted(
        (state.get("echoes") or {}).values(),
        key=lambda x: (-int(x.get("fame") or 0), -int(x.get("kill_total") or 0)),
    )[:8]
    lines.append("回写名气：")
    if not rows:
        lines.append("  · 暂无")
    for e in rows:
        labels = "、".join(e.get("labels") or []) or "—"
        lines.append(
            f"  · {e.get('name')} 名气{e.get('fame', 0)} 斩{e.get('kill_total', 0)} [{labels}]"
        )
    st = state.get("stats") or {}
    lines.append(
        f"累计：击杀回写 {st.get('kills_recorded', 0)} · 坊市变价 {st.get('market_shifts', 0)} · "
        f"惊动天道 {st.get('director_wakes', 0)}"
    )
    lines.append("边界：安全区/庇护规则不变；回写影响热度、恐慌价、除凶压力与叙事。")
    return "\n".join(lines)


def format_region_strip(viewer: Any = None, now: Optional[float] = None) -> str:
    """世情/look 用短条"""
    t = _now(now)
    loc = getattr(viewer, "location", "") or ""
    parts = []
    mod = echo_modifiers(t)
    if mod["market_panic"] >= 8:
        parts.append(f"坊市恐慌{mod['market_panic']:.0f}")
    if loc:
        d = float(region_info(loc, t).get("danger") or 0)
        if d >= 15:
            parts.append(f"{loc}危险{d:.0f}")
    if mod["blood_index"] >= 20:
        parts.append(f"血气{mod['blood_index']:.0f}")
    return "；".join(parts) or "世道尚稳"


def decay_echoes(now: Optional[float] = None) -> Dict[str, Any]:
    """tick：区域危险衰减、连斩窗清理、恐慌回落"""
    t = _now(now)
    state = _load()
    region = state.get("region") or {}
    changed = False
    for loc, r in list(region.items()):
        d = float(r.get("danger") or 0)
        k = float(r.get("kill_24h") or 0)
        new_d = max(0.0, d - ECHO_REGION_DECAY_PER_TICK)
        # kill_24h 不自动清零窗口太长；按危险衰减连带略降
        new_k = k
        if new_d < d:
            changed = True
        r["danger"] = new_d
        r["panic"] = max(0.0, float(r.get("panic") or 0) - ECHO_REGION_DECAY_PER_TICK * 0.6)
        if new_d < 5 and new_k:
            r["kill_24h"] = max(0, new_k - 0.2)
        if new_d < 2 and float(r.get("panic") or 0) < 2:
            # 可移除冷却区域
            if float(r.get("kill_24h") or 0) < 0.5:
                region.pop(loc, None)
                changed = True
                continue
        region[loc] = r
    if changed:
        state["region"] = region
    _recompute_market_and_mood(state, t)
    _save(state)
    return {"changed": changed, "market": state.get("market")}


def reset_for_tests() -> None:
    """清空回写态（测试用，保证坊市基准价）"""
    WorldStateRepository.set(
        _KEY,
        {
            "echoes": {},
            "region": {},
            "market": {"buy_mult": 1.0, "sell_mult": 1.0, "panic": 0.0, "reason": ""},
            "bounty": {"n_marked": 0, "pool_bonus": 0, "hunt_heat": 1.0},
            "mood": {"blood_index": 0.0, "fear_index": 0.0},
            "log": [],
            "stats": {
                "kills_recorded": 0,
                "region_updates": 0,
                "market_shifts": 0,
                "director_wakes": 0,
            },
        },
    )


def handle_echo_command(parts: List[str], character: Any = None, now: Optional[float] = None) -> Dict[str, Any]:
    sub = (parts[1].strip().lower() if len(parts) > 1 else "")
    if sub in ("己", "self", "我"):
        return {"ok": True, "text": player_echo_text(character, now)}
    return {"ok": True, "text": format_echo_board(now)}


def agenda_bias_from_echo(npc: Any, now: Optional[float] = None) -> Optional[Dict[str, str]]:
    """高危区域 NPC 议程偏置"""
    if npc is None:
        return None
    loc = getattr(npc, "location", "") or ""
    if not loc:
        return None
    info = region_info(loc, now)
    danger = float(info.get("danger") or 0)
    if danger >= 55:
        return {"agenda_type": "survive", "note": f"望气·{loc}凶险（{danger:.0f}），趋避"}
    if danger >= 30:
        return {
            "agenda_type": "patrol" if not _is_npc(npc) else "patrol",
            "note": f"望气·{loc}血气未散（{danger:.0f}）",
        }
    top = info.get("top_actor_name") or ""
    if top and top != getattr(npc, "name", ""):
        try:
            from core.npc_mind import attitude_toward

            # 仅当知道凶手 id
            aid = info.get("top_actor") or ""
            if aid:
                att = attitude_toward(npc, aid)
                if int(att.get("value") or 0) <= -40:
                    return {"agenda_type": "revenge", "note": f"望气·忌惮/仇视【{top}】"}
        except Exception:
            pass
    return None
