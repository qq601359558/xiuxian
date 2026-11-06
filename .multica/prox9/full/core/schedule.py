"""
世情 / 世界演变：玩家向世界态势总览（频道是新闻，这里是账本）
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.models import CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository

_ACTIONS_KEY = "last_schedule"


def _store_actions(user_id: str, actions: List[Dict[str, Any]]) -> None:
    try:
        d = WorldStateRepository.get(_ACTIONS_KEY) or {}
        d[user_id] = {"ts": time.time(), "actions": actions[:30]}
        if len(d) > 50:
            items = sorted(d.items(), key=lambda x: -float(x[1].get("ts") or 0))[:50]
            d = dict(items)
        WorldStateRepository.set(_ACTIONS_KEY, d)
    except Exception:
        pass


def _load_actions(user_id: str) -> List[Dict[str, Any]]:
    try:
        d = WorldStateRepository.get(_ACTIONS_KEY) or {}
        rec = d.get(user_id) or {}
        if time.time() - float(rec.get("ts") or 0) > 1800:
            return []
        return rec.get("actions") or []
    except Exception:
        return []


def build_world_evolution(viewer_id: str = "", now: Optional[float] = None) -> Dict[str, Any]:
    """结构化世界演变数据（指令 / 网页态势卡共用）"""
    t = now if now is not None else time.time()
    payload: Dict[str, Any] = {
        "ok": True,
        "kind": "world_evolution",
        "updated_at": t,
        "director": {},
        "arcs": [],
        "faction": {},
        "echo": {},
        "era": {},
        "blood": [],
        "realms_open": [],
        "npc_brief": [],
        "channel_recent": [],
        "actions": [],
        "summary_lines": [],
    }
    try:
        from core.world_director import director_snapshot

        snap = director_snapshot(t)
        payload["director"] = snap.get("director") or {}
        payload["modifiers"] = snap.get("modifiers") or {}
        payload["arcs"] = snap.get("arcs") or []
        payload["faction"] = snap.get("faction") or {}
        payload["echo"] = snap.get("echo") or {}
        payload["era"] = snap.get("era") or {}
        payload["arc_board_text"] = snap.get("arc_board_text") or ""
        payload["faction_board_text"] = (snap.get("faction") or {}).get("board_text") or ""
        payload["echo_board_text"] = (snap.get("echo") or {}).get("board_text") or ""
        payload["era_board_text"] = (snap.get("era") or {}).get("board_text") or ""
        payload["director_board_text"] = (snap.get("director") or {}).get("board_text") or ""
    except Exception as e:
        payload["director"] = {"error": str(e)[:80]}

    actions: List[Dict[str, Any]] = []
    # 血煞
    try:
        from core.hunt import is_marked

        marked = []
        for c in CharacterRepository.list_all_alive():
            if c.status != CharacterStatus.DEAD and is_marked(c):
                marked.append(c)
        marked.sort(key=lambda x: -x.karma.sin_value)
        for c in marked[:8]:
            payload["blood"].append(
                {
                    "id": c.id,
                    "name": c.name,
                    "realm": c.realm.name,
                    "sin": c.karma.sin_value,
                    "location": c.location,
                }
            )
            actions.append({"kind": "mark", "name": c.name, "loc": c.location, "label": "除凶"})
    except Exception:
        pass

    # 秘境
    try:
        from core.secret_realm import realm_status

        for r in realm_status(t):
            if r.get("is_open"):
                payload["realms_open"].append(r)
                actions.append({"kind": "realm", "name": r.get("name"), "loc": r.get("location"), "label": "秘境"})
    except Exception:
        pass

    # NPC 动向（跟进用）
    try:
        from core.npc_agenda import NpcAgendaEngine, agenda_cn, _is_npc

        agendas = NpcAgendaEngine.list_agendas()
        name_map = {}
        try:
            for c in CharacterRepository.list_all_alive():
                name_map[c.id] = c
        except Exception:
            name_map = {}
        n = 0
        for a in agendas[:40]:
            npc = name_map.get(a.get("npc_id"))
            if not npc or not _is_npc(npc) or npc.status == CharacterStatus.DEAD:
                continue
            n += 1
            label = a.get("agenda_cn") or agenda_cn(a.get("agenda_type"))
            payload["npc_brief"].append(
                {"name": npc.name, "agenda": label, "location": npc.location}
            )
            actions.append({"kind": "npc", "name": npc.name, "loc": npc.location, "label": label})
            if n >= 10:
                break
    except Exception:
        pass

    # 频道近闻（新闻摘要，不替代频道全文）
    try:
        from core.world_channel import WorldChannel

        for m in WorldChannel.recent(limit=8):
            if getattr(m, "level", "") in ("major", "epic", "gm"):
                payload["channel_recent"].append(
                    {
                        "level": m.level,
                        "text": m.text,
                        "location": m.location,
                        "ts": m.ts,
                        "kind": m.kind,
                    }
                )
    except Exception:
        pass

    if viewer_id:
        payload["actions"] = actions
        _store_actions(viewer_id, actions)
    else:
        payload["actions"] = actions

    # 一句话总结
    summary = []
    d = payload.get("director") or {}
    active = d.get("active") or []
    if active:
        summary.append(f"天道活跃态势 {len(active)} 条")
    else:
        summary.append("天道暂无活跃态势")
    if payload.get("arcs"):
        summary.append(f"世界弧 {len(payload['arcs'])} 场")
    fac = (payload.get("faction") or {}).get("modifiers") or {}
    sieges = fac.get("active_sieges") or []
    if sieges:
        summary.append(f"宗门围剿 {len(sieges)}")
    em = (payload.get("echo") or {}).get("modifiers") or {}
    if float(em.get("market_panic") or 0) >= 8:
        summary.append(f"坊市恐慌 {float(em['market_panic']):.0f}")
    if payload.get("blood"):
        summary.append(f"血煞 {len(payload['blood'])} 人")
    bias = (payload.get("era") or {}).get("bias_cn") or {}
    if bias:
        top = sorted(bias.items(), key=lambda x: -float(x[1]))[:2]
        summary.append("史笔：" + "、".join(f"{k}{v:.0f}" for k, v in top))
    payload["summary_lines"] = summary
    return payload


def format_world_schedule(viewer_id: str = "", simple: bool = False) -> Dict[str, Any]:
    """/世情 = 世界演变总览（升级版）"""
    from core.npc_agenda import agenda_cn
    from core.world_channel import WorldChannel

    if simple:
        ev = build_world_evolution(viewer_id)
        lines = ["【世界演变·摘要 / 世情】详情输入 /世情"]
        for s in ev.get("summary_lines") or []:
            lines.append(f"· {s}")
        majors = ev.get("channel_recent") or []
        lines.append("近闻：")
        if majors:
            for m in majors[:3]:
                lines.append(f"· {m.get('text')}")
        else:
            lines.append("  · 风平浪静")
        if viewer_id:
            _store_actions(viewer_id, [])
        return {"text": "\n".join(lines), "actions": [], "evolution": ev}

    ev = build_world_evolution(viewer_id)
    actions = ev.get("actions") or []
    lines = [
        "【世界演变 · 世情】天道/弧/势力/望气/史笔 一页总览",
        "指令：/世情 /世界演变 · /天道 /势力 /望气 /世界弧 /纪元回流 · /频道 看新闻流 · /追 <编号> 跟进",
        "",
        "「" + "；".join(ev.get("summary_lines") or ["世间暂稳"]) + "」",
        "",
        "▌一、天道导演",
    ]
    d = ev.get("director") or {}
    active = d.get("active") or []
    src = d.get("last_source") or "—"
    lines.append(
        f"  上次：{d.get('last_trigger') or '—'} · 来源 {src} · 活跃 {len(active)}"
    )
    if active:
        for a in active[:5]:
            loc = f" @{a.get('location')}" if a.get("location") else ""
            lines.append(f"  · [{a.get('type')}] {a.get('title')}{loc}")
            if a.get("narrative"):
                lines.append(f"    {str(a.get('narrative'))[:60]}")
    else:
        lines.append("  · 暂无活跃指令（/天道 推演 可触发）")

    lines.append("")
    lines.append("▌二、世界弧（预兆→升级→决算）")
    arcs = ev.get("arcs") or []
    if arcs:
        stage_cn = {"prophesy": "预兆", "escalate": "升级", "climax": "决算"}
        for a in arcs[:5]:
            loc = f" @{a.get('location')}" if a.get("location") else ""
            lines.append(
                f"  · [{stage_cn.get(a.get('stage'), a.get('stage'))}] {a.get('title')}{loc}（{a.get('kind')}）"
            )
    else:
        lines.append("  · 暂无进行中的世界弧")

    lines.append("")
    lines.append("▌三、势力格局")
    fac = (ev.get("faction") or {}) or {}
    fm = fac.get("modifiers") or {}
    rels = fac.get("relations") or []
    hostile = [r for r in rels if r.get("status") == "hostile"]
    tense = [r for r in rels if r.get("status") == "tense"]
    if hostile:
        lines.append("  敌对：" + "、".join(f"{r.get('a')}×{r.get('b')}" for r in hostile[:4]))
    if tense:
        lines.append("  紧张：" + "、".join(f"{r.get('a')}×{r.get('b')}" for r in tense[:4]))
    if not hostile and not tense:
        lines.append("  · 各宗门大体平稳")
    sieges = fm.get("active_sieges") or []
    if sieges:
        for s in sieges[:3]:
            lines.append(f"  · 围剿【{s.get('sect')}】→{s.get('target')} @{s.get('loc')}")
    if fm.get("n_open_missions"):
        lines.append(f"  · 开放宗门令 {fm.get('n_open_missions')} 条（/宗门令）")

    lines.append("")
    lines.append("▌四、望气 · 坊市 · 血煞")
    em = (ev.get("echo") or {}).get("modifiers") or {}
    panic = float(em.get("market_panic") or 0)
    if panic >= 8:
        lines.append(
            f"  坊市恐慌 {panic:.0f}：买×{em.get('market_buy_mult',1)} / 卖×{em.get('market_sell_mult',1)}"
            + (f" — {em.get('market_reason')}" if em.get("market_reason") else "")
        )
    else:
        lines.append("  坊市：平稳")
    hot = em.get("hot_regions") or []
    if hot:
        lines.append("  凶地：" + "、".join(f"{loc}({d:.0f})" for loc, d in hot[:4]))
    else:
        lines.append("  凶地：无显著热点")
    blood = ev.get("blood") or []
    if blood:
        lines.append(f"  血煞/重业（{len(blood)}）：")
        for i, b in enumerate(blood[:6], 1):
            lines.append(f"    B{i}. {b.get('name')} {b.get('realm')} 业力{b.get('sin')} @{b.get('location')}")
            actions.append({"kind": "mark", "name": b["name"], "loc": b["location"], "label": "除凶"})
    else:
        lines.append("  血煞：天道清朗")

    lines.append("")
    lines.append("▌五、纪元回流（史笔）")
    era = ev.get("era") or {}
    bias_cn = era.get("bias_cn") or {}
    if bias_cn:
        top = sorted(bias_cn.items(), key=lambda x: -float(x[1]))[:4]
        lines.append("  权重：" + "；".join(f"{k} {v:.1f}" for k, v in top))
    else:
        lines.append("  · 暂无史笔权重（传说未积）")

    lines.append("")
    lines.append("▌六、秘境开启")
    realms = ev.get("realms_open") or []
    if realms:
        for i, r in enumerate(realms[:5], 1):
            lines.append(f"  S{i}. {r.get('name')} @ {r.get('location')}")
            actions.append({"kind": "realm", "name": r.get("name"), "loc": r.get("location"), "label": "秘境"})
    else:
        lines.append("  · 暂无开启中的秘境")

    lines.append("")
    lines.append("▌七、NPC 动向（/追 <编号>）")
    npcs = ev.get("npc_brief") or []
    if npcs:
        for i, n in enumerate(npcs[:8], 1):
            lines.append(f"  {i}. {n.get('name')} · {n.get('agenda')} · {n.get('location')}")
            actions.append(
                {"kind": "npc", "name": n.get("name"), "loc": n.get("location"), "label": n.get("agenda")}
            )
    else:
        lines.append("  · 暂无")

    lines.append("")
    lines.append("▌八、近闻（新闻摘要，全文 /频道）")
    majors = ev.get("channel_recent") or []
    if majors:
        for m in majors[:4]:
            lines.append(f"  · {m.get('text')}")
    else:
        lines.append("  · 风平浪静")

    lines.append("")
    lines.append("说明：频道=刚发生什么；本页=世界现在怎样在演变。细节用 /天道 /势力 /望气 等。")

    if viewer_id:
        # 重新按最终 actions 写入（含血煞/秘境/NPC）
        _store_actions(viewer_id, actions)
    ev["actions"] = actions
    return {"text": "\n".join(lines), "actions": actions, "evolution": ev}


def follow_action(viewer, raw: str) -> Dict[str, Any]:
    """/追 <编号>：支持 3 或 B1 或 S1"""
    raw = (raw or "").strip().upper()
    if not raw:
        return {"success": False, "message": "用法：/追 <编号>，如 /追 1 或 /追 B1"}
    actions = _load_actions(viewer.id)
    kind = "npc"
    num = raw
    if raw.startswith("B"):
        kind = "mark"
        num = raw[1:]
    elif raw.startswith("S"):
        kind = "realm"
        num = raw[1:]
    elif raw.isdigit():
        kind = "npc"
    if not num.isdigit():
        return {"success": False, "message": "编号无效。"}
    idx = int(num) - 1
    bucket = [a for a in actions if a.get("kind") == kind]
    if idx < 0 or idx >= len(bucket):
        return {"success": False, "message": "编号不存在，请先 /世情 刷新。"}
    act = bucket[idx]
    name = act.get("name") or ""
    loc = act.get("loc") or ""

    if kind == "mark":
        from core.hunt import accept, my_target

        if my_target(viewer):
            return {"success": False, "message": "你已有除凶令在身，先 /弃除凶。"}
        res = accept(viewer, name)
        return res

    if kind == "realm":
        if loc and viewer.location != loc:
            return {
                "success": False,
                "message": f"【{name}】入口在 {loc}，请 /go {loc} 后再 /秘境 {name}。",
            }
        return {
            "success": True,
            "message": f"已至秘境【{name}】附近，输入 /秘境 {name} 进入。",
        }

    if loc and viewer.location != loc:
        return {
            "success": False,
            "message": f"【{name}】在 {loc}，请 /go {loc} 后再 /交谈 {name}。",
        }
    return {
        "success": True,
        "message": f"【{name}】就在同场（{act.get('label') or ''}）。可 /交谈 {name}。",
    }
