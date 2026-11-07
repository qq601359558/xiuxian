"""
NPC 主动互动：玩家到达某地时，同场 NPC 可能先开口
由态度/性格驱动；经门禁；可 shift 态度
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository
from core.npc_mind import (
    ensure_mind,
    attitude_toward,
    shift_attitude,
    ATTITUDE_LABELS,
    _is_npc,
)
from core.memory import record_event, ensure_bio
from core.here import list_here
from ai.gate import gate
from ai.gateway import ai_ready
from ai.audit import write_audit
from config import (
    NPC_PROACTIVE_AI_BUDGET_PER_TICK,
    NPC_PROACTIVE_LOCAL_ONLY_AFTER,
    SECONDS_PER_GAME_DAY,
)
from server.log import log_event
from storage.db import WorldStateRepository

# 进程内 AI 开口预算（每窗口重置）；权威在 world_state
_BUDGET_KEY = "npc_proactive_ai_budget"
_ai_budget_used = 0
_budget_window_start = 0.0
_AI_BUDGET_WINDOW = 300.0  # 5 分钟窗口
_budget_loaded = False


def _ensure_budget_loaded() -> None:
    global _ai_budget_used, _budget_window_start, _budget_loaded
    if _budget_loaded:
        return
    try:
        data = WorldStateRepository.get(_BUDGET_KEY) or {}
        _ai_budget_used = int(data.get("used") or 0)
        _budget_window_start = float(data.get("window_start") or 0.0)
    except Exception:
        pass
    _budget_loaded = True


def _persist_budget() -> None:
    try:
        WorldStateRepository.set(
            _BUDGET_KEY,
            {"used": _ai_budget_used, "window_start": _budget_window_start},
        )
    except Exception:
        pass


def _consume_ai_budget() -> bool:
    """返回是否允许再调一次 AI；超预算则 False"""
    global _ai_budget_used, _budget_window_start
    _ensure_budget_loaded()
    now = time.time()
    if now - _budget_window_start > _AI_BUDGET_WINDOW:
        _budget_window_start = now
        _ai_budget_used = 0
        _persist_budget()
    if _ai_budget_used >= NPC_PROACTIVE_AI_BUDGET_PER_TICK:
        return False
    _ai_budget_used += 1
    _persist_budget()
    return True


# 主动开口概率（按态度）
PROACTIVE_CHANCE = {
    "hostile": 0.55,
    "wary": 0.35,
    "neutral": 0.22,
    "friendly": 0.40,
    "ally": 0.50,
}


def _local_opening(npc: Character, player: Character, att_label: str, personality: str) -> Dict[str, Any]:
    if att_label == "hostile":
        return {
            "line": f"{npc.name}目光一冷，手按兵刃：「{player.name}，你还敢来？」",
            "delta": 0,
        }
    if att_label == "ally":
        return {
            "line": f"{npc.name}拱手：「{player.name}道友，正要找你。」",
            "delta": 0,
        }
    if "贪" in (personality or ""):
        return {"line": f"{npc.name}搓了搓手指：「道友可是有买卖？」", "delta": 1}
    if "谨慎" in (personality or ""):
        return {"line": f"{npc.name}后退半步，打量你一眼，不语。", "delta": -1}
    if "豪爽" in (personality or ""):
        return {"line": f"{npc.name}朗声：「{player.name}！来得正好，坐。」", "delta": 2}
    if "记仇" in (personality or ""):
        return {"line": f"{npc.name}皮笑肉不笑：「哟，稀客。」", "delta": -1}
    return {"line": f"{npc.name}微微颔首：「{player.name}道友。」", "delta": 0}


class NpcProactiveEngine:
    """玩家进入场景时，可能被 NPC 主动搭话"""

    COOLDOWN_SECONDS = 90.0
    _last: Dict[str, float] = {}  # player_id -> ts

    @staticmethod
    def maybe_engage(
        player: Character,
        chance_scale: float = 1.0,
        max_speakers: int = 1,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        返回主动互动列表（可能为空）。
        每玩家冷却，避免刷屏。
        """
        if player.status == CharacterStatus.DEAD:
            return []
        now = time.time()
        last = NpcProactiveEngine._last.get(player.id, 0)
        if not force and (now - last) < NpcProactiveEngine.COOLDOWN_SECONDS:
            return []

        others = [c for c in list_here(player) if c.get("is_npc")]
        if not others:
            return []

        # 按态度优先：敌对/亲近更爱开口
        def prio(item):
            order = {"hostile": 0, "ally": 1, "friendly": 2, "wary": 3, "neutral": 4}
            return order.get(item.get("attitude") or "neutral", 5)

        others.sort(key=prio)

        results: List[Dict[str, Any]] = []
        for info in others:
            if len(results) >= max_speakers:
                break
            att = info.get("attitude") or "neutral"
            p = (PROACTIVE_CHANCE.get(att, 0.2)) * chance_scale
            if not force and random.random() > p:
                continue

            npc = CharacterRepository.get_by_name(info.get("name") or "")
            if not npc or npc.id == player.id:
                continue
            if npc.location != player.location:
                continue

            mind = ensure_mind(npc)
            personality = mind.get("personality") or ""
            ensure_bio(npc)
            att_cn = ATTITUDE_LABELS.get(att, "中立")

            opening = None
            source = "local"
            use_ai = ai_ready() and _consume_ai_budget()
            if use_ai:
                try:
                    from core.npc_personas import persona_prompt_block

                    persona_blk = persona_prompt_block(npc)
                except Exception:
                    persona_blk = ""
                data = None
                try:
                    from ai.router import invoke as ai_invoke

                    result = ai_invoke(
                        "npc_proactive",
                        payload={
                            "name": npc.name,
                            "realm": npc.realm.name,
                            "personality": personality,
                            "persona": persona_blk,
                            "player": player.name,
                            "att_cn": att_cn,
                            "location": npc.location,
                        },
                        actor_id=npc.id,
                    )
                    if result.get("ok"):
                        data = result.get("data")
                except Exception:
                    data = None
                if data and data.get("line"):
                    opening = {
                        "line": str(data["line"])[:200],
                        "delta": max(-5, min(5, int(data.get("delta") or 0))),
                    }
                    source = "ai"
                else:
                    log_event("GATE", "npc_proactive_ai_empty", npc=npc.name)
            elif ai_ready() and NPC_PROACTIVE_LOCAL_ONLY_AFTER:
                # 超预算：本地模板，记一笔
                log_event("GATE", "npc_proactive_budget_skip", npc=npc.name)
            if not opening:
                opening = _local_opening(npc, player, att, personality)

            if opening.get("delta"):
                att = shift_attitude(npc, player.id, opening["delta"], reason="主动搭话")
            else:
                att = attitude_toward(npc, player.id)

            eid = record_event(
                type="TALK",
                actor=npc,
                target=player,
                summary=f"{npc.name}主动搭话：{opening['line'][:40]}",
                location=npc.location,
            )
            write_audit({
                "ts": now, "actor": npc.id, "kind": "npc_proactive",
                "source": source, "event_id": eid,
            })

            results.append({
                "npc": npc.name,
                "personality": personality,
                "attitude": att.get("label", att),
                "attitude_cn": ATTITUDE_LABELS.get(att.get("label", att) if isinstance(att, dict) else att, att_cn),
                "line": opening["line"],
                "delta": opening.get("delta", 0),
                "source": source,
                "text": f"【{npc.name}·{personality}】{opening['line']}",
            })

        if results:
            NpcProactiveEngine._last[player.id] = now
        return results

    @staticmethod
    def reset_cooldown(player_id: str):
        NpcProactiveEngine._last.pop(player_id, None)


# =====================================================================
# 主动戏剧层（game-feel-phase2 Spec §5）：五类戏剧，类型判定与后果
# 100% 规则；戏剧本身零数值发放——后果全落既有系统（机会目标/
# 赠礼转移/斗法入口/诺言与因果链既有结算/因果链 nudge 钳制口）。
# 状态只落两处 KV：drama_pending:{char_id}、drama_quota:{char_id}。
# 评估只挂登录入局与迁跃落点两个既有触发点，零新增 tick 扫描。
# =====================================================================

DRAMA_TYPES_CN = {
    "betrayal": "背叛", "provoke": "挑衅", "involvement": "牵连",
    "help": "求助", "favor": "示好",
}
# 优先级写死：背叛 > 挑衅 > 牵连 > 求助 > 示好
DRAMA_PRIORITY = ("betrayal", "provoke", "involvement", "help", "favor")
DRAMA_OPTIONS: Dict[str, List[Dict[str, str]]] = {
    "betrayal": [{"key": "confront", "label": "摊牌"}],
    "provoke": [{"key": "fight", "label": "应战"}, {"key": "avoid", "label": "避走"}],
    "involvement": [{"key": "mediate", "label": "劝和"}, {"key": "harden", "label": "硬顶"}],
    "help": [{"key": "accept", "label": "接取"}, {"key": "decline", "label": "婉拒"}],
    "favor": [{"key": "ack", "label": "知晓"}],
}
DRAMA_DAILY_CAP = 3          # 每玩家每现实日计件戏剧上限（示好不占额）
DRAMA_COUNTED = ("help", "provoke", "betrayal", "involvement")
_DRAMA_KIND_CN = {"en": "恩", "chou": "仇", "nuo": "诺", "xue": "血仇"}


def _drama_band(value: int) -> str:
    if value <= -40:
        return "hostile"
    if value <= -15:
        return "wary"
    if value >= 40:
        return "ally"
    if value >= 15:
        return "friendly"
    return "neutral"


# 本地模板：每类型 × 态度档 ≥1 条（§5.5）；变量只取人名/地点/既有账文本。
_DRAMA_TEMPLATES: Dict[str, Dict[str, List[str]]] = {
    "betrayal": {
        "hostile": ["风闻{npc}提起那桩未了之诺，冷笑道：「{fact}——这笔账，我自有算法。」"],
        "wary": ["有传闻说{npc}对那桩未了之诺耿耿于怀：{fact}。言语间，已生变意。"],
        "neutral": ["坊间隐隐有话：{npc}与你之间那桩未了之诺（{fact}），怕有波澜。"],
        "friendly": ["有人瞧见{npc}独自对着那桩未了之诺出神：{fact}。神色难明。"],
        "ally": ["{npc}遣人捎话，只提那桩未了之诺：{fact}。话里有话。"],
    },
    "provoke": {
        "hostile": ["{npc}按剑而立，扬声道：「{player}！{fact}，今日便要讨个说法！」"],
        "wary": ["{npc}斜眼睨你：「听闻阁下近来好大威风。{fact}，可敢一试？」"],
        "neutral": ["{npc}忽然拦住去路：「{fact}。怎么，不敢应声？」"],
        "friendly": ["{npc}半真半假地笑道：「{fact}——切磋切磋，你总不会避战吧？」"],
        "ally": ["{npc}大笑着拍案：「{fact}！来，与我过两招助兴！」"],
    },
    "involvement": {
        "hostile": ["{npc}寻上门来，话带威胁：「{fact}——这事，你脱不了干系。」"],
        "wary": ["{npc}拦下你，压低声音：「{fact}。你若识相，便给个交代。」"],
        "neutral": ["{npc}前来转告：「{fact}。我在中间，只盼两边都消停。」"],
        "friendly": ["{npc}温言相劝：「{fact}。冤家宜解不宜结，让我从中说和。」"],
        "ally": ["{npc}亲自登门：「{fact}。你的事，我不能坐视。」"],
    },
    "help": {
        "hostile": ["{npc}竟破天荒开口求助：「{fact}……此事，只你能帮。」"],
        "wary": ["{npc}迟疑再三，仍道：「{fact}。若你肯援手，我记这份情。」"],
        "neutral": ["{npc}寻到你：「{fact}。不知你可愿帮衬一二？」"],
        "friendly": ["{npc}拱手相求：「{fact}。此事非你不可，望道友援手。」"],
        "ally": ["{npc}开门见山：「{fact}。自家人不说两家话，帮我这一回。」"],
    },
    "favor": {
        "hostile": ["{npc}竟遣人送来一份薄礼，附言：「{fact}，两讫。」"],
        "wary": ["{npc}托人捎来些许灵石，只道：「{fact}，聊表心意。」"],
        "neutral": ["{npc}使人送来一份心意：「{fact}，不成敬意。」"],
        "friendly": ["{npc}备了份薄礼亲手奉上：「{fact}，小小心意。」"],
        "ally": ["{npc}大笑着塞来一袋灵石：「{fact}！拿着，自家兄弟。」"],
    },
}


def _drama_quota_key(char_id: str) -> str:
    return f"drama_quota:{char_id}"


def _drama_pending_key(char_id: str) -> str:
    return f"drama_pending:{char_id}"


def _load_drama_quota(char_id: str, now: float) -> Dict[str, Any]:
    """频控 KV（§5.4）：现实日翻页时 count 清零；同人游戏日标记与
    示好消费 ts 跨日保留（各自带日/时戳口径，过期自然失效）。"""
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    try:
        rec = WorldStateRepository.get(_drama_quota_key(char_id)) or {}
    except Exception:
        rec = {}
    if not isinstance(rec, dict):
        rec = {}
    out = {
        "day": day,
        "count": int(rec.get("count") or 0) if rec.get("day") == day else 0,
        "npc_game_day": dict(rec.get("npc_game_day") or {}),
        "favor_consumed_ts": [
            float(x) for x in (rec.get("favor_consumed_ts") or [])
            if float(x or 0) >= now - SECONDS_PER_GAME_DAY],
    }
    return out


def _save_drama_quota(char_id: str, quota: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_drama_quota_key(char_id), quota)
    except Exception:
        pass


def _load_drama_pending(char_id: str, now: float) -> List[Dict[str, Any]]:
    """待回应队列；过期事件惰性清除（过期无任何后果，§5.4）。"""
    try:
        raw = WorldStateRepository.get(_drama_pending_key(char_id)) or []
    except Exception:
        raw = []
    if not isinstance(raw, list):
        return []
    alive = [e for e in raw if isinstance(e, dict)
             and float(e.get("expires_at") or 0) > now]
    if len(alive) != len(raw):
        try:
            WorldStateRepository.set(_drama_pending_key(char_id), alive)
        except Exception:
            pass
    return alive


def _save_drama_pending(char_id: str, pending: List[Dict[str, Any]]) -> None:
    try:
        WorldStateRepository.set(_drama_pending_key(char_id), pending)
    except Exception:
        pass


class DramaEngine:
    """NPC 主动戏剧引擎（§5）：evaluate 评估新建至多 1 件；respond 落账。"""

    # ---------------- 台词（AI 可用走既有 scene + 人设块，否则本地模板） ----------------
    @staticmethod
    def _line(npc: Character, player: Character, dtype: str,
              att_value: int, fact: str) -> tuple:
        source = "local"
        if ai_ready() and _consume_ai_budget():
            data = None
            try:
                from core.npc_personas import persona_prompt_block

                persona_blk = persona_prompt_block(npc)
            except Exception:
                persona_blk = ""
            try:
                from ai.router import invoke as ai_invoke

                result = ai_invoke(
                    "npc_proactive",
                    payload={
                        "name": npc.name,
                        "realm": npc.realm.name,
                        "personality": (ensure_mind(npc).get("personality") or ""),
                        "persona": persona_blk,
                        "player": player.name,
                        "att_cn": ATTITUDE_LABELS.get(_drama_band(att_value), "中立"),
                        "location": npc.location,
                        "drama_type": dtype,
                        "drama_fact": fact,
                    },
                    actor_id=npc.id,
                )
                if result.get("ok"):
                    data = result.get("data")
            except Exception:
                data = None
            if data and data.get("line"):
                return str(data["line"])[:200], "ai"
        band = _drama_band(att_value)
        tpls = (_DRAMA_TEMPLATES.get(dtype) or {}).get(band) \
            or (_DRAMA_TEMPLATES.get(dtype) or {}).get("neutral") or ["{npc}寻上门来。"]
        import zlib

        tpl = tpls[zlib.crc32(f"{npc.id}:{dtype}".encode("utf-8")) % len(tpls)]
        return tpl.format(npc=npc.name, player=player.name, fact=fact), source

    # ---------------- 评估（只在 login / travel 两触发点被调用） ----------------
    @staticmethod
    def evaluate(player: Character, *, trigger: str,
                 now: Optional[float] = None) -> List[Dict[str, Any]]:
        t = now if now is not None else time.time()
        if player is None or player.status == CharacterStatus.DEAD:
            return []
        pending = _load_drama_pending(player.id, t)
        quota = _load_drama_quota(player.id, t)
        game_day = int(t // SECONDS_PER_GAME_DAY)

        try:
            npcs = [c for c in CharacterRepository.list_all_alive()
                    if _is_npc(c) and c.id != player.id]
        except Exception:
            return []
        att: Dict[str, int] = {}
        for n in npcs:
            try:
                att[n.id] = int(attitude_toward(n, player.id).get("value") or 0)
            except Exception:
                att[n.id] = 0
        by_id = {n.id: n for n in npcs}

        # 既有账快照：诺言 / 因果链 / KarmaLink 边
        open_promises: List[Any] = []
        try:
            from core.promises import PromiseEngine

            for p in PromiseEngine._involving(player.id):
                st = p.status.value if hasattr(p.status, "value") else str(p.status)
                if p.promiser_id == player.id and st in ("PENDING", "ACTIVE"):
                    open_promises.append(p)
        except Exception:
            open_promises = []
        chains: List[Any] = []
        try:
            from storage.db import KarmaChainRepository

            chains = KarmaChainRepository.list_by_player(player.id)
        except Exception:
            chains = []
        fermenting = [c for c in chains if c.status == "fermenting"]
        links: List[Any] = []
        try:
            from storage.db import KarmaLinkRepository

            links = KarmaLinkRepository.list_all()
        except Exception:
            links = []

        def _link_between(a_id: str, b_id: str, types: tuple) -> Optional[Any]:
            for lk in links:
                if lk.link_type in types and lk.involves(a_id) and lk.involves(b_id):
                    return lk
            return None

        def _born(n: Character) -> float:
            return float(getattr(n, "born_at", 0.0) or 0.0)

        # ---- 候选（每类按态度极值排序；同类多候选逐个过闸，§5.2/§5.4） ----
        cands: Dict[str, List[Dict[str, Any]]] = {k: [] for k in DRAMA_PRIORITY}

        # 背叛（F9 口径）：未了诺言 + 态度 ≤−15，或 KarmaLink 仇边 ≥3 + 未了诺言
        bl = []
        for p in open_promises:
            npc = by_id.get(p.promisee_id)
            if npc is None:
                continue
            edge = _link_between(player.id, npc.id, ("仇",))
            if att[npc.id] <= -15 or (edge is not None and int(edge.strength or 0) >= 3):
                bl.append((att[npc.id], -_born(npc), npc, p))
        bl.sort(key=lambda x: (x[0], x[1]))
        cands["betrayal"] = [
            {"npc": npc, "promise": p, "fact": p.desc or "一桩未了之诺"}
            for _, _, npc, p in bl]

        # 挑衅：hostile 同场，或 fermenting chou/xue 链（不限同场）
        pl = []
        chain_by_cp: Dict[str, Any] = {}
        for ch in fermenting:
            if ch.kind in ("chou", "xue"):
                chain_by_cp.setdefault(ch.counterparty_id, ch)
        for npc in npcs:
            ch = chain_by_cp.get(npc.id)
            if att[npc.id] <= -40 and npc.location == player.location:
                pl.append((att[npc.id], -_born(npc), npc, ch))
            elif ch is not None:
                pl.append((att[npc.id], -_born(npc), npc, ch))
        pl.sort(key=lambda x: (x[0], x[1]))
        cands["provoke"] = [
            {"npc": npc, "chain": ch,
             "fact": (f"与你的{_DRAMA_KIND_CN.get(ch.kind, '因果')}未了"
                      if ch is not None else "旧怨未消")}
            for _, _, npc, ch in pl]

        # 牵连：fermenting 链 counterparty 的同 sect 者 / 师徒·结拜边者（第三方）
        il = []
        for ch in fermenting:
            cp = by_id.get(ch.counterparty_id)
            if cp is None:
                continue
            for npc in npcs:
                if npc.id in (cp.id, player.id):
                    continue
                same_sect = bool(cp.sect) and npc.sect == cp.sect
                bonded = _link_between(npc.id, cp.id, ("师徒", "结拜")) is not None
                if not (same_sect or bonded):
                    continue
                if att[npc.id] < -15:
                    continue
                il.append((-int(ch.strength or 0), -att[npc.id], -_born(npc), npc, ch, cp))
        il.sort(key=lambda x: (x[0], x[1], x[2]))
        cands["involvement"] = [
            {"npc": npc, "chain": ch,
             "fact": f"你与{cp.name}那桩{_DRAMA_KIND_CN.get(ch.kind, '因果')}未了，"
                     f"{npc.name}身为其{'同门' if (cp.sect and npc.sect == cp.sect) else '旧谊牵连'}，特来分说"}
            for _, _, _, npc, ch, cp in il]

        # 求助：态度 ≥+15、agenda ∈ {treasure, survive}、境界不高于玩家、同场
        hl = []
        for npc in npcs:
            if att[npc.id] < 15 or npc.location != player.location:
                continue
            if int(npc.realm.tier) > int(player.realm.tier):
                continue
            try:
                from core.npc_agenda import ensure_agenda

                agenda = (ensure_agenda(npc) or {}).get("agenda_type") or ""
            except Exception:
                agenda = ""
            if agenda not in ("treasure", "survive"):
                continue
            hl.append((-att[npc.id], -_born(npc), npc, agenda))
        hl.sort(key=lambda x: (x[0], x[1]))
        cands["help"] = [
            {"npc": npc, "agenda": agenda,
             "fact": f"{npc.name}在{player.location}"
                     f"{'为一桩寻宝机缘犯难' if agenda == 'treasure' else '为一桩存身之难犯愁'}"}
            for _, _, npc, agenda in hl]

        # 示好：(a) en 链 1 游戏日内了结；(b) 1 游戏日内 RELATION 正向跨档留痕未消费
        fl = []
        for ch in chains:
            if ch.kind == "en" and ch.status == "resolved" \
                    and float(ch.resolved_at or 0) >= t - SECONDS_PER_GAME_DAY:
                npc = by_id.get(ch.counterparty_id)
                if npc is not None:
                    fl.append((0, -float(ch.resolved_at or 0), npc, None))
        if not fl:
            try:
                from core.relations import parse_relation_row
                from storage.db import EventLedgerRepository

                rows = EventLedgerRepository.query_by_type_for_target(
                    player.id, type="RELATION", limit=30)
                consumed = set(quota.get("favor_consumed_ts") or [])
                for row in rows:
                    item = parse_relation_row(row)
                    if item is None:
                        continue
                    if float(item["ts"]) < t - SECONDS_PER_GAME_DAY:
                        continue
                    if int(item["delta"]) <= 0 \
                            or item["after_label"] not in ("friendly", "ally"):
                        continue
                    if float(item["ts"]) in consumed:
                        continue
                    npc = by_id.get(item["npc_id"])
                    if npc is not None:
                        fl.append((1, -float(item["ts"]), npc, float(item["ts"])))
            except Exception:
                pass
        fl.sort(key=lambda x: (x[0], x[1]))
        cands["favor"] = [
            {"npc": npc, "favor_ts": favor_ts, "fact": "前番恩义未曾言谢"}
            for _, _, npc, favor_ts in fl]

        # ---- 优先级 + 频控闸 → 至多新建 1 件（同类候选逐个过闸） ----
        chosen = None
        chosen_type = ""
        for dtype in DRAMA_PRIORITY:
            if dtype in DRAMA_COUNTED and int(quota.get("count") or 0) >= DRAMA_DAILY_CAP:
                continue  # 总闸（示好不占额、不受此闸）
            for cand in cands.get(dtype) or []:
                if int((quota.get("npc_game_day") or {}).get(cand["npc"].id, -1)) == game_day:
                    continue  # 同人闸（含示好）
                chosen, chosen_type = cand, dtype
                break
            if chosen is not None:
                break
        if chosen is not None:
            cand = chosen
            dtype = chosen_type
            npc = cand["npc"]
            fresh_npc = CharacterRepository.get_by_id(npc.id) or npc
            text, source = DramaEngine._line(
                fresh_npc, player, dtype, att[npc.id], cand.get("fact") or "")
            import uuid as _uuid

            ev: Dict[str, Any] = {
                "id": "dr_" + _uuid.uuid4().hex[:10],
                "type": dtype,
                "npc_id": npc.id,
                "npc_name": npc.name,
                "chain_id": (cand.get("chain").id if cand.get("chain") is not None else ""),
                "promise_id": (cand.get("promise").id if cand.get("promise") is not None else ""),
                "text": text,
                "source": source,
                "options": [dict(o) for o in DRAMA_OPTIONS[dtype]],
                "created_at": t,
                "expires_at": t + 86400.0,
            }
            # 呈现时先兆/自动落账（§5.3）
            if dtype == "betrayal":
                try:
                    from core import rumors as _rum

                    _rum.add_rumor(
                        f"风闻【{npc.name}】与【{player.name}】之间那桩未了之诺，怕是要生变故。",
                        origin=npc.name, tags=["betrayal", npc.name], truth=0.85, now=t)
                except Exception:
                    pass
                nuo = next((c for c in fermenting
                            if c.kind == "nuo" and c.counterparty_id == npc.id), None)
                if nuo is not None:
                    try:
                        from core.karma_chains import KarmaChainEngine

                        KarmaChainEngine.nudge_ferment(nuo.id, days=-2, now=t)
                        ev["chain_id"] = nuo.id
                    except Exception:
                        pass
            elif dtype == "favor":
                # 赠礼是 NPC 自有灵石的转移，非发放（双方 Repository 落盘）
                try:
                    amount = min(20, max(0, int(fresh_npc.spirit_stones or 0)))
                    if amount > 0:
                        fresh_npc.spirit_stones -= amount
                        CharacterRepository.save(fresh_npc)
                        player.spirit_stones = int(player.spirit_stones or 0) + amount
                        CharacterRepository.save(player)
                    shift_attitude(fresh_npc, player.id, 3, reason="戏剧·示好")
                except Exception:
                    pass
                if cand.get("favor_ts") is not None:
                    quota.setdefault("favor_consumed_ts", []).append(float(cand["favor_ts"]))
            # 频控记账（计件时点 = 新建时）
            quota.setdefault("npc_game_day", {})[npc.id] = game_day
            if dtype in DRAMA_COUNTED:
                quota["count"] = int(quota.get("count") or 0) + 1
            _save_drama_quota(player.id, quota)
            pending.append(ev)
            _save_drama_pending(player.id, pending)
            return [ev]
        _save_drama_quota(player.id, quota)
        return []

    # ---------------- 待回应队列读口（供 briefing 集成与 /回应 列表） ----------------
    @staticmethod
    def list_pending(player: Character, *,
                     now: Optional[float] = None) -> List[Dict[str, Any]]:
        t = now if now is not None else time.time()
        if player is None:
            return []
        return _load_drama_pending(player.id, t)

    @staticmethod
    def queue_item_for(event: Dict[str, Any]) -> Dict[str, Any]:
        """§8.2 入局 queue 的 drama 项形状（briefing 侧拼装调用口）。"""
        return {
            "kind": "drama",
            "priority": 2,
            "title": f"{DRAMA_TYPES_CN.get(event.get('type'), '戏剧')} · {event.get('npc_name', '')}",
            "text": event.get("text", ""),
            "ref_id": event.get("id", ""),
            "target": {"command": f"/回应 {event.get('id', '')}"},
            "ts": float(event.get("created_at") or 0),
            "options": [dict(o) for o in (event.get("options") or [])],
        }

    @staticmethod
    def panel_text(player: Character, *,
                   now: Optional[float] = None) -> str:
        pend = DramaEngine.list_pending(player, now=now)
        if not pend:
            return "眼下无待回应的戏剧。江湖平静，各安其道。"
        lines = ["【待回应】有人寻上门来，账要当面算："]
        for e in pend:
            opts = " / ".join(f"{o['key']} {o['label']}" for o in e.get("options") or [])
            lines.append(
                f"· [{e['id']}] {DRAMA_TYPES_CN.get(e['type'], e['type'])}"
                f" · {e.get('npc_name', '')}：{e.get('text', '')}（{opts}）")
        lines.append("回应：/回应 <id> <选项key>")
        return "\n".join(lines)

    # ---------------- 回应落账（§5.3；后果全落既有系统） ----------------
    @staticmethod
    def respond(player: Character, drama_id: str, option_key: str, *,
                now: Optional[float] = None,
                fight_fn=None) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if player is None:
            return {"success": False, "error": "角色不存在。"}
        pending = _load_drama_pending(player.id, t)
        ev = next((e for e in pending if e.get("id") == drama_id), None)
        if ev is None:
            return {"success": False, "error": "这场戏已散场或不存在。"}
        keys = {o.get("key") for o in (ev.get("options") or [])}
        if option_key not in keys:
            return {"success": False, "error": "无此回应选项。"}
        dtype = ev.get("type")
        npc_name = ev.get("npc_name") or ""
        npc = CharacterRepository.get_by_id(ev.get("npc_id") or "")
        result: Dict[str, Any] = {
            "success": True, "drama_id": drama_id, "type": dtype,
            "npc_id": ev.get("npc_id") or "", "npc_name": npc_name,
        }

        def _chain():
            cid = ev.get("chain_id") or ""
            if not cid:
                return None
            try:
                from storage.db import KarmaChainRepository

                return KarmaChainRepository.get(cid)
            except Exception:
                return None

        if dtype == "help" and option_key == "accept":
            try:
                from core.goals import GoalEngine
                from core.npc_agenda import ensure_agenda

                agenda = ""
                if npc is not None:
                    agenda = (ensure_agenda(npc) or {}).get("agenda_type") or ""
                need = "寻宝机缘" if agenda == "treasure" else "存身之难"
                r = GoalEngine.add_opportunity(
                    player, f"{npc_name}的求助",
                    f"{npc_name}在{player.location}为{need}相求，望你援手。")
            except Exception:
                r = {"success": False, "error": "目标挂接失败。"}
            if not r.get("success"):
                return {"success": False,
                        "error": r.get("error") or "机缘目标未能挂上。"}
            try:
                CharacterRepository.save(player)
            except Exception:
                pass
            result["goal"] = r.get("goal")
            result["message"] = f"已应下{npc_name}所求，机缘记入目标。"
        elif dtype == "help" and option_key == "decline":
            if npc is not None:
                shift_attitude(npc, player.id, -2, reason="戏剧·求助被拒")
            result["message"] = f"你婉拒了{npc_name}，对方神色一黯。"
        elif dtype == "favor" and option_key == "ack":
            result["message"] = f"你收下了{npc_name}的心意。"
        elif dtype == "provoke" and option_key == "fight":
            result["action"] = "fight"
            if fight_fn is not None:
                result["fight"] = fight_fn(npc_name)
            result["message"] = f"你应下{npc_name}的挑衅——斗法见分晓。"
        elif dtype == "provoke" and option_key == "avoid":
            try:
                from core import rumors as _rum

                _rum.note_avoid_fight(player.name, npc_name)
            except Exception:
                pass
            result["message"] = f"你避而不战，{npc_name}冷哼一声，自去了。"
        elif dtype == "betrayal" and option_key == "confront":
            # 只做呈现转向：诺言/链的结算仍走其既有路径，戏剧不提前结算
            result["action"] = "talk"
            result["message"] = f"你决定与{npc_name}当面摊牌，把旧账说清。"
        elif dtype == "involvement" and option_key == "mediate":
            chain = _chain()
            third_att = 0
            if npc is not None:
                try:
                    third_att = int(attitude_toward(npc, player.id).get("value") or 0)
                except Exception:
                    third_att = 0
            if chain is not None and third_att >= 15:
                try:
                    from core.karma_chains import KarmaChainEngine

                    if chain.kind == "en":
                        KarmaChainEngine.nudge_ferment(chain.id, days=-3, now=t)
                    elif chain.kind in ("chou", "xue"):
                        KarmaChainEngine.nudge_strength(chain.id, delta=-1, now=t)
                except Exception:
                    pass
                if npc is not None:
                    shift_attitude(npc, player.id, 3, reason="戏剧·牵连劝和")
                result["mediated"] = True
                result["message"] = f"{npc_name}被你说动，愿从中斡旋，因果稍缓。"
            else:
                result["mediated"] = False
                result["message"] = f"{npc_name}摇头不应——这一劝，没劝动。"
        elif dtype == "involvement" and option_key == "harden":
            if npc is not None:
                shift_attitude(npc, player.id, -3, reason="戏剧·牵连硬顶")
            chain = _chain()
            if chain is not None and chain.kind in ("chou", "xue"):
                try:
                    from core.karma_chains import KarmaChainEngine

                    KarmaChainEngine.nudge_strength(chain.id, delta=1, now=t)
                except Exception:
                    pass
            result["message"] = f"你硬顶回去，{npc_name}脸色铁青——梁子更紧了。"
        else:
            return {"success": False, "error": "无此回应选项。"}

        _save_drama_pending(
            player.id, [e for e in pending if e.get("id") != drama_id])
        return result
