"""
AI 天道事件链（karma-event-chains）：重大因果的「延迟兑现」管道。

设计口径（docs/compose/spec/karma-event-chains.md）：
- 五源（态度跨阈/关系边达阈/出师转恩/诺言终态/击杀/悬赏销案）登记一条
  有时限、有强度、有状态的链；规则引擎按游戏日发酵、到期一次性兑现。
- 数值/时序/状态机 100% 规则裁决；寿元恒 0 影响（铁律）；LLM 只在
  兑现落锚后润色一句话台词，失败/关闭/无预算一律本地模板，永不断链。
- 幂等沿 promises 范式：chain_key 判重起链、终态先落锚再发效果
  （at-most-once）、终态入口短路重放。
- 链是一世内（角色键）状态：死亡全消散，不进留痕、不折算影子（§7）。
"""
from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config import (
    SECONDS_PER_GAME_DAY,
    KARMA_CHAIN_ATT_GRACE,
    KARMA_CHAIN_ATT_HOSTILE,
    KARMA_CHAIN_DAILY_RESOLVE_MAX,
    KARMA_CHAIN_DAILY_STONES_MAX,
    KARMA_CHAIN_DURATIONS,
    KARMA_CHAIN_EFFECT_CAPS,
    KARMA_CHAIN_HISTORY_N,
    KARMA_CHAIN_LIFETIME_DAYS,
    KARMA_CHAIN_MAX_ACTIVE_GLOBAL,
    KARMA_CHAIN_MAX_ACTIVE_PER_NPC,
    KARMA_CHAIN_MAX_ACTIVE_PER_PLAYER,
    KARMA_CHAIN_MAX_NODES,
    KARMA_CHAIN_NPC_START_INTERVAL_DAYS,
    KARMA_CHAIN_PAIR_COOLDOWN_DAYS,
    KARMA_CHAIN_STRENGTH_CAP,
    KARMA_CHAIN_TERMINAL_KEEP_PER_PLAYER,
    KARMA_CHAIN_TICK_FERMENT_MAX,
    KARMA_CHAIN_TICK_RESOLVE_MAX,
    KARMA_CHAIN_WINDOW_DAYS,
)
from core.models import Character, CharacterStatus

_log = logging.getLogger(__name__)

ACTIVE_STATUSES = ("latent", "fermenting")
TERMINAL_STATUSES = ("resolved", "dissipated")

KIND_CN = {"en": "恩", "chou": "仇", "nuo": "诺", "xue": "血仇"}
STATUS_CN = {
    "latent": "潜伏", "fermenting": "发酵",
    "resolved": "已兑现", "dissipated": "已消散",
}
OUTCOME_CN = {
    "repaid": "报恩", "retaliated": "报复", "honored": "践诺余绪",
    "shamed": "追诺昭告", "avenged": "血仇昭告", "fizzled": "无果而散",
}
DISSIPATE_REASON_CN = {
    "player_dead": "诺随旧世（主体身死）",
    "counterparty_dead": "对象已逝",
    "no_avenger": "无人承仇",
    "expired": "逾期无果",
    "lifetime_cap": "链龄已尽",
    "superseded_by_kill": "对象殁于主体之手，血仇另记",
}
# 发酵传闻可信度（§4.3）
_FERMENT_TRUTH = {"en": 0.85, "chou": 0.9, "nuo+": 0.85, "nuo-": 0.9, "xue": 0.9}


class ChainNode(BaseModel):
    ts: float = 0.0
    game_day: int = 0
    type: str = ""  # origin|strengthen|ferment|rumor|resolve|dissipate|death
    summary: str = ""
    effects: Dict[str, Any] = Field(default_factory=dict)
    source_ref: str = ""


class KarmaChain(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    chain_key: str = ""
    kind: str = ""  # en|chou|nuo|xue
    polarity: int = 0  # +1 恩向 / -1 仇向
    player_id: str = ""
    player_name: str = ""
    counterparty_id: str = ""
    counterparty_name: str = ""
    counterparty_kind: str = "npc"
    delivery_actor_id: str = ""
    delivery_actor_name: str = ""
    strength: int = 1
    status: str = "latent"  # latent|fermenting|resolved|dissipated
    origin_summary: str = ""
    created_at: float = 0.0
    ferment_at: float = 0.0
    mature_at: float = 0.0
    deadline_at: float = 0.0
    resolved_at: float = 0.0
    budget_deferred: bool = False  # R1/MF-3：曾被每日兑现预算暂缓的持久标记
    # （豁免 deadline/链龄硬顶消散，§4.2；旧数据缺字段默认 False 兼容）
    resolution: Dict[str, Any] = Field(default_factory=dict)
    flipped: bool = False
    nodes: List[ChainNode] = Field(default_factory=list)


def _is_npc_char(c: Optional[Character]) -> bool:
    if c is None:
        return False
    uid = str(c.user_id or "")
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def _alive(c: Optional[Character], now: float) -> bool:
    return bool(c) and c.status != CharacterStatus.DEAD and not c.lifespan.is_dead(now)


def _duration_days(kind: str, polarity: int) -> int:
    if kind == "nuo":
        return int(KARMA_CHAIN_DURATIONS["nuo+" if polarity >= 0 else "nuo-"])
    return int(KARMA_CHAIN_DURATIONS.get(kind, 9))


def _kind_polarity_key(kind: str, polarity: int) -> str:
    if kind == "nuo":
        return "nuo+" if polarity >= 0 else "nuo-"
    return kind


def effects_summary(effects: Dict[str, Any]) -> str:
    """effects → 中文落账摘要（面板/江湖账共用口径）。"""
    if not effects:
        return "无数值落账"
    parts = []
    if effects.get("stones_gain"):
        parts.append(f"灵石+{effects['stones_gain']}")
    if effects.get("stones_lose"):
        parts.append(f"灵石-{effects['stones_lose']}")
    if effects.get("exp_gain"):
        parts.append(f"修为+{effects['exp_gain']}")
    if effects.get("exp_lose"):
        parts.append(f"修为-{effects['exp_lose']}")
    if effects.get("merit"):
        parts.append(f"功德+{effects['merit']}")
    if effects.get("sin"):
        parts.append(f"业力+{effects['sin']}")
    if effects.get("dao_heart"):
        parts.append(f"道心{effects['dao_heart']:+d}")
    if effects.get("attitude"):
        parts.append(f"态度{effects['attitude']:+d}")
    return "，".join(parts) if parts else "无数值落账"


class KarmaChainEngine:
    """因果链裁决引擎（规则唯一权威）"""

    # ---------------- 仓储（惰性导入，避开 storage.db ↔ core 循环） ----------------
    @staticmethod
    def _repo():
        from storage.db import KarmaChainRepository

        return KarmaChainRepository

    @staticmethod
    def _chars():
        from storage.db import CharacterRepository

        return CharacterRepository

    # ---------------- 纯函数：数值支与 effects ----------------
    @staticmethod
    def branch_for(chain: KarmaChain) -> str:
        """数值支二选一：由 chain.id 的稳定哈希奇偶定（起链即可预知、不可操纵）。"""
        digest = hashlib.sha256(str(chain.id).encode("utf-8")).digest()
        return "stones" if digest[0] % 2 == 0 else "exp"

    @staticmethod
    def effective_strength(chain: KarmaChain, now: Optional[float] = None) -> int:
        t = now if now is not None else time.time()
        age_days = max(0.0, (t - chain.created_at) / SECONDS_PER_GAME_DAY)
        eff = int(chain.strength) - int(age_days // 30)
        return max(1, min(5, eff))

    @staticmethod
    def compute_effects(chain: KarmaChain, now: Optional[float] = None) -> Dict[str, Any]:
        """兑现 effects 名义值（纯函数，可单测）。flipped 恒 {}；寿元恒不出现。

        灵石/修为扣支的名义值在此给出，落账时按余额/现有修为再钳实际值。
        """
        if chain.flipped:
            return {}
        eff = KarmaChainEngine.effective_strength(chain, now)
        caps = KARMA_CHAIN_EFFECT_CAPS
        branch = KarmaChainEngine.branch_for(chain)
        out: Dict[str, Any] = {}
        if chain.kind == "en":
            if branch == "stones":
                out["stones_gain"] = min(caps["stones_gain"], 15 + 10 * eff)
            else:
                out["exp_gain"] = min(caps["exp_gain"], 20 * eff)
            out["attitude"] = 5
        elif chain.kind == "nuo" and chain.polarity >= 0:
            if branch == "stones":
                out["stones_gain"] = min(caps["stones_gain"], 10 + 5 * eff)
            else:
                out["exp_gain"] = min(caps["exp_gain"], 20 * eff)
            out["merit"] = min(caps["merit"], 5)
            out["attitude"] = 5
        elif chain.kind == "chou":
            if branch == "stones":
                out["stones_lose"] = min(caps["stones_lose"], 10 + 5 * eff)
            else:
                out["exp_lose"] = min(caps["exp_lose"], 10 * eff)
            out["attitude"] = -min(caps["attitude"], 10 + 2 * eff)
            out["dao_heart"] = -min(caps["dao_heart"], 3)
        elif chain.kind == "nuo":  # BROKEN
            out["sin"] = min(caps["sin"], 5)
            out["attitude"] = -12
        elif chain.kind == "xue":
            out["sin"] = min(caps["sin"], 10)
            out["attitude"] = -caps["attitude"]
        return out

    # ---------------- 节点 ----------------
    @staticmethod
    def _append_node(chain: KarmaChain, node_type: str, summary: str, now: float,
                     source_ref: str = "", effects: Optional[Dict[str, Any]] = None,
                     force: bool = False) -> None:
        if len(chain.nodes) >= KARMA_CHAIN_MAX_NODES:
            if not force:
                return
            # 终态节点不受上限：挤掉最旧一条 strengthen 节点腾位
            for i, n in enumerate(chain.nodes):
                if n.type == "strengthen":
                    del chain.nodes[i]
                    break
            else:
                return
        chain.nodes.append(ChainNode(
            ts=now,
            game_day=int(max(0.0, (now - chain.created_at) // SECONDS_PER_GAME_DAY)),
            type=node_type,
            summary=summary,
            effects=dict(effects or {}),
            source_ref=source_ref,
        ))

    # ---------------- 起链（五源共用入口） ----------------
    @staticmethod
    def note_origin(
        player: Character,
        counterparty: Character,
        *,
        kind: str,
        polarity: int,
        strength: int,
        chain_key: str,
        origin_summary: str = "",
        source_ref: str = "",
        now: Optional[float] = None,
    ) -> Optional[KarmaChain]:
        """五源共用起链闸：校验主体/对象 → chain_key 判重 → 同对同 kind 续链
        → 翻转/冷却判定 → 上限与间隔闸 → 落账。任一闸不过返回 None。"""
        t = now if now is not None else time.time()
        if player is None or counterparty is None or player.id == counterparty.id:
            return None
        if kind not in KIND_CN or polarity not in (1, -1) or not chain_key:
            return None
        if _is_npc_char(player) or not _is_npc_char(counterparty):
            return None
        if not _alive(player, t):
            return None
        if kind != "xue" and not _alive(counterparty, t):
            return None
        repo = KarmaChainEngine._repo()
        all_chains = repo.list_all()
        # 1) chain_key 判重：同键任意状态存在——active 走续链，终态视为已消费
        for ch in all_chains:
            if ch.chain_key == chain_key:
                if ch.status in ACTIVE_STATUSES:
                    return KarmaChainEngine._strengthen(ch, source_ref, origin_summary, t)
                return None
        pair = [c for c in all_chains
                if c.player_id == player.id and c.counterparty_id == counterparty.id]
        # 2) 同对同 kind 已有 active → 续链
        for ch in pair:
            if ch.kind == kind and ch.status in ACTIVE_STATUSES:
                return KarmaChainEngine._strengthen(ch, source_ref, origin_summary, t)
        # 3) 翻转/冷却（以该对最近一条终态链为准）
        flipped = False
        terminals = [c for c in pair if c.status in TERMINAL_STATUSES]
        if terminals:
            latest = max(terminals, key=lambda c: c.resolved_at or c.created_at)
            term_at = latest.resolved_at or latest.created_at
            if 0 <= (t - term_at) < KARMA_CHAIN_PAIR_COOLDOWN_DAYS * SECONDS_PER_GAME_DAY:
                if latest.flipped:
                    return None  # 翻转链终态后窗口内再起链：直接拒绝（§8.2 再犯）
                if latest.kind == kind:
                    return None  # 同对同 kind 终态冷却
                if latest.polarity != polarity:
                    flipped = True  # 反向新链降级：只叙事不落数值
        # 4) 上限闸
        actives = [c for c in all_chains if c.status in ACTIVE_STATUSES]
        if len(actives) >= KARMA_CHAIN_MAX_ACTIVE_GLOBAL:
            return None
        if sum(1 for c in actives if c.player_id == player.id) >= KARMA_CHAIN_MAX_ACTIVE_PER_PLAYER:
            return None
        if sum(1 for c in actives if c.counterparty_id == counterparty.id) >= KARMA_CHAIN_MAX_ACTIVE_PER_NPC:
            return None
        # 5) 单 NPC 新起链间隔（续链不限，已在上方返回）
        cp_chains = [c for c in all_chains if c.counterparty_id == counterparty.id]
        if cp_chains:
            latest_created = max(c.created_at for c in cp_chains)
            if 0 <= (t - latest_created) < KARMA_CHAIN_NPC_START_INTERVAL_DAYS * SECONDS_PER_GAME_DAY:
                return None
        duration = _duration_days(kind, polarity)
        chain = KarmaChain(
            chain_key=chain_key,
            kind=kind,
            polarity=polarity,
            player_id=player.id,
            player_name=player.name,
            counterparty_id=counterparty.id,
            counterparty_name=counterparty.name,
            delivery_actor_id="" if kind == "xue" else counterparty.id,
            delivery_actor_name="" if kind == "xue" else counterparty.name,
            strength=max(1, min(KARMA_CHAIN_STRENGTH_CAP, int(strength))),
            status="latent",
            origin_summary=origin_summary,
            created_at=t,
            ferment_at=t + duration * SECONDS_PER_GAME_DAY / 2.0,
            mature_at=t + duration * SECONDS_PER_GAME_DAY,
            deadline_at=t + (duration + KARMA_CHAIN_WINDOW_DAYS) * SECONDS_PER_GAME_DAY,
            flipped=flipped,
        )
        KarmaChainEngine._append_node(chain, "origin", origin_summary or "因果已记", t,
                                      source_ref=source_ref)
        repo.save(chain)
        KarmaChainEngine._prune_terminals(player.id)
        return chain

    @staticmethod
    def _strengthen(chain: KarmaChain, source_ref: str, summary: str, now: float,
                    amount: int = 1) -> Optional[KarmaChain]:
        """续链加强：source_ref 已有 strengthen 节点则跳过（幂等）。"""
        if chain.status not in ACTIVE_STATUSES:
            return None
        # source_ref 判重认全部节点（含 origin）：同一事实的双点钩子
        #（如 S4 resolve_ambush + cascade_kill 同键同 ref）不得二次加强。
        if source_ref and any(n.source_ref == source_ref for n in chain.nodes):
            return chain
        chain.strength = min(KARMA_CHAIN_STRENGTH_CAP, chain.strength + amount)
        KarmaChainEngine._append_node(
            chain, "strengthen", summary or "因果续深", now, source_ref=source_ref)
        KarmaChainEngine._repo().save(chain)
        return chain

    @staticmethod
    def _prune_terminals(player_id: str) -> None:
        """终态链每玩家保留最近 N 条（active 永不删）。"""
        try:
            repo = KarmaChainEngine._repo()
            terminals = [c for c in repo.list_by_player(player_id)
                         if c.status in TERMINAL_STATUSES]
            terminals.sort(key=lambda c: c.resolved_at or c.created_at, reverse=True)
            for ch in terminals[KARMA_CHAIN_TERMINAL_KEEP_PER_PLAYER:]:
                repo.delete(ch.id)
        except Exception:
            pass

    # ---------------- S1 态度跨阈 ----------------
    @staticmethod
    def note_attitude_cross(npc: Character, other_id: str, before: int, after: int,
                            reason: str = "", now: Optional[float] = None) -> Optional[KarmaChain]:
        if (reason or "").startswith("因果链"):
            return None  # 防自激：链自身落账不反起新链
        if npc is None or not _is_npc_char(npc):
            return None
        t = now if now is not None else time.time()
        try:
            player = KarmaChainEngine._chars().get_by_id(other_id)
        except Exception:
            return None
        if player is None or _is_npc_char(player):
            return None
        before, after = int(before), int(after)
        if before < KARMA_CHAIN_ATT_GRACE <= after:
            kind, polarity = "en", 1
            mag = after
            summary = f"施恩累积，态度跨过恩义之线（至 {after}）"
        elif before > KARMA_CHAIN_ATT_HOSTILE >= after:
            kind, polarity = "chou", -1
            mag = abs(after)
            summary = f"积怨渐深，态度跌破仇线（至 {after}）"
        else:
            return None
        strength = 3 + (2 if mag >= 85 else 1 if mag >= 70 else 0)
        try:
            pair = KarmaChainEngine._repo().list_by_pair(player.id, npc.id)
        except Exception:
            pair = []
        epoch = sum(1 for c in pair if c.kind == kind and c.status in TERMINAL_STATUSES) + 1
        return KarmaChainEngine.note_origin(
            player, npc, kind=kind, polarity=polarity, strength=strength,
            chain_key=f"att:{player.id}:{npc.id}:{kind}:{epoch}",
            origin_summary=summary,
            source_ref=f"att-cross:{t:.3f}:{before}->{after}",
            now=t,
        )

    # ---------------- S2 关系边达阈 / S2b 出师转恩 ----------------
    @staticmethod
    def _player_npc_pair(a: Character, b: Character):
        if _is_npc_char(a) and not _is_npc_char(b):
            return b, a
        if _is_npc_char(b) and not _is_npc_char(a):
            return a, b
        return None, None

    @staticmethod
    def note_link_strength(link: Any, a: Character, b: Character,
                           now: Optional[float] = None) -> Optional[KarmaChain]:
        if link is None or getattr(link, "link_type", "") not in ("仇", "恩"):
            return None
        player, npc = KarmaChainEngine._player_npc_pair(a, b)
        if player is None:
            return None
        kind = "chou" if link.link_type == "仇" else "en"
        polarity = -1 if kind == "chou" else 1
        t = now if now is not None else time.time()
        return KarmaChainEngine.note_origin(
            player, npc, kind=kind, polarity=polarity,
            strength=min(5, int(getattr(link, "strength", 1) or 1)),
            chain_key=f"link:{link.id}:{kind}",
            origin_summary=f"因果边「{link.link_type}」积至 {link.strength} 重，成链",
            source_ref=f"link-inc:{link.id}:{link.strength}",
            now=t,
        )

    @staticmethod
    def note_graduation(link: Any, disciple: Character, master: Character,
                        now: Optional[float] = None) -> Optional[KarmaChain]:
        if link is None or disciple is None or master is None:
            return None
        player, npc = KarmaChainEngine._player_npc_pair(disciple, master)
        if player is None:
            return None
        t = now if now is not None else time.time()
        return KarmaChainEngine.note_origin(
            player, npc, kind="en", polarity=1, strength=3,
            chain_key=f"link:{link.id}:en",
            origin_summary="出师转恩，师恩成链",
            source_ref=f"graduation:{link.id}",
            now=t,
        )

    # ---------------- S3 诺言终态 ----------------
    @staticmethod
    def note_promise_settled(p: Any, outcome: Any, now: Optional[float] = None) -> Optional[KarmaChain]:
        outcome_val = getattr(outcome, "value", outcome)
        if outcome_val not in ("KEPT", "BROKEN"):
            return None  # DISSOLVED 永不起链
        if not getattr(p, "promisee_is_npc", False):
            return None  # 受诺人须为 NPC
        t = now if now is not None else time.time()
        try:
            chars = KarmaChainEngine._chars()
            player = chars.get_by_id(p.promiser_id)
            npc = chars.get_by_id(p.promisee_id)
        except Exception:
            return None
        if player is None or npc is None:
            return None
        kept = outcome_val == "KEPT"
        return KarmaChainEngine.note_origin(
            player, npc, kind="nuo", polarity=1 if kept else -1,
            strength=2 if kept else 3,
            chain_key=f"promise:{p.id}",
            origin_summary=(f"践诺余绪：{p.desc}" if kept else f"背诺成账：{p.desc}"),
            source_ref=f"promise:{p.id}",
            now=t,
        )

    # ---------------- S4 击杀（血仇） ----------------
    @staticmethod
    def note_kill(killer: Character, victim: Character,
                  now: Optional[float] = None) -> Optional[KarmaChain]:
        if killer is None or victim is None:
            return None
        if _is_npc_char(killer) or not _is_npc_char(victim):
            return None
        t = now if now is not None else time.time()
        return KarmaChainEngine.note_origin(
            killer, victim, kind="xue", polarity=-1, strength=5,
            chain_key=f"kill:{victim.id}",
            origin_summary=f"【{killer.name}】斩杀【{victim.name}】，血仇已记",
            source_ref=f"kill:{victim.id}",
            now=t,
        )

    # ---------------- S5 悬赏销案 ----------------
    @staticmethod
    def note_bounty_settled(killer: Character, victim: Character, bounties: List[Any],
                            now: Optional[float] = None) -> Optional[KarmaChain]:
        if killer is None or victim is None or not bounties:
            return None
        if _is_npc_char(killer) or not _is_npc_char(victim):
            return None
        t = now if now is not None else time.time()
        ids = sorted(str(b.id) for b in bounties)
        source_ref = f"bounty:{','.join(ids)}"
        total = sum(int(getattr(b, "reward", 0) or 0) for b in bounties)
        # S5 仅续链（R1/MF-2）：已有 active 链（通常 S4 血仇）→ 只续链 +1
        #（source_ref 判重）；无 active 链 → 明确返回 None、不新建链——原
        #「兜底新建 chou 链」语义已废弃（真实击杀路径必先经 S4 起血仇链，
        # 该分支不可达，属死代码；悬赏事实本身已由 bounty 结算落账）。
        try:
            pair = KarmaChainEngine._repo().list_by_pair(killer.id, victim.id)
        except Exception:
            pair = []
        for ch in pair:
            if ch.status in ACTIVE_STATUSES:
                return KarmaChainEngine._strengthen(
                    ch, source_ref, f"悬赏销案（赏金 {total} 灵石）", t)
        return None

    # ---------------- 发酵 ----------------
    @staticmethod
    def _ferment_rumor_text(chain: KarmaChain) -> str:
        p, c = chain.player_name, chain.counterparty_name
        if chain.kind == "en":
            return f"听闻【{c}】屡屡念及【{p}】的恩义，此事怕不会就此作罢。"
        if chain.kind == "chou":
            return f"风闻【{c}】对【{p}】记恨日深，江湖怕有后账要算。"
        if chain.kind == "nuo" and chain.polarity >= 0:
            return f"坊间传【{p}】践诺守信，【{c}】那头自有回音将至。"
        if chain.kind == "nuo":
            return f"【{p}】背诺之事已在坊间传开，【{c}】怕要讨个说法。"
        return f"【{c}】之死已有人誓雪此仇，矛头直指【{p}】。"

    @staticmethod
    def _select_avenger(chain: KarmaChain, now: float) -> Optional[Character]:
        """血仇兑现者现选：死者同宗、存活、NPC；|对玩家态度| 降序、id 升序。"""
        try:
            chars = KarmaChainEngine._chars()
            victim = chars.get_by_id(chain.counterparty_id)
            if victim is None or not victim.sect:
                return None
            from storage.db import NpcMindRepository

            cands = []
            for c in chars.list_all_alive():
                if c.id == chain.counterparty_id or not _is_npc_char(c):
                    continue
                if c.sect != victim.sect:
                    continue
                mind = NpcMindRepository.get(c.id) or {}
                val = ((mind.get("attitudes") or {}).get(chain.player_id) or {}).get("value", 0)
                cands.append((-abs(int(val or 0)), c.id, c))
            cands.sort(key=lambda x: (x[0], x[1]))
            return cands[0][2] if cands else None
        except Exception:
            return None

    @staticmethod
    def _ferment(chain: KarmaChain, now: float) -> bool:
        if chain.status != "latent":
            return False
        # 先落状态+节点（锚），再发传闻/议程（崩溃重放不重复，§5-3）
        chain.status = "fermenting"
        KarmaChainEngine._append_node(chain, "ferment", "因果发酵", now)
        KarmaChainEngine._repo().save(chain)
        try:
            from core import rumors

            rumors.add_rumor(
                KarmaChainEngine._ferment_rumor_text(chain),
                origin=chain.player_name,
                tags=["karma_chain", chain.kind],
                truth=_FERMENT_TRUTH[_kind_polarity_key(chain.kind, chain.polarity)],
                now=now,
            )
        except Exception:
            pass
        if chain.kind == "xue":
            avenger = KarmaChainEngine._select_avenger(chain, now)
            if avenger is not None:
                chain.delivery_actor_id = avenger.id
                chain.delivery_actor_name = avenger.name
                KarmaChainEngine._repo().save(chain)
                try:
                    from storage.db import NpcAgendaRepository

                    existing = NpcAgendaRepository.get(avenger.id) or {}
                    NpcAgendaRepository.upsert(
                        npc_id=avenger.id,
                        npc_name=avenger.name,
                        agenda_type="revenge",
                        target_hint=chain.player_name,
                        note=f"为同门{chain.counterparty_name}复仇（因果链）",
                        state="active",
                        last_tick=float(existing.get("last_tick") or 0.0),
                        progress=int(existing.get("progress") or 0),
                        extra=existing.get("extra") or {},
                    )
                except Exception:
                    pass
        return True

    # ---------------- 每日兑现预算（现实日口径） ----------------
    @staticmethod
    def _resolved_on_day(player_id: str, now: float) -> List[KarmaChain]:
        day = int(now // 86400)
        out = []
        try:
            for ch in KarmaChainEngine._repo().list_by_player(player_id):
                if ch.status == "resolved" and ch.resolved_at \
                        and int(ch.resolved_at // 86400) == day:
                    out.append(ch)
        except Exception:
            pass
        return out

    @staticmethod
    def _budget_allows(chain: KarmaChain, effects: Dict[str, Any], now: float) -> bool:
        done = KarmaChainEngine._resolved_on_day(chain.player_id, now)
        if len(done) >= KARMA_CHAIN_DAILY_RESOLVE_MAX:
            return False
        gain = int(effects.get("stones_gain") or 0)
        if gain:
            used = sum(int((c.resolution.get("effects") or {}).get("stones_gain") or 0)
                       for c in done)
            if used + gain > KARMA_CHAIN_DAILY_STONES_MAX:
                return False  # 顺延，不改支（§8.1）
        return True

    # ---------------- 兑现 ----------------
    @staticmethod
    def _resolve_narrative(chain: KarmaChain, actor_name: str, eff_text: str) -> str:
        p = chain.player_name
        if chain.flipped:
            return f"【{actor_name}】与【{p}】恩仇反复，天道不赏——此链只作昭告，不落数值。"
        if chain.kind == "en":
            return f"【{actor_name}】念及【{p}】旧恩，专程前来报恩——{eff_text}。"
        if chain.kind == "chou":
            return f"【{actor_name}】积怨终有回响，向【{p}】讨还旧账——{eff_text}。"
        if chain.kind == "nuo" and chain.polarity >= 0:
            return f"【{actor_name}】践诺余绪未消，向【{p}】回礼致意——{eff_text}。"
        if chain.kind == "nuo":
            return f"【{actor_name}】因【{p}】背诺昭告讨个说法——{eff_text}。"
        return f"【{actor_name}】为同门【{chain.counterparty_name}】昭告雪仇——{eff_text}。"

    @staticmethod
    def _resolve(chain: KarmaChain, now: Optional[float] = None,
                 allow_polish: bool = False) -> bool:
        """唯一写 resolved 终态入口：先落锚（终态+resolution）再发效果。"""
        t = now if now is not None else time.time()
        if chain.status not in ACTIVE_STATUSES:
            return False
        repo = KarmaChainEngine._repo()
        chars = KarmaChainEngine._chars()
        try:
            player = chars.get_by_id(chain.player_id)
        except Exception:
            player = None
        if not _alive(player, t):
            KarmaChainEngine._dissipate(chain, "player_dead", t)
            return False
        # 兑现者复核
        actor: Optional[Character] = None
        if chain.kind == "xue":
            if chain.delivery_actor_id:
                try:
                    cand = chars.get_by_id(chain.delivery_actor_id)
                except Exception:
                    cand = None
                if _alive(cand, t):
                    actor = cand
            if actor is None:
                actor = KarmaChainEngine._select_avenger(chain, t)
            if actor is None:
                try:
                    from core import rumors

                    rumors.add_rumor(
                        f"【{chain.counterparty_name}】之死终究无人承仇，血债随风淡去。",
                        origin=chain.player_name, tags=["karma_chain", "xue"],
                        truth=0.9, now=t,
                    )
                except Exception:
                    pass
                KarmaChainEngine._dissipate(chain, "no_avenger", t)
                return False
            chain.delivery_actor_id = actor.id
            chain.delivery_actor_name = actor.name
        else:
            try:
                actor = chars.get_by_id(chain.counterparty_id)
            except Exception:
                actor = None
            if not _alive(actor, t):
                has_xue = any(
                    c.kind == "xue" for c in repo.list_by_pair(chain.player_id, chain.counterparty_id)
                )
                KarmaChainEngine._dissipate(
                    chain, "superseded_by_kill" if has_xue else "counterparty_dead", t)
                return False
        # 算效 + 预算（顺延：保持 fermenting，不落锚）
        nominal = KarmaChainEngine.compute_effects(chain, t)
        if not KarmaChainEngine._budget_allows(chain, nominal, t):
            # R1/MF-3：链已到期、本可兑现、仅因每日预算被顺延——当场把
            # budget_deferred 置 True 并落库，豁免 deadline/链龄硬顶消散
            #（§4.2；豁免判定只认此持久标记，进程重启不丢失）。
            if not chain.budget_deferred:
                chain.budget_deferred = True
                repo.save(chain)
            return False
        # 实际落账值：扣支按余额/现有修为钳制；exp_gain 按 max_exp 钳
        # 实际可落值（R1/OBS-2，§4.4：resolution.effects 记实际落账值，
        # 已满时为 0 并省略该键，不得记公式名义值）。
        effects = dict(nominal)
        if effects.get("stones_lose"):
            effects["stones_lose"] = min(int(effects["stones_lose"]), max(0, player.spirit_stones))
        if effects.get("exp_lose"):
            effects["exp_lose"] = min(int(effects["exp_lose"]), max(0, player.realm.current_exp))
        if effects.get("exp_gain"):
            room = max(0, player.realm.max_exp - player.realm.current_exp)
            actual_gain = min(int(effects["exp_gain"]), room)
            if actual_gain > 0:
                effects["exp_gain"] = actual_gain
            else:
                del effects["exp_gain"]
        if chain.flipped:
            outcome = "fizzled"
        else:
            outcome = {
                "en": "repaid", "chou": "retaliated", "xue": "avenged",
            }.get(chain.kind, "honored" if chain.polarity >= 0 else "shamed")
        eff_text = effects_summary(effects)
        narrative = KarmaChainEngine._resolve_narrative(chain, actor.name, eff_text)
        # 落锚：先 save 终态 + resolution，再发效果（at-most-once）。
        # AI 润色不在此处：按 §9/§2.1（R1/OBS-1）润色须在落锚发效之后，
        # 且只替换呈现副本、不回写 resolution/节点字段——见发效后段。
        chain.status = "resolved"
        chain.resolved_at = t
        chain.resolution = {
            "outcome": outcome,
            "effects": dict(effects),
            "narrative": narrative,
        }
        KarmaChainEngine._append_node(
            chain, "resolve", narrative, t, effects=dict(effects), force=True)
        repo.save(chain)
        # 发效（任一子项异常只丢该子项，不回滚锚、不重发）
        if effects:
            try:
                fresh = chars.get_by_id(chain.player_id) or player
                if effects.get("stones_gain"):
                    fresh.spirit_stones += int(effects["stones_gain"])
                if effects.get("stones_lose"):
                    fresh.spirit_stones = max(
                        0, fresh.spirit_stones - int(effects["stones_lose"]))
                if effects.get("exp_gain"):
                    # 修为落账钳 max_exp（R1/OBS-2；effects 已记实际值，此为双保险）
                    fresh.realm.current_exp = min(
                        fresh.realm.max_exp,
                        fresh.realm.current_exp + int(effects["exp_gain"]))
                if effects.get("exp_lose"):
                    fresh.realm.current_exp = max(
                        0, fresh.realm.current_exp - int(effects["exp_lose"]))
                if effects.get("merit"):
                    fresh.karma.add_merit(int(effects["merit"]))
                if effects.get("sin"):
                    fresh.karma.add_sin(int(effects["sin"]), t)
                if effects.get("dao_heart"):
                    fresh.karma.dao_heart = max(
                        0, min(100, fresh.karma.dao_heart + int(effects["dao_heart"])))
                chars.save(fresh)
                player = fresh
            except Exception:
                _log.warning("karma chain %s player effects failed", chain.id, exc_info=True)
            if effects.get("attitude"):
                try:
                    from core.npc_mind import shift_attitude

                    reason_map = {
                        "en": "因果链·报恩", "chou": "因果链·报复",
                        "xue": "因果链·寻仇",
                    }
                    reason = reason_map.get(
                        chain.kind,
                        "因果链·践诺余绪" if chain.polarity >= 0 else "因果链·追诺")
                    shift_attitude(actor, chain.player_id, int(effects["attitude"]),
                                   reason=reason)
                except Exception:
                    _log.warning("karma chain %s attitude failed", chain.id, exc_info=True)
        # AI 润色（R1/OBS-1，回齐 §9/§2.1）：落锚发效之后才润色，结果只进
        # 本次呈现副本（present_narrative，供下方江湖账/角色账留痕文本），
        # 不回写 chain.resolution["narrative"] 与 resolve 节点 summary——
        # 模型字段恒为本地模板，QA 对账与重放口径不受 AI 影响。
        present_narrative = narrative
        if allow_polish:
            try:
                from core import ai_flavor

                personality = ""
                try:
                    from core.npc_mind import ensure_mind

                    personality = (ensure_mind(actor).get("personality") or "")
                except Exception:
                    personality = ""
                polished = ai_flavor.polish_karma_outcome(
                    chain.kind, chain.polarity, actor.name, chain.player_name,
                    narrative, personality=personality,
                )
                if polished:
                    present_narrative = str(polished)[:200]
            except Exception:
                pass  # AI 润色失败/抛异常：本地模板已在手，永不断链
        # 留痕：江湖账（public 自动同步编年史）+ 角色账 KARMA_CHAIN + 血仇频道昭告
        try:
            import core.jianghu as jianghu

            jianghu.append_event(
                kind="karma_chain",
                actor_ids=[actor.id],
                actor_names=[actor.name],
                target_ids=[chain.player_id],
                location=getattr(player, "location", "") or "",
                summary=present_narrative[:200],
                rule_result={"chain_id": chain.id, "kind": chain.kind,
                             "outcome": outcome, "effects": dict(effects)},
                narrative=present_narrative[:200],
                ref_ids=[chain.player_id, actor.id],
                source="rule",
                now=t,
            )
        except Exception:
            pass
        try:
            from core.memory import record_event

            record_event(
                type="KARMA_CHAIN",
                actor=player,
                target=actor,
                summary=present_narrative[:120],
                location=getattr(player, "location", None),
                effects_digest=eff_text,
                chain_id=chain.id,
                now=t,
            )
            # 同场留话：兑现者与主体同场时留一句（不触发战斗）
            if getattr(actor, "location", None) == getattr(player, "location", None):
                record_event(
                    type="TALK",
                    actor=actor,
                    target=player,
                    summary=present_narrative[:120],
                    location=player.location,
                    effects_digest=eff_text,
                    now=t,
                )
        except Exception:
            pass
        if chain.kind == "xue":
            try:
                from core.world_channel import WorldChannel

                WorldChannel.post(
                    "karma_chain",
                    f"【同门寻仇 · 天道记账】{actor.name} 为同门{chain.counterparty_name}昭告雪仇，"
                    f"矛头直指{chain.player_name}。",
                    level="major",
                    actor=chain.player_name,
                    location=getattr(player, "location", "") or "",
                    now=t,
                )
            except Exception:
                pass
        return True

    # ---------------- 消散 ----------------
    @staticmethod
    def _dissipate(chain: KarmaChain, reason: str, now: Optional[float] = None) -> bool:
        """唯一写 dissipated 终态入口：先落锚再发收尾留痕。"""
        t = now if now is not None else time.time()
        if chain.status not in ACTIVE_STATUSES:
            return False
        was_fermenting = chain.status == "fermenting"
        reason_cn = DISSIPATE_REASON_CN.get(reason, reason)
        chain.status = "dissipated"
        chain.resolved_at = t
        chain.resolution = {"outcome": "dissipated", "reason": reason, "effects": {}}
        KarmaChainEngine._append_node(
            chain, "dissipate", f"因果链消散：{reason_cn}", t, force=True)
        KarmaChainEngine._repo().save(chain)
        if was_fermenting:
            try:
                import core.jianghu as jianghu

                if reason == "player_dead":
                    summary = (f"【{chain.player_name}】与【{chain.counterparty_name}】"
                               f"之间未了之链随旧世而散。")
                else:
                    summary = (f"【{chain.player_name}】与【{chain.counterparty_name}】"
                               f"之间的因果链消散（{reason_cn}）。")
                jianghu.append_event(
                    kind="karma_chain",
                    actor_ids=[chain.player_id],
                    actor_names=[chain.player_name],
                    target_ids=[chain.counterparty_id],
                    location="",
                    summary=summary,
                    rule_result={"chain_id": chain.id, "kind": chain.kind,
                                 "outcome": "dissipated", "reason": reason},
                    narrative="",
                    ref_ids=[chain.player_id, chain.counterparty_id],
                    source="rule",
                    now=t,
                )
            except Exception:
                pass
        return True

    # ---------------- 推进 ----------------
    @staticmethod
    def _advance_chain(chain: KarmaChain, now: float, allow_polish: bool = False,
                       do_ferment: bool = True, do_resolve: bool = True) -> Optional[Dict[str, Any]]:
        if chain.status not in ACTIVE_STATUSES:
            return None
        t = now
        chars = KarmaChainEngine._chars()
        # 存活检查先行（R1/MF-3 豁免边界）：死亡类消散不豁免——主体/对象
        # 死亡的判定全部排在时间类消散（链龄硬顶/窗口逾期）与豁免判定之前。
        # 主体死亡 → 消散（与 on_owner_death 幂等合流）
        try:
            player = chars.get_by_id(chain.player_id)
        except Exception:
            player = None
        if not _alive(player, t):
            if KarmaChainEngine._dissipate(chain, "player_dead", t):
                return {"chain_id": chain.id, "action": "dissipated", "reason": "player_dead"}
            return None
        # 对象死亡（血仇的对象即死者，豁免）
        if chain.kind != "xue":
            try:
                cp = chars.get_by_id(chain.counterparty_id)
            except Exception:
                cp = None
            if not _alive(cp, t):
                has_xue = False
                try:
                    has_xue = any(
                        c.kind == "xue"
                        for c in KarmaChainEngine._repo().list_by_pair(
                            chain.player_id, chain.counterparty_id)
                    )
                except Exception:
                    pass
                reason = "superseded_by_kill" if has_xue else "counterparty_dead"
                if KarmaChainEngine._dissipate(chain, reason, t):
                    return {"chain_id": chain.id, "action": "dissipated", "reason": reason}
                return None
        # 链龄硬顶（存活检查之后；budget_deferred 豁免：被每日预算暂缓
        # 的链不因此消散，R1/MF-3）
        if not chain.budget_deferred and \
                t - chain.created_at > KARMA_CHAIN_LIFETIME_DAYS * SECONDS_PER_GAME_DAY:
            if KarmaChainEngine._dissipate(chain, "lifetime_cap", t):
                return {"chain_id": chain.id, "action": "dissipated", "reason": "lifetime_cap"}
            return None
        # 窗口逾期（先于兑现判定：逾期未兑现即消散，零落账；
        # budget_deferred 豁免 R1/MF-3：暂缓链保持 fermenting 等预算重置）
        if not chain.budget_deferred and t > chain.deadline_at:
            if KarmaChainEngine._dissipate(chain, "expired", t):
                return {"chain_id": chain.id, "action": "dissipated", "reason": "expired"}
            return None
        acted: Optional[Dict[str, Any]] = None
        if do_ferment and chain.status == "latent" and t >= chain.ferment_at:
            if KarmaChainEngine._ferment(chain, t):
                acted = {"chain_id": chain.id, "action": "fermented"}
        if do_resolve and chain.status == "fermenting" and t >= chain.mature_at:
            if KarmaChainEngine._resolve(chain, t, allow_polish=allow_polish):
                acted = {"chain_id": chain.id, "action": "resolved",
                         "text": (chain.resolution or {}).get("narrative", "")}
            elif chain.status == "dissipated":
                acted = {"chain_id": chain.id, "action": "dissipated",
                         "reason": (chain.resolution or {}).get("reason", "")}
        return acted

    @staticmethod
    def tick_world(now: Optional[float] = None) -> List[Dict[str, Any]]:
        """世界 tick 推进（挂 NpcAgendaEngine.tick_world 尾）：单轮发酵 ≤10、兑现 ≤5。"""
        t = now if now is not None else time.time()
        results: List[Dict[str, Any]] = []
        try:
            chains = KarmaChainEngine._repo().list_active()
        except Exception:
            return results
        # 预算重置后暂缓链优先兑现（R1/MF-3）：budget_deferred 在前，
        # 其内仍按 mature_at 升序。
        chains.sort(key=lambda c: (not c.budget_deferred, c.mature_at, c.created_at))
        ferment_used = 0
        resolve_used = 0
        polished = False
        for chain in chains:
            need_resolve = t >= chain.mature_at and chain.status in ACTIVE_STATUSES
            # 每条 active 链每轮都过 _advance_chain 的存活/消散检查（主体/对象
            # 死亡、窗口逾期、链龄硬顶），不因「未到发酵/到期时点」跳过——否则
            # 绕过死亡钩子直接死亡的主体（如测试夹具置死）名下链永不消散、
            # 跨轮累积撑满全服上限。预算只钳发酵/兑现动作本身（do_* 标志）。
            allow_polish = need_resolve and not polished
            r = KarmaChainEngine._advance_chain(
                chain, t, allow_polish=allow_polish,
                do_ferment=ferment_used < KARMA_CHAIN_TICK_FERMENT_MAX,
                do_resolve=resolve_used < KARMA_CHAIN_TICK_RESOLVE_MAX,
            )
            if r:
                results.append(r)
                if r["action"] == "fermented":
                    ferment_used += 1
                elif r["action"] == "resolved":
                    resolve_used += 1
                    if allow_polish:
                        polished = True
        return results

    @staticmethod
    def advance_for(char: Character, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """惰性推进单个玩家名下链（查询前调用）；单轮至多兑现 1 条。"""
        t = now if now is not None else time.time()
        results: List[Dict[str, Any]] = []
        if char is None:
            return results
        try:
            chains = [c for c in KarmaChainEngine._repo().list_by_player(char.id)
                      if c.status in ACTIVE_STATUSES]
        except Exception:
            return results
        chains.sort(key=lambda c: (not c.budget_deferred, c.mature_at, c.created_at))
        resolved = 0
        for chain in chains:
            r = KarmaChainEngine._advance_chain(
                chain, t, allow_polish=False, do_resolve=resolved < 1)
            if r:
                results.append(r)
                if r["action"] == "resolved":
                    resolved += 1
        return results

    # ---------------- 死亡衔接 ----------------
    @staticmethod
    def on_owner_death(char: Character, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """主体死亡：其未了链全部消散（不抢先兑现、不进留痕、不折算影子）。

        返回值只供调用方日志/计数，不注入 settle_death（§7.1）。
        """
        t = now if now is not None else time.time()
        out: List[Dict[str, Any]] = []
        if char is None:
            return out
        try:
            chains = [c for c in KarmaChainEngine._repo().list_by_player(char.id)
                      if c.status in ACTIVE_STATUSES]
        except Exception:
            return out
        for chain in chains:
            if KarmaChainEngine._dissipate(chain, "player_dead", t):
                out.append({
                    "chain_id": chain.id,
                    "kind": chain.kind,
                    "counterparty_name": chain.counterparty_name,
                    "reason": "player_dead",
                })
        return out

    # ---------------- 面板（双端同源） ----------------
    @staticmethod
    def panel_text(char: Character, now: Optional[float] = None) -> str:
        t = now if now is not None else time.time()
        try:
            mine = KarmaChainEngine._repo().list_by_player(char.id)
        except Exception:
            mine = []
        active = [c for c in mine if c.status in ACTIVE_STATUSES]
        active.sort(key=lambda c: c.created_at)
        history = [c for c in mine if c.status in TERMINAL_STATUSES]
        history.sort(key=lambda c: c.resolved_at or c.created_at, reverse=True)
        lines = ["天道记账，前因后果皆有回音。"]
        if active:
            lines.append(f"〔进行中〕（{len(active)}/{KARMA_CHAIN_MAX_ACTIVE_PER_PLAYER}）")
            for ch in active:
                total = _duration_days(ch.kind, ch.polarity)
                elapsed = int(max(0.0, (t - ch.created_at) // SECONDS_PER_GAME_DAY))
                pct = min(99, int(100 * elapsed / max(1, total))) if total else 0
                if ch.kind == "xue":
                    direction = "同门誓仇"
                elif ch.polarity > 0:
                    direction = "对象念恩" if ch.kind == "en" else "对象念诺"
                else:
                    direction = "对象记恨" if ch.kind == "chou" else "对象追诺"
                lines.append(
                    f"· [{KIND_CN.get(ch.kind, ch.kind)}·{STATUS_CN.get(ch.status, ch.status)} "
                    f"{elapsed}/{total} 日] {ch.counterparty_name}——{ch.origin_summary}")
                lines.append(f"  强度 {ch.strength} · 发酵 {pct}% · 余波将至：{direction}")
        if history:
            lines.append("〔近史〕")
            for ch in history[:KARMA_CHAIN_HISTORY_N]:
                kind_cn = KIND_CN.get(ch.kind, ch.kind)
                if ch.status == "resolved":
                    res = ch.resolution or {}
                    outcome_cn = OUTCOME_CN.get(res.get("outcome", ""), "已兑现")
                    eff = res.get("effects") or {}
                    tail = effects_summary(eff) if eff else (res.get("narrative") or "只叙事")
                    lines.append(
                        f"· [已兑现·{kind_cn}] {ch.counterparty_name}——{outcome_cn}：{tail}")
                else:
                    reason = (ch.resolution or {}).get("reason", "")
                    lines.append(
                        f"· [已消散·{kind_cn}] {ch.counterparty_name}——"
                        f"{DISSIPATE_REASON_CN.get(reason, reason or '已消散')}")
        if not active and not history:
            lines.append("眼下无因果缠身。施恩、结仇、立诺、行凶，天道都记着。")
        return "\n".join(lines)

    @staticmethod
    def status_summary(char: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """_status_dict 只增键的数据源（前端岗接线）：计数 + 最近到期游戏日。"""
        t = now if now is not None else time.time()
        try:
            mine = KarmaChainEngine._repo().list_by_player(char.id)
        except Exception:
            mine = []
        active = [c for c in mine if c.status in ACTIVE_STATUSES]
        nearest: Optional[int] = None
        for ch in active:
            remain = ch.mature_at - t
            days = 0 if remain <= 0 else int(math.ceil(remain / SECONDS_PER_GAME_DAY))
            nearest = days if nearest is None else min(nearest, days)
        return {
            "active": len(active),
            "fermenting": sum(1 for c in active if c.status == "fermenting"),
            "nearest_mature_game_days": nearest,
        }
