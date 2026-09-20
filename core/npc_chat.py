"""
NPC 会话式聊天：连续对话、意愿挂断；挂断后不再调 AI
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository

_KEY = "npc_chat_sessions"
_MAX_TURNS = 24
_TIMEOUT_S = 900.0  # 15 分钟无消息自动散
_MAX_MSG_LEN = 200


def _load_all() -> Dict[str, Any]:
    try:
        return WorldStateRepository.get(_KEY) or {}
    except Exception:
        return {}


def _save_all(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, d)
    except Exception:
        pass


def _session_id(player_id: str, npc_id: str) -> str:
    return f"{player_id}::{npc_id}"


def get_session(player_id: str) -> Optional[Dict[str, Any]]:
    d = _load_all()
    rec = d.get(player_id)
    if not rec:
        return None
    if rec.get("status") != "open":
        return None
    if time.time() - float(rec.get("updated_at") or 0) > _TIMEOUT_S:
        rec["status"] = "timeout"
        rec["end_reason"] = "久候无言，对方拱手离去。"
        d[player_id] = rec
        _save_all(d)
        return None
    return rec


def open_session(player: Character, npc: Character) -> Dict[str, Any]:
    now = time.time()
    if player.id == npc.id:
        return {"success": False, "message": "不可与自己交谈。"}
    if npc.status == CharacterStatus.DEAD or npc.lifespan.is_dead():
        return {"success": False, "message": f"【{npc.name}】已坐化。"}
    if npc.status == CharacterStatus.CAPTURED:
        return {"success": False, "message": f"【{npc.name}】已被擒，无心应答。"}
    if player.status == CharacterStatus.MEDITATING:
        return {"success": False, "message": "闭关锁门，不可交谈。"}
    if player.location != npc.location:
        return {
            "success": False,
            "message": f"【{npc.name}】不在【{player.location}】，无法当面交谈。",
        }
    d = _load_all()
    d[player.id] = {
        "npc_id": npc.id,
        "npc_name": npc.name,
        "status": "open",
        "turns": 0,
        "willingness": _init_willingness(npc, player.id),
        "messages": [],
        "created_at": now,
        "updated_at": now,
        "end_reason": "",
    }
    _save_all(d)
    return {"success": True, "session": d[player.id], "npc": npc}


def _init_willingness(npc: Character, player_id: str) -> int:
    """0~100，态度映射"""
    try:
        from core.npc_mind import attitude_toward

        att = attitude_toward(npc, player_id)
        v = int(att.get("value") or 0)
        return max(15, min(95, 50 + v))
    except Exception:
        return 50


def close_session(player_id: str, reason: str, by: str = "player") -> Optional[Dict[str, Any]]:
    d = _load_all()
    rec = d.get(player_id)
    if not rec:
        return None
    rec["status"] = "closed"
    rec["end_reason"] = reason
    rec["ended_by"] = by
    rec["updated_at"] = time.time()
    d[player_id] = rec
    _save_all(d)
    return rec


def history_lines(rec: Dict[str, Any], limit: int = 12) -> str:
    msgs = rec.get("messages") or []
    lines = []
    for m in msgs[-limit:]:
        who = m.get("who") or "?"
        lines.append(f"{who}：{m.get('text','')}")
    return "\n".join(lines)


def player_say(player: Character, text: str) -> Dict[str, Any]:
    """
    玩家在会话中发言。
    - 无会话 → 提示先 /交谈
    - 会话已关 → 不调 AI，直接拒绝
    - 有会话 → 追加消息，返回需要 AI 回复的上下文
    """
    text = (text or "").strip()[:_MAX_MSG_LEN]
    if not text:
        return {"success": False, "message": "你想说什么？"}
    rec = get_session(player.id)
    if not rec:
        d = _load_all()
        old = d.get(player.id) or {}
        if old.get("status") in ("closed", "timeout"):
            return {
                "success": False,
                "message": (
                    f"【会话已终】{old.get('end_reason') or '对方已不愿再谈。'}\n"
                    f"如需再谈，请重新 /交谈 {old.get('npc_name') or ''}。"
                ),
                "ended": True,
            }
        return {"success": False, "message": "当前没有进行中的交谈。先 /交谈 <道号>。"}

    msgs = rec.get("messages") or []
    msgs.append({"who": player.name, "text": text, "ts": time.time()})
    rec["messages"] = msgs[-_MAX_TURNS:]
    rec["turns"] = int(rec.get("turns") or 0) + 1
    rec["updated_at"] = time.time()
    d = _load_all()
    d[player.id] = rec
    _save_all(d)

    npc = CharacterRepository.get_by_id(rec.get("npc_id") or "")
    if not npc:
        close_session(player.id, "对方已不在场。", by="system")
        return {"success": False, "message": "对方已不在场，会话终止。", "ended": True}
    return {
        "success": True,
        "need_ai": True,
        "session": rec,
        "npc": npc,
        "player_text": text,
    }


def apply_npc_reply(
    player_id: str,
    line: str,
    will_continue: bool,
    attitude_delta: int = 0,
    hangup_reason: str = "",
) -> Dict[str, Any]:
    """写入 NPC 回复；will_continue=False 则关闭会话"""
    d = _load_all()
    rec = d.get(player_id)
    if not rec:
        return {"success": False, "message": "会话已不存在。"}
    line = (line or "").strip()[:_MAX_MSG_LEN] or "（对方沉默）"
    msgs = rec.get("messages") or []
    msgs.append({"who": rec.get("npc_name") or "对方", "text": line, "ts": time.time()})
    rec["messages"] = msgs[-_MAX_TURNS:]
    rec["updated_at"] = time.time()

    try:
        w = int(rec.get("willingness") or 50)
        w = max(0, min(100, w + int(attitude_delta or 0) - (0 if will_continue else 20)))
        rec["willingness"] = w
    except Exception:
        pass

    if not will_continue or int(rec.get("willingness") or 50) <= 5:
        rec["status"] = "closed"
        rec["end_reason"] = hangup_reason or f"【{rec.get('npc_name')}】似不愿再言，拱手作别。"
        rec["ended_by"] = "npc"
        d[player_id] = rec
        _save_all(d)
        return {
            "success": True,
            "line": line,
            "ended": True,
            "message": line + "\n" + rec["end_reason"] + "\n（继续发送将不会得到回应；可重新 /交谈）",
        }

    d[player_id] = rec
    _save_all(d)
    return {"success": True, "line": line, "ended": False, "message": line}


def local_hangup_or_reply(npc: Character, player: Character, rec: Dict[str, Any]) -> Dict[str, Any]:
    """无 AI 时：按性格/态度本地一句，并可能挂断"""
    pers = ""
    try:
        from core.npc_mind import ensure_mind

        pers = (ensure_mind(npc) or {}).get("personality") or ""
    except Exception:
        pers = ""
    w = int(rec.get("willingness") or 50)
    turns = int(rec.get("turns") or 0)
    # 越聊越不耐烦
    if turns >= 8 or w < 25:
        return {
            "line": f"「{npc.name}」摆手：「今日便到此吧。」",
            "will_continue": False,
            "hangup_reason": f"【{npc.name}】无意再谈。",
            "attitude_delta": -2,
        }
    if "记仇" in pers or "好斗" in pers:
        line = f"「{npc.name}」冷哼一声：「有话快说。」"
    elif "市侩" in pers or "贪" in pers:
        line = f"「{npc.name}」搓了搓手：「道友可是有买卖？」"
    elif "淡泊" in pers or "清高" in pers:
        line = f"「{npc.name}」淡淡道：「嗯。」"
    else:
        line = f"「{npc.name}」看向你：「然后呢？」"
    return {"line": line, "will_continue": True, "attitude_delta": 0}


def format_chat_panel(player_id: str) -> str:
    rec = get_session(player_id)
    if not rec:
        d = _load_all()
        old = d.get(player_id) or {}
        if old.get("status") in ("closed", "timeout"):
            return f"【会话已终】{old.get('end_reason') or ''}\n可重新 /交谈 <道号>。"
        return "当前无交谈。/交谈 <道号> 开启会话；会话中用 /说 <内容>。"
    lines = [
        f"【交谈中】{rec.get('npc_name')} · 续聊意愿 {rec.get('willingness')}",
        "（/说 <内容> 继续 · /挂断 结束）",
        "---",
        history_lines(rec, 16),
    ]
    return "\n".join(lines)
