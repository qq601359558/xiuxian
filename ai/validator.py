"""
AI 生成 DSL 语法与天道数值平衡校验器
"""
from typing import Dict, Any, Tuple


class DSLValidator:
    """天道平衡校验器：确保 AI 生成的机制不超模、不崩溃"""

    @staticmethod
    def validate_custom_art(data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        校验自创功法 DSL
        :return: (是否合法, 校验意见/错误原因)
        """
        # 1. 必填字段检查
        required_fields = ["name", "rank", "nature", "cultivation_modifiers", "spells"]
        for f in required_fields:
            if f not in data:
                return False, f"缺少关键天道字段: {f}"

        mods = data.get("cultivation_modifiers", {})
        exp_gain = mods.get("exp_gain_multiplier", 1.0)
        lifespan_burn = mods.get("lifespan_burn_per_year", 0.0)
        tribulation_add = mods.get("tribulation_power_add", 0.0)

        # 2. 算力与价值天平：收益必须匹配代价！
        # 如果修炼加速超过 1.5 倍，必须承担天劫增强或寿命流逝！
        if exp_gain > 1.5:
            if lifespan_burn < 0.2 and tribulation_add < 0.15:
                return False, "【天道不公·降级拦截】进境神速而无寿元损耗或天劫反噬，此乃伪道，天道不容！"

        # 封顶限制
        if exp_gain > 2.5:
            return False, "【数值崩坏】修炼速度倍率不可超过 2.5 倍！"

        return True, "天道准允"
