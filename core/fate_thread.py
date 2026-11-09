"""
命途主线全量（game-feel-phase2 §3）+ 世仇选人（§4）。

口径要点（Spec 写死）：
- 每角色同时 1 条 active 主线，6 章骨架（立命/经营×2/冲突/高潮/暮年）；
  章节状态派生自其 checked goal 的 status（单一事实源 = goals 求值器，
  本引擎只做绑定、激活与派生，不做第二套判定，§3.5 K2）。
- 种子六级优先级：未竟 > 世仇 > 影子 > 血仇 > 宗门 > 出身（§3.3）；
  未竟之志与终局命题「二居其一」。
- 推进只搭既有事件点（§3.6 T1–T6），零 tick 扫描；AI 零参与判定。
- 本模块自身不产生任何数值（A5）：写操作只有 fate_threads 仓储与
  goals 挂载，不 import 任何钱包/灵石/修为写入口。
- config 常量按 Spec §3.2 数值写死于本模块（FATE_THREAD_*），
  避免跨岗改 config.py。
"""
from __future__ import annotations

import copy
import time
import uuid
import zlib
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import WORLD_LOCATIONS
from core.models import Character, CharacterStatus

# ---- Spec §3.2 新常量（数值写死） ----
FATE_THREAD_MAX_ACTIVE = 1
FATE_CHAPTER_WINDOW_DAYS = {"setup": 15, "manage": 20, "conflict": 21, "climax": 30, "finale": 0}
FATE_THREAD_SKELETON = 6

SEED_SOURCES = ("unfinished", "vendetta", "karma_shadow", "blood_feud", "sect", "origin")
CHAPTER_KINDS = ("visit", "feud", "treasure", "choice", "sect", "climax", "finale")
CHAPTER_GROUPS = ["setup", "manage", "manage", "conflict", "climax", "finale"]
CHAPTER_TIERS = ["short", "short", "mid", "mid", "final", "final"]
SEALED_STATUSES = ("completed", "broken", "inherited")

_SEED_TITLES = {
    "unfinished": "未竟之志",
    "vendetta": "世仇雪恨",
    "karma_shadow": "旧影重逢",
    "blood_feud": "血仇未了",
    "sect": "宗门风云",
    "origin": "出身牵命",
}

# 章节标题/目标模板族（每 kind ≥2 条，确定性选句沿一期 crc32 先例）
_CHAPTER_TEMPLATES: Dict[str, List[Tuple[str, str]]] = {
    "visit": [
        ("去见那个人", "前往{npc}所在之地，当面照一照这一世的因果。"),
        ("千里访旧", "动身去寻{npc}，有些话须当面说清。"),
    ],
    "feud": [
        ("旧账初鸣", "与{npc}的旧账已经摆上台面，先去探一探虚实。"),
        ("恩怨有头", "血债有头，冤家有主——先找到{npc}。"),
    ],
    "treasure": [
        ("寻一份立身之资", "经营一世，先寻一份能傍身的机缘与资财。"),
        ("山中访宝", "听闻近处有宝光隐现，去碰一碰运气。"),
    ],
    "choice": [
        ("十字路口", "一桩牵连多方的事将至，届时须亲手做出抉择。"),
        ("两难之局", "进退之间，须以一诺或一链定下取舍。"),
    ],
    "sect": [
        ("山门内外", "宗门之事已牵到你身上，先去把来龙去脉看清。"),
        ("同门之谊", "宗门风云渐起，去见一见牵涉其中的人。"),
    ],
    "climax": [
        ("决战之时", "与{npc}的这一笔账，到了当面了结的时候。"),
        ("高潮决算", "所有线索汇于一处，成败在此一举。"),
    ],
    "finale": [
        ("暮年回望", "走到这一世的尽头前，把该了的都了了吧。"),
        ("终局之命", "终局命题高悬，成败由这一世的行止裁决。"),
    ],
}

# 未成章 check.kind → 命题 kind 映射（§3.8：与 legacy._CHECK_TO_PROP_KIND
# 同源口径 + thread 专属两项 thread_climax/chain_resolved → foe_reckoning）
_CHECK_TO_PROP_KIND: Dict[str, str] = {
    "promise_settled": "debt_clear",
    "promise_kept_count": "debt_clear",
    "npc_attitude_at_least": "foe_reckoning",
    "item_in_bag_at_death": "lost_relic",
    "item_in_bag": "lost_relic",
    "stones_at_least": "family_revive",
    "sect_joined": "sect_inner",
    "realm_at_least": "stand_firm",
    "visit_location": "stand_firm",
    "chain_resolved": "foe_reckoning",
    "thread_climax": "foe_reckoning",
}


class FateThread(BaseModel):
    """命途主线一世一行（§3.2 数据模型写死）。"""

    id: str
    player_id: str = ""
    user_id: str = ""
    life_no: int = 1
    status: str = "active"  # active|shelved|completed|broken|inherited
    seed_source: str = "origin"
    seed_ref: str = ""
    seed_npc_id: str = ""
    title: str = ""
    antagonist_npc_id: str = ""
    antagonist_name: str = ""
    patron_npc_id: str = ""
    patron_name: str = ""
    origin: Dict[str, Any] = Field(default_factory=dict)
    final_proposition: Dict[str, Any] = Field(default_factory=dict)
    chapters: List[Dict[str, Any]] = Field(default_factory=list)
    current_chapter: int = 0
    signature: str = ""
    signature_forced: bool = False
    visited: List[str] = Field(default_factory=list)
    shelved_at: float = 0.0
    created_at: float = 0.0
    sealed_at: float = 0.0
    unfinished_note: str = ""


def _repo():
    from storage.db import FateThreadRepository

    return FateThreadRepository


def _char_by_id(char_id: str) -> Optional[Character]:
    if not char_id:
        return None
    try:
        from storage.db import CharacterRepository

        return CharacterRepository.get_by_id(char_id)
    except Exception:
        return None


def _alive(c: Optional[Character], now: float) -> bool:
    return bool(c) and c.status != CharacterStatus.DEAD and not c.lifespan.is_dead(now)


def _is_npc_char(c: Optional[Character]) -> bool:
    if c is None:
        return False
    uid = str(c.user_id or "")
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def _new_thread_id() -> str:
    return f"ft_{uuid.uuid4().hex[:12]}"


class FateThreadEngine:
    """命途主线引擎：种子扫描 / 章节绑定派生 / 搁置 / 封存 / 世仇选人。"""

    # ---------------- 基础查询 ----------------
    @staticmethod
    def get_for_player(player_id: str) -> Optional[FateThread]:
        """最新一条线（未封存优先的呈现口径由调用方按 status 判读）。"""
        try:
            mine = _repo().list_by_player(player_id)
        except Exception:
            return None
        if not mine:
            return None
        for th in reversed(mine):
            if th.status in ("active", "shelved"):
                return th
        return mine[-1]

    @staticmethod
    def _active_thread(player_id: str) -> Optional[FateThread]:
        try:
            mine = _repo().list_by_player(player_id)
        except Exception:
            return None
        for th in reversed(mine):
            if th.status in ("active", "shelved"):
                return th
        return None

    # ---------------- 导演门禁（§3.3，函数与测试先行） ----------------
    @staticmethod
    def validate_seed_hint(hint: Any) -> Optional[Dict[str, Any]]:
        """外部种子建议校验：只许 {seed_source, npc_id, location,
        chapter_kind} 四键，数值类键按 DIRECTOR_STRIP_EFFECT_KEYS 口径
        剥离丢弃；npc_id 不在册 / location 不在 WORLD_LOCATIONS /
        取值不在合法集合者整条拒绝（返回 None）。"""
        if not isinstance(hint, dict):
            return None
        out: Dict[str, Any] = {}
        if "seed_source" in hint:
            if hint.get("seed_source") not in SEED_SOURCES:
                return None
            out["seed_source"] = hint["seed_source"]
        if hint.get("npc_id"):
            nid = str(hint["npc_id"])
            ok = False
            try:
                from core.npc_roster import ROSTER

                ok = any(row.get("uid") == nid for row in ROSTER)
            except Exception:
                ok = False
            if not ok:
                ok = _char_by_id(nid) is not None
            if not ok:
                try:
                    from storage.db import CharacterRepository

                    ok = CharacterRepository.get_by_user_id(nid) is not None
                except Exception:
                    ok = False
            if not ok:
                return None
            out["npc_id"] = nid
        if hint.get("location"):
            if str(hint["location"]) not in WORLD_LOCATIONS:
                return None
            out["location"] = str(hint["location"])
        if "chapter_kind" in hint:
            if hint.get("chapter_kind") not in CHAPTER_KINDS:
                return None
            out["chapter_kind"] = hint["chapter_kind"]
        return out

    # ---------------- 种子扫描（§3.3 六级优先级） ----------------
    @staticmethod
    def _unfinished_rebindable(char: Character, unfinished: Dict[str, Any]) -> bool:
        """未竟之志可否重绑定为章节判定式（§3.3 二居其一判定）。"""
        if not unfinished:
            return False
        kind = str(unfinished.get("kind") or "")
        check = unfinished.get("check") or {}
        if kind == "debt_clear":
            if (getattr(char, "origin", None) or {}).get("debt"):
                return True
            try:
                from core.promises import TERMINAL_STATUSES, PromiseEngine

                for p in PromiseEngine._involving(char.id):
                    st = p.status.value if hasattr(p.status, "value") else str(p.status)
                    if p.kind == "debt" and st not in TERMINAL_STATUSES:
                        return True
            except Exception:
                pass
            return False
        if kind == "foe_reckoning":
            npc_id = str(check.get("npc_id") or "")
            if npc_id and _char_by_id(npc_id) is not None:
                return True
            rels = (getattr(char, "origin", None) or {}).get("relations") or []
            return any(r.get("role") == "foe" for r in rels)
        if kind in ("lost_relic", "family_revive", "sect_inner", "stand_firm"):
            return True
        return str(check.get("kind") or "") in (
            "visit_location", "promise_kept_count", "chain_resolved",
            "stones_at_least", "realm_at_least", "sect_joined",
            "item_in_bag", "npc_attitude_at_least",
        )

    @staticmethod
    def _scan_seed(char: Character, account, now: float) -> Dict[str, Any]:
        traces = list(getattr(account, "traces", None) or []) if account is not None else []
        last = traces[-1] if traces else None
        unfinished: Dict[str, Any] = (
            dict(getattr(last, "unfinished_prop", None) or {}) if last else {})
        rebindable = FateThreadEngine._unfinished_rebindable(char, unfinished)
        origin = getattr(char, "origin", None) or {}
        rels = origin.get("relations") or []

        def rel_npc(role: str) -> Tuple[str, str]:
            r = next((x for x in rels if x.get("role") == role), None)
            return (str(r["npc_id"]), str(r["npc_name"])) if r else ("", "")

        def done(source, ref, seed_npc_id, antagonist, patron):
            return {
                "seed_source": source, "seed_ref": str(ref or ""),
                "seed_npc_id": seed_npc_id or antagonist[0] or patron[0],
                "antagonist": antagonist, "patron": patron,
                "unfinished": unfinished, "unfinished_rebindable": rebindable,
            }

        # P0 未竟之志（可重绑 → 占种子位）
        if rebindable:
            npc_id = str((unfinished.get("check") or {}).get("npc_id") or "")
            ant: Tuple[str, str] = ("", "")
            if npc_id:
                c = _char_by_id(npc_id)
                ant = (npc_id, c.name if c else "")
            if not ant[0]:
                ant = rel_npc("foe")
            patron = rel_npc("kin")
            if patron[0] == ant[0]:
                patron = ("", "")
            ref = str((unfinished.get("check") or {}).get("ref") or npc_id or "")
            return done("unfinished", ref, npc_id, ant, patron)
        # P1 世仇（出身 foe 名额中的 vendetta 条目为单一事实源，§4.3）
        for r in rels:
            if r.get("vendetta"):
                ant = (str(r.get("npc_id") or ""), str(r.get("npc_name") or ""))
                return done("vendetta", ant[0], ant[0], ant, ("", ""))
        # P2 因果影子最强者（并列取列表序首位；NPC 须在世）
        if last and (getattr(last, "shadow", None) or []):
            top = None
            for e in last.shadow:
                if top is None or abs(int(e.value)) > abs(int(top.value)):
                    top = e
            if top is not None:
                npc = _char_by_id(top.npc_id)
                if _alive(npc, now):
                    pair = (top.npc_id, top.npc_name)
                    if int(top.value) < 0:
                        return done("karma_shadow", top.npc_id, top.npc_id, pair, ("", ""))
                    return done("karma_shadow", top.npc_id, top.npc_id, ("", ""), pair)
        # P3 本世血仇链（active/fermenting 中 created_at 最新）
        try:
            from storage.db import KarmaChainRepository

            xue = [
                c for c in KarmaChainRepository.list_by_player(char.id)
                if c.kind == "xue" and c.status in ("latent", "fermenting")
            ]
            if xue:
                ch = max(xue, key=lambda c: c.created_at)
                ant = (ch.counterparty_id, ch.counterparty_name)
                return done("blood_feud", ch.id, ch.counterparty_id, ant, ("", ""))
        except Exception:
            pass
        # P4 宗门（导演指令 / 世界弧只读已落账者）
        try:
            from core.world_director import active_directives

            directives = sorted(
                active_directives() or [],
                key=lambda d: float(d.get("updated_at") or d.get("created_at") or 0),
                reverse=True,
            )
            for d in directives:
                if d.get("type") != "sect_tension":
                    continue
                eff = d.get("effects") or {}
                sects = {str(eff.get("sect_a") or ""), str(eff.get("sect_b") or ""),
                         str(d.get("sect") or "")}
                if (char.sect and char.sect in sects) or (
                    d.get("location") and d.get("location") == char.location
                ):
                    ant_id = str(d.get("npc_id") or eff.get("npc_id") or "")
                    ant_c = _char_by_id(ant_id)
                    ant = (ant_id, ant_c.name if ant_c else "") if ant_id else ("", "")
                    return done("sect", d.get("id") or "", ant_id, ant,
                                FateThreadEngine._sect_patron(char, now))
        except Exception:
            pass
        try:
            from core.world_arc import active_arcs

            arcs = sorted(
                active_arcs() or [],
                key=lambda a: float(a.get("updated_at") or a.get("created_at") or 0),
                reverse=True,
            )
            for a in arcs:
                if a.get("kind") != "sect_crisis":
                    continue
                eff = a.get("effects") or {}
                sects = {str(eff.get("sect_a") or ""), str(eff.get("sect_b") or ""),
                         str(a.get("sect") or "")}
                if char.sect and char.sect in sects:
                    return done("sect", a.get("id") or "", "", ("", ""),
                                FateThreadEngine._sect_patron(char, now))
        except Exception:
            pass
        # P5 出身兜底（恒命中）
        if origin:
            old = origin.get("old_story") or {}
            npc_id = str(old.get("npc_id") or "")
            ant = rel_npc("foe")
            patron = rel_npc("kin")
            if npc_id and not ant[0] and not patron[0]:
                c = _char_by_id(npc_id)
                patron = (npc_id, c.name if c else "")
            return done("origin", npc_id or str(origin.get("signature") or ""),
                        npc_id, ant, patron)
        # 老角色无出身：按灵根/地点从 ROSTER 选引路人（agenda 优先序）
        try:
            from core.npc_roster import ROSTER
            from storage.db import CharacterRepository

            cands = [r for r in ROSTER if r.get("agenda") in ("treasure", "revenge")]
            cands.sort(key=lambda r: (0 if r.get("loc") == char.location else 1,
                                      str(r.get("uid") or "")))
            if cands:
                row = cands[0]
                npc = CharacterRepository.get_by_user_id(str(row.get("uid") or ""))
                pid = npc.id if npc is not None else str(row.get("uid") or "")
                pname = npc.name if npc is not None else str(row.get("name") or "")
                return done("origin", f"roster:{row.get('uid')}", pid,
                            ("", ""), (pid, pname))
        except Exception:
            pass
        return done("origin", "", "", ("", ""), ("", ""))

    @staticmethod
    def _sect_patron(char: Character, now: float) -> Tuple[str, str]:
        """引路人 = 本宗门 rank 最高在世者（以境界 tier 近似 rank 序）。"""
        if not char.sect:
            return ("", "")
        try:
            from core.origin import OriginEngine

            pool = [c for c in OriginEngine._npc_pool(now) if c.sect == char.sect]
            if not pool:
                return ("", "")
            top = max(pool, key=lambda c: (c.realm.tier, c.realm.sub_tier))
            return (top.id, top.name)
        except Exception:
            return ("", "")

    # ---------------- 章节骨架与绑定（§3.4/§3.5） ----------------
    @staticmethod
    def _chapter_kinds(seed_source: str, has_antagonist: bool) -> List[str]:
        idx0 = {
            "unfinished": "visit", "vendetta": "visit", "karma_shadow": "visit",
            "blood_feud": "feud", "sect": "sect", "origin": "visit",
        }.get(seed_source, "visit")
        idx1 = "treasure" if seed_source in ("karma_shadow", "origin") else "visit"
        if seed_source == "sect":
            idx3 = "sect"
        elif has_antagonist:
            idx3 = "feud"
        else:
            idx3 = "treasure"
        return [idx0, idx1, "choice", idx3, "climax", "finale"]

    @staticmethod
    def _chapter_text(thread_id: str, idx: int, kind: str, npc_name: str) -> Tuple[str, str]:
        cands = _CHAPTER_TEMPLATES.get(kind) or _CHAPTER_TEMPLATES["visit"]
        title, goal = cands[zlib.crc32(f"{thread_id}:{idx}".encode("utf-8")) % len(cands)]
        name = npc_name or "那位故人"
        return title, goal.replace("{npc}", name)

    @staticmethod
    def _build_chapters(thread_id: str, kinds: List[str],
                        npc_name: str) -> List[Dict[str, Any]]:
        chapters: List[Dict[str, Any]] = []
        for idx, kind in enumerate(kinds):
            title, goal_text = FateThreadEngine._chapter_text(thread_id, idx, kind, npc_name)
            chapters.append({
                "idx": idx,
                "group": CHAPTER_GROUPS[idx],
                "kind": kind,
                "tier": CHAPTER_TIERS[idx],
                "title": title,
                "goal_text": goal_text,
                "check_template": {"kind": kind},
                "check": {},
                "goal_id": "",
                "trigger_type": (
                    "on_create" if idx == 0
                    else "climax_resolved_or_lifespan" if idx == 5
                    else "prev_resolved"),
                "status": "locked",
                "summary": "",
                "activated_at": 0.0,
                "resolved_at": 0.0,
            })
        return chapters

    @staticmethod
    def _bind_check(thread: FateThread, chapter: Dict[str, Any],
                    char: Character) -> Dict[str, Any]:
        """章节 check 在激活瞬间按当时事实绑定（§3.5 表）。"""
        idx = int(chapter.get("idx") or 0)
        ant_id = thread.antagonist_npc_id
        pat_id = thread.patron_npc_id
        seed_npc_id = thread.seed_npc_id or ant_id or pat_id
        relic = str((thread.origin.get("old_story") or {}).get("item_ref") or "")
        if idx == 0:
            npc = _char_by_id(seed_npc_id) if seed_npc_id else None
            if npc is not None and npc.location:
                return {"kind": "visit_location", "ref": npc.location,
                        "npc_id": seed_npc_id}
            if seed_npc_id:
                return {"kind": "npc_attitude_at_least", "npc_id": seed_npc_id,
                        "value": -10}
            return {"kind": "visit_location", "ref": char.location}
        if idx == 1:
            return {"kind": "promise_kept_count", "count": 1}
        if idx == 2:
            npc_id = ant_id or pat_id
            if npc_id:
                return {"kind": "chain_resolved", "npc_id": npc_id, "outcome": "any"}
            if relic:
                return {"kind": "item_in_bag", "item_ref": relic}
            return {"kind": "stones_at_least", "amount": 200}
        if idx == 3:
            # 冲突章 NPC 绑定序（§4.3）：未竟关联人 > 世仇植入者 > 种子 NPC
            # ——三者已在种子扫描时收敛为 antagonist/patron/seed_npc_id。
            if ant_id:
                return {"kind": "chain_resolved", "npc_id": ant_id, "outcome": "any"}
            if pat_id:
                return {"kind": "npc_attitude_at_least", "npc_id": pat_id, "value": 15}
            if relic:
                return {"kind": "item_in_bag", "item_ref": relic}
            return {"kind": "stones_at_least", "amount": 200}
        if idx == 4:
            ss = thread.seed_source
            if ss in ("unfinished", "vendetta", "blood_feud"):
                if ant_id:
                    return {"kind": "chain_resolved", "npc_id": ant_id,
                            "outcome": "any"}
                return {"kind": "realm_at_least", "tier": 2}
            if ss == "karma_shadow":
                value = 0 if (ant_id and ant_id == seed_npc_id) else 60
                if seed_npc_id:
                    return {"kind": "npc_attitude_at_least",
                            "npc_id": seed_npc_id, "value": value}
                return {"kind": "realm_at_least", "tier": 2}
            if ss == "sect":
                if char.sect:
                    return {"kind": "realm_at_least",
                            "tier": int(char.realm.tier) + 1}
                return {"kind": "sect_joined", "ref": ""}
            if relic:
                return {"kind": "item_in_bag", "item_ref": relic}
            return {"kind": "realm_at_least", "tier": 2}
        return {}

    @staticmethod
    def _activate_chapter(thread: FateThread, chapter: Dict[str, Any],
                          char: Character, now: float,
                          events: List[Dict[str, Any]]) -> None:
        from core.goals import GoalEngine

        chapter["status"] = "active"
        chapter["activated_at"] = now
        idx = int(chapter.get("idx") or 0)
        if idx == 5:
            # finale：不另挂目标，回填 fate 命题目标的 instance（§3.5）
            chapter["check"] = dict(thread.final_proposition.get("check") or {})
            fid = str(thread.final_proposition.get("goal_id") or "")
            for g in (char.goals or []):
                if g.get("id") == fid or (
                    g.get("source") == "fate" and g.get("status") == "active"
                ):
                    chk = dict(g.get("check") or {})
                    if not chk.get("instance"):
                        chk["instance"] = f"{thread.id}:c5"
                        g["check"] = chk
                    thread.final_proposition["goal_id"] = g.get("id", "")
                    break
        else:
            check = dict(FateThreadEngine._bind_check(thread, chapter, char))
            check["instance"] = f"{thread.id}:c{idx}"
            chapter["check"] = check
            goal = GoalEngine.add_checked_goal(
                char, source="thread",
                title=str(chapter.get("title") or ""),
                detail=str(chapter.get("goal_text") or ""),
                check=check,
                deadline_days=(
                    FATE_CHAPTER_WINDOW_DAYS.get(str(chapter.get("group") or ""))
                    or None),
                instance=f"{thread.id}:c{idx}",
                now=now,
            )
            chapter["goal_id"] = goal.get("id", "")
        events.append({
            "idx": idx, "kind": "activated",
            "title": str(chapter.get("title") or ""),
            "text": str(chapter.get("goal_text") or ""),
            "ref_id": thread.id,
        })

    # ---------------- 建线（§3.8） ----------------
    @staticmethod
    def ensure_thread(char: Character, account=None,
                      now: Optional[float] = None) -> Optional[FateThread]:
        """幂等建线：已有 active/shelved 线即返回既有线；同世已封存不重建。"""
        t = now if now is not None else time.time()
        repo = _repo()
        try:
            mine = repo.list_by_player(char.id)
        except Exception:
            mine = []
        for th in mine:
            if th.status in ("active", "shelved"):
                return th
        if mine:
            return mine[-1]

        from core.goals import GoalEngine
        from core.origin import select_fate_proposition

        seed = FateThreadEngine._scan_seed(char, account, t)
        origin_copy = copy.deepcopy(getattr(char, "origin", None) or {})
        rels = origin_copy.get("relations") or []
        foe_rel = next((r for r in rels if r.get("role") == "foe"), None)
        debt = origin_copy.get("debt") or {}

        def _make_proposition(unfinished_arg: Dict[str, Any]):
            kind_s, text_s, check_s = select_fate_proposition(
                has_debt=bool(debt),
                debt_promise_id=str(debt.get("promise_id") or ""),
                has_foe=foe_rel is not None,
                foe_id=str(foe_rel["npc_id"]) if foe_rel else "",
                foe_name=str(foe_rel["npc_name"]) if foe_rel else "",
                old_story_kind=str((origin_copy.get("old_story") or {}).get("kind") or ""),
                family=str(origin_copy.get("family") or ""),
                item_ref=str((origin_copy.get("old_story") or {}).get("item_ref") or ""),
                unfinished=unfinished_arg,
            )
            return GoalEngine.add_checked_goal(
                char, source="fate", title=text_s, detail=text_s,
                check=check_s, deadline_days=None, now=t)

        # 命题收编（§3.8）：已有 active fate 目标直接取之；未竟占种子位时
        # 若命题恰为同一未竟（origin 生成时先行占用），让位重选（§3.3）。
        fate_goal = next(
            (g for g in (char.goals or [])
             if g.get("source") == "fate" and g.get("status") == "active"),
            None,
        )
        if fate_goal is not None and seed["seed_source"] == "unfinished":
            uchk = (seed["unfinished"].get("check") or {})
            gchk = fate_goal.get("check") or {}
            if uchk and gchk.get("kind") == uchk.get("kind") and (
                str(gchk.get("ref") or "") == str(uchk.get("ref") or "")
                and str(gchk.get("npc_id") or "") == str(uchk.get("npc_id") or "")
            ):
                fate_goal["status"] = "superseded"
                fate_goal = _make_proposition({})
        if fate_goal is None:
            unfinished_arg = {} if seed["unfinished_rebindable"] else seed["unfinished"]
            fate_goal = _make_proposition(unfinished_arg)

        ant_id, ant_name = seed["antagonist"]
        pat_id, pat_name = seed["patron"]
        thread_id = _new_thread_id()
        kinds = FateThreadEngine._chapter_kinds(
            seed["seed_source"], bool(ant_id))
        signature = (
            f"{seed['seed_source']}|{ant_id or pat_id}|{'/'.join(kinds)}")
        npc_display = ant_name or pat_name
        chapters = FateThreadEngine._build_chapters(thread_id, kinds, npc_display)
        thread = FateThread(
            id=thread_id,
            player_id=char.id,
            user_id=str(char.user_id or ""),
            life_no=(
                int(getattr(account, "total_lives", 0) or 0) + 1
                if account is not None
                else int(origin_copy.get("life_no") or 1)),
            status="active",
            seed_source=seed["seed_source"],
            seed_ref=seed["seed_ref"],
            seed_npc_id=seed["seed_npc_id"],
            title=_SEED_TITLES.get(seed["seed_source"], "命途"),
            antagonist_npc_id=ant_id,
            antagonist_name=ant_name,
            patron_npc_id=pat_id,
            patron_name=pat_name,
            origin=origin_copy,
            final_proposition={
                "text": str(fate_goal.get("title") or ""),
                "check": dict(fate_goal.get("check") or {}),
                "status": str(fate_goal.get("status") or "active"),
                "goal_id": str(fate_goal.get("id") or ""),
            },
            chapters=chapters,
            current_chapter=0,
            signature=signature,
            created_at=t,
        )
        # 防套路化（§3.7）：与同账户最近 3 条线比对指纹，确定性轮换 kind
        try:
            recents = [
                th for th in repo.list_by_user(str(char.user_id or ""))
                if th.id != thread.id
            ]
            recents.sort(key=lambda th: th.created_at, reverse=True)
            if any(th.signature == signature for th in recents[:3]):
                rotated = list(kinds)
                rotated[1] = "visit" if rotated[1] == "treasure" else "treasure"
                for cand in ("sect", "treasure", "feud"):
                    if cand != rotated[3]:
                        rotated[3] = cand
                        break
                new_sig = (
                    f"{seed['seed_source']}|{ant_id or pat_id}|{'/'.join(rotated)}")
                if new_sig != signature:
                    thread.chapters = FateThreadEngine._build_chapters(
                        thread_id, rotated, npc_display)
                    thread.signature = new_sig
                if any(th.signature == thread.signature for th in recents[:3]):
                    thread.signature_forced = True
        except Exception:
            pass
        events: List[Dict[str, Any]] = []
        if thread.chapters:
            FateThreadEngine._activate_chapter(
                thread, thread.chapters[0], char, t, events)
        repo.save(thread)
        return thread


    # ---------------- 派生与求值（§3.5/§3.6） ----------------
    @staticmethod
    def _fate_goal(char: Character, thread: FateThread) -> Optional[Dict[str, Any]]:
        fid = str(thread.final_proposition.get("goal_id") or "")
        fallback = None
        for g in (char.goals or []):
            if fid and g.get("id") == fid:
                return g
            if g.get("source") == "fate":
                fallback = g
        return fallback

    @staticmethod
    def _derive_current(thread: FateThread, char: Character, now: float,
                        events: List[Dict[str, Any]]) -> bool:
        """当前章 goal 终态 → 章节同步 + 激活下一章。返回是否有推进。"""
        idx = int(thread.current_chapter or 0)
        if idx >= len(thread.chapters or []):
            return False
        chapter = thread.chapters[idx]
        if chapter.get("status") != "active":
            return False
        if idx == 5:
            fg = FateThreadEngine._fate_goal(char, thread)
            if fg is not None and fg.get("status") in ("done", "failed"):
                chapter["status"] = fg.get("status")
                chapter["resolved_at"] = now
                chapter["summary"] = (
                    "终局命题已成" if fg.get("status") == "done" else "终局命题未成")
                events.append({
                    "idx": idx, "kind": "resolved",
                    "title": str(chapter.get("title") or ""),
                    "text": chapter["summary"], "ref_id": thread.id,
                })
                return True
            return False
        goal = None
        gid = str(chapter.get("goal_id") or "")
        inst = f"{thread.id}:c{idx}"
        for g in (char.goals or []):
            if gid and g.get("id") == gid:
                goal = g
                break
            if str((g.get("check") or {}).get("instance") or "") == inst:
                goal = g
        if goal is None or goal.get("status") not in ("done", "failed"):
            return False
        chapter["status"] = goal.get("status")
        chapter["resolved_at"] = now
        chapter["summary"] = (
            f"已成：{goal.get('title', '')}" if goal.get("status") == "done"
            else f"未成：{goal.get('title', '')}（{goal.get('done_reason', '到期未达成')}）")
        events.append({
            "idx": idx, "kind": "resolved",
            "title": str(chapter.get("title") or ""),
            "text": chapter["summary"], "ref_id": thread.id,
        })
        if goal.get("status") == "failed":
            thread.unfinished_note = (
                f"「{chapter.get('title', '')}」未成：{chapter.get('goal_text', '')}")
        nxt = idx + 1
        if nxt < len(thread.chapters):
            thread.current_chapter = nxt
            nch = thread.chapters[nxt]
            if nch.get("status") == "locked":
                FateThreadEngine._activate_chapter(thread, nch, char, now, events)
                if goal.get("status") == "failed":
                    nch["summary"] = f"因「{chapter.get('title', '')}」未成改道"
        return True

    @staticmethod
    def evaluate_for(char: Character, now: Optional[float] = None,
                     *, final: bool = False) -> Dict[str, Any]:
        """触发点求值（§3.6）：顺序由循环保证——每轮先 evaluate 全部
        判定式目标，再做章节派生；有推进则再轮 evaluate，使
        thread_climax 型命题在章节派生后被求值（§3.5 写死序）。
        shelved 线跳过派生与到期判定（§3.9）。"""
        from core.goals import GoalEngine

        t = now if now is not None else time.time()
        thread = FateThreadEngine._active_thread(char.id)
        if thread is None:
            return {"changed": False, "chapter_events": [], "thread": None}
        if thread.status == "shelved":
            return {"changed": False, "chapter_events": [], "thread": thread}
        events: List[Dict[str, Any]] = []
        changed = False
        for _ in range(8):
            GoalEngine.evaluate_checked_goals(char, t, final=final)
            progressed = FateThreadEngine._derive_current(thread, char, t, events)
            if progressed:
                changed = True
            if not progressed:
                break
        # 暮年章提前激活：剩余寿元 ≤3 游戏年（§3.4 finale 触发口径之二）
        try:
            if len(thread.chapters or []) > 5:
                finale = thread.chapters[5]
                if finale.get("status") == "locked" and (
                    char.lifespan.get_remaining_years() <= 3
                ):
                    FateThreadEngine._activate_chapter(
                        thread, finale, char, t, events)
                    changed = True
        except Exception:
            pass
        # finale 已激活时的独立派生（当前章可能还在前面章节）
        try:
            if len(thread.chapters or []) > 5:
                finale = thread.chapters[5]
                if finale.get("status") == "active" and int(
                    thread.current_chapter or 0
                ) != 5:
                    fg = FateThreadEngine._fate_goal(char, thread)
                    if fg is not None and fg.get("status") in ("done", "failed"):
                        finale["status"] = fg.get("status")
                        finale["resolved_at"] = t
                        changed = True
        except Exception:
            pass
        # 命题状态派生 + 线完成判定
        fg = FateThreadEngine._fate_goal(char, thread)
        if fg is not None:
            st = str(fg.get("status") or "active")
            if thread.final_proposition.get("status") != st:
                thread.final_proposition["status"] = st
                changed = True
        if len(thread.chapters or []) > 5 and (
            thread.chapters[5].get("status") == "done"
        ) and thread.status == "active":
            thread.status = "completed"
            changed = True
        if changed:
            try:
                _repo().save(thread)
            except Exception:
                pass
        return {"changed": changed, "chapter_events": events, "thread": thread}

    @staticmethod
    def record_visit(char: Character, location: str,
                     now: Optional[float] = None) -> Dict[str, Any]:
        """迁跃落点（T5）：先记 visited 再 evaluate_for（§3.6 写死序）。"""
        t = now if now is not None else time.time()
        thread = FateThreadEngine._active_thread(char.id)
        if thread is not None and location:
            if location not in (thread.visited or []):
                thread.visited = list(thread.visited or []) + [location]
                thread.visited = thread.visited[-20:]
                try:
                    _repo().save(thread)
                except Exception:
                    pass
        return FateThreadEngine.evaluate_for(char, t)

    # ---------------- 搁置 / 续（§3.9） ----------------
    @staticmethod
    def shelve_thread(char: Character, now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        thread = FateThreadEngine._active_thread(char.id)
        if thread is None:
            return {"success": False, "message": "眼下并无命途主线可搁置。"}
        if thread.status == "shelved":
            return {"success": False, "message": "命途已在搁置中。"}
        if thread.status != "active":
            return {"success": False, "message": "此线已封存，无从搁置。"}
        thread.status = "shelved"
        thread.shelved_at = t
        _repo().save(thread)
        return {"success": True, "message": f"命途「{thread.title}」已搁置，不删不罚，随时可续。",
                "thread": thread}

    @staticmethod
    def resume_thread(char: Character, now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        thread = FateThreadEngine._active_thread(char.id)
        if thread is None or thread.status != "shelved":
            return {"success": False, "message": "命途未在搁置中。"}
        shift = max(0.0, t - float(thread.shelved_at or t))
        idx = int(thread.current_chapter or 0)
        if 0 <= idx < len(thread.chapters or []):
            gid = str(thread.chapters[idx].get("goal_id") or "")
            for g in (char.goals or []):
                if gid and g.get("id") == gid and float(g.get("deadline_at") or 0):
                    g["deadline_at"] = float(g["deadline_at"]) + shift
        thread.status = "active"
        thread.shelved_at = 0.0
        _repo().save(thread)
        return {"success": True,
                "message": f"命途「{thread.title}」已续行，当前章期限顺延。",
                "thread": thread, "deadline_shift": shift}

    # ---------------- 呈现（§8.1/§8.4） ----------------
    @staticmethod
    def thread_status_dict(char: Character) -> Optional[Dict[str, Any]]:
        thread = FateThreadEngine.get_for_player(char.id)
        if thread is None:
            return None
        goals_by_id = {
            g.get("id"): g for g in (char.goals or []) if g.get("id")
        }
        chapters_out = []
        for ch in (thread.chapters or []):
            goal = goals_by_id.get(str(ch.get("goal_id") or ""))
            _row: Dict[str, Any] = {
                "idx": ch.get("idx"), "group": ch.get("group"),
                "kind": ch.get("kind"), "tier": ch.get("tier"),
                "title": ch.get("title"), "goal_text": ch.get("goal_text"),
                "status": ch.get("status"),
                "deadline_at": float(goal.get("deadline_at") or 0.0) if goal else 0.0,
            }
            # B1-4：章内 check 透传（存在时才带，只取 kind/ref/npc_id 三键）
            _chk = ch.get("check") or {}
            if _chk:
                _row["check"] = {
                    k: _chk.get(k) for k in ("kind", "ref", "npc_id") if _chk.get(k)
                }
            chapters_out.append(_row)
        # B1-4：current_target——第一个 active 且 visit 类 check 的章，现查目标 NPC
        # （NPC 会迁徙，必须现查，禁止存快照）；无此类章/查不到 NPC 时为 null。
        current_target: Optional[Dict[str, Any]] = None
        for ch in (thread.chapters or []):
            if ch.get("status") != "active":
                continue
            _chk = ch.get("check") or {}
            _kind = str(_chk.get("kind") or "")
            if not (_kind == "visit" or _kind.startswith("visit")):
                continue
            _npc_id = str(_chk.get("npc_id") or "")
            if not _npc_id:
                break
            _npc = _char_by_id(_npc_id)
            if _npc is None:
                break
            current_target = {
                "npc_id": _npc_id,
                "npc_name": _npc.name,
                "npc_location": _npc.location,
                "same_location": _npc.location == char.location,
            }
            break
        return {
            "id": thread.id,
            "title": thread.title,
            "status": thread.status,
            "seed_source": thread.seed_source,
            "seed_ref": thread.seed_ref,
            "antagonist": (
                {"id": thread.antagonist_npc_id, "name": thread.antagonist_name}
                if thread.antagonist_npc_id else None),
            "patron": (
                {"id": thread.patron_npc_id, "name": thread.patron_name}
                if thread.patron_npc_id else None),
            "final_proposition": {
                "text": str(thread.final_proposition.get("text") or ""),
                "status": str(thread.final_proposition.get("status") or "active"),
            },
            "current_chapter": thread.current_chapter,
            "current_target": current_target,
            "chapters": chapters_out,
            "shelvable": thread.status == "active",
            "origin_present": bool(thread.origin),
        }

    @staticmethod
    def panel_text(char: Character) -> str:
        thread = FateThreadEngine.get_for_player(char.id)
        if thread is None:
            return "【命途】尚无命途主线。降生或转世后，天道自会为你牵一线因果。"
        seed_cn = {
            "unfinished": "未竟之志", "vendetta": "世仇", "karma_shadow": "因果影子",
            "blood_feud": "血仇", "sect": "宗门", "origin": "出身",
        }.get(thread.seed_source, thread.seed_source)
        status_cn = {
            "active": "进行中", "shelved": "已搁置", "completed": "功成",
            "broken": "留憾", "inherited": "未竟封存",
        }.get(thread.status, thread.status)
        lines = [
            f"【命途】{thread.title}（{status_cn}）",
            f"种子：{seed_cn}" + (
                f" · 对手：{thread.antagonist_name}" if thread.antagonist_name else "")
            + (f" · 引路人：{thread.patron_name}" if thread.patron_name else ""),
            "章节：",
        ]
        mark = {"done": "✓", "failed": "✗", "active": "▶", "locked": "·"}
        for ch in (thread.chapters or []):
            lines.append(
                f"  {mark.get(ch.get('status'), '·')} 第{int(ch.get('idx') or 0) + 1}章 "
                f"{ch.get('title', '')}——{ch.get('goal_text', '')}")
        prop = thread.final_proposition or {}
        lines.append(
            f"终局命题：{prop.get('text', '')}（{prop.get('status', 'active')}）")
        if thread.status == "active":
            lines.append("（/命途 搁置 可暂放主线，不删不罚；/命途 续 再启）")
        elif thread.status == "shelved":
            lines.append("（/命途 续 恢复主线，当前章期限顺延）")
        return "\n".join(lines)

    # ---------------- 死亡封存（§3.8） ----------------
    @staticmethod
    def seal_for_death(char: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """settle_death 内的 thread 分支：派生→定状态→算未竟与摘要前缀。

        返回 {"prefix": 命途摘要段, "unfinished_prop": dict|None, "thread"}；
        无线时返回 {}。异常由调用方（legacy）try/except 兜底。
        """
        t = now if now is not None else time.time()
        thread = FateThreadEngine._active_thread(char.id)
        if thread is None:
            return {}
        events: List[Dict[str, Any]] = []
        for _ in range(8):
            if not FateThreadEngine._derive_current(thread, char, t, events):
                break
        fg = FateThreadEngine._fate_goal(char, thread)
        if fg is not None:
            thread.final_proposition["status"] = str(fg.get("status") or "active")
        chapters = thread.chapters or []
        done_n = sum(1 for ch in chapters if ch.get("status") == "done")
        finale_done = len(chapters) > 5 and chapters[5].get("status") == "done"
        prop_done = bool(fg and fg.get("status") == "done")
        prop_failed = bool(fg and fg.get("status") == "failed")
        if finale_done or prop_done:
            thread.status = "completed"
            ending = "功成"
        elif prop_failed:
            thread.status = "broken"
            ending = "留憾"
        else:
            thread.status = "inherited"
            ending = "中道崩殂"
        thread.sealed_at = t
        # 未竟 note：未成章取舍——failed 章优先（最后一条），其次当前
        # 进行中章，再次未激活章（首条）；finale 章即命题本身，不作候选
        body = [ch for ch in chapters if int(ch.get("idx") or 0) != 5]
        unmet = None
        for ch in reversed(body):
            if ch.get("status") == "failed":
                unmet = ch
                break
        if unmet is None:
            for ch in body:
                if ch.get("status") == "active":
                    unmet = ch
                    break
        if unmet is None:
            for ch in body:
                if ch.get("status") == "locked":
                    unmet = ch
                    break
        if thread.status != "completed" and unmet is not None:
            if not thread.unfinished_note:
                thread.unfinished_note = (
                    f"「{unmet.get('title', '')}」未成：{unmet.get('goal_text', '')}")
        _repo().save(thread)
        prefix = (
            f"命途「{thread.title}」{done_n}/{len(chapters)} 章了结，{ending}；")
        unfinished_prop = None
        if thread.status != "completed" and thread.unfinished_note and unmet is not None:
            chk = dict(unmet.get("check") or {})
            if chk:
                unfinished_prop = {
                    "kind": _CHECK_TO_PROP_KIND.get(
                        str(chk.get("kind") or ""), "stand_firm"),
                    "text": thread.unfinished_note,
                    "check": chk,
                }
        return {"prefix": prefix, "unfinished_prop": unfinished_prop,
                "thread": thread}

    # ---------------- 世仇选人（§4.2） ----------------
    @staticmethod
    def select_vendetta(account, new_char: Character,
                        now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """转世世仇选人链：xue 链 > KarmaLink 仇/怨孤儿行 > 负值影子。

        每级 bounds 复核（在世 + tier ≤ 新角起始境界+1）；本人超界/已死
        降级同门/后人；植入者不得是影子已覆盖者（来源 1/2 口径）——
        来源 3 的候选本身即影子条目，covered 者仍植入但标
        shadow_covered，origin 落账时不叠加 shift（VD-05 口径，
        态度以影子值为准）。全空返回 None（诚实降级）。
        返回 {"npc_id","npc_name","for_id","for_name","shadow_covered"}。
        """
        t = now if now is not None else time.time()
        if account is None or not (getattr(account, "traces", None) or []):
            return None
        trace = account.traces[-1]
        covered: set = set()
        try:
            from core.inheritance import applied_shadow_entries

            covered = {e["npc_id"] for e in applied_shadow_entries(account, trace)}
        except Exception:
            covered = set()
        bound = int(new_char.realm.tier) + 1

        # 来源候选（仇源角色 id 有序列表）
        s1: List[str] = []
        try:
            from storage.db import KarmaChainRepository

            xue = [c for c in KarmaChainRepository.list_by_player(trace.character_id)
                   if c.kind == "xue"]
            for c in sorted(xue, key=lambda x: x.created_at, reverse=True):
                if c.counterparty_id and c.counterparty_id not in s1:
                    s1.append(c.counterparty_id)
        except Exception:
            pass
        s2: List[str] = []
        try:
            from storage.db import KarmaLinkRepository

            rows = []
            for link in KarmaLinkRepository.list_all():
                if link.link_type not in ("仇", "怨"):
                    continue
                if not link.involves(trace.character_id):
                    continue
                other_id, _ = link.other_side(trace.character_id)
                other = _char_by_id(other_id)
                if other is not None and _is_npc_char(other):
                    rows.append((int(link.strength or 0), other_id))
            for _s, oid in sorted(rows, key=lambda x: -x[0]):
                if oid not in s2:
                    s2.append(oid)
        except Exception:
            pass
        s3: List[str] = []
        try:
            from config import SHADOW_MIN_ABS

            negs = [e for e in (trace.shadow or []) if int(e.value) <= -SHADOW_MIN_ABS]
            for e in sorted(negs, key=lambda e: -abs(int(e.value))):
                if e.npc_id not in s3:
                    s3.append(e.npc_id)
        except Exception:
            pass

        def implant_for(source_id: str) -> Optional[Dict[str, Any]]:
            src = _char_by_id(source_id)
            if src is None:
                return None
            if _alive(src, t) and src.realm.tier <= bound and src.id not in covered:
                return {"npc_id": src.id, "npc_name": src.name,
                        "for_id": src.id, "for_name": src.name,
                        "shadow_covered": False}
            # 同门 / 后人降级
            cands: List[Character] = []
            try:
                from core.origin import OriginEngine

                pool = OriginEngine._npc_pool(t)
                if src.sect:
                    cands = [c for c in pool if c.sect == src.sect]
                else:
                    from storage.db import KarmaLinkRepository

                    linked = set()
                    for link in KarmaLinkRepository.list_all():
                        if link.link_type in ("师徒", "结拜") and link.involves(src.id):
                            oid, _ = link.other_side(src.id)
                            linked.add(oid)
                    cands = [c for c in pool if c.id in linked]
            except Exception:
                cands = []
            agenda_by_uid: Dict[str, str] = {}
            try:
                from core.npc_roster import ROSTER

                agenda_by_uid = {r.get("uid", ""): r.get("agenda", "") for r in ROSTER}
            except Exception:
                pass
            cands = [
                c for c in cands
                if c.id != src.id and c.id not in covered
                and _alive(c, t) and c.realm.tier <= bound
            ]
            cands.sort(key=lambda c: (
                0 if agenda_by_uid.get(str(c.user_id)) == "revenge" else 1,
                int(c.realm.tier), str(c.user_id)))
            if cands:
                pick = cands[0]
                return {"npc_id": pick.id, "npc_name": pick.name,
                        "for_id": src.id, "for_name": src.name,
                        "shadow_covered": False}
            return None

        for source_list in (s1, s2):
            for sid in source_list:
                got = implant_for(sid)
                if got is not None:
                    return got
        for sid in s3:
            src = _char_by_id(sid)
            if src is None or not _alive(src, t) or src.realm.tier > bound:
                continue
            return {"npc_id": src.id, "npc_name": src.name,
                    "for_id": src.id, "for_name": src.name,
                    "shadow_covered": src.id in covered}
        return None
