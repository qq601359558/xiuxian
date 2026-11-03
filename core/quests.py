"""
NPC 委托链（F07）：同场 NPC 发布 2–4 环系列委托（送信/寻物/除妖），逐环当面交付推进。

设计口径（docs/compose/spec/quests.md）：
- 与悬赏板区分：悬赏=玩家出钱杀人结赏；委托=NPC 出题、规则定价、系统发奖，不杀人、不收钱。
- 核验只认既有事实：交付对象实时位置（CharacterRepository）、行囊物品、探险落账计数。
- 环目标与奖励 100% 规则生成（模板池常量），零 AI 参与；奖励成链定价、完成一次发放（幂等）。
- 状态存角色字段（active_quest，随旧世消散）；可接 offers 存 world_state（视图/接取一致）。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character, CharacterStatus, QuestChain, QuestRing
from storage.db import CharacterRepository, WorldStateRepository

# ---------------- 常量（规则单点，见 spec） ----------------
QUEST_MAX_ACTIVE = 1                # 同时进行中链上限
QUEST_CHAIN_MIN_RINGS = 2
QUEST_CHAIN_MAX_RINGS = 4
QUEST_CHAIN_TTL_SECONDS = 86400.0   # 链有效期：现实 24 小时
QUEST_ACCEPT_COOLDOWN_SECONDS = 600.0  # 链了结后接取冷却（防接→弃洗链）
QUEST_OFFER_TTL_SECONDS = 3600.0    # offers 缓存有效期
QUEST_REWARD_STONES_PER_RING = 30
QUEST_REWARD_TIER_BONUS = 10        # 发布者境界 tier 每级加成
QUEST_REWARD_STONES_CAP = 200       # 链奖励灵石封顶（公式极值 210，此值真实生效；< EVENT_EFFECT_CAPS stones_gain 300）
QUEST_REWARD_MERIT = 5              # 链奖励功德
QUEST_ART_CLUE_P = 0.25             # 完成时功法线索概率（每链至多 1 门）
QUEST_ATTITUDE_DELTA = 8            # 完成时发布 NPC 态度增量（既有 ±10 口径内）
QUEST_FETCH_ITEMS = ["妖兽内丹", "百年灵芝", "聚灵草", "灵谷"]
QUEST_ART_CLUE_POOL = ["裂风斩", "寒冰诀", "厚土诀", "流云步"]
QUEST_SLAY_NEED_RANGE = (1, 2)

QUEST_KIND_CN = {"deliver": "送信", "fetch": "寻物", "slay": "除妖"}

# 环文案模板池（本地规则模板，零 AI；{target}/{item}/{need} 为规则参数）
QUEST_RING_TEMPLATES: Dict[str, List[str]] = {
    "deliver": [
        "替我把这封手书送到【{target}】手中，凭委托手令当面交清，他自会明白。",
        "我有一桩要事需告知【{target}】，劳你跑一趟，当面传到。",
    ],
    "fetch": [
        "我正缺一味【{item}】，替我寻来一份，必有重谢。",
        "听闻【{item}】难得，你若能寻得一份交我，我自有报答。",
    ],
    "slay": [
        "近来山野妖兽猖獗，去探险除妖 {need} 次，再回来报我。",
        "周边妖兽扰我清净，劳你外出探险剿除 {need} 次，事成复命。",
    ],
}


def _is_npc(c: Character) -> bool:
    return str(c.user_id).startswith("npc_") or str(c.user_id).startswith("ai_npc_")


def _alive(c: Optional[Character], now: float) -> bool:
    return bool(c) and c.status != CharacterStatus.DEAD and not c.lifespan.is_dead(now)


def _offers_key(player_id: str) -> str:
    return f"quest_offers:{player_id}"


def reward_stones_for(publisher: Character, ring_count: int) -> int:
    """链奖励定价公式（成链写死）：环数×30 + 发布者境界×10，封顶 QUEST_REWARD_STONES_CAP=200"""
    raw = ring_count * QUEST_REWARD_STONES_PER_RING + publisher.realm.tier * QUEST_REWARD_TIER_BONUS
    return min(QUEST_REWARD_STONES_CAP, raw)


class QuestEngine:
    """委托链裁决引擎（规则唯一权威）"""

    # ---------------- 生成 ----------------
    @staticmethod
    def generate_chain(
        publisher: Character,
        player: Character,
        rng: Optional[random.Random] = None,
        others: Optional[List[Character]] = None,
    ) -> QuestChain:
        """按规则模板生成一条链（奖励定价写死；accepted_at/expires_at 接取时才写）"""
        r = rng or random.Random()
        if others is None:
            others = [
                c for c in CharacterRepository.list_all_alive()
                if _is_npc(c) and c.id != publisher.id
            ]
        kinds = ["fetch", "slay"] + (["deliver"] if others else [])
        n = r.randint(QUEST_CHAIN_MIN_RINGS, QUEST_CHAIN_MAX_RINGS)
        rings: List[QuestRing] = []
        prev = ""
        for _ in range(n):
            choices = [k for k in kinds if k != prev] or kinds
            kind = r.choice(choices)
            prev = kind
            if kind == "deliver":
                target = r.choice(others)
                desc = r.choice(QUEST_RING_TEMPLATES["deliver"]).format(target=target.name)
                rings.append(QuestRing(
                    kind=kind, desc=desc,
                    deliver_npc_id=target.id, deliver_npc_name=target.name,
                ))
            elif kind == "fetch":
                item = r.choice(QUEST_FETCH_ITEMS)
                desc = r.choice(QUEST_RING_TEMPLATES["fetch"]).format(item=item)
                rings.append(QuestRing(
                    kind=kind, desc=desc,
                    deliver_npc_id=publisher.id, deliver_npc_name=publisher.name,
                    item_name=item, need=1,
                ))
            else:  # slay
                need = r.randint(*QUEST_SLAY_NEED_RANGE)
                desc = r.choice(QUEST_RING_TEMPLATES["slay"]).format(need=need)
                rings.append(QuestRing(
                    kind=kind, desc=desc,
                    deliver_npc_id=publisher.id, deliver_npc_name=publisher.name,
                    need=need,
                ))
        return QuestChain(
            publisher_id=publisher.id,
            publisher_name=publisher.name,
            rings=rings,
            reward_stones=reward_stones_for(publisher, len(rings)),
            reward_merit=QUEST_REWARD_MERIT,
        )

    # ---------------- offers（可接预览，存 world_state） ----------------
    @staticmethod
    def offers_for(
        player: Character,
        now: Optional[float] = None,
        rng: Optional[random.Random] = None,
    ) -> List[Tuple[Character, QuestChain]]:
        """当前同场 NPC 的可接链。TTL 内且同场集合不变则复用缓存，保证所见即所接。"""
        t = now if now is not None else time.time()
        alive = CharacterRepository.list_all_alive()
        npcs_here = sorted(
            (c for c in alive if _is_npc(c) and c.location == player.location and _alive(c, t)),
            key=lambda c: c.name,
        )
        if not npcs_here:
            return []
        key = _offers_key(player.id)
        cached = None
        try:
            cached = WorldStateRepository.get(key)
        except Exception:
            cached = None
        # 缓存容错（评审 S4）：at 被写坏成非数值时按过期处理，不抛错
        cached_offers: Dict[str, Any] = {}
        cached_at = 0.0
        if isinstance(cached, dict):
            try:
                cached_at = float(cached.get("at") or 0)
            except (TypeError, ValueError):
                cached_at = 0.0
            if isinstance(cached.get("offers"), dict):
                cached_offers = cached["offers"]
        fresh = (t - cached_at) < QUEST_OFFER_TTL_SECONDS
        # 逐 NPC 复用（评审 S2）：缓存新鲜时同场每位 NPC 优先用其既存预览链，
        # 仅新到场者现生成、已离场者自然剔除——接走一条不会连带其余预览重掷。
        all_npcs = [c for c in alive if _is_npc(c) and _alive(c, t)]
        offers: Dict[str, Any] = {}
        out: List[Tuple[Character, QuestChain]] = []
        changed = False
        for npc in npcs_here:
            chain = None
            if fresh and npc.id in cached_offers:
                try:
                    chain = QuestChain.model_validate(cached_offers[npc.id])
                except Exception:
                    chain = None
            if chain is None:
                others = [c for c in all_npcs if c.id != npc.id]
                chain = QuestEngine.generate_chain(npc, player, rng=rng, others=others)
                changed = True
            offers[npc.id] = chain.model_dump()
            out.append((npc, chain))
        if changed or set(offers.keys()) != set(cached_offers.keys()):
            try:
                WorldStateRepository.set(key, {"at": t, "offers": offers})
            except Exception:
                pass
        return out

    @staticmethod
    def _drop_offer(player_id: str, npc_id: str) -> None:
        key = _offers_key(player_id)
        try:
            cached = WorldStateRepository.get(key)
            if isinstance(cached, dict) and npc_id in (cached.get("offers") or {}):
                cached["offers"].pop(npc_id, None)
                WorldStateRepository.set(key, cached)
        except Exception:
            pass

    @staticmethod
    def _invalidate_offers(player_id: str) -> None:
        try:
            WorldStateRepository.set(_offers_key(player_id), {"at": 0.0, "offers": {}})
        except Exception:
            pass

    # ---------------- 惰性结算 ----------------
    @staticmethod
    def settle_expired(char: Character, now: Optional[float] = None) -> bool:
        """链过期 → 清链 + 写冷却。返回是否变更（变更时调用方须 save）。"""
        t = now if now is not None else time.time()
        ch = char.active_quest
        if ch and ch.expires_at and t >= ch.expires_at:
            char.active_quest = None
            char.quest_cooldown_until = max(char.quest_cooldown_until, t + QUEST_ACCEPT_COOLDOWN_SECONDS)
            return True
        return False

    @staticmethod
    def current_ring(char: Character) -> Optional[QuestRing]:
        ch = char.active_quest
        if not ch or ch.ring_index >= len(ch.rings):
            return None
        return ch.rings[ch.ring_index]

    # ---------------- 接取 ----------------
    @staticmethod
    def accept(
        char: Character,
        hint: str,
        now: Optional[float] = None,
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if char.status == CharacterStatus.DEAD or char.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，不可再接人间委托。"}
        dirty = QuestEngine.settle_expired(char, t)
        active_count = 1 if char.active_quest else 0
        if active_count >= QUEST_MAX_ACTIVE:
            return {"success": False, "dirty": dirty,
                    "message": "已有一条委托在身，先办完或 /弃委托 再接新的。"}
        if t < char.quest_cooldown_until:
            left = int(char.quest_cooldown_until - t) + 1
            return {"success": False, "dirty": dirty,
                    "message": f"刚了结一桩委托，气息未平，{left} 秒后可再接。"}
        offers = QuestEngine.offers_for(char, now=t, rng=rng)
        if not offers:
            return {"success": False, "dirty": dirty,
                    "message": "此地暂无可委托的修士，先 /同场 看看谁在。"}
        picked: Optional[Tuple[Character, QuestChain]] = None
        h = (hint or "").strip()
        if h.isascii() and h.isdigit():
            idx = int(h)
            if 1 <= idx <= len(offers):
                picked = offers[idx - 1]
        if picked is None and h:
            exact = [o for o in offers if o[0].name == h]
            fuzzy = [o for o in offers if h in o[0].name]
            picked = (exact or fuzzy or [None])[0]
        if picked is None:
            names = "、".join(f"{i + 1}.{npc.name}" for i, (npc, _) in enumerate(offers))
            return {"success": False, "dirty": dirty,
                    "message": f"未找到可接的委托。用 /接委托 <编号或NPC名>，当前可接：{names}。"}
        npc, chain = picked
        # 发布者实时复核：须仍存活且仍与玩家同场（offers 生成后可能已迁跃/陨落）
        fresh = CharacterRepository.get_by_id(npc.id)
        if not _alive(fresh, t) or fresh.location != char.location:
            QuestEngine._invalidate_offers(char.id)
            return {"success": False, "dirty": dirty,
                    "message": f"【{npc.name}】已不在此地，这条委托作罢。用 /委托 刷新看看。"}
        chain.accepted_at = t
        chain.expires_at = t + QUEST_CHAIN_TTL_SECONDS
        chain.ring_index = 0
        char.active_quest = chain
        QuestEngine._drop_offer(char.id, npc.id)
        first = chain.rings[0]
        return {
            "success": True, "dirty": True, "chain": chain,
            "message": (
                f"【接委托】{npc.name} 拱手道：「此事便托付道友了。」\n"
                f"委托链共 {len(chain.rings)} 环 · 全链赏：灵石 {chain.reward_stones} + 功德 {chain.reward_merit}"
                f"（现实 24 小时内办完）\n"
                f"第 1 环【{QUEST_KIND_CN.get(first.kind, first.kind)}】{first.desc}\n"
                f"办妥后找到交付对象当面 /交付。"
            ),
        }

    # ---------------- 交付 ----------------
    @staticmethod
    def deliver(
        char: Character,
        now: Optional[float] = None,
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if char.status == CharacterStatus.DEAD or char.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，委托已随旧世而散。"}
        if QuestEngine.settle_expired(char, t):
            return {"success": False, "dirty": True,
                    "message": "这条委托已过期作废（现实 24 小时未办完），无赏无罚。可用 /委托 再接。"}
        chain = char.active_quest
        if not chain:
            return {"success": False, "message": "眼下无进行中的委托。用 /委托 查看可接委托。"}
        ring = QuestEngine.current_ring(char)
        if ring is None:
            # 脏数据兜底：下标越界视为账目已乱，清链不发奖（奖励只走正常完成路径）
            char.active_quest = None
            char.quest_cooldown_until = max(char.quest_cooldown_until, t + QUEST_ACCEPT_COOLDOWN_SECONDS)
            return {"success": False, "dirty": True, "message": "这条委托账目已乱，天道将其作废（无赏）。"}
        target = CharacterRepository.get_by_id(ring.deliver_npc_id)
        if not _alive(target, t):
            char.active_quest = None
            char.quest_cooldown_until = max(char.quest_cooldown_until, t + QUEST_ACCEPT_COOLDOWN_SECONDS)
            return {"success": False, "dirty": True,
                    "message": f"交付对象【{ring.deliver_npc_name}】已陨落，这条委托作废（无赏无罚）。"}
        if target.location != char.location:
            return {"success": False,
                    "message": f"须当面交付：【{ring.deliver_npc_name}】此刻在【{target.location}】，你身在【{char.location}】。"}
        if ring.kind == "fetch":
            if ring.item_name not in char.inventory:
                return {"success": False,
                        "message": f"行囊中无【{ring.item_name}】，寻得后再来交付（坊市有售，探险亦有掉落）。"}
        elif ring.kind == "slay":
            if ring.progress < ring.need:
                return {"success": False,
                        "message": f"除妖未毕：已成 {ring.progress}/{ring.need} 次探险除妖，再接再厉。"}
        elif ring.kind != "deliver":
            # fail-closed（评审 M1）：未知环种不放行——与下标越界同口径作废清链，
            # 防改档/未来新环种漏接核验时静默推进发奖。
            char.active_quest = None
            char.quest_cooldown_until = max(char.quest_cooldown_until, t + QUEST_ACCEPT_COOLDOWN_SECONDS)
            return {"success": False, "dirty": True,
                    "message": "这条委托的环目天道未识，已作废（无赏无罚）。"}
        # 核验通过：落账本环
        if ring.kind == "fetch":
            char.inventory.remove(ring.item_name)
        chain.ring_index += 1
        done_desc = ring.desc
        # 势力版图（F09）：每环交付成功为本宗在交付地扬名（两处成功出口共用此点，恰计一次）
        try:
            from core.atlas import AtlasEngine

            AtlasEngine.record_activity(char, "quest")
        except Exception:
            pass
        if chain.ring_index < len(chain.rings):
            nxt = chain.rings[chain.ring_index]
            return {
                "success": True, "dirty": True, "advanced": True,
                "message": (
                    f"【交付 · 第 {chain.ring_index}/{len(chain.rings)} 环已成】{done_desc}\n"
                    f"下一环【{QUEST_KIND_CN.get(nxt.kind, nxt.kind)}】{nxt.desc}\n"
                    f"办妥后找到【{nxt.deliver_npc_name}】当面 /交付。"
                ),
            }
        # 全环完成：清链与冷却先落，再发奖（结构性幂等，重复交付只会扑空）
        stones = int(chain.reward_stones)
        merit = int(chain.reward_merit)
        ring_total = len(chain.rings)
        publisher_name = chain.publisher_name
        publisher_id = chain.publisher_id
        char.active_quest = None
        char.quest_cooldown_until = max(char.quest_cooldown_until, t + QUEST_ACCEPT_COOLDOWN_SECONDS)
        char.spirit_stones += stones
        if merit:
            char.karma.add_merit(merit)
        # 著书立说（F11）：整链完成积攒灵感（与发奖同落账段，恰一次）
        try:
            from core.books import INSPIRATION_FROM_QUEST, BookEngine

            BookEngine.gain_inspiration(char, INSPIRATION_FROM_QUEST)
        except Exception:
            pass
        clue_line = ""
        r = rng or random.Random()
        if r.random() < QUEST_ART_CLUE_P:
            for sk in QUEST_ART_CLUE_POOL:
                if sk not in char.skills:
                    char.skills.append(sk)
                    clue_line = f"\n【功法线索】{publisher_name} 临别授你一式【{sk}】，已录入法门（/心法 可装配）。"
                    break
        # 与 agenda 共存：发布者态度 +8（既有口径）+ 世情播报（尽力而为，不炸主流程）
        publisher = CharacterRepository.get_by_id(publisher_id)
        if _alive(publisher, t) and _is_npc(publisher):
            try:
                from core.npc_mind import shift_attitude

                shift_attitude(publisher, char.id, QUEST_ATTITUDE_DELTA, reason="完成委托")
            except Exception:
                pass
        try:
            import core.jianghu as jianghu

            jianghu.append_event(
                kind="quest",
                actor_ids=[char.id],
                actor_names=[char.name],
                target_ids=[publisher_id],
                location=char.location,
                summary=f"【{char.name}】办妥【{publisher_name}】的连环委托，获赏 {stones} 灵石",
                rule_result={"stones": stones, "merit": merit, "rings": ring_total},
                narrative="",
                ref_ids=[char.id, publisher_id],
                source="rule",
            )
        except Exception:
            pass
        return {
            "success": True, "dirty": True, "completed": True,
            "reward_stones": stones, "reward_merit": merit,
            "message": (
                f"【委托达成】{done_desc}\n"
                f"【{publisher_name}】大喜过望，奉上谢仪：灵石 +{stones} · 功德 +{merit}。"
                f"{clue_line}\n（其对你态度转暖；{int(QUEST_ACCEPT_COOLDOWN_SECONDS)} 秒后可再接新委托）"
            ),
        }

    # ---------------- 放弃 ----------------
    @staticmethod
    def abandon(char: Character, now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if char.status == CharacterStatus.DEAD or char.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，委托已随旧世而散。"}
        if QuestEngine.settle_expired(char, t):
            return {"success": False, "dirty": True,
                    "message": "这条委托已过期作废，无需再弃。"}
        if not char.active_quest:
            return {"success": False, "message": "眼下无进行中的委托，无需放弃。"}
        name = char.active_quest.publisher_name
        char.active_quest = None
        char.quest_cooldown_until = max(char.quest_cooldown_until, t + QUEST_ACCEPT_COOLDOWN_SECONDS)
        return {"success": True, "dirty": True,
                "message": f"已弃【{name}】的委托（无惩罚）；{int(QUEST_ACCEPT_COOLDOWN_SECONDS)} 秒后可再接新委托。"}

    # ---------------- 死亡钩子 ----------------
    @staticmethod
    def on_owner_death(char: Character) -> None:
        """委托随旧世而散（与 F01 灵宠 / F06 灵田同口径）：清进行中链，不发奖不惩罚。"""
        char.active_quest = None

    # ---------------- 探险计数钩子 ----------------
    @staticmethod
    def note_adventure_win(char: Character) -> None:
        """探险规则成功时由 AdventureEngine 落账段调用：当前为除妖环则计数（封顶 need）。"""
        ring = QuestEngine.current_ring(char)
        if ring is not None and ring.kind == "slay" and ring.progress < ring.need:
            ring.progress += 1

    # ---------------- 面板 ----------------
    @staticmethod
    def panel_text(char: Character, now: Optional[float] = None, rng: Optional[random.Random] = None) -> str:
        t = now if now is not None else time.time()
        # 惰性结算收引擎内（评审 S1）：直调方也不会看到过期链仍「进行中」；
        # 是否变更由调用方另行 settle_expired 判断并 save（重复 settle 幂等）。
        QuestEngine.settle_expired(char, t)
        chain = char.active_quest
        if chain:
            ring = QuestEngine.current_ring(char)
            left_h = max(0.0, (chain.expires_at - t) / 3600.0)
            lines = [
                f"【委托进行中】发布者：{chain.publisher_name} · 第 {chain.ring_index + 1}/{len(chain.rings)} 环"
                f" · 全链赏 灵石 {chain.reward_stones} + 功德 {chain.reward_merit} · 余 {left_h:.1f} 小时",
            ]
            if ring is not None:
                lines.append(f"当前环【{QUEST_KIND_CN.get(ring.kind, ring.kind)}】{ring.desc}")
                if ring.kind == "slay":
                    lines.append(f"· 除妖进度：{ring.progress}/{ring.need}（探险成功计入）")
                elif ring.kind == "fetch":
                    has = "有" if ring.item_name in char.inventory else "无"
                    lines.append(f"· 寻物核验：行囊中{has}【{ring.item_name}】")
                target = CharacterRepository.get_by_id(ring.deliver_npc_id)
                if not _alive(target, t):
                    lines.append(f"· 交付对象【{ring.deliver_npc_name}】已陨落，/交付 将作废此链（无惩罚）")
                else:
                    lines.append(f"· 交付：找到【{ring.deliver_npc_name}】（此刻在【{target.location}】）当面 /交付")
            lines.append("放弃：/弃委托（无惩罚，了结后有短暂冷却）")
            return "\n".join(lines)
        lines = ["【NPC 委托】同场修士若有事相托，皆列于下（与悬赏板不同：此乃办事跑环，不杀人、不收费）："]
        if t < char.quest_cooldown_until:
            lines.append(f"（刚了结一桩委托，{int(char.quest_cooldown_until - t) + 1} 秒后可再接）")
        offers = QuestEngine.offers_for(char, now=t, rng=rng)
        if not offers:
            lines.append("此地暂无可委托的修士。换个地点 /同场 看看，或先与 NPC /交谈 混个脸熟。")
            return "\n".join(lines)
        for i, (npc, ch) in enumerate(offers, 1):
            first = ch.rings[0] if ch.rings else None
            first_s = f"首环【{QUEST_KIND_CN.get(first.kind, first.kind)}】{first.desc}" if first else ""
            lines.append(
                f"{i}. 【{npc.name}】（{npc.realm.name}）委托 {len(ch.rings)} 环"
                f" · 赏 灵石 {ch.reward_stones} + 功德 {ch.reward_merit}\n   {first_s}"
            )
        lines.append("接取：/接委托 <编号或NPC名>（同时只能持一条链，现实 24 小时内办完）")
        return "\n".join(lines)
