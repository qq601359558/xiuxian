"""
诺言账闭环（F14）：/许诺 立诺 → 既有事实核验 → 因果账结算。

设计口径（docs/compose/spec/promises.md）：
- 诺言类型/核验/结算 100% 规则模板；交谈文本（哪怕 AI 说「我答应你」）不产生诺言，
  唯 /许诺 指令立诺、/应诺 应下，天道方认。
- 核验只认既有事实，钩子挂在四个既有落账点：会话赠礼（chat_actions.do_gift）、
  迁跃落点（server _go / cli /前往）、委托整链完成（quests.deliver 完成段）、
  斗法出手（combat_fate.resolve_ambush 硬前置全过后）。钩子全程 try/except 包裹，
  异常不炸主流程（与 F09 版图钩子同例）。
- 落账只走既有口径：功德/业力走 Character.karma.add_merit/add_sin（唯一账本，
  禁止第二套数）；NPC 态度走 npc_mind.shift_attitude；因果留痕写 karma_links
  （link_type=「诺」）；违约入 jianghu 世情播报。
- 结算结构性幂等：_settle 是唯一写终态入口，先落终态存库（锚）再发效果；
  终态不可逆，重复触发短路。
- 玩家对象须 /应诺 才成立（PENDING→ACTIVE，期限自应诺起算），防单方面陷阱诺；
  NPC 对象当面立诺即 ACTIVE。
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config import WORLD_LOCATIONS
from core.models import Character, CharacterStatus

# ---------------- 常量（规则单点，见 spec §2） ----------------
PROMISE_MAX_OPEN = 3                    # 一人同时未结诺上限（PENDING+ACTIVE）
PROMISE_ACCEPT_TTL_SECONDS = 86400.0    # 待应诺有效期：现实 24 小时
PROMISE_MERIT_KEPT = 10                 # 履约功德（≤ EVENT_EFFECT_CAPS merit 40）
PROMISE_SIN_BROKEN = 15                 # 违约业力（≤ EVENT_EFFECT_CAPS sin 40）
PROMISE_ATTITUDE_DELTA = 8              # NPC 对象履约 +8 / 违约 -8（F07 态度口径）
PROMISE_HISTORY_N = 5                   # 面板近史条数

# kind → (中文名, 期限秒)；期限为现实秒（与委托 TTL 86400 同口径），文案称「日」
PROMISE_KINDS: Dict[str, Dict[str, Any]] = {
    "gift": {"cn": "赠物", "ttl": 3 * 86400.0},
    "arrive": {"cn": "抵达", "ttl": 3 * 86400.0},
    "quest": {"cn": "委托", "ttl": 3 * 86400.0},
    "no_attack": {"cn": "不攻", "ttl": 7 * 86400.0},
    # 游戏感第一期（§3.5）：出身旧债。ttl 仅作面板文案/兜底；生成器直写
    # deadline = generated_at + 10 游戏日（SECONDS_PER_GAME_DAY 口径）。
    "debt": {"cn": "旧债", "ttl": 10 * 86400.0},
}
PROMISE_KIND_ALIASES = {
    "赠物": "gift", "gift": "gift",
    "抵达": "arrive", "到达": "arrive", "arrive": "arrive",
    "委托": "quest", "quest": "quest",
    "不攻": "no_attack", "不战": "no_attack", "no_attack": "no_attack", "noattack": "no_attack",
    "旧债": "debt", "debt": "debt",
}

TERMINAL_STATUSES = ("KEPT", "BROKEN", "DISSOLVED")


class PromiseStatus(str, Enum):
    PENDING = "PENDING"        # 待应诺（仅玩家对象）
    ACTIVE = "ACTIVE"          # 进行中
    KEPT = "KEPT"              # 已践诺（终态）
    BROKEN = "BROKEN"          # 已违约（终态）
    DISSOLVED = "DISSOLVED"    # 已消散（终态：未成/撤回/任一方身死）


class Promise(BaseModel):
    """一诺之账：立诺者对受诺人的一条规则诺言"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    promiser_id: str
    promiser_name: str
    promisee_id: str
    promisee_name: str
    promisee_is_npc: bool = False
    kind: str = "quest"         # gift/arrive/quest/no_attack
    param: str = ""             # gift=物品名 / arrive=地点全名 / 其余空
    desc: str = ""
    status: PromiseStatus = PromiseStatus.PENDING
    created_at: float = 0.0
    activated_at: float = 0.0
    deadline: float = 0.0       # PENDING 时为 0，应诺后写入
    settled_at: float = 0.0
    settle_note: str = ""
    paid: int = 0               # 旧债已还累计（仅 debt 类使用，旧档默认 0）


def _is_npc(c: Character) -> bool:
    return str(c.user_id).startswith("npc_") or str(c.user_id).startswith("ai_npc_")


def _alive(c: Optional[Character], now: float) -> bool:
    return bool(c) and c.status != CharacterStatus.DEAD and not c.lifespan.is_dead(now)


def _fmt_left(seconds: float) -> str:
    if seconds <= 0:
        return "已到期"
    if seconds >= 86400:
        return f"约 {seconds / 86400.0:.1f} 日"
    if seconds >= 3600:
        return f"约 {seconds / 3600.0:.1f} 小时"
    return f"约 {max(1, int(seconds // 60))} 分钟"


def describe_promise(kind: str, param: str, promisee_name: str) -> str:
    days = int(PROMISE_KINDS[kind]["ttl"] // 86400)
    if kind == "gift":
        return f"{days} 日内赠【{promisee_name}】【{param}】"
    if kind == "arrive":
        return f"{days} 日内抵达【{param}】（【{promisee_name}】见证）"
    if kind == "quest":
        return f"{days} 日内办成一单连环委托（【{promisee_name}】见证）"
    if kind == "debt":
        return f"旧债：欠【{promisee_name}】{param} 灵石（出身）"
    return f"{days} 日不向【{promisee_name}】出手"


class PromiseEngine:
    """诺言裁决引擎（规则唯一权威）"""

    # ---------------- 仓储（惰性导入，避开 storage.db ↔ core 循环） ----------------
    @staticmethod
    def _repo():
        from storage.db import PromiseRepository

        return PromiseRepository

    @staticmethod
    def _open_of(promiser_id: str) -> List[Promise]:
        return [
            p for p in PromiseEngine._repo().list_all()
            if p.promiser_id == promiser_id and p.status.value not in TERMINAL_STATUSES
        ]

    @staticmethod
    def _involving(char_id: str) -> List[Promise]:
        return [
            p for p in PromiseEngine._repo().list_all()
            if char_id in (p.promiser_id, p.promisee_id)
        ]

    # ---------------- 立诺 ----------------
    @staticmethod
    def make_promise(
        promiser: Character,
        promisee: Character,
        kind: str,
        param: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        param = (param or "").strip()
        if not _alive(promiser, t):
            return {"success": False, "message": "身死道消，诺随旧世而散，无从立诺。"}
        # 先惰性推进：过期/消散的旧诺先落终态，不长期占用上限与去重名额（评审 S3）；
        # settle_due 若对立诺者活对象落了账，dirty 透传给调用方回存
        dirty0 = PromiseEngine.settle_due(promiser, t, actor_obj=promiser)
        if promisee is None or promisee.id == promiser.id:
            return {"success": False, "dirty": dirty0, "message": "不可向自己立诺——天道只记对他人之诺。"}
        if not _alive(promisee, t):
            return {"success": False, "dirty": dirty0, "message": f"【{promisee.name}】已身死道消，无从受诺。"}
        if promisee.location != promiser.location:
            return {
                "success": False, "dirty": dirty0,
                "message": (
                    f"立诺须当面：【{promisee.name}】此刻在【{promisee.location}】，"
                    f"你身在【{promiser.location}】。先 /go 过去再立。"
                ),
            }
        if kind not in PROMISE_KINDS:
            return {"success": False, "dirty": dirty0, "message": "诺目须是规则四类之一：赠物 / 抵达 / 委托 / 不攻（自由口诺天道不记）。"}
        promisee_is_npc = _is_npc(promisee)
        if kind == "gift":
            if not promisee_is_npc:
                return {
                    "success": False, "dirty": dirty0,
                    "message": "赠物之诺只可对同场 NPC 立：玩家间财货往来走 /交易，并无纯赠予之实可核；对玩家可立 抵达 / 委托 / 不攻 之诺。",
                }
            if not param:
                return {"success": False, "dirty": dirty0, "message": "用法：/许诺 <NPC名> 赠物 <物品名>（物品可先立诺后寻，期限内经交谈赠出即践诺）。"}
            # 诺面以物品全名为准（评审 S2）：行囊已有含参物品时规范为全名，
            # 免得简称立诺、赠礼模糊命中全名后核验对不上而误判违约
            for it in promiser.inventory:
                if param in it:
                    param = it
                    break
        elif kind == "arrive":
            matched = None
            for loc in WORLD_LOCATIONS:
                if param and param in loc:
                    matched = loc
                    break
            if not matched:
                return {"success": False, "message": f"未知地点：{param}（/地图 查全界灵脉）"}
            if matched == promiser.location:
                return {"success": False, "message": f"你已身在【{matched}】，此诺无从践行；先离此地再立抵达之诺。"}
            param = matched
        open_list = PromiseEngine._open_of(promiser.id)
        if len(open_list) >= PROMISE_MAX_OPEN:
            return {
                "success": False, "dirty": dirty0,
                "message": f"诺不可多立：你已有 {len(open_list)} 条未结之诺（上限 {PROMISE_MAX_OPEN}），先了结再立新诺。",
            }
        for p in open_list:
            if p.promisee_id == promisee.id and p.kind == kind:
                return {
                    "success": False, "dirty": dirty0,
                    "message": f"你已对【{promisee.name}】立有同类未结之诺（{p.desc}），不可叠诺。",
                }
        desc = describe_promise(kind, param, promisee.name)
        promise = Promise(
            promiser_id=promiser.id,
            promiser_name=promiser.name,
            promisee_id=promisee.id,
            promisee_name=promisee.name,
            promisee_is_npc=promisee_is_npc,
            kind=kind,
            param=param,
            desc=desc,
            created_at=t,
        )
        if promisee_is_npc:
            promise.status = PromiseStatus.ACTIVE
            promise.activated_at = t
            promise.deadline = t + float(PROMISE_KINDS[kind]["ttl"])
            msg = (
                f"【立诺】你当【{promisee.name}】之面立诺：{desc}。\n"
                f"天道已记账，{_fmt_left(promise.deadline - t)}内践诺得功德 +{PROMISE_MERIT_KEPT}，"
                f"逾期违约沾业力 +{PROMISE_SIN_BROKEN} 并昭告世情。（/诺言 查看）"
            )
            if kind == "gift":
                msg += f"\n（诺物以全名为准：【{param}】；经交谈赠出全名同字之物方算践诺。）"
        else:
            promise.status = PromiseStatus.PENDING
            msg = (
                f"【立诺 · 待应诺】你向【{promisee.name}】立诺：{desc}。\n"
                f"须待对方 /应诺 之后此诺方生效（期限自应诺起算）；逾一日不应则诺未成、自动消散。"
                f"践诺功德 +{PROMISE_MERIT_KEPT}，违约业力 +{PROMISE_SIN_BROKEN}。"
            )
        PromiseEngine._repo().save(promise)
        return {"success": True, "message": msg, "promise": promise}

    # ---------------- 应诺 ----------------
    @staticmethod
    def accept(promisee: Character, promiser_hint: str = "", now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if not _alive(promisee, t):
            return {"success": False, "message": "身死道消，无从应诺。"}
        dirty = PromiseEngine.settle_due(promisee, t, actor_obj=promisee)
        hint = (promiser_hint or "").strip()
        pendings = [
            p for p in PromiseEngine._repo().list_all()
            if p.promisee_id == promisee.id and p.status == PromiseStatus.PENDING
            and (not hint or hint in p.promiser_name)
        ]
        if not pendings:
            return {
                "success": False, "dirty": dirty,
                "message": "眼下无人向你立下待应之诺。（立诺者以 /许诺 向你立诺后，你再 /应诺）",
            }
        if len(pendings) > 1:
            names = "、".join(sorted({p.promiser_name for p in pendings}))
            return {
                "success": False, "dirty": dirty,
                "message": f"有 {len(pendings)} 条待应之诺（立诺者：{names}），请指明：/应诺 <立诺者名>。",
            }
        p = pendings[0]
        p.status = PromiseStatus.ACTIVE
        p.activated_at = t
        p.deadline = t + float(PROMISE_KINDS[p.kind]["ttl"])
        PromiseEngine._repo().save(p)
        return {
            "success": True, "dirty": True,
            "message": (
                f"【应诺】你应下了【{p.promiser_name}】之诺：{p.desc}。\n"
                f"诺期自此刻起算（{_fmt_left(p.deadline - t)}）；义务只在立诺者一身，你无所担。"
            ),
            "promise": p,
        }

    # ---------------- 毁诺 / 撤诺 ----------------
    @staticmethod
    def break_promise(promiser: Character, promisee_hint: str = "", now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if not _alive(promiser, t):
            return {"success": False, "message": "身死道消，诺已随旧世而散，无需再毁。"}
        dirty = PromiseEngine.settle_due(promiser, t, actor_obj=promiser)
        hint = (promisee_hint or "").strip()
        opens = [
            p for p in PromiseEngine._open_of(promiser.id)
            if not hint or hint in p.promisee_name
        ]
        if not opens:
            return {"success": False, "dirty": dirty, "message": "你眼下并无未结之诺可毁。"}
        if len(opens) > 1:
            names = "、".join(sorted({p.promisee_name for p in opens}))
            return {
                "success": False, "dirty": dirty,
                "message": f"你有 {len(opens)} 条未结之诺（受诺人：{names}），请指明：/毁诺 <受诺人名>。",
            }
        p = opens[0]
        if p.status == PromiseStatus.PENDING:
            PromiseEngine._settle(p, PromiseStatus.DISSOLVED, "立诺者于应诺前撤回，诺未成", t, promiser_obj=promiser)
            return {
                "success": True, "dirty": True,
                "message": f"【撤诺】待应之诺（{p.desc}）已撤回——诺未成，无功无过。",
            }
        PromiseEngine._settle(p, PromiseStatus.BROKEN, "立诺者主动毁诺（与逾期违约同罪）", t, promiser_obj=promiser)
        return {
            "success": True, "dirty": True,
            "message": (
                f"【毁诺】你亲口毁弃前诺：{p.desc}。\n"
                f"天道按违约记账：业力 +{PROMISE_SIN_BROKEN}，并昭告世情。"
            ),
        }

    # ---------------- 惰性推进 ----------------
    @staticmethod
    def settle_due(char: Character, now: Optional[float] = None, actor_obj: Optional[Character] = None) -> bool:
        """惰性核验所有涉及 char 的未结诺（到期/消散）；返回是否有变更。

        actor_obj：调用方手中的 char 活对象（通常就是 char 本人），效果落账优先用它，
        防调用方随后以旧对象回存覆盖（F05 陈旧对象教训）。
        """
        t = now if now is not None else time.time()
        actor = actor_obj if actor_obj is not None else char
        changed = False
        for p in PromiseEngine._involving(char.id):
            if p.status.value in TERMINAL_STATUSES:
                continue
            if PromiseEngine._advance(p, t, actor_obj=actor):
                changed = True
        return changed

    @staticmethod
    def _advance(p: Promise, t: float, actor_obj: Optional[Character] = None) -> bool:
        """单条惰性判定：任一方身死→消散；待应诺过期→消散；到期→不攻履约/其余违约。"""
        from storage.db import CharacterRepository

        promiser = CharacterRepository.get_by_id(p.promiser_id)
        promisee = CharacterRepository.get_by_id(p.promisee_id)
        if not _alive(promiser, t) or not _alive(promisee, t):
            return PromiseEngine._settle(
                p, PromiseStatus.DISSOLVED, "立诺人或受诺人已身死道消，诺随旧世而散", t,
                promiser_obj=actor_obj if actor_obj is not None and actor_obj.id == p.promiser_id else None,
            )
        if p.status == PromiseStatus.PENDING:
            if t > p.created_at + PROMISE_ACCEPT_TTL_SECONDS:
                return PromiseEngine._settle(p, PromiseStatus.DISSOLVED, "逾一日未获应诺，诺未成", t)
            return False
        if p.status == PromiseStatus.ACTIVE and t > p.deadline:
            if p.kind == "no_attack":
                return PromiseEngine._settle(
                    p, PromiseStatus.KEPT, "诺期内未曾出手，期满自践", t,
                    promiser_obj=actor_obj if actor_obj is not None and actor_obj.id == p.promiser_id else None,
                )
            return PromiseEngine._settle(
                p, PromiseStatus.BROKEN, "期满未践诺", t,
                promiser_obj=actor_obj if actor_obj is not None and actor_obj.id == p.promiser_id else None,
            )
        return False

    # ---------------- 结算（唯一写终态入口） ----------------
    @staticmethod
    def _settle(
        p: Promise,
        outcome: PromiseStatus,
        note: str,
        t: float,
        promiser_obj: Optional[Character] = None,
    ) -> bool:
        if p.status.value in TERMINAL_STATUSES:
            return False
        # 幂等锚：先落终态存库，再发效果——任何路径重复触发都在此短路
        p.status = outcome
        p.settled_at = t
        p.settle_note = note
        PromiseEngine._repo().save(p)
        if outcome == PromiseStatus.KEPT:
            PromiseEngine._apply_effects(p, kept=True, t=t, promiser_obj=promiser_obj)
        elif outcome == PromiseStatus.BROKEN:
            PromiseEngine._apply_effects(p, kept=False, t=t, promiser_obj=promiser_obj)
            PromiseEngine._broadcast_broken(p)
        # 因果链 S3（karma-event-chains）：诺言终态既有结算全部完成后注记起链
        #（仅 KEPT/BROKEN 且受诺人为 NPC，引擎侧再校验）；钩子异常不炸结算。
        if outcome in (PromiseStatus.KEPT, PromiseStatus.BROKEN):
            try:
                from core.karma_chains import KarmaChainEngine

                KarmaChainEngine.note_promise_settled(p, outcome, now=t)
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "karma chain S3 hook failed", exc_info=True)
        # 判定式求值点 E2（game-feel-phase1 §3.7）：诺言终态后对 promiser
        # 活对象（若可得）求值其 checked 目标；不可得时跳过，E1/E6 兜底。
        if promiser_obj is not None and promiser_obj.id == p.promiser_id:
            try:
                from core.goals import evaluate_checked_goals

                if evaluate_checked_goals(promiser_obj, t):
                    from storage.db import CharacterRepository

                    CharacterRepository.save(promiser_obj)
            except Exception:
                pass
        return True

    @staticmethod
    def _apply_effects(p: Promise, kept: bool, t: float, promiser_obj: Optional[Character] = None) -> None:
        """功德/业力走既有 karma 账本；NPC 态度走既有 shift_attitude；因果链留痕。"""
        from storage.db import CharacterRepository, KarmaLinkRepository
        from core.bounty import KarmaLink

        promiser = promiser_obj if (promiser_obj is not None and promiser_obj.id == p.promiser_id) \
            else CharacterRepository.get_by_id(p.promiser_id)
        if _alive(promiser, t):
            if kept:
                promiser.karma.add_merit(PROMISE_MERIT_KEPT)
            else:
                promiser.karma.add_sin(PROMISE_SIN_BROKEN, t)
            try:
                CharacterRepository.save(promiser)
            except Exception:
                pass
        if p.promisee_is_npc:
            promisee = CharacterRepository.get_by_id(p.promisee_id)
            if _alive(promisee, t):
                try:
                    from core.npc_mind import shift_attitude

                    shift_attitude(
                        promisee, p.promiser_id,
                        PROMISE_ATTITUDE_DELTA if kept else -PROMISE_ATTITUDE_DELTA,
                        reason="践诺" if kept else "背诺",
                    )
                except Exception:
                    pass
        try:
            KarmaLinkRepository.save(KarmaLink(
                a_id=p.promiser_id, a_name=p.promiser_name,
                b_id=p.promisee_id, b_name=p.promisee_name,
                link_type="诺", strength=1,
                note=(f"践诺：{p.desc}" if kept else f"违约：{p.desc}（{p.settle_note}）"),
                created_at=t,
            ))
        except Exception:
            pass

    @staticmethod
    def _broadcast_broken(p: Promise) -> None:
        try:
            import core.jianghu as jianghu

            jianghu.append_event(
                kind="promise",
                actor_ids=[p.promiser_id],
                actor_names=[p.promiser_name],
                target_ids=[p.promisee_id],
                location="",
                summary=(
                    f"【背诺】{p.promiser_name} 曾诺「{p.desc}」，如今{p.settle_note}——"
                    f"天道记账：业力 +{PROMISE_SIN_BROKEN}"
                ),
                rule_result={"sin": PROMISE_SIN_BROKEN, "kind": p.kind},
                narrative="",
                ref_ids=[p.promiser_id, p.promisee_id],
                source="rule",
            )
        except Exception:
            pass

    @staticmethod
    def note_debt_payment(
        payer: Character, creditor: Character, amount: int, now: Optional[float] = None,
    ) -> Optional[str]:
        """旧债还款事实钩子（game-feel-phase1 §3.5）：灵石/财货真实流向
        债主时累计 paid，paid ≥ param 时走唯一终态入口判 KEPT。

        挂点：专柜买入结算（付款额）、会话赠礼结算（计价折算值）。
        无对应 ACTIVE debt 时静默返回 None。
        """
        t = now if now is not None else time.time()
        try:
            amt = int(amount or 0)
        except (TypeError, ValueError):
            amt = 0
        if amt <= 0 or payer is None or creditor is None:
            return None
        for p in PromiseEngine._open_of(payer.id):
            if p.kind != "debt" or p.promisee_id != creditor.id:
                continue
            if p.status != PromiseStatus.ACTIVE:
                continue
            p.paid = int(p.paid or 0) + amt
            try:
                due = int(p.param or 0)
            except (TypeError, ValueError):
                due = 0
            if due > 0 and p.paid >= due:
                if PromiseEngine._settle(p, PromiseStatus.KEPT, "旧债已清", t, promiser_obj=payer):
                    return f"【旧债已清】对【{creditor.name}】的旧债 {due} 灵石已还清，天道销账。"
                return None
            PromiseEngine._repo().save(p)
            return f"【抵旧债】此笔往来抵旧债：已还 {p.paid}/{due} 灵石。"
        return None

    # ---------------- 事实钩子（各既有落账点调用，均只认真实落账） ----------------
    @staticmethod
    def note_gift(giver: Character, receiver: Character, item_name: str, now: Optional[float] = None) -> Optional[str]:
        """会话赠礼落账段调用：真赠出同名物品给受诺 NPC → 践诺。"""
        t = now if now is not None else time.time()
        for p in PromiseEngine._open_of(giver.id):
            if p.kind != "gift" or p.promisee_id != receiver.id:
                continue
            if p.status == PromiseStatus.ACTIVE and t <= p.deadline and p.param == item_name:
                if PromiseEngine._settle(p, PromiseStatus.KEPT, "如约赠出诺物", t, promiser_obj=giver):
                    return f"【践诺】你赠出的【{item_name}】正应前诺——天道记下此诺已践：功德 +{PROMISE_MERIT_KEPT}。"
            else:
                PromiseEngine._advance(p, t, actor_obj=giver)
        return None

    @staticmethod
    def note_arrival(char: Character, location: str, now: Optional[float] = None) -> Optional[str]:
        """迁跃落点调用：落点命中抵达诺目标地 → 践诺。

        见证人不消费事实（评审 M1）：同一次抵达可同时践多条同目标抵达诺
        （不同见证人），结算全部命中诺而非首条即返；总量受未结上限约束。
        """
        t = now if now is not None else time.time()
        msgs: List[str] = []
        for p in PromiseEngine._open_of(char.id):
            if p.kind != "arrive":
                continue
            if p.status == PromiseStatus.ACTIVE and t <= p.deadline and p.param == location:
                if PromiseEngine._settle(p, PromiseStatus.KEPT, "如约抵达诺地", t, promiser_obj=char):
                    msgs.append(
                        f"【践诺】你如约抵达【{location}】（【{p.promisee_name}】见证）"
                        f"——天道记下此诺已践：功德 +{PROMISE_MERIT_KEPT}。"
                    )
            else:
                PromiseEngine._advance(p, t, actor_obj=char)
        return "\n".join(msgs) if msgs else None

    @staticmethod
    def note_quest_completed(char: Character, now: Optional[float] = None) -> Optional[str]:
        """委托整链完成落账段调用 → 委托诺践诺。

        见证人不消费事实（评审 M1）：同一次整链完成可同时践多条委托诺
        （不同见证人），结算全部命中诺而非首条即返；总量受未结上限约束。
        """
        t = now if now is not None else time.time()
        msgs: List[str] = []
        for p in PromiseEngine._open_of(char.id):
            if p.kind != "quest":
                continue
            if p.status == PromiseStatus.ACTIVE and t <= p.deadline:
                if PromiseEngine._settle(p, PromiseStatus.KEPT, "如约办成连环委托", t, promiser_obj=char):
                    msgs.append(
                        f"【践诺】连环委托办成，正应【{p.promisee_name}】见证之诺"
                        f"——天道记下此诺已践：功德 +{PROMISE_MERIT_KEPT}。"
                    )
            else:
                PromiseEngine._advance(p, t, actor_obj=char)
        return "\n".join(msgs) if msgs else None

    @staticmethod
    def note_attack(attacker: Character, defender: Character, now: Optional[float] = None) -> Optional[str]:
        """斗法出手调用（硬前置全过、出手动作成立）：对受诺人出手 → 当场判毁诺；
        若诺期已满（期内未出手），先按履约结算，本次出手不背诺。"""
        t = now if now is not None else time.time()
        for p in PromiseEngine._open_of(attacker.id):
            if p.kind != "no_attack" or p.promisee_id != defender.id:
                continue
            if p.status == PromiseStatus.PENDING:
                # 待应诺之诺义务未生效，出手不背诺；仅顺带惰性推进（过期/身死消散）
                PromiseEngine._advance(p, t, actor_obj=attacker)
            elif p.status == PromiseStatus.ACTIVE and t > p.deadline:
                PromiseEngine._advance(p, t, actor_obj=attacker)
            elif p.status == PromiseStatus.ACTIVE:
                if PromiseEngine._settle(p, PromiseStatus.BROKEN, "诺期内率先对受诺人出手", t, promiser_obj=attacker):
                    return (
                        f"【诺破】你曾立诺不向【{defender.name}】出手，如今率先动手——"
                        f"天道记下此诺已破：业力 +{PROMISE_SIN_BROKEN}。"
                    )
        return None

    # ---------------- 死亡钩子 ----------------
    @staticmethod
    def on_owner_death(char: Character, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """任一方身死：其未结诺全部消散（不判违约、无功无过），随旧世而散。

        行为不变，仅多返回被消散的未结诺摘要
        [{other_name, desc, kind, role}]，供转世留痕（LifeTrace.open_promises）
        经调用方注入 LegacyEngine.settle_death（诺在 settle 前已被消散，
        settle_death 内部无从再查未结态，故须由此回传）。"""
        t = now if now is not None else time.time()
        dissolved: List[Dict[str, Any]] = []
        for p in PromiseEngine._involving(char.id):
            if p.status.value in TERMINAL_STATUSES:
                continue
            if p.promiser_id == char.id:
                other_name, role = p.promisee_name, "我许诺"
            else:
                other_name, role = p.promiser_name, "诺于我"
            dissolved.append({
                "other_name": other_name,
                "desc": p.desc,
                "kind": p.kind,
                "role": role,
            })
            PromiseEngine._settle(p, PromiseStatus.DISSOLVED, "立诺人或受诺人已身死道消，诺随旧世而散", t)
        return dissolved

    # ---------------- 面板 ----------------
    @staticmethod
    @staticmethod
    def _row(p: "Promise", bucket: str, t: float) -> Dict[str, Any]:
        if p.status == PromiseStatus.PENDING:
            left = max(0.0, p.created_at + PROMISE_ACCEPT_TTL_SECONDS - t)
        elif p.status == PromiseStatus.ACTIVE:
            left = max(0.0, (p.deadline or 0) - t)
        else:
            left = 0.0
        return {
            "bucket": bucket,
            "desc": p.desc,
            "kind": p.kind,
            "promiser": p.promiser_name,
            "promisee": p.promisee_name,
            "status": p.status.value,
            "left_s": left,
            "deadline": p.deadline,
            "settle_note": p.settle_note or "",
        }

    @staticmethod
    def panel_data(char: Character, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """诺言行集（/诺言 promises 键；与 panel_text 同源）。空态为 []。"""
        t = now if now is not None else time.time()
        mine = PromiseEngine._involving(char.id)
        my_open = [p for p in mine if p.promiser_id == char.id and p.status.value not in TERMINAL_STATUSES]
        to_accept = [p for p in mine if p.promisee_id == char.id and p.status == PromiseStatus.PENDING]
        received = [p for p in mine if p.promisee_id == char.id and p.status == PromiseStatus.ACTIVE]
        history = [p for p in mine if p.status.value in TERMINAL_STATUSES]
        history.sort(key=lambda p: p.settled_at, reverse=True)
        rows = [PromiseEngine._row(p, "我立之诺", t) for p in my_open]
        rows += [PromiseEngine._row(p, "待我应诺", t) for p in to_accept]
        rows += [PromiseEngine._row(p, "我受之诺", t) for p in received]
        rows += [PromiseEngine._row(p, "近史", t) for p in history[:PROMISE_HISTORY_N]]
        return rows

    def panel_text(char: Character, now: Optional[float] = None) -> str:
        t = now if now is not None else time.time()
        mine = PromiseEngine._involving(char.id)
        my_open = [p for p in mine if p.promiser_id == char.id and p.status.value not in TERMINAL_STATUSES]
        to_accept = [p for p in mine if p.promisee_id == char.id and p.status == PromiseStatus.PENDING]
        received = [p for p in mine if p.promisee_id == char.id and p.status == PromiseStatus.ACTIVE]
        history = [p for p in mine if p.status.value in TERMINAL_STATUSES]
        history.sort(key=lambda p: p.settled_at, reverse=True)
        lines = [
            "【诺言账】天道为凭，言出法随。",
            "（唯 /许诺 指令立诺、/应诺 应下入账；交谈口头应承——纵是亲口说「我答应你」——天道不记、不核、不算。）",
        ]
        if my_open:
            lines.append("〔我立之诺 · 进行中〕")
            for p in my_open:
                if p.status == PromiseStatus.PENDING:
                    tail = f"待【{p.promisee_name}】应诺（余 {_fmt_left(p.created_at + PROMISE_ACCEPT_TTL_SECONDS - t)}，逾期未应则消散）"
                else:
                    tail = f"诺期余 {_fmt_left(p.deadline - t)}"
                lines.append(f"· {p.desc}——{tail}")
        if to_accept:
            lines.append("〔待我应诺〕")
            for p in to_accept:
                lines.append(
                    f"· 【{p.promiser_name}】向你立诺：{p.desc}——/应诺 {p.promiser_name} 应下"
                    f"（余 {_fmt_left(p.created_at + PROMISE_ACCEPT_TTL_SECONDS - t)}）"
                )
        if received:
            lines.append("〔我受之诺 · 进行中〕（义务在对方，你只见证）")
            for p in received:
                lines.append(f"· 【{p.promiser_name}】诺你：{p.desc}——诺期余 {_fmt_left(p.deadline - t)}")
        if not (my_open or to_accept or received):
            lines.append("眼下无未结之诺。同场以 /许诺 <对象> 赠物 <物品> | 抵达 <地点> | 委托 | 不攻 立诺。")
        if history:
            lines.append("〔近史〕")
            mark = {"KEPT": "践诺", "BROKEN": "违约", "DISSOLVED": "消散"}
            for p in history[:PROMISE_HISTORY_N]:
                role = "我诺" if p.promiser_id == char.id else "诺我"
                lines.append(f"· [{mark.get(p.status.value, p.status.value)}·{role}] {p.desc}——{p.settle_note}")
        return "\n".join(lines)
