"""
长期记忆工作流：
  落账 → 检索 → 压成 L1/L2 摘要 → 供 AI 事实包
复仇回访：从杀戮/仇怨账续写
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character, CharacterStatus
from storage.db import (
    EventLedgerRepository,
    CharacterBioRepository,
    KarmaLinkRepository,
    CharacterRepository,
)
from ai.gate import gate
from ai.facts import FactPack, build_fact_pack
from ai.gateway import AIGateway, _chat_json
from ai.audit import write_audit
from core.bounty import BountyEngine
from core.events import EventEngine


# 上下文预算（字）
BUDGET = {
    "free_action": 800,
    "heart_demon": 400,
    "combat": 500,
    "revenge": 500,
}


def new_event_id() -> str:
    return f"ev_{uuid.uuid4().hex[:10]}"


def record_event(
    *,
    type: str,
    actor: Character,
    summary: str,
    target: Optional[Character] = None,
    location: Optional[str] = None,
    effects_digest: str = "",
    chain_id: Optional[str] = None,
    refs: Optional[List[str]] = None,
    now: Optional[float] = None,
) -> str:
    """写入事件账，返回 event_id"""
    eid = new_event_id()
    EventLedgerRepository.append(
        event_id=eid,
        ts=now or time.time(),
        type=type,
        actor_id=actor.id,
        actor_name=actor.name,
        summary=summary,
        target_id=target.id if target else None,
        target_name=target.name if target else None,
        location=location or actor.location,
        effects_digest=effects_digest,
        chain_id=chain_id,
        refs=refs,
    )
    return eid


def ensure_bio(character: Character, refresh: bool = False) -> str:
    """保证角色有 L1 小传；无则按状态生成短传（不调 AI，确定性）
    refresh=True 或旧 bio 缺职分时，用花名册职分/备注重写一次。
    """
    existing = CharacterBioRepository.get(character.id)
    rank = character.sect_rank or "散修"
    note = ""
    try:
        from core.npc_roster import ROSTER
        for row in ROSTER:
            if row.get("name") == character.name:
                note = row.get("note") or ""
                rank = row.get("rank") or rank
                break
    except Exception:
        pass

    need_rewrite = (
        refresh
        or not existing
        or (rank and rank != "散修" and rank not in existing)
        or (note and note not in existing)
    )
    if existing and not need_rewrite:
        return existing

    traits = {
        "sect": character.sect or "散修",
        "sin": character.karma.sin_value,
        "merit": character.karma.merit_value,
    }
    if character.karma.sin_value >= 100:
        tone = "凶名在外，杀孽缠身"
    elif character.karma.merit_value >= 50:
        tone = "行善积德，颇有侠名"
    else:
        tone = "籍籍无名，谨慎求生"
    bio = (
        f"{character.name}，{character.realm.name}，{character.sect or '散修'}·{rank}。"
        f"业力{character.karma.sin_value}/功德{character.karma.merit_value}。{tone}。"
        + (f"坊间称：{note}。" if note else "")
        + f"常驻{character.location}一带。"
    )
    CharacterBioRepository.save(character.id, bio, traits)
    return bio


def compress_events_for_prompt(events: List[dict], max_items: int = 5) -> List[str]:
    """事件 → 极短句，控制 token"""
    lines = []
    for e in events[:max_items]:
        t = e.get("type", "事")
        s = (e.get("summary") or "")[:60]
        loc = e.get("location") or "?"
        lines.append(f"[{t}@{loc}] {s}")
    return lines


def memory_block_for(
    character: Character,
    *,
    kind: str = "free_action",
    others: Optional[List[Character]] = None,
    extra_events: int = 0,
) -> str:
    """
    组装给 AI 的「记忆块」：L1 小传 + L2 因果 + L3 检索事件
    压进预算，避免整库进上下文
    """
    ensure_bio(character)
    bio = CharacterBioRepository.get(character.id) or ""
    events = EventLedgerRepository.query_for_memory(
        character.id, location=character.location, limit=6 + extra_events
    )
    ev_lines = compress_events_for_prompt(events, max_items=5)
    links = KarmaLinkRepository.list_all()
    link_lines = []
    for link in links:
        try:
            if link.involves(character.id):
                _oid, other = link.other_side(character.id)
                link_lines.append(f"{link.link_type}:{other}(强度{link.strength})")
        except Exception:
            continue
        if len(link_lines) >= 4:
            break

    block_lines = [
        f"【角色小传】{bio}",
        "【因果】" + ("；".join(link_lines) if link_lines else "无特别纠缠"),
        "【近日账录】",
    ]
    if ev_lines:
        for ln in ev_lines:
            block_lines.append(f"  - {ln}")
    else:
        block_lines.append("  （暂无）")
    block = "\n".join(block_lines)
    # 硬截断
    budget = BUDGET.get(kind, 600)
    if len(block) > budget:
        block = block[:budget]
    return block


def enrich_facts_with_memory(
    character: Character,
    facts: Optional[FactPack] = None,
    others: Optional[List[Character]] = None,
    kind: str = "free_action",
) -> FactPack:
    """在事实包中附加记忆块（供 gateway 使用）"""
    if facts is None:
        facts = build_fact_pack(character, others=others)
    block = memory_block_for(character, kind=kind, others=others)
    data = dict(facts.data)
    data["memory_block"] = block
    # 也并进 prompt
    return FactPack(data)


# ---------------- 复仇回访工作流 ----------------
class RevengeEngine:
    """从杀戮账续写寻仇戏；禁止否认已落账事实"""

    @staticmethod
    def maybe_callback(character: Character, chance: float = 0.35) -> Optional[Dict[str, Any]]:
        """
        上线/出关/赶路后调用：若账上有血仇，概率触发回访。
        返回叙事结果或 None。
        """
        import random
        if character.status == CharacterStatus.DEAD:
            return None
        if random.random() > chance:
            return None
        return RevengeEngine.force_callback(character)

    @staticmethod
    def force_callback(character: Character) -> Optional[Dict[str, Any]]:
        events = EventLedgerRepository.query_feud_pairs(character.id, limit=6)
        if not events:
            return None

        # 选一条：优先自己被杀/被悬赏，其次自己杀过人（对方可能寻仇）
        seed = None
        for e in events:
            if e.get("target_id") == character.id and e.get("type") in ("KILL", "BOUNTY", "COMBAT"):
                seed = e
                break
        if seed is None:
            seed = events[0]

        # 对手：若我是 target，则仇家是 actor；反之我是 actor，仇家是 target
        if seed.get("target_id") == character.id:
            foe_id = seed.get("actor_id")
            foe_name = seed.get("actor_name")
            role = "victim"  # 我曾受害
        else:
            foe_id = seed.get("target_id")
            foe_name = seed.get("target_name")
            role = "killer"  # 我曾加害，对方可能寻仇

        # 仇家是否还在世
        foe = None
        if foe_id:
            for c in CharacterRepository.list_all_alive():
                if c.id == foe_id:
                    foe = c
                    break

        facts = enrich_facts_with_memory(character, kind="revenge")
        mem = facts.data.get("memory_block", "")
        origin = f"[{seed.get('type')}] {seed.get('summary')} @{seed.get('location')}"
        data = _chat_json(
            "你是修仙世界因果引擎。根据事件账续写一幕「寻仇/报恩回访」。\n"
            f"{facts.to_prompt_block()}\n"
            f"【记忆】\n{mem}\n"
            f"【前因账录】{origin}\n"
            f"【角色】主角 {character.name}；对手 {foe_name or '（或已不在场）'}；"
            f"主角立场：{'曾受害' if role=='victim' else '曾加害'}。\n"
            "硬约束：不得否认上述前因；不得凭空复活已死者；效果受钳制。\n"
            "输出 JSON：{\"narrative\":\"100-180字回访戏\","
            "\"effects\":{},\"escalate\":false,\"spawn\":null}"
        )
        if not data:
            narrative = (
                f"风闻【{foe_name}】仍在打听你的下落。"
                f"旧账未清，因果如影随形。"
            )
            effects = {}
            escalate = False
            spawn = None
            source = "local"
        else:
            narrative = str(data.get("narrative", ""))[:400] or "因果无声。"
            effects = data.get("effects") or {}
            escalate = bool(data.get("escalate"))
            spawn = data.get("spawn") if escalate else None
            source = "ai"

        ok, _m, cleaned = gate.admit(
            "event",
            {"narrative": narrative, "effects": effects, "spawn": spawn if escalate else None},
            facts,
            actor_id=character.id,
        )
        if not ok:
            cleaned = {"narrative": narrative, "effects": {}}

        summary = EventEngine.apply_effects(character, cleaned.get("effects") or {})
        eid = record_event(
            type="REVENGE",
            actor=character,
            summary=(cleaned.get("narrative") or narrative)[:80],
            location=character.location,
            effects_digest=summary,
            refs=[seed.get("event_id")] if seed.get("event_id") else None,
        )

        spawned = None
        if cleaned.get("spawn"):
            from core.combat_fate import _spawn_from_proposal
            spawned = _spawn_from_proposal(cleaned["spawn"])

        write_audit({
            "ts": time.time(),
            "actor": character.id,
            "kind": "revenge_callback",
            "seed_event": seed.get("event_id"),
            "source": source,
        })

        return {
            "ok": True,
            "kind": "revenge",
            "origin": origin,
            "narrative": cleaned.get("narrative") or narrative,
            "effects_summary": summary,
            "event_id": eid,
            "spawned": spawned,
            "source": source,
            "foe_name": foe_name,
            "foe_alive": foe is not None,
            "text": (
                f"【因果回访】前因：{origin}\n"
                f"{cleaned.get('narrative') or narrative}\n"
                f"落账：{summary}"
            ),
        }
