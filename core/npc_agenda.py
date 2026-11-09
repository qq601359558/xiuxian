"""
NPC 议程 tick：
  每 NPC 只加载 议程1条 + 小传 + 近账3条 + 当前地
  → AI 决定是否行动 → 落公账/事件账 → 更新议程
控制上下文，禁止跨 NPC 脑补联盟
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from storage.db import (
    NpcAgendaRepository,
    CharacterRepository,
    EventLedgerRepository,
    CharacterBioRepository,
)
from core.memory import ensure_bio, record_event, compress_events_for_prompt
from core.events import EventEngine
from ai.gate import gate
from ai.facts import build_fact_pack
from ai.router import invoke as ai_invoke
from ai.gateway import ai_ready
from ai.audit import write_audit
from config import WORLD_LOCATIONS


AGENDA_TYPES = {
    "revenge": "寻仇",
    "treasure": "夺宝",
    "seclusion": "闭关求突破",
    "patrol": "巡守宗门/地盘",
    "social": "结交/打探",
    "survive": "避劫求生",
}


def agenda_cn(key: str) -> str:
    return AGENDA_TYPES.get(key or "", key or "—")


def default_agenda_for(npc: Character) -> Dict[str, Any]:
    """按状态给默认议程（确定性，不调 AI）"""
    if npc.karma.sin_value >= 100:
        return {"agenda_type": "survive", "note": "血债缠身，避人耳目或寻靠山", "target_hint": ""}
    if npc.karma.is_blood_marked():
        return {"agenda_type": "revenge", "note": "被天道标记，急于除凶或遁走", "target_hint": ""}
    if npc.realm.is_full:
        return {"agenda_type": "seclusion", "note": "修为圆满，欲寻洞府突破", "target_hint": ""}
    if npc.sect:
        return {"agenda_type": "patrol", "note": f"为【{npc.sect}】巡守周边", "target_hint": npc.sect}
    if npc.spirit_stones >= 800:
        return {"agenda_type": "treasure", "note": "身怀重资，防人觊觎或寻机购置", "target_hint": ""}
    return {"agenda_type": "social", "note": "市井打探机缘与消息", "target_hint": ""}


def ensure_agenda(npc: Character) -> Dict[str, Any]:
    ag = NpcAgendaRepository.get(npc.id)
    if ag:
        return ag
    d = default_agenda_for(npc)
    NpcAgendaRepository.upsert(
        npc_id=npc.id,
        npc_name=npc.name,
        agenda_type=d["agenda_type"],
        target_hint=d.get("target_hint", ""),
        note=d.get("note", ""),
        state="active",
        last_tick=0.0,
        progress=0,
    )
    return NpcAgendaRepository.get(npc.id) or {}


def _is_npc(c: Character) -> bool:
    return str(c.user_id).startswith("npc_") or str(c.user_id).startswith("ai_npc_")


def list_npc_characters(limit: int = 12) -> List[Character]:
    out = []
    for c in CharacterRepository.list_all_alive():
        if _is_npc(c):
            out.append(c)
        if len(out) >= limit:
            break
    return out


class NpcAgendaEngine:
    """NPC 议程推进"""

    TICK_COOLDOWN_SECONDS = 180.0  # 同一 NPC 至少间隔 3 分钟

    @staticmethod
    def build_npc_prompt_pack(npc: Character) -> Dict[str, Any]:
        """压上下文：小传 + 议程 + 近账3 + 地点"""
        ensure_bio(npc)
        bio = CharacterBioRepository.get(npc.id) or ""
        ag = ensure_agenda(npc)
        events = EventLedgerRepository.query_for_memory(npc.id, location=npc.location, limit=4)
        ev_lines = compress_events_for_prompt(events, max_items=3)
        loc = WORLD_LOCATIONS.get(npc.location, {})
        others = [
            c for c in CharacterRepository.list_all_alive()
            if c.id != npc.id and c.location == npc.location
        ][:3]
        other_names = "、".join(f"{o.name}({o.realm.name})" for o in others) or "无"
        return {
            "bio": bio,
            "agenda": ag,
            "events": ev_lines,
            "loc_name": npc.location,
            "loc_safe": loc.get("is_safe", True),
            "others": other_names,
            "npc": npc,
        }

    @staticmethod
    def prepare_tick_one(npc: Character, force: bool = False) -> Optional[Dict[str, Any]]:
        """三段式·段一（调用方持 World.lock 时执行）：规则权威结算 + 快照 DTO。

        与原 tick_one 前半完全同序：冷却/议程选取/事实包组装/规则结算
        （JianghuSimulator.resolve_agenda，数值唯一权威）都在本段完成。
        产出纯数据 DTO（角色序列化快照 + 结算结果 + AI 载荷），不把角色
        对象引用带出本段；AI 调用在段二（锁外），落盘在段三（复验后）。
        冷却/非 NPC/已死返回 None（与原 tick_one 同口径）。
        """
        if not _is_npc(npc):
            return None
        if npc.status == CharacterStatus.DEAD:
            return None
        ag = ensure_agenda(npc)
        now = time.time()
        if not force and (now - (ag.get("last_tick") or 0)) < NpcAgendaEngine.TICK_COOLDOWN_SECONDS:
            return None

        use_ai = ai_ready()

        # 本 tick 按权重选议程（主/副）；force 时用档案主议程，便于结算与追赶
        try:
            from core.npc_mind import pick_agenda_for_tick, ensure_mind
            if force:
                ag_type = ag.get("agenda_type") or "social"
                ag_note = ag.get("note") or ""
            else:
                chosen = pick_agenda_for_tick(npc)
                ag_type = chosen.get("agenda_type") or ag.get("agenda_type") or "social"
                ag_note = chosen.get("note") or ag.get("note") or ""
            mind = ensure_mind(npc)
            personality = mind.get("personality", "")
        except Exception:
            ag_type = ag.get("agenda_type") or "social"
            ag_note = ag.get("note") or ""
            personality = ""

        pack = NpcAgendaEngine.build_npc_prompt_pack(npc)
        ag_cn = AGENDA_TYPES.get(ag_type, ag_type)
        try:
            from core.npc_personas import persona_prompt_block

            persona_blk = persona_prompt_block(npc)
        except Exception:
            persona_blk = ""

        # ① 规则权威结算：目标/生死/夺宝/突破 —— AI 不得驱动
        from core.jianghu_sim import JianghuSimulator

        resolution = JianghuSimulator.resolve_agenda(npc, ag_type, ag, now=now)
        narrative = resolution.get("narrative") or ""
        new_loc = resolution.get("new_location")
        notes = list(resolution.get("notes") or [])

        # ② AI 载荷（纯 DTO）：事实包是可序列化只读数据，载荷皆为字符串/标量。
        # 组装顺序与原 tick_one 一致：事实包按结算后、位移前的地点取同场他人。
        facts = None
        payload = None
        if use_ai and resolution.get("acted") and narrative:
            try:
                import core.jianghu as jianghu

                facts = build_fact_pack(
                    npc,
                    others=[
                        c
                        for c in CharacterRepository.list_all_alive()
                        if c.id != npc.id and c.location == npc.location
                    ][:3],
                    recent_ledger=None,
                    jianghu_events=jianghu.events_for_prompt(4),
                    npc_agendas=[{"npc_id": npc.id, "npc_name": npc.name, "agenda_type": ag_type, "note": ag_note}],
                )
            except Exception:
                facts = build_fact_pack(npc)
            payload = {
                "bio": pack["bio"],
                "personality": personality,
                "ag_cn": ag_cn,
                "ag_note": ag_note,
                "loc_name": pack["loc_name"],
                "safe_cn": "安全" if pack["loc_safe"] else "凶险",
                "others": pack["others"],
                "events": "\n".join(f"  - {e}" for e in (pack["events"] or ["（无）"])),
                "persona": persona_blk,
                "rule_outcome": resolution.get("outcome"),
                "rule_narrative": narrative,
                "rule_target": resolution.get("target_name") or "",
            }

        # 应用位移（原 tick_one 在 AI 后、落盘前应用；此处在载荷组装后、
        # 快照序列化前应用，使 DTO 即最终落盘态）
        if resolution.get("acted") and new_loc and new_loc in WORLD_LOCATIONS:
            old = npc.location
            npc.location = new_loc
            notes.append(f"{old}→{new_loc}")

        # 复验基线：结算后、AI 前的 DB 行版本（updated_at）。段三落盘前
        # 重读比对，窗口内被他人改过（死亡/移位/灵石变动）即整条丢弃。
        _fresh, baseline_updated_at = (None, None)
        try:
            _fresh, baseline_updated_at = CharacterRepository.get_by_id_with_meta(npc.id)
        except Exception:
            pass

        return {
            "npc_id": npc.id,
            "npc_name": npc.name,
            "npc_json": npc.model_dump_json(),
            "baseline_updated_at": baseline_updated_at,
            "ag": dict(ag),
            "ag_type": ag_type,
            "ag_note": ag_note,
            "ag_cn": ag_cn,
            "now": now,
            "use_ai": bool(use_ai),
            "facts": facts,
            "payload": payload,
            "resolution": {
                "acted": bool(resolution.get("acted")),
                "action": resolution.get("action") or "stay",
                "outcome": resolution.get("outcome"),
                "narrative": narrative,
                "progress_delta": int(resolution.get("progress_delta") or 0),
                "new_location": new_loc,
                "notes": notes,
                "cascade_notes": list(resolution.get("cascade_notes") or []),
                "target_id": resolution.get("target_id"),
                "target_name": resolution.get("target_name"),
            },
            "narrative": narrative,
            "source": "rule",
        }

    @staticmethod
    def ai_tick_one_prepared(prep: Dict[str, Any]) -> None:
        """三段式·段二（锁外执行）：AI 仅改写叙事，结果已定，禁止覆盖 action/outcome。

        只读写 prep DTO，不触碰任何角色对象与 DB（ai_invoke 本身除外）。
        合并规则与原 tick_one 内联段逐字一致。
        """
        resolution = prep["resolution"]
        if not (prep.get("use_ai") and resolution.get("acted") and prep.get("payload")):
            return
        narrative = prep["narrative"]
        result = ai_invoke(
            "npc_agenda",
            facts=prep.get("facts"),
            payload=prep["payload"],
            actor_id=prep["npc_id"],
        )
        if result.get("ok") and isinstance(result.get("data"), dict):
            data = result["data"]
            ai_line = str(data.get("narrative") or "").strip()
            # 只允许润色叙事，且不得凭空否定已发生的 kill/夺宝
            if ai_line and resolution.get("outcome") not in ("idle",):
                if resolution.get("outcome") in ("kill", "rob_kill", "patrol_kill", "tribulation_die", "breakthrough"):
                    # 关键结局：保留规则叙事关键信息，AI 句子作补充
                    if resolution.get("target_name") and resolution["target_name"] not in ai_line:
                        narrative = f"{narrative}（{ai_line[:80]}）"
                    else:
                        narrative = ai_line[:240]
                else:
                    narrative = ai_line[:240]
                prep["source"] = "rule+ai"
            prep["narrative"] = narrative

    @staticmethod
    def apply_tick_one_prepared(prep: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """三段式·段三（调用方持 World.lock 时执行）：复验后落盘。

        复验口径：按 npc_id 重读当前行——不存在/已死/updated_at 与段一
        基线不一致（窗口内被并发写过）→ 整条丢弃并 write_audit 留痕，
        绝不把陈旧快照整行写回（对齐 director save_if_unchanged 先例）。
        落盘步骤与原 tick_one 后半逐项一致（存档→议程进度→江湖账→
        事件账→审计）。
        """
        npc_id = prep["npc_id"]
        resolution = prep["resolution"]
        narrative = prep["narrative"]
        source = prep["source"]
        ag = prep["ag"]
        now = prep["now"]
        action = resolution.get("action") or "stay"
        notes = list(resolution.get("notes") or [])
        cascade_notes = list(resolution.get("cascade_notes") or [])

        # 复验：角色仍存在且未被并发改写
        fresh = None
        fresh_updated_at = None
        try:
            fresh, fresh_updated_at = CharacterRepository.get_by_id_with_meta(npc_id)
        except Exception:
            fresh = None
        if fresh is None or fresh.status == CharacterStatus.DEAD:
            write_audit({
                "ts": now, "actor": npc_id, "kind": "npc_tick_stale_discarded",
                "reason": "gone_or_dead", "outcome": resolution.get("outcome"),
            })
            return None
        baseline = prep.get("baseline_updated_at")
        if baseline is not None and fresh_updated_at is not None and fresh_updated_at != baseline:
            write_audit({
                "ts": now, "actor": npc_id, "kind": "npc_tick_stale_discarded",
                "reason": "row_changed_during_ai", "outcome": resolution.get("outcome"),
            })
            return None
        try:
            npc = Character.model_validate_json(prep["npc_json"])
        except Exception:
            return None

        if not resolution.get("acted"):
            NpcAgendaRepository.mark_tick(npc.id, last_action="静观其变")
            return {
                "ok": True,
                "acted": False,
                "npc": npc.name,
                "narrative": narrative or f"【{npc.name}】于{npc.location}静观其变，未起波澜。",
                "source": source,
            }

        try:
            CharacterRepository.save(npc)
            if resolution.get("target_id"):
                tgt = CharacterRepository.get_by_id(resolution["target_id"])
                if tgt:
                    CharacterRepository.save(tgt)
        except Exception:
            pass

        new_progress = int(ag.get("progress") or 0) + int(resolution.get("progress_delta") or 0)
        if new_progress >= 5 or resolution.get("outcome") in (
            "kill",
            "breakthrough",
            "tribulation_die",
            "rob",
            "patrol_kill",
        ):
            # 议程阶段性完成，换新主议程
            d = default_agenda_for(npc)
            prev_extra = ag.get("extra") or {}
            sec = prev_extra.get("secondary") or []
            sec = [s for s in sec if s.get("agenda_type") != d["agenda_type"]]
            prev_extra = dict(prev_extra)
            prev_extra["secondary"] = sec
            NpcAgendaRepository.upsert(
                npc_id=npc.id,
                npc_name=npc.name,
                agenda_type=d["agenda_type"],
                target_hint=d.get("target_hint", ""),
                note=d.get("note", ""),
                state="active",
                last_tick=now,
                progress=0,
                extra=prev_extra,
            )
            notes.append(f"议程更迭→{AGENDA_TYPES.get(d['agenda_type'], d['agenda_type'])}")
        else:
            NpcAgendaRepository.mark_tick(
                npc.id,
                last_action=f"{action}:{narrative[:40]}",
                progress=new_progress,
            )

        summary = f"{npc.name}({prep['ag_cn']}) {narrative[:50]}"
        try:
            import core.jianghu as jianghu

            jh_id = jianghu.append_event(
                kind="npc_agenda",
                actor_ids=[npc.id],
                actor_names=[npc.name],
                target_ids=[resolution["target_id"]] if resolution.get("target_id") else [],
                location=npc.location,
                summary=summary,
                rule_result={
                    "action": action,
                    "outcome": resolution.get("outcome"),
                    "notes": notes,
                    "cascade": cascade_notes,
                    "source": source,
                    "agenda": prep["ag_type"],
                    "target": resolution.get("target_name"),
                },
                narrative=narrative[:200],
                ref_ids=[npc.id] + ([resolution["target_id"]] if resolution.get("target_id") else []),
                source=source,
                enforce_budget=True,
                now=now,
            )
        except Exception:
            jh_id = None

        eid = record_event(
            type="NPC_TICK",
            actor=npc,
            summary=f"{npc.name}({prep['ag_cn']}) {narrative[:50]}",
            location=npc.location,
            effects_digest="；".join(notes + cascade_notes),
        )

        write_audit({
            "ts": now,
            "actor": npc.id,
            "kind": "npc_tick",
            "action": action,
            "outcome": resolution.get("outcome"),
            "source": source,
            "event_id": eid,
            "jianghu_id": jh_id,
        })

        extra_txt = ""
        if cascade_notes:
            extra_txt = "（" + "；".join(cascade_notes[:3]) + "）"
        elif notes:
            extra_txt = "（" + "；".join(notes[:3]) + "）"

        return {
            "ok": True,
            "acted": True,
            "npc": npc.name,
            "action": action,
            "outcome": resolution.get("outcome"),
            "target": resolution.get("target_name"),
            "narrative": narrative,
            "notes": notes,
            "cascade_notes": cascade_notes,
            "event_id": eid,
            "jianghu_id": jh_id,
            "source": source,
            "text": f"【NPC·{prep['ag_cn']}】{npc.name}：{narrative}{extra_txt}",
        }

    @staticmethod
    def tick_one(npc: Character, force: bool = False) -> Optional[Dict[str, Any]]:
        """推进一个 NPC（兼容入口：三段连跑，语义与原实现一致）。"""
        prep = NpcAgendaEngine.prepare_tick_one(npc, force=force)
        if prep is None:
            return None
        NpcAgendaEngine.ai_tick_one_prepared(prep)
        return NpcAgendaEngine.apply_tick_one_prepared(prep)

    @staticmethod
    def _local_tick(npc: Character, ag_type: str):
        roll = random.random()
        if ag_type == "seclusion":
            if roll < 0.45:
                return True, "train", f"{npc.name}于洞府吐纳，真元鼓荡。", 1, None
            return False, "stay", "", 0, None
        if ag_type == "revenge":
            if roll < 0.35:
                return True, "scheme", f"{npc.name}四下打听仇家行踪，袖中剑意森然。", 1, None
            return False, "stay", "", 0, None
        if ag_type == "patrol":
            if roll < 0.4:
                return True, "talk", f"{npc.name}在{npc.location}盘问过路散修。", 1, None
            return False, "stay", "", 0, None
        if ag_type == "treasure":
            if roll < 0.3:
                return True, "scheme", f"{npc.name}乔装入坊市，暗中估价灵材。", 1, None
            return False, "stay", "", 0, None
        # social / survive
        if roll < 0.35:
            return True, "talk", f"{npc.name}与人闲话近日天象，眉间隐有忧色。", 1, None
        return False, "stay", "", 0, None

    @staticmethod
    def prepare_tick_world(max_npcs: int = 5, force: bool = False) -> List[Dict[str, Any]]:
        """三段式·段一（批量）：逐 NPC 规则结算并收集 DTO。

        选取口径与原 tick_world 一致：按名录序遍历，acted 数达 max_npcs 即止。
        """
        prepared: List[Dict[str, Any]] = []
        acted = 0
        for npc in list_npc_characters(limit=max_npcs * 2):
            if acted >= max_npcs:
                break
            try:
                prep = NpcAgendaEngine.prepare_tick_one(npc, force=force)
            except Exception:
                continue
            if prep is None:
                continue
            prepared.append(prep)
            if prep["resolution"].get("acted"):
                acted += 1
        return prepared

    @staticmethod
    def ai_tick_world(prepared: List[Dict[str, Any]]) -> None:
        """三段式·段二（批量，锁外）：逐条 AI 叙事润色，单条失败不影响其余。"""
        for prep in prepared or []:
            try:
                NpcAgendaEngine.ai_tick_one_prepared(prep)
            except Exception:
                continue

    @staticmethod
    def apply_tick_world(prepared: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """三段式·段三（批量）：逐条复验落盘 + 原 tick_world 尾随推进。

        尾随段（合谋/避祸/传闻/因果链）与原实现同序、同 try/except 包裹，
        在落盘后执行（与原「全部 tick_one 完成后再跑尾随」一致）。
        """
        results: List[Dict[str, Any]] = []
        for prep in prepared or []:
            try:
                r = NpcAgendaEngine.apply_tick_one_prepared(prep)
            except Exception:
                continue
            if r and r.get("acted"):
                results.append(r)
        try:
            from core.collusion import try_collude_in_world

            for c in try_collude_in_world(max_pairs=1):
                results.append(c)
        except Exception:
            pass
        try:
            from core.hunt import maybe_flee_npc

            for npc in list_npc_characters(limit=8):
                dest = maybe_flee_npc(npc)
                if dest:
                    results.append(
                        {
                            "acted": True,
                            "text": f"【{npc.name}】似在避祸，已遁往 {dest}。",
                            "kind": "flee",
                        }
                    )
                    break
        except Exception:
            pass
        try:
            from core import rumors

            rumors.maybe_ambient_tick(chance=0.12)
        except Exception:
            pass
        # 因果链推进（karma-event-chains §4.1）：挂 tick_world 尾，照既有
        # 顺带推进先例 try/except 包裹，异常不炸世界 tick。
        try:
            from core.karma_chains import KarmaChainEngine

            for r in KarmaChainEngine.tick_world():
                if r.get("action") == "resolved" and r.get("text"):
                    results.append({
                        "acted": True,
                        "kind": "karma_chain",
                        "text": f"【因果链】{r['text']}",
                    })
        except Exception:
            pass
        return results

    @staticmethod
    def tick_world(max_npcs: int = 5, force: bool = False) -> List[Dict[str, Any]]:
        """批量 tick 若干 NPC（兼容入口：三段连跑，语义与原实现一致）。"""
        prepared = NpcAgendaEngine.prepare_tick_world(max_npcs=max_npcs, force=force)
        NpcAgendaEngine.ai_tick_world(prepared)
        return NpcAgendaEngine.apply_tick_world(prepared)

    @staticmethod
    def list_agendas() -> List[Dict[str, Any]]:
        """议程一览（含中文与副议程摘要）"""
        out = []
        for a in NpcAgendaRepository.list_all():
            extra = a.get("extra") or {}
            sec = extra.get("secondary") or []
            sec_s = "、".join(
                f"{AGENDA_TYPES.get(s.get('agenda_type',''), s.get('agenda_type',''))}"
                for s in sec[:2]
            )
            out.append({
                **a,
                "agenda_cn": AGENDA_TYPES.get(a.get("agenda_type", ""), a.get("agenda_type", "")),
                "secondary_cn": sec_s,
                "secondary": sec,
            })
        return out
