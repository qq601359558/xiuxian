"""
悬赏告示榜与因果复仇链
"""
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import (
    BOUNTY_MIN_REWARD,
    BOUNTY_MAX_REWARD,
    BOUNTY_FEE_RATE,
    BOUNTY_ANON_EXTRA_FEE,
    BOUNTY_ACTIVE_HOURS,
    BOUNTY_HUNTER_MERIT,
    BOUNTY_MAX_PER_TARGET,
    KARMA_LINK_TYPES,
)
from core.models import Character, CharacterStatus


class BountyStatus(str, Enum):
    OPEN = "OPEN"           # 待猎
    CLAIMED = "CLAIMED"     # 已被接令
    COMPLETED = "COMPLETED" # 已领赏
    EXPIRED = "EXPIRED"     # 过期未果
    CANCELLED = "CANCELLED" # 挂赏者撤回


BOUNTY_STATUS_CN = {
    BountyStatus.OPEN: "待猎",
    BountyStatus.CLAIMED: "已接令",
    BountyStatus.COMPLETED: "已领赏",
    BountyStatus.EXPIRED: "已过期",
    BountyStatus.CANCELLED: "已撤回",
}


def bounty_status_cn(status: Any) -> str:
    if isinstance(status, BountyStatus):
        return BOUNTY_STATUS_CN.get(status, status.value)
    try:
        return BOUNTY_STATUS_CN.get(BountyStatus(str(status)), str(status))
    except Exception:
        return str(status)


class Bounty(BaseModel):
    """悬赏令"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    issuer_id: str
    issuer_name: str
    issuer_anonymous: bool = False
    target_id: str
    target_name: str
    reward: int
    reason: str = "血海深仇"
    status: BountyStatus = BountyStatus.OPEN
    hunter_id: Optional[str] = None
    hunter_name: Optional[str] = None
    created_at: float = 0.0
    expires_at: float = 0.0
    completed_at: float = 0.0

    def is_active(self, now: Optional[float] = None) -> bool:
        t = now or time.time()
        return self.status in (BountyStatus.OPEN, BountyStatus.CLAIMED) and t < self.expires_at

    def issuer_display(self) -> str:
        return "匿名苦主" if self.issuer_anonymous else self.issuer_name


class KarmaLink(BaseModel):
    """修士间因果关系链"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    a_id: str
    a_name: str
    b_id: str
    b_name: str
    link_type: str  # 仇 / 恩 / 师徒 / 宗门
    strength: int = 1
    note: str = ""
    created_at: float = 0.0

    def involves(self, char_id: str) -> bool:
        return char_id in (self.a_id, self.b_id)

    def other_side(self, char_id: str) -> Tuple[str, str]:
        if char_id == self.a_id:
            return self.b_id, self.b_name
        return self.a_id, self.a_name


class BountyEngine:
    """悬赏裁决引擎（规则唯一权威，防骗赏/防双领）"""

    # ---------------- 挂赏 ----------------
    @staticmethod
    def place_bounty(
        issuer: Character,
        target: Character,
        reward: int,
        reason: str = "血海深仇",
        anonymous: bool = False,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        current_time = now or time.time()

        if issuer.id == target.id:
            return {"success": False, "message": "不可对自己下悬赏令，天道不容此等荒唐。"}

        if target.status == CharacterStatus.DEAD or target.lifespan.is_dead(current_time):
            return {"success": False, "message": f"【{target.name}】已身死道消，无需再挂悬赏。"}

        reward = int(reward)
        if reward < BOUNTY_MIN_REWARD:
            return {
                "success": False,
                "message": f"悬赏金至少 {BOUNTY_MIN_REWARD} 灵石，否则无人愿接。",
            }
        if reward > BOUNTY_MAX_REWARD:
            return {
                "success": False,
                "message": f"单笔悬赏至多 {BOUNTY_MAX_REWARD} 灵石，防坊市洗钱。",
            }

        fee_rate = BOUNTY_FEE_RATE + (BOUNTY_ANON_EXTRA_FEE if anonymous else 0.0)
        fee = max(1, int(reward * fee_rate))
        total_cost = reward + fee
        if issuer.spirit_stones < total_cost:
            return {
                "success": False,
                "message": (
                    f"挂赏需赏金 {reward} + 坊市抽成 {fee} = 共 {total_cost} 灵石，"
                    f"道友囊中仅有 {issuer.spirit_stones}。"
                ),
            }

        issuer.spirit_stones -= total_cost

        bounty = Bounty(
            issuer_id=issuer.id,
            issuer_name=issuer.name,
            issuer_anonymous=anonymous,
            target_id=target.id,
            target_name=target.name,
            reward=reward,
            reason=reason.strip() or "血海深仇",
            status=BountyStatus.OPEN,
            created_at=current_time,
            expires_at=current_time + BOUNTY_ACTIVE_HOURS * 3600.0,
        )

        # 因果链：仇
        link = KarmaLink(
            a_id=issuer.id,
            a_name=issuer.name,
            b_id=target.id,
            b_name=target.name,
            link_type="仇",
            strength=1,
            note=f"挂赏 {reward} 灵石：{bounty.reason}",
            created_at=current_time,
        )

        try:
            import core.jianghu as jianghu

            jianghu.append_event(
                kind="bounty",
                actor_ids=[issuer.id],
                actor_names=[bounty.issuer_display()],
                target_ids=[target.id],
                location=getattr(issuer, "location", ""),
                summary=f"【{bounty.issuer_display()}】悬赏 {reward} 灵石取【{target.name}】首级",
                rule_result={"reward": reward, "fee": fee, "anonymous": anonymous},
                narrative=bounty.reason,
                ref_ids=[issuer.id, target.id],
                source="rule",
            )
        except Exception:
            pass

        return {
            "success": True,
            "bounty": bounty,
            "link": link,
            "fee": fee,
            "total_cost": total_cost,
            "message": (
                f"【告示张榜】坊市告示栏新贴血红悬赏令！\n"
                f"· 目标：【{target.name}】\n"
                f"· 赏金：{reward} 灵石（挂赏抽成 {fee}）\n"
                f"· 缘由：{bounty.reason}\n"
                f"· 苦主：{bounty.issuer_display()}\n"
                f"· 有效期：现实 {BOUNTY_ACTIVE_HOURS:.0f} 小时\n"
                f"天下猎手皆可凭此令诛之领赏。"
            ),
        }

    # ---------------- 接令 ----------------
    @staticmethod
    def claim_bounty(
        hunter: Character,
        bounty: Bounty,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        current_time = now or time.time()

        if bounty.status != BountyStatus.OPEN:
            return {"success": False, "message": f"此悬赏已非待猎状态（{bounty.status.value}）。"}
        if current_time >= bounty.expires_at:
            bounty.status = BountyStatus.EXPIRED
            return {"success": False, "message": "悬赏令已过期，墨迹褪色，无人再认。"}
        if hunter.id == bounty.target_id:
            return {"success": False, "message": "不可接自己头上的悬赏。"}
        if hunter.id == bounty.issuer_id:
            return {"success": False, "message": "苦主不可亲自领自己的赏（防自导自演骗赏）。"}

        bounty.status = BountyStatus.CLAIMED
        bounty.hunter_id = hunter.id
        bounty.hunter_name = hunter.name
        try:
            import core.jianghu as jianghu

            jianghu.append_event(
                kind="bounty",
                actor_ids=[hunter.id],
                actor_names=[hunter.name],
                target_ids=[bounty.target_id],
                location=getattr(hunter, "location", ""),
                summary=f"【{hunter.name}】接下悬赏，追杀【{bounty.target_name}】",
                rule_result={"reward": bounty.reward, "action": "claim"},
                ref_ids=[hunter.id, bounty.target_id],
                source="rule",
            )
        except Exception:
            pass
        return {
            "success": True,
            "bounty": bounty,
            "message": (
                f"【接令猎凶】{hunter.name} 揭下告示，接令追杀【{bounty.target_name}】！\n"
                f"赏金 {bounty.reward} 灵石 · 苦主：{bounty.issuer_display()}\n"
                f"凶徒若血煞在身，诛之另有功德。"
            ),
        }

    # ---------------- 击杀后自动结赏 ----------------
    @staticmethod
    def settle_on_kill(
        killer: Character,
        victim: Character,
        bounties: List[Bounty],
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        击杀成立后结算所有指向 victim 的有效悬赏。
        - 仅 OPEN/CLAIMED 且未过期
        - 赏金全部归 killer（防双领：结算后置 COMPLETED）
        - 凶人（血煞/高业力）额外功德
        """
        current_time = now or time.time()
        paid: List[Bounty] = []
        total_reward = 0
        already_done: List[Bounty] = []

        for b in bounties:
            if b.target_id != victim.id:
                continue
            if b.status == BountyStatus.COMPLETED:
                continue
            if not b.is_active(current_time):
                if current_time >= b.expires_at and b.status in (BountyStatus.OPEN, BountyStatus.CLAIMED):
                    b.status = BountyStatus.EXPIRED
                continue

            # 接令校验：若已被他人接令，仍允许「路过斩杀」领赏（鼓励除凶）
            # 但若接令人不是 killer，接令人不能拿（防抢功争议简化：谁杀谁领）
            b.status = BountyStatus.COMPLETED
            b.completed_at = current_time
            if not b.hunter_id:
                b.hunter_id = killer.id
                b.hunter_name = killer.name
            paid.append(b)
            total_reward += b.reward

        if not paid:
            # 无有效悬赏：若对方是凶人，仍给一点除凶功德（与 combat 逻辑互补）
            extra_merit = 0
            if victim.karma.is_blood_marked(current_time) or victim.karma.sin_value >= 100:
                extra_merit = BOUNTY_HUNTER_MERIT
                killer.karma.add_merit(extra_merit)
            return {
                "success": True,
                "bounty_paid": False,
                "total_reward": 0,
                "completed": [],
                "extra_merit": extra_merit,
                "message": "",
            }

        killer.spirit_stones += total_reward
        merit = BOUNTY_HUNTER_MERIT * len(paid)
        if victim.karma.is_blood_marked(current_time):
            merit += BOUNTY_HUNTER_MERIT
        killer.karma.add_merit(merit)

        names = "、".join(b.issuer_display() for b in paid)
        return {
            "success": True,
            "bounty_paid": True,
            "total_reward": total_reward,
            "completed": paid,
            "extra_merit": merit,
            "message": (
                f"【告示销案 · 领赏】{killer.name} 诛杀【{victim.name}】，"
                f"坊市验明正身后发放赏金共 {total_reward} 灵石！\n"
                f"· 苦主：{names}\n"
                f"· 除凶功德 +{merit}"
            ),
        }

    # ---------------- 告示榜 ----------------
    @staticmethod
    def list_board(
        bounties: List[Bounty],
        now: Optional[float] = None,
        include_finished: bool = False,
    ) -> List[Bounty]:
        current_time = now or time.time()
        out = []
        for b in bounties:
            if b.expires_at and current_time >= b.expires_at and b.status in (
                BountyStatus.OPEN, BountyStatus.CLAIMED
            ):
                b.status = BountyStatus.EXPIRED
            if include_finished or b.status in (BountyStatus.OPEN, BountyStatus.CLAIMED):
                out.append(b)
        # 高赏金在前
        out.sort(key=lambda x: (-x.reward, x.created_at))
        return out

    @staticmethod
    def count_active_for_target(
        bounties: List[Bounty],
        target_id: str,
        now: Optional[float] = None,
    ) -> int:
        current_time = now or time.time()
        return sum(1 for b in bounties if b.target_id == target_id and b.is_active(current_time))

    # ---------------- 因果链 ----------------
    @staticmethod
    def ensure_feud_link(
        links: List[KarmaLink],
        a: Character,
        b: Character,
        note: str = "",
        now: Optional[float] = None,
    ) -> Optional[KarmaLink]:
        """确保 A 与 B 之间存在「仇」链；已有则加强，不重复建。"""
        current_time = now or time.time()
        for link in links:
            if link.link_type == "仇" and link.involves(a.id) and link.involves(b.id):
                link.strength += 1
                if note:
                    link.note = f"{link.note}；{note}" if link.note else note
                return link
        link = KarmaLink(
            a_id=a.id,
            a_name=a.name,
            b_id=b.id,
            b_name=b.name,
            link_type="仇",
            strength=1,
            note=note or f"{a.name} 与 {b.name} 结下血仇",
            created_at=current_time,
        )
        links.append(link)
        return link

    @staticmethod
    def list_links_for(links: List[KarmaLink], char_id: str) -> List[KarmaLink]:
        return [l for l in links if l.involves(char_id)]
