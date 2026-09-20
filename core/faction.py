"""
M3 势力操盘：宗门关系状态机 · 宗门令 · 宗门围剿 · 敌对修正

原则：AI/导师只提案；关系分、任务奖励、围剿名单由规则落账。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from config import (
    FACTION_DECAY_PER_TICK,
    FACTION_HOSTILE_LOC_HEAT,
    FACTION_HOSTILE_POWER_BONUS,
    FACTION_MISSION_MAX_OPEN,
    FACTION_MISSION_REWARD,
    FACTION_MISSION_TTL_H,
    FACTION_SCORE_ALLIED,
    FACTION_SCORE_HOSTILE,
    FACTION_SCORE_TENSE,
    FACTION_SCORE_WARM,
    FACTION_SIEGE_NPC_MAX,
    FACTION_SIEGE_TTL_H,
    SECTS_CONFIG,
    WORLD_LOCATIONS,
)
from storage.db import CharacterRepository, ChronicleRepository, WorldStateRepository
from core.models import CharacterStatus
from core.world_channel import WorldChannel
from ai.audit import write_audit

_KEY = "faction_state"
_ORDER_KINDS = frozenset({"patrol", "hunt", "boycott", "siege"})


def _now(now: Optional[float] = None) -> float:
    return now if now is not None else time.time()


def _pair_key(a: str, b: str) -> str:
    return "|".join(sorted([a, b]))


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
    data.setdefault("relations", {})
    data.setdefault("missions", [])
    data.setdefault("sieges", [])
    data.setdefault("log", [])
    data.setdefault("stats", {"missions_open": 0, "missions_done": 0, "sieges": 0, "shifts": 0})
    if not isinstance(data.get("stats"), dict):
        data["stats"] = {"missions_open": 0, "missions_done": 0, "sieges": 0, "shifts": 0}
    return data


def _save(state: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, state)
    except Exception:
        pass


def _audit(rec: Dict[str, Any]) -> None:
    try:
        write_audit({"source": "ai.faction", **rec})
    except Exception:
        pass


def _log(state: Dict[str, Any], line: str, limit: int = 40) -> None:
    rows = list(state.get("log") or [])
    rows.append(line[:160])
    state["log"] = rows[-limit:]


def status_from_score(score: float) -> str:
    if score <= FACTION_SCORE_HOSTILE:
        return "hostile"
    if score <= FACTION_SCORE_TENSE:
        return "tense"
    if score >= FACTION_SCORE_ALLIED:
        return "allied"
    if score >= FACTION_SCORE_WARM:
        return "warm"
    return "neutral"


STATUS_CN = {
    "hostile": "敌对",
    "tense": "紧张",
    "neutral": "中立",
    "warm": "亲近",
    "allied": "结盟",
}

# 初始关系（规则默认，可被导演/弧改写）
DEFAULT_RELATIONS = {
    ("青云宗", "九幽天魔宗"): -55,
    ("青云宗", "万剑仙门"): -5,
    ("万剑仙门", "九幽天魔宗"): -25,
    ("四海散修商会", "青云宗"): 15,
    ("四海散修商会", "万剑仙门"): 10,
    ("四海散修商会", "九幽天魔宗"): -5,
}


def ensure_defaults(now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    state = _load()
    rels = state.get("relations") or {}
    changed = False
    for (a, b), sc in DEFAULT_RELATIONS.items():
        k = _pair_key(a, b)
        if k not in rels:
            rels[k] = {
                "a": a,
                "b": b,
                "score": float(sc),
                "status": status_from_score(sc),
                "updated_at": t,
                "note": "初始格局",
            }
            changed = True
    state["relations"] = rels
    if changed:
        _save(state)
    return state


def get_relation(a: str, b: str, now: Optional[float] = None) -> Dict[str, Any]:
    if not a or not b or a == b:
        return {"a": a, "b": b, "score": 100.0, "status": "allied", "note": "同门"}
    ensure_defaults(now)
    state = _load()
    k = _pair_key(a, b)
    rel = (state.get("relations") or {}).get(k)
    if rel:
        return dict(rel)
    return {
        "a": a,
        "b": b,
        "score": 0.0,
        "status": "neutral",
        "note": "素无往来",
        "updated_at": _now(now),
    }


def shift_relation(
    a: str,
    b: str,
    delta: float,
    *,
    note: str = "",
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """规则钳制的关系分变动"""
    if not a or not b or a == b:
        return {"ok": False, "error": "无效宗门对"}
    t = _now(now)
    ensure_defaults(t)
    state = _load()
    k = _pair_key(a, b)
    rels = state.get("relations") or {}
    rel = rels.get(k) or {
        "a": min(a, b) if a != b else a,
        "b": max(a, b) if a != b else b,
        "score": 0.0,
        "status": "neutral",
        "note": "",
        "updated_at": t,
    }
    # 规范 a/b 为 pair key 顺序
    ka, kb = k.split("|", 1)
    rel["a"] = ka
    rel["b"] = kb
    old = float(rel.get("score") or 0)
    new = max(-100.0, min(100.0, old + float(delta)))
    rel["score"] = new
    rel["status"] = status_from_score(new)
    rel["updated_at"] = t
    if note:
        rel["note"] = note[:80]
    rels[k] = rel
    state["relations"] = rels
    state["stats"]["shifts"] = int(state["stats"].get("shifts") or 0) + 1
    _log(state, f"{int(t)}|shift|{ka}×{kb}|{old:.0f}→{new:.0f}|{note[:40]}")
    _save(state)
    try:
        ChronicleRepository.record("势力", "关系", f"{ka}×{kb}：{STATUS_CN.get(rel['status'], rel['status'])}（{old:.0f}→{new:.0f}）")
    except Exception:
        pass
    _audit({"event": "shift_relation", "pair": k, "old": old, "new": new, "note": note[:60]})
    return {"ok": True, "relation": rel, "old": old, "new": new}


def is_hostile(a: str, b: str, now: Optional[float] = None) -> bool:
    return get_relation(a, b, now).get("status") == "hostile"


def is_tense_or_worse(a: str, b: str, now: Optional[float] = None) -> bool:
    return get_relation(a, b, now).get("status") in ("hostile", "tense")


def hostile_power_bonus(attacker_sect: str, defender_sect: str, now: Optional[float] = None) -> float:
    """敌对宗门交手：进攻方战力加成（规则）"""
    if not attacker_sect or not defender_sect or attacker_sect == defender_sect:
        return 1.0
    st = get_relation(attacker_sect, defender_sect, now).get("status")
    if st == "hostile":
        return 1.0 + FACTION_HOSTILE_POWER_BONUS
    if st == "tense":
        return 1.0 + FACTION_HOSTILE_POWER_BONUS * 0.5
    return 1.0


def location_faction_heat(location: str, viewer_sect: str = "", now: Optional[float] = None) -> float:
    """敌对宗门总坛/洞府：外门进入时危险热度上浮"""
    if not location or not viewer_sect:
        return 1.0
    for sname, cfg in SECTS_CONFIG.items():
        if sname == viewer_sect:
            continue
        hqs = {cfg.get("headquarters"), cfg.get("cave_location")}
        if location not in hqs:
            continue
        if is_hostile(viewer_sect, sname, now):
            return FACTION_HOSTILE_LOC_HEAT
        if is_tense_or_worse(viewer_sect, sname, now):
            return 1.0 + (FACTION_HOSTILE_LOC_HEAT - 1.0) * 0.5
    return 1.0


def decay_relations(now: Optional[float] = None) -> int:
    """向中立缓慢回归，防永久锁死敌对"""
    t = _now(now)
    ensure_defaults(t)
    state = _load()
    n = 0
    rels = state.get("relations") or {}
    for k, rel in rels.items():
        sc = float(rel.get("score") or 0)
        if abs(sc) < 0.5:
            continue
        step = FACTION_DECAY_PER_TICK if sc < 0 else -FACTION_DECAY_PER_TICK
        new = max(-100.0, min(100.0, sc + step))
        # 不跨过 0 再来回抖
        if sc < 0 < new:
            new = min(new, 0.0)
        if sc > 0 > new:
            new = max(new, 0.0)
        if abs(new - sc) < 0.05:
            continue
        rel["score"] = new
        rel["status"] = status_from_score(new)
        rel["updated_at"] = t
        n += 1
    if n:
        state["relations"] = rels
        _save(state)
    return n


# ---------------- 宗门令（任务） ----------------
def _purge_missions(state: Dict[str, Any], now: float) -> None:
    missions = []
    for m in state.get("missions") or []:
        if m.get("status") == "open" and float(m.get("expires_at") or 0) < now:
            m["status"] = "expired"
        if m.get("status") in ("open", "done", "expired"):
            if m.get("status") != "open" and float(m.get("created_at") or 0) < now - 7 * 86400:
                continue
        missions.append(m)
    state["missions"] = missions[-80:]


def open_mission(
    sect: str,
    kind: str,
    *,
    title: str = "",
    detail: str = "",
    target_sect: str = "",
    target_name: str = "",
    location: str = "",
    reward_contrib: int = 0,
    source: str = "rule",
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    if sect not in SECTS_CONFIG or kind not in _ORDER_KINDS:
        return None
    t = _now(now)
    ensure_defaults(t)
    state = _load()
    _purge_missions(state, t)
    open_n = sum(1 for m in state.get("missions") if m.get("status") == "open" and m.get("sect") == sect)
    if open_n >= FACTION_MISSION_MAX_OPEN:
        return None
    # 同类型同宗同目标去重
    for m in state.get("missions") or []:
        if (
            m.get("status") == "open"
            and m.get("sect") == sect
            and m.get("kind") == kind
            and m.get("target_name") == target_name
            and m.get("target_sect") == target_sect
            and m.get("location") == location
        ):
            return None
    reward = int(reward_contrib or FACTION_MISSION_REWARD.get(kind, 5))
    if not title:
        title = {
            "patrol": f"巡守{location or SECTS_CONFIG[sect].get('headquarters') or '山门'}",
            "hunt": f"缉凶{target_name or target_sect}",
            "boycott": f"抵制{target_sect or '敌对势力'}",
            "siege": f"宗门围剿{target_name or '血煞'}",
        }.get(kind, "宗门令")
    if not detail:
        detail = {
            "patrol": "宗门示警，弟子宜巡守山门/洞府一带。",
            "hunt": "缉拿血煞缠身或敌对门下凶徒。",
            "boycott": "减少与敌对势力往来，坊市亦当谨慎。",
            "siege": "号令门下，共诛天道所指凶人。",
        }.get(kind, "遵宗门之令。")
    if location and location not in WORLD_LOCATIONS and location not in SECTS_CONFIG.get(sect, {}).values():
        # 允许 HQ 名
        if location not in (SECTS_CONFIG[s].get("headquarters") for s in SECTS_CONFIG):
            if location not in WORLD_LOCATIONS:
                location = ""
    mid = f"f_{uuid.uuid4().hex[:8]}"
    mission = {
        "id": mid,
        "sect": sect,
        "kind": kind,
        "title": title[:40],
        "detail": detail[:160],
        "target_sect": target_sect,
        "target_name": target_name,
        "location": location,
        "reward_contrib": reward,
        "status": "open",
        "source": source,
        "created_at": t,
        "expires_at": t + FACTION_MISSION_TTL_H * 3600,
        "accepted_by": [],
    }
    state.setdefault("missions", []).append(mission)
    state["stats"]["missions_open"] = int(state["stats"].get("missions_open") or 0) + 1
    _log(state, f"{int(t)}|mission|{sect}|{kind}|{title[:30]}")
    _save(state)
    try:
        WorldChannel.post(
            "faction",
            f"【宗门令·{sect}】{title}（贡献+{reward}）",
            level="major",
            actor=sect,
            location=location or "",
            skip_limit=True,
        )
    except Exception:
        pass
    return mission


def list_missions(sect: str = "", status: str = "open", now: Optional[float] = None) -> List[Dict[str, Any]]:
    t = _now(now)
    ensure_defaults(t)
    state = _load()
    _purge_missions(state, t)
    _save(state)
    out = []
    for m in state.get("missions") or []:
        if sect and m.get("sect") != sect:
            continue
        if status and m.get("status") != status:
            continue
        out.append(m)
    return out


def accept_mission(character: Any, mission_id: str, now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    if character is None or not getattr(character, "sect", None):
        return {"success": False, "message": "须有宗籍方可接宗门令。/拜入 或 /宗门"}
    state = _load()
    _purge_missions(state, t)
    target = None
    for m in state.get("missions") or []:
        if m.get("id") == mission_id:
            target = m
            break
    if not target or target.get("status") != "open":
        return {"success": False, "message": "无此宗门令或已失效。/宗门令 查看。"}
    if target.get("sect") != character.sect:
        return {"success": False, "message": f"此令出自【{target.get('sect')}】，非你宗门。"}
    acc = list(target.get("accepted_by") or [])
    if character.id not in acc:
        acc.append(character.id)
        target["accepted_by"] = acc[-20:]
    _save(state)
    try:
        from core.sect_contrib import sync_ring

        sync_ring(character, "patrol" if target.get("kind") == "patrol" else "hunt")
    except Exception:
        pass
    return {
        "success": True,
        "mission": target,
        "message": (
            f"【接宗门令】{target.get('title')}\n{target.get('detail')}\n"
            f"完成后 /交宗门令 {target.get('id')} 领贡献 +{target.get('reward_contrib')}"
        ),
    }


def complete_mission(character: Any, mission_id: str, now: Optional[float] = None) -> Dict[str, Any]:
    """规则验收：按 kind 检查可观测条件"""
    t = _now(now)
    if character is None:
        return {"success": False, "message": "无角色"}
    state = _load()
    _purge_missions(state, t)
    m = None
    for row in state.get("missions") or []:
        if row.get("id") == mission_id:
            m = row
            break
    if not m or m.get("status") != "open":
        return {"success": False, "message": "宗门令不存在或已结束。"}
    if m.get("sect") != character.sect:
        return {"success": False, "message": "非本宗之令。"}
    kind = m.get("kind")
    ok = False
    why = ""
    if kind == "patrol":
        loc_need = m.get("location") or (SECTS_CONFIG.get(character.sect) or {}).get("headquarters")
        if not loc_need or character.location == loc_need:
            ok = True
            why = f"已至 {character.location}"
        else:
            why = f"须亲至【{loc_need}】（当前 {character.location}）"
    elif kind == "hunt":
        tn = m.get("target_name")
        if tn:
            from core.hunt import my_target

            tgt = my_target(character)
            if tgt and tgt.name == tn:
                ok = True
                why = f"已接令缉拿【{tn}】"
            else:
                # 允许：目标已死
                dead = False
                try:
                    from storage.db import CharacterRepository as CR

                    obj = CR.find_alive_by_name(tn)
                    if obj is None:
                        dead = True
                except Exception:
                    dead = False
                if dead:
                    ok = True
                    why = f"【{tn}】已不在人世"
                else:
                    why = f"须先 /接除凶 {tn} 或待其伏诛"
        else:
            from core.hunt import my_target

            if my_target(character):
                ok = True
                why = "已接任意除凶令"
            else:
                why = "须接任一除凶令 (/除凶)"
    elif kind == "boycott":
        # 轻量验收：在坊市/安全区自证「未深入敌坛」
        hq_enemy = ""
        ts = m.get("target_sect") or ""
        if ts in SECTS_CONFIG:
            hq_enemy = SECTS_CONFIG[ts].get("headquarters") or ""
        if not hq_enemy or character.location != hq_enemy:
            ok = True
            why = "未驻敌坛，已遵抵制之令"
        else:
            why = f"抵制期间不宜久留敌坛【{hq_enemy}】"
    elif kind == "siege":
        from core.faction import siege_active_on  # noqa: F401 — defined below; use local import cycle-safe

        tn = m.get("target_name")
        # 号令类：接了对应除凶或目标死亡
        if tn:
            from core.hunt import my_target

            tgt = my_target(character)
            if tgt and tgt.name == tn:
                ok = True
                why = f"已响应围剿令缉【{tn}】"
            else:
                try:
                    from storage.db import CharacterRepository as CR

                    if CR.find_alive_by_name(tn) is None:
                        ok = True
                        why = f"【{tn}】已伏诛"
                    else:
                        why = f"请 /接除凶 {tn} 响应宗门围剿"
                except Exception:
                    why = "请接除凶响应围剿"
        else:
            why = "围剿令缺少目标"
    if not ok:
        return {"success": False, "message": f"【宗门令未毕】{why}"}
    m["status"] = "done"
    m["done_at"] = t
    m["done_by"] = character.id
    reward = int(m.get("reward_contrib") or 0)
    character.sect_contribution = int(character.sect_contribution or 0) + reward
    try:
        CharacterRepository.save(character)
    except Exception:
        pass
    state["stats"]["missions_done"] = int(state["stats"].get("missions_done") or 0) + 1
    _log(state, f"{int(t)}|mission_done|{m.get('sect')}|{m.get('kind')}|{character.name}")
    _save(state)
    try:
        ChronicleRepository.record("势力", character.sect, f"{character.name} 完成宗门令《{m.get('title')}》贡献+{reward}")
    except Exception:
        pass
    return {
        "success": True,
        "message": f"【宗门令毕】{m.get('title')} — {why}。贡献 +{reward}，现 {character.sect_contribution}。",
        "mission": m,
    }


# ---------------- 宗门围剿 ----------------
def open_siege(
    sect: str,
    target: Any,
    *,
    reason: str = "",
    source: str = "rule",
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """宗门号令围剿血煞目标：写入 siege + 为门下 NPC 自动接除凶令"""
    t = _now(now)
    if sect not in SECTS_CONFIG or target is None:
        return {"success": False, "message": "无效围剿"}
    from core.hunt import is_marked

    if not is_marked(target):
        return {"success": False, "message": f"【{target.name}】未染血煞，宗门不可妄动。"}
    ensure_defaults(t)
    state = _load()
    # 去重活跃
    for s in state.get("sieges") or []:
        if s.get("status") == "active" and s.get("target_id") == target.id and s.get("sect") == sect:
            return {"success": False, "message": f"【{sect}】已在围剿【{target.name}】。"}
    sid = f"s_{uuid.uuid4().hex[:8]}"
    siege = {
        "id": sid,
        "sect": sect,
        "target_id": target.id,
        "target_name": target.name,
        "location": target.location,
        "reason": reason[:80] or "血煞盈野，天道借我宗之手",
        "announced_at": t,
        "expires_at": t + FACTION_SIEGE_TTL_H * 3600,
        "status": "active",
        "source": source,
        "npc_joined": [],
    }
    # NPC 自动接令
    joined = []
    try:
        from core.hunt import _load as hunt_load, _save as hunt_save, _purge_expired

        hunts = _purge_expired(t)
        members = []
        for c in CharacterRepository.list_all_alive():
            if c.status == CharacterStatus.DEAD:
                continue
            if c.sect != sect:
                continue
            if _is_npc(c):
                members.append(c)
            if len(members) >= FACTION_SIEGE_NPC_MAX:
                break
        for m in members:
            if m.id == target.id:
                continue
            hunts[m.id] = {
                "target_id": target.id,
                "expires_at": t + FACTION_SIEGE_TTL_H * 3600,
                "target_name": target.name,
            }
            joined.append(m.name)
        hunt_save(hunts)
    except Exception:
        joined = []
    siege["npc_joined"] = joined
    state.setdefault("sieges", []).append(siege)
    state["stats"]["sieges"] = int(state["stats"].get("sieges") or 0) + 1
    # 同步开一条宗门令
    open_mission(
        sect,
        "siege",
        title=f"围剿{target.name}",
        detail=f"{siege['reason']}。门下可 /接除凶 {target.name}。",
        target_name=target.name,
        location=target.location,
        reward_contrib=FACTION_MISSION_REWARD.get("siege", 25),
        source=source,
        now=t,
    )
    _log(state, f"{int(t)}|siege|{sect}|{target.name}|{source}")
    _save(state)
    try:
        WorldChannel.post(
            "faction_siege",
            f"【宗门围剿·{sect}】{siege['reason']} — 共诛【{target.name}】@ {target.location}。门下响应 {len(joined)} 人。",
            level="epic",
            actor=sect,
            location=target.location or "",
            skip_limit=True,
        )
        ChronicleRepository.record("势力", sect, f"围剿【{target.name}】：{siege['reason']}")
    except Exception:
        pass
    # 若目标是敌对宗门门下，关系再降
    tsect = getattr(target, "sect", "") or ""
    if tsect and tsect != sect and tsect in SECTS_CONFIG:
        shift_relation(sect, tsect, -10, note=f"围剿{target.name}", now=t)
    _audit({"event": "siege", "sect": sect, "target": target.name, "source": source})
    return {"success": True, "siege": siege, "message": f"【宗门围剿】{sect} 号令诛【{target.name}】，NPC 响应：{'、'.join(joined) or '暂无'}。"}


def purge_sieges(now: Optional[float] = None) -> None:
    t = _now(now)
    state = _load()
    changed = False
    for s in state.get("sieges") or []:
        if s.get("status") == "active" and float(s.get("expires_at") or 0) < t:
            s["status"] = "expired"
            changed = True
    if changed:
        _save(state)


def active_sieges(now: Optional[float] = None) -> List[Dict[str, Any]]:
    purge_sieges(now)
    state = _load()
    return [s for s in state.get("sieges") or [] if s.get("status") == "active"]


def siege_active_on(character: Any, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    if character is None:
        return None
    for s in active_sieges(now):
        if s.get("target_id") == character.id:
            return s
    return None


def agenda_bias_for_npc(npc: Any, now: Optional[float] = None) -> Optional[Dict[str, str]]:
    """势力态势 → NPC 议程偏置（优先于通用导演偏置时由调用方决定）"""
    if npc is None:
        return None
    t = _now(now)
    sect = getattr(npc, "sect", "") or ""
    loc = getattr(npc, "location", "") or ""
    if not sect:
        return None
    # 围剿目标
    for s in active_sieges(t):
        if s.get("sect") == sect:
            try:
                tgt = CharacterRepository.get_by_id(s.get("target_id"))
            except Exception:
                tgt = None
            if tgt and tgt.status != CharacterStatus.DEAD:
                return {
                    "agenda_type": "revenge",
                    "note": f"势力·宗门围剿【{s.get('target_name')}】",
                }
    # 所在地为敌对宗门总坛 → 巡守/结交打探
    for sname, cfg in SECTS_CONFIG.items():
        if sname == sect:
            continue
        if loc in (cfg.get("headquarters"), cfg.get("cave_location")):
            if is_hostile(sect, sname, t):
                return {
                    "agenda_type": "social" if "商会" in sect else "patrol",
                    "note": f"势力·敌境【{sname}】地界",
                }
            if is_tense_or_worse(sect, sname, t):
                return {"agenda_type": "patrol", "note": f"势力·紧张【{sname}】地界"}
    # 敌对宗门成员同图时偏寻仇
    if is_tense_or_worse:
        try:
            for c in CharacterRepository.list_all_alive():
                if c.id == npc.id or c.status == CharacterStatus.DEAD:
                    continue
                if c.sect and c.sect != sect and is_hostile(sect, c.sect, t) and c.location == loc:
                    return {
                        "agenda_type": "revenge" if npc.karma.sin_value >= 40 else "patrol",
                        "note": f"势力·同场敌门【{c.name}·{c.sect}】",
                    }
        except Exception:
            pass
    return None


# ---------------- 导师 / 弧 钩子 ----------------
def on_director_sect_tension(sect_a: str, sect_b: str, now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    if not sect_a or not sect_b or sect_a not in SECTS_CONFIG or sect_b not in SECTS_CONFIG:
        return {"ok": False}
    shift_relation(sect_a, sect_b, -12, note="天道导演·宗门紧张", now=t)
    # 可能下达抵制令
    if is_tense_or_worse(sect_a, sect_b, t):
        open_mission(sect_a, "boycott", target_sect=sect_b, source="director", now=t)
        open_mission(sect_b, "boycott", target_sect=sect_a, source="director", now=t)
    return {"ok": True}


def on_sect_crisis_climax(sect_a: str, sect_b: str, answered: bool, now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    if not sect_a or not sect_b:
        return {"ok": False}
    if answered:
        shift_relation(sect_a, sect_b, 8, note="世界弧决算·暂歇", now=t)
    else:
        shift_relation(sect_a, sect_b, -8, note="世界弧决算·暗流", now=t)
    # 敌对加深则可能围剿
    if is_hostile(sect_a, sect_b, t):
        # 选血煞或重业目标
        try:
            for c in CharacterRepository.list_all_alive():
                if c.status == CharacterStatus.DEAD:
                    continue
                from core.hunt import is_marked

                if is_marked(c) and c.sect in (sect_a, sect_b):
                    open_siege(
                        sect_a if c.sect == sect_b else sect_b,
                        c,
                        reason=f"世界弧决算后敌意沸腾，共诛【{c.name}】",
                        source="arc",
                        now=t,
                    )
                    break
        except Exception:
            pass
    return {"ok": True}


def faction_modifiers(now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    ensure_defaults(t)
    state = _load()
    purge_sieges(t)
    hostile = []
    tense = []
    for rel in (state.get("relations") or {}).values():
        st = rel.get("status")
        pair = (rel.get("a"), rel.get("b"))
        if st == "hostile":
            hostile.append(pair)
        elif st == "tense":
            tense.append(pair)
    sieges = active_sieges(t)
    return {
        "hostile_pairs": hostile,
        "tense_pairs": tense,
        "active_sieges": [
            {"sect": s.get("sect"), "target": s.get("target_name"), "loc": s.get("location")}
            for s in sieges
        ],
        "n_open_missions": sum(1 for m in list_missions(status="open", now=t)),
    }


def format_faction_board(viewer: Any = None, now: Optional[float] = None) -> str:
    t = _now(now)
    ensure_defaults(t)
    state = _load()
    purge_sieges(t)
    _purge_missions(state, t)
    lines = ["【天下势力】AI/导师提案 · 规则落账（关系分/令/围剿）"]
    lines.append("— 宗门关系 —")
    rels = sorted(
        (state.get("relations") or {}).values(),
        key=lambda x: float(x.get("score") or 0),
    )
    if not rels:
        lines.append("  · 暂无格局数据")
    for rel in rels:
        sc = float(rel.get("score") or 0)
        st = rel.get("status") or status_from_score(sc)
        lines.append(
            f"  · {rel.get('a')} × {rel.get('b')}：{STATUS_CN.get(st, st)}（{sc:.0f}）"
            f"{(' — ' + rel.get('note')) if rel.get('note') else ''}"
        )
    missions = list_missions(status="open", now=t)
    lines.append(f"— 宗门令（{len(missions)}）—")
    if not missions:
        lines.append("  · 暂无进行中的宗门令")
    for m in missions[:8]:
        lines.append(
            f"  · [{m.get('sect')}] {m.get('title')}（{m.get('kind')}）贡献+{m.get('reward_contrib')}"
            f" id={m.get('id')}"
        )
    lines.append("  接令：/接宗门令 <id> · 完成：/交宗门令 <id>")
    sieges = active_sieges(t)
    lines.append(f"— 宗门围剿（{len(sieges)}）—")
    if not sieges:
        lines.append("  · 天下暂无宗门围剿")
    for s in sieges[:6]:
        lines.append(
            f"  · 【{s.get('sect')}】→【{s.get('target_name')}】@ {s.get('location')} "
            f"（{s.get('reason','')[:40]}）"
        )
    if viewer is not None and getattr(viewer, "sect", None):
        mine = [m for m in missions if m.get("sect") == viewer.sect]
        lines.append(f"你的宗籍【{viewer.sect}】可接宗门令：{len(mine)} 条")
        rel_you = []
        for sname in SECTS_CONFIG:
            if sname == viewer.sect:
                continue
            r = get_relation(viewer.sect, sname, t)
            rel_you.append(f"{sname}:{STATUS_CN.get(r.get('status'), r.get('status'))}")
        if rel_you:
            lines.append("你的宗门对外：" + " · ".join(rel_you))
    elif viewer is not None:
        lines.append("散修无宗门令，可观 /势力 旁观格局。")
    st = state.get("stats") or {}
    lines.append(
        f"累计：开令 {st.get('missions_open', 0)} · 完成 {st.get('missions_done', 0)} · "
        f"围剿 {st.get('sieges', 0)} · 关系变动 {st.get('shifts', 0)}"
    )
    return "\n".join(lines)


def handle_faction_command(parts: List[str], character: Any = None, now: Optional[float] = None) -> Dict[str, Any]:
    t = _now(now)
    sub = (parts[1].strip() if len(parts) > 1 else "").lower()
    if sub in ("令", "missions"):
        ms = list_missions(sect=getattr(character, "sect", "") or "", status="open", now=t)
        if not ms:
            ms = list_missions(status="open", now=t)
        text = "\n".join(
            f"· [{m.get('sect')}] {m.get('id')} {m.get('title')} +{m.get('reward_contrib')}贡献"
            for m in ms[:12]
        ) or "暂无宗门令"
        return {"ok": True, "text": "【宗门令】\n" + text}
    return {"ok": True, "text": format_faction_board(character, now=t)}


def handle_accept_mission(character: Any, mission_id: str) -> Dict[str, Any]:
    res = accept_mission(character, mission_id)
    return {"ok": res.get("success"), "text": res.get("message", "")}


def handle_complete_mission(character: Any, mission_id: str) -> Dict[str, Any]:
    res = complete_mission(character, mission_id)
    return {"ok": res.get("success"), "text": res.get("message", "")}


def director_apply_faction_order(d: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    """导师 faction_order 落账"""
    eff = (d.get("effects") or {}) if isinstance(d, dict) else {}
    sect = str(eff.get("sect") or "").strip()
    kind = str(eff.get("order_kind") or eff.get("kind") or "patrol").strip()
    target_sect = str(eff.get("target_sect") or "").strip()
    target_name = str(eff.get("target_name") or "").strip()
    location = str(eff.get("location") or d.get("location") or "").strip()
    if sect not in SECTS_CONFIG:
        return {"ok": False, "error": "unknown_sect"}
    if kind not in _ORDER_KINDS:
        kind = "patrol"
    if target_sect and target_sect not in SECTS_CONFIG:
        target_sect = ""
    m = open_mission(
        sect,
        kind,
        title=str(d.get("title") or "")[:40],
        detail=str(d.get("narrative") or "")[:160],
        target_sect=target_sect,
        target_name=target_name,
        location=location,
        source="director",
        now=now,
    )
    return {"ok": bool(m), "mission": m}


def director_apply_sect_siege(d: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    eff = (d.get("effects") or {}) if isinstance(d, dict) else {}
    sect = str(eff.get("sect") or "").strip()
    tname = str(eff.get("target_name") or "").strip()
    if sect not in SECTS_CONFIG or not tname:
        return {"ok": False, "error": "bad_siege_args"}
    target = None
    try:
        target = CharacterRepository.find_alive_by_name(tname)
    except Exception:
        target = None
    if not target:
        return {"ok": False, "error": "target_not_found"}
    res = open_siege(sect, target, reason=str(d.get("narrative") or "")[:80], source="director", now=now)
    return {"ok": res.get("success"), "message": res.get("message", ""), "siege": res.get("siege")}


def tick_world(now: Optional[float] = None) -> Dict[str, Any]:
    """势力后台：关系衰减 + 按敌对态势自动开令 + 血煞宗门围剿提案（规则）"""
    t = _now(now)
    ensure_defaults(t)
    decayed = decay_relations(t)
    state = _load()
    _purge_missions(state, t)
    opened = []
    # 敌对且无抵制令 → 自动开
    for rel in (state.get("relations") or {}).values():
        if rel.get("status") not in ("hostile", "tense"):
            continue
        a, b = rel.get("a"), rel.get("b")
        for sect, other in ((a, b), (b, a)):
            if sect not in SECTS_CONFIG:
                continue
            m = open_mission(sect, "boycott", target_sect=other, source="rule_tick", now=t)
            if m:
                opened.append(m)
    # 正道宗门对血煞目标（敌对门下优先）下围剿
    try:
        from core.hunt import is_marked

        for c in CharacterRepository.list_all_alive():
            if c.status == CharacterStatus.DEAD or not is_marked(c):
                continue
            csect = c.sect or ""
            for sect, cfg in SECTS_CONFIG.items():
                if "正道" not in str(cfg.get("alignment") or "") and sect != "万剑仙门":
                    continue
                if csect and csect == sect:
                    continue
                if csect and not is_hostile(sect, csect, t) and not is_tense_or_worse(sect, csect, t):
                    # 正道也可除凶，但概率/条件：业力极高
                    if c.karma.sin_value < 150:
                        continue
                if c.karma.sin_value < 80 and not c.karma.is_blood_marked(t):
                    continue
                # 仅在已有敌对或重业时尝试
                if csect and is_hostile(sect, csect, t):
                    res = open_siege(sect, c, reason="敌门血煞，借天道除之", source="rule_tick", now=t)
                    if res.get("success"):
                        opened.append(res.get("siege"))
                break
    except Exception:
        pass
    _save(state)
    return {"decayed": decayed, "opened": len(opened)}
