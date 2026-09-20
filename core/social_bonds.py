"""
师徒 / 结拜：社会契约（规则权威）
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from core.bounty import KarmaLink
from core.collusion import ensure_link, links_between, links_of, format_links
from storage.db import CharacterRepository, WorldStateRepository

_PENDING_KEY = "pending_bonds"
_TIMEOUT = 600.0


def _load_pending() -> Dict[str, Any]:
    try:
        return WorldStateRepository.get(_PENDING_KEY) or {}
    except Exception:
        return {}


def _save_pending(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_PENDING_KEY, d)
    except Exception:
        pass


def _purge_pending(now: float) -> Dict[str, Any]:
    d = _load_pending()
    out = {
        k: v
        for k, v in d.items()
        if now - float(v.get("ts") or 0) < _TIMEOUT
    }
    if len(out) != len(d):
        _save_pending(out)
    return out


def _alive(name: str) -> Optional[Character]:
    return CharacterRepository.find_alive_by_name(name)


def _ok_pair(a: Character, b: Character) -> tuple[bool, str]:
    if a.id == b.id:
        return False, "不可与自己结契。"
    if b.status == CharacterStatus.DEAD or b.lifespan.is_dead():
        return False, f"【{b.name}】已不在人世。"
    if a.status == CharacterStatus.DEAD or a.lifespan.is_dead():
        return False, "身死道消，何谈结契。"
    return True, ""


def propose_master(a: Character, master_name: str) -> Dict[str, Any]:
    """弟子 a 请求拜师 master_name"""
    m = _alive(master_name)
    if not m:
        return {"success": False, "message": f"未寻得【{master_name}】。"}
    ok, err = _ok_pair(a, m)
    if not ok:
        return {"success": False, "message": err}
    if m.realm.tier <= a.realm.tier:
        return {"success": False, "message": f"【{m.name}】境界不高于你，无法为师。"}
    # 敌对不可拜师
    try:
        from core.npc_mind import attitude_toward, _is_npc

        if _is_npc(m):
            att = attitude_toward(m, a.id)
            if int(att.get("value") or 0) <= -40:
                return {"success": False, "message": f"【{m.name}】对你敌意甚深，不肯收徒。"}
    except Exception:
        pass
    if any(l.link_type == "师徒" and l.involves(a.id) for l in links_of(a.id)):
        return {"success": False, "message": "你已有师承，须先 /出师 或 /绝交。"}
    pending = _purge_pending(time.time())
    pending[a.id] = {
        "type": "master",
        "a_id": a.id,
        "a_name": a.name,
        "b_id": m.id,
        "b_name": m.name,
        "ts": time.time(),
    }
    _save_pending(pending)
    return {
        "success": True,
        "message": (
            f"【拜师帖】已递至【{m.name}】。\n"
            f"对方需在线输入 /确认拜师。10 分钟内有效。"
        ),
    }


def propose_disciple(master: Character, disciple_name: str) -> Dict[str, Any]:
    """师父主动收徒：生成 pending，待弟子 /确认拜师"""
    d = _alive(disciple_name)
    if not d:
        return {"success": False, "message": f"未寻得【{disciple_name}】。"}
    ok, err = _ok_pair(master, d)
    if not ok:
        return {"success": False, "message": err}
    if master.realm.tier <= d.realm.tier:
        return {"success": False, "message": "境界须高于弟子。"}
    if any(l.link_type == "师徒" and l.involves(d.id) for l in links_of(d.id)):
        return {"success": False, "message": f"【{d.name}】已有师承。"}
    pending = _purge_pending(time.time())
    pending[f"to_{d.id}"] = {
        "type": "invite_disciple",
        "a_id": master.id,
        "a_name": master.name,
        "b_id": d.id,
        "b_name": d.name,
        "ts": time.time(),
    }
    _save_pending(pending)
    return {
        "success": True,
        "message": f"【收徒帖】已递至【{d.name}】。对方 /确认拜师 后礼成。",
    }


def confirm_master(c: Character) -> Dict[str, Any]:
    """师父确认收徒，或弟子确认被收"""
    pending = _purge_pending(time.time())
    # 1) 有人向我递拜师帖
    entry = next(
        (v for v in pending.values() if v.get("type") == "master" and v.get("b_id") == c.id),
        None,
    )
    if entry:
        disciple = CharacterRepository.get_by_id(entry["a_id"])
        if not disciple or disciple.status == CharacterStatus.DEAD or disciple.lifespan.is_dead():
            pending.pop(entry["a_id"], None)
            _save_pending(pending)
            return {"success": False, "message": "弟子已不在世。"}
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
            return {"success": False, "message": "你已不在人世。"}
        if c.realm.tier <= disciple.realm.tier:
            return {"success": False, "message": "境界须高于弟子。"}
        ensure_link(c, disciple, "师徒", note=f"{c.name}收{disciple.name}为徒")
        pending.pop(entry["a_id"], None)
        _save_pending(pending)
        try:
            from core.world_channel import WorldChannel

            WorldChannel.post(
                "bond",
                f"【师徒】{c.name} 收 {disciple.name} 为徒，道统有继。焚香告天，礼成。",
                level="major",
                actor=c.name,
            )
        except Exception:
            pass
        return {
            "success": True,
            "message": (
                f"【收徒】{c.name} 与 {disciple.name} 结成师徒。\n"
                f"传功礼金减半；可 /传功 点拨。"
            ),
        }
    # 2) 师父向我发收徒帖
    invite = next(
        (v for v in pending.values() if v.get("type") == "invite_disciple" and v.get("b_id") == c.id),
        None,
    )
    if invite:
        master = CharacterRepository.get_by_id(invite["a_id"])
        if not master or master.status == CharacterStatus.DEAD or master.lifespan.is_dead():
            pending.pop(f"to_{c.id}", None)
            _save_pending(pending)
            return {"success": False, "message": "师父已不在世。"}
        if master.realm.tier <= c.realm.tier:
            return {"success": False, "message": "对方境界须高于你。"}
        ensure_link(master, c, "师徒", note=f"{master.name}收{c.name}为徒")
        pending.pop(f"to_{c.id}", None)
        _save_pending(pending)
        try:
            from core.world_channel import WorldChannel

            WorldChannel.post(
                "bond",
                f"【师徒】{master.name} 收 {c.name} 为徒，道统有继。焚香告天，礼成。",
                level="major",
                actor=master.name,
            )
        except Exception:
            pass
        return {"success": True, "message": f"【拜师礼成】投入【{master.name}】门下。"}
    return {"success": False, "message": "当前无人向你递帖。"}


def graduate(c: Character) -> Dict[str, Any]:
    """出师：须 strength≥3 或弟子境界 ≥ 师父-1；断师徒边，记恩"""
    links = [l for l in links_of(c.id) if l.link_type == "师徒"]
    if not links:
        return {"success": False, "message": "你并无师承。"}
    from storage.db import KarmaLinkRepository

    graduated_any = False
    msgs = []
    for l in links:
        oid, oname = l.other_side(c.id)
        master = CharacterRepository.get_by_id(oid) if oid != c.id else None
        # c 可能是师父或弟子；找对方
        other = CharacterRepository.get_by_id(oid)
        if not other:
            continue
        # 弟子出师：c 是弟子，other 是师父
        if l.a_id == c.id or l.b_id == c.id:
            disc, mast = (c, other) if other.realm.tier > c.realm.tier else (other, c)
        else:
            disc, mast = c, other
        ok_grad = (
            l.strength >= 3
            or disc.realm.tier >= max(0, mast.realm.tier - 1)
            or has_graduate_credit(disc)
        )
        if not ok_grad:
            msgs.append(f"与【{other.name}】缘分未到（需传功往还或境界相近）。")
            continue
        l.link_type = "恩"
        l.note = (l.note or "") + "；已出师"
        KarmaLinkRepository.save(l)
        disc.karma.add_merit(10)
        mast.karma.add_merit(10)
        CharacterRepository.save(disc)
        CharacterRepository.save(mast)
        graduated_any = True
        try:
            from core import ai_flavor

            tip = ai_flavor.polish_graduation(mast.name, disc.name)
            msgs.append(tip or f"与【{other.name}】出师，转为恩义，双方功德 +10。")
        except Exception:
            msgs.append(f"与【{other.name}】出师，转为恩义，双方功德 +10。")
    if not graduated_any:
        return {"success": False, "message": "\n".join(msgs) or "出师未成。"}
    return {"success": True, "message": "【出师】" + "\n".join(msgs)}


def propose_sworn(a: Character, name: str) -> Dict[str, Any]:
    b = _alive(name)
    if not b:
        return {"success": False, "message": f"未寻得【{name}】。"}
    ok, err = _ok_pair(a, b)
    if not ok:
        return {"success": False, "message": err}
    from config import WORLD_LOCATIONS

    loc = WORLD_LOCATIONS.get(a.location) or {}
    if a.location != b.location or not loc.get("is_safe"):
        return {"success": False, "message": "结拜须同处安全区，歃血为盟。"}
    pending = _purge_pending(time.time())
    pending[a.id] = {
        "type": "sworn",
        "a_id": a.id,
        "a_name": a.name,
        "b_id": b.id,
        "b_name": b.name,
        "ts": time.time(),
    }
    _save_pending(pending)
    return {
        "success": True,
        "message": f"【结拜】已向【{b.name}】提出。对方 /结拜同意 后礼成。",
    }


def accept_sworn(c: Character) -> Dict[str, Any]:
    pending = _purge_pending(time.time())
    entry = next(
        (v for v in pending.values() if v.get("type") == "sworn" and v.get("b_id") == c.id),
        None,
    )
    if not entry:
        return {"success": False, "message": "当前无人与你结拜。"}
    other = CharacterRepository.get_by_id(entry["a_id"])
    if not other or other.status == CharacterStatus.DEAD or other.lifespan.is_dead():
        pending.pop(entry["a_id"], None)
        _save_pending(pending)
        return {"success": False, "message": "对方已不在世。"}
    if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
        return {"success": False, "message": "你已不在人世。"}
    from config import WORLD_LOCATIONS

    loc = WORLD_LOCATIONS.get(c.location) or {}
    if other.location != c.location or not loc.get("is_safe"):
        return {"success": False, "message": "地点已变，结拜未成。"}
    ensure_link(other, c, "结拜", note="义结金兰")
    pending.pop(entry["a_id"], None)
    _save_pending(pending)
    CharacterRepository.save(other)
    CharacterRepository.save(c)
    try:
        from core.world_channel import WorldChannel

        WorldChannel.post(
            "bond",
            f"【结拜】{other.name} 与 {c.name} 义结金兰，不求同生，但求同死。",
            level="major",
            actor=other.name,
            location=c.location,
        )
    except Exception:
        pass
    return {"success": True, "message": f"【结拜礼成】{other.name} ↔ {c.name}。同场斗法 +5%。"}


def break_bond(c: Character, name: str) -> Dict[str, Any]:
    b = _alive(name)
    if not b:
        return {"success": False, "message": f"未寻得【{name}】。"}
    from storage.db import KarmaLinkRepository

    found = False
    for l in links_between(c.id, b.id):
        if l.link_type in ("师徒", "结拜"):
            KarmaLinkRepository.delete(l.id) if hasattr(KarmaLinkRepository, "delete") else None
            # 无 delete 则改类型为断
            l.link_type = "断"
            l.note = (l.note or "") + "；绝交"
            KarmaLinkRepository.save(l)
            found = True
    if not found:
        return {"success": False, "message": "与对方并无师徒/结拜。"}
    c.karma.add_sin(5)
    CharacterRepository.save(c)
    return {"success": True, "message": f"【绝交】与【{b.name}】恩断义绝，业力 +5。"}


def transmit_cost_mult(master: Character, disciple: Character) -> float:
    for l in links_between(master.id, disciple.id):
        if l.link_type == "师徒":
            return 0.5
    return 1.0


def combat_sworn_bonus(a: Character, b: Character) -> float:
    """结拜同场（任一方视角）+5%"""
    for l in links_between(a.id, b.id):
        if l.link_type == "结拜":
            return 0.05
    return 0.0


# ---------------- 加深：师门任务 / 叛师 / 出师 credit / 结义任务 ----------------

_DAILY_KEY = "bond_daily"
_CREDIT_KEY = "graduate_credit"

MASTER_TASKS = [
    {"id": "herb", "label": "为师采一株【百年灵芝】交来", "need_item": "百年灵芝"},
    {"id": "patrol", "label": "赴本宗总坛巡山一周（迁跃到总坛）", "need_visit": True},
    {"id": "hunt", "label": "接下一枚除凶令（/接除凶）", "need_hunt": True},
    {"id": "herb2", "label": "寻一味【妖兽内丹】献上", "need_item": "妖兽内丹"},
    {"id": "herb3", "label": "取一株【回春露】（可坊市购得）", "need_item": "回春露"},
    {"id": "herb4", "label": "奉上【聚气丹】一枚以供试药", "need_item": "聚气丹"},
    {"id": "patrol2", "label": "回山听训：亲至本宗总坛", "need_visit": True},
    {"id": "hunt2", "label": "为师留意血煞之徒：接除凶令", "need_hunt": True},
    {"id": "herb5", "label": "寻【百年灵芝】佐药（重要）", "need_item": "百年灵芝"},
]

SWORN_TASKS = [
    {"id": "joint1", "label": "同场完成一次历练（提交时须同场）", "need_joint": True},
    {"id": "joint2", "label": "并肩立于同一处（提交时同场）", "need_joint": True},
    {"id": "joint3", "label": "肝胆相照：同场交割结义之礼", "need_joint": True},
    {"id": "joint4", "label": "共闯江湖：同场提交结义", "need_joint": True},
]


def _day_id(now: Optional[float] = None) -> str:
    t = now if now is not None else time.time()
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _load_daily() -> Dict[str, Any]:
    try:
        return WorldStateRepository.get(_DAILY_KEY) or {}
    except Exception:
        return {}


def _save_daily(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_DAILY_KEY, d)
    except Exception:
        pass


def master_of(c: Character) -> Optional[Character]:
    for l in links_of(c.id):
        if l.link_type != "师徒":
            continue
        oid, _ = l.other_side(c.id)
        other = CharacterRepository.get_by_id(oid)
        if other and other.realm.tier > c.realm.tier:
            return other
    return None


def disciples_of(master: Character) -> List[Character]:
    out = []
    for l in links_of(master.id):
        if l.link_type != "师徒":
            continue
        oid, _ = l.other_side(master.id)
        other = CharacterRepository.get_by_id(oid)
        if other and other.realm.tier < master.realm.tier:
            out.append(other)
    return out


def sworn_partner(c: Character) -> Optional[Character]:
    for l in links_of(c.id):
        if l.link_type != "结拜":
            continue
        oid, _ = l.other_side(c.id)
        other = CharacterRepository.get_by_id(oid)
        if other:
            return other
    return None


def format_master_task(c: Character) -> Dict[str, Any]:
    m = master_of(c)
    if not m:
        return {"success": False, "message": "你并无师父。"}
    day = _day_id()
    data = _load_daily()
    key = f"{c.id}:master"
    cur = data.get(key) or {}
    if cur.get("day") != day or cur.get("kind") != "master":
        import random as _r

        task = _r.choice(MASTER_TASKS)
        cur = {"day": day, "kind": "master", "task": task, "done": False}
        data[key] = cur
        _save_daily(data)
    task = cur.get("task") or {}
    mark = "✓" if cur.get("done") else "○"
    lore = f"【师门任务 · 师父 {m.name}】{mark} {task.get('label')}"
    try:
        from core import ai_flavor

        if not cur.get("done"):
            lore = ai_flavor.polish_master_task(m.name, c.name, task.get("label") or "") or lore
    except Exception:
        pass
    return {
        "success": True,
        "task": task,
        "done": bool(cur.get("done")),
        "message": (
            f"{lore}\n"
            f"完成后 /交师门。师父得功德，你增师徒缘分。"
        ),
    }


def submit_master_task(c: Character) -> Dict[str, Any]:
    m = master_of(c)
    if not m:
        return {"success": False, "message": "你并无师父。"}
    day = _day_id()
    data = _load_daily()
    key = f"{c.id}:master"
    cur = data.get(key) or {}
    if cur.get("day") != day or cur.get("kind") != "master":
        return {"success": False, "message": "今日未领师门任务，先 /师门任务。"}
    if cur.get("done"):
        return {"success": False, "message": "今日师门任务已交。"}
    task = cur.get("task") or {}
    # 校验完成条件
    if task.get("need_item"):
        item = task["need_item"]
        if c.inventory.count(item) < 1:
            return {"success": False, "message": f"尚未备齐【{item}】。"}
        c.inventory.remove(item)
    if task.get("need_hunt"):
        from core.hunt import my_target

        if not my_target(c):
            return {"success": False, "message": "尚未接除凶令。"}
    if task.get("need_visit"):
        from config import SECTS_CONFIG

        hq = (SECTS_CONFIG.get(c.sect) or {}).get("headquarters") or ""
        if not hq or c.location != hq:
            return {"success": False, "message": f"须亲至总坛【{hq or '本宗山门'}】。"}
    cur["done"] = True
    data[key] = cur
    _save_daily(data)
    m.karma.add_merit(5)
    c.karma.add_merit(3)
    CharacterRepository.save(m)
    CharacterRepository.save(c)
    for l in links_between(c.id, m.id):
        if l.link_type == "师徒":
            l.strength += 1
            from storage.db import KarmaLinkRepository

            KarmaLinkRepository.save(l)
    return {
        "success": True,
        "message": f"【交师门】{task.get('label')} 已毕。师父功德+5，你功德+3，缘分加深。",
    }


def format_sworn_task(c: Character) -> Dict[str, Any]:
    p = sworn_partner(c)
    if not p:
        return {"success": False, "message": "你并无结拜兄弟。"}
    day = _day_id()
    data = _load_daily()
    key = f"{c.id}:sworn"
    cur = data.get(key) or {}
    if cur.get("day") != day or cur.get("kind") != "sworn":
        cur = {
            "day": day,
            "kind": "sworn",
            "task": SWORN_TASKS[0],
            "done": False,
        }
        data[key] = cur
        _save_daily(data)
    mark = "✓" if cur.get("done") else "○"
    return {
        "success": True,
        "done": bool(cur.get("done")),
        "message": (
            f"【结义任务 · 与 {p.name}】{mark} {SWORN_TASKS[0]['label']}\n"
            f"同场历练后 /交结义。"
        ),
    }


def submit_sworn_task(c: Character) -> Dict[str, Any]:
    p = sworn_partner(c)
    if not p:
        return {"success": False, "message": "你并无结拜兄弟。"}
    if p.location != c.location:
        return {"success": False, "message": f"【{p.name}】不在同场。"}
    day = _day_id()
    data = _load_daily()
    key = f"{c.id}:sworn"
    cur = data.get(key) or {}
    if cur.get("day") != day or cur.get("kind") != "sworn" or cur.get("done"):
        return {"success": False, "message": "今日无待交结义任务。"}
    cur["done"] = True
    data[key] = cur
    _save_daily(data)
    c.karma.add_merit(8)
    p.karma.add_merit(8)
    CharacterRepository.save(c)
    CharacterRepository.save(p)
    for l in links_between(c.id, p.id):
        if l.link_type == "结拜":
            l.strength += 1
            from storage.db import KarmaLinkRepository

            KarmaLinkRepository.save(l)
    return {"success": True, "message": f"【结义】与 {p.name} 同甘共苦，双方功德+8。"}


def mark_graduate_credit(c: Character) -> None:
    """走通秘境后调用：出师考核加分"""
    try:
        d = WorldStateRepository.get(_CREDIT_KEY) or {}
        d[c.id] = time.time()
        WorldStateRepository.set(_CREDIT_KEY, d)
    except Exception:
        pass


def has_graduate_credit(c: Character) -> bool:
    try:
        d = WorldStateRepository.get(_CREDIT_KEY) or {}
        return c.id in d
    except Exception:
        return False


def rebel_master(c: Character, name: str) -> Dict[str, Any]:
    """叛师：断师徒→怨，业力+15，同宗态度恶化"""
    m = _alive(name)
    if not m:
        return {"success": False, "message": f"未寻得【{name}】。"}
    found = False
    from storage.db import KarmaLinkRepository

    for l in links_between(c.id, m.id):
        if l.link_type == "师徒":
            l.link_type = "怨"
            l.note = (l.note or "") + f"；{c.name}叛出师门"
            KarmaLinkRepository.save(l)
            found = True
    if not found:
        return {"success": False, "message": "与对方并无师承。"}
    c.karma.add_sin(15)
    CharacterRepository.save(c)
    try:
        from core.npc_mind import shift_attitude, _is_npc

        for o in CharacterRepository.list_all_alive():
            if o.id in (c.id, m.id):
                continue
            if _is_npc(o) and o.sect and o.sect == m.sect:
                shift_attitude(o, c.id, -20, reason="叛出师门")
    except Exception:
        pass
    try:
        from core.world_channel import WorldChannel
        from core import rumors

        WorldChannel.post(
            "bond",
            f"【叛师】{c.name} 背离【{m.name}】师门，江湖侧目。",
            level="major",
            actor=c.name,
        )
        rumors.add_rumor(
            f"风闻 {c.name} 叛出 {m.name} 门下，同门切齿。",
            origin=c.location,
            tags=["bond", "rebel"],
            truth=0.8,
        )
    except Exception:
        pass
    return {"success": True, "message": f"【叛师】与【{m.name}】恩断义绝，业力+15，同门记恨。"}


def sworn_defense_bonus(attacker: Character, defender: Character) -> float:
    """被除凶/血煞者其结拜兄弟同场 → 防守方（或攻方友军）额外 5% 已在 combat；此处给被攻击者友军"""
    p = sworn_partner(defender)
    if p and p.location == defender.location and p.id != attacker.id:
        return 0.05
    return 0.0
