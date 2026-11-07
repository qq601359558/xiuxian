"""
转世继承（reincarnation-inheritance §2.3/§2.5）：因果影子施加、墓碑查询、
留痕摘要与「前世因果」文本拼装。server 与 CLI 共用同一引擎，文案同源。

口径要点：
- 影子只认最近一世 trace，不叠加多世；施加用 set（绝对值），天然幂等。
- shadow_applied 除 spec 的 {"life_no","char_id"} 外另存本次实际用的
  retention/cap 两键（Dict[str, Any] 容纳），供 legacy_info 的
  karma_shadow 按「实际施加口径」只读重算展示；幂等判定只比
  life_no + char_id 两键。
- 玩家间 KarmaLink（师徒/结拜）不施加、不重建，只在因果清单以文字呈现。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import SHADOW_APPLY_MIN, SHADOW_CAP, SHADOW_RETENTION
from core.legacy import LegacyAccount, LifeTrace
from core.models import Character

# 态度标签口径与 NpcMindRepository.set_attitude 一致（阈值同源）
_LABEL_CN = {
    "hostile": "仇视",
    "wary": "戒备",
    "neutral": "中立",
    "friendly": "友善",
    "ally": "亲近",
}


def label_for_value(value: int) -> str:
    if value <= -40:
        return "hostile"
    if value <= -15:
        return "wary"
    if value >= 40:
        return "ally"
    if value >= 15:
        return "friendly"
    return "neutral"


def label_cn(value: int) -> str:
    return _LABEL_CN.get(label_for_value(value), "中立")


def shadow_value(raw: int, retention: float, cap: int) -> int:
    """前世态度原值 → 本世施加值（衰减 + 硬顶钳制）"""
    v = int(round(raw * retention))
    return max(-int(cap), min(int(cap), v))


def applied_shadow_entries(
    account: Optional[LegacyAccount],
    trace: Optional[LifeTrace],
    retention: float = SHADOW_RETENTION,
    cap: int = SHADOW_CAP,
) -> List[Dict[str, Any]]:
    """统一展示/计数口径（观察4，评审修订）：实际会落账的影子条目清单。

    过滤 |折算值| < SHADOW_APPLY_MIN 的条目（这类条目从未落账，不应
    在文本/计数中呈现为「本世 ±X」）。已施加时（shadow_applied 命中
    该 trace 的 life_no）用 marker 已存的 retention/cap 口径，未施加
    （死者预览）用调用方给的基准口径。
    返回 [{npc_id, npc_name, kind, raw_value, value, label}]。
    """
    if trace is None:
        return []
    eff_retention, eff_cap = retention, cap
    marker = (getattr(account, "shadow_applied", None) or {}) if account else {}
    if marker.get("life_no") == trace.life_no:
        if marker.get("retention") is not None:
            eff_retention = float(marker.get("retention"))
        if marker.get("cap") is not None:
            eff_cap = int(marker.get("cap"))
    out: List[Dict[str, Any]] = []
    for entry in trace.shadow or []:
        v = shadow_value(entry.value, eff_retention, eff_cap)
        if abs(v) < SHADOW_APPLY_MIN:
            continue
        out.append({
            "npc_id": entry.npc_id,
            "npc_name": entry.npc_name,
            "kind": entry.kind,
            "raw_value": entry.value,
            "value": v,
            "label": label_for_value(v),
        })
    return out


# ---------------- 因果影子施加 ----------------
def apply_karma_shadow(
    account: LegacyAccount,
    new_char: Character,
    *,
    retention: float,
    cap: int,
) -> List[Dict[str, Any]]:
    """把最近一世的因果影子按 retention/cap 施加到新角身上（免费，非 boost）。

    返回 [{npc_name, value, label}] 供转世文案与因果清单展示。
    幂等：shadow_applied 已记同一世 + 同一新角时直接返回已施加清单，不重复写。
    本函数不落盘：account 的保存由调用方在转世编排末尾统一完成。
    """
    from storage.db import CharacterRepository, NpcMindRepository

    if not account.traces:
        return []
    trace = account.traces[-1]
    if trace.character_id == new_char.id:
        return []

    def _planned(eff_retention: float, eff_cap: int) -> List[Dict[str, Any]]:
        # 本世应施加清单（只读推导：NPC 仍存在 + 施加后 |v| ≥ SHADOW_APPLY_MIN）
        out: List[Dict[str, Any]] = []
        for entry in trace.shadow:
            v = shadow_value(entry.value, eff_retention, eff_cap)
            if abs(v) < SHADOW_APPLY_MIN:
                continue
            if CharacterRepository.get_by_id(entry.npc_id) is None:
                continue
            out.append({
                "npc_id": entry.npc_id,
                "npc_name": entry.npc_name,
                "value": v,
                "label": label_for_value(v),
            })
        return out

    applied_marker = account.shadow_applied or {}
    if (
        applied_marker.get("life_no") == trace.life_no
        and applied_marker.get("char_id") == new_char.id
    ):
        # MF-4（评审修订）：幂等重入按 marker 已存的 retention/cap 重算
        # 返回（与 current_karma_shadow 口径一致），不按本次参数伪造、不写库
        eff_retention = float(applied_marker.get("retention") or SHADOW_RETENTION)
        eff_cap = int(applied_marker.get("cap") or SHADOW_CAP)
        return [
            {"npc_name": p["npc_name"], "value": p["value"], "label": p["label"]}
            for p in _planned(eff_retention, eff_cap)
        ]

    planned = _planned(retention, cap)

    for p in planned:
        NpcMindRepository.set_attitude(p["npc_id"], new_char.id, p["value"])
    account.shadow_applied = {
        "life_no": trace.life_no,
        "char_id": new_char.id,
        "retention": retention,
        "cap": cap,
    }
    return [
        {"npc_name": p["npc_name"], "value": p["value"], "label": p["label"]}
        for p in planned
    ]


def current_karma_shadow(account: LegacyAccount) -> List[Dict[str, Any]]:
    """当前角色这一世被施加的影子清单（只读推导，不落新表）：
    [{npc_name, value, label, from_life}]；未施加过为空。

    retention/cap 取 shadow_applied 中记录的实际施加口径，缺失时回退基准值。
    """
    from storage.db import CharacterRepository

    marker = account.shadow_applied or {}
    life_no = marker.get("life_no")
    if life_no is None:
        return []
    trace = next((t for t in account.traces if t.life_no == life_no), None)
    if trace is None:
        return []
    retention = float(marker.get("retention") or SHADOW_RETENTION)
    cap = int(marker.get("cap") or SHADOW_CAP)
    out: List[Dict[str, Any]] = []
    for entry in trace.shadow:
        v = shadow_value(entry.value, retention, cap)
        if abs(v) < SHADOW_APPLY_MIN:
            continue
        if CharacterRepository.get_by_id(entry.npc_id) is None:
            continue
        out.append({
            "npc_name": entry.npc_name,
            "value": v,
            "label": label_for_value(v),
            "from_life": trace.life_no,
        })
    return out


# ---------------- 留痕摘要（API 下发） ----------------
def trace_summary(trace: LifeTrace) -> Dict[str, Any]:
    """LifeTrace 的结构化摘要（legacy_info / dead_payload 共用口径，只增字段）"""
    return {
        "life_no": trace.life_no,
        "character_id": trace.character_id,
        "name": trace.name,
        "realm": trace.realm,
        "cause": trace.cause,
        "lifespan_lived": trace.lifespan_lived,
        "sin": trace.sin,
        "merit": trace.merit,
        "points_gained": trace.points_gained,
        "died_at": trace.died_at,
        "sect": trace.sect,
        "skills_learned": list(trace.skills_learned),
        "belongings": list(trace.belongings),
        "shadow": [
            {
                "npc_id": e.npc_id, "npc_name": e.npc_name,
                "value": e.value, "kind": e.kind,
            }
            for e in trace.shadow
        ],
        "shadow_count": len(trace.shadow),
        "open_promises": [
            {
                "other_name": p.other_name, "desc": p.desc,
                "kind": p.kind, "role": p.role,
            }
            for p in trace.open_promises
        ],
        "promises_count": len(trace.open_promises),
        # 游戏感第一期（§3.9）：评语四键只增（dead_payload/legacy_info 自动受益）
        "fate_summary": getattr(trace, "fate_summary", "") or "",
        "life_epitaph": getattr(trace, "life_epitaph", "") or "",
        "origin_signature": getattr(trace, "origin_signature", "") or "",
        "unfinished_prop": dict(getattr(trace, "unfinished_prop", None) or {}),
    }


# ---------------- 墓碑 ----------------
def tombstone_text(trace: LifeTrace) -> str:
    """墓碑文本（引擎同源拼装，server/CLI 共用）"""
    lines = [
        f"【墓碑】{trace.name}",
        f"{trace.name} · {trace.realm} · {trace.cause} · "
        f"享寿 {trace.lifespan_lived} 岁 · 业 {trace.sin} 德 {trace.merit}",
        f"道统点 +{trace.points_gained} · 第 {trace.life_no} 世",
        f"因果摘要：前世余绪 {len(trace.shadow)} 条 · 未了之诺 {len(trace.open_promises)} 条",
    ]
    # 游戏感第一期（§3.9 落点①）：评语非空时末尾只增一行
    epitaph = getattr(trace, "life_epitaph", "") or ""
    if epitaph:
        lines.append(f"一生评语：{epitaph}")
    return "\n".join(lines)


def find_trace(name: str) -> Optional[LifeTrace]:
    """扫描全部账户 traces 按道号精确匹配，返回最近一世的留痕（died_at 最大）。"""
    from storage.db import LegacyRepository

    target = (name or "").strip()
    if not target:
        return None
    best: Optional[LifeTrace] = None
    for account in LegacyRepository.list_all():
        for trace in account.traces or []:
            if trace.name != target:
                continue
            if best is None or trace.died_at >= best.died_at:
                best = trace
    return best


def find_tombstone(name: str) -> Optional[str]:
    """按道号查墓碑文本；查无此人返回 None（调用方呈现「江湖无此碑」）。"""
    trace = find_trace(name)
    if trace is None:
        return None
    return tombstone_text(trace)


# ---------------- 前世因果清单（/道统 文本段） ----------------
def player_bond_lines(trace: LifeTrace) -> List[str]:
    """玩家间旧缘文字行：按旧角色 id 现查 KarmaLink 孤儿行（师徒/结拜），
    只呈现、不重建（spec §2.5 注）。"""
    from storage.db import CharacterRepository, KarmaLinkRepository

    lines: List[str] = []
    try:
        links = KarmaLinkRepository.list_all()
    except Exception:
        return lines
    seen = set()
    for link in links:
        if link.link_type not in ("师徒", "结拜"):
            continue
        if not link.involves(trace.character_id):
            continue
        other_id, other_name = link.other_side(trace.character_id)
        other = CharacterRepository.get_by_id(other_id)
        if other is None:
            continue
        uid = str(other.user_id or "")
        if uid.startswith("npc_") or uid.startswith("ai_npc_"):
            continue  # NPC 旧缘走影子口径，不在此重复呈现
        key = (other_id, link.link_type)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"旧缘：{other_name}（{link.link_type}）——已随旧世消散")
    return lines


def causality_text(account: LegacyAccount) -> str:
    """「前世因果」段文本（server /道统 与 CLI render_legacy_panel 同源）：
    最近一世 trace 的影子清单（折算后本世值）+ 未了之诺回声 + 玩家旧缘行。
    无 trace 时返回空串（整段省略）。"""
    if not account.traces:
        return ""
    trace = account.traces[-1]
    lines = [f"【前世因果】第 {trace.life_no} 世 · {trace.name}（{trace.realm} · {trace.cause}）"]
    # 观察4：统一走 applied_shadow_entries（已施加 marker 口径 / 未施加
    # 基准口径，低于 SHADOW_APPLY_MIN 的条目不进清单，避免显示已落账假象）
    _applied = applied_shadow_entries(account, trace)
    if _applied:
        lines.append("因果余绪（前世态度折入本世）：")
        for ent in _applied:
            raw = ent["raw_value"]
            v = ent["value"]
            lines.append(f"· {ent['npc_name']}：前世{label_cn(raw)}（{raw:+d}）→ 本世 {v:+d}（{label_cn(v)}）")
    if trace.open_promises:
        lines.append("未了之诺（已随旧世消散）：")
        for p in trace.open_promises:
            who = f"{p.role}【{p.other_name}】" if p.role else f"【{p.other_name}】"
            lines.append(f"· {who}：{p.desc}——已随旧世消散")
    lines.extend(player_bond_lines(trace))
    if len(lines) == 1:
        return ""
    return "\n".join(lines)
