"""
玩家口述门禁：禁止用言行/聊天「创建」地点·人物·物品等专名。
例外：/自创功法（走 art DSL，不在此拦）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# 造物意图关键词（命中即疑似）
_CREATE_VERBS = [
    "建立", "创建", "创建一座", "建造", "筑城", "开宗", "立派", "创立",
    "命名", "取名", "叫做", "称为", "改名为", "自称",
    "我门派叫", "我宗门叫", "我洞府叫", "我府邸叫",
    "收徒.*名为", "收了.*徒弟",
]

_PATTERNS = [
    re.compile(r"(建|创建|建造|筑造|开辟).{0,10}(城|宫|殿|谷|渊|池|园|林|海|窟|崖|峰|岭|关|市|集|山门|洞府|宗|派|坊)"),
    re.compile(r"(命名|取名|叫做|称为|改名为)\s*[「『\"]?([一-鿿]{2,12})"),
    re.compile(r"(开创|创立|开宗|立派).{0,6}(宗|派|门|教)"),
    re.compile(r"(我|本人).{0,4}(门派|宗门|洞府|道场).{0,4}叫\s*[「『\"]?([一-鿿]{2,12})"),
    re.compile(r"(师父|师傅|道侣|弟子|师兄|爱徒).{0,4}(叫|名唤|道号)\s*[「『\"]?([一-鿿]{2,8})"),
    re.compile(r"(炼出|炼制出|得到|获得|发现).{0,6}(丹|剑|甲|珠|镜|印|符|图)"),
    re.compile(r"来到了\s*[「『\"]?([一-鿿]{2,10})[」』\"]?\s*(，|。|$)"),
    re.compile(r"此地(?:名为|叫)\s*[「『\"]?([一-鿿]{2,10})"),
    re.compile(r"有一(?:座|处|口|间)\s*[「『\"]?([一-鿿]{2,10})"),
]

_REJECT_MSG = (
    "【天道不允】不可妄言造物。\n"
    "地点、人物、宗门、灵材法宝等名物，须由天道（AI/GM）落册后方可存在。\n"
    "你可以：使用已有地名（/舆图、/坊市）、描述环境、或走 /自创功法 创一门独门法门。"
)


def _known_sets() -> Tuple[set, set, set]:
    from config import WORLD_LOCATIONS, ITEM_CATALOG, SECTS_CONFIG

    locs = set(WORLD_LOCATIONS.keys())
    items = set(ITEM_CATALOG.keys())
    sects = set(SECTS_CONFIG.keys())
    try:
        from core.npc_roster import ROSTER

        names = {r.get("name") for r in ROSTER}
    except Exception:
        names = set()
    try:
        from storage.db import CharacterRepository

        names |= {c.name for c in CharacterRepository.list_all_alive()[:200]}
    except Exception:
        pass
    return locs, items, sects | names


def looks_like_name_creation(text: str) -> Optional[Dict[str, Any]]:
    """返回命中信息或 None。短句/纯询问不误伤。"""
    t = (text or "").strip()
    if not t or len(t) < 4:
        return None
    if any(t.startswith(p) for p in ("请问", "哪里", "如何", "能否", "是不是")):
        return None
    locs, items, people = _known_sets()
    hits: List[str] = []
    for pat in _PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        # 从所有捕获组里挑「更像专名」的那个（更长、非职衔词）
        role_words = {
            "师父", "师傅", "道侣", "弟子", "师兄", "爱徒", "城", "宫", "殿",
            "谷", "渊", "山门", "洞府", "宗", "派", "坊", "叫", "名唤", "道号",
        }
        cand = ""
        for g in m.groups():
            if not g or not isinstance(g, str):
                continue
            g2 = g.strip("「」『』\"'")
            if not re.fullmatch(r"[一-鿿]{2,12}", g2):
                continue
            if g2 in role_words:
                continue
            if len(g2) > len(cand):
                cand = g2
        if cand:
            if cand in locs or cand in items or cand in people:
                continue
        hits.append(m.group(0)[:24])
    if not hits:
        return None
    return {"hits": hits, "sample": hits[0]}


def reject_player_creation(text: str) -> Optional[Dict[str, Any]]:
    """命中则返回拒绝结果；否则 None。"""
    info = looks_like_name_creation(text)
    if not info:
        return None
    return {
        "success": False,
        "rejected": True,
        "reason": "name_creation",
        "message": _REJECT_MSG,
        "hits": info.get("hits"),
    }
