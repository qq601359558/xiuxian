"""
宗门贡献 · 兑换 · 日环
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from config import ITEM_CATALOG, MARKET_SELL_BACK_RATE, SECTS_CONFIG
from storage.db import WorldStateRepository, CharacterRepository
from core.content_pack import (
    EXCHANGE_SHOP,
    RARE_SHOP,
    THEME_POOL,
)

_RING_KEY = "sect_ring"


def _day_id(now: Optional[float] = None) -> str:
    t = now if now is not None else time.time()
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _load_ring() -> Dict[str, Any]:
    try:
        return WorldStateRepository.get(_RING_KEY) or {}
    except Exception:
        return {}


def _save_ring(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_RING_KEY, d)
    except Exception:
        pass


def _streak_key(c: Character) -> str:
    return f"sect_streak:{c.id}"


def get_streak(c: Character) -> int:
    try:
        rec = WorldStateRepository.get(_streak_key(c)) or {}
        if isinstance(rec, int):
            return rec
        # 昨日未完成则重置
        last = rec.get("day") or ""
        if last and last != _day_id():
            # 昨天是否完成由 last_done_day 判断：若 last != today 且 last != yesterday 算断
            from datetime import datetime, timedelta

            today = datetime.strptime(_day_id(), "%Y-%m-%d").date()
            yest = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            if last not in (yest, _day_id()):
                _set_streak(c, 0)
                return 0
        return int(rec.get("n") or 0)
    except Exception:
        return 0


def _set_streak(c: Character, n: int) -> None:
    try:
        WorldStateRepository.set(
            _streak_key(c), {"n": max(0, int(n)), "day": _day_id()}
        )
    except Exception:
        pass


def ensure_daily_ring(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
    day = _day_id(now)
    data = _load_ring()
    cur = data.get(c.id) or {}
    if cur.get("day") != day or not c.sect:
        import random as _r

        themes = _r.sample(THEME_POOL, k=min(3, len(THEME_POOL)))
        cur = {
            "day": day,
            "sect": c.sect,
            "themes": themes,
            "accepted": None,  # 主题 id
            "done": False,
            "bonus_claimed": False,
            "lore": "",
        }
        data[c.id] = cur
        _save_ring(data)
    return cur


def accept_theme(c: Character, idx: int, now: Optional[float] = None) -> Dict[str, Any]:
    if not c.sect:
        return {"success": False, "message": "散修无宗门日环。"}
    ensure_daily_ring(c, now)
    data = _load_ring()
    cur = data.get(c.id) or {}
    themes = cur.get("themes") or []
    if not (1 <= idx <= len(themes)):
        return {"success": False, "message": f"用法：/接宗门环 1~{len(themes)}"}
    if cur.get("accepted"):
        return {"success": False, "message": "今日已接过宗门环。"}
    th = themes[idx - 1]
    cur["accepted"] = th["id"]
    cur["hook"] = th["hook"]
    cur["label"] = th["label"]
    lore = th.get("lore", "")
    try:
        from core import ai_flavor

        lore = ai_flavor.polish_ring_accept(c.sect or "", th["label"], lore, who=c.name) or lore
    except Exception:
        pass
    cur["lore"] = lore
    data[c.id] = cur
    _save_ring(data)
    return {
        "success": True,
        "hook": th["hook"],
        "message": f"【接环】{th['label']}\n{lore}\n完成后系统自动记功；/宗门环 查看。",
    }


def sync_ring(c: Character, kind: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """kind: explore|donate|visit|hunt"""
    if not c.sect:
        return None
    ensure_daily_ring(c, now)
    data = _load_ring()
    cur = data.get(c.id) or {}
    if not cur.get("accepted") or cur.get("done"):
        return None
    if cur.get("hook") != kind:
        return None
    cur["done"] = True
    c.sect_contribution += 8
    c.karma.add_merit(2)
    c.spirit_stones += 50
    streak = get_streak(c) + 1
    _set_streak(c, streak)
    bonus_msg = ""
    gold = 50
    if streak == 3:
        c.sect_contribution += 15
        c.spirit_stones += 120
        gold += 120
        bonus_msg = " 连续三日勤勉，额外贡献+15、灵石+120！稀有兑换已解锁。"
    elif streak == 7:
        c.sect_contribution += 40
        c.spirit_stones += 300
        gold += 300
        bonus_msg = " 连续七日不辍，额外贡献+40、灵石+300！"
    data[c.id] = cur
    _save_ring(data)
    CharacterRepository.save(c)
    return {
        "bonus": streak in (3, 7),
        "kind": kind,
        "streak": streak,
        "gold": gold,
        "msg": (
            f"【宗门日环】完成「{cur.get('label')}」，贡献+8、灵石+50"
            f"（现贡献 {c.sect_contribution} / 灵石 {c.spirit_stones}），连环 {streak} 日。{bonus_msg}"
        ),
    }


def format_ring(c: Character) -> str:
    if not c.sect:
        return "散修无宗门日环。可 /拜入 <宗门>。"
    cur = ensure_daily_ring(c)
    streak = get_streak(c)
    lines = [
        f"【宗门日环】{c.sect} · 贡献 {c.sect_contribution} · 连环 {streak} 日",
        f"日期：{cur.get('day')}",
    ]
    themes = cur.get("themes") or []
    if not cur.get("accepted"):
        lines.append("今日主题（三选一，/接宗门环 <n>）：")
        for i, th in enumerate(themes, 1):
            lines.append(f"  {i}. {th.get('label')}")
    else:
        mark = "✓" if cur.get("done") else "○"
        lines.append(f"已接：{mark} {cur.get('label')}")
        if cur.get("lore"):
            lines.append(f"  「{cur.get('lore')}」")
    if streak >= 3:
        lines.append("稀有兑换已解锁：/兑换")
    else:
        lines.append(f"连环 3 日解锁稀有兑换（现 {streak}）。")
    lines.append("完成主题环：贡献+8、灵石+50；连环3日再+120，7日再+300。")
    return "\n".join(lines)


def donate_item(c: Character, item_name: str, qty: int = 1) -> Dict[str, Any]:
    if not c.sect:
        return {"success": False, "message": "散修不可上交宗门。"}
    if qty < 1:
        return {"success": False, "message": "数量至少 1。"}
    if c.inventory.count(item_name) < qty:
        # 模糊
        hit = next((n for n in c.inventory if item_name and item_name in n), None)
        if not hit or c.inventory.count(hit) < qty:
            return {"success": False, "message": f"随身并无足够的【{item_name}】。"}
        item_name = hit
    cfg = ITEM_CATALOG.get(item_name, {"price": 20})
    gain = max(1, int(cfg.get("price", 20) * MARKET_SELL_BACK_RATE / 10)) * qty
    for _ in range(qty):
        c.inventory.remove(item_name)
    c.sect_contribution += gain
    CharacterRepository.save(c)
    res = sync_ring(c, "donate")
    extra = ("\n" + res["msg"]) if res else ""
    return {
        "success": True,
        "gain": gain,
        "message": f"【上交】献上【{item_name}】×{qty}，贡献 +{gain}（现 {c.sect_contribution}）。{extra}",
    }


def format_shop() -> str:
    lines = ["【贡献兑换】/兑换 <名>"]
    for name, price in EXCHANGE_SHOP.items():
        lines.append(f"· {name} — {price} 贡献")
    streak_gated = []
    try:
        # streak 展示需要角色，此处仅列稀有名
        lines.append("稀有（连环3日解锁）：")
        for name, cfg in RARE_SHOP.items():
            lines.append(f"· {name} — {cfg['price']} 贡献（需连环≥{cfg['need_streak']}）")
    except Exception:
        pass
    return "\n".join(lines)


def exchange(c: Character, item_name: str) -> Dict[str, Any]:
    if not c.sect:
        return {"success": False, "message": "散修不可兑换。"}
    # 模糊匹配普通+稀有
    all_names = list(EXCHANGE_SHOP.keys()) + list(RARE_SHOP.keys())
    if item_name not in all_names:
        for k in all_names:
            if item_name and (item_name in k or k in item_name):
                item_name = k
                break
    if item_name in RARE_SHOP:
        cfg = RARE_SHOP[item_name]
        if get_streak(c) < cfg["need_streak"]:
            return {
                "success": False,
                "message": f"【{item_name}】需宗门连环 ≥{cfg['need_streak']} 日（现 {get_streak(c)}）。",
            }
        price = cfg["price"]
    elif item_name in EXCHANGE_SHOP:
        price = EXCHANGE_SHOP[item_name]
    else:
        return {"success": False, "message": "无此兑换物。/兑换 查看。"}
    if c.sect_contribution < price:
        return {
            "success": False,
            "message": f"贡献不足：需 {price}，现 {c.sect_contribution}。",
        }
    c.sect_contribution -= price
    cfg = ITEM_CATALOG.get(item_name) or {}
    if cfg.get("kind") == "array":
        if item_name not in c.arrays:
            c.arrays.append(item_name)
        else:
            c.inventory.append(item_name)
    else:
        c.inventory.append(item_name)
    CharacterRepository.save(c)
    return {
        "success": True,
        "message": f"【兑换】以 {price} 贡献换得【{item_name}】。余 {c.sect_contribution}。",
    }


def sect_powerboard() -> str:
    """宗门实力只读条（成员境界加权）"""
    from core.models import CharacterStatus as CS

    lines = ["【宗门实力】（人数×境界，只读）"]
    scores: Dict[str, float] = {k: 0.0 for k in SECTS_CONFIG}
    counts: Dict[str, int] = {k: 0 for k in SECTS_CONFIG}
    try:
        for c in CharacterRepository.list_all_alive():
            if c.sect and c.sect in scores and c.status != CS.DEAD:
                scores[c.sect] += 1.0 + c.realm.tier * 1.5 + c.realm.sub_tier * 0.3
                counts[c.sect] += 1
    except Exception:
        pass
    mx = max(scores.values()) if scores else 1.0
    for name, sc in sorted(scores.items(), key=lambda x: -x[1]):
        bar_n = int(round(sc / mx * 10)) if mx else 0
        lines.append(f"· {name} {'█' * bar_n}{'░' * (10 - bar_n)}  {counts[name]} 人 · 分 {sc:.0f}")
    return "\n".join(lines)
