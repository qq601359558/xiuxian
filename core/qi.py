"""
灵气总量稀释：高阶修士越多，全服吐纳进境越慢（天道自平衡核心）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import QI_HIGH_TIER, QI_DILUTION_K, QI_MULT_MIN, QI_MULT_MAX
from core.models import Character, CharacterStatus


def count_high_tier(alive: Optional[List[Character]] = None) -> int:
    from storage.db import CharacterRepository

    chars = alive if alive is not None else CharacterRepository.list_all_alive()
    n = 0
    for c in chars:
        if c.status == CharacterStatus.DEAD:
            continue
        if c.realm.tier >= QI_HIGH_TIER:
            n += 1
    return n


def global_qi_multiplier(high_count: Optional[int] = None) -> float:
    """
    全局灵气稀释系数（双曲，避免线性被种子 NPC 打穿）。
    mult = 1 / (1 + n * K)，下限 QI_MULT_MIN。
    """
    n = high_count if high_count is not None else count_high_tier()
    mult = 1.0 / (1.0 + max(0, n) * QI_DILUTION_K)
    return max(QI_MULT_MIN, min(QI_MULT_MAX, mult))


def effective_density(location_density: float, high_count: Optional[int] = None) -> Dict[str, Any]:
    """地点密度 × 全局稀释 = 实际修炼倍率"""
    qi = global_qi_multiplier(high_count)
    return {
        "location_density": location_density,
        "qi_multiplier": qi,
        "effective": location_density * qi,
        "high_count": high_count if high_count is not None else count_high_tier(),
        "threshold_tier": QI_HIGH_TIER,
    }


def qi_status_text() -> str:
    info = effective_density(1.0)
    mult = info["qi_multiplier"]
    if mult >= 0.98:
        state = "灵机充沛"
    elif mult >= 0.75:
        state = "灵气尚可"
    elif mult >= 0.55:
        state = "灵脉略显稀薄"
    else:
        state = "天地灵气被高阶大能抽汲，吐纳维艰"
    return (
        f"{state}：全服高阶修士 {info['high_count']} 人，"
        f"灵气稀释系数 {mult:.2f}x（地点灵气仍按各自密度叠加）"
    )
