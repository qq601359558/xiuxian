"""
同场插话：与交谈主题相关才开口，宁缺毋滥
规则：话题命中 + 职分相关 → 最多 1 人插一句；否则沉默
"""
from __future__ import annotations

import random
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository

# 话题标签 → 关键词
_TOPIC_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "goods": ("丹", "药", "阵", "剑", "符", "价", "灵石", "买", "卖", "货", "坊市", "商会", "寄售"),
    "realm": ("秘境", "古洞", "遗迹", "探险", "挖宝", "落霞", "黑风", "万星", "洞天"),
    "sect": ("宗门", "山门", "掌门", "长老", "戒律", "门规", "拜入", "叛门", "同门"),
    "combat": ("斗法", "杀", "仇", "血", "凶", "除凶", "悬赏", "围剿", "伏击"),
    "cultivate": ("修炼", "突破", "闭关", "天劫", "筑基", "金丹", "功法", "灵气"),
    "world": ("天道", "大劫", "纪元", "天机", "世道", "血煞", "大势"),
}

# 职分/性格 → 擅长的话题（命中才更有资格插话）
_ROLE_TOPICS: Dict[str, Set[str]] = {
    "掌柜": {"goods", "realm", "world"},
    "伙计": {"goods", "world", "combat"},
    "会长": {"goods", "sect", "world"},
    "牙人": {"goods", "realm", "combat", "world"},
    "镖头": {"combat", "goods", "realm"},
    "弟子": {"cultivate", "sect", "realm"},
    "执事": {"sect", "combat", "world"},
    "长老": {"sect", "cultivate", "world"},
    "掌门": {"sect", "cultivate", "world"},
    "散修": {"realm", "combat", "goods", "cultivate"},
    "妖修": {"combat", "realm"},
    "魔修": {"combat", "world"},
    "宗主": {"sect", "combat", "world"},
}

_PERSONA_TOPIC_BOOST = {
    "市侩圆滑": {"goods"},
    "莽撞好斗": {"combat"},
    "豪爽仗义": {"combat", "sect"},
    "谨慎多疑": {"goods", "world"},
    "清高自持": {"cultivate", "sect"},
    "淡泊避世": set(),
}

_BASE_P = 0.08
_MAX_BANTER = 1
_NPC_COOLDOWN_S = 600.0
_LOC_COOLDOWN_S = 240.0
_CD_KEY = "banter_cd"


def _is_npc(c: Character) -> bool:
    uid = str(getattr(c, "user_id", "") or "")
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def extract_topics(text: str) -> Set[str]:
    t = text or ""
    hits: Set[str] = set()
    for topic, words in _TOPIC_KEYWORDS.items():
        if any(w in t for w in words):
            hits.add(topic)
    return hits


def _topic_brief(text: str, topics: Set[str]) -> str:
    """从对话里截取与话题相关的短语，供台词回扣"""
    t = (text or "").replace("\n", " ")
    words: List[str] = []
    for topic in topics:
        for kw in _TOPIC_KEYWORDS.get(topic, ()):  # type: ignore
            if kw in t and kw not in words:
                words.append(kw)
        if len(words) >= 3:
            break
    if words:
        return "、".join(words[:3])
    # 兜底：取最后一句人话里的名词性片段
    parts = re.split(r"[。！？\n]", t)
    tail = (parts[-2] if len(parts) >= 2 else parts[-1]) if parts else ""
    tail = re.sub(r"^[^：:]{0,6}[：:]", "", tail).strip()
    return tail[:16]


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


def _npc_profile(npc: Character) -> Tuple[str, str, Set[str]]:
    role = ""
    pers = ""
    topics: Set[str] = set()
    try:
        from core.npc_personas import get_persona
        from core.npc_mind import ensure_mind

        p = get_persona(npc) or {}
        role = p.get("role") or ""
        mind = ensure_mind(npc) or {}
        pers = mind.get("personality") or ""
        topics = set(_ROLE_TOPICS.get(role) or set())
        for k, v in _PERSONA_TOPIC_BOOST.items():
            if k in pers:
                topics |= v
        if not topics:
            topics = {"world"}
    except Exception:
        topics = {"world"}
    return role, pers, topics


def relevance_score(npc: Character, topics: Set[str]) -> float:
    """0=无关；越高越适合插话"""
    if not topics:
        return 0.0
    _role, _pers, ntopics = _npc_profile(npc)
    overlap = topics & ntopics
    if not overlap:
        return 0.0
    return 0.35 + 0.2 * len(overlap)


def _local_banter_line(npc: Character, role: str, topics: Set[str], brief: str) -> str:
    """必须扣住话题；禁止空泛口头禅刷屏"""
    name = npc.name
    brief = (brief or "").strip() or "此事"
    if "goods" in topics:
        if "伙计" in role:
            return f"「{name}」擦桌凑近：「二位说的是{brief}？柜上若有，我替您取。」"
        if "掌柜" in role:
            return f"「{name}」拨着算盘：「若论{brief}，本店货真，童叟无欺。」"
        if "牙人" in role:
            return f"「{name}」压低声：「打听{brief}？行情我熟，另算。」"
        return f"「{name}」插话：「{brief}的行情，坊市里各有说法。」"
    if "realm" in topics:
        return f"「{name}」道：「{brief}一带，机缘与杀劫并存，去时多带一双眼睛。」"
    if "sect" in topics:
        return f"「{name}」正色：「论及{brief}，当守本分，勿要多嘴惹祸。」"
    if "combat" in topics:
        return f"「{name}」眼神一冷：「说到{brief}……手底下见真章才是。」"
    if "cultivate" in topics:
        return f"「{name}」微微颔首：「{brief}一道，急也无用。」"
    return f"「{name}」低声接了一句：「方才提到{brief}……倒也未必无因。」"


def _ai_banter_line(
    npc: Character,
    player: Character,
    main_npc: Character,
    transcript_tail: str,
    topics: Set[str],
    brief: str,
) -> Optional[str]:
    try:
        from config import ai_available

        if not ai_available():
            return None
        from core.npc_personas import character_card_block
        from ai.gateway import _chat_json

        card = character_card_block(npc)
        topic_cn = "、".join(sorted(topics)) or "闲谈"
        prompt = (
            "你是修仙世界同场旁听 NPC。只在与「当前话题」强相关时插一句。\n"
            + card + "\n"
            f"你是 {npc.name}；主谈：{main_npc.name} 与 {player.name}\n"
            f"当前话题标签：{topic_cn}\n"
            f"话题关键词：{brief}\n"
            f"最近对话：\n{(transcript_tail or '')[-220:]}\n"
            "硬约束：\n"
            "1) 只能议论上述话题，不得另起无关话头，不得客套刷存在感。\n"
            "2) 20~45 字，符合人设；不必每场都显得「听过很多」。\n"
            "3) 若无话可接，输出空 line。\n"
            "只输出 JSON。\n"
            '输出：{"line":""}'
        )
        data = _chat_json(prompt)
        if data and data.get("line"):
            return str(data["line"])[:90]
    except Exception:
        return None
    return None


def _load_cd() -> Dict[str, Any]:
    try:
        raw = WorldStateRepository.get(_CD_KEY) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_cd(cd: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_CD_KEY, cd)
    except Exception:
        pass


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
    旁听插话：与主题相关才可能开口；默认最多 1 条。
    force=True：测试/演出用，仍优先选话题相关者；完全无关则返回空。
    """
    t = now if now is not None else time.time()
    loc = main_npc.location or getattr(player, "location", "") or ""
    if not loc:
        return []
    topics = extract_topics(transcript_tail)
    brief = _topic_brief(transcript_tail, topics)
    # 无明确主题 → 不插话（避免「无关紧要」）
    if not topics and not force:
        return []
    candidates = list_bystanders(loc, exclude_ids=[player.id, main_npc.id], limit=10)
    if not candidates:
        return []
    # 仅保留与话题相关（或 force 时相关分>0）的 NPC
    scored: List[Tuple[float, Character]] = []
    for npc in candidates:
        rel = relevance_score(npc, topics if topics else {"world"})
        if rel <= 0:
            continue
        scored.append((rel, npc))
    if not scored:
        return []
    scored.sort(key=lambda x: -x[0])
    cd = _load_cd()
    now_cd = t
    loc_cd = float(cd.get("_loc") or 0)
    npc_cd = cd.get("npcs") or {}
    if isinstance(npc_cd, dict):
        npc_cd = {k: float(v) for k, v in npc_cd.items() if t - float(v) < _NPC_COOLDOWN_S}
    else:
        npc_cd = {}

    if not force:
        if loc_cd and t - loc_cd < _LOC_COOLDOWN_S:
            return []
        # 总概率：相关度 × 职分系数，整体压低
        lines: List[Dict[str, Any]] = []
        for rel, npc in scored[:3]:
            if npc.id in npc_cd:
                continue
            _role, _pers, _tp = _npc_profile(npc)
            # 伙计/牙人仍稍爱接话，但远低于从前
            boost = 1.4 if _role in ("伙计", "牙人") else 0.9 if _role in ("掌柜", "牙人") else 0.7
            p = min(0.28, rel * boost * max(0.05, chance_scale))
            if random.random() > p:
                continue
            line = _ai_banter_line(npc, player, main_npc, transcript_tail, topics, brief)
            source = "ai" if line else "local"
            if not line:
                line = _local_banter_line(npc, _role, topics or {"world"}, brief)
            lines.append(
                {
                    "who": npc.name,
                    "npc_id": npc.id,
                    "line": line[:100],
                    "source": source,
                    "location": loc,
                    "topics": sorted(topics),
                }
            )
            npc_cd[npc.id] = t
            break  # 只允许一人插话
        if lines:
            cd["_loc"] = t
            cd["npcs"] = npc_cd
            _save_cd(cd)
        return lines

    # force：选最相关一人，写主题台词
    rel, npc = scored[0]
    role, _pers, _tp = _npc_profile(npc)
    line = _ai_banter_line(npc, player, main_npc, transcript_tail, topics, brief)
    source = "ai" if line else "local"
    if not line:
        line = _local_banter_line(npc, role, topics or {"world"}, brief)
    npc_cd[npc.id] = t
    cd["_loc"] = t
    cd["npcs"] = npc_cd
    _save_cd(cd)
    return [
        {
            "who": npc.name,
            "npc_id": npc.id,
            "line": line[:100],
            "source": source,
            "location": loc,
            "topics": sorted(topics),
        }
    ]


def format_banter(lines: List[Dict[str, Any]]) -> str:
    if not lines:
        return ""
    return "\n".join(f"【同场】{b.get('who')}：{b.get('line')}" for b in lines)


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


def reset_banter_cooldowns() -> None:
    try:
        _save_cd({})
    except Exception:
        pass
