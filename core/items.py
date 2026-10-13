"""
Core-V2 实体道具与法宝引擎 (Entity Item System)
彻底终结纯字符串背包，赋能装备词缀、前世因果、动态法宝与实体藏宝图。
"""
from __future__ import annotations

import enum
import random
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ItemKind(str, enum.Enum):
    EQUIP = "equip"                # 装备（武器/护甲/饰品）
    PILL = "pill"                  # 丹药
    HERB = "herb"                  # 药材
    TREASURE_MAP = "treasure_map"  # 藏宝图
    MATERIAL = "material"          # 铸造/阵法材料
    RELIC = "relic"                # 上古残片/机缘异宝
    MANUAL = "manual"              # 功法玉简
    CONSUMABLE = "consumable"      # 灵露/消耗仙品


TIER_NAMES = {
    1: "凡品",
    2: "人品",
    3: "地品",
    4: "天品",
    5: "仙品",
}


class ItemAffix(BaseModel):
    """道具词缀"""
    name: str
    desc: str
    effect_type: str = "stat_bonus"
    stat_key: str = "power"
    value: float = 0.0


class ItemEntity(BaseModel):
    """一等公民：实体道具模型"""
    uid: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    template_id: str = "item_generic"
    name: str = "无名物"
    kind: ItemKind = ItemKind.MATERIAL
    slot: Optional[str] = None     # weapon | armor | trinket (当 kind == EQUIP 时)
    tier: int = 1                  # 1=凡, 2=人, 3=地, 4=天, 5=仙
    stats: Dict[str, float] = Field(default_factory=dict)
    affixes: List[ItemAffix] = Field(default_factory=list)
    lineage_lore: str = ""         # 前世传承背景或批注
    creator_id: Optional[str] = None
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.uid

    @classmethod
    def create(
        cls,
        name: str,
        kind: ItemKind = ItemKind.MATERIAL,
        tier: int = 1,
        quality: Optional[int] = None,
        description: str = "",
        stats: Optional[Dict[str, float]] = None,
        slot: Optional[str] = None,
        **kwargs: Any,
    ) -> "ItemEntity":
        actual_tier = quality if quality is not None else tier
        return cls(
            name=name,
            kind=kind,
            tier=actual_tier,
            slot=slot,
            stats=stats or {},
            lineage_lore=description,
            custom_metadata=kwargs,
        )

    @property
    def tier_name(self) -> str:
        return TIER_NAMES.get(self.tier, "凡品")

    @property
    def display_name(self) -> str:
        prefix = f"[{self.tier_name}] "
        if self.affixes:
            aff_names = "·".join(a.name for a in self.affixes[:2])
            return f"{prefix}{self.name}（{aff_names}）"
        return f"{prefix}{self.name}"

    def format_tooltip(self) -> str:
        """生成详细描述卡片"""
        lines = [f"【{self.display_name}】类别：{self.kind.value}"]
        if self.slot:
            lines.append(f"部位：{self.slot}")
        if self.stats:
            stat_str = " · ".join(f"{k}+{v:g}" for k, v in self.stats.items())
            lines.append(f"属性：{stat_str}")
        if self.affixes:
            for aff in self.affixes:
                lines.append(f"词缀·{aff.name}：{aff.desc}")
        if self.lineage_lore:
            lines.append(f"古籍载：{self.lineage_lore}")
        
        # 藏宝图专属展示
        if self.kind == ItemKind.TREASURE_MAP:
            target_name = self.custom_metadata.get("target_node_name", "未知幽域")
            archetype = self.custom_metadata.get("archetype", "未知")
            arch_cn = {
                "combat": "凶地降妖",
                "element_puzzle": "五行天机阵",
                "ruin_hazard": "地渊残迹",
            }.get(archetype, archetype)
            lines.append(f"秘图玄机：隐指【{target_name}】· 阵象【{arch_cn}】")
            riddle = self.custom_metadata.get("riddle_text")
            if riddle:
                lines.append(f"谶语：\"{riddle}\"")

        return "\n".join(lines)


# ==================== 工厂与生成器 ====================

AFFIX_POOL = {
    "破煞": {"desc": "破罡煞之气，对魔道与阴邪额外增伤", "stat_key": "pierce", "val": 0.15},
    "嗜血": {"desc": "剑饮敌血，击杀小幅恢复气血寿元", "stat_key": "lifesteal", "val": 0.08},
    "凝神": {"desc": "道心澄澈，略微抵御心魔侵扰", "stat_key": "mind_guard", "val": 10.0},
    "固元": {"desc": "气血如磐，微幅提升防御与生机", "stat_key": "defense", "val": 15.0},
    "生光": {"desc": "宝光微露，对坊市交易有微弱声望加成", "stat_key": "charm", "val": 5.0},
}


class ItemFactory:
    """法宝与道具铸造工厂"""

    @staticmethod
    def create_equip(
        name: str,
        tier: int = 1,
        slot: str = "weapon",
        base_power: float = 20.0,
        lore: str = "",
        affix_count: int = 1,
    ) -> ItemEntity:
        stats = {"power": base_power * (1.0 + (tier - 1) * 0.6)}
        if slot in ("armor", "trinket"):
            stats["defense"] = base_power * 0.5 * (1.0 + (tier - 1) * 0.5)

        affixes: List[ItemAffix] = []
        if affix_count > 0:
            chosen = random.sample(list(AFFIX_POOL.keys()), min(affix_count, len(AFFIX_POOL)))
            for aff_name in chosen:
                cfg = AFFIX_POOL[aff_name]
                affixes.append(
                    ItemAffix(
                        name=aff_name,
                        desc=cfg["desc"],
                        stat_key=cfg["stat_key"],
                        value=cfg["val"] * tier,
                    )
                )

        return ItemEntity(
            template_id=f"equip_{slot}_{tier}",
            name=name,
            kind=ItemKind.EQUIP,
            slot=slot,
            tier=tier,
            stats=stats,
            affixes=affixes,
            lineage_lore=lore or f"此物泛着淡淡灵晕，不知曾历经何等激斗沉浮。",
        )

    @staticmethod
    def create_treasure_map(
        target_node_id: str,
        target_node_name: str,
        tier: int = 2,
        archetype: str = "element_puzzle",
        riddle: str = "",
        lore: str = "",
    ) -> ItemEntity:
        """生成一张绑定空间节点的实体藏宝图"""
        tier_str = TIER_NAMES.get(tier, "人品")
        map_name = f"{tier_str}·古修遗图[{target_node_name}]"
        if tier >= 4:
            map_name = f"绝代天图·通幽卷[{target_node_name}]"

        return ItemEntity(
            template_id="treasure_map_entity",
            name=map_name,
            kind=ItemKind.TREASURE_MAP,
            tier=tier,
            lineage_lore=lore or f"上古修士随身皮卷，笔触苍劲，封印着一处洞府秘藏的地理天机。",
            custom_metadata={
                "target_node_id": target_node_id,
                "target_node_name": target_node_name,
                "archetype": archetype,  # combat | element_puzzle | ruin_hazard
                "riddle_text": riddle or f"云深水阔何处寻，暗指【{target_node_name}】地脉交汇之处。",
                "is_active": True,
                "puzzle_data": {},
            },
        )

    @staticmethod
    def from_legacy_name(name: str) -> ItemEntity:
        """将旧版纯字符串物品平滑升级为实体对象"""
        name = name.strip()
        if "藏宝图" in name:
            return ItemFactory.create_treasure_map(
                target_node_id="node_heishui_swamp",
                target_node_name="黑水沼泽",
                tier=2,
                archetype="element_puzzle",
                riddle="水炽交错，阵眼潜藏于黑水阴寒之底。",
            )

        # 装备判别
        from config import ITEM_CATALOG
        cfg = ITEM_CATALOG.get(name) or {}
        kind_str = cfg.get("kind", "")
        tier = 1
        grade = cfg.get("grade", "凡品")
        for t, t_name in TIER_NAMES.items():
            if t_name == grade:
                tier = t
                break

        if kind_str == "equip" or any(w in name for w in ("剑", "甲", "珠", "刃", "履", "袍")):
            slot = cfg.get("slot") or ("weapon" if "剑" in name or "刃" in name else "armor")
            power = float(cfg.get("power") or 25.0)
            return ItemFactory.create_equip(name, tier=tier, slot=slot, base_power=power)

        if kind_str == "pill" or "丹" in name:
            return ItemEntity(
                name=name,
                kind=ItemKind.PILL,
                tier=tier,
                lineage_lore=cfg.get("desc", "散发着沁人药香的灵丹。"),
            )

        if kind_str == "herb" or "草" in name or "花" in name or "芝" in name:
            return ItemEntity(
                name=name,
                kind=ItemKind.HERB,
                tier=tier,
                lineage_lore=cfg.get("desc", "山野采集的天地灵材。"),
            )

        return ItemEntity(name=name, kind=ItemKind.MATERIAL, tier=tier)
