"""
登录/近况摘要：世间在发生什么 + 与你何干 + 世间目标。
"""
from __future__ import annotations

from typing import Any, Dict

from core.models import Character, CharacterStatus


def briefing(character: Character, *, world_limit: int = 6, me_limit: int = 4) -> Dict[str, Any]:
    import core.jianghu as jianghu
    from core.goals import GoalEngine

    world = jianghu.list_recent(limit=world_limit)
    mine = jianghu.project_related(character.id, limit=me_limit)
    GoalEngine.sync_progress(character)
    goals = GoalEngine.list_for(character)
    active = [g for g in goals if g.get("status") == "active"]
    dead = character.status == CharacterStatus.DEAD or character.lifespan.is_dead()

    world_lines = [jianghu.format_event_line(e) for e in world]
    me_lines = [jianghu.format_event_line(e) for e in mine]
    # 入局结构只增键（game-feel-phase1 §2.3）：端点/命令刷新不触发来访
    entry = None
    try:
        since = character.born_at
        try:
            from storage.db import AccountRepository

            last = AccountRepository.get_last_login(character.user_id)
            if last:
                since = float(last)
        except Exception:
            pass
        entry = build_entry(character, since=since, allow_proactive=False)
    except Exception:
        entry = None
    return {
        "ok": True,
        "dead": dead,
        "location": character.location,
        "world": world_lines,
        "related": me_lines,
        "goals": active,
        "text": format_briefing_text(character, world_lines, me_lines, active, dead),
        "entry": entry,
    }


_GOAL_STATUS_CN = {
    "active": "进行中", "done": "已成", "failed": "已憾",
    "rejected": "已弃", "expired": "已过期", "superseded": "已替",
}


def build_entry(
    character: Character,
    *,
    since: float,
    now: float | None = None,
    allow_proactive: bool = True,
    _out_dirty: list | None = None,
) -> Dict[str, Any]:
    """入局拼装（game-feel-phase1 §2.2/§2.3）。

    拼装顺序写死：① settle_due（先捕获到期快照）→ ② advance_for →
    ③ evaluate_checked_goals（E1）→ ④ 只读组装 lines/queue →
    ⑤ allow_proactive 时至多 1 次 maybe_engage。
    每个数据源各自 try/except，单源失败只缺该源的项。
    character 必须是锁外新读对象（陈旧对象铁律）；①②③ 产生变更时
    经 _out_dirty 回报调用方，由调用方至多回存一次。
    """
    import time as _time

    t = now if now is not None else _time.time()
    changed = False
    queue: list[Dict[str, Any]] = []

    def _item(kind, priority, title, text, ref_id, target):
        return {
            "kind": kind, "priority": priority, "title": title,
            "text": text, "ref_id": ref_id, "target": target, "ts": t,
        }

    # ① 诺言惰性推进（先捕获到期快照）
    due_ids: list[str] = []
    try:
        from core.promises import PROMISE_ACCEPT_TTL_SECONDS, PromiseEngine

        for p in PromiseEngine._involving(character.id):
            st = p.status.value if hasattr(p.status, "value") else str(p.status)
            if st == "ACTIVE" and p.deadline and t > p.deadline:
                due_ids.append(p.id)
            elif st == "PENDING" and t > float(p.created_at or 0) + PROMISE_ACCEPT_TTL_SECONDS:
                due_ids.append(p.id)
    except Exception:
        due_ids = []
    try:
        from core.promises import PromiseEngine

        if PromiseEngine.settle_due(character, t, actor_obj=character):
            changed = True
    except Exception:
        pass
    settled_promises = []
    if due_ids:
        try:
            from core.promises import PromiseEngine, TERMINAL_STATUSES

            for p in PromiseEngine._involving(character.id):
                st = p.status.value if hasattr(p.status, "value") else str(p.status)
                if p.id in due_ids and st in TERMINAL_STATUSES:
                    settled_promises.append(p)
        except Exception:
            settled_promises = []
    if len(settled_promises) > 2:
        queue.append(_item(
            "promise_settled", 1, f"{len(settled_promises)} 条诺言已结算",
            "到期诺言已由天道逐条结算，详见诺言账。",
            settled_promises[0].id, {"command": "/诺言"}))
    else:
        for p in settled_promises:
            queue.append(_item(
                "promise_settled", 1, "诺言已结算",
                f"{p.desc}——{p.settle_note}", p.id, {"command": "/诺言"}))

    # ② 因果链惰性推进
    advance_results: list[Dict[str, Any]] = []
    try:
        from core.karma_chains import KarmaChainEngine

        advance_results = KarmaChainEngine.advance_for(character, t) or []
    except Exception:
        advance_results = []
    for r in advance_results:
        if r.get("action") == "resolved":
            queue.append(_item(
                "karma_resolved", 0, "因果链已兑现",
                r.get("text") or "一条因果链已兑现，恩怨自有回音。",
                r.get("chain_id", ""), {"command": "/因果链"}))
            changed = True
    chains_summary: Dict[str, Any] = {"active": 0, "fermenting": 0, "nearest_mature_game_days": None}
    try:
        from core.karma_chains import KarmaChainEngine

        chains_summary = KarmaChainEngine.status_summary(character, t) or chains_summary
    except Exception:
        pass
    maturing = [r for r in advance_results if r.get("action") in ("fermented", "fermenting", "dormant")]
    nearest = chains_summary.get("nearest_mature_game_days")
    if maturing:
        queue.append(_item(
            "karma_maturing", 3, "因果发酵中",
            "有因果链正在发酵，临近兑现。", maturing[0].get("chain_id", ""),
            {"command": "/因果链"}))
    elif nearest is not None and nearest <= 1:
        queue.append(_item(
            "karma_maturing", 3, "因果将至",
            f"有因果链约 {nearest} 游戏日后到期。", "", {"command": "/因果链"}))

    # MF-1 修复（返工口径 a）：②的 advance_for 由 KarmaChainEngine 以另一
    # 实例自读自存完成兑现落账，入参 character 仍是拼装前快照（灵石/修为/
    # 功德皆兑现前值）。③ 求值前重读角色行、就地同步回入参对象（保对象
    # 同一性）：③ 据兑现后数值求值；join 等调用方以同一对象经
    # CharacterRepository.save 回存时即最新行，不再整行覆写回滚链兑现。
    # ① settle_due 对角色的落账已由其内部分支 save 落盘，重读不丢。
    # MF-R1 修复（第二轮，取舍 (c) 重读合并策略）：briefing() 在本拼装前
    # 已调 GoalEngine.sync_progress——只改内存补目标 + E6 求值、未落盘。
    # 无条件逐字段同步会把内存 goals 整表冲回 DB 旧值（DB goals=[] 的无
    # origin 老角 fate 行误报「尚未立命」、与同响应 goals 字段矛盾）。
    # 故 goals 一字段不整表覆盖，改按 id 并集、内存优先：内存 goals
    # （sync_progress 补出/① E2 翻转的活对象状态）保序在前，DB 独有项
    # 补在后；其余字段仍以 DB 为准——MF-1 的链兑现数值不回滚、③ 仍基于
    # 兑现后数值求值（且对并集后的 goals 求值，DB 独有判定式目标不漏）。
    # 未取 (b) briefing 侧落盘：/近况 与 GET /world/briefing 是读面，
    # 不为修展示口径新增写行为与锁内耗时。
    try:
        from storage.db import CharacterRepository as _CharRepo

        _mem_goals = list(character.goals) if isinstance(character.goals, list) else []
        _latest = _CharRepo.get_by_id(character.id)
        if _latest is not None and _latest is not character:
            for _field in type(character).model_fields:
                setattr(character, _field, getattr(_latest, _field))
            _mem_ids = {
                g.get("id") for g in _mem_goals
                if isinstance(g, dict) and g.get("id")
            }
            _merged_goals = list(_mem_goals)
            for _g in (_latest.goals or []):
                if isinstance(_g, dict) and _g.get("id"):
                    if _g.get("id") not in _mem_ids:
                        _merged_goals.append(_g)
                elif _g not in _merged_goals:
                    _merged_goals.append(_g)
            character.goals = _merged_goals
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "build_entry 重读同步失败，降级沿用入参对象", exc_info=True)

    # ③ 判定式求值（E1）
    try:
        from core.goals import evaluate_checked_goals

        flipped = evaluate_checked_goals(character, t)
        if flipped:
            changed = True
        flips = [g for g in flipped if g.get("source") in ("origin", "fate")][:2]
        for g in flips:
            queue.append(_item(
                "goal_flip", 2, g.get("title", "命途有变"),
                f"目标已{g.get('done_reason', '翻转')}。", g.get("id", ""),
                {"view": "sanctum"}))
    except Exception:
        pass

    # ④ 只读组装：奇遇 / 机缘 / 世界弧
    try:
        from core.event_chains import EventChainEngine

        chain = EventChainEngine.active_for(character.id)
        if chain is not None:
            queue.append(_item(
                "omen_active", 4, getattr(chain, "title", "") or "奇遇进行中",
                "一场奇遇尚未散场。", getattr(chain, "id", ""), {"command": "/奇遇"}))
        else:
            raise LookupError("no event chain")
    except Exception:
        try:
            from core.omen_scene import get_scene

            scene = get_scene(character.id)
            if scene:
                queue.append(_item(
                    "omen_active", 4, scene.get("title") or "奇遇进行中",
                    "一场奇遇尚未散场。", str(scene.get("id", "")), {"command": "/奇遇"}))
        except Exception:
            pass
    try:
        omen_goals = [
            g for g in (character.goals or [])
            if g.get("source") == "omen" and g.get("status") == "active"]
        if omen_goals:
            g = omen_goals[-1]
            queue.append(_item(
                "opportunity", 6, g.get("title", "机缘"),
                g.get("detail", ""), g.get("id", ""), {"command": "/目标"}))
    except Exception:
        pass
    try:
        from core.world_arc import active_arcs

        hit = None
        for a in active_arcs() or []:
            if a.get("location") == character.location or (
                character.sect and a.get("sect") == character.sect):
                hit = a
                break
        if hit is not None:
            queue.append(_item(
                "world_arc", 7, hit.get("title") or "世界弧",
                hit.get("summary") or "与你相关的世界弧正在推进。",
                str(hit.get("id", "")), {"command": "/世情"}))
        else:
            raise LookupError("no personal arc")
    except Exception:
        try:
            from core.world_director import active_directives

            for d in active_directives() or []:
                if d.get("type") == "calamity_forecast":
                    queue.append(_item(
                        "world_arc", 7, d.get("title") or "大劫将至",
                        "天道有劫兆临世。", str(d.get("id", "")), {"command": "/世情"}))
                    break
        except Exception:
            pass

    # lines 组装
    fate_line = "命途：尚未立命，转世后自有新命"
    try:
        goals = list(character.goals or [])
        if getattr(character, "origin", None):
            fate_g = next((g for g in goals if g.get("source") == "fate"), None)
            short_g = next((g for g in goals if g.get("source") == "origin"), None)
            fate_part = (
                f"{fate_g.get('title')}（{_GOAL_STATUS_CN.get(fate_g.get('status'), fate_g.get('status'))}）"
                if fate_g else "尚未立命")
            short_part = (
                f"{short_g.get('title')}（{_GOAL_STATUS_CN.get(short_g.get('status'), short_g.get('status'))}）"
                if short_g else "未立")
            fate_line = f"命途：{fate_part} · 短期：{short_part}"
        else:
            active_goals = [g for g in goals if g.get("status") == "active"]
            if active_goals:
                g0 = active_goals[0]
                fate_line = f"命途：{g0.get('title', '')} — {g0.get('detail', '')}"
    except Exception:
        pass
    fermenting = int(chains_summary.get("fermenting") or 0)
    chains_text = f"发酵中因果链 {fermenting} 条"
    if nearest is not None:
        chains_text += f"，最近一条约 {nearest} 游戏日后到期"
    relations_items: list[Dict[str, Any]] = []
    try:
        from core.relations import relations_recent_and_marks

        recent, _marks = relations_recent_and_marks(character.id, recent_limit=30, pool=30)
        fresh = [x for x in recent if float(x.get("ts") or 0) > float(since or 0)]
        relations_items = (fresh + [x for x in recent if x not in fresh])[:3]
    except Exception:
        relations_items = []

    # ⑤ 主动来访（仅登录拼装；既有预算闸/冷却兜底）
    proactive: list[Dict[str, Any]] = []
    if allow_proactive:
        try:
            from core.npc_proactive import NpcProactiveEngine

            proactive = NpcProactiveEngine.maybe_engage(character, force=False) or []
        except Exception:
            proactive = []
        for pv in proactive[:1]:
            queue.append(_item(
                "npc_visit", 5, f"{pv.get('npc', '有人')} 来访",
                pv.get("line") or pv.get("text") or "", "", {"view": "world"}))
    # S-2：entry.proactive 对外形状为单对象 {text, npc}（取第一条来访），
    # 无来访时为 None——双端前端按 string 或 .text 取值，list 恒空。
    # queue 的 npc_visit 项仍由上方完整列表驱动，逻辑不动。
    proactive_obj: Dict[str, Any] | None = None
    if proactive:
        _pv0 = proactive[0] or {}
        proactive_obj = {
            "text": _pv0.get("text") or _pv0.get("line") or "",
            "npc": _pv0.get("npc", ""),
        }

    queue.sort(key=lambda q: q["priority"])
    queue = queue[:8]
    entry = {
        "version": 1,
        "since": float(since or 0),
        "generated_at": t,
        "lines": {
            "fate": fate_line,
            "chains": {
                "fermenting": fermenting,
                "nearest_mature_game_days": nearest,
                "text": chains_text,
            },
            "relations": relations_items,
        },
        "queue": queue,
        "highlight": queue[:3],
        "rest_count": max(0, len(queue) - 3),
        "empty": len(queue) == 0,
        "empty_text": "江湖无事，可自由行动",
        "proactive": proactive_obj,
    }
    if _out_dirty is not None:
        _out_dirty.append(changed)
    return entry


def format_briefing_text(character, world_lines, me_lines, goals, dead=False) -> str:
    from core.goals import KINDS

    parts = []
    parts.append(f"=== 近况 · {character.name} @ {character.location} ===")
    if dead:
        parts.append("（此身已道消，可转世再入红尘）")
    parts.append("【世间】")
    parts.append("\n".join("  " + (ln or "") for ln in world_lines) if world_lines else "  江湖无事。")
    parts.append("【与你何干】")
    parts.append("\n".join("  " + (ln or "") for ln in me_lines) if me_lines else "  近日暂无与你直接相关的落账。")
    parts.append("【世间目标】")
    if goals:
        for g in goals:
            key = g.get("source") or g.get("type") or ""
            kn = KINDS.get(key, key)
            parts.append(f"  · 【{kn}】{g.get('title')} — {g.get('detail','')}")
    else:
        parts.append("  暂无。")
    return "\n".join(parts)


def format_cli(character: Character) -> str:
    b = briefing(character)
    return b.get("text") or "（无法生成近况）"
