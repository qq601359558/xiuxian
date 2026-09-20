"""
事实包：调用 AI 前从规则库抽出的「当前世界真相」
时间/地点/人物/事件/因果 —— AI 只许在此包络内编剧
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from config import WORLD_LOCATIONS, SECTS_CONFIG
from core.models import Character, CharacterStatus


def format_epoch_time(now: Optional[float] = None) -> str:
    from core.clock import WorldClock
    return WorldClock.format_game_time(now or time.time())


class FactPack:
    """一次 AI 调用的事实上下文（只读、可序列化）"""

    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @property
    def known_ids(self) -> set:
        ids = set(self.data.get("known_ids") or [])
        me = self.data.get("self", {})
        if me.get("id"):
            ids.add(me["id"])
        return ids

    def to_prompt_block(self) -> str:
        """压成给模型的中文事实块（约束其不得虚构）"""
        d = self.data
        me = d.get("self", {})
        loc = d.get("location", {})
        others = d.get("others_nearby", [])
        links = d.get("karma_links", [])
        bounties = d.get("bounties", [])
        recent = d.get("recent_ledger", [])
        jianghu = d.get("jianghu_events", [])
        agendas = d.get("npc_agendas", [])
        season = d.get("season", {})

        lines = [
            "【天道事实包 · 权威世界状态 · 禁止虚构不存在的人物/地点/已发生事件】",
            f"纪元时：{season.get('time_str', '?')}",
            f"自身：{me.get('name','?')} id={me.get('id','?')} 境界={me.get('realm','?')} "
            f"状态={me.get('status','?')} 位置={me.get('location','?')}",
            f"寿元剩余约 {me.get('rem_years', '?')} 岁；业力 {me.get('sin',0)} 功德 {me.get('merit',0)} "
            f"道心 {me.get('dao_heart',100)}；随身灵石 {me.get('stones',0)} 金库 {me.get('vault',0)}",
            f"法门：{'、'.join(me.get('skills', [])[:8]) or '无'}",
            f"所在：{loc.get('name','?')}（{loc.get('region','?')} · "
            f"灵气 {loc.get('density',1)} · {'安全' if loc.get('is_safe') else '凶险'}）",
        ]
        if others:
            lines.append("同处/可感知修士：" + "；".join(others[:8]))
        else:
            lines.append("同处修士：无（方圆暂无他人灵压）")
        if links:
            lines.append("因果链：" + "；".join(links[:6]))
        if bounties:
            lines.append("相关悬赏：" + "；".join(bounties[:4]))
        if recent:
            lines.append("近期世界大事（已落账，不可否认）：")
            for r in recent[:5]:
                lines.append(f"  - {r}")
        if jianghu:
            lines.append("江湖因果账（event_id 必须引用或声明新增前已知晓）：")
            for r in jianghu[:8]:
                lines.append(f"  - {r}")
        if agendas:
            lines.append("可感知的 NPC 议程动向（仅限下列）：")
            for r in agendas[:6]:
                lines.append(f"  - {r}")
        try:
            from core.legends import pick_for_npc_prompt

            legend = pick_for_npc_prompt(1)
            if legend:
                lines.append(f"史载传说：{legend}")
        except Exception:
            pass
        lines.append(
            "硬约束：人物只能引用上述 id/道号或申请 spawn 新档；地点不得瞬移；"
            "时间不得改写纪元历；效果字段必须符合提案 schema 与上下界。"
        )
        mem = d.get("memory_block")
        if mem:
            lines.append("")
            lines.append(str(mem))
        return "\n".join(lines)

    def summary_dict(self) -> Dict[str, Any]:
        return self.data


def build_fact_pack(
    character: Character,
    *,
    others: Optional[List[Character]] = None,
    karma_links: Optional[List[Any]] = None,
    bounties: Optional[List[Any]] = None,
    recent_ledger: Optional[List[str]] = None,
    jianghu_events: Optional[List[Any]] = None,
    npc_agendas: Optional[List[Any]] = None,
    known_extra_ids: Optional[List[str]] = None,
    now: Optional[float] = None,
) -> FactPack:
    """从规则状态构建事实包；多人时传入 others=同场景其他角色"""
    current_time = now or time.time()
    loc_info = WORLD_LOCATIONS.get(character.location, {
        "region": "未知", "density": 1.0, "is_safe": True, "desc": ""
    })

    me = {
        "id": character.id,
        "name": character.name,
        "realm": character.realm.name,
        "tier": character.realm.tier,
        "status": character.status.value if isinstance(character.status, CharacterStatus) else str(character.status),
        "location": character.location,
        "rem_years": round(character.lifespan.get_remaining_years(current_time), 2),
        "sin": character.karma.sin_value,
        "merit": character.karma.merit_value,
        "dao_heart": character.karma.dao_heart,
        "blood_marked": character.karma.is_blood_marked(current_time),
        "stones": character.spirit_stones,
        "vault": character.vault_stones,
        "skills": list(character.skills[:8]),
        "arrays": list(character.arrays[:6]),
        "sect": character.sect,
        "exp": f"{character.realm.current_exp}/{character.realm.max_exp}",
    }

    others_list: List[str] = []
    known_ids = [character.id]
    if others:
        for o in others:
            if o.id == character.id or o.status == CharacterStatus.DEAD:
                continue
            known_ids.append(o.id)
            marked = "【血煞】" if o.karma.is_blood_marked(current_time) else ""
            others_list.append(
                f"{o.name}(id={o.id}, {o.realm.name}, {o.status.value}{marked})"
            )

    link_summaries: List[str] = []
    if karma_links:
        for link in karma_links[:8]:
            # 只摘要与自己相关的
            try:
                if not link.involves(character.id):
                    continue
                _oid, other = link.other_side(character.id)
                link_summaries.append(f"{link.link_type}:{other}(强度{link.strength})")
            except Exception:
                continue

    bounty_summaries: List[str] = []
    if bounties:
        for b in bounties[:6]:
            try:
                role = "目标" if getattr(b, "target_id", "") == character.id else "旁观"
                if getattr(b, "issuer_id", "") == character.id:
                    role = "苦主"
                if getattr(b, "hunter_id", None) == character.id:
                    role = "猎手"
                bounty_summaries.append(
                    f"{role}→{b.target_name} 赏{b.reward} {b.status.value}"
                )
            except Exception:
                continue

    jianghu_lines: List[str] = []
    if jianghu_events:
        for ev in jianghu_events[:8]:
            try:
                if isinstance(ev, dict):
                    eid = str(ev.get("id") or ev.get("event_id") or "")
                    kind = ev.get("kind") or ev.get("type") or ""
                    summary = ev.get("summary") or ev.get("narrative") or ""
                    loc = ev.get("location") or ""
                    actors = ev.get("actor_ids") or []
                    jianghu_lines.append(
                        f"[{eid}] {kind} {loc} {summary}".strip()
                    )
                    for a in actors:
                        if a:
                            known_ids.append(str(a))
                    for t in (ev.get("target_ids") or []):
                        if t:
                            known_ids.append(str(t))
                    if eid:
                        known_ids.append(eid)
                else:
                    jianghu_lines.append(str(ev)[:120])
            except Exception:
                continue

    agenda_lines: List[str] = []
    if npc_agendas:
        for ag in npc_agendas[:6]:
            try:
                if isinstance(ag, dict):
                    nid = str(ag.get("npc_id") or "")
                    name = ag.get("npc_name") or ""
                    at = ag.get("agenda_type") or ""
                    note = ag.get("note") or ""
                    agenda_lines.append(f"{name}(id={nid}) {at} {note}".strip())
                    if nid:
                        known_ids.append(nid)
                else:
                    agenda_lines.append(str(ag)[:100])
            except Exception:
                continue

    if known_extra_ids:
        for kid in known_extra_ids:
            if kid:
                known_ids.append(str(kid))

    # 去重保序
    seen = set()
    uniq_known = []
    for kid in known_ids:
        if kid not in seen:
            seen.add(kid)
            uniq_known.append(kid)

    return FactPack({
        "season": {
            "time_str": format_epoch_time(current_time),
            "timestamp": current_time,
        },
        "self": me,
        "location": {
            "name": character.location,
            "region": loc_info.get("region", "未知"),
            "density": loc_info.get("density", 1.0),
            "is_safe": loc_info.get("is_safe", True),
            "desc": loc_info.get("desc", "")[:60],
        },
        "others_nearby": others_list,
        "known_ids": uniq_known,
        "karma_links": link_summaries,
        "bounties": bounty_summaries,
        "recent_ledger": list(recent_ledger or []),
        "jianghu_events": jianghu_lines,
        "npc_agendas": agenda_lines,
    })
