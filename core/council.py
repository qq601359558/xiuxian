"""
长老议政（F08）：宗门定期议题 → 长老立场（agenda/性情确定性推导）→ 玩家投票/游说
→ 多数决惰性结算 → 效果落宗门状态（world_state）+ 世情播报。
全程规则裁决，零 AI 依赖；状态存 world_state KV，不建表、不改 models。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from config import SECTS_CONFIG
from core.models import Character, CharacterStatus
from storage.db import WorldStateRepository

# ==================== 常量（灰度口径，见 docs/compose/spec/council.md） ====================
COUNCIL_VOTE_WINDOW_SECONDS = 7200      # 投票窗口：现实 2h（与月俸同节律）
COUNCIL_INTERVAL_SECONDS = 3600         # 结算后 1h 开下一场
COUNCIL_LOBBY_BASE_COST = 60            # 游说基础灵石（按该长老本场被游说次数递增）
COUNCIL_LOBBY_MAX_PER_ELDER = 2         # 每长老本场被游说上限（全宗合计）
COUNCIL_LOBBY_MAX_PER_PLAYER = 3        # 每玩家本场游说上限
COUNCIL_LOBBY_RESIST_SCORE = -2         # 原始立场分 ≤ 此值 = 铁杆反对，游说不入
COUNCIL_EFFECT_CAPS = {"vault": 400, "prestige": 15, "morale": 15}
COUNCIL_STATE_DEFAULTS = {"vault": 1000, "prestige": 50, "morale": 50}
COUNCIL_LEADER_RANKS = ("掌门", "宗主", "会长")
COUNCIL_VIRTUAL_AGENDAS = ("patrol", "social", "seclusion")
COUNCIL_VIRTUAL_NAMES = ("值年虚席·甲", "值年虚席·乙", "值年虚席·丙")

# 议题模板池：agenda 亲和（六维）/ traits 修正 / 长老发言（本地模板）/ 结算效果
COUNCIL_TOPICS: List[Dict[str, Any]] = [
    {
        "id": "mining",
        "name": "开矿增收",
        "desc": "开掘宗门后山三阶灵矿，充盈金库；矿工劳顿，士气稍挫。",
        "agenda": {"treasure": 2, "social": 1, "seclusion": -1, "revenge": -1, "patrol": 0, "survive": 0},
        "traits": [("greed", 0.7, 1), ("caution", 0.7, -1)],
        "lines": {
            "support": ["灵矿在山，不取何待？金库充盈，满门受益。", "开源方能节流，此议当行。"],
            "oppose": ["掘山伤脉，涸泽而渔，老夫不取。", "矿利虽厚，人心易躁，当慎。"],
            "neutral": ["利弊参半，老夫且听诸位高论。"],
        },
        "effects": {"pass": {"vault": 300, "morale": -5}, "fail": {"morale": 2}},
    },
    {
        "id": "war",
        "name": "对外开战",
        "desc": "邻宗屡犯边境，举兵讨之；胜则扬威，败则伤本。",
        "agenda": {"revenge": 2, "patrol": 1, "seclusion": -2, "survive": -2, "treasure": -1, "social": 0},
        "traits": [("wrath", 0.7, 1), ("caution", 0.7, -1)],
        "lines": {
            "support": ["犯我门墙者，虽远必诛！", "剑已出鞘，岂能空回？"],
            "oppose": ["兵者凶器，宗门根基经不起连年烽火。", "忍一时之气，保百年之业。"],
            "neutral": ["战和两难，老夫不置可否。"],
        },
        "effects": {"pass": {"prestige": 12, "vault": -150, "morale": 8}, "fail": {"prestige": -3}},
    },
    {
        "id": "festival",
        "name": "举办祭典",
        "desc": "大办开宗祭典，宴请四方；耗费不菲，却振士气、扬声名。",
        "agenda": {"social": 2, "patrol": 1, "seclusion": -1, "revenge": 0, "treasure": 0, "survive": 0},
        "traits": [("wrath", 0.7, -1)],
        "lines": {
            "support": ["祭典聚人心，正该热闹一番。", "声名远播，门人同光，此议甚好。"],
            "oppose": ["铺张靡费，非修行人所为。", "虚名而已，老夫不喜。"],
            "neutral": ["办亦可，不办亦可，老夫随缘。"],
        },
        "effects": {"pass": {"vault": -120, "morale": 12, "prestige": 6}, "fail": {"morale": -4}},
    },
    {
        "id": "recruit",
        "name": "广纳门徒",
        "desc": "开山门广收弟子，壮大门楣；需贴补新进用度。",
        "agenda": {"social": 1, "patrol": 1, "seclusion": -1, "survive": 1, "revenge": 0, "treasure": 0},
        "traits": [("caution", 0.7, -1)],
        "lines": {
            "support": ["薪火相传，宗门方能不绝。", "多收良才，何乐不为？"],
            "oppose": ["来历不明者众，恐引狼入室。", "贵精不贵多，老夫以为不妥。"],
            "neutral": ["收徒一事，老夫且看掌门意思。"],
        },
        "effects": {"pass": {"prestige": 8, "morale": 4, "vault": -60}, "fail": {}},
    },
    {
        "id": "array",
        "name": "修缮大阵",
        "desc": "护山大阵年久失修，出资修缮；耗资颇巨，却保满门安稳。",
        "agenda": {"patrol": 1, "seclusion": 1, "survive": 1, "treasure": -1, "social": 0, "revenge": 0},
        "traits": [("caution", 0.7, 1)],
        "lines": {
            "support": ["大阵是满门的命根子，再贵也得修。", "未雨绸缪，方为长久之计。"],
            "oppose": ["耗资太过，金库要被掏空了。", "阵尚能用，何必急于一时？"],
            "neutral": ["修与不修，老夫都无不可。"],
        },
        "effects": {"pass": {"vault": -200, "prestige": 5, "morale": 3}, "fail": {"morale": -3}},
    },
]

_TOPIC_BY_ID = {t["id"]: t for t in COUNCIL_TOPICS}
_STATE_LABEL = {"vault": "金库", "prestige": "声望", "morale": "士气"}
_STANCE_LABEL = {"support": "支持", "oppose": "反对", "neutral": "中立"}


def topic_by_id(topic_id: str) -> Dict[str, Any]:
    return _TOPIC_BY_ID.get(topic_id) or COUNCIL_TOPICS[0]


def stance_score(topic_id: str, agenda_type: str, traits: Optional[Dict[str, Any]] = None) -> int:
    """立场分（纯函数、确定性）：议题×议程亲和 + 议题×性情修正"""
    topic = topic_by_id(topic_id)
    score = int((topic.get("agenda") or {}).get(agenda_type or "", 0))
    traits = traits or {}
    for trait, threshold, delta in topic.get("traits") or []:
        try:
            if float(traits.get(trait) or 0) >= threshold:
                score += int(delta)
        except (TypeError, ValueError):
            continue
    return score


def _tier_to_stance(tier: int) -> str:
    if tier >= 1:
        return "support"
    if tier <= -1:
        return "oppose"
    return "neutral"


def stance_of(topic_id: str, seat: Dict[str, Any], steps: int = 0) -> str:
    """席位有效立场 = 基础立场（按 score 定档）向支持位移 steps 档后钳制"""
    score = stance_score(topic_id, seat.get("agenda_type") or "", seat.get("traits"))
    tier = 1 if score >= 1 else (-1 if score <= -1 else 0)
    tier = max(-1, min(1, tier + int(steps or 0)))
    return _tier_to_stance(tier)


def _is_npc(c: Character) -> bool:
    uid = str(c.user_id)
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def _is_leader_rank(rank: str) -> bool:
    rank = rank or ""
    return ("长老" in rank) or (rank in COUNCIL_LEADER_RANKS)


def _session_key(sect: str) -> str:
    return f"sect_council:{sect}"


def _state_key(sect: str) -> str:
    return f"sect_state:{sect}"


def _fmt_remain(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, m = divmod(seconds // 60, 60)
    if h:
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分"
    return "片刻"


def _elder_line(topic_id: str, seat: Dict[str, Any], stance: str) -> str:
    lines = (topic_by_id(topic_id).get("lines") or {}).get(stance) or [""]
    if not lines:
        return ""
    digest = hashlib.md5(f"{seat.get('id')}|{topic_id}|{stance}".encode("utf-8")).hexdigest()
    return lines[int(digest, 16) % len(lines)]


class CouncilEngine:
    """长老议政引擎（规则单点，双端共用）"""

    # ---------------- 宗门状态 ----------------
    @staticmethod
    def get_sect_state(sect: str) -> Dict[str, int]:
        raw: Dict[str, Any] = {}
        try:
            raw = WorldStateRepository.get(_state_key(sect)) or {}
        except Exception:
            raw = {}
        out: Dict[str, int] = {}
        for key, default in COUNCIL_STATE_DEFAULTS.items():
            try:
                value = int(raw.get(key, default))
            except (TypeError, ValueError):
                value = default
            if key == "vault":
                value = max(0, value)
            else:
                value = max(0, min(100, value))
            out[key] = value
        return out

    @staticmethod
    def _save_sect_state(sect: str, state: Dict[str, int]) -> None:
        # 合并写：只覆盖三维内务键，保留 KV 中其他键不被整表抹掉
        try:
            raw = WorldStateRepository.get(_state_key(sect)) or {}
            merged = dict(raw)
            merged.update(state)
            WorldStateRepository.set(_state_key(sect), merged)
        except Exception:
            pass

    # ---------------- 长老席位 ----------------
    @staticmethod
    def elder_seats(sect: str, chars: Optional[List[Character]] = None) -> List[Dict[str, Any]]:
        """本宗在册长老席位（NPC 编制）；为空时以 3 名虚席兜底"""
        if chars is None:
            from storage.db import CharacterRepository

            chars = CharacterRepository.list_all_alive()
        seats: List[Dict[str, Any]] = []
        for c in chars:
            if c.sect != sect or not _is_npc(c):
                continue
            if c.status == CharacterStatus.DEAD:
                continue
            if not _is_leader_rank(c.sect_rank):
                continue
            agenda_type = ""
            traits: Dict[str, Any] = {}
            try:
                from core.npc_agenda import ensure_agenda

                agenda_type = (ensure_agenda(c) or {}).get("agenda_type") or ""
            except Exception:
                agenda_type = ""
            try:
                from core.npc_mind import ensure_mind

                traits = (ensure_mind(c) or {}).get("traits") or {}
            except Exception:
                traits = {}
            seats.append({
                "id": c.id,
                "name": c.name,
                "rank": c.sect_rank or "",
                "virtual": False,
                "agenda_type": agenda_type,
                "traits": traits,
            })
        seats.sort(key=lambda s: s["name"])
        if seats:
            return seats
        return [
            {
                "id": f"virtual:{sect}:{i}",
                "name": COUNCIL_VIRTUAL_NAMES[i],
                "rank": "虚席",
                "virtual": True,
                "agenda_type": COUNCIL_VIRTUAL_AGENDAS[i],
                "traits": {},
            }
            for i in range(len(COUNCIL_VIRTUAL_NAMES))
        ]

    # ---------------- 会话生命周期（惰性推进） ----------------
    @staticmethod
    def _load_session(sect: str) -> Optional[Dict[str, Any]]:
        try:
            return WorldStateRepository.get(_session_key(sect))
        except Exception:
            return None

    @staticmethod
    def _save_session(sect: str, session: Dict[str, Any]) -> None:
        try:
            WorldStateRepository.set(_session_key(sect), session)
        except Exception:
            pass

    @staticmethod
    def _open_session(sect: str, session_no: int, now: float) -> Dict[str, Any]:
        topic = COUNCIL_TOPICS[session_no % len(COUNCIL_TOPICS)]
        session = {
            "session_no": session_no,
            "topic_id": topic["id"],
            "opened_at": now,
            "closes_at": now + COUNCIL_VOTE_WINDOW_SECONDS,
            "next_open_at": now + COUNCIL_VOTE_WINDOW_SECONDS + COUNCIL_INTERVAL_SECONDS,
            "votes": {},
            "lobby_attempts": {},
            "lobby_steps": {},
            "lobby_by_player": {},
            "settled": False,
            "result": None,
        }
        CouncilEngine._save_session(sect, session)
        return session

    @staticmethod
    def _advance(sect: str, now: float) -> "tuple[Dict[str, Any], bool]":
        """惰性推进：开场/结算/再开场。返回 （当前会话， 是否有变更）"""
        session = CouncilEngine._load_session(sect)
        if not session:
            return CouncilEngine._open_session(sect, 0, now), True
        changed = False
        if not session.get("settled") and now >= float(session.get("closes_at") or 0):
            CouncilEngine.settle(sect, session, now=now)
            session = CouncilEngine._load_session(sect) or session
            changed = True
        if session.get("settled") and now >= float(session.get("next_open_at") or 0):
            session = CouncilEngine._open_session(sect, int(session.get("session_no") or 0) + 1, now)
            changed = True
        return session, changed

    @staticmethod
    def advance(sect: str, now: Optional[float] = None) -> Dict[str, Any]:
        session, _ = CouncilEngine._advance(sect, now if now is not None else time.time())
        return session

    # ---------------- 结算（幂等） ----------------
    @staticmethod
    def tally(
        sect: str, session: Dict[str, Any], seats: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, int]:
        """计票：长老有效立场（含游说位移）+ 玩家票，中立不入分母"""
        topic_id = session.get("topic_id") or ""
        steps_map = session.get("lobby_steps") or {}
        support = oppose = 0
        for seat in (seats if seats is not None else CouncilEngine.elder_seats(sect)):
            stance = stance_of(topic_id, seat, int(steps_map.get(seat["id"]) or 0))
            if stance == "support":
                support += 1
            elif stance == "oppose":
                oppose += 1
        for side in (session.get("votes") or {}).values():
            if side == "support":
                support += 1
            elif side == "oppose":
                oppose += 1
        return {"support": support, "oppose": oppose}

    @staticmethod
    def settle(
        sect: str,
        session: Dict[str, Any],
        now: Optional[float] = None,
        seats: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """多数决结算：已 settled 直接返回快照，效果绝不重复落账"""
        if session.get("settled"):
            return session
        # 复查 KV：同一会话的两份独立快照先后 settle 时，以落盘状态为准防双重落账
        # （注意 session_no 可为 0，禁用 `or` 哨兵以免 falsy 误判）
        stored = CouncilEngine._load_session(sect)
        stored_no = stored.get("session_no") if stored else None
        this_no = session.get("session_no")
        if stored is not None and stored.get("settled") and stored_no is not None and stored_no == this_no:
            return stored
        now = now if now is not None else time.time()
        topic = topic_by_id(session.get("topic_id") or "")
        counts = CouncilEngine.tally(sect, session, seats=seats)
        passed = counts["support"] > counts["oppose"]
        raw_effects = (topic.get("effects") or {}).get("pass" if passed else "fail") or {}
        state = CouncilEngine.get_sect_state(sect)
        applied: Dict[str, int] = {}
        for key, delta in raw_effects.items():
            cap = COUNCIL_EFFECT_CAPS.get(key, 0)
            delta = max(-cap, min(cap, int(delta)))
            if delta == 0:
                continue
            before = state[key]
            if key == "vault":
                state["vault"] = max(0, before + delta)
            else:
                state[key] = max(0, min(100, before + delta))
            # 快照/播报记实际落账差值（经下限/上限钳制后），不记名义增量
            actual = state[key] - before
            if actual:
                applied[key] = actual
        CouncilEngine._save_sect_state(sect, state)
        session["settled"] = True
        session["result"] = {
            "passed": passed,
            "support": counts["support"],
            "oppose": counts["oppose"],
            "effects": applied,
            "settled_at": now,
        }
        CouncilEngine._save_session(sect, session)
        if passed:
            # 势力版图（F09）：议政通过为本宗总坛区域扬名；引擎内取真实墙钟，
            # 不透传本结算的注入逻辑时刻（防污染衰减时间基线）
            try:
                from core.atlas import AtlasEngine

                AtlasEngine.record_council(sect)
            except Exception:
                pass
        CouncilEngine._broadcast(sect, topic, session["result"])
        return session

    @staticmethod
    def _broadcast(sect: str, topic: Dict[str, Any], result: Dict[str, Any]) -> None:
        try:
            import core.jianghu as jianghu

            verdict = "通过" if result.get("passed") else "否决"
            eff = result.get("effects") or {}
            eff_txt = "、".join(
                f"{_STATE_LABEL.get(k, k)}{'+' if v > 0 else ''}{v}" for k, v in eff.items()
            ) or "宗门状态不变"
            summary = (
                f"【{sect}】长老议政「{topic.get('name')}」{verdict}"
                f"（支持 {result.get('support', 0)} : 反对 {result.get('oppose', 0)}），{eff_txt}。"
            )
            jianghu.append_event(
                kind="sect_council",
                actor_names=[sect],
                location=(SECTS_CONFIG.get(sect) or {}).get("headquarters", ""),
                summary=summary,
                rule_result={
                    "topic": topic.get("id"),
                    "passed": bool(result.get("passed")),
                    "support": result.get("support", 0),
                    "oppose": result.get("oppose", 0),
                    "effects": eff,
                },
                narrative=summary,
                source="rule",
                # 播报时刻取真实墙钟（append_event 默认 time.time()）：会话的逻辑结算时刻
                # 只存 result.settled_at，不用它给世情排序，避免注入时刻污染公共信息流。
            )
        except Exception:
            pass

    # ---------------- 玩家动作 ----------------
    @staticmethod
    def _reject(message: str, dirty: bool = False) -> Dict[str, Any]:
        return {"success": False, "message": message, "dirty": dirty}

    @staticmethod
    def _dead(char: Character) -> bool:
        return char.status == CharacterStatus.DEAD or char.lifespan.is_dead()

    @staticmethod
    def panel_text(
        char: Character,
        now: Optional[float] = None,
        seats: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if not char.sect:
            return "【宗门议政】散修无宗可议。先 /拜入 <宗门>，再来与长老共商门中大事。"
        now = now if now is not None else time.time()
        sect = char.sect
        session, _ = CouncilEngine._advance(sect, now)
        state = CouncilEngine.get_sect_state(sect)
        topic = topic_by_id(session.get("topic_id") or "")
        lines = [
            f"【宗门议政】{sect} · 第 {int(session.get('session_no') or 0) + 1} 场",
            f"宗门状态：金库 {state['vault']} 灵石 · 声望 {state['prestige']} · 士气 {state['morale']}",
        ]
        result = session.get("result")
        if session.get("settled") and result:
            verdict = "通过" if result.get("passed") else "否决"
            eff = result.get("effects") or {}
            eff_txt = "、".join(
                f"{_STATE_LABEL.get(k, k)}{'+' if v > 0 else ''}{v}" for k, v in eff.items()
            ) or "宗门状态不变"
            lines.append(
                f"上场议题：「{topic.get('name')}」{verdict}"
                f"（支持 {result.get('support', 0)} : 反对 {result.get('oppose', 0)}），{eff_txt}。"
            )
            lines.append(
                f"下一场议政将于 {_fmt_remain(float(session.get('next_open_at') or now) - now)} 后开启。"
            )
            return "\n".join(lines)

        steps_map = session.get("lobby_steps") or {}
        lines.append(f"本场议题：「{topic.get('name')}」— {topic.get('desc')}")
        lines.append(f"投票截止：{_fmt_remain(float(session.get('closes_at') or now) - now)} 后（多数决，平局否决）")
        lines.append("长老席位与立场：")
        for seat in (seats if seats is not None else CouncilEngine.elder_seats(sect)):
            steps = int(steps_map.get(seat["id"]) or 0)
            stance = stance_of(session.get("topic_id") or "", seat, steps)
            tags = []
            if seat.get("virtual"):
                tags.append("虚席")
            if steps:
                tags.append("经游说")
            tag_txt = f"（{'、'.join(tags)}）" if tags else ""
            line = _elder_line(session.get("topic_id") or "", seat, stance)
            lines.append(
                f"· {seat['name']}（{seat.get('rank') or '长老'}）— {_STANCE_LABEL[stance]}{tag_txt}"
                + (f"：「{line}」" if line else "")
            )
        votes = session.get("votes") or {}
        p_support = sum(1 for v in votes.values() if v == "support")
        p_oppose = sum(1 for v in votes.values() if v == "oppose")
        mine = votes.get(char.id)
        mine_txt = _STANCE_LABEL.get(mine, "未投") if mine else "未投"
        lines.append(f"弟子投票：支持 {p_support} · 反对 {p_oppose}（你：{mine_txt}，截止前可改票）")
        lines.append("参与：/投票 支持|反对 · /游说 <长老名>（灵石拉票，铁杆长老油盐不进，虚席无从游说）")
        return "\n".join(lines)

    @staticmethod
    def panel_data(char: Character, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """议政面板结构（/议政 council 键；与 panel_text 同源）。散修为 None。"""
        if not char.sect:
            return None
        now = now if now is not None else time.time()
        sect = char.sect
        session, _ = CouncilEngine._advance(sect, now)
        state = CouncilEngine.get_sect_state(sect)
        topic = topic_by_id(session.get("topic_id") or "")
        base: Dict[str, Any] = {
            "sect": sect,
            "session_no": int(session.get("session_no") or 0) + 1,
            "vault": state["vault"],
            "prestige": state["prestige"],
            "morale": state["morale"],
            "topic": {
                "id": session.get("topic_id"),
                "name": topic.get("name"),
                "desc": topic.get("desc"),
            },
            "settled": bool(session.get("settled")),
        }
        if session.get("settled") and session.get("result"):
            result = session.get("result") or {}
            base["result"] = {
                "passed": result.get("passed"),
                "support": result.get("support", 0),
                "oppose": result.get("oppose", 0),
                "effects": result.get("effects") or {},
            }
            base["next_open_in_s"] = max(0.0, float(session.get("next_open_at") or now) - now)
            base["seats"] = []
            base["votes"] = {
                "support": int(result.get("support", 0)),
                "oppose": int(result.get("oppose", 0)),
                "mine": None,
            }
            return base
        steps_map = session.get("lobby_steps") or {}
        seats = []
        for seat in CouncilEngine.elder_seats(sect):
            steps = int(steps_map.get(seat["id"]) or 0)
            stance = stance_of(session.get("topic_id") or "", seat, steps)
            seats.append(
                {
                    "name": seat["name"],
                    "rank": seat.get("rank") or "长老",
                    "stance": stance,
                    "stance_cn": _STANCE_LABEL[stance],
                    "lobbied": steps > 0,
                    "virtual": bool(seat.get("virtual")),
                    "line": _elder_line(session.get("topic_id") or "", seat, stance),
                }
            )
        votes = session.get("votes") or {}
        p_support = sum(1 for v in votes.values() if v == "support")
        p_oppose = sum(1 for v in votes.values() if v == "oppose")
        base["closes_in_s"] = max(0.0, float(session.get("closes_at") or now) - now)
        base["seats"] = seats
        base["votes"] = {"support": p_support, "oppose": p_oppose, "mine": votes.get(char.id)}
        return base

    @staticmethod
    def vote(char: Character, side: str, now: Optional[float] = None) -> Dict[str, Any]:
        if CouncilEngine._dead(char):
            return CouncilEngine._reject("身死道消，议政之事已与你无关。")
        if not char.sect:
            return CouncilEngine._reject("散修无宗可议，不可投票。先 /拜入 <宗门>。")
        side_key = {
            "支持": "support", "赞成": "support", "support": "support",
            "反对": "oppose", "oppose": "oppose",
        }.get((side or "").strip())
        if not side_key:
            return CouncilEngine._reject("用法：/投票 支持|反对")
        now = now if now is not None else time.time()
        session, changed = CouncilEngine._advance(char.sect, now)
        if session.get("settled"):
            return CouncilEngine._reject("本场议政已结算，下场开启后再来投票。", dirty=changed)
        votes = session.setdefault("votes", {})
        prev = votes.get(char.id)
        votes[char.id] = side_key
        CouncilEngine._save_session(char.sect, session)
        topic = topic_by_id(session.get("topic_id") or "")
        verb = "改票为" if prev and prev != side_key else "投下"
        return {
            "success": True,
            "dirty": True,
            "message": (
                f"【议政投票】你已就「{topic.get('name')}」{verb}【{_STANCE_LABEL[side_key]}】。"
                f"截止前可再 /投票 改票。"
            ),
        }

    @staticmethod
    def void_dead_votes(char: Character) -> int:
        """死亡 sweep：清除死者所属宗门未结算场次 votes 中键为死者角色 id 的票。

        已结算场次快照不动（spec 裁定 3）；游说位移与已付费用沉没不退。
        返回清除票数（0/1；无宗门或无场次时为 0）。
        """
        if not getattr(char, "sect", None):
            return 0
        session = CouncilEngine._load_session(char.sect)
        if not session or session.get("settled"):
            return 0
        votes = session.get("votes") or {}
        if char.id not in votes:
            return 0
        del votes[char.id]
        session["votes"] = votes
        CouncilEngine._save_session(char.sect, session)
        return 1

    @staticmethod
    def lobby(
        char: Character,
        hint: str,
        now: Optional[float] = None,
        seats: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if CouncilEngine._dead(char):
            return CouncilEngine._reject("身死道消，议政之事已与你无关。")
        if not char.sect:
            return CouncilEngine._reject("散修无宗可议，不可游说。先 /拜入 <宗门>。")
        hint = (hint or "").strip()
        if not hint:
            return CouncilEngine._reject("用法：/游说 <长老名>")
        now = now if now is not None else time.time()
        session, changed = CouncilEngine._advance(char.sect, now)
        if session.get("settled"):
            return CouncilEngine._reject("本场议政已结算，下场开启后再来游说。", dirty=changed)
        topic_id = session.get("topic_id") or ""
        if seats is None:
            seats = CouncilEngine.elder_seats(char.sect)
        # 精确名优先，子串兜底（防短 hint 误中他人）
        seat = next((s for s in seats if s["name"] == hint), None)
        if seat is None:
            seat = next((s for s in seats if hint in s["name"] or s["name"] in hint), None)
        if seat is None:
            return CouncilEngine._reject(f"本宗长老席中无【{hint}】。/议政 查看席位。", dirty=changed)
        if seat.get("virtual"):
            return CouncilEngine._reject(f"【{seat['name']}】乃值年虚席，无形无迹，无从游说。", dirty=changed)
        steps_map = session.setdefault("lobby_steps", {})
        steps = int(steps_map.get(seat["id"]) or 0)
        attempts_map = session.setdefault("lobby_attempts", {})
        attempts = int(attempts_map.get(seat["id"]) or 0)
        if attempts >= COUNCIL_LOBBY_MAX_PER_ELDER:
            return CouncilEngine._reject(
                f"【{seat['name']}】本场已被游说 {attempts} 次，言多必失，不可再扰。", dirty=changed
            )
        if stance_of(topic_id, seat, steps) == "support":
            return CouncilEngine._reject(f"【{seat['name']}】已然赞同本场议题，不必游说。", dirty=changed)
        base_score = stance_score(topic_id, seat.get("agenda_type") or "", seat.get("traits"))
        if base_score <= COUNCIL_LOBBY_RESIST_SCORE:
            return CouncilEngine._reject(
                f"【{seat['name']}】对此议铁了心反对，油盐不进——灵石就不收你的了。", dirty=changed
            )
        by_player = session.setdefault("lobby_by_player", {})
        my_attempts = int(by_player.get(char.id) or 0)
        if my_attempts >= COUNCIL_LOBBY_MAX_PER_PLAYER:
            return CouncilEngine._reject(
                f"你本场已游说 {my_attempts} 次，门中大事不可一人操弄。", dirty=changed
            )
        cost = COUNCIL_LOBBY_BASE_COST * (attempts + 1)
        if char.spirit_stones < cost:
            return CouncilEngine._reject(
                f"游说需备礼 {cost} 灵石（随身 {char.spirit_stones}），不足。", dirty=changed
            )
        char.spirit_stones -= cost
        attempts_map[seat["id"]] = attempts + 1
        by_player[char.id] = my_attempts + 1
        steps_map[seat["id"]] = steps + 1
        CouncilEngine._save_session(char.sect, session)
        new_stance = stance_of(topic_id, seat, steps + 1)
        return {
            "success": True,
            "dirty": True,
            "cost": cost,
            "message": (
                f"【游说】备礼 {cost} 灵石拜会【{seat['name']}】，其立场松动，现为【{_STANCE_LABEL[new_stance]}】。"
                f"（该长老本场已被游说 {attempts + 1}/{COUNCIL_LOBBY_MAX_PER_ELDER} 次）"
            ),
        }
