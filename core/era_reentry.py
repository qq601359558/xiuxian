"""
M5 纪元回流：传说/大劫史笔 → 导师提案权重与世界记忆

- 从 legends.tags 聚合 bias
- 大劫结算快照进 era_legacy，供下一纪导演引用
- 本地/AI 导师按 bias 提高对应指令类型优先级
规则：bias 只影响「提什么」，效果仍过 admit 门禁。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from config import DIRECTOR_TYPES, SEASON_WARN_DAYS, SECRET_REALMS, WORLD_LOCATIONS
from storage.db import ChronicleRepository, WorldStateRepository
from core.world_channel import WorldChannel

_KEY = "era_legacy"

# legend tag → director type 加权（仅明确类型标签；通用 world_arc 不硬推 omen）
TAG_TO_TYPE = {
    "blood_feud": "blood_tide",
    "blood_tide": "blood_tide",
    "sect_crisis": "sect_tension",
    "realm_storm": "secret_realm_pressure",
    "calamity_arc": "calamity_forecast",
    "omen_arc": "omen",
    "apocalypse": "calamity_forecast",
    "calamity": "calamity_forecast",
    "answered": "omen",
    "player": "omen",
    "highlight": "omen",
    "faction": "sect_tension",
    "siege": "blood_tide",
    "hunt": "blood_tide",
}

TYPE_CN = {
    "blood_tide": "血煞潮",
    "sect_tension": "宗门紧张",
    "secret_realm_pressure": "秘境压力",
    "calamity_forecast": "大劫预兆",
    "omen": "机缘预兆",
    "faction_order": "宗门令",
    "sect_siege": "宗门围剿",
}


def _now(now: Optional[float] = None) -> float:
    return now if now is not None else time.time()


def _load() -> Dict[str, Any]:
    try:
        data = WorldStateRepository.get(_KEY) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("current_season", 0)
    data.setdefault("completed_eras", [])
    data.setdefault("active_bias", {})
    data.setdefault("anchors", [])
    data.setdefault("last_reentry_ts", 0.0)
    data.setdefault("last_apocalypse_season", 0)
    data.setdefault("cited_count", 0)
    data.setdefault("log", [])
    return data


def _save(state: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, state)
    except Exception:
        pass


def _log(state: Dict[str, Any], line: str, limit: int = 30) -> None:
    rows = list(state.get("log") or [])
    rows.append(line[:160])
    state["log"] = rows[-limit:]


def legend_tags_to_bias(tags: List[str], weight: int = 1) -> Dict[str, float]:
    bias: Dict[str, float] = {}
    w = max(1, int(weight or 1))
    for tag in tags or []:
        key = str(tag or "").lower()
        dt = TAG_TO_TYPE.get(key)
        if dt and dt in DIRECTOR_TYPES:
            bias[dt] = float(bias.get(dt) or 0) + float(w)
    return bias


def compute_legend_bias(season: Optional[int] = None, limit: int = 24, now: Optional[float] = None) -> Dict[str, float]:
    """按传说库聚合导师类型权重"""
    try:
        from core.legends import list_legends

        rows = list_legends(season=season, limit=limit)
    except Exception:
        rows = []
    total: Dict[str, float] = {}
    for r in rows:
        b = legend_tags_to_bias(list(r.tags or []), int(r.weight or 1))
        for k, v in b.items():
            total[k] = float(total.get(k) or 0) + v
    # 大劫传说只轻推 calamity（真正出现仍要窗口门禁）
    if "calamity_forecast" in total:
        total["calamity_forecast"] = min(float(total["calamity_forecast"]), 3.0)
    return total


def extract_anchors(limit: int = 6) -> List[str]:
    """从传说文本提取地点锚点，供提案 location 偏好"""
    try:
        from core.legends import list_legends

        rows = list_legends(limit=20)
    except Exception:
        rows = []
    anchors: List[str] = []
    vocab = list(WORLD_LOCATIONS.keys()) + list(SECRET_REALMS.keys())
    for r in rows:
        blob = f"{r.title} {r.text}"
        for name in vocab:
            if name and name in blob and name not in anchors:
                anchors.append(name)
        if len(anchors) >= limit:
            break
    return anchors[:limit]


def rebuild_active_bias(now: Optional[float] = None, season: Optional[int] = None) -> Dict[str, Any]:
    """综合当前传说 + 已完结纪元快照 → active_bias"""
    t = _now(now)
    state = _load()
    live = compute_legend_bias(season=None, now=t)
    past: Dict[str, float] = {}
    for era in (state.get("completed_eras") or [])[-3:]:
        for k, v in (era.get("bias") or {}).items():
            past[k] = float(past.get(k) or 0) + float(v) * 0.85
    merged: Dict[str, float] = {}
    for src in (live, past):
        for k, v in src.items():
            if k not in DIRECTOR_TYPES:
                continue
            merged[k] = float(merged.get(k) or 0) + float(v)
    state["active_bias"] = {k: round(v, 3) for k, v in merged.items()}
    state["anchors"] = extract_anchors()
    state["last_reentry_ts"] = t
    try:
        from core.season import season_info

        state["current_season"] = int(season_info(t).get("season_number") or 0)
    except Exception:
        pass
    _save(state)
    return state


def on_apocalypse_settle(ended_season: int, now: Optional[float] = None) -> Dict[str, Any]:
    """大劫结算后的纪元回流：快照本纪传说 → 为下一纪 bias 预热"""
    t = _now(now)
    ended = int(ended_season or 0)
    state = _load()
    if int(state.get("last_apocalypse_season") or 0) == ended and ended:
        return {"ok": False, "reason": "already_snapshotted", "state": state}
    bias = compute_legend_bias(season=ended if ended else None, now=t)
    # 若本纪传说稀少，退回全库
    if not bias:
        bias = compute_legend_bias(season=None, now=t)
    try:
        from core.legends import list_legends

        legs = list_legends(season=ended if ended else None, limit=8) or list_legends(limit=8)
    except Exception:
        legs = []
    top = [
        {
            "title": x.title,
            "text": x.text[:80],
            "tags": list(x.tags or []),
            "weight": int(x.weight or 1),
            "season": int(x.season or 0),
        }
        for x in legs
    ]
    anchors = extract_anchors()
    era_rec = {
        "season": ended,
        "ended_at": t,
        "bias": bias,
        "legend_tags_sample": top,
        "anchors": anchors,
        "note": f"第{ended}纪元史笔回流",
    }
    eras = list(state.get("completed_eras") or [])
    eras.append(era_rec)
    state["completed_eras"] = eras[-8:]
    state["last_apocalypse_season"] = ended
    state["last_reentry_ts"] = t
    _save(state)
    rebuild_active_bias(t)
    # 世界可见：回流声明
    try:
        line_bias = "、".join(f"{TYPE_CN.get(k, k)}+{v:.0f}" for k, v in sorted(bias.items(), key=lambda x: -x[1])[:4])
        WorldChannel.post(
            "era_reentry",
            f"【纪元回流】第 {ended} 纪元史笔已入天道记忆" + (f"；本界余势：{line_bias}" if line_bias else "。"),
            level="epic",
            actor="天道",
            skip_limit=True,
        )
        ChronicleRepository.record("纪元回流", "天道", f"第{ended}纪 bias={bias}")
    except Exception:
        pass
    state = _load()
    _log(state, f"{int(t)}|apocalypse_reentry|season={ended}|bias={bias}")
    _save(state)
    return {"ok": True, "era": era_rec, "active_bias": state.get("active_bias")}


def on_season_number_change(season_no: int, now: Optional[float] = None) -> bool:
    """纪元号变化但未走大劫指令时，仍重建 bias（防漏）"""
    t = _now(now)
    state = _load()
    cur = int(state.get("current_season") or 0)
    sn = int(season_no or 0)
    if sn and cur and sn != cur and sn > cur:
        rebuild_active_bias(t)
        return True
    if sn and not cur:
        state["current_season"] = sn
        _save(state)
        rebuild_active_bias(t)
    return False


def active_bias(now: Optional[float] = None) -> Dict[str, float]:
    state = _load()
    bias = dict(state.get("active_bias") or {})
    if not bias:
        rebuild_active_bias(now)
        bias = dict((_load().get("active_bias") or {}))
    return {k: float(v) for k, v in bias.items() if k in DIRECTOR_TYPES}


def preferred_directive_types(now: Optional[float] = None, top: int = 3) -> List[str]:
    bias = active_bias(now)
    if not bias:
        return []
    return [k for k, _v in sorted(bias.items(), key=lambda x: -x[1])[:top] if float(bias.get(k) or 0) > 0]


def bias_score(dtype: str, now: Optional[float] = None) -> float:
    return float(active_bias(now).get(dtype) or 0)


def seed_local_directives(now: Optional[float] = None) -> List[Dict[str, Any]]:
    """无 AI / 多样性补齐：史笔 bias + 当前世界态势 → 候选提案原料"""
    t = _now(now)
    rebuild_active_bias(t)
    bias = active_bias(t)
    anchors = list((_load().get("anchors") or []))
    seeds: List[Dict[str, Any]] = []
    seen_types = set()

    def _add(dtype: str, title: str, narrative: str, location: str = "", effects: Optional[Dict[str, Any]] = None) -> None:
        if dtype in seen_types:
            return
        seen_types.add(dtype)
        seeds.append(
            {
                "type": dtype,
                "title": title[:40],
                "narrative": narrative[:160],
                "location": location,
                "effects": effects or {"whisper": "天道"},
                "priority": 2,
            }
        )

    loc = ""
    for a in anchors:
        if a in WORLD_LOCATIONS:
            loc = a
            break
    rid = ""
    for a in anchors:
        if a in SECRET_REALMS:
            rid = a
            break
    # —— 世界态势驱动（优先，打破 omen 单一）——
    try:
        from core.faction import faction_modifiers, active_sieges
        from core.player_echo import echo_modifiers
        from core.secret_realm import realm_status

        fm = faction_modifiers(t)
        sieges = active_sieges(t)
        em = echo_modifiers(t)
        hot = em.get("hot_regions") or []
        if sieges:
            s0 = sieges[0]
            _add(
                "blood_tide",
                f"围剿余波·{s0.get('target_name') or '凶人'}",
                f"【{s0.get('sect')}】围剿未歇，{s0.get('location') or '坊市'}一带血气浮动，除凶与避祸之议再起。",
                str(s0.get("location") or ""),
                {
                    "location": str(s0.get("location") or ""),
                    "goal_title": "留意围剿风声",
                    "goal_detail": f"宗门围剿【{s0.get('target_name')}】进行中，/势力 /除凶 可览。",
                },
            )
        if fm.get("hostile_pairs"):
            a, b = fm["hostile_pairs"][0]
            _add(
                "sect_tension",
                f"敌门暗涌·{a}×{b}",
                f"【{a}】与【{b}】势同水火，门下在坊市与野外屡有龃龉，天道静观其变。",
                "",
                {"sect_a": a, "sect_b": b, "whisper": "敌对"},
            )
        open_realms = [r for r in realm_status(t) if r.get("is_open")]
        if open_realms:
            rn = str(open_realms[0].get("name") or "")
            _add(
                "secret_realm_pressure",
                f"秘境躁动·{rn}",
                f"【{rn}】禁制波动，附近灵气紊乱，机缘与杀劫并存。",
                str(open_realms[0].get("location") or ""),
                {"realm_id": rn, "force_open": False},
            )
        if hot:
            hloc = str(hot[0][0])
            _add(
                "blood_tide",
                f"凶地血气·{hloc}",
                f"【{hloc}】近来血气不散，修士过境多有戒惧。",
                hloc,
                {"location": hloc, "whisper": "望气凶地"},
            )
        if float(em.get("market_panic") or 0) >= 30:
            _add(
                "omen",
                "坊市惶惶",
                "坊市人心浮动，货价上扬，或有机缘藏于乱局，亦有趁火打劫者。",
                "青云坊市客栈",
                {
                    "goal_title": "乱市观风",
                    "goal_detail": "坊市恐慌中留意 /望气 /坊市，谨防凶险。",
                    "whisper": "恐慌",
                },
            )
        if fm.get("n_open_missions"):
            # 有宗门令时倾向宗门令提案
            _add(
                "faction_order",
                "宗门催令",
                "各宗门令频发，弟子宜 /宗门令 查看本门差事，为宗门立功。",
                "",
                {"sect": "青云宗", "order_kind": "patrol", "whisper": "宗门令"},
            )
    except Exception:
        pass
    # —— 史笔 bias 补齐（不覆盖已有类型）——
    ranked = sorted(bias.items(), key=lambda x: -x[1])
    for dtype, score in ranked[:3]:
        if float(score) < 0.5:
            continue
        title = f"史笔余势·{TYPE_CN.get(dtype, dtype)}"
        narrative = f"上纪传说犹在坊间流传，天道记忆未冷，【{TYPE_CN.get(dtype, dtype)}】之势或再起。"
        effects: Dict[str, Any] = {"whisper": "纪元回流"}
        dloc = loc
        if dtype == "secret_realm_pressure" and rid:
            effects["realm_id"] = rid
            effects["force_open"] = False
            dloc = str(SECRET_REALMS.get(rid, {}).get("location") or loc)
        if dtype == "blood_tide" and loc:
            effects["location"] = loc
        if dtype == "omen":
            effects["goal_title"] = "循史笔而行"
            effects["goal_detail"] = narrative[:80]
        _add(dtype, title, narrative, dloc, effects)
    return seeds[:6]


def variety_seeds_from_world(now: Optional[float] = None) -> List[Dict[str, Any]]:
    """供导师多样性补齐：非 omen 的世界态势种子"""
    seeds = seed_local_directives(now=now)
    return [s for s in seeds if s.get("type") != "omen"]


def reorder_by_bias(rows: List[Dict[str, Any]], now: Optional[float] = None) -> List[Dict[str, Any]]:
    """AI 提案排序：史笔 bias + 世界多样性（非单一 omen）"""
    if not rows:
        return rows
    bias = active_bias(now)
    # 世界态势也加入排序键
    try:
        vs = {s.get("type") for s in variety_seeds_from_world(now)}
    except Exception:
        vs = set()

    def _key(d: Dict[str, Any]) -> Tuple[float, float, float]:
        dt = str(d.get("type") or "")
        variety = 2.0 if dt in vs else 0.0
        omen_pen = -0.5 if dt == "omen" else 0.0
        return (-variety - float(bias.get(dt) or 0) + omen_pen, -float(d.get("priority") or 1), 0.0)

    return sorted(rows, key=_key)


def format_era_board(now: Optional[float] = None) -> str:
    t = _now(now)
    rebuild_active_bias(t)
    state = _load()
    bias = active_bias(t)
    try:
        from core.season import season_info

        info = season_info(t)
        cur = int(info.get("season_number") or 0)
    except Exception:
        cur = int(state.get("current_season") or 0)
    lines = ["【纪元回流】史笔 → 天道记忆 → 导师提案权重"]
    lines.append(f"当前纪元：第 {cur} 纪 · 上次回流：{_fmt(state.get('last_reentry_ts'))}")
    if bias:
        parts = [
            f"{TYPE_CN.get(k, k)} {v:.1f}"
            for k, v in sorted(bias.items(), key=lambda x: -x[1])
            if v > 0
        ]
        lines.append("活跃权重：" + "；".join(parts[:6]))
    else:
        lines.append("活跃权重：暂无（传说未积）")
    anchors = state.get("anchors") or []
    if anchors:
        lines.append("史笔地点锚：" + "、".join(anchors[:6]))
    eras = list(state.get("completed_eras") or [])[-3:]
    if eras:
        lines.append("已完结纪元：")
        for e in reversed(eras):
            b = e.get("bias") or {}
            top = "、".join(f"{TYPE_CN.get(k,k)}+{v:.0f}" for k, v in sorted(b.items(), key=lambda x: -x[1])[:3]) or "—"
            lines.append(f"  · 第{e.get('season')}纪 → {top}")
    try:
        from core.legends import list_legends

        legs = list_legends(limit=4)
        lines.append("近传说：")
        for x in legs[:4]:
            tags = ",".join(x.tags[:3]) if x.tags else ""
            lines.append(f"  · {x.title}（第{x.season}纪 {tags}）")
    except Exception:
        pass
    lines.append(f"引用累计：{state.get('cited_count', 0)} · 边界：bias 只影响提案优先级，不绕过门禁。")
    return "\n".join(lines)


def _fmt(ts: Any) -> str:
    try:
        ts = float(ts or 0)
        if ts <= 0:
            return "从未"
        return time.strftime("%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "—"


def note_citation(reason: str = "director") -> None:
    state = _load()
    state["cited_count"] = int(state.get("cited_count") or 0) + 1
    _log(state, f"{int(_now())}|cite|{reason[:40]}")
    _save(state)


def tick(now: Optional[float] = None) -> Dict[str, Any]:
    """后台：纪元号变化时重建 bias"""
    t = _now(now)
    try:
        from core.season import season_info

        sn = int(season_info(t).get("season_number") or 0)
    except Exception:
        sn = 0
    changed = on_season_number_change(sn, t)
    if not (_load().get("active_bias") or {}):
        rebuild_active_bias(t)
    return {"season": sn, "changed": changed, "bias": active_bias(t)}


def handle_era_command(parts: List[str], now: Optional[float] = None) -> Dict[str, Any]:
    sub = (parts[1].strip().lower() if len(parts) > 1 else "")
    if sub in ("重建", "rebuild", "刷新"):
        st = rebuild_active_bias(now)
        return {"ok": True, "text": format_era_board(now), "bias": st.get("active_bias")}
    return {"ok": True, "text": format_era_board(now)}
