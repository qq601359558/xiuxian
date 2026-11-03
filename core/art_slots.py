"""
心法槽位引擎（F02）：主修 1 + 辅修 2 的装配/卸下与规则加成。

设计口径（见 docs/compose/spec/arts.md）：
- 自创功法固有效果（最高修炼倍率/燃寿/神通战力）保持原样自动生效，槽位不接管；
  槽位只提供一层独立的「专注」加成，未装配时所有因子恒为 1.0，旧行为不变。
- 主修：闭关修为 ×(1+ART_MAIN_MEDITATION_BONUS)；辅修：斗法战力每门
  +ART_SUB_POWER_BONUS_EACH，封顶 ART_SUB_POWER_BONUS_CAP。
- 任一成功槽位变更进入冷却（防临场刷加成）；首次变更不受冷却。
- 纯规则，无 AI 依赖；引擎只在成功时改角色，失败零副作用，落库由调用方负责。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus

# ---- 常量（新数值只进本模块，总纲约束 2） ----
ART_SUB_MAX = 2  # 辅修槽位数
ART_SLOT_COOLDOWN_SECONDS = 3600.0  # 槽位变更冷却（现实秒，1 小时）
ART_MAIN_MEDITATION_BONUS = 0.10  # 主修专注：闭关修为 +10%
ART_SUB_POWER_BONUS_EACH = 0.03  # 每门有效辅修：斗法战力 +3%
ART_SUB_POWER_BONUS_CAP = 0.06  # 辅修战力加成封顶 +6%


def _fail(msg: str) -> Dict[str, Any]:
    return {"success": False, "message": msg}


def _resolve_skill(c: Character, hint: str) -> Dict[str, Any]:
    """在已习得功法中按名解析（精确 → 子串模糊，与 /穿戴、灵宠同惯例）。
    返回 {"skill": 功法全名} 或 {"error": ...}"""
    hint = (hint or "").strip()
    if not hint:
        return {"error": "须指明功法名。/心法 查看已习得功法。"}
    skills = list(getattr(c, "skills", None) or [])
    if hint in skills:
        return {"skill": hint}
    hits = [s for s in skills if hint in s]
    if not hits:
        return {"error": f"未习得【{hint}】，不可装配。可 /心法 查看已习得功法。"}
    if len(hits) > 1:
        return {"error": f"【{hint}】匹配到多门功法（{'、'.join(hits)}），请指明全名。"}
    return {"skill": hits[0]}


def _cooldown_left(c: Character, now: float) -> float:
    """剩余冷却秒数；从未变更过（changed_at<=0）恒为 0"""
    changed = float(getattr(c, "art_slot_changed_at", 0.0) or 0.0)
    if changed <= 0:
        return 0.0
    return max(0.0, ART_SLOT_COOLDOWN_SECONDS - (now - changed))


def valid_subs(c: Character) -> List[str]:
    """有效辅修：仍在 skills 中、非主修、去重（防御脏数据白嫖）"""
    skills = set(getattr(c, "skills", None) or [])
    main = getattr(c, "main_art", "") or ""
    out: List[str] = []
    for s in getattr(c, "sub_arts", None) or []:
        if s in skills and s != main and s not in out:
            out.append(s)
    return out


class ArtSlotEngine:
    """心法槽位裁决引擎（纯规则，无 AI 依赖）"""

    # ---------------- 变更 ----------------
    @staticmethod
    def _guard_change(c: Character, now: float) -> Optional[Dict[str, Any]]:
        """变更前通用门禁：死亡 / 冷却。返回失败 dict 或 None（放行）"""
        if c.status == CharacterStatus.DEAD:
            return _fail("身死道消，心法已随主而散。")
        left = _cooldown_left(c, now)
        if left > 0:
            return _fail(
                f"【心法未稳】上次调整槽位后心境未平，尚需 {int(left // 60) + 1} 分钟"
                f"方可再改（防临阵换功）。可先 /心法 查看。"
            )
        return None

    @staticmethod
    def set_main(c: Character, name: str, now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else now
        guard = ArtSlotEngine._guard_change(c, now)
        if guard:
            return guard
        found = _resolve_skill(c, name)
        if "error" in found:
            return _fail(found["error"])
        skill = found["skill"]
        if (getattr(c, "main_art", "") or "") == skill:
            return _fail(f"【{skill}】已是主修，无需重设。")
        moved = skill in (getattr(c, "sub_arts", None) or [])
        if moved:
            c.sub_arts = [s for s in c.sub_arts if s != skill]
        c.main_art = skill
        c.art_slot_changed_at = now
        msg = f"【主修】定【{skill}】为心法主修：闭关吐纳专注一门，修为 +{int(ART_MAIN_MEDITATION_BONUS * 100)}%。"
        if moved:
            msg += "（已自辅修移入主修）"
        msg += f" {int(ART_SLOT_COOLDOWN_SECONDS // 60)} 分钟内不可再调整槽位。"
        return {"success": True, "message": msg}

    @staticmethod
    def add_sub(c: Character, name: str, now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else now
        guard = ArtSlotEngine._guard_change(c, now)
        if guard:
            return guard
        found = _resolve_skill(c, name)
        if "error" in found:
            return _fail(found["error"])
        skill = found["skill"]
        if (getattr(c, "main_art", "") or "") == skill:
            return _fail(f"【{skill}】已是主修，不可再入辅修（槽位互斥）。")
        subs = list(getattr(c, "sub_arts", None) or [])
        if skill in subs:
            return _fail(f"【{skill}】已在辅修槽中。")
        if len(subs) >= ART_SUB_MAX:
            return _fail(
                f"辅修槽已满（{ART_SUB_MAX} 门：{'、'.join(subs)}）。先 /卸功 再换。"
            )
        subs.append(skill)
        c.sub_arts = subs
        c.art_slot_changed_at = now
        return {
            "success": True,
            "message": (
                f"【辅修】纳【{skill}】入辅修槽（{len(subs)}/{ART_SUB_MAX}）："
                f"斗法战力 +{int(ART_SUB_POWER_BONUS_EACH * 100)}%。"
                f" {int(ART_SLOT_COOLDOWN_SECONDS // 60)} 分钟内不可再调整槽位。"
            ),
        }

    @staticmethod
    def remove(c: Character, name: str, now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else now
        guard = ArtSlotEngine._guard_change(c, now)
        if guard:
            return guard
        hint = (name or "").strip()
        if not hint:
            return _fail("用法：/卸功 <功法名>。/心法 查看当前槽位。")
        # 只在已装配项里解析（主修 + 辅修）
        equipped = ([c.main_art] if getattr(c, "main_art", "") else []) + list(
            getattr(c, "sub_arts", None) or []
        )
        target = None
        if hint in equipped:
            target = hint
        else:
            hits = [s for s in equipped if hint in s]
            if len(hits) == 1:
                target = hits[0]
            elif len(hits) > 1:
                return _fail(f"【{hint}】匹配到多门已装配功法（{'、'.join(hits)}），请指明全名。")
        if target is None:
            return _fail(f"【{hint}】未装配在心法槽中。/心法 查看当前槽位。")
        if (getattr(c, "main_art", "") or "") == target:
            c.main_art = ""
            where = "主修"
        else:
            c.sub_arts = [s for s in c.sub_arts if s != target]
            where = "辅修"
        c.art_slot_changed_at = now
        return {
            "success": True,
            "message": f"【卸功】已将【{target}】自{where}槽卸下。 {int(ART_SLOT_COOLDOWN_SECONDS // 60)} 分钟内不可再调整槽位。",
        }

    # ---------------- 加成（接入点，只读） ----------------
    @staticmethod
    def meditation_mult(c: Character) -> float:
        """闭关专注加成：主修有效时 ×(1+bonus)，否则 1.0（旧行为）"""
        main = getattr(c, "main_art", "") or ""
        if main and main in (getattr(c, "skills", None) or []):
            return 1.0 + ART_MAIN_MEDITATION_BONUS
        return 1.0

    @staticmethod
    def power_bonus(c: Character) -> float:
        """斗法辅修加成乘子：1 + min(cap, each × 有效辅修数)"""
        n = len(valid_subs(c))
        if n <= 0:
            return 1.0
        return 1.0 + min(ART_SUB_POWER_BONUS_CAP, ART_SUB_POWER_BONUS_EACH * n)

    # ---------------- 面板 ----------------
    @staticmethod
    def panel_text(c: Character, now: Optional[float] = None) -> str:
        now = time.time() if now is None else now
        main = getattr(c, "main_art", "") or ""
        subs = list(getattr(c, "sub_arts", None) or [])
        skills = list(getattr(c, "skills", None) or [])
        lines = ["【心法槽位】主修一门定乾坤，辅修二门助斗法"]
        if main:
            lines.append(f"主修：{main}（闭关修为 +{int(ART_MAIN_MEDITATION_BONUS * 100)}%）")
        else:
            lines.append("主修：（空）—— /主修 <功法名> 装配")
        if subs:
            pct = int(min(ART_SUB_POWER_BONUS_CAP, ART_SUB_POWER_BONUS_EACH * len(valid_subs(c))) * 100)
            lines.append(f"辅修：{'、'.join(subs)}（斗法战力 +{pct}%）")
        else:
            lines.append("辅修：（空）—— /辅修 <功法名> 装配")
        left = _cooldown_left(c, now)
        if left > 0:
            lines.append(f"槽位冷却中：尚余约 {int(left // 60) + 1} 分钟可再调整。")
        if skills:
            lines.append(f"已习得（{len(skills)} 门）：{'、'.join(skills)}")
        else:
            lines.append("尚未习得任何功法。")
        lines.append("注：自创功法的修炼倍率/燃寿/神通照旧自动生效，槽位加成与之独立结算。")
        return "\n".join(lines)
