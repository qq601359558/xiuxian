"""
同场一览：当前地点 NPC/修士列表（含性格、态度、议程摘要）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository, NpcAgendaRepository
from core.npc_mind import ensure_mind, attitude_toward, ATTITUDE_LABELS, _is_npc
from core.npc_agenda import agenda_cn
from config import WORLD_LOCATIONS


def list_here(
    viewer: Character,
    include_self: bool = False,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    列出与 viewer 同地点的存活角色。
    每项：name, realm, status, is_npc, personality, attitude, agenda, blood_marked
    """
    out: List[Dict[str, Any]] = []
    for c in CharacterRepository.list_all_alive():
        if c.location != viewer.location:
            continue
        if c.id == viewer.id and not include_self:
            continue
        if c.status == CharacterStatus.DEAD:
            continue

        item: Dict[str, Any] = {
            "id": c.id,
            "name": c.name,
            "realm": c.realm.name,
            "tier": c.realm.tier,
            "status": c.status.value if isinstance(c.status, CharacterStatus) else str(c.status),
            "is_npc": _is_npc(c),
            "sect": c.sect or "散修",
            "rank": c.sect_rank or "",
            "blood_marked": c.karma.is_blood_marked(),
            "stealth": c.stealth_active,
        }

        # 对 viewer 的态度（仅 NPC 有心智表；玩家显示「—」）
        if _is_npc(c):
            try:
                mind = ensure_mind(c)
                item["personality"] = mind.get("personality", "")
            except Exception:
                item["personality"] = ""
            try:
                att = attitude_toward(c, viewer.id)
                item["attitude"] = att.get("label", "neutral")
                item["attitude_cn"] = ATTITUDE_LABELS.get(att.get("label", "neutral"), "中立")
                item["attitude_value"] = att.get("value", 0)
            except Exception:
                item["attitude"] = "neutral"
                item["attitude_cn"] = "中立"
                item["attitude_value"] = 0
            try:
                ag = NpcAgendaRepository.get(c.id)
                if ag:
                    item["agenda"] = agenda_cn(ag.get("agenda_type", ""))
                    item["agenda_key"] = ag.get("agenda_type", "")
                    item["agenda_note"] = (ag.get("note") or "")[:24]
                    item["agenda_progress"] = ag.get("progress", 0)
                else:
                    item["agenda"] = ""
                    item["agenda_key"] = ""
                    item["agenda_note"] = ""
                    item["agenda_progress"] = 0
            except Exception:
                item["agenda"] = ""
                item["agenda_key"] = ""
                item["agenda_note"] = ""
                item["agenda_progress"] = 0
        else:
            item["personality"] = ""
            item["attitude"] = ""
            item["attitude_cn"] = ""
            item["attitude_value"] = 0
            item["agenda"] = ""
            item["agenda_note"] = ""

        out.append(item)
        if len(out) >= limit:
            break
    return out


def format_here(viewer: Character, rows: Optional[List[Dict[str, Any]]] = None) -> str:
    """渲染为文本（CLI / 局域网共用）"""
    if rows is None:
        rows = list_here(viewer)
    loc = WORLD_LOCATIONS.get(viewer.location, {})
    safe = "安全" if loc.get("is_safe", True) else "凶险"
    lines = [
        f"【{viewer.location}】{loc.get('region', '')} · {safe} · 灵气 {loc.get('density', 1.0)}"
    ]
    if not rows:
        lines.append("此地暂无其他修士灵压。")
        return "\n".join(lines)

    lines.append(f"同场共 {len(rows)} 人：")
    for r in rows:
        tags = []
        if r.get("blood_marked"):
            tags.append("血煞")
        if r.get("stealth"):
            tags.append("敛息")
        tag_s = f" [{'/'.join(tags)}]" if tags else ""
        if r.get("is_npc"):
            att = r.get("attitude_cn") or "中立"
            pers = r.get("personality") or ""
            ag = r.get("agenda") or ""
            ag_note = r.get("agenda_note") or ""
            rank = r.get("rank") or ""
            lines.append(
                f"  · [NPC] {r['name']}（{r['realm']} · {r['sect']}·{rank}）{tag_s}\n"
                f"      性格:{pers} | 对你:{att} | 议程:{ag} {ag_note}"
            )
        else:
            lines.append(f"  · [玩家] {r['name']}（{r['realm']} · {r['sect']}）{tag_s}")
    lines.append("可 /交谈 <道号> 或 /斗法 <道号>。")
    return "\n".join(lines)
