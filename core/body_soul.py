"""
炼体/炼神双修（F10）：两条与主境界并行的副修进度，资源换确定性层数。
规则权威：成本、层数、加成、寿元微增全部在此裁决；叙事只用本地模板，不依赖 AI。
Spec：docs/compose/spec/body-soul.md
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.models import Character, CharacterStatus

# ==================== 常量（对照坊市物价与既有加成环校准） ====================
BODY_MAX_LEVEL = 10             # 炼体层数上限
SOUL_MAX_LEVEL = 10             # 炼神层数上限

BODY_POWER_PER_LEVEL = 0.01     # 炼体每层斗法战力 +1%
BODY_POWER_CAP = 0.10           # 炼体战力封顶 +10%（与灵宠同档，全乘链最小环之一）
BODY_LIFESPAN_PER_LEVEL = 1.0   # 炼体每层增寿 1 岁（升层瞬间发放）
BODY_LIFESPAN_TOTAL_CAP = 10.0  # 炼体增寿总量封顶（= 单层量 × 满层，天然不可超发）

SOUL_DAO_HEART_PER_LEVEL = 2    # 炼神每层有效道心 +2（只供抗性判定点读取，不改本体）
SOUL_DAO_HEART_CAP = 20         # 炼神道心加值封顶（突破惩罚至多减免 10% 成功率）
SOUL_SENSE_PER_LEVEL = 3        # 炼神每层神识探查 +3（满层 +30，约天灵根修正量级）

BODY_ITEM = "妖兽内丹"          # 炼体材料：探险掉落/坊市既有材料（价 80）
SOUL_ITEM = "百年灵芝"          # 炼神材料：探险掉落/灵田产出既有材料（价 55）
BODY_STONES_PER_LEVEL = 20      # 炼体目标层 L 的灵石成本 = 20 × L
SOUL_STONES_PER_LEVEL = 15      # 炼神目标层 L 的灵石成本 = 15 × L

TRACK_CN = {"body": "炼体", "soul": "炼神"}


def _clamp_level(v: Any, cap: int) -> int:
    """层数读取钳制（防脏数据超发加成）"""
    try:
        n = int(v or 0)
    except Exception:
        return 0
    return max(0, min(cap, n))


def material_count_for(target_level: int) -> int:
    """升至目标层 L（1 起）的材料数：L1-3:1、L4-6:2、L7-9:3、L10:4（满层共 22 枚）"""
    L = max(1, int(target_level))
    return (L - 1) // 3 + 1


def next_cost(track: str, level: int) -> Optional[Dict[str, Any]]:
    """下一层成本 {item, item_count, stones}；已满层返回 None"""
    cap = BODY_MAX_LEVEL if track == "body" else SOUL_MAX_LEVEL
    lv = _clamp_level(level, cap)
    if lv >= cap:
        return None
    target = lv + 1
    per_stone = BODY_STONES_PER_LEVEL if track == "body" else SOUL_STONES_PER_LEVEL
    item = BODY_ITEM if track == "body" else SOUL_ITEM
    return {"item": item, "item_count": material_count_for(target), "stones": per_stone * target}


class BodySoulEngine:
    """炼体/炼神裁决引擎（纯规则，无 AI 依赖）；只在成功时改角色，失败零副作用"""

    # ---------------- 只读加成（未修炼恒为旧行为） ----------------
    @staticmethod
    def body_level(c: Character) -> int:
        return _clamp_level(getattr(c, "body_level", 0), BODY_MAX_LEVEL)

    @staticmethod
    def soul_level(c: Character) -> int:
        return _clamp_level(getattr(c, "soul_level", 0), SOUL_MAX_LEVEL)

    @staticmethod
    def power_bonus(c: Character) -> float:
        """炼体斗法战力乘子（与 PetEngine.power_bonus 同模式）"""
        return 1.0 + min(BODY_POWER_CAP, BODY_POWER_PER_LEVEL * BodySoulEngine.body_level(c))

    @staticmethod
    def sense_bonus(c: Character) -> int:
        """炼神神识探查加值（接 CombatEngine.scan_surroundings 的 s_sense）"""
        return SOUL_SENSE_PER_LEVEL * BodySoulEngine.soul_level(c)

    @staticmethod
    def dao_heart_bonus(c: Character) -> int:
        """炼神有效道心加值（封顶 SOUL_DAO_HEART_CAP）"""
        return min(SOUL_DAO_HEART_CAP, SOUL_DAO_HEART_PER_LEVEL * BodySoulEngine.soul_level(c))

    @staticmethod
    def effective_dao_heart(c: Character) -> int:
        """有效道心：供突破心魔惩罚与心魔 death 门读取；本体 dao_heart 不被副修改动"""
        return min(100, int(c.karma.dao_heart) + BodySoulEngine.dao_heart_bonus(c))

    # ---------------- 修炼 ----------------
    @staticmethod
    def _train(c: Character, track: str, times: int) -> Dict[str, Any]:
        cn = TRACK_CN[track]
        item_name = BODY_ITEM if track == "body" else SOUL_ITEM
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
            return {"success": False, "message": "已死之身，副修随旧世俱散。"}
        cap = BODY_MAX_LEVEL if track == "body" else SOUL_MAX_LEVEL
        level = BodySoulEngine.body_level(c) if track == "body" else BodySoulEngine.soul_level(c)
        if level >= cap:
            return {"success": False, "message": f"【{cn}】已至 {cap} 层圆满，无可再进。"}
        try:
            n = int(times)
        except Exception:
            n = 1
        n = max(1, min(n, cap - level))

        gained = 0
        spent_items = 0
        spent_stones = 0
        stop_reason = ""
        for _ in range(n):
            cost = next_cost(track, level)
            if cost is None:
                break
            have_items = list(c.inventory or []).count(cost["item"])
            if have_items < cost["item_count"]:
                stop_reason = f"缺少【{cost['item']}】（需 {cost['item_count']}，现有 {have_items}）"
                break
            if int(c.spirit_stones) < cost["stones"]:
                stop_reason = f"灵石不足（需 {cost['stones']}，现有 {int(c.spirit_stones)}）"
                break
            # 校验通过才扣费升层（单层原子：校验→扣费→升层）
            for _i in range(cost["item_count"]):
                c.inventory.remove(cost["item"])
            c.spirit_stones -= cost["stones"]
            level += 1
            gained += 1
            spent_items += cost["item_count"]
            spent_stones += cost["stones"]
            if track == "body":
                c.body_level = level
                # 寿元只在真实升层瞬间发放，并按封顶显式守卫：
                # 已发量 = 升层前钳后层数 × 单层量，本次增量不使总量越过 TOTAL_CAP
                granted_before = BODY_LIFESPAN_PER_LEVEL * (level - 1)
                grant = min(BODY_LIFESPAN_PER_LEVEL,
                            max(0.0, BODY_LIFESPAN_TOTAL_CAP - granted_before))
                if grant > 0:
                    c.lifespan.add_lifespan(grant)
            else:
                c.soul_level = level

        if gained <= 0:
            return {"success": False, "message": f"【{cn}】未能精进：{stop_reason}。分文未扣。"}
        tail = f"；后续因 {stop_reason} 停下" if stop_reason and gained < n else ""
        if track == "body":
            pct = int(round(min(BODY_POWER_CAP, BODY_POWER_PER_LEVEL * level) * 100))
            effect = f"战力加成 +{pct}%、累计增寿 {BODY_LIFESPAN_PER_LEVEL * level:.0f} 岁"
        else:
            effect = f"有效道心 +{BodySoulEngine.dao_heart_bonus(c)}、神识 +{BodySoulEngine.sense_bonus(c)}"
        return {
            "success": True,
            "levels_gained": gained,
            "level": level,
            "message": (
                f"【{cn}精进】连破 {gained} 层，臻至 {level} 层！"
                f"耗 【{item_name}】{spent_items} 枚、灵石 {spent_stones} 块{tail}。"
                f"当前副修成效：{effect}。"
            ),
        }

    @staticmethod
    def train_body(c: Character, times: int = 1) -> Dict[str, Any]:
        return BodySoulEngine._train(c, "body", times)

    @staticmethod
    def train_soul(c: Character, times: int = 1) -> Dict[str, Any]:
        return BodySoulEngine._train(c, "soul", times)

    # ---------------- 面板 ----------------
    @staticmethod
    def panel_text(c: Character, track: str) -> str:
        cn = TRACK_CN[track]
        cap = BODY_MAX_LEVEL if track == "body" else SOUL_MAX_LEVEL
        level = BodySoulEngine.body_level(c) if track == "body" else BodySoulEngine.soul_level(c)
        other = "soul" if track == "body" else "body"
        other_level = BodySoulEngine.soul_level(c) if track == "body" else BodySoulEngine.body_level(c)
        if track == "body":
            pct = min(BODY_POWER_CAP, BODY_POWER_PER_LEVEL * level) * 100
            effect = (
                f"斗法战力 +{pct:.0f}%（每层 +1%，封顶 +10%）；"
                f"已增寿 {BODY_LIFESPAN_PER_LEVEL * level:.0f} 岁（封顶 +10 岁）"
            )
        else:
            effect = (
                f"有效道心 +{BodySoulEngine.dao_heart_bonus(c)}（突破/心魔抗性判定读取，本体道心不变）；"
                f"神识探查 +{BodySoulEngine.sense_bonus(c)}"
            )
        lines = [
            f"【{cn}】副修 {level} / {cap} 层",
            f"  · 当前成效：{effect}",
            f"  · 另一轨：{TRACK_CN[other]} {other_level} 层（/{TRACK_CN[other]} 查看）",
        ]
        cost = next_cost(track, level)
        if cost is None:
            lines.append("  · 已至圆满，无可再进。")
        else:
            have = list(c.inventory or []).count(cost["item"])
            lines.append(
                f"  · 下一层（{level + 1} 层）成本：【{cost['item']}】× {cost['item_count']}"
                f"（现有 {have}）+ 灵石 {cost['stones']}（现有 {int(c.spirit_stones)}）"
            )
            lines.append(f"  · 修炼：/{cn} 修炼 [次数]（付满一层成本即升一层，无骰子；资源不足零扣费）")
        return "\n".join(lines)
