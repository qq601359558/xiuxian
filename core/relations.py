"""
关系可见化拼装（game-feel-phase1 §5.3）：RELATION 留痕 → status 下发。

数据源唯一：EventLedger 中 type="RELATION" 且 target_id=玩家 的行
（写入点在 core/npc_mind.shift_attitude，见 §5.2）。本模块纯读拼装：
relations_recent（近 5 条）与 relations_marks（每 NPC 最近一次变化）
同源同批，保证命盘与同场箭头一致（D1）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

_LABEL_CN = {
    "hostile": "仇视",
    "wary": "戒备",
    "neutral": "中立",
    "friendly": "友善",
    "ally": "亲近",
}


def label_cn(label: str) -> str:
    return _LABEL_CN.get(label or "", "中立")


def parse_relation_row(row: Dict[str, Any]) -> Dict[str, Any] | None:
    """EventLedger 行 → relations_recent 项；refs 解析失败的脏行返回 None（跳过）。"""
    refs = row.get("refs") or []
    kv: Dict[str, str] = {}
    for ref in refs:
        if not isinstance(ref, str) or ":" not in ref:
            continue
        k, v = ref.split(":", 1)
        kv[k] = v
    try:
        delta = int(kv["delta"])
        before_label = kv["before"]
        after_label = kv["after"]
    except (KeyError, TypeError, ValueError):
        return None
    if before_label not in _LABEL_CN or after_label not in _LABEL_CN:
        return None
    return {
        "npc_id": row.get("actor_id") or "",
        "npc_name": row.get("actor_name") or "",
        "delta": delta,
        "before_label": before_label,
        "after_label": after_label,
        "before_cn": label_cn(before_label),
        "after_cn": label_cn(after_label),
        "reason": kv.get("reason", ""),
        "summary": row.get("summary") or "",
        "ts": float(row.get("ts") or 0.0),
    }


def relations_recent_and_marks(
    character_id: str, *, recent_limit: int = 5, pool: int = 30,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """近 recent_limit 条 RELATION + 每 NPC 最近一次变化标记（同批同源）。"""
    try:
        from storage.db import EventLedgerRepository

        rows = EventLedgerRepository.query_by_type_for_target(
            character_id, type="RELATION", limit=pool)
    except Exception:
        rows = []
    items: List[Dict[str, Any]] = []
    for row in rows:
        item = parse_relation_row(row)
        if item is None:
            continue  # 脏行跳过不报错（§5.3）
        items.append(item)
    marks: Dict[str, Dict[str, Any]] = {}
    for item in items:  # rows 已按 ts 倒序：首现即最近一次
        if item["npc_id"] and item["npc_id"] not in marks:
            marks[item["npc_id"]] = {"delta": item["delta"], "ts": item["ts"]}
    return items[:recent_limit], marks
