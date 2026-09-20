"""
AI 叙事增强层（A 档）：只润色措辞，不改数值。
规则先落账，AI 再「说人话」；失败静默用原文。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from storage.db import WorldStateRepository

# 简易预算：每现实小时 N 次叙事调用
_BUDGET_KEY = "ai_flavor_budget"
_BUDGET_PER_HOUR = 40
_window_start = 0.0
_used = 0
_loaded = False


def _ensure_budget() -> None:
    global _window_start, _used, _loaded
    if _loaded:
        return
    try:
        rec = WorldStateRepository.get(_BUDGET_KEY) or {}
        _window_start = float(rec.get("t") or 0)
        _used = int(rec.get("n") or 0)
    except Exception:
        pass
    _loaded = True


def _consume() -> bool:
    global _window_start, _used, _loaded
    _ensure_budget()
    now = time.time()
    if now - _window_start > 3600:
        _window_start = now
        _used = 0
    if _used >= _BUDGET_PER_HOUR:
        return False
    _used += 1
    try:
        WorldStateRepository.set(_BUDGET_KEY, {"t": _window_start, "n": _used})
    except Exception:
        pass
    return True


def _ask(prompt: str, timeout: float = 12.0) -> Optional[str]:
    """有 AI 且有预算才问；只取一行文本。"""
    try:
        from ai.gateway import _chat_json, ai_ready

        if not ai_ready():
            return None
        if not _consume():
            return None
        data = _chat_json(prompt, timeout=timeout)
        if not data:
            return None
        for k in ("line", "text", "prompt", "narrative", "flavor"):
            if data.get(k):
                return str(data[k])[:180]
        # 任意单字符串字段
        for v in data.values():
            if isinstance(v, str) and len(v) >= 4:
                return v[:180]
    except Exception:
        return None
    return None


def polish_omen_open(title: str, template_prompt: str, loc: str = "", who: str = "") -> str:
    try:
        from ai.play_prompts import omen_open_prompt

        p = omen_open_prompt(title, template_prompt, loc, who)
    except Exception:
        p = (
            "润色修仙奇遇开场，50~70字，只输出 JSON {\"line\":\"...\"}。\n"
            f"标题：{title}；地点：{loc or '野外'}；人物：{who or '一名修士'}。\n"
            f"模板原文（意思不变，文笔可更好）：{template_prompt}"
        )
    out = _ask(p)
    return out or template_prompt


def polish_omen_next(title: str, step_prompt: str, prev_choice: str = "") -> str:
    try:
        from ai.play_prompts import omen_next_prompt

        p = omen_next_prompt(title, step_prompt, prev_choice)
    except Exception:
        p = (
            "续写修仙奇遇下一步，50字内，只输出 JSON {\"line\":\"...\"}。\n"
            f"标题：{title}；上一步选择：{prev_choice or '无'}。\n"
            f"模板：{step_prompt}"
        )
    out = _ask(p)
    return out or step_prompt


def polish_omen_outcome(title: str, choice_label: str, effect_summary: str, who: str = "") -> str:
    try:
        from ai.play_prompts import omen_outcome_prompt

        p = omen_outcome_prompt(title, choice_label, effect_summary, who)
    except Exception:
        p = (
            "写一句奇遇落账判词，40字内，只输出 JSON {\"line\":\"...\"}。\n"
            f"标题：{title}；选择：{choice_label}；落账：{effect_summary}；人物：{who}。\n"
            "不得改数值，只抒写体感。"
        )
    out = _ask(p)
    if out:
        return out
    return f"你选择了「{choice_label}」。{effect_summary}"


def polish_ring_accept(sect: str, label: str, lore: str, who: str = "") -> str:
    try:
        from ai.play_prompts import ring_accept_prompt

        p = ring_accept_prompt(sect, label, lore, who)
    except Exception:
        p = (
            "写一句宗门执事派活的口白，40字内，只输出 JSON {\"line\":\"...\"}。\n"
            f"宗门：{sect}；任务：{label}；原口白：{lore}；弟子：{who}。"
        )
    out = _ask(p)
    return out or lore


def polish_master_task(master: str, disciple: str, label: str) -> str:
    try:
        from ai.play_prompts import master_task_prompt

        p = master_task_prompt(master, disciple, label)
    except Exception:
        p = (
            "写一句师父派师门任务的话，40字内，只输出 JSON {\"line\":\"...\"}。\n"
            f"师父：{master}；弟子：{disciple}；任务：{label}。口吻可严厉或慈和。"
        )
    out = _ask(p)
    return out or f"【{master}】道：{label}"


def twist_rumor(text: str, style: str = "坊间") -> str:
    """把规则传闻扭成更像人话的闲话（truth 已由规则定，不在此改）"""
    try:
        from ai.play_prompts import rumor_twist_prompt

        p = rumor_twist_prompt(text)
    except Exception:
        p = (
            "把下列坊间传闻改写成更口语、带一点添油加醋的闲话，50字内，"
            "只输出 JSON {\"line\":\"...\"}。不要否认已有事实。\n"
            f"原文：{text}"
        )
    out = _ask(p, timeout=10.0)
    return out or text


def polish_hunt_announce(hunter: str, target: str, loc: str = "") -> str:
    try:
        from ai.play_prompts import hunt_announce_prompt

        p = hunt_announce_prompt(hunter, target, loc)
    except Exception:
        p = (
            "写一句围剿号令，40字内，只输出 JSON {\"line\":\"...\"}。\n"
            f"发起人：{hunter}；目标：{target}；地点：{loc}。要正气或杀气。"
        )
    out = _ask(p)
    return out or f"【围剿】{hunter} 号召同道共诛【{target}】。"


def polish_graduation(master: str, disciple: str) -> str:
    try:
        from ai.play_prompts import graduation_prompt

        p = graduation_prompt(master, disciple)
    except Exception:
        p = (
            "写一句出师判词，40字内，只输出 JSON {\"line\":\"...\"}。\n"
            f"师父：{master}；弟子：{disciple}。"
        )
    out = _ask(p)
    return out or f"【出师】{disciple} 拜别 {master}，独闯江湖。"


def polish_npc_sell(npc: str, player: str, item: str, list_price: int, mult: float, loc: str = "", persona: str = "") -> str:
    try:
        from ai.play_prompts import trade_haggle_prompt

        p = trade_haggle_prompt(player, npc, item, list_price, mult, who_speaks="seller", location=loc, persona_seller=persona)
    except Exception:
        return ""
    return _ask(p, timeout=10.0) or ""


def polish_face_trade(a: str, b: str, a_stones: int, b_stones: int, a_items: str, b_items: str, loc: str = "") -> str:
    try:
        from ai.play_prompts import trade_face_offer_prompt

        p = trade_face_offer_prompt(a, b, a_stones, b_stones, a_items, b_items, loc)
    except Exception:
        return ""
    return _ask(p, timeout=10.0) or ""


def polish_auction_bid(bidder: str, item: str, amount: int, prev_leader: str = "", buyout: int = 0) -> str:
    try:
        from ai.play_prompts import auction_bid_prompt

        p = auction_bid_prompt(bidder, item, amount, prev_leader, buyout)
    except Exception:
        return ""
    return _ask(p, timeout=10.0) or ""


def polish_auction_settle(item: str, winner: str, price: int, seller: str, kind: str = "落槌") -> str:
    try:
        from ai.play_prompts import auction_settle_prompt

        p = auction_settle_prompt(item, winner, price, seller, kind)
    except Exception:
        return ""
    return _ask(p, timeout=10.0) or ""


def polish_guild_deal(who: str, action: str, item: str, qty: int, price: int, loc: str = "") -> str:
    try:
        from ai.play_prompts import market_guild_prompt

        p = market_guild_prompt(who, action, item, qty, price, loc)
    except Exception:
        return ""
    return _ask(p, timeout=10.0) or ""


def flavor_ok() -> bool:
    try:
        from ai.gateway import ai_ready

        return ai_ready()
    except Exception:
        return False
