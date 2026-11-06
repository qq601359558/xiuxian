"""
天地道则 · 修士道体数据合规与守恒引擎 (Character Integrity & Audit Rule)
"""
from typing import Optional, List, Collection
import time

from core.models import Character, CharacterStatus


class CharacterIntegrityError(ValueError):
    """道体合规通用异常基类"""
    pass


class CharacterDeadError(CharacterIntegrityError):
    """道身已殒异常（寿尽或身死道消）"""
    pass


class CharacterBusyError(CharacterIntegrityError):
    """定势排他性冲突（闭关/被擒）"""
    pass


class InsufficientCurrencyError(CharacterIntegrityError):
    """灵石资财不足异常"""
    pass


class BagFullError(CharacterIntegrityError):
    """纳戒百宝囊满格异常"""
    pass


class CharacterIntegrity:
    """修士道体合规核验与守恒审计器"""

    ALLOWED_MEDITATING_ACTIONS: Collection[str] = {
        "/look", "/地图", "look", "/道身",
        "/here", "/同场", "/who",
        "/help", "/帮助",
        "/emerge", "/出关",
        "/legacy", "/道统",
        "/goals", "/目标",
        "/qi", "/灵气",
        "/season", "/纪元",
        "/agenda", "/议程",
        "/roster", "/名录",
        "/bounty", "/告示",
        "/profile", "/人物", "/角色",
        "/logout", "/下线",
    }

    ALLOWED_CAPTURED_ACTIONS: Collection[str] = {
        "/help", "/帮助",
        "/profile", "/人物", "/角色",
        "/who", "/here", "/同场",
        "/logout", "/下线",
        "/自救", "/认输", "/赎身",
    }

    ALLOWED_DEAD_ACTIONS: Collection[str] = {
        "/help", "/帮助",
        "/legacy", "/道统",
        "/reincarnate", "/转世",
        "/who",
        "/logout", "/下线",
    }

    @classmethod
    def assert_alive(cls, char: Character, now: Optional[float] = None) -> None:
        """核验修士道身存活状态与寿元非负"""
        t = now or time.time()
        is_dead = (
            char.status == CharacterStatus.DEAD
            or char.lifespan.is_dead(t)
            or char.lifespan.get_remaining_years(t) <= 0.0
        )
        if is_dead:
            if char.status != CharacterStatus.DEAD:
                char.status = CharacterStatus.DEAD
            cause = char.death_cause or "寿尽道消"
            raise CharacterDeadError(
                f"【天道敕令】修士 {char.name} 已坐化道消（死因：{cause}），不可再行世俗之事。请轮回转世！"
            )

    @classmethod
    def assert_idle(
        cls,
        char: Character,
        action: Optional[str] = None,
        allowed_actions: Optional[Collection[str]] = None,
    ) -> None:
        """核验修士是否处于自由活动状态（排斥闭关/被擒）"""
        act = (action or "").strip().lower()
        if char.status == CharacterStatus.MEDITATING:
            allow = allowed_actions or cls.ALLOWED_MEDITATING_ACTIONS
            if act not in allow:
                raise CharacterBusyError(
                    f"【闭关锁门】修士 {char.name} 正闭关入定，六识封闭，不可执行世俗行动。可 /出关 提前收功后再试。"
                )

        if char.status == CharacterStatus.CAPTURED:
            allow = allowed_actions or cls.ALLOWED_CAPTURED_ACTIONS
            if act not in allow:
                raise CharacterBusyError(
                    f"【身陷囹圄】修士 {char.name} 当前处于被擒状态，无法自由行动！"
                )

    @classmethod
    def assert_currency(cls, char: Character, cost_stones: int) -> None:
        """核验修士随身灵石资财充足"""
        if cost_stones < 0:
            raise CharacterIntegrityError(f"消耗灵石数不可为负数: {cost_stones}")
        if char.spirit_stones < cost_stones:
            raise InsufficientCurrencyError(
                f"随身灵石不足（需 {cost_stones} 灵石，现存 {char.spirit_stones} 灵石）"
            )

    @classmethod
    def deduct_currency(cls, char: Character, cost_stones: int) -> None:
        """扣除修士随身灵石"""
        cls.assert_currency(char, cost_stones)
        char.spirit_stones -= cost_stones

    @classmethod
    def assert_bag_space(cls, char: Character, needed_slots: int = 1) -> None:
        """核验百宝纳戒容量充足"""
        if needed_slots <= 0:
            return
        current_count = len(char.items)
        if current_count + needed_slots > char.MAX_BAG_SLOTS:
            raise BagFullError(
                f"纳戒百宝囊已满（当前 {current_count}/{char.MAX_BAG_SLOTS} 格），"
                f"无法再容纳 {needed_slots} 件宝物，请先移挪旧物！"
            )

    @classmethod
    def audit_character(
        cls,
        char: Character,
        now: Optional[float] = None,
        auto_repair: bool = True,
    ) -> List[str]:
        """
        后置权威审查：核验 6 大道体不变式，自动纠偏并返回审计告警列表
        """
        t = now or time.time()
        warnings: List[str] = []

        # 1. 生死与寿元不变式
        rem = char.lifespan.get_remaining_years(t)
        if rem <= 0.0 and char.status != CharacterStatus.DEAD:
            if auto_repair:
                char.status = CharacterStatus.DEAD
                if not char.death_cause:
                    char.death_cause = "寿尽坐化"
            warnings.append(f"寿元已耗尽({rem:.2f}岁)，已修正道体状态为陨落(DEAD)")

        # 2. 境界与修为不变式
        if char.realm.tier < 0:
            if auto_repair:
                char.realm.tier = 0
            warnings.append("境界大阶下溢，已修正为凡人(tier=0)")
        if char.realm.sub_tier < 0 or char.realm.sub_tier > 3:
            if auto_repair:
                char.realm.sub_tier = max(0, min(3, char.realm.sub_tier))
            warnings.append("境界小阶越界，已钳位至[0, 3]")
        if char.realm.current_exp < 0:
            if auto_repair:
                char.realm.current_exp = 0
            warnings.append("当前修为值为负，已钳位归零")

        # 3. 资产非负不变式
        if char.spirit_stones < 0:
            if auto_repair:
                char.spirit_stones = 0
            warnings.append("随身灵石下溢变负，已重置归零")
        if char.vault_stones < 0:
            if auto_repair:
                char.vault_stones = 0
            warnings.append("洞府寄存灵石下溢变负，已重置归零")
        if char.stall_earnings < 0:
            if auto_repair:
                char.stall_earnings = 0
            warnings.append("坊市地摊收益下溢变负，已重置归零")

        # 4. 道心与业力不变式
        if char.karma.dao_heart < 0 or char.karma.dao_heart > 100:
            if auto_repair:
                char.karma.dao_heart = max(0, min(100, char.karma.dao_heart))
            warnings.append("道心数值异常，已钳位至[0, 100]")
        if char.karma.sin_value < 0:
            if auto_repair:
                char.karma.sin_value = 0
            warnings.append("业力值下溢变负，已重置归零")
        if char.karma.merit_value < 0:
            if auto_repair:
                char.karma.merit_value = 0
            warnings.append("功德值下溢变负，已重置归零")

        # 5. 纳戒容量与物品守恒不变式
        if len(char.items) > char.MAX_BAG_SLOTS:
            excess = len(char.items) - char.MAX_BAG_SLOTS
            if auto_repair:
                overflow_items = char.items[char.MAX_BAG_SLOTS:]
                char.items = char.items[:char.MAX_BAG_SLOTS]
                if char.crane_pending_item is None and overflow_items:
                    char.crane_pending_item = overflow_items[0].model_dump()
            warnings.append(f"纳戒百宝囊超格(溢出{excess}件)，已执行防爆仓裁剪保护")

        # 同步 inventory 列表与 items 实体名一致（保留 legacy 道具名）
        if auto_repair:
            item_names = [it.name for it in char.items]
            for x in char.inventory:
                if x not in item_names:
                    item_names.append(x)
            char.inventory = item_names

        # 6. 定势排他性不变式
        if char.status == CharacterStatus.DEAD and char.meditation.is_active:
            if auto_repair:
                char.meditation.is_active = False
            warnings.append("死者处于闭关态，已自动终止闭关会话")
        elif char.status == CharacterStatus.CAPTURED and char.meditation.is_active:
            if auto_repair:
                char.meditation.is_active = False
            warnings.append("被擒修士处于闭关态，已自动终止闭关会话")

        return warnings
