"""
名物入册：仅 AI/GM 产出的专名可登记为「听闻实体」（L1）。
不自动物化为可 /go 地点。
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from storage.db import WorldStateRepository

_KEY = "name_registry"
_MAX = 120
# conf 阈值按 source
THRESHOLDS = {
    "gm_broadcast": 0.55,
    "ai_event": 0.60,
    "ai_combat": 0.60,
    "npc_talk": 0.65,
    "ai_flavor": 0.75,
    "ai_other": 0.80,
}

_NAME_PROMPT = """你是天道名物司。审查系统文案中的专名：
exists=已在清单；should_register=应补听闻档；其余 rumor_only。
玩家来源禁止建档。禁止与已知名近似重复建档。
只输出 JSON：{"checked":[{"raw","verdict","type"}],"to_register":[{"type","name","desc","confidence","parent"}],"ok":true}

source={source}
文案={text}
发布者={author}
已知名：地{known_locations}
人{known_npcs}
物{known_items}
功法{known_arts}
宗门{known_sects}
"""


def _load() -> List[Dict[str, Any]]:
    try:
        data = WorldStateRepository.get(_KEY) or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(pool: List[Dict[str, Any]]) -> None:
    try:
        WorldStateRepository.set(_KEY, pool[-_MAX:])
    except Exception:
        pass


def register_heard(
    name: str,
    ntype: str = "location",
    desc: str = "",
    source: str = "ai_other",
    author: str = "",
    parent: str = "",
    confidence: float = 0.6,
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    name = (name or "").strip()[:24]
    if not name:
        return None
    pool = _load()
    if any(x.get("name") == name for x in pool):
        return None
    item = {
        "id": uuid.uuid4().hex[:6],
        "name": name,
        "type": ntype if ntype in ("location", "npc", "item", "art", "realm", "sect") else "location",
        "desc": (desc or "")[:120],
        "source": source,
        "author": author[:40],
        "parent": parent[:40],
        "confidence": round(float(confidence), 2),
        "created_at": now if now is not None else time.time(),
        "status": "heard",
    }
    pool.append(item)
    _save(pool)
    return item


def list_heard(ntype: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    pool = _load()
    if ntype:
        pool = [x for x in pool if x.get("type") == ntype]
    pool.sort(key=lambda x: -float(x.get("confidence") or 0))
    return pool[:limit]


def format_board(limit: int = 15) -> str:
    rows = list_heard(limit=limit)
    if not rows:
        return "【名物·听闻册】暂无未入正册的传说名物。"
    lines = ["【名物·听闻册】江湖有闻、尚未正册："]
    for r in rows:
        st = "已探明" if r.get("status") == "located" else "听闻"
        go = "（可 /go）" if r.get("status") == "located" else "（/追查 <名> 可物化）"
        lines.append(
            f"· [{r.get('type')}] {r.get('name')} · {st} — {r.get('desc') or '语焉不详'}"
            f"（源:{r.get('source')}·信{r.get('confidence')}）{go}"
        )
    return "\n".join(lines)


def get_heard(name: str) -> Optional[Dict[str, Any]]:
    name = (name or "").strip()
    pool = _load()
    for r in pool:
        if r.get("name") == name:
            return r
    for r in pool:
        if name and (name in r.get("name") or r.get("name") in name):
            return r
    return None


def mark_located(name: str) -> Optional[Dict[str, Any]]:
    pool = _load()
    for r in pool:
        if r.get("name") == name:
            r["status"] = "located"
            _save(pool)
            return r
    return None


_CHASE_CD_KEY = "chase_daily"


def _chase_ok(user_id: str, now: float, max_per_day: int = 3) -> Tuple[bool, str]:
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    try:
        rec = WorldStateRepository.get(_CHASE_CD_KEY) or {}
        row = rec.get(user_id) or {}
        if row.get("day") != day:
            row = {"day": day, "n": 0}
        if int(row.get("n") or 0) >= max_per_day:
            return False, "今日追查次数已尽（每日 3 次）。"
        return True, ""
    except Exception:
        return True, ""


def _chase_tick(user_id: str, now: float) -> None:
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    try:
        rec = WorldStateRepository.get(_CHASE_CD_KEY) or {}
        row = rec.get(user_id) or {}
        if row.get("day") != day:
            row = {"day": day, "n": 0}
        row["n"] = int(row.get("n") or 0) + 1
        rec[user_id] = row
        WorldStateRepository.set(_CHASE_CD_KEY, rec)
    except Exception:
        pass


def materialize_location(heard: Dict[str, Any], player: Optional[Any] = None) -> Dict[str, Any]:
    """把听闻地点写入 WORLD_LOCATIONS，使其可 /go"""
    from config import WORLD_LOCATIONS

    name = heard.get("name") or ""
    if not name:
        return {"success": False, "message": "无名可物化。"}
    if name in WORLD_LOCATIONS:
        mark_located(name)
        return {"success": True, "message": f"【{name}】早已在舆图之上。", "already": True}
    parent = (heard.get("parent") or "").strip()
    if parent not in WORLD_LOCATIONS:
        # 挂到玩家当前地或坊市
        if player is not None and getattr(player, "location", "") in WORLD_LOCATIONS:
            parent = player.location
        else:
            parent = "青云坊市客栈"
    is_safe = True
    desc = (heard.get("desc") or "江湖传闻中的一处所在。")[:80]
    WORLD_LOCATIONS[name] = {
        "region": parent,
        "qi_density": 1.0,
        "danger": 0.2,
        "is_safe": is_safe,
        "desc": f"{desc}（探明自传闻）",
    }
    mark_located(name)
    try:
        from core.world_channel import WorldChannel

        WorldChannel.post(
            "locate",
            f"【舆图添新】有人探明【{name}】，自此可御剑前往。",
            level="major",
            actor=player.name if player is not None else "",
            location=name,
        )
    except Exception:
        pass
    return {"success": True, "message": f"【探明】{name} 已入舆图，可 /go {name}。", "location": name}


def chase(c: Any, name: str, now: Optional[float] = None, force: bool = False) -> Dict[str, Any]:
    """追查听闻地点并尝试物化"""
    t = now if now is not None else time.time()
    from core.models import CharacterStatus

    if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
        return {"success": False, "message": "身死道消，如何追查。"}
    if c.status == CharacterStatus.MEDITATING:
        return {"success": False, "message": "闭关中不可追查。"}
    heard = get_heard(name)
    if not heard:
        return {"success": False, "message": f"听闻册中并无【{name}】。/名物 查看。"}
    if heard.get("type") not in ("location", "realm"):
        return {"success": False, "message": f"【{heard.get('name')}】非地点，暂不可追查入图。"}
    if heard.get("status") == "located":
        return {"success": False, "message": f"【{heard.get('name')}】早已探明，直接 /go。"}
    if not force:
        ok_cd, why = _chase_ok(c.user_id, t)
        if not ok_cd:
            return {"success": False, "message": why}
        fee = 30
        if c.spirit_stones < fee:
            return {"success": False, "message": f"追查需 {fee} 灵石打点耳目，囊中仅有 {c.spirit_stones}。"}
        c.spirit_stones -= fee
        _chase_tick(c.user_id, t)
        import random as _r

        rate = max(0.25, min(0.85, 0.45 + 0.02 * c.realm.tier))
        if _r.random() >= rate:
            from storage.db import CharacterRepository

            CharacterRepository.save(c)
            return {
                "success": True,
                "chased": False,
                "message": (
                    f"【追查无果】耗 {fee} 灵石，只闻【{heard.get('name')}】之名，未见其门。"
                    f"（成率 {rate:.0%}）"
                ),
            }
    res = materialize_location(heard, player=c)
    if not res.get("success"):
        return res
    from storage.db import CharacterRepository

    CharacterRepository.save(c)
    fee_note = "（强制物化）" if force else "（耗 30 灵石）"
    return {
        "success": True,
        "chased": True,
        "message": res.get("message", "") + fee_note,
        "location": res.get("location"),
    }


def _known_lists() -> Dict[str, str]:
    from config import WORLD_LOCATIONS, ITEM_CATALOG, SECTS_CONFIG

    locs = "、".join(list(WORLD_LOCATIONS.keys())[:40])
    items = "、".join(list(ITEM_CATALOG.keys())[:40])
    sects = "、".join(list(SECTS_CONFIG.keys()))
    try:
        from core.npc_roster import ROSTER

        npcs = "、".join(r.get("name") or "" for r in ROSTER[:40])
    except Exception:
        npcs = ""
    arts = "吐纳术、御剑术"
    return {
        "known_locations": locs,
        "known_items": items,
        "known_sects": sects,
        "known_npcs": npcs,
        "known_arts": arts,
    }


def _rule_candidates(text: str, known_names: set) -> List[str]:
    """粗抽：引号内或「X谷/X山/X宗/X老祖」类"""
    out = []
    for m in re.finditer(r"[「『\"]([一-鿿]{2,12})[」』\"]", text or ""):
        n = m.group(1)
        if n not in known_names:
            out.append(n)
    for m in re.finditer(r"([一-鿿]{2,8}(?:谷|渊|山|崖|岛|殿|阁|楼|宗|门|派|教|老祖|真君|剑尊|魔尊))", text or ""):
        n = m.group(1)
        if n not in known_names and n not in out:
            out.append(n)
    return out[:6]


def review_and_register(
    text: str,
    source: str = "ai_other",
    author: str = "",
    force_ai: bool = False,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """
    审查系统文案并入听闻册。
    - source 含 player → 拒绝登记
    - 无 AI：仅规则候选，高置信直接登记（gm 用中阈值）
    """
    if source.startswith("player"):
        return {"ok": False, "reason": "player_forbidden", "registered": []}
    from config import WORLD_LOCATIONS, ITEM_CATALOG

    known = set(WORLD_LOCATIONS) | set(ITEM_CATALOG)
    try:
        from core.npc_roster import ROSTER

        known |= {r.get("name") for r in ROSTER}
    except Exception:
        pass

    registered: List[Dict[str, Any]] = []
    threshold = THRESHOLDS.get(source, 0.8)

    # AI 路径
    ai_data = None
    try:
        from ai.gateway import _chat_json, ai_available

        if ai_available() or force_ai:
            known_pack = _known_lists()
            prompt = _NAME_PROMPT.format(
                source=source,
                text=(text or "")[:500],
                author=author or "系统",
                **known_pack,
            )
            ai_data = _chat_json(prompt, timeout=12.0)
    except Exception:
        ai_data = None

    if ai_data and isinstance(ai_data.get("to_register"), list):
        for row in ai_data["to_register"][:5]:
            try:
                conf = float(row.get("confidence") or 0)
            except Exception:
                conf = 0
            name = str(row.get("name") or "").strip()
            if not name or name in known:
                continue
            if conf < threshold:
                continue
            item = register_heard(
                name=name,
                ntype=str(row.get("type") or "location"),
                desc=str(row.get("desc") or row.get("lore") or ""),
                source=source,
                author=author,
                parent=str(row.get("parent") or ""),
                confidence=conf,
                now=now,
            )
            if item:
                registered.append(item)
        return {"ok": True, "registered": registered, "via": "ai"}

    # 无 AI：gm_broadcast 用规则候选中阈值；其它 source 不登记
    if source == "gm_broadcast":
        for n in _rule_candidates(text or "", known):
            item = register_heard(
                name=n, ntype="location", desc="公告提及", source=source, author=author, confidence=0.7, now=now
            )
            if item:
                registered.append(item)
    return {"ok": True, "registered": registered, "via": "rule" if registered else "none"}
