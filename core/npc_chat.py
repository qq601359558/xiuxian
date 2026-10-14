"""
NPC 会话式聊天：连续对话、意愿挂断；挂断后不再调 AI
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository

_KEY = "npc_chat_sessions"
_MEM_KEY = "npc_chat_memory"
_INBOX_KEY = "player_chat_inbox"
_P2P_KEY = "p2p_chat_history"
_MAX_TURNS = 24
_TIMEOUT_S = 900.0  # 15 分钟无消息自动散
_MAX_MSG_LEN = 200
_MEM_MAX_PAIRS = 3
_MEM_TTL_S = 7 * 86400.0


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


def _p2p_pair_key(id_a: str, id_b: str) -> str:
    return f"{min(id_a, id_b)}::{max(id_a, id_b)}"


def get_p2p_history(id_a: str, id_b: str, limit: int = 30) -> List[Dict[str, Any]]:
    try:
        data = WorldStateRepository.get(_P2P_KEY) or {}
        pair = _p2p_pair_key(id_a, id_b)
        return list(data.get(pair) or [])[-limit:]
    except Exception:
        return []


def deliver_player_message(sender: Character, receiver: Character, text: str) -> Dict[str, Any]:
    """真人玩家向真人玩家传音：零 AI 调用，消息双向落账，写入接收方识海信箱"""
    now = time.time()
    msg_item = {
        "from_id": sender.id,
        "from_name": sender.name,
        "to_id": receiver.id,
        "to_name": receiver.name,
        "text": text,
        "ts": now,
        "who": sender.name,
    }
    # 1. 记入双人 P2P 共享对话历史
    try:
        p2p_all = WorldStateRepository.get(_P2P_KEY) or {}
        pair = _p2p_pair_key(sender.id, receiver.id)
        history = list(p2p_all.get(pair) or [])
        history.append(msg_item)
        p2p_all[pair] = history[-40:]
        WorldStateRepository.set(_P2P_KEY, p2p_all)
    except Exception:
        pass

    # 2. 记入双方在 npc_chat_sessions 中的活跃 session（若存在）
    try:
        d = _load_all()
        # 发送方 session
        rec_sender = d.get(sender.id)
        if rec_sender and rec_sender.get("npc_id") == receiver.id:
            rec_sender.setdefault("messages", []).append({"who": sender.name, "text": text, "ts": now})
            rec_sender["messages"] = rec_sender["messages"][-_MAX_TURNS:]
            rec_sender["updated_at"] = now
            d[sender.id] = rec_sender
        # 接收方 session（若当前打开了针对发送方的会话）
        rec_rcv = d.get(receiver.id)
        if rec_rcv and rec_rcv.get("npc_id") == sender.id:
            rec_rcv.setdefault("messages", []).append({"who": sender.name, "text": text, "ts": now})
            rec_rcv["messages"] = rec_rcv["messages"][-_MAX_TURNS:]
            rec_rcv["updated_at"] = now
            d[receiver.id] = rec_rcv
        _save_all(d)
    except Exception:
        pass

    # 3. 记入接收方的未读识海信箱
    try:
        inbox_all = WorldStateRepository.get(_INBOX_KEY) or {}
        rcv_inbox = list(inbox_all.get(receiver.id) or [])
        rcv_inbox.append({
            "from_name": sender.name,
            "from_id": sender.id,
            "text": text,
            "ts": now,
        })
        inbox_all[receiver.id] = rcv_inbox[-20:]
        WorldStateRepository.set(_INBOX_KEY, inbox_all)
    except Exception:
        pass

    return {"success": True, "msg": msg_item}


def pop_player_inbox(player_id: str) -> List[Dict[str, Any]]:
    """读取并清空玩家的未读传音信箱"""
    try:
        inbox_all = WorldStateRepository.get(_INBOX_KEY) or {}
        msgs = list(inbox_all.get(player_id) or [])
        if msgs:
            inbox_all[player_id] = []
            WorldStateRepository.set(_INBOX_KEY, inbox_all)
        return msgs
    except Exception:
        return []


def peek_player_inbox(player_id: str) -> List[Dict[str, Any]]:
    """只读查看玩家未读信箱"""
    try:
        inbox_all = WorldStateRepository.get(_INBOX_KEY) or {}
        return list(inbox_all.get(player_id) or [])
    except Exception:
        return []


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


def _mem_key(player_id: str, npc_id: str) -> str:
    return f"{player_id}::{npc_id}"


def _load_memory() -> Dict[str, Any]:
    try:
        return WorldStateRepository.get(_MEM_KEY) or {}
    except Exception:
        return {}


def _save_memory(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_MEM_KEY, d)
    except Exception:
        pass


def summarize_session_rule(rec: Dict[str, Any], player: Optional[Character] = None, npc: Optional[Character] = None) -> str:
    """规则摘要（无 AI 也稳定）：提取双方要点"""
    msgs = rec.get("messages") or []
    if not msgs:
        return ""
    who_p = player.name if player else ""
    who_n = npc.name if npc else (rec.get("npc_name") or "")
    p_lines = [m.get("text", "") for m in msgs if (m.get("who") == who_p or (player and m.get("who") == player.name))]
    n_lines = [m.get("text", "") for m in msgs if (m.get("who") == who_n or m.get("who") == rec.get("npc_name"))]
    bits = []
    if p_lines:
        bits.append(f"{who_p or '对方'}曾问/说：{p_lines[0][:24]}…{p_lines[-1][:20] if len(p_lines)>1 else ''}")
    if n_lines:
        bits.append(f"{who_n}曾答：{n_lines[0][:24]}…{n_lines[-1][:20] if len(n_lines)>1 else ''}")
    end = rec.get("end_reason") or ""
    turns = int(rec.get("turns") or len(msgs))
    att = rec.get("final_attitude_delta")
    extra = f"共{turns}回合"
    if att is not None:
        extra += f"，态度Δ{att}"
    if end:
        extra += f"；结果：{str(end)[:24]}"
    return ("；".join(bits) + "；" + extra)[:120]


def summarize_session_ai(
    rec: Dict[str, Any],
    player: Optional[Character] = None,
    npc: Optional[Character] = None,
) -> str:
    """有 AI 时：一句话会话摘要（失败回退规则摘要）"""
    rule = summarize_session_rule(rec, player, npc)
    try:
        from config import ai_available

        if not ai_available():
            return rule
        from ai.gateway import _chat_json
        from ai.play_prompts import npc_chat_summary_prompt

        hist = history_lines(rec, 16)
        prompt = npc_chat_summary_prompt(
            player=player.name if player else rec.get("player_name") or "",
            npc=npc.name if npc else rec.get("npc_name") or "",
            history=hist,
            end_reason=rec.get("end_reason") or "",
        )
        data = _chat_json(prompt)
        if data and data.get("summary"):
            s = str(data["summary"]).strip()[:140]
            if s:
                return s
    except Exception:
        pass
    return rule


def write_chat_memory(
    player: Character,
    npc: Character,
    rec: Dict[str, Any],
    summary: str = "",
) -> Dict[str, Any]:
    """会话结束：写入双方记忆摘要 + 事件账（优先 AI 摘要）"""
    summary = (
        summary
        or summarize_session_ai(rec, player, npc)
        or summarize_session_rule(rec, player, npc)
        or "曾有一席交谈"
    ).strip()[:140]
    now = time.time()
    mem = _load_memory()
    key = _mem_key(player.id, npc.id)
    row = mem.get(key) or {"summaries": []}
    rows = list(row.get("summaries") or [])
    rows.append({"text": summary, "ts": now, "ended": rec.get("end_reason") or ""})
    # 过期裁剪
    rows = [r for r in rows if now - float(r.get("ts") or 0) < _MEM_TTL_S]
    mem[key] = {"summaries": rows[-_MEM_MAX_PAIRS:], "npc_name": npc.name, "player_name": player.name}
    # 反向也记一份（NPC 侧简表）
    rkey = _mem_key(npc.id, player.id)
    rrow = mem.get(rkey) or {"summaries": []}
    rrows = list(rrow.get("summaries") or [])
    rrows.append({"text": summary, "ts": now, "ended": rec.get("end_reason") or ""})
    mem[rkey] = {"summaries": rrows[-_MEM_MAX_PAIRS:], "npc_name": npc.name, "player_name": player.name}
    _save_memory(mem)
    try:
        from core.memory import record_event

        record_event(
            type="CHAT",
            actor=npc,
            target=player,
            summary=f"与{player.name}交谈：{summary[:60]}",
            location=npc.location,
        )
    except Exception:
        pass
    return mem.get(key) or {}


def chat_memory_lines(player_id: str, npc_id: str, limit: int = 2) -> str:
    """下次开口时注入：上次聊过什么"""
    mem = _load_memory()
    row = mem.get(_mem_key(player_id, npc_id)) or {}
    rows = list(row.get("summaries") or [])[-limit:]
    if not rows:
        return ""
    lines = [f"· {r.get('text','')}" for r in rows]
    return "【上次交谈记忆】\n" + "\n".join(lines)


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

    from core.npc_mind import _is_npc
    is_target_npc = _is_npc(npc)
    shared_msgs = []
    if not is_target_npc:
        shared_msgs = get_p2p_history(player.id, npc.id)

    d = _load_all()
    d[player.id] = {
        "npc_id": npc.id,
        "npc_name": npc.name,
        "status": "open",
        "turns": len(shared_msgs),
        "willingness": 100 if not is_target_npc else _init_willingness(npc, player.id),
        "messages": shared_msgs,
        "created_at": now,
        "updated_at": now,
        "end_reason": "",
        "running_attitude_delta": 0,
        "is_player": not is_target_npc,
    }
    _save_all(d)
    return {"success": True, "session": d[player.id], "npc": npc, "is_player": not is_target_npc}


def _init_willingness(npc: Character, player_id: str) -> int:
    """0~100，态度映射"""
    try:
        from core.npc_mind import _is_npc, attitude_toward
        if not _is_npc(npc):
            return 100

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
    # 写入会话摘要记忆（ST 式）
    try:
        if int(rec.get("turns") or 0) >= 2 or len(rec.get("messages") or []) >= 3:
            player = CharacterRepository.get_by_id(player_id)
            npc = CharacterRepository.get_by_id(rec.get("npc_id") or "")
            if player and npc:
                rec["final_attitude_delta"] = int(rec.get("running_attitude_delta") or 0)
                write_chat_memory(player, npc, rec)
    except Exception:
        pass
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

    try:
        from core.tasks import hook_note

        note = hook_note(player, "chat_say")
        if note:
            rec = d.get(player.id) or rec
            rec["task_note"] = note
            d[player.id] = rec
            _save_all(d)
        # 会话两轮 → 日常问安
        if int(rec.get("turns") or 0) >= 2:
            hook_note(player, "chat_rounds")
    except Exception:
        pass

    npc = CharacterRepository.get_by_id(rec.get("npc_id") or "")
    if not npc:
        close_session(player.id, "对方已不在场。", by="system")
        return {"success": False, "message": "对方已不在场，会话终止。", "ended": True}

    from core.npc_mind import _is_npc
    is_target_npc = _is_npc(npc)
    if not is_target_npc:
        deliver_player_message(player, npc, text)

    return {
        "success": True,
        "need_ai": is_target_npc,
        "is_player": not is_target_npc,
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
        rec["running_attitude_delta"] = int(rec.get("running_attitude_delta") or 0) + int(attitude_delta or 0)
    except Exception:
        pass

    if not will_continue or int(rec.get("willingness") or 50) <= 5:
        rec["status"] = "closed"
        rec["end_reason"] = hangup_reason or f"【{rec.get('npc_name')}】似不愿再言，拱手作别。"
        rec["ended_by"] = "npc"
        d[player_id] = rec
        _save_all(d)
        try:
            if int(rec.get("turns") or 0) >= 2 or len(rec.get("messages") or []) >= 3:
                player = CharacterRepository.get_by_id(player_id)
                npc = CharacterRepository.get_by_id(rec.get("npc_id") or "")
                if player and npc:
                    rec["final_attitude_delta"] = int(rec.get("running_attitude_delta") or 0)
                    write_chat_memory(player, npc, rec)
        except Exception:
            pass
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
    try:
        mem = chat_memory_lines(player_id, rec.get("npc_id") or "", limit=2)
        if mem:
            lines.append("")
            lines.append(mem)
    except Exception:
        pass
    return "\n".join(lines)
