"""
自创功法：品阶、功效格式化、闭关加成
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# 品阶：英文 key → (中文, 修炼倍率下限, 上限)
ART_RANKS: Dict[str, Tuple[str, float, float]] = {
    "MORTAL": ("凡品", 1.00, 1.20),
    "EARTH": ("人品", 1.20, 1.50),
    "MYSTIC": ("地品", 1.50, 1.80),
    "HEAVEN": ("天品", 1.80, 2.20),
    "IMMORTAL": ("仙品", 2.20, 2.50),
}

NATURE_CN = {
    "ORTHODOX": "正道",
    "EVIL": "魔道",
    "NEUTRAL": "中立",
}


def infer_rank(exp_mult: float, lifespan_burn: float, trib_add: float) -> str:
    """由数值反推品阶"""
    if exp_mult >= 2.2:
        return "IMMORTAL"
    if exp_mult >= 1.8:
        return "HEAVEN"
    if exp_mult >= 1.5:
        return "MYSTIC"
    if exp_mult >= 1.2:
        return "EARTH"
    return "MORTAL"


def clamp_art(data: Dict[str, Any]) -> Dict[str, Any]:
    """钳制倍率并回写 rank/rank_cn/effects_text"""
    mods = data.get("cultivation_modifiers") or {}
    try:
        exp_m = float(mods.get("exp_gain_multiplier") or 1.0)
    except Exception:
        exp_m = 1.0
    try:
        burn = float(mods.get("lifespan_burn_per_year") or 0.0)
    except Exception:
        burn = 0.0
    try:
        trib = float(mods.get("tribulation_power_add") or 0.0)
    except Exception:
        trib = 0.0

    exp_m = max(1.0, min(2.5, exp_m))
    burn = max(0.0, min(2.0, burn))
    trib = max(-0.1, min(1.0, trib))

    # 天道不公：高倍率必须有代价
    if exp_m > 1.5 and burn < 0.2 and trib < 0.15:
        burn = max(burn, 0.25)
        trib = max(trib, 0.15)

    mods["exp_gain_multiplier"] = round(exp_m, 2)
    mods["lifespan_burn_per_year"] = round(burn, 2)
    mods["tribulation_power_add"] = round(trib, 2)
    data["cultivation_modifiers"] = mods

    rank = infer_rank(exp_m, burn, trib)
    # 若 AI 给的 rank 与数值不符，以数值为准
    data["rank"] = rank
    cn, lo, hi = ART_RANKS[rank]
    data["rank_cn"] = cn
    nature = str(data.get("nature") or "NEUTRAL").upper()
    data["nature"] = nature
    data["nature_cn"] = NATURE_CN.get(nature, "中立")

    # 神通钳制
    spells = []
    for sp in data.get("spells") or []:
        if not isinstance(sp, dict):
            continue
        try:
            mult = float(sp.get("multiplier") or 1.0)
        except Exception:
            mult = 1.0
        mult = max(1.0, min(3.0, mult))
        spells.append(
            {
                "name": str(sp.get("name") or "无名神通"),
                "effect_type": str(sp.get("effect_type") or "DAMAGE"),
                "multiplier": round(mult, 2),
            }
        )
    if not spells:
        spells = [{"name": "基础吐纳", "effect_type": "BUFF", "multiplier": 1.0}]
    data["spells"] = spells[:3]

    data["effects_text"] = build_effects_text(data)
    return data


def build_effects_text(data: Dict[str, Any]) -> str:
    mods = data.get("cultivation_modifiers") or {}
    exp_m = float(mods.get("exp_gain_multiplier") or 1.0)
    burn = float(mods.get("lifespan_burn_per_year") or 0.0)
    trib = float(mods.get("tribulation_power_add") or 0.0)
    lines = []
    bonus_pct = int(round((exp_m - 1.0) * 100))
    if bonus_pct > 0:
        lines.append(f"修炼加速 ×{exp_m:.2f}（闭关/吐纳修为 +{bonus_pct}%）")
    else:
        lines.append("修炼：无显著加速，重在根基稳固")
    if burn > 0:
        lines.append(f"代价：每闭关 1 年额外燃寿 {burn:.2f} 岁")
    else:
        lines.append("代价：无额外燃寿")
    if trib > 0:
        lines.append(f"天劫：威力 +{int(trib*100)}%（渡劫更凶险）")
    elif trib < 0:
        lines.append(f"天劫：威力 {int(trib*100)}%（略缓天威）")
    for sp in data.get("spells") or []:
        et = {"DAMAGE": "战斗伤害", "BUFF": "辅助", "HEAL": "回复", "CONTROL": "制敌"}.get(
            sp.get("effect_type"), sp.get("effect_type")
        )
        lines.append(f"神通：{sp.get('name')} — {et} ×{sp.get('multiplier')}")
    return "\n".join(lines)


def format_art_card(data: Dict[str, Any]) -> str:
    name = data.get("name") or "无名功法"
    rank_cn = data.get("rank_cn") or ART_RANKS.get(data.get("rank"), ("凡品",))[0]
    nature_cn = data.get("nature_cn") or "中立"
    lore = data.get("lore") or ""
    effects = data.get("effects_text") or build_effects_text(data)
    src = data.get("source") or "local"
    lines = [
        f"【自创功法】{rank_cn}·{nature_cn} —— {name}",
        effects,
    ]
    if lore:
        lines.append(f"判词：{lore}")
    lines.append(f"（来源：{'天道推演' if src == 'ai' else '残卷推演'}）")
    return "\n".join(lines)


def best_exp_multiplier(arts: Optional[List[Dict[str, Any]]]) -> float:
    best = 1.0
    for a in arts or []:
        try:
            best = max(best, float((a.get("cultivation_modifiers") or {}).get("exp_gain_multiplier") or 1.0))
        except Exception:
            continue
    return best


def total_burn_per_year(arts: Optional[List[Dict[str, Any]]]) -> float:
    """多门功法取最高燃寿，不叠加（防滚雪球）"""
    best = 0.0
    for a in arts or []:
        try:
            best = max(best, float((a.get("cultivation_modifiers") or {}).get("lifespan_burn_per_year") or 0.0))
        except Exception:
            continue
    return best


def list_arts_text(arts: Optional[List[Dict[str, Any]]]) -> str:
    arts = arts or []
    if not arts:
        return "尚未自创任何功法。可用 /自创功法 <理念>。"
    lines = [f"【已悟功法】共 {len(arts)} 门（闭关按最高修炼倍率生效）"]
    for i, a in enumerate(arts, 1):
        lines.append(f"\n—— {i} ——")
        lines.append(format_art_card(a))
    return "\n".join(lines)
