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
_ORDER_KEY = "hunt_orders"  # target_id -> order dict（F15 令状态机）
SIN_THRESHOLD = 80
HUNT_TTL_H = 48.0
FLEE_CHANCE = 0.25

# ---- F15 除凶令状态机常量（spec: docs/compose/spec/hunt.md）----
ORDER_OPEN = "OPEN"
ORDER_SETTLED = "SETTLED"
ORDER_EXPIRED = "EXPIRED"
ORDER_DISSOLVED = "DISSOLVED"
ORDER_MAX_HUNTERS = 5  # 单令接令人数上限
ASSIST_MERIT = 15  # 协剿功德（同场接令者，≤ EVENT_EFFECT_CAPS["merit"]=40）
TRACK_REFRESH_SECONDS = 3600.0  # 追凶情报快照刷新间隔


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


# ================= F15：除凶令状态机（令实体层） =================
# 令以凶犯为中心存 hunt_orders（target_id -> order）；hunts KV 继续做猎手侧索引，
# 旧路径（my_target/siege/settle 旧口径）语义不变。发布/过期/消散全部惰性推进。

def _load_orders() -> Dict[str, Any]:
    try:
        d = WorldStateRepository.get(_ORDER_KEY) or {}
        return {str(k): v for k, v in d.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _save_orders(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_ORDER_KEY, d)
    except Exception:
        pass


def _region_of(location: Optional[str]) -> str:
    try:
        from core.market import MarketEngine

        return MarketEngine.region_of(location)
    except Exception:
        return location or ""


def _clear_hunter_records(target_id: str) -> None:
    """清除全部指向 target_id 的猎手侧 hunts 记录（令终态时调用）。"""
    d = _load()
    changed = False
    for hid in list(d.keys()):
        rec = d[hid]
        tid = rec.get("target_id") if isinstance(rec, dict) else rec
        if tid == target_id:
            d.pop(hid, None)
            changed = True
    if changed:
        _save(d)


def _close_order(order: Dict[str, Any], status: str, now: float) -> None:
    order["status"] = status
    order["closed_at"] = now
    _clear_hunter_records(str(order.get("target_id") or ""))


def ensure_order(target: Character, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """惰性发布/推进某凶犯的除凶令。

    - 已有 OPEN 令：过期→EXPIRED、凶犯已死/洗清→DISSOLVED（均清猎手记录）；
      过期后凶犯仍在标记中则立即重新发布新令。
    - 无 OPEN 令且凶犯在标记中：发布新令（同 target 同时至多一 OPEN，结构性去重）。
    返回当前 OPEN 令（dict 副本）；无令可发时返回既有终态令或 None。
    """
    t = now if now is not None else time.time()
    orders = _load_orders()
    order = orders.get(target.id)
    if order and order.get("status") == ORDER_OPEN:
        if t > float(order.get("expires_at") or 0):
            _close_order(order, ORDER_EXPIRED, t)
            orders[target.id] = order
            order = None  # 落入重新发布判断
        elif target.status == CharacterStatus.DEAD or not is_marked(target, t):
            _close_order(order, ORDER_DISSOLVED, t)
            orders[target.id] = order
            _save_orders(orders)
            return dict(order)
        else:
            return dict(order)
    if target.status == CharacterStatus.DEAD or not is_marked(target, t):
        _save_orders(orders)
        return dict(order) if order else None
    fresh = {
        "order_id": f"hunt_{target.id}_{int(t)}",
        "target_id": target.id,
        "target_name": target.name,
        "issued_at": t,
        "expires_at": t + HUNT_TTL_H * 3600,
        "status": ORDER_OPEN,
        "hunters": {},
        "intel_region": _region_of(target.location),
        "intel_at": t,
        "settled_by": None,
        "settled_at": 0.0,
        "closed_at": 0.0,
    }
    orders[target.id] = fresh
    _save_orders(orders)
    return dict(fresh)


def _sweep_orders(now: Optional[float] = None) -> Dict[str, Any]:
    """惰性推进全部 OPEN 令的过期/消散（看板/追凶等访问点调用）。"""
    t = now if now is not None else time.time()
    orders = _load_orders()
    changed = False
    for tid, order in orders.items():
        if order.get("status") != ORDER_OPEN:
            continue
        target = CharacterRepository.get_by_id(tid)
        if t > float(order.get("expires_at") or 0):
            _close_order(order, ORDER_EXPIRED, t)
            changed = True
        elif (not target) or target.status == CharacterStatus.DEAD or not is_marked(target, t):
            _close_order(order, ORDER_DISSOLVED, t)
            changed = True
    if changed:
        _save_orders(orders)
    return orders


def get_order(target_id: str) -> Optional[Dict[str, Any]]:
    o = _load_orders().get(target_id)
    return dict(o) if o else None


def _unregister_from_order(hunter_id: str, target_id: str) -> None:
    """把猎手从某令的登记册摘除（换接他令/弃令共用）。"""
    orders = _load_orders()
    order = orders.get(target_id)
    if order and order.get("status") == ORDER_OPEN and hunter_id in (order.get("hunters") or {}):
        order["hunters"].pop(hunter_id, None)
        _save_orders(orders)


def format_board(limit: int = 12) -> str:
    now = time.time()
    _purge_expired(now)
    _sweep_orders(now)
    rows = []
    for c in CharacterRepository.list_all_alive():
        if c.status == CharacterStatus.DEAD:
            continue
        if is_marked(c):
            ensure_order(c, now)  # F15：看板即发布点（惰性发令）
            rows.append(c)
    rows.sort(key=lambda x: -x.karma.sin_value)
    if not rows:
        return "【除凶榜】天道清朗，暂无血煞缠身之人。"
    lines = [
        f"【除凶榜】血煞或业力≥{SIN_THRESHOLD}者；令限时 {int(HUNT_TTL_H)}h。",
        "接令：/接令（/接除凶）<道号> · /追凶 查区域情报 · /弃令（/弃除凶）· /围剿 <道号> 宣告 · /反悬赏 防身",
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
    # F15：换接他令时先摘除旧令登记（一人一令在令侧同样成立，防协剿误发/白占名额）
    prev = d.get(hunter.id)
    prev_tid = prev.get("target_id") if isinstance(prev, dict) else prev
    if prev_tid and prev_tid != target.id:
        _unregister_from_order(hunter.id, prev_tid)
    # F15：令侧登记（满员拒绝；已在令中者不重复占位）
    order = ensure_order(target, now)
    if order and order.get("status") == ORDER_OPEN:
        hunters = order.get("hunters") or {}
        if hunter.id not in hunters and len(hunters) >= ORDER_MAX_HUNTERS:
            return {
                "success": False,
                "message": (
                    f"【{target.name}】的除凶令接令已满 {ORDER_MAX_HUNTERS} 人，"
                    "天道昭昭，不必拥挤，可另寻凶犯。"
                ),
            }
        if hunter.id not in hunters:
            orders = _load_orders()
            live = orders.get(target.id)
            if live and live.get("status") == ORDER_OPEN:
                live.setdefault("hunters", {})[hunter.id] = now
                _save_orders(orders)
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
            f"限时 {int(HUNT_TTL_H)} 现实小时；/追凶 查其所在区域；同场可 /围剿 {target.name} 宣告。"
        ),
    }


def abandon(hunter: Character) -> Dict[str, Any]:
    d = _load()
    if hunter.id not in d:
        return {"success": False, "message": "你并未接除凶令。"}
    rec = d.pop(hunter.id, None)
    _save(d)
    # F15：同步摘除令侧登记（令本身不因弃令终结）
    try:
        tid = rec.get("target_id") if isinstance(rec, dict) else rec
        if tid:
            orders = _load_orders()
            order = orders.get(tid)
            if order and order.get("status") == ORDER_OPEN and hunter.id in (order.get("hunters") or {}):
                order["hunters"].pop(hunter.id, None)
                _save_orders(orders)
    except Exception:
        pass
    return {"success": True, "message": "【弃令】放下杀心。"}


def track(hunter: Character, now: Optional[float] = None) -> Dict[str, Any]:
    """F15 追凶：区域级情报快照（刷新间隔 TRACK_REFRESH_SECONDS），不给精确地点。"""
    t = now if now is not None else time.time()
    d = _purge_expired(t)
    rec = d.get(hunter.id)
    if not rec:
        return {"success": False, "message": "你未接除凶令。先 /除凶 看榜，再 /接令 <道号>。"}
    tid = rec.get("target_id") if isinstance(rec, dict) else rec
    target = CharacterRepository.get_by_id(tid) if tid else None
    # 惰性推进终态：令过期/消散会连带清掉本猎手记录
    _sweep_orders(t)
    if hunter.id not in _load():
        if target and target.status != CharacterStatus.DEAD and is_marked(target, t):
            ensure_order(target, t)  # 凶犯仍在标记中：为后来者重发新令
        return {
            "success": False,
            "message": "【追凶】此令已作废（凶犯身死、洗清或令已过期），猎手记录已清，可另接新令。",
        }
    if not target or target.status == CharacterStatus.DEAD:
        d = _load()
        d.pop(hunter.id, None)
        _save(d)
        return {"success": False, "message": "【追凶】目标已身死道消，此令作废。"}
    order = ensure_order(target, t)
    if not order or order.get("status") != ORDER_OPEN:
        d = _load()
        d.pop(hunter.id, None)
        _save(d)
        return {"success": False, "message": "【追凶】此令已终结（过期或凶犯洗清），可另接新令。"}
    # 情报快照：过刷新间隔才更新为凶犯当前区域
    orders = _load_orders()
    live = orders.get(target.id) or order
    intel_at = float(live.get("intel_at") or 0)
    if t - intel_at >= TRACK_REFRESH_SECONDS:
        live["intel_region"] = _region_of(target.location)
        live["intel_at"] = t
        orders[target.id] = live
        _save_orders(orders)
        intel_at = t
    age_min = max(0, int((t - intel_at) // 60))
    left_h = max(0.0, float(live.get("expires_at") or 0) - t) / 3600.0
    n_hunters = len(live.get("hunters") or {})
    in_roster = hunter.id in (live.get("hunters") or {})
    roster_line = "你已登记令册（协剿位）" if in_roster else "你未在令册（旧记录接令，协剿不计；可 /弃令 后重接）"
    mark = "血煞" if target.karma.is_blood_marked(t) else "重业"
    msg = (
        f"【追凶】{target.name}（{target.realm.name}·{mark}·业力{target.karma.sin_value}）\n"
        f"· 情报区域：{live.get('intel_region') or '未知'}（{age_min} 分钟前探得，"
        f"每 {int(TRACK_REFRESH_SECONDS // 60)} 分钟刷新；天道只示区域，不泄确切行踪）\n"
        f"· 令状态：进行中 · 接令 {n_hunters}/{ORDER_MAX_HUNTERS} 人 · 余 {left_h:.1f}h · {roster_line}\n"
        "· 同场接令者协剿得功德；亲手诛之者全功。前往该区域后 /同场 寻其踪迹。"
    )
    return {
        "success": True,
        "message": msg,
        "region": live.get("intel_region"),
        "target_id": target.id,
        "hunters": n_hunters,
    }


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
    # QA-02 结算前复核（仅当存在 OPEN 令时；无令实体兼容路径不复核、旧口径逐值
    # 不变，spec 验收 6）：与 _sweep_orders 同口径——过期优先（走下方 EXPIRED
    # 分支，旧赏照发，M3 口径不变）；未过期但目标已洗清（不再 is_marked）→
    # 令走 DISSOLVED，且除凶通道旧赏（功德/业力消解）不发——旧赏是「除凶」
    # 之赏，目标已非凶犯。注意：此处不以 victim.status == DEAD 判消散：
    # combat_fate 先置 DEAD 再调本函数，DEAD 是「本次击杀致死」的正常结果，
    # 必须走 SETTLED；「击杀前已死」的消散由看板/追凶/接令访问点的 sweep 负责。
    orders = _load_orders()
    order = orders.get(victim.id)
    order_open = bool(order and order.get("status") == ORDER_OPEN)
    order_expired = bool(order_open and now > float(order.get("expires_at") or 0))
    washed = bool(order_open and not order_expired and not is_marked(victim, now))
    if not washed:
        # QA-01：功德 +40 经 KarmaLedger.add_merit 入账，其账本语义自带业力
        # 消解 40//2=20，与 spec「业力 −20」恰一致——不得再叠加显式扣减
        # （原双路叠加总消解 40，与自报 sin_reduced=20 矛盾）。
        hunter.karma.add_merit(40)
        CharacterRepository.save(hunter)
        # 势力版图（F09）：除凶结算为猎手本宗在事发区域扬名（区域取 victim.location）
        try:
            from core.atlas import AtlasEngine

            AtlasEngine.record_activity(hunter, "hunt", location=victim.location)
        except Exception:
            pass
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
    # QA-02：洗清消散——清全部猎手记录、不发协剿；旧赏已在上方按裁定未发，
    # 返回值如实标注（merit/sin_reduced 均为 0，dissolved=True）。
    assists: List[Dict[str, Any]] = []
    if washed:
        try:
            _close_order(order, ORDER_DISSOLVED, now)
            orders[victim.id] = order
            _save_orders(orders)
        except Exception:
            pass  # 令层异常不炸主流程；消散裁定已定，返回值如实标注
        return {"merit": 0, "sin_reduced": 0, "assists": assists, "dissolved": True}
    # F15：令终态 + 同场协剿分账（旧口径之上的加法层；无令实体时整段跳过）
    try:
        if order_open:
            if order_expired:
                # 结算点同样推进过期：过期令按 EXPIRED 终结，无协剿（击杀者旧赏已在上方按旧口径发放）
                _close_order(order, ORDER_EXPIRED, now)
                orders[victim.id] = order
                _save_orders(orders)
            else:
                live_hunts = _load()
                for hid in list((order.get("hunters") or {}).keys()):
                    if hid in (hunter.id, victim.id):
                        continue
                    # 协剿资格回验：该猎手当前猎手记录须仍指向 victim（防换令后的陈旧登记）
                    rec = live_hunts.get(hid)
                    rec_tid = rec.get("target_id") if isinstance(rec, dict) else rec
                    if rec_tid != victim.id:
                        continue
                    try:
                        c = CharacterRepository.get_by_id(hid)  # 现读现存，防陈旧对象
                        if not c or c.status == CharacterStatus.DEAD:
                            continue
                        if c.location != victim.location:
                            continue
                        c.karma.add_merit(ASSIST_MERIT)
                        CharacterRepository.save(c)
                        assists.append({"name": c.name, "merit": ASSIST_MERIT})
                    except Exception:
                        continue  # 逐人容错：已发名单保留，不因个别人失败清零
                order["status"] = ORDER_SETTLED
                order["settled_by"] = hunter.id
                order["settled_at"] = now
                order["closed_at"] = now
                orders[victim.id] = order
                _save_orders(orders)
                _clear_hunter_records(victim.id)
                if assists:
                    try:
                        from core.world_channel import WorldChannel

                        names = "、".join(a["name"] for a in assists)
                        WorldChannel.post(
                            "hunt",
                            f"【协剿】{names} 同场助 {hunter.name} 诛 {victim.name}，各得功德 {ASSIST_MERIT}。",
                            level="major",
                            actor=hunter.name,
                            location=victim.location,
                        )
                    except Exception:
                        pass
    except Exception:
        pass  # 令层异常不炸旧口径结算；assists 保留已实际发放名单
    return {"merit": 40, "sin_reduced": 20, "assists": assists}


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
