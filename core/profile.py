"""
人物详情：汇总角色档案（命盘 + 心智 + 议程 + 近账 + 态度）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from storage.db import (
    CharacterRepository,
    NpcMindRepository,
    NpcAgendaRepository,
    EventLedgerRepository,
    CharacterBioRepository,
)
from core.npc_mind import ensure_mind, attitude_toward, ATTITUDE_LABELS, _is_npc
from core.npc_agenda import ensure_agenda, agenda_cn
from core.memory import ensure_bio, compress_events_for_prompt
from config import WORLD_LOCATIONS


def build_profile(viewer: Character, target: Optional[Character] = None) -> Dict[str, Any]:
    """
    构建人物详情。target 缺省为自己。
    信息脱敏：他人精确灵石不展示（防反推配装）。
    """
    c = target or viewer
    is_self = target is None or target.id == viewer.id
    is_npc = _is_npc(c)

    loc = WORLD_LOCATIONS.get(c.location, {})
    rem = c.lifespan.get_remaining_years()

    data: Dict[str, Any] = {
        "id": c.id,
        "name": c.name,
        "is_self": is_self,
        "is_npc": is_npc,
        "realm": c.realm.name,
        "tier": c.realm.tier,
        "sub_tier": c.realm.sub_tier,
        "exp": f"{c.realm.current_exp}/{c.realm.max_exp}",
        "exp_full": c.realm.is_full,
        "root": c.spiritual_root.display_name(),
        "location": c.location,
        "location_safe": loc.get("is_safe", True),
        "location_region": loc.get("region", ""),
        "density": loc.get("density", 1.0),
        "sect": c.sect or "散修",
        "rank": c.sect_rank or "散修",
        "sin": c.karma.sin_value,
        "merit": c.karma.merit_value,
        "dao_heart": c.karma.dao_heart,
        "blood_marked": c.karma.is_blood_marked(),
        "rem_years": round(rem, 2),
        "status": c.status.value if isinstance(c.status, CharacterStatus) else str(c.status),
        "skills": list(c.skills[:10]),
        "arrays": list(c.arrays[:8]),
        "inventory_count": len(c.inventory),
        "stealth": c.stealth_active,
    }

    # M4：望气投影
    try:
        from core.player_echo import get_player_echo, player_echo_text, region_info

        e = get_player_echo(c)
        data["echo_labels"] = list(e.get("labels") or [])
        data["echo_fame"] = int(e.get("fame") or 0)
        data["echo_kills"] = int(e.get("kill_total") or 0)
        ri = region_info(c.location)
        data["region_danger"] = float(ri.get("danger") or 0)
        if is_self:
            try:
                from core.player_echo import market_panic_text

                data["market_panic_text"] = market_panic_text()
            except Exception:
                data["market_panic_text"] = ""
    except Exception:
        data["echo_labels"] = []

    if is_self:
        data["stones"] = c.spirit_stones
        data["vault"] = c.vault_stones
        data["inventory"] = list(c.inventory[:12])
    else:
        # 他人只给区间，防精确反推
        s = c.spirit_stones
        if s < 100:
            data["stones_hint"] = "囊中羞涩"
        elif s < 500:
            data["stones_hint"] = "略有积蓄"
        elif s < 2000:
            data["stones_hint"] = "身家颇丰"
        else:
            data["stones_hint"] = "富可敌宗"

    # 小传
    if is_npc or is_self:
        ensure_bio(c)
        data["bio"] = CharacterBioRepository.get(c.id) or ""

    # 心智（NPC）
    if is_npc:
        try:
            mind = ensure_mind(c)
            data["personality"] = mind.get("personality", "")
            data["traits"] = mind.get("traits") or {}
        except Exception:
            data["personality"] = ""
            data["traits"] = {}
        try:
            att = attitude_toward(c, viewer.id) if not is_self else {"value": 0, "label": "self"}
            data["attitude"] = att.get("label", "neutral")
            data["attitude_cn"] = ATTITUDE_LABELS.get(att.get("label", "neutral"), "—")
            data["attitude_value"] = att.get("value", 0)
        except Exception:
            data["attitude"] = "neutral"
            data["attitude_cn"] = "中立"
            data["attitude_value"] = 0
        try:
            ag = ensure_agenda(c)
            extra = ag.get("extra") or {}
            sec = extra.get("secondary") or []
            data["agenda"] = agenda_cn(ag.get("agenda_type", ""))
            data["agenda_key"] = ag.get("agenda_type", "")
            data["agenda_note"] = ag.get("note", "")
            data["agenda_progress"] = ag.get("progress", 0)
            data["agenda_secondary"] = [
                {"type": agenda_cn(s.get("agenda_type", "")), "note": s.get("note", "")}
                for s in sec[:2]
            ]
        except Exception:
            data["agenda"] = ""
            data["agenda_note"] = ""
            data["agenda_progress"] = 0
            data["agenda_secondary"] = []

    # 近账（自己或 NPC 公开摘要）
    events = EventLedgerRepository.query_for_memory(c.id, limit=6)
    data["recent"] = compress_events_for_prompt(events, max_items=4)

    return data


def format_profile(viewer: Character, profile: Dict[str, Any]) -> str:
    """渲染为文本（CLI / 局域网）"""
    lines = []
    title = profile["name"]
    if profile.get("is_npc"):
        title += "【NPC】"
    elif profile.get("is_self"):
        title += "（阁下）"
    lines.append(f"═══ {title} ═══")
    lines.append(
        f"{profile['realm']} · {profile['sect']}·{profile['rank']} · "
        f"修为 {profile['exp']}{'（圆满）' if profile.get('exp_full') else ''}"
    )
    lines.append(
        f"命格 {profile.get('root','')} · 寿元约 {profile['rem_years']} 岁 · "
        f"道心 {profile['dao_heart']} · 业力 {profile['sin']} / 功德 {profile['merit']}"
    )
    if profile.get("blood_marked"):
        lines.append("【血煞狼烟·天道通缉】")
    lines.append(
        f"所在 {profile['location']}（{profile.get('location_region','')} · "
        f"{'安全' if profile.get('location_safe') else '凶险'}）"
    )
    if profile.get("is_self"):
        lines.append(f"随身灵石 {profile.get('stones',0)} · 金库 {profile.get('vault',0)}")
        inv = "、".join(profile.get("inventory") or []) or "无"
        lines.append(f"杂物：{inv}")
    elif profile.get("stones_hint"):
        lines.append(f"身家：{profile['stones_hint']}")
    if profile.get("personality"):
        lines.append(f"性格：{profile['personality']}")
    if profile.get("attitude_cn"):
        lines.append(
            f"对你的态度：{profile['attitude_cn']}"
            f"（{profile.get('attitude_value',0)}）"
        )
    if profile.get("agenda"):
        sec = profile.get("agenda_secondary") or []
        sec_s = "；".join(f"{s['type']}·{s['note']}" for s in sec if s.get("type"))
        lines.append(
            f"当前议程：{profile['agenda']} — {profile.get('agenda_note','')} "
            f"({profile.get('agenda_progress',0)}/5)"
        )
        if sec_s:
            lines.append(f"副议程：{sec_s}")
    if profile.get("skills"):
        lines.append("法门：" + "、".join(profile["skills"]))
    if profile.get("bio"):
        lines.append("小传：" + profile["bio"])
    if profile.get("recent"):
        lines.append("近日账录：")
        for r in profile["recent"]:
            lines.append(f"  · {r}")
    return "\n".join(lines)


def find_by_name(name: str) -> Optional[Character]:
    return CharacterRepository.get_by_name(name)
