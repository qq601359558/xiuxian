"""
同场插话：群聊式旁听 NPC 一两句
参考 ST group chat 的轻量版：规则选人 + 人设语气，可选 AI 一句
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository

# 性格/职分更爱插话
_BANTER_BIAS = {
    "伙计": 0.55,
    "牙人": 0.50,
    "弟子": 0.40,
    "市侩圆滑": 0.45,
    "莽撞好斗": 0.35,
    "豪爽仗义": 0.35,
    "谨慎多疑": 0.12,
    "淡泊避世": 0.08,
    "清高自持": 0.10,
}

_BASE_P = 0.18
_MAX_BANTER = 2
_COOLDOWN_KEY_PREFIX = "banter_cd"


def _is_npc(c: Character) -> bool:
    uid = str(getattr(c, "user_id", "") or "")
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def list_bystanders(location: str, exclude_ids: Optional[List[str]] = None, limit: int = 6) -> List[Character]:
    exclude_ids = exclude_ids or []
    out = []
    try:
        for c in CharacterRepository.list_all_alive():
            if c.status == CharacterStatus.DEAD or c.status == CharacterStatus.CAPTURED:
                continue
            if c.location != location:
                continue
            if c.id in exclude_ids:
                continue
            if not _is_npc(c):
                continue
            out.append(c)
            if len(out) >= limit:
                break
    except Exception:
        return []
    return out


def _persona_chance(npc: Character) -> float:
    try:
        from core.npc_personas import get_persona
        from core.npc_mind import ensure_mind

        p = get_persona(npc) or {}
        mind = ensure_mind(npc) or {}
        role = p.get("role") or ""
        pers = mind.get("personality") or ""
        return float(_BANTER_BIAS.get(role, _BASE_P) + _BANTER_BIAS.get(pers, 0.0))
    except Exception:
        return _BASE_P


def _local_banter_line(npc: Character, player: Character, topic: str) -> str:
    from core.npc_personas import example_lines, get_persona

    ex = example_lines(npc)
    p = get_persona(npc) or {}
    catch = p.get("catch") or ""
    role = p.get("role") or ""
    topic = (topic or "")[:24]
    if "伙计" in role:
        return f"「{npc.name}」擦着桌子凑近：「二位聊的可是{topic or '坊市'}？小的耳朵尖着呢。」"
    if "牙人" in role:
        return f"「{npc.name}」压低声音：「这事儿嘛……道友若是想打听，可得另算。」"
    if "弟子" in role:
        return f"「{npc.name}」竖起耳朵：「前辈说的可是真的？我也想听一耳朵。」"
    if "掌柜" in role:
        return f"「{npc.name}」拨着算盘头也不抬：「店小人杂，二位说话注意些。」"
    if "魔修" in role or "魔" in (npc.sect or ""):
        return f"「{npc.name}」嗤笑一声：「有意思，接着说。」"
    if catch:
        return f"「{npc.name}」在一旁道：「{catch}」"
    if ex:
        sample = str(ex[0]).strip("「」\"'")
        return f"「{npc.name}」插话：「{sample}」"
    return f"「{npc.name}」侧目望来，未置可否。"


def _ai_banter_line(npc: Character, player: Character, main_npc: Character, transcript_tail: str) -> Optional[str]:
    try:
        from config import ai_available, local_ai_allowed

        if not ai_available():
            return None
        from core.npc_personas import character_card_block
        from ai.gateway import _chat_json

        card = character_card_block(npc)
        prompt = (
            "你是修仙世界同场旁听的 NPC，别人在交谈，你偶尔插一句。只输出 JSON。\n"
            + card + "\n"
            f"你是 {npc.name}（{npc.realm.name}）\n"
            f"场上主谈：{main_npc.name} 与 {player.name}\n"
            f"最近对话：\n{transcript_tail[-200:]}\n"
            "插话须符合人设，15~40字，不抢主谈风头，不改设定。\n"
            f"{'只输出 JSON，不要解释。'}\n"
            '输出：{"line":"插话"}'
        )
        data = _chat_json(prompt)
        if data and data.get("line"):
            return str(data["line"])[:80]
    except Exception:
        return None
    return None


def maybe_banter(
    player: Character,
    main_npc: Character,
    transcript_tail: str = "",
    *,
    force: bool = False,
    chance_scale: float = 1.0,
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    返回旁听插话列表：[{who, npc_id, line, source}]
    规则选人；AI 可选一句；无 AI 用本地人设句。
    force=True 时跳过冷却，并至少产出 1 条（便于测试/演出）。
    """
    t = now if now is not None else time.time()
    loc = main_npc.location or player.location
    if not loc:
        return []
    candidates = list_bystanders(loc, exclude_ids=[player.id, main_npc.id], limit=8)
    if not candidates:
        return []
    lines: List[Dict[str, Any]] = []
    try:
        from storage.db import WorldStateRepository

        cd = WorldStateRepository.get("banter_cd") or {}
        cd = {k: v for k, v in cd.items() if t - float(v) < 180.0}
    except Exception:
        cd = {}
    # force：优先职分爱插话者
    if force:
        candidates = sorted(candidates, key=lambda c: -_persona_chance(c))
    for npc in candidates:
        if len(lines) >= _MAX_BANTER:
            break
        if npc.id in cd and not force:
            continue
        p = min(0.75, _persona_chance(npc) * max(0.1, chance_scale))
        if not force and random.random() > p:
            continue
        source = "local"
        line = _ai_banter_line(npc, player, main_npc, transcript_tail)
        if line:
            source = "ai"
        else:
            line = _local_banter_line(npc, player, transcript_tail[-20:])
        lines.append(
            {
                "who": npc.name,
                "npc_id": npc.id,
                "line": line[:100],
                "source": source,
                "location": loc,
            }
        )
        cd[npc.id] = t
        if force and len(lines) >= 1:
            break
    try:
        from storage.db import WorldStateRepository

        WorldStateRepository.set("banter_cd", cd)
    except Exception:
        pass
    return lines


def format_banter(lines: List[Dict[str, Any]]) -> str:
    if not lines:
        return ""
    parts = [f"【同场】{b.get('who')}：{b.get('line')}" for b in lines]
    return "\n".join(parts)


def append_banter_to_session(player_id: str, lines: List[Dict[str, Any]]) -> None:
    if not lines:
        return
    try:
        from core import npc_chat

        d = npc_chat._load_all()
        rec = d.get(player_id)
        if not rec:
            return
        msgs = rec.get("messages") or []
        for b in lines:
            msgs.append({"who": b.get("who"), "text": b.get("line"), "ts": time.time(), "kind": "banter"})
        rec["messages"] = msgs[-npc_chat._MAX_TURNS:]
        rec["updated_at"] = time.time()
        d[player_id] = rec
        npc_chat._save_all(d)
    except Exception:
        pass
