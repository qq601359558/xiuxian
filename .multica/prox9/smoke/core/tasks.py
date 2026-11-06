"""
任务系统：初玩教学（T1–T10）+ 日常委托
规则钩子推进 · 发奖规则钳制 · 与 GoalEngine 并存
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from storage.db import CharacterRepository, WorldStateRepository
from core.models import CharacterStatus

_KEY = "task_progress"

# 步骤奖励钳制
_REWARD_CAPS = {"stones": 200, "exp": 200, "contrib": 50, "merit": 20}


def _day(now: Optional[float] = None) -> str:
    t = now if now is not None else time.time()
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _intro_steps() -> List[Dict[str, Any]]:
    return [
        {
            "id": "t1_say",
            "title": "T1 识人",
            "desc": "点同场道友，弹窗里说一句话",
            "check": "chat_say",
            "learn": "同场与交谈",
            "reward": {"stones": 10},
        },
        {
            "id": "t2_query",
            "title": "T2 问货",
            "desc": "在交谈中问一句「有什么货」",
            "check": "trade_query",
            "learn": "会话式交易",
            "reward": {},
        },
        {
            "id": "t3_buy",
            "title": "T3 买卖",
            "desc": "买下任意一货（如：买下聚气丹）",
            "check": "trade_buy",
            "learn": "坊市成交",
            "reward": {"items": ["聚气丹"]},
        },
        {
            "id": "t4_pill",
            "title": "T4 服药",
            "desc": "服用聚气丹：/服用 聚气丹",
            "check": "use_pill",
            "learn": "行囊与丹药",
            "reward": {"exp": 20},
        },
        {
            "id": "t5_move",
            "title": "T5 迁跃",
            "desc": "迁跃到另一处：/go 落霞山灵泉（或任一地点）",
            "check": "move",
            "learn": "地图与安全区",
            "reward": {"stones": 15},
        },
        {
            "id": "t6a_tiandao",
            "title": "T6 观照·天道",
            "desc": "观照天道：/天道",
            "check": "look_board",
            "learn": "天道导演",
            "reward": {},
        },
        {
            "id": "t6b_shiqing",
            "title": "T6 观照·世情",
            "desc": "查看世间：/世情",
            "check": "look_schedule",
            "learn": "世界演变",
            "reward": {"merit": 5},
        },
        {
            "id": "t7_seclusion",
            "title": "T7 吐纳",
            "desc": "闭关一时并出关：/闭关 1 → /出关",
            "check": "cultivate_done",
            "learn": "修炼闭环",
            "reward": {"exp": 40},
        },
        {
            "id": "t8_dao",
            "title": "T8 渡劫意识",
            "desc": "了解突破与道途：/突破 或 /目标",
            "check": "look_breakthrough",
            "learn": "突破与寿元",
            "reward": {"exp": 30},
        },
        {
            "id": "t9_echo",
            "title": "T9 望气",
            "desc": "望气天下：/望气",
            "check": "look_echo",
            "learn": "世界回写",
            "reward": {"stones": 20},
        },
        {
            "id": "t10_close",
            "title": "T10 收束",
            "desc": "分清指引与机缘：/任务 与 /目标",
            "check": "look_task",
            "learn": "任务与目标",
            "reward": {"merit": 3, "stones": 15},
            "finale": True,
        },
    ]


TASK_DEFS: Dict[str, Dict[str, Any]] = {
    "intro_teach": {
        "id": "intro_teach",
        "kind": "intro",
        "title": "初玩教学",
        "summary": "用十步学会说话、买卖、迁跃、修炼与观照天道。",
        "steps": _intro_steps(),
        "once_per": "character",
    },
    "daily_greet": {
        "id": "daily_greet",
        "kind": "daily",
        "title": "日常·问安",
        "summary": "与同场道友多说两句。",
        "steps": [
            {
                "id": "d1_talk",
                "title": "问安",
                "desc": "与任一 NPC 交谈（会话内 2 次发言）",
                "check": "chat_rounds",
                "reward": {"merit": 3},
            }
        ],
        "once_per": "day",
    },
    "daily_scout": {
        "id": "daily_scout",
        "kind": "daily",
        "title": "日常·探风",
        "summary": "看世间风向，再走动走动。",
        "steps": [
            {
                "id": "d2_shiqing",
                "title": "观世",
                "desc": "/世情 看世界演变",
                "check": "look_schedule",
                "reward": {},
            },
            {
                "id": "d2_move",
                "title": "走动",
                "desc": "迁跃 1 次：/go <地点>",
                "check": "move",
                "reward": {"stones": 20},
            },
        ],
        "once_per": "day",
    },
}

# check → 可一次推进的步骤（同一 check 多处可复用）
_CHECK_TO_STEPS = {}
for _tid, _td in TASK_DEFS.items():
    for _st in _td.get("steps") or []:
        _CHECK_TO_STEPS.setdefault(_st.get("check"), []).append((_tid, _st.get("id")))


def _pid(character: Any) -> str:
    return str(getattr(character, "id", "") or "")


def _load_store() -> Dict[str, Any]:
    try:
        return WorldStateRepository.get(_KEY) or {}
    except Exception:
        return {}


def _save_store(store: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, store)
    except Exception:
        pass


def ensure_tasks(character: Any, now: Optional[float] = None) -> Dict[str, Any]:
    """保证 intro 激活；刷新 daily 可接"""
    t = _now = now if now is not None else time.time()
    if character is None:
        return {}
    store = _load_store()
    pid = _pid(character)
    rec = store.get(pid) or {
        "active": [],
        "done": [],
        "day_key": "",
        "daily_taken": [],
        "name": getattr(character, "name", ""),
        "updated_at": t,
    }
    day = _day(t)
    # 新一天：清 daily
    if rec.get("day_key") != day:
        rec["day_key"] = day
        rec["daily_taken"] = []
        rec["active"] = [
            a for a in (rec.get("active") or []) if a.get("task_id") not in ("daily_greet", "daily_scout")
        ]
    # intro 自动激活
    done_ids = {d.get("task_id") for d in rec.get("done") or []}
    active_ids = {a.get("task_id") for a in rec.get("active") or []}
    if "intro_teach" not in done_ids and "intro_teach" not in active_ids:
        steps = TASK_DEFS["intro_teach"]["steps"]
        rec["active"].append(
            {
                "task_id": "intro_teach",
                "started_at": t,
                "step_idx": 0,
                "done_steps": [],
                "meta": {},
            }
        )
    rec["updated_at"] = t
    rec["name"] = getattr(character, "name", rec.get("name") or "")
    store[pid] = rec
    _save_store(store)
    return rec


def get_progress(character: Any, now: Optional[float] = None) -> Dict[str, Any]:
    return ensure_tasks(character, now)


def _apply_reward(character: Any, reward: Dict[str, Any]) -> List[str]:
    notes = []
    if not reward:
        return notes
    stones = max(0, min(int(reward.get("stones") or 0), _REWARD_CAPS["stones"]))
    exp = max(0, min(int(reward.get("exp") or 0), _REWARD_CAPS["exp"]))
    contrib = max(0, min(int(reward.get("contrib") or 0), _REWARD_CAPS["contrib"]))
    merit = max(0, min(int(reward.get("merit") or 0), _REWARD_CAPS["merit"]))
    if stones:
        character.spirit_stones = int(character.spirit_stones or 0) + stones
        notes.append(f"灵石+{stones}")
    if exp:
        try:
            character.realm.current_exp = min(
                character.realm.max_exp, int(character.realm.current_exp or 0) + exp
            )
            notes.append(f"修为+{exp}")
        except Exception:
            pass
    if contrib:
        character.sect_contribution = int(character.sect_contribution or 0) + contrib
        notes.append(f"贡献+{contrib}")
    if merit:
        character.karma.add_merit(merit)
        notes.append(f"功德+{merit}")
    for item in (reward.get("items") or [])[:3]:
        name = str(item)[:20]
        if name:
            if name.endswith("阵") or "阵" in name:
                if name not in (character.arrays or []):
                    character.arrays = list(character.arrays or []) + [name]
            else:
                character.inventory = list(character.inventory or []) + [name]
            notes.append(f"得【{name}】")
    try:
        CharacterRepository.save(character)
    except Exception:
        pass
    return notes


def complete_step(
    character: Any,
    check: str,
    *,
    note: str = "",
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """
    钩子上报：完成当前激活任务里匹配 check 的步骤（含跳步：历史步骤一并勾）。
    返回 {advanced:[], finished:[], messages:[]}
    """
    t = now if now is not None else time.time()
    if character is None or not check:
        return {"advanced": [], "finished": [], "messages": []}
    rec = ensure_tasks(character, t)
    advanced: List[Dict[str, Any]] = []
    finished: List[Dict[str, Any]] = []
    messages: List[str] = []

    targets = _CHECK_TO_STEPS.get(check) or []
    if not targets:
        return {"advanced": [], "finished": [], "messages": []}

    store = _load_store()
    pid = _pid(character)
    rec = store.get(pid) or rec

    for a in list(rec.get("active") or []):
        tid = a.get("task_id")
        tdef = TASK_DEFS.get(tid) or {}
        steps = tdef.get("steps") or []
        step_map = {s.get("id"): s for s in steps}
        cur = int(a.get("step_idx") or 0)
        done_steps = list(a.get("done_steps") or [])
        changed = False
        # 跳步：当前及更早未完成步骤若 check 匹配则完成
        for i, st in enumerate(steps):
            if st.get("id") in done_steps:
                continue
            if st.get("check") != check:
                continue
            # 跳步：提前完成后续步骤也勾掉并补奖
            done_steps.append(st.get("id"))
            rew = _apply_reward(character, st.get("reward") or {})
            advanced.append({"task_id": tid, "step": st.get("id"), "learn": st.get("learn") or ""})
            messages.append(
                f"【已学会】{st.get('learn') or st.get('title')}"
                + (f" · {'、'.join(rew)}" if rew else "")
            )
            changed = True
        if changed:
            cur = 0
            while cur < len(steps) and steps[cur].get("id") in done_steps:
                cur += 1
        if changed:
            a["step_idx"] = cur
            a["done_steps"] = done_steps
            a["updated_at"] = t
            # 整链完成？
            if cur >= len(steps):
                rec["active"] = [x for x in rec.get("active") if x.get("task_id") != tid]
                rec.setdefault("done", []).append(
                    {"task_id": tid, "finished_at": t, "title": tdef.get("title")}
                )
                finished.append({"task_id": tid, "title": tdef.get("title")})
                if tdef.get("kind") == "intro" or (steps and steps[-1].get("finale")):
                    msgs = (
                        "【天道小赏】初玩既毕：你已识人、行商、迁跃、吐纳、观照天道。"
                        "此后 /任务 为指引与赏格，/目标 为世间机缘；二者可并行。"
                    )
                    messages.append(msgs)
                    _apply_reward(character, {"merit": 5, "stones": 25})
                    messages.append("终赏：灵石+25、功德+5")
                else:
                    messages.append(f"【委托达成】{tdef.get('title')}")

    rec["updated_at"] = t
    store[pid] = rec
    _save_store(store)
    return {"advanced": advanced, "finished": finished, "messages": messages}


def take_daily(character: Any, task_id: str, now: Optional[float] = None) -> Dict[str, Any]:
    t = now if now is not None else time.time()
    rec = ensure_tasks(character, t)
    tdef = TASK_DEFS.get(task_id) or {}
    if tdef.get("kind") != "daily":
        return {"success": False, "message": "该任务不是日常委托。"}
    if task_id in (rec.get("daily_taken") or []):
        return {"success": False, "message": "今日已接过该委托，明日再来。"}
    if any(a.get("task_id") == task_id for a in rec.get("active") or []):
        return {"success": False, "message": "已在进行中。"}
    store = _load_store()
    pid = _pid(character)
    rec = store.get(pid) or rec
    steps = tdef.get("steps") or []
    rec.setdefault("active", []).append(
        {
            "task_id": task_id,
            "started_at": t,
            "step_idx": 0,
            "done_steps": [],
            "meta": {},
        }
    )
    rec.setdefault("daily_taken", []).append(task_id)
    rec["updated_at"] = t
    store[pid] = rec
    _save_store(store)
    return {"success": True, "message": f"【接委托】{tdef.get('title')}：{tdef.get('summary')}"}


def abandon_task(character: Any, task_id: str) -> Dict[str, Any]:
    rec = ensure_tasks(character)
    tdef = TASK_DEFS.get(task_id) or {}
    if tdef.get("kind") == "intro":
        return {"success": False, "message": "初玩教学不可弃，完成即可。"}
    store = _load_store()
    pid = _pid(character)
    rec = store.get(pid) or rec
    rec["active"] = [a for a in rec.get("active") or [] if a.get("task_id") != task_id]
    store[pid] = rec
    _save_store(store)
    return {"success": True, "message": f"已放下【{tdef.get('title') or task_id}】。"}


def format_task_board(character: Any, now: Optional[float] = None) -> Dict[str, Any]:
    rec = ensure_tasks(character, now)
    tdef_all = TASK_DEFS
    active = rec.get("active") or []
    done = rec.get("done") or []
    lines = ["【任务】指引与赏格（/目标 为世间机缘，二者可并行）"]
    if not active:
        lines.append("暂无进行中任务。日常可 /任务 接 <id>。")
    for a in active:
        tid = a.get("task_id")
        td = tdef_all.get(tid) or {}
        steps = td.get("steps") or []
        idx = int(a.get("step_idx") or 0)
        lines.append("")
        lines.append(f"▶ {td.get('title') or tid}（{td.get('kind')}）— {td.get('summary') or ''}")
        for i, st in enumerate(steps):
            mark = "✓" if st.get("id") in (a.get("done_steps") or []) else ("→" if i == idx else "·")
            lines.append(f"  {mark} {st.get('title')}：{st.get('desc')}")
        nxt = steps[idx] if idx < len(steps) else None
        if nxt:
            lines.append(f"  下一步：{nxt.get('desc')}")
    lines.append("")
    lines.append("可接日常：")
    any_daily = False
    for tid, td in tdef_all.items():
        if td.get("kind") != "daily":
            continue
        if tid in (rec.get("daily_taken") or []):
            lines.append(f"  · {td.get('title')}（今日已接）")
        else:
            any_daily = True
            lines.append(f"  · /任务 接 {tid} — {td.get('summary')}")
    if not any_daily:
        lines.append("  · 今日委托已接完或无更替")
    if done:
        lines.append("")
        lines.append("已完成：")
        for d in done[-5:]:
            lines.append(f"  ✓ {d.get('title') or d.get('task_id')}")
    payload = {
        "ok": True,
        "text": "\n".join(lines),
        "tasks": rec,
        "defs": {k: {"title": v.get("title"), "kind": v.get("kind"), "summary": v.get("summary")} for k, v in tdef_all.items()},
    }
    return payload


def handle_task_command(character: Any, parts: List[str]) -> Dict[str, Any]:
    sub = (parts[1] if len(parts) > 1 else "").strip()
    if sub in ("接", "accept") and len(parts) >= 3:
        tid = parts[2].strip()
        res = take_daily(character, tid)
        return {"ok": res.get("success"), "text": res.get("message", "")}
    if sub in ("弃", "abandon") and len(parts) >= 3:
        res = abandon_task(character, parts[2].strip())
        return {"ok": res.get("success"), "text": res.get("message", "")}
    return format_task_board(character)


def notify_steps(character: Any, check: str, **kw: Any) -> None:
    """钩子便捷入口：打印用 messages 由调用方合并"""
    return complete_step(character, check, **kw)


def hook_note(character: Any, check: str, now: Optional[float] = None) -> str:
    """钩子：完成后拼一行可显示文案（无进度则空）"""
    try:
        res = complete_step(character, check, now=now)
        msgs = res.get("messages") or []
        return "\n".join(msgs)
    except Exception:
        return ""
