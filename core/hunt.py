"""
除凶令 + 围剿 + 限时/逃亡/反悬赏
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository

_HUNT_KEY = "hunts"  # hunter_id -> {target_id, expires_at}
_COUNTER_KEY = "counter_hunts"  # target_id -> {hunter_id, paid}
SIN_THRESHOLD = 80
HUNT_TTL_H = 48.0
FLEE_CHANCE = 0.25


def _load() -> Dict[str, Any]:
    try:
        d = WorldStateRepository.get(_HUNT_KEY) or {}
        out: Dict[str, Any] = {}
        for k, v in d.items():
            if isinstance(v, str):
                out[str(k)] = {"target_id": v, "expires_at": 0.0}
            else:
                out[str(k)] = v
        return out
    except Exception:
        return {}


def _save(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_HUNT_KEY, d)
    except Exception:
        pass


def _purge_expired(now: float) -> Dict[str, Any]:
    d = _load()
    changed = False
    out = {}
    for k, v in d.items():
        exp = float(v.get("expires_at") or 0)
        # 旧数据无过期：给宽限
        if exp <= 0:
            v["expires_at"] = now + HUNT_TTL_H * 3600
            exp = v["expires_at"]
        if now > exp:
            changed = True
            continue
        out[k] = v
    if changed or len(out) != len(d):
        _save(out)
    return out


def is_marked(c: Character, now: Optional[float] = None) -> bool:
    t = now if now is not None else time.time()
    return c.karma.is_blood_marked(t) or c.karma.sin_value >= SIN_THRESHOLD


def format_board(limit: int = 12) -> str:
    now = time.time()
    _purge_expired(now)
    rows = []
    for c in CharacterRepository.list_all_alive():
        if c.status == CharacterStatus.DEAD:
            continue
        if is_marked(c):
            rows.append(c)
    rows.sort(key=lambda x: -x.karma.sin_value)
    if not rows:
        return "【除凶榜】天道清朗，暂无血煞缠身之人。"
    lines = [
        f"【除凶榜】血煞或业力≥{SIN_THRESHOLD}者；令限时 {int(HUNT_TTL_H)}h。",
        "接令：/接除凶 <道号> · /弃除凶 · /围剿 <道号> 宣告 · /反悬赏 防身",
    ]
    hunts = _load()
    for c in rows[:limit]:
        mark = "血煞" if c.karma.is_blood_marked() else "重业"
        who = "NPC" if str(c.user_id).startswith("npc_") else "修士"
        n_hunt = sum(1 for v in hunts.values() if v.get("target_id") == c.id)
        lines.append(
            f"· 【{c.name}】{c.realm.name} {mark} 业力{c.karma.sin_value} "
            f"@ {c.location}（{who}·被{n_hunt}人盯上）"
        )
    return "\n".join(lines)


def accept(hunter: Character, target_name: str) -> Dict[str, Any]:
    now = time.time()
    d = _purge_expired(now)
    target = CharacterRepository.find_alive_by_name(target_name)
    if not target:
        return {"success": False, "message": f"未寻得【{target_name}】。"}
    if target.id == hunter.id:
        return {"success": False, "message": "不可接自己的除凶令。"}
    if not is_marked(target):
        return {
            "success": False,
            "message": f"【{target.name}】未染血煞，天道不允私刑。",
        }
    d[hunter.id] = {
        "target_id": target.id,
        "expires_at": now + HUNT_TTL_H * 3600,
        "target_name": target.name,
    }
    _save(d)
    # 目标察觉（若玩家）
    try:
        if not str(target.user_id).startswith("npc_"):
            from core.world_channel import WorldChannel

            # 仅提示，不点名猎人
            pass
    except Exception:
        pass
    return {
        "success": True,
        "target_id": target.id,
        "message": (
            f"【除凶令】已接：诛【{target.name}】（{target.realm.name} @ {target.location}）。\n"
            f"限时 {int(HUNT_TTL_H)} 现实小时；同场可 /围剿 {target.name} 宣告。"
        ),
    }


def abandon(hunter: Character) -> Dict[str, Any]:
    d = _load()
    if hunter.id not in d:
        return {"success": False, "message": "你并未接除凶令。"}
    d.pop(hunter.id, None)
    _save(d)
    return {"success": True, "message": "【弃令】放下杀心。"}


def my_target(hunter: Character) -> Optional[Character]:
    now = time.time()
    d = _purge_expired(now)
    rec = d.get(hunter.id)
    if not rec:
        return None
    tid = rec.get("target_id") if isinstance(rec, dict) else rec
    if not tid:
        return None
    t = CharacterRepository.get_by_id(tid)
    if not t or t.status == CharacterStatus.DEAD:
        return None
    return t


def my_target_info(hunter: Character) -> Optional[Dict[str, Any]]:
    now = time.time()
    d = _purge_expired(now)
    rec = d.get(hunter.id)
    if not rec:
        return None
    t = my_target(hunter)
    if not t:
        return None
    left = max(0.0, float(rec.get("expires_at") or 0) - now) / 3600.0
    return {"target": t, "remain_h": round(left, 1)}


def settle_kill(hunter: Character, victim: Character) -> Optional[Dict[str, Any]]:
    now = time.time()
    d = _purge_expired(now)
    rec = d.get(hunter.id)
    tid = rec.get("target_id") if isinstance(rec, dict) else rec
    if tid != victim.id:
        return None
    d.pop(hunter.id, None)
    _save(d)
    hunter.karma.add_merit(40)
    hunter.karma.sin_value = max(0, hunter.karma.sin_value - 20)
    CharacterRepository.save(hunter)
    try:
        from core.world_channel import WorldChannel

        WorldChannel.post(
            "hunt",
            f"【除凶】{hunter.name} 诛 {victim.name}，天道降功德，血煞稍解。",
            level="major",
            actor=hunter.name,
            location=victim.location,
        )
    except Exception:
        pass
    # 反悬赏结算（键为 hunter_id）
    try:
        cd = WorldStateRepository.get(_COUNTER_KEY) or {}
        if victim.id in cd:
            cd.pop(victim.id, None)
            WorldStateRepository.set(_COUNTER_KEY, cd)
        else:
            for k in list(cd.keys()):
                if cd[k].get("hunter_id") == victim.id:
                    cd.pop(k, None)
            WorldStateRepository.set(_COUNTER_KEY, cd)
    except Exception:
        pass
    return {"merit": 40, "sin_reduced": 20}


def settle_hunter_slain(hunter: Character, killer: Character) -> Optional[Dict[str, Any]]:
    """被悬赏的猎人被目标杀死：目标得功德"""
    cd = WorldStateRepository.get(_COUNTER_KEY) or {}
    hit_key = None
    for k, rec in cd.items():
        if rec.get("hunter_id") == hunter.id and rec.get("target_id") == killer.id:
            hit_key = k
            break
    if not hit_key:
        return None
    cd.pop(hit_key, None)
    WorldStateRepository.set(_COUNTER_KEY, cd)
    killer.karma.add_merit(20)
    CharacterRepository.save(killer)
    try:
        from core.world_channel import WorldChannel

        WorldChannel.post(
            "hunt",
            f"【反杀】{killer.name} 诛除凶人 {hunter.name}，天道记其反抗。",
            level="major",
            actor=killer.name,
        )
    except Exception:
        pass
    return {"merit": 20}


def place_counter(hunted: Character) -> Dict[str, Any]:
    """被盯上者花 50 灵石挂反悬赏"""
    now = time.time()
    d = _purge_expired(now)
    hunters = [hid for hid, v in d.items() if v.get("target_id") == hunted.id]
    if not hunters:
        return {"success": False, "message": "当前无人对你下除凶令。"}
    if hunted.spirit_stones < 50:
        return {"success": False, "message": "反悬赏需 50 灵石。"}
    hunted.spirit_stones -= 50
    CharacterRepository.save(hunted)
    cd = WorldStateRepository.get(_COUNTER_KEY) or {}
    for hid in hunters:
        cd[hid] = {"target_id": hunted.id, "hunter_id": hid, "paid": 50}
    WorldStateRepository.set(_COUNTER_KEY, cd)
    return {
        "success": True,
        "message": (
            f"【反悬赏】耗 50 灵石，悬 {len(hunters)} 名猎人之首。\n"
            f"若你诛杀盯上你的人，额外功德 +20。"
        ),
    }


def announce_siege(actor: Character, target_name: str) -> Dict[str, Any]:
    target = CharacterRepository.find_alive_by_name(target_name)
    if not target:
        return {"success": False, "message": f"未寻得【{target_name}】。"}
    if target.location != actor.location:
        return {"success": False, "message": "围剿须同场宣告。"}
    if not is_marked(target):
        return {"success": False, "message": "对方未染血煞。"}
    d = _load()
    rec = d.get(actor.id)
    tid = rec.get("target_id") if isinstance(rec, dict) else rec
    if tid != target.id:
        return {"success": False, "message": "须先 /接除凶 该目标，方可号令围剿。"}
    try:
        from core.world_channel import WorldChannel
        from core import rumors
        from core import ai_flavor

        line = ai_flavor.polish_hunt_announce(actor.name, target.name, target.location) or (
            f"【围剿】{actor.name} 于 {target.location} 号召同道共诛【{target.name}】。"
        )
        WorldChannel.post(
            "hunt",
            line,
            level="major",
            actor=actor.name,
            location=target.location,
        )
        rumors.note_collusion(actor.name, target.name, "寻仇未遂", target.location)
    except Exception:
        pass
    return {
        "success": True,
        "message": f"【围剿宣告】已传告同场道友，共诛【{target.name}】。系数 1.15 生效中。",
    }


def maybe_flee_npc(target: Character, now: Optional[float] = None) -> Optional[str]:
    """被接令的 NPC tick 时可能逃亡"""
    if not str(target.user_id).startswith("npc_"):
        return None
    t = now if now is not None else time.time()
    d = _purge_expired(t)
    if not any(v.get("target_id") == target.id for v in d.values()):
        return None
    if random.random() > FLEE_CHANCE:
        return None
    from config import WORLD_LOCATIONS

    locs = list(WORLD_LOCATIONS.keys())
    if not locs:
        return None
    dest = random.choice([x for x in locs if x != target.location] or locs)
    target.location = dest
    CharacterRepository.save(target)
    try:
        from core import rumors

        rumors.add_rumor(
            f"有人见【{target.name}】行色匆匆，似在避祸，往 {dest} 去了。",
            origin=dest,
            tags=["flee", target.name],
            truth=0.7,
        )
    except Exception:
        pass
    return dest


def siege_multiplier(attacker: Character, defender: Character) -> float:
    if not is_marked(defender):
        return 1.0
    same = [
        c
        for c in CharacterRepository.list_all_alive()
        if c.location == defender.location
        and c.id != defender.id
        and c.status != CharacterStatus.DEAD
    ]
    d = _load()
    hunters = [c for c in same if (d.get(c.id) or {}).get("target_id") == defender.id]
    players = [c for c in same if not str(c.user_id).startswith("npc_")]
    if len(hunters) >= 2 or (len(players) >= 2 and is_marked(defender)):
        return 1.15
    return 1.0


def hunt_triggered(c: Character) -> bool:
    """用于日环 hook：今日接过令"""
    d = _load()
    return c.id in d
