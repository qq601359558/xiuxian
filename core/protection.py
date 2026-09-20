"""
离线庇护与逃遁失败结算（OQ1 三护栏③④）

规则：
1. 主动「闭关归隐」：须已脱战且身处非冲突区（is_safe=True 或非野外凶域）。
2. 斗法中直接下线 → 逃遁失败：可被夺随身财货，记仓皇败走，短暂冷却。
3. 冲突区（is_safe=False）非斗法即时下线 → 仓皇遁走：遗财折损，不伤性命。
4. 庇护中：不可被攻击；随身财货不可交易/转移/寄存（防下线保险库）。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional

from config import (
    WORLD_LOCATIONS,
    OFFLINE_PROTECT_MAX_HOURS,
    FLEE_STONES_LOSS_MIN,
    FLEE_STONES_LOSS_MAX,
    COMBAT_LOGOUT_LOOT_MIN,
    COMBAT_LOGOUT_LOOT_MAX,
    FLEE_COOLDOWN_SECONDS,
)
from core.models import Character, CharacterStatus


def is_conflict_zone(location: str) -> bool:
    """冲突区：无安全大阵的野外/凶域"""
    loc = WORLD_LOCATIONS.get(location, {})
    return not loc.get("is_safe", False)


def protection_active(c: Character, now: Optional[float] = None) -> bool:
    """是否处于离线/归隐庇护（不含新手期）"""
    t = now if now is not None else time.time()
    return c.offline_protected_until > t


def is_fully_protected(c: Character, now: Optional[float] = None) -> bool:
    """新手期 或 离线归隐庇护"""
    t = now if now is not None else time.time()
    return c.is_newbie_protected(t) or protection_active(c, t)


class ProtectionEngine:
    """庇护与下线裁决"""

    @staticmethod
    def enter_reclusion(
        c: Character,
        hours: float = OFFLINE_PROTECT_MAX_HOURS,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """主动闭关归隐：脱战 + 非冲突区"""
        t = now if now is not None else time.time()

        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，何须归隐。"}

        if c.status == CharacterStatus.IN_FIGHT:
            return {
                "success": False,
                "message": "【不可归隐】正在斗法搏杀，须先脱战（或胜负已分）方可遁入红尘之外。",
            }

        if c.flee_cooldown_until > t:
            left = int(c.flee_cooldown_until - t)
            return {
                "success": False,
                "message": f"【遁迹未稳】方才仓皇遁走，心神未定，还需 {left} 秒方可归隐。",
            }

        if is_conflict_zone(c.location):
            return {
                "success": False,
                "message": (
                    f"【此地凶险】身处冲突区【{c.location}】，无安全大阵庇护，"
                    f"不可归隐。请先 /前往 坊市或宗门驻地。"
                ),
            }

        if c.status == CharacterStatus.MEDITATING:
            return {
                "success": False,
                "message": "已在闭关洞府之中，闭关即离线托管，无需重复归隐。",
            }

        hours = max(0.5, min(float(hours), OFFLINE_PROTECT_MAX_HOURS))
        c.offline_protected_until = t + hours * 3600.0
        c.reclusion_active = True
        return {
            "success": True,
            "hours": hours,
            "until": c.offline_protected_until,
            "message": (
                f"【闭关归隐】于【{c.location}】结庐谢客，遁出红尘。\n"
                f"· 庇护约 {hours:.1f} 现实小时：不可被攻击，随身财货不可转移。\n"
                f"· 此间可安心下线；归来输入 /出隐 即可再入尘世。"
            ),
        }

    @staticmethod
    def exit_reclusion(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if not protection_active(c, t) and not c.reclusion_active:
            return {"success": False, "message": "道友本就不在归隐之中。"}
        c.offline_protected_until = 0.0
        c.reclusion_active = False
        return {
            "success": True,
            "message": f"【出隐入世】{c.name} 自【{c.location}】再踏仙途，庇护解除。",
        }

    @staticmethod
    def mark_combat(c: Character, now: Optional[float] = None) -> None:
        """进入斗法：标记脱战前不可归隐"""
        t = now if now is not None else time.time()
        c.last_combat_at = t
        c.combat_lock_until = t + 30.0  # 30 秒脱战窗口
        if c.status != CharacterStatus.DEAD and c.status != CharacterStatus.MEDITATING:
            c.status = CharacterStatus.IN_FIGHT

    @staticmethod
    def clear_combat(c: Character) -> None:
        if c.status == CharacterStatus.IN_FIGHT:
            c.status = CharacterStatus.IDLE
        c.combat_lock_until = 0.0

    @staticmethod
    def in_combat(c: Character, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.time()
        return c.status == CharacterStatus.IN_FIGHT or c.combat_lock_until > t

    @staticmethod
    def can_be_attacked(c: Character, now: Optional[float] = None) -> tuple[bool, str]:
        """返回 (可否攻击, 原因)"""
        t = now if now is not None else time.time()
        if c.status == CharacterStatus.DEAD:
            return False, "对方已坐化陨落。"
        if c.is_newbie_protected(t):
            return False, f"【天道庇护·新手】{c.name} 尚在新手庇护期内，不可被攻击。"
        if protection_active(c, t):
            return False, f"【天道庇护·归隐】{c.name} 已闭关归隐，神游物外，不可被攻击。"
        if c.status == CharacterStatus.MEDITATING:
            # 闭关可被伏击（野外裸露），安全区不可——由战斗引擎再判地点
            pass
        return True, ""

    @staticmethod
    def can_transfer_assets(c: Character, now: Optional[float] = None) -> tuple[bool, str]:
        """归隐/离线庇护中禁止寄存/转移随身财货（新手期可正常交易）"""
        t = now if now is not None else time.time()
        if protection_active(c, t):
            return False, (
                "【庇护锁财】归隐/离线庇护期间随身财货不可转移或寄存，"
                "请先 /出隐 并身处安全时再操作。"
            )
        return True, ""

    @staticmethod
    def settle_logout(
        c: Character,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        会话结束/显式下线结算。
        - 斗法中 → 逃遁失败（可被夺随身）
        - 冲突区 → 仓皇遁走（遗财折损）
        - 其他 → 自动进入归隐庇护
        """
        t = now if now is not None else time.time()

        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return {
                "ok": True,
                "kind": "dead",
                "message": "身已陨落，真灵待转世。",
            }

        # 已在闭关：托管继续，同时若在安全区可叠加庇护
        if c.status == CharacterStatus.MEDITATING:
            loc = WORLD_LOCATIONS.get(c.location, {"is_safe": True})
            if loc.get("is_safe", False):
                c.offline_protected_until = max(
                    c.offline_protected_until,
                    t + min(OFFLINE_PROTECT_MAX_HOURS, c.meditation.hours_planned or 24) * 3600.0,
                )
                c.reclusion_active = True
            return {
                "ok": True,
                "kind": "meditate_offline",
                "message": (
                    f"闭关托管继续；"
                    + ("安全洞府已入庇护。" if loc.get("is_safe") else "野外裸露闭关，阵外有险。")
                ),
            }

        # 1) 斗法中下线 → 逃遁失败
        if ProtectionEngine.in_combat(c, t):
            loot_pct = random.uniform(COMBAT_LOGOUT_LOOT_MIN, COMBAT_LOGOUT_LOOT_MAX)
            lost = int(c.spirit_stones * loot_pct)
            c.spirit_stones = max(0, c.spirit_stones - lost)
            # 无指定对手时，灵石散落天地（规则引擎吞没，防刷）
            ProtectionEngine.clear_combat(c)
            c.flee_cooldown_until = t + FLEE_COOLDOWN_SECONDS
            c.death_cause = None
            return {
                "ok": True,
                "kind": "combat_flee_fail",
                "lost_stones": lost,
                "message": (
                    f"【逃遁失败】斗法中强行离线，天道判定遁光溃散，"
                    f"随身灵石折损 {lost} 块。短时内不可归隐。"
                ),
            }

        # 2) 冲突区即时下线 → 仓皇遁走
        if is_conflict_zone(c.location):
            pct = random.uniform(FLEE_STONES_LOSS_MIN, FLEE_STONES_LOSS_MAX)
            lost = int(c.spirit_stones * pct)
            c.spirit_stones = max(0, c.spirit_stones - lost)
            c.flee_cooldown_until = t + FLEE_COOLDOWN_SECONDS
            return {
                "ok": True,
                "kind": "panic_flee",
                "lost_stones": lost,
                "message": (
                    f"【仓皇遁走】身处冲突区【{c.location}】匆忙离线，"
                    f"行囊散乱，遗失灵石 {lost} 块（性命无碍）。"
                ),
            }

        # 3) 常规下线 → 归隐庇护
        c.offline_protected_until = t + OFFLINE_PROTECT_MAX_HOURS * 3600.0
        c.reclusion_active = True
        return {
            "ok": True,
            "kind": "reclusion",
            "message": (
                f"【离线归隐】{c.name} 于【{c.location}】暂别红尘，"
                f"进入庇护（最长 {OFFLINE_PROTECT_MAX_HOURS:.0f}h）。"
            ),
        }

    @staticmethod
    def status_text(c: Character, now: Optional[float] = None) -> str:
        t = now if now is not None else time.time()
        if c.is_newbie_protected(t):
            left = max(0.0, c.newbie_protect_until() - t) / 3600.0
            return f"新手庇护 {left:.1f}h"
        if protection_active(c, t):
            left = max(0.0, c.offline_protected_until - t) / 3600.0
            return f"归隐庇护 {left:.1f}h"
        return ""
