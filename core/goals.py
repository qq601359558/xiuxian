"""
玩家世间目标系统。

既有契约（server/world.py · tests/test_phase1_rules.py）：
  GoalEngine.ensure_goals / add_opportunity / reject
  on_breakthrough_major / sync_progress / format_board / list_for

江湖因果扩展：sync_progress / ensure 时从因果账补齐与世界相关目标（扬名/复仇等）。
AI 只可解释，不直接发放数值。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from config import GOAL_MAX_ACTIVE, GOAL_SOURCES

# 展示用中文
KINDS = {
    "dao": "道途",
    "omen": "机缘",
    "bounty": "悬赏",
    "sect": "宗门",
    "season": "纪元",
    "newbie": "新入",
    "avenge": "复仇",
    "fame": "扬名",
    "survive": "避劫",
    "legacy": "道统",
    # 游戏感第一期（§3.7 契约变更④）：出身短期目标 / 终局命题展示名
    "origin": "出身",
    "fate": "命途",
    # 游戏感第二期（§3.5 契约变更②）：命途章节目标展示名
    "thread": "命途",
}

# 不可拒绝的目标源（§3.7 契约变更③：fate 命题同 dao 口径不可弃；
# 二期 §3.5 契约变更③：thread 章节目标同口径，搁置走线级开关）
NON_REJECTABLE = {"dao", "fate", "thread"}

# 判定式目标源（§3.7）：豁免 7 日过期与 GOAL_MAX_ACTIVE 计数
# 二期 §3.5 契约变更①：新增 thread 源，一期四点契约同等适用
CHECKED_SOURCES = ("origin", "fate", "thread")

SOURCE_TEMPLATES = {
    "dao": ("问道长生", "稳固道基，勤修不辍，境界自会有进。"),
    "newbie": ("初入红尘", "先熟悉坊市与天道规则，活下去才有仙缘。"),
    "season": ("纪元大势", "本纪元周期有限，留意终局前的天象与榜单。"),
}


def _gid(source: str) -> str:
    return f"g_{source}_{uuid.uuid4().hex[:8]}"


def _active_goals(character: Character) -> List[Dict[str, Any]]:
    return [g for g in (character.goals or []) if g.get("status") == "active"]


def _counted_active(character: Character) -> List[Dict[str, Any]]:
    """计入 GOAL_MAX_ACTIVE 的 active 目标（§3.7 契约变更②：
    origin/fate 两源不计入上限计数，也永不被 omen supersede 选中）。"""
    return [
        g for g in _active_goals(character)
        if g.get("source") not in CHECKED_SOURCES
    ]


def _has_source(character: Character, source: str) -> bool:
    return any(g.get("source") == source for g in _active_goals(character))


class GoalEngine:
    """六类源目标引擎 + 江湖因果投影"""

    @staticmethod
    def ensure_goals(character: Character) -> List[Dict[str, Any]]:
        if not character:
            return []
        if not isinstance(character.goals, list):
            character.goals = []
        now = time.time()
        # 过期清理（7 天）（§3.7 契约变更①：origin/fate 两源豁免，
        # 其期限由 check 的 deadline 独立管辖）
        for g in character.goals:
            if g.get("source") in CHECKED_SOURCES:
                continue
            if g.get("status") == "active" and now - float(g.get("created_at") or 0) > 7 * 86400:
                g["status"] = "expired"

        def _add(source: str, title: str, detail: str, **extra) -> None:
            active_n = len(_counted_active(character))
            # 基础三类不限满额挤占；扩展类留出 add_opportunity 余量
            base = source in ("dao", "newbie", "season")
            limit = GOAL_MAX_ACTIVE if base else max(4, GOAL_MAX_ACTIVE - 2)
            if active_n >= limit:
                return
            if _has_source(character, source) and source not in ("omen",):
                return
            character.goals.append({
                "id": _gid(source),
                "source": source,
                "title": title,
                "detail": detail,
                "status": "active",
                "progress": 0,
                "created_at": now,
                **extra,
            })

        # 基础三类（测试硬约束）
        _add("dao", *SOURCE_TEMPLATES["dao"])
        _add("newbie", *SOURCE_TEMPLATES["newbie"])
        _add("season", *SOURCE_TEMPLATES["season"])

        active_n = len(_counted_active(character))
        if active_n < 5:
            if character.sect:
                _add("sect", f"效力【{character.sect}】", "完成日环、上交贡献或除凶，为宗门立功。", target=character.sect)
            else:
                _add("sect", "寻一门庭", "散修无依，可择正魔宗门拜入。")

        if character.karma.is_blood_marked():
            _add("avenge", "血煞缠身", "身负血煞，宜避祸或主动除凶。")

        # 江湖投影：近日因果（不占满，给秘境机缘留位）
        try:
            import core.jianghu as jianghu

            active_n = len(_counted_active(character))
            if active_n < 5:
                mine = jianghu.project_related(character.id, limit=6)
                if not _has_source(character, "fame"):
                    _add(
                        "fame",
                        "扬名立万",
                        "江湖多事，宜在斗法/宗门/除凶中留下名号。",
                        progress=min(2, len(mine)),
                    )
            active_n = len(_counted_active(character))
            if active_n < GOAL_MAX_ACTIVE:
                for e in jianghu.list_recent(limit=6):
                    if "夺" in (e.get("summary") or "") or e.get("kind") in ("npc_agenda",):
                        if not _has_source(character, "omen"):
                            _add("omen", "机缘未远", f"坊间传闻：{(e.get('summary') or '')[:60]}", ref=e.get("id", ""))
                        break
        except Exception:
            pass

        return character.goals

    @staticmethod
    def add_opportunity(character: Character, title: str, detail: str) -> Dict[str, Any]:
        """外部事件挂接机缘目标（秘境等）。机缘类允许超基础配额，上限仍为 GOAL_MAX_ACTIVE。"""
        GoalEngine.ensure_goals(character)
        # 若 ensure 已写入 omen（江湖传闻），先降其优先级为 superseded，保证外部机缘可挂接
        # （§3.7 契约变更②：满额口径不计 origin/fate，supersede 只选 omen 源）
        if len(_counted_active(character)) >= GOAL_MAX_ACTIVE:
            for g in character.goals or []:
                if g.get("status") == "active" and g.get("source") == "omen":
                    g["status"] = "superseded"
                    break
        if len(_counted_active(character)) >= GOAL_MAX_ACTIVE:
            return {"success": False, "error": "世间目标已满，可先 /目标 处理。"}
        goal = {
            "id": _gid("omen"),
            "source": "omen",
            "title": str(title)[:40],
            "detail": str(detail)[:200],
            "status": "active",
            "progress": 0,
            "created_at": time.time(),
        }
        character.goals.append(goal)
        return {"success": True, "goal": goal}

    @staticmethod
    def reject(character: Character, goal_id: str) -> Dict[str, Any]:
        for g in character.goals or []:
            if g.get("id") != goal_id:
                continue
            if g.get("source") in NON_REJECTABLE:
                return {"success": False, "error": "道途目标不可弃。"}
            if g.get("status") != "active":
                return {"success": False, "error": "该目标非进行中。"}
            g["status"] = "rejected"
            g["done_at"] = time.time()
            return {"success": True, "goal": g, "message": f"已放下【{g.get('title')}】。"}
        return {"success": False, "error": "未找到该目标。"}

    @staticmethod
    def complete(character: Character, goal_id: str, reason: str = "") -> Optional[Dict[str, Any]]:
        for g in character.goals or []:
            if g.get("id") == goal_id and g.get("status") == "active":
                g["status"] = "done"
                g["done_at"] = time.time()
                g["done_reason"] = reason[:120]
                return g
        return None

    # ---------------- 判定式目标（game-feel-phase1 §3.7） ----------------
    @staticmethod
    def add_checked_goal(
        character: Character,
        *,
        source: str,
        title: str,
        detail: str,
        check: Dict[str, Any],
        deadline_days: Optional[float] = None,
        now: Optional[float] = None,
        instance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """挂一条 check 判定式目标（origin 短期 / fate 命题 / thread 章节）。

        幂等键（game-feel-phase2 §2.2 写死）：四元组
        (source, check.kind, check.ref, check.instance)，缺失的
        ref/instance 一律以 "" 归一后比较——存量无 instance 目标与
        同样无 instance 的新目标仍互斥（一期行为逐字不变），与带
        instance 的新目标不互斥（二期章节目标可并存）。
        instance 只参与幂等与章节派生映射，求值器不读它。
        """
        t = now if now is not None else time.time()
        if not isinstance(character.goals, list):
            character.goals = []
        chk = dict(check or {})
        if instance is not None:
            chk["instance"] = instance
        if deadline_days is not None:
            chk.setdefault("deadline_days", deadline_days)
        for g in character.goals:
            if g.get("status") != "active" or g.get("source") != source:
                continue
            gc = g.get("check") or {}
            if (
                gc.get("kind") == chk.get("kind")
                and str(gc.get("ref") or "") == str(chk.get("ref") or "")
                and str(gc.get("instance") or "") == str(chk.get("instance") or "")
            ):
                return g
        from config import SECONDS_PER_GAME_DAY

        goal = {
            "id": _gid(source),
            "source": source,
            "title": str(title)[:60],
            "detail": str(detail)[:200],
            "status": "active",
            "progress": 0,
            "created_at": t,
            "tier": "short" if source == "origin" else "final",
            "check": chk,
            "deadline_at": (
                t + float(deadline_days) * SECONDS_PER_GAME_DAY
                if deadline_days is not None else 0.0
            ),
        }
        character.goals.append(goal)
        return goal

    @staticmethod
    def evaluate_checked_goals(
        character: Character, now: Optional[float] = None, *, final: bool = False,
    ) -> List[Dict[str, Any]]:
        """判定式求值器（§3.7 口径 K3）：纯读既有账 + 只改入参 char 的
        goals 项 status，从不自行落盘。返回本轮新翻转（done/failed）的项。

        求值点只有 E1 登录拼装 / E2 诺言终态 / E3 突破成功 / E4 态度移位
        （仅 attitude 类，见 evaluate_attitude_goals）/ E5 死亡终判
        （final=True）/ E6 sync_progress 尾部，禁止新增 tick 扫描。
        """
        t = now if now is not None else time.time()
        flipped: List[Dict[str, Any]] = []
        # 二期 §3.9：搁置中的主线，其章节目标跳过求值与到期判定
        # （恢复时 deadline 顺延，见 FateThreadEngine.resume_thread）。
        shelved_thread_ids: set = set()
        if any(
            g.get("source") == "thread" and g.get("status") == "active"
            for g in (character.goals or [])
        ):
            try:
                from storage.db import FateThreadRepository

                shelved_thread_ids = {
                    th.id for th in FateThreadRepository.list_by_player(character.id)
                    if th.status == "shelved"
                }
            except Exception:
                shelved_thread_ids = set()
        for g in list(character.goals or []):
            if g.get("status") != "active" or g.get("source") not in CHECKED_SOURCES:
                continue
            check = g.get("check") or {}
            kind = check.get("kind")
            if not kind:
                continue
            if g.get("source") == "thread" and shelved_thread_ids:
                _inst = str(check.get("instance") or "")
                _tid = _inst.rsplit(":", 1)[0] if ":" in _inst else ""
                if _tid in shelved_thread_ids:
                    continue
            outcome = GoalEngine._eval_check(character, check, t, final=final)
            if outcome == "done":
                g["status"] = "done"
                g["done_at"] = t
                g["done_reason"] = "判定式达成"
                flipped.append(g)
            elif outcome == "failed":
                g["status"] = "failed"
                g["done_at"] = t
                g["done_reason"] = "判定式未成"
                flipped.append(g)
            else:
                deadline_at = float(g.get("deadline_at") or 0.0)
                if deadline_at and t > deadline_at:
                    g["status"] = "failed"
                    g["done_at"] = t
                    g["done_reason"] = "到期未达成"
                    flipped.append(g)
        return flipped

    @staticmethod
    def evaluate_attitude_goals(
        character: Character, now: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """E4 专用：只求值 npc_attitude_at_least 类（态度移位点）。"""
        t = now if now is not None else time.time()
        flipped: List[Dict[str, Any]] = []
        # 二期 §3.9（评审 M-1 销账）：搁置中的主线章节目标在 E4 同样跳过
        # 求值——与 evaluate_checked_goals 同口径（按本角色 list_by_player）。
        shelved_thread_ids: set = set()
        if any(
            g.get("source") == "thread" and g.get("status") == "active"
            for g in (character.goals or [])
        ):
            try:
                from storage.db import FateThreadRepository

                shelved_thread_ids = {
                    th.id for th in FateThreadRepository.list_by_player(character.id)
                    if th.status == "shelved"
                }
            except Exception:
                shelved_thread_ids = set()
        for g in list(character.goals or []):
            if g.get("status") != "active" or g.get("source") not in CHECKED_SOURCES:
                continue
            check = g.get("check") or {}
            if check.get("kind") != "npc_attitude_at_least":
                continue
            if g.get("source") == "thread" and shelved_thread_ids:
                _inst = str(check.get("instance") or "")
                _tid = _inst.rsplit(":", 1)[0] if ":" in _inst else ""
                if _tid in shelved_thread_ids:
                    continue
            if GoalEngine._eval_check(character, check, t, final=False) == "done":
                g["status"] = "done"
                g["done_at"] = t
                g["done_reason"] = "判定式达成"
                flipped.append(g)
        return flipped

    @staticmethod
    def _eval_check(
        character: Character, check: Dict[str, Any], now: float, *, final: bool,
    ) -> Optional[str]:
        """单条 check 求值：返回 "done" / "failed" / None(pending)。

        failed 只由 promise_settled 遇 BROKEN/DISSOLVED 产生（不等到期）；
        到期 failed 由 evaluate_checked_goals 的 deadline 分支统一处理。
        """
        kind = check.get("kind")
        try:
            if kind == "promise_settled":
                from core.promises import PromiseEngine

                for p in PromiseEngine._involving(character.id):
                    if p.id != check.get("ref"):
                        continue
                    st = p.status.value if hasattr(p.status, "value") else str(p.status)
                    if st == "KEPT":
                        return "done"
                    if st in ("BROKEN", "DISSOLVED"):
                        return "failed"
                    return None
                return None
            if kind == "stones_at_least":
                return "done" if character.spirit_stones >= int(check.get("amount") or 0) else None
            if kind == "realm_at_least":
                tier = int(check.get("tier") or 0)
                sub = check.get("sub")
                if character.realm.tier > tier:
                    return "done"
                if character.realm.tier == tier:
                    if sub is None or character.realm.sub_tier >= int(sub):
                        return "done"
                return None
            if kind == "npc_attitude_at_least":
                from storage.db import CharacterRepository
                from core.npc_mind import attitude_toward

                npc = CharacterRepository.get_by_id(str(check.get("npc_id") or ""))
                if npc is None:
                    return None
                # 死亡终判特例（仅 E5）：目标 NPC 已死 → 恩怨两消判 done
                if final and (
                    npc.status == CharacterStatus.DEAD or npc.lifespan.is_dead(now)
                ):
                    return "done"
                value = int(attitude_toward(npc, character.id).get("value") or 0)
                return "done" if value >= int(check.get("value") or 0) else None
            if kind == "item_in_bag":
                ref = str(check.get("item_ref") or "")
                if ref and GoalEngine._bag_has(character, ref):
                    return "done"
                return None
            if kind == "item_in_bag_at_death":
                if not final:
                    return None  # 生前恒 pending，只在 E5 终判求值
                ref = str(check.get("item_ref") or "")
                if ref and GoalEngine._bag_has(character, ref):
                    return "done"
                return None
            if kind == "sect_joined":
                ref = str(check.get("ref") or "")
                if character.sect and (not ref or character.sect == ref):
                    return "done"
                return None
            # ---- 二期新 kind（§3.5）：只读既有账，AI 零参与判定 ----
            if kind == "visit_location":
                ref = str(check.get("ref") or "")
                if not ref:
                    return None
                # 块一复测再修（B1-4）：取线口径与 FateThreadEngine._active_thread
                # 一致（最新一条 active/shelved 线）。此前此处自扫 list 首条，
                # 玩家搁置旧线另开新线时，求值会读旧线的 visited——旧线到过
                # 的地点会让新线章节误成，或新线到过的地点因读旧线而不成。
                # 单线时与旧口径完全等价。
                from core.fate_thread import FateThreadEngine

                thread = FateThreadEngine._active_thread(character.id)
                if thread is None:
                    return None
                # 块一复测残余（出生地同场）：visited 只由 /go 落点
                # record_visit 写入，出生地从未落账——目标恰在出生地时
                # 原地谈完也永远差「到访」一半，须离场再 /go 返回才成
                # （simr2b 实测）。修复取 C 口径（纯求值、零写入）：
                # 「角色当前所在地 == ref」视为已到访，与 visited 命中
                # 取或。visited 全库核查：唯一写入者 record_visit
                # （/go 落点）、唯一逻辑读者即此处，无展示/其他逻辑
                # 消费，故不回写 visited、不污染其落点记录语义，对
                # 既有账改动为零；已到访后离场者仍凭 visited 命中，
                # 旧行为不变。带 npc_id 时下方交谈一半仍不可缺。
                if ref not in (thread.visited or []) and str(
                    getattr(character, "location", "") or ""
                ) != ref:
                    return None
                npc_id = str(check.get("npc_id") or "")
                if npc_id:
                    from storage.db import CharacterRepository

                    npc = CharacterRepository.get_by_id(npc_id)
                    if npc is None or npc.location != ref:
                        return None
                    # 块一复测再修（B1-4）：带 npc_id 的寻访章（命途第一章）
                    # 不能只凭“到过该地”就成——否则玩家抵达当场章即成，
                    # 目标卡的「就在此处 + 上前交谈」永不可达（见复测 B/D 号）。
                    # 章题本就是「有些话须当面说清」：须与该 NPC 有过一轮
                    # 交谈（会话记录含双方发言，或已落账的交谈记忆）才成。
                    # 无 npc_id 的纯地点访问（兜底分支）保持旧口径。
                    if not GoalEngine._talked_with_npc(character, npc):
                        return None
                return "done"
            if kind == "promise_kept_count":
                from core.promises import PromiseEngine

                kept = 0
                for p in PromiseEngine._involving(character.id):
                    st = p.status.value if hasattr(p.status, "value") else str(p.status)
                    if st == "KEPT":
                        kept += 1
                return "done" if kept >= int(check.get("count") or 1) else None
            if kind == "chain_resolved":
                from storage.db import KarmaChainRepository

                terminal = ("resolved", "dissipated")
                ref = str(check.get("ref") or "")
                if ref:
                    one = KarmaChainRepository.get(ref)
                    chains = [one] if one is not None else []
                else:
                    npc_id = str(check.get("npc_id") or "")
                    chains = [
                        c for c in KarmaChainRepository.list_by_player(character.id)
                        if not npc_id or c.counterparty_id == npc_id
                    ]
                outcome_req = str(check.get("outcome") or "any")
                for c in chains:
                    if c.status not in terminal:
                        continue
                    if outcome_req in ("en", "chou") and c.kind != outcome_req:
                        continue
                    return "done"
                return None
            if kind == "thread_climax":
                # 只许出现在 fate 命题目标上；章节派生后才可能 done
                # （调用序由 FateThreadEngine.evaluate_for 写死，§3.5）。
                from storage.db import FateThreadRepository

                th = FateThreadRepository.get_by_id(str(check.get("ref") or ""))
                if (
                    th is not None and len(th.chapters or []) > 4
                    and (th.chapters[4] or {}).get("status") == "done"
                ):
                    return "done"
                return None
        except Exception:
            return None
        return None

    @staticmethod
    def _bag_has(character: Character, item_ref: str) -> bool:
        names = list(character.inventory or [])
        for it in (character.items or []):
            nm = getattr(it, "name", "")
            if nm:
                names.append(nm)
        return any(item_ref in (n or "") for n in names)

    @staticmethod
    def _talked_with_npc(character: Character, npc: Character) -> bool:
        """是否与该 NPC 有过一轮交谈（块一复测再修 B1-4 的判定信号）。

        三路账，任一命中即算：① 进行中/已结束的交谈会话记录里
        同时出现玩家与该 NPC 的发言（open_session 建会话、player_say
        记玩家句、apply_npc_reply 记 NPC 句；会话关闭后记录仍保留）；
        ② 已落账的交谈记忆摘要（close_session 写，换会话也不丢）；
        ③ M4 按 (玩家, NPC) 对持久留存的「已完成一轮」标记
        （npc_chat.has_talked_pair，apply_npc_reply 落账时写入，
        不被切换会话的单槽覆盖——①的单槽缺陷由此路补齐）。
        只读，不写任何账；任一读账失败按“未谈过”计（pending，不误判）。
        """
        try:
            from core import npc_chat

            rec = (npc_chat._load_all() or {}).get(character.id) or {}
            if rec.get("npc_id") == npc.id:
                msgs = rec.get("messages") or []
                who = {str(m.get("who") or "") for m in msgs}
                if character.name in who and npc.name in who:
                    return True
        except Exception:
            pass
        try:
            from core.npc_chat import _load_memory, _mem_key

            mem = _load_memory() or {}
            row = mem.get(_mem_key(character.id, npc.id)) or {}
            if row.get("summaries"):
                return True
        except Exception:
            pass
        try:
            from core.npc_chat import has_talked_pair

            if has_talked_pair(character.id, npc.id):
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def on_breakthrough_major(character: Character) -> None:
        """大境界突破：刷新道途/纪元目标"""
        GoalEngine.ensure_goals(character)
        now = time.time()
        for g in character.goals or []:
            if g.get("status") == "active" and g.get("source") in ("dao", "season"):
                g["status"] = "done"
                g["done_at"] = now
                g["done_reason"] = f"突破至 {character.realm.name}"
        # 重新生成
        for g in character.goals or []:
            if g.get("status") == "active" and g.get("source") in ("dao", "season"):
                g["status"] = "superseded"
        GoalEngine.ensure_goals(character)

    @staticmethod
    def sync_progress(character: Character) -> List[Dict[str, Any]]:
        """按规则状态刷新进度；尝试完成。返回本次完成列表。"""
        GoalEngine.ensure_goals(character)
        completed: List[Dict[str, Any]] = []
        now = time.time()
        for g in list(character.goals or []):
            if g.get("status") != "active":
                continue
            src = g.get("source")
            # 道途：有修为增长则进度缓慢前进
            if src == "dao":
                try:
                    g["progress"] = int(character.realm.tier)
                except Exception:
                    pass
            if src == "fame":
                try:
                    import core.jianghu as jianghu
                    mine = [
                        e for e in jianghu.project_related(character.id, limit=10)
                        if character.id in (e.get("actor_ids") or [])
                    ]
                    g["progress"] = min(3, len(mine))
                    if len(mine) >= 2:
                        hit = GoalEngine.complete(character, g["id"], reason="江湖已有名号痕迹")
                        if hit:
                            completed.append(hit)
                except Exception:
                    pass
            if src == "survive" and not character.karma.is_blood_marked():
                hit = GoalEngine.complete(character, g["id"], reason="血煞已消")
                if hit:
                    completed.append(hit)
            if src == "newbie":
                try:
                    if not character.is_newbie_protected(now):
                        # 入世已久仍在则进度打满但不强制完成
                        g["progress"] = 1
                except Exception:
                    pass
        # E6（§3.7）：sync_progress 尾部全量求值判定式目标（兜底点）
        try:
            for g in GoalEngine.evaluate_checked_goals(character, now):
                if g.get("status") == "done":
                    completed.append(g)
        except Exception:
            pass
        return completed

    @staticmethod
    def list_for(character: Character) -> List[Dict[str, Any]]:
        return [g for g in (character.goals or []) if g.get("status") == "active"]

    @staticmethod
    def format_board(character: Character) -> str:
        items = GoalEngine.list_for(character)
        if not items:
            return "暂无世间目标。可 /世情 观察江湖，或 /近况 查看。"
        lines = [f"=== 世间目标（{len(items)}/{GOAL_MAX_ACTIVE}）· {character.name} ==="]
        for g in items:
            kn = KINDS.get(g.get("source", ""), g.get("source", ""))
            prog = g.get("progress") or 0
            lines.append(f"  · 【{kn}】{g.get('title')} — {g.get('detail','')}（进度 {prog}）")
        return "\n".join(lines)


# ---------- 兼容 briefing / CLI 的函数式接口 ----------

def ensure_goals(character: Character) -> List[Dict[str, Any]]:
    return GoalEngine.ensure_goals(character)


def format_goals(character: Character) -> str:
    return GoalEngine.format_board(character)


def evaluate_and_complete(character: Character) -> List[Dict[str, Any]]:
    return GoalEngine.sync_progress(character)


def add_checked_goal(character: Character, **kwargs) -> Dict[str, Any]:
    return GoalEngine.add_checked_goal(character, **kwargs)


def evaluate_checked_goals(
    character: Character, now: Optional[float] = None, *, final: bool = False,
) -> List[Dict[str, Any]]:
    return GoalEngine.evaluate_checked_goals(character, now, final=final)


def get_goals(character_id: str) -> List[Dict[str, Any]]:
    """按 id 读目标（近况等场景）。"""
    try:
        from storage.db import CharacterRepository
        c = CharacterRepository.get_by_id(character_id)
        if not c:
            return []
        return list(c.goals or [])
    except Exception:
        return []
