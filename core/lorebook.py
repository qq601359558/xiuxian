"""
Lorebook：按关键词注入世界知识（参考 SillyTavern WorldInfo 的轻量版）
只进提示词，不改数值。
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character
from config import SECTS_CONFIG, SECRET_REALMS, WORLD_LOCATIONS

# 关键词 → 取 lore 的函数名（按优先级）
_MAX_LORE_CHARS = 360


def _sec() -> str:
    return time.strftime("%H:%M")


def _director_bits() -> List[str]:
    out = []
    try:
        from core.world_director import active_directives, world_modifiers

        mods = world_modifiers()
        if mods.get("blood_tide_locations"):
            out.append("血煞潮地：" + "、".join(mods["blood_tide_locations"][:3]))
        if mods.get("sect_tensions"):
            out.append("宗门不睦：" + "、".join(f"{a}×{b}" for a, b in mods["sect_tensions"][:3]))
        if mods.get("calamity_forecast"):
            out.append("大劫预兆笼罩纪元")
        for d in active_directives()[:2]:
            out.append(f"天道态势：【{d.get('title')}】{str(d.get('narrative') or '')[:40]}")
    except Exception:
        pass
    return out


def _faction_bits() -> List[str]:
    out = []
    try:
        from core.faction import faction_modifiers

        fm = faction_modifiers()
        for s in (fm.get("active_sieges") or [])[:2]:
            out.append(f"宗门围剿：{s.get('sect')}→{s.get('target')} @{s.get('loc')}")
        for a, b in (fm.get("hostile_pairs") or [])[:3]:
            out.append(f"敌对：{a}×{b}")
        if fm.get("n_open_missions"):
            out.append(f"宗门令开放 {fm.get('n_open_missions')} 条")
    except Exception:
        pass
    return out


def _echo_bits() -> List[str]:
    out = []
    try:
        from core.player_echo import echo_modifiers

        em = echo_modifiers()
        if float(em.get("market_panic") or 0) >= 8:
            out.append(f"坊市恐慌{float(em['market_panic']):.0f}")
        for loc, d in (em.get("hot_regions") or [])[:2]:
            out.append(f"凶地 {loc} 危险{float(d):.0f}")
    except Exception:
        pass
    return out


def _legend_bits(n: int = 3) -> List[str]:
    out = []
    try:
        from core.legends import list_legends

        for x in list_legends(limit=n):
            out.append(f"史笔：{x.title} — {x.text[:40]}")
    except Exception:
        pass
    return out


def _rumor_bits(n: int = 2) -> List[str]:
    out = []
    try:
        from core import rumors

        for r in rumors.list_rumors(limit=n):
            t = r.get("text") if isinstance(r, dict) else str(r)
            if t:
                out.append(f"传闻：{str(t)[:40]}")
    except Exception:
        pass
    return out


def _arc_bits() -> List[str]:
    out = []
    try:
        from core.world_arc import active_arcs

        stage_cn = {"prophesy": "预兆", "escalate": "升级", "climax": "决算"}
        for a in active_arcs()[:2]:
            out.append(f"世界弧：[{stage_cn.get(a.get('stage'), a.get('stage'))}] {a.get('title')}")
    except Exception:
        pass
    return out


def collect_world_lore(max_lines: int = 8) -> List[str]:
    """全量世界 lore 池（供关键词命中前的候选）"""
    lines: List[str] = []
    lines.extend(_director_bits())
    lines.extend(_arc_bits())
    lines.extend(_faction_bits())
    lines.extend(_echo_bits())
    lines.extend(_legend_bits())
    lines.extend(_rumor_bits())
    return lines[: max_lines * 2]


def keyword_hits(text: str, extra_keys: Optional[List[str]] = None) -> List[str]:
    """从对话/人名/地点提取应注入的 lore 碎片"""
    blob = (text or "")
    pool = collect_world_lore(max_lines=12)
    hits: List[str] = []
    keys: List[str] = []
    for name in list(SECTS_CONFIG.keys()) + list(SECRET_REALMS.keys()) + list(WORLD_LOCATIONS.keys())[:20]:
        if name and name in blob:
            keys.append(name)
    if extra_keys:
        keys.extend([k for k in extra_keys if k])
    # 地点/秘境相关：从 pool 与配置 desc 拼
    for k in keys:
        if k in SECTS_CONFIG:
            cfg = SECTS_CONFIG[k]
            hits.append(f"【{k}】{cfg.get('alignment','')}·总坛{cfg.get('headquarters')}：{str(cfg.get('rules_tip',''))[:36]}")
        if k in SECRET_REALMS:
            cfg = SECRET_REALMS[k]
            hits.append(f"【{k}】@{cfg.get('location')}：{str(cfg.get('desc',''))[:40]}")
        if k in WORLD_LOCATIONS:
            cfg = WORLD_LOCATIONS[k]
            safe = "安全区" if cfg.get("is_safe") else "凶险地"
            hits.append(f"【{k}】{cfg.get('region','')}·{safe}")
        # pool 中提到该关键词
        for line in pool:
            if k in line and line not in hits:
                hits.append(line)
    # 无关键词时仍给 2 条全服态势（NPC 也应知道大势）
    if not hits:
        hits.extend(pool[:3])
    else:
        for line in pool[:3]:
            if line not in hits:
                hits.append(line)
    # 去重截断
    seen = set()
    out = []
    for h in hits:
        h = h.strip()[:120]
        if h and h not in seen:
            seen.add(h)
            out.append(h)
        if len(out) >= 8:
            break
    return out


def lore_prompt_block(
    player: Character,
    npc: Character,
    player_words: str = "",
    max_lines: int = 6,
) -> str:
    """拼给 NPC 对话的 lore 注入块"""
    extra = [npc.name, npc.sect or "", player.sect or "", player.location or "", npc.location or ""]
    blob = f"{player_words} {player.name} {npc.name} {player.location} {npc.location} {player.sect or ''} {npc.sect or ''}"
    hits = keyword_hits(blob, extra_keys=extra)
    lines = [h for h in hits if h][:max_lines]
    if not lines:
        return ""
    # 玩家侧态势（简）
    try:
        from core.player_echo import player_echo_text

        labels = []
        from core.player_echo import get_player_echo

        e = get_player_echo(player)
        labels = e.get("labels") or []
        if labels:
            lines.append(f"对方凶名/气象：{'、'.join(labels)}")
    except Exception:
        pass
    text = "【坊间与天机（可作谈资，勿编造账上没有的细节）】\n" + "\n".join(f"- {x}" for x in lines)
    return text[:_MAX_LORE_CHARS]
