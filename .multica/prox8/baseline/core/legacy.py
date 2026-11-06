"""
转世与道统点：一世结算、元进度账本、降生加成
"""
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import (
    LEGACY_BASE_POINTS,
    LEGACY_PER_TIER,
    LEGACY_MERIT_DIVISOR,
    LEGACY_SIN_DIVISOR,
    LEGACY_SIN_PENALTY_MAX,
    LEGACY_MAX_PER_LIFE,
    LEGACY_SUICIDE_WINDOW_SECONDS,
    LEGACY_SUICIDE_THRESHOLD,
    LEGACY_SUICIDE_PENALTY,
    LEGACY_MAX_BOOSTS_PER_LIFE,
    LEGACY_BOOSTS,
    SECONDS_PER_GAME_YEAR,
)
from core.models import Character, CharacterStatus, RootType


class PastLife(BaseModel):
    """前世档案摘要"""
    name: str
    realm: str
    cause: str
    lifespan_lived: float  # 约活了多少岁
    sin: int = 0
    merit: int = 0
    points_gained: int = 0
    died_at: float = 0.0


class LegacyAccount(BaseModel):
    """账号级元进度（跨一世保留）"""
    user_id: str
    points: int = 0
    total_lives: int = 0
    total_points_earned: int = 0
    death_times: List[float] = Field(default_factory=list)
    past_lives: List[PastLife] = Field(default_factory=list)


class LegacyEngine:
    """道统传承裁决引擎"""

    @staticmethod
    def compute_points(character: Character) -> Dict[str, Any]:
        """按本世成就估算可结转的道统点（未计自杀惩罚）"""
        tier = character.realm.tier
        sin = character.karma.sin_value
        merit = character.karma.merit_value

        base = LEGACY_BASE_POINTS
        tier_pts = tier * LEGACY_PER_TIER
        merit_pts = merit // LEGACY_MERIT_DIVISOR
        sin_penalty = min(LEGACY_SIN_PENALTY_MAX, sin // LEGACY_SIN_DIVISOR)

        raw = max(0, base + tier_pts + merit_pts - sin_penalty)
        capped = min(LEGACY_MAX_PER_LIFE, raw)
        return {
            "base": base,
            "tier_points": tier_pts,
            "merit_points": merit_pts,
            "sin_penalty": sin_penalty,
            "raw": raw,
            "capped": capped,
        }

    @staticmethod
    def _recent_death_count(account: LegacyAccount, now: float) -> int:
        window_start = now - LEGACY_SUICIDE_WINDOW_SECONDS
        return sum(1 for t in account.death_times if t >= window_start)

    @staticmethod
    def settle_death(
        account: LegacyAccount,
        character: Character,
        death_cause: str = "身死道消",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        本世终结：归档前世、结算道统点并入账。
        必须只调用一次（由 CLI 死亡流程保证）。
        """
        current_time = now or time.time()

        # 若角色尚未标 DEAD，补标
        if character.status != CharacterStatus.DEAD:
            character.status = CharacterStatus.DEAD
        if character.death_cause is None:
            character.death_cause = death_cause
        character.death_settled = True

        breakdown = LegacyEngine.compute_points(character)
        raw_pts = breakdown["capped"]

        recent = LegacyEngine._recent_death_count(account, current_time)
        penalty_applied = recent >= LEGACY_SUICIDE_THRESHOLD
        gained = int(raw_pts * LEGACY_SUICIDE_PENALTY) if penalty_applied else raw_pts

        # 约活了多少岁：出生基数 + 突破增寿（近似本世寿元消耗）
        lived = character.lifespan.birth_base + character.lifespan.accumulated_gain

        past = PastLife(
            name=character.name,
            realm=character.realm.name,
            cause=death_cause,
            lifespan_lived=round(lived, 1),
            sin=character.karma.sin_value,
            merit=character.karma.merit_value,
            points_gained=gained,
            died_at=current_time,
        )

        account.points += gained
        account.total_points_earned += gained
        account.total_lives += 1
        account.death_times.append(current_time)
        # 只保留最近 20 次死亡时间戳
        account.death_times = account.death_times[-20:]
        account.past_lives.append(past)
        account.past_lives = account.past_lives[-10:]

        return {
            "success": True,
            "points_gained": gained,
            "points_raw": raw_pts,
            "penalty_applied": penalty_applied,
            "recent_deaths": recent + 1,
            "breakdown": breakdown,
            "past_life": past,
            "account_points": account.points,
            "total_lives": account.total_lives,
            "cause": death_cause,
        }

    @staticmethod
    def check_reincarnate_gate(
        account: LegacyAccount,
        now: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        是否允许立刻转世。
        仅「连续极速送死」时短暂锁转世，避免自杀刷点后马上再死。
        """
        current_time = now or time.time()
        recent = LegacyEngine._recent_death_count(account, current_time)
        if recent >= LEGACY_SUICIDE_THRESHOLD + 2:
            oldest_in_window = min(
                t for t in account.death_times
                if t >= current_time - LEGACY_SUICIDE_WINDOW_SECONDS
            )
            wait = int(LEGACY_SUICIDE_WINDOW_SECONDS - (current_time - oldest_in_window))
            wait = max(1, wait)
            return False, (
                f"真灵连遭重创，短时间内陨落过多（{recent} 次），需静养 {wait} 秒"
                f"待神魂稳固后方可再入轮回。"
            )
        return True, ""

    @staticmethod
    def list_boosts() -> List[Dict[str, Any]]:
        out = []
        for key, cfg in LEGACY_BOOSTS.items():
            out.append({
                "key": key,
                "name": cfg["name"],
                "cost": cfg["cost"],
                "desc": cfg["desc"],
            })
        return out

    @staticmethod
    def apply_birth_boosts(
        character: Character,
        account: LegacyAccount,
        boost_keys: List[str],
    ) -> Dict[str, Any]:
        """
        转世降生时消费道统点，为新角色附加轻量出身优势。
        :param boost_keys: 如 ["stones", "lifespan"]
        """
        applied: List[str] = []
        errors: List[str] = []
        spent = 0

        # 去重且限量
        unique_keys: List[str] = []
        for k in boost_keys:
            if k not in unique_keys:
                unique_keys.append(k)

        if len(unique_keys) > LEGACY_MAX_BOOSTS_PER_LIFE:
            return {
                "success": False,
                "message": (
                    f"单次转世至多选择 {LEGACY_MAX_BOOSTS_PER_LIFE} 项出身加成，"
                    f"天道不容贪求。"
                ),
            }

        for key in unique_keys:
            cfg = LEGACY_BOOSTS.get(key)
            if not cfg:
                errors.append(f"未知道统传承：{key}")
                continue
            cost = cfg["cost"]
            if account.points < cost:
                errors.append(f"道统点不足，无法兑换【{cfg['name']}】（需 {cost}）")
                continue

            # 应用效果
            if key == "stones":
                character.spirit_stones += 150
            elif key == "lifespan":
                character.lifespan.add_lifespan(8.0)
            elif key == "root":
                new_eff = min(2.5, character.spiritual_root.efficiency + 0.25)
                character.spiritual_root.efficiency = new_eff
            elif key == "skill":
                extras = ["御风诀", "龟息敛气术", "小周天引气法", "血遁残篇"]
                for sk in extras:
                    if sk not in character.skills:
                        character.skills.append(sk)
                        break

            account.points -= cost
            spent += cost
            applied.append(cfg["name"])

        return {
            "success": len(applied) > 0 or (not boost_keys),
            "applied": applied,
            "spent": spent,
            "errors": errors,
            "remaining_points": account.points,
            "message": (
                f"道统点化：已继承【{'、'.join(applied)}】，消耗 {spent} 点。"
                if applied
                else "本世未兑换任何道统传承。"
            ) + (("；" + "；".join(errors)) if errors else ""),
        }

    @staticmethod
    def default_account(user_id: str) -> LegacyAccount:
        return LegacyAccount(user_id=user_id)
