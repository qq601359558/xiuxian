"""
局域网权威世界：内存态 + 与 SQLite 角色同步
多玩家共用一界；所有写操作在此串行化
"""
from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
import uuid
import random
from typing import Any, Dict, List, Optional

from storage.db import (
    init_db,
    CharacterRepository,
    ChronicleRepository,
    BountyRepository,
    KarmaLinkRepository,
    MarketListingRepository,
    LegacyRepository,
    AuthSessionRepository,
)
from core.models import Character, CharacterStatus, status_cn
from core.clock import WorldClock
from core.events import EventEngine
from core.heart_demon import HeartDemonEngine
from core.combat_fate import CombatFateEngine
from core.free_action import FreeActionEngine
from core.memory import RevengeEngine
from core.npc_agenda import NpcAgendaEngine
from core.npc_mind import NpcDialogueEngine
from core.legacy import LegacyAccount, LegacyEngine
from core.here import list_here, format_here
from core.profile import build_profile, format_profile
from core.npc_proactive import NpcProactiveEngine
from core.bounty import BountyEngine, bounty_status_cn
from core.market import MarketEngine, ListingStatus
from core.items import ItemEntity, ItemKind
from core.atlas import AtlasEngine
from core.ascension import AscensionEngine
from core.breakthrough import BreakthroughEngine
from core.protection import ProtectionEngine, is_conflict_zone
from core.goals import GoalEngine
from core.season import season_status_text, season_info
from core import qi as qi_mod
from core.leaderboard import LeaderboardEngine
from core.sect import (
    join_sect,
    leave_sect,
    claim_salary,
    promote,
    transmit_teaching,
    format_sect_board,
)
from core.secret_realm import SecretRealmEngine
from core.combat import CombatEngine
from core.adventure import AdventureEngine
from core.loot_equip import DigEngine, EquipEngine
from core.pets import PetEngine, active_pet as pet_active, level_for as pet_level_for
from core.farm import FarmEngine, split_sow_args
from core.quests import QuestEngine
from core.promises import PROMISE_KIND_ALIASES, PromiseEngine
from core.art_slots import ArtSlotEngine
from core.body_soul import BodySoulEngine
from core.heart_demon_state import DemonStateEngine
from core.books import BOOK_ITEM, BookEngine
from core.season import settle_apocalypse
from core import forge as forge_mod
from config import (
    WORLD_LOCATIONS,
    NPC_TICK_INTERVAL_SECONDS,
    LEGACY_BOOSTS,
    LEGACY_MAX_BOOSTS_PER_LIFE,
    BOUNTY_MAX_PER_TARGET,
    MARKET_MAX_LISTINGS,
    LIFESPAN_WARNING_YEARS,
)
from server.log import log_event
from ai.gate import gate
from ai.facts import build_fact_pack


class Session:
    def __init__(self, token: str, user_id: str, character_id: str):
        self.token = token
        self.user_id = user_id
        self.character_id = character_id
        self.created_at = time.time()
        self.pending_heart_demon: Optional[str] = None  # session id


# login-latency-fix §2.2.4（修订 R1）：有界获取 + 锁外回退。
# 登录/注册路径上 World.lock 的每一次获取都以 2 秒为界，禁止无界 with self.lock。
# 2 秒总界从进入 join/dead_payload 起算，含锁等待 + 锁外 DB 快照读 + 组装；
# _LOCK_SNAPSHOT_RESERVE_SECONDS 是给锁外快照读与组装预留的余量，取锁等待
# 到达 deadline-余量即放弃，保证整体仍在 2 秒内返回。余量取 0.3 秒：除快
# 照读外，还要覆盖 HTTP 层验密（PBKDF2）与响应开销造成的墙钟抖动。
LOCK_ACQUIRE_TIMEOUT_SECONDS = 2.0
_LOCK_SNAPSHOT_RESERVE_SECONDS = 0.3

SERVER_BUSY_MESSAGE = "世界正在演化，请稍后重试"


def is_db_locked_error(exc: BaseException) -> bool:
    """DB 争用类异常判定（playability-block1 B1-1）：sqlite3.OperationalError
    且消息含 locked/busy。此类异常是 tick/并发窗口的瞬时争用，注册/入世
    路径应转 WorldBusyError → 503 可重试，绝不裸 500；其余异常照旧抛。"""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


# ---- 交谈结构化呈现（chat-structure spec §B）：chat_lines 拼装助手 ----
# 语义：本次响应要在交谈视图新增呈现的行；前端只按字段渲染，不再解析 text。
# 每条 text 在此统一过呈现清洗（§C，幂等）；text 字段本身保持原样不动。
def _cl_sys(text: Any) -> Dict[str, Any]:
    from core.dialogue_text import clean_dialogue_text

    return {"who": "", "cls": "sys", "text": clean_dialogue_text(str(text or ""))}


def _cl_npc(who: Any, text: Any) -> Dict[str, Any]:
    from core.dialogue_text import clean_dialogue_text

    return {"who": str(who or ""), "cls": "npc", "text": clean_dialogue_text(str(text or ""))}


def _cl_text_lines(text: Any) -> List[Dict[str, Any]]:
    """整段文本逐行 → sys 行（开启问候/挂断/记忆等系统拼装段用）。"""
    return [_cl_sys(ln) for ln in str(text or "").split("\n") if ln.strip()]


def _cl_bystanders(rows: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for b in rows or []:
        if isinstance(b, dict):
            out.append(_cl_npc(b.get("who"), b.get("line")))
    return out


class WorldBusyError(Exception):
    """拿不到 World.lock 且该路径需要写操作（建角/收养/结算/发 token）。

    调用方（HTTP 层）应将其转为 503 SERVER_BUSY 可重试响应，且此前
    不得发生任何写操作（“繁忙即未写”，客户端原样重试安全）。
    读路径拿不到锁时不抛此异常，改为走锁外 DB 快照回退。
    """


class World:
    """进程内权威世界（局域网单服）"""

    def __init__(self, auto_tick: bool = True):
        init_db()
        self.lock = threading.RLock()
        # first-night 异步化（login-latency-fix §2.2.3）：单 flight / 每角色每世
        # 一次，同一时刻最多 4 个在跑；_first_night_lock 只 guard 这两个结构，
        # 与 World.lock 是两把不同的锁。
        self._first_night_lock = threading.Lock()
        self._first_night_inflight: set = set()
        self._first_night_status: Dict[str, str] = {}
        self._first_night_sem = threading.Semaphore(4)
        self.sessions: Dict[str, Session] = {}
        self.hd_sessions: Dict[str, Any] = {}  # HeartDemonSession
        self._stop_tick = False
        self._seed_npcs()
        # 启动即对时/追赶离线江湖
        try:
            from core.jianghu_sim import JianghuSimulator

            off = JianghuSimulator.simulate_offline()
            if off.get("waves"):
                try:
                    log_event("JIANGHU", "offline_catchup", **{k: off.get(k) for k in ("waves", "actions", "deaths", "breakthroughs")})
                except Exception:
                    pass
        except Exception:
            pass
        if auto_tick and NPC_TICK_INTERVAL_SECONDS > 0:
            self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
            self._tick_thread.start()

    def _tick_loop(self):
        """后台：按间隔推进 NPC（世界自己动）+ 离线波次"""
        while not self._stop_tick:
            try:
                time.sleep(NPC_TICK_INTERVAL_SECONDS)
                self._tick_once()
            except Exception:
                continue

    def _tick_once(self):
        """一轮 tick（playability-block1 B1-2 三段式）：AI 阶段移出 World.lock。

        分工：纯规则阶段维持锁内；agenda 与 director 两阶段走
        「锁内取快照（DTO）→ 锁外调 AI → 锁内复验落盘」——agenda 经
        NpcAgendaEngine.prepare/ai/apply_tick_world，director 经
        WorldDirector.prepare/propose/apply_cycle。持锁时长只计锁内段
        （hold_ms），整轮墙钟另记 wall_ms；phases 保留 agenda/director
        总时长键并增 *_prepare/*_ai/*_apply 分段键。单阶段异常仍按现状
        swallow，但记带阶段名的错误行。结算口径不变：规则结算仍在锁内
        段一完成，AI 只改叙事/提案内容，落盘前复验（见各引擎段三）。
        """
        t_start = time.time()
        self._tick_count = getattr(self, "_tick_count", 0) + 1
        try:
            log_event("TICK", "tick_start", tick_no=self._tick_count)
        except Exception:
            pass
        phases: Dict[str, int] = {}
        lock_hold_seconds = [0.0]

        def _run_phase(name: str, fn) -> None:
            t0 = time.time()
            try:
                fn()
            except Exception as e:
                try:
                    log_event("TICK", "tick_phase_error", phase=name, err=str(e)[:120])
                except Exception:
                    pass
            phases[name] = int((time.time() - t0) * 1000)

        def _locked_phase(name: str, fn) -> None:
            with self.lock:
                t0 = time.time()
                _run_phase(name, fn)
                lock_hold_seconds[0] += time.time() - t0

        def _unlocked_phase(name: str, fn) -> None:
            _run_phase(name, fn)

        def _jianghu():
            from core.jianghu_sim import JianghuSimulator

            JianghuSimulator.simulate_offline()

        _locked_phase("jianghu", _jianghu)

        # ---- agenda 三段式 ----
        _agenda_holder: Dict[str, Any] = {}

        def _agenda_prepare():
            _agenda_holder["prepared"] = NpcAgendaEngine.prepare_tick_world(max_npcs=3, force=False)

        _locked_phase("agenda_prepare", _agenda_prepare)

        def _agenda_ai():
            NpcAgendaEngine.ai_tick_world(_agenda_holder.get("prepared") or [])

        _unlocked_phase("agenda_ai", _agenda_ai)

        def _agenda_apply():
            NpcAgendaEngine.apply_tick_world(_agenda_holder.get("prepared") or [])

        _locked_phase("agenda_apply", _agenda_apply)
        phases["agenda"] = (
            phases.get("agenda_prepare", 0) + phases.get("agenda_ai", 0) + phases.get("agenda_apply", 0)
        )

        # ---- director 三段式 ----
        _director_holder: Dict[str, Any] = {}

        def _director_prepare():
            from core.world_director import WorldDirector

            plan, _early = WorldDirector.prepare_cycle(trigger="timer", force=False)
            _director_holder["plan"] = plan

        _locked_phase("director_prepare", _director_prepare)

        def _director_ai():
            plan = _director_holder.get("plan")
            if plan is not None:
                from core.world_director import WorldDirector

                _director_holder["proposal"] = WorldDirector.propose_cycle(plan)

        _unlocked_phase("director_ai", _director_ai)

        def _director_apply():
            plan = _director_holder.get("plan")
            proposal = _director_holder.get("proposal")
            if plan is not None and proposal is not None:
                from core.world_director import WorldDirector

                cleaned, source, error = proposal
                WorldDirector.apply_cycle(plan, cleaned, source, error)

        _locked_phase("director_apply", _director_apply)
        phases["director"] = (
            phases.get("director_prepare", 0) + phases.get("director_ai", 0) + phases.get("director_apply", 0)
        )

        def _world_arc():
            from core import world_arc

            world_arc.tick_world(max_advance=2)

        _locked_phase("world_arc", _world_arc)

        def _faction():
            from core import faction

            faction.tick_world()

        _locked_phase("faction", _faction)

        def _player_echo():
            from core import player_echo

            player_echo.decay_echoes()

        _locked_phase("player_echo", _player_echo)

        def _era_reentry():
            from core import era_reentry

            era_reentry.tick()

        _locked_phase("era_reentry", _era_reentry)

        def _auction():
            from core.trade import AuctionEngine

            try:
                AuctionEngine.advance(react=True)
            except Exception as e:
                try:
                    log_event("AUCTION", "advance_error", err=str(e)[:120])
                except Exception:
                    pass

        _locked_phase("auction", _auction)
        hold_ms = int(lock_hold_seconds[0] * 1000)
        wall_ms = int((time.time() - t_start) * 1000)
        try:
            log_event("TICK", "tick_end", tick_no=self._tick_count, hold_ms=hold_ms, wall_ms=wall_ms, phases=phases)
        except Exception:
            pass

    def stop_tick(self):
        self._stop_tick = True

    def _seed_npcs(self):
        try:
            from core.npc_roster import seed_roster
            seed_roster()
        except Exception:
            # 回退：至少 3 人
            try:
                alive = CharacterRepository.list_all_alive()
                if len(alive) >= 3:
                    return
                c1 = WorldClock.create_new_character("npc_01", "陆仁贾")
                c1.spirit_stones = 380
                c1.location = "青云山外围"
                CharacterRepository.save(c1)
                c2 = WorldClock.create_new_character("npc_02", "血刀老祖")
                c2.realm.tier = 2
                c2.spirit_stones = 1200
                c2.karma.add_sin(280)
                c2.location = "黑风峡谷"
                CharacterRepository.save(c2)
                c3 = WorldClock.create_new_character("npc_03", "云鹤道人")
                c3.realm.tier = 2
                c3.realm.sub_tier = 2
                c3.karma.add_merit(150)
                c3.spirit_stones = 650
                c3.location = "古修士洞府残址"
                CharacterRepository.save(c3)
            except Exception:
                pass

    # ---------------- 会话 ----------------
    def join(self, name: str, user_id: Optional[str] = None, *, auto_rebirth: bool = False,
             _deadline: Optional[float] = None) -> Dict[str, Any]:
        """入世双轨（合并裁定）：

        - 显式 user_id（已认证）：严格按 uid 恢复本账户角色，绝不按道号收养
          他人同名号（分支账户隔离 / PROX-9）；角色已死时默认返回 dead_payload
          （main §2.6，建角须显式 /转世），auto_rebirth=True 时直接结算旧世、
          开启新一世（HTTP /join 凭据/令牌路径的分支语义）。
        - 无 user_id（匿名局域网，main 口径）：按道号收养仍存活的非 NPC 玩家号
          （换设备/清缓存），查无则以 lan_ 匿名号开新世。
        冲突裁定留痕：分支原签名要求 user_id 必传（TypeError 于缺省调用），
        与 main 约二十处 join(name) 匿名调用点同形冲突，不可兼得——取 main
        匿名语义，分支的显式-uid 严格性在 uid 路径内完整保留；HTTP 层裸
        user_id 入口另由 app.py 的 AUTH_REQUIRED 门禁封堵（PROX-9 不回退）。

        login-latency-fix §2.2.1：同步路径只在短临界区内持锁（纯 DB 读写，
        无 AI/网络调用）。临界区内完成：按名收养判定、死亡结算、建角落盘、
        会话 token 登记、道统行读取；任务板格式化与 first-night 在锁外。
        死者分支走 dead_payload（锁内结算 + 锁外快照）；若快照间隙角色
        已被转世（dead_payload 返回 None），重走正常入世流程。
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("join requires a non-empty name")
        name = name.strip()
        if user_id is not None and (not isinstance(user_id, str) or not user_id.strip()):
            raise ValueError("join requires an authenticated user_id")
        if _deadline is None:
            _deadline = time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
        try:
            return self._join_inner(name, user_id, auto_rebirth=auto_rebirth, _deadline=_deadline)
        except sqlite3.OperationalError as e:
            # B1-1 注册兜底：DB 争用（database is locked/busy）转繁忙语义，
            # HTTP 层回 503 SERVER_BUSY，绝不裸 500；其他异常照旧抛。
            if is_db_locked_error(e):
                raise WorldBusyError(SERVER_BUSY_MESSAGE) from e
            raise

    def _acquire_bounded(self, deadline: float) -> bool:
        """以 deadline 为界尝试取 World.lock（§2.2.4）。

        预留快照余量后仍无剩余时间即直接放弃，不取锁。同一线程已持锁
        时 RLock 立即返回 True（重入），不等待。
        """
        remaining = deadline - time.monotonic() - _LOCK_SNAPSHOT_RESERVE_SECONDS
        if remaining <= 0:
            return False
        return self.lock.acquire(timeout=remaining)

    @contextlib.contextmanager
    def _bounded_lock(self, deadline: float):
        """有界临界区：拿不到锁时抛 WorldBusyError，调用方走回退/503。

        登录/注册路径禁止无界 with self.lock，一律走这里。
        """
        if not self._acquire_bounded(deadline):
            raise WorldBusyError(SERVER_BUSY_MESSAGE)
        try:
            yield
        finally:
            self.lock.release()

    def _live_fallback_snapshot(self, char, uid: str, *, resumed: bool) -> Dict[str, Any]:
        """活角色锁外回退快照（§2.2.4）：纯 DB 单查询读，不写任何数据、不发 token。

        道统行只读（LegacyRepository.get，缺行时用内存默认值，绝不创建）；
        读到的数据可能比 tick 写入滞后一个 tick（可接受的 transient staleness）。
        """
        account = LegacyRepository.get(uid)
        if account is None:
            account = LegacyAccount(user_id=uid)
        return {
            "token": None,
            "user_id": uid,
            "character_id": char.id,
            "name": char.name,
            "realm": char.realm.name,
            "location": char.location,
            "rem_years": round(char.lifespan.get_remaining_years(), 2),
            "legacy_points": account.points,
            "lives": account.total_lives,
            "is_new_life": False,
            "resumed": resumed,
            "newbie_feed": "",
            "first_night": None,
            "lock_fallback": True,
            "session_issued": False,
            # 游戏感第一期（§2.3）：繁忙回退不拼装，entry 明示待补
            "entry": None,
            "entry_pending": True,
        }

    def _join_fallback(self, name: str, user_id, *, auto_rebirth: bool,
                       deadline: float) -> Dict[str, Any]:
        """拿不到锁时的 join 出口（§2.2.1 修订表）：读路径回退快照，写路径繁忙。

        判定本身只做锁外 DB 读，不写任何数据。死者走 dead_payload（其内部
        同样有界：能拿到锁则正常结算，不能则回退未结算快照）；活角色返回
        只读快照；无角色/需建角/需收养/需转世（auto_rebirth）一律抛
        WorldBusyError——建角、收养、发 token 一律要求持锁，锁外绝不创建角色。
        """
        uid = user_id.strip() if isinstance(user_id, str) else ""
        if uid:
            char = CharacterRepository.get_by_user_id(uid)
            if char is not None and (char.status == CharacterStatus.DEAD or char.lifespan.is_dead()):
                if auto_rebirth:
                    raise WorldBusyError(SERVER_BUSY_MESSAGE)
                dead = self.dead_payload(uid, _deadline=deadline)
                if dead is not None:
                    return dead
                # 快照间隙角色已被转世：重读一次，活了就回退活快照，否则请重试
                char2 = CharacterRepository.get_by_user_id(uid)
                if char2 is not None and not (
                    char2.status == CharacterStatus.DEAD or char2.lifespan.is_dead()
                ):
                    return self._live_fallback_snapshot(char2, uid, resumed=True)
                raise WorldBusyError(SERVER_BUSY_MESSAGE)
            if char is not None:
                return self._live_fallback_snapshot(char, uid, resumed=True)
            raise WorldBusyError(SERVER_BUSY_MESSAGE)
        by_name = CharacterRepository.get_by_name(name)
        if by_name and by_name.status != CharacterStatus.DEAD and not by_name.lifespan.is_dead():
            uid_n = str(by_name.user_id or "")
            if uid_n and not (uid_n.startswith("npc_") or uid_n.startswith("ai_npc_")):
                return self._live_fallback_snapshot(by_name, uid_n, resumed=True)
        raise WorldBusyError(SERVER_BUSY_MESSAGE)

    def _join_inner(self, name, user_id, *, auto_rebirth=False, _dead_retry=0, _deadline=None):
        """入世实现体：短临界区（判定/结算/建角/发 token）+ 锁外收尾。

        拿不到锁时不等待、不写操作：读路径走 _join_fallback 锁外快照，
        写路径抛 WorldBusyError（HTTP 层转 503 SERVER_BUSY）。
        死者分支在锁外走 dead_payload；若快照间隙角色已被转世
        （dead_payload 返回 None），递归重入正常入世流程，最多 2 次。
        """
        deadline = _deadline if _deadline is not None else time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
        try:
            return self._join_locked(
                name, user_id, auto_rebirth=auto_rebirth,
                _dead_retry=_dead_retry, _deadline=deadline,
            )
        except WorldBusyError:
            return self._join_fallback(name, user_id, auto_rebirth=auto_rebirth, deadline=deadline)

    def _join_locked(self, name, user_id, *, auto_rebirth=False, _dead_retry=0, _deadline=None):
        """入世实现体（持锁部分）：短临界区 + 锁外收尾。仅由 _join_inner 调用。"""
        deadline = _deadline if _deadline is not None else time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
        with self._bounded_lock(deadline):
            uid = user_id.strip() if isinstance(user_id, str) else ""
            char: Optional[Any] = None
            resumed = False
            dead_uid: Optional[str] = None
            if uid:
                char = CharacterRepository.get_by_user_id(uid)
                if (
                    char is not None
                    and (char.status == CharacterStatus.DEAD or char.lifespan.is_dead())
                    and not auto_rebirth
                ):
                    dead_uid = uid
            else:
                # 匿名路径：按道号找回仍存活的玩家号（换设备/清缓存）
                by_name = CharacterRepository.get_by_name(name)
                if by_name and by_name.status != CharacterStatus.DEAD and not by_name.lifespan.is_dead():
                    uid_n = str(by_name.user_id or "")
                    if uid_n and not (uid_n.startswith("npc_") or uid_n.startswith("ai_npc_")):
                        char = by_name
                        uid = uid_n
                        resumed = True
            is_new_life = False
            if dead_uid is not None:
                pass  # 死者分支：出锁后走 dead_payload，不建角、不发 token
            elif not char or char.status == CharacterStatus.DEAD or char.lifespan.is_dead():
                # 已死（匿名路径或 auto_rebirth）：结算道统（若尚未结算），再新一世
                if char is not None:
                    self._settle_if_needed(char, cause=char.death_cause or "身死道消")
                if not uid:
                    uid = f"lan_{uuid.uuid4().hex[:8]}"
                char = WorldClock.create_new_character(uid, name)
                CharacterRepository.save(char)
                ChronicleRepository.record("JOIN", name, f"修士【{name}】登入局域网大世界。")
                is_new_life = True
            else:
                resumed = True
            snap: Optional[Dict[str, Any]] = None
            char_obj: Optional[Any] = None
            if dead_uid is None:
                token = uuid.uuid4().hex
                self.sessions[token] = Session(token, uid, char.id)
                try:
                    AuthSessionRepository.save(token, uid, char.id, char.name)
                except Exception:
                    pass
                account = LegacyRepository.get_or_create(uid)
                char_obj = char
                snap = {
                    "token": token,
                    "user_id": uid,
                    "character_id": char.id,
                    "name": char.name,
                    "realm": char.realm.name,
                    "location": char.location,
                    "rem_years": round(char.lifespan.get_remaining_years(), 2),
                    "legacy_points": account.points,
                    "lives": account.total_lives,
                    "is_new_life": is_new_life,
                    "resumed": resumed and not is_new_life,
                    "lock_fallback": False,
                    "session_issued": True,
                }
        # ---- 锁外：死者分支（dead_payload 内部：锁内结算 + 锁外快照）----
        if dead_uid is not None:
            dead = self.dead_payload(dead_uid, _deadline=deadline)
            if dead is not None:
                return dead
            # 快照间隙角色已被转世：重走正常入世流程
            if _dead_retry >= 2:
                raise RuntimeError("join failed: dead_payload race did not converge")
            return self._join_locked(name, user_id, auto_rebirth=auto_rebirth, _dead_retry=_dead_retry + 1, _deadline=deadline)
        assert snap is not None and char_obj is not None
        # ---- 锁外：任务板格式化（只读衍生数据，失败静默）----
        try:
            from core.tasks import ensure_tasks, format_task_board

            ensure_tasks(char_obj)
        except Exception:
            pass
        # ---- 锁外：新号 first-night 异步化（§2.2.3）----
        newbie_feed = ""
        first_night = None
        if is_new_life:
            newbie_feed = (
                "【初入道】打开 /任务：十步学会说话、买卖、迁跃、修炼与观照天道；"
                "每步有赏。也可直接 /天道 /世情。新手庇护 72 小时。"
            )
            first_night = {"pending": True}
            # §2.2.3：seed_roster() 调用位置语义不改动——新号建角后、AI 调用前
            # 同步播种（锁外），只把两次强制 AI 留给后台线程。同步播种保证
            # join 返回时花名册已落盘，注册后快照不再被后台写盘扰动。
            try:
                from core.npc_roster import seed_roster

                seed_roster()
            except Exception:
                pass
            self._schedule_first_night(char_obj.id, snap["user_id"], char_obj.name)
        # ---- 锁外：出身生成（新一世）+ 入局拼装（game-feel §2.2/§3.10）----
        # 陈旧对象铁律：拼装只用此处锁外新读对象；①②③ 有变更时至多回存一次。
        entry = None
        origin_card: Dict[str, Any] = {
            "origin": None, "prev_epitaph": "", "just_created": False}
        try:
            fresh = CharacterRepository.get_by_user_id(snap["user_id"]) or char_obj
            if is_new_life and not (getattr(fresh, "origin", None) or {}):
                try:
                    from core.origin import OriginEngine

                    _acc = LegacyRepository.get_or_create(snap["user_id"])
                    # 世仇选人（二期 §4.3）：有前世留痕时先选人再生成出身
                    _vendetta = None
                    try:
                        from core.fate_thread import FateThreadEngine as _FTEv

                        _vendetta = _FTEv.select_vendetta(_acc, fresh)
                    except Exception:
                        _vendetta = None
                    OriginEngine.generate_for_new_life(fresh, _acc, vendetta=_vendetta)
                    CharacterRepository.save(fresh)
                except Exception:
                    pass  # 出身是增益层：失败留空、建角照常成功（§3.10）
            # 命途建线（二期 §3.8 调用点①）：origin 生成之后、入局拼装
            # 之前；新号/老号登录均在此首次建线，失败吞掉不阻断登录
            # （主线是增益层，不是登录门禁）。建线新挂的 goals 随 fresh 回存。
            try:
                from core.fate_thread import FateThreadEngine as _FTEj

                _acc_j = LegacyRepository.get_or_create(snap["user_id"])
                _goals_before = len(getattr(fresh, "goals", None) or [])
                _FTEj.ensure_thread(fresh, _acc_j)
                if len(getattr(fresh, "goals", None) or []) != _goals_before:
                    CharacterRepository.save(fresh)
            except Exception:
                pass
            try:
                _acc2 = LegacyRepository.get(snap["user_id"])
                if _acc2 and _acc2.traces:
                    origin_card["prev_epitaph"] = (
                        getattr(_acc2.traces[-1], "life_epitaph", "") or "")
            except Exception:
                pass
            origin_card["origin"] = getattr(fresh, "origin", None) or None
            origin_card["just_created"] = bool(
                is_new_life and origin_card["origin"])
            _since = float(getattr(fresh, "born_at", 0.0) or 0.0)
            try:
                from storage.db import AccountRepository as _AcctRepo

                _last_login = _AcctRepo.get_last_login(snap["user_id"])
                if _last_login:
                    _since = float(_last_login)
            except Exception:
                pass
            from core.briefing import build_entry

            _dirty: list = []
            entry = build_entry(
                fresh, since=_since, allow_proactive=True, _out_dirty=_dirty)
            if _dirty and _dirty[0]:
                try:
                    CharacterRepository.save(fresh)
                except Exception:
                    pass
        except Exception:
            entry = None  # 入口降级为旧行为，登录照常（§2.2 失败隔离）
        return {
            **snap,
            "newbie_feed": newbie_feed,
            "first_night": first_night,
            "entry": entry,
            "origin_card": origin_card,
        }

    def _schedule_epitaph_polish(self, user_id: str) -> None:
        """评语润色单飞调度（二期 §7.2）：同账户同时只跑一条守护线程；
        润色失败/超时在 LegacyEngine.try_polish_epitaph 内静默降级。"""
        inflight = getattr(self, "_epitaph_polish_inflight", None)
        if inflight is None:
            inflight = self._epitaph_polish_inflight = set()
            self._epitaph_polish_lock = threading.Lock()
        with self._epitaph_polish_lock:
            if user_id in inflight:
                return
            inflight.add(user_id)
        t = threading.Thread(
            target=self._run_epitaph_polish,
            args=(user_id,),
            daemon=True,
            name=f"epitaph-polish-{user_id[:8]}",
        )
        t.start()

    def _run_epitaph_polish(self, user_id: str) -> None:
        """锁外执行评语润色：重读账户行后单次尝试，任何异常静默。"""
        try:
            from core.legacy import LegacyEngine as _LEp

            account = LegacyRepository.get_or_create(user_id)
            _LEp.try_polish_epitaph(account)
        except Exception:
            pass
        finally:
            try:
                with self._epitaph_polish_lock:
                    self._epitaph_polish_inflight.discard(user_id)
            except Exception:
                pass

    def first_night_status(self, character_id: str) -> Optional[str]:
        """first-night 异步任务终态查询（测试/运维用）：pending|done|failed。

        pending 只存在于内存（join 返回的 first_night 字段）；done=结果已写
        入编年史，failed=AI 失败/无内容被静默丢弃。重启后不补跑，未完成
        的 first-night 在新进程里无记录（可接受降级）。
        """
        with self._first_night_lock:
            return self._first_night_status.get(character_id)

    def _schedule_first_night(self, character_id: str, user_id: str, char_name: str) -> None:
        """同一角色同一世只跑一次 first-night；超 4 并发时丢弃并记日志。"""
        with self._first_night_lock:
            if character_id in self._first_night_inflight:
                return
            self._first_night_inflight.add(character_id)
            self._first_night_status[character_id] = "pending"
        if not self._first_night_sem.acquire(blocking=False):
            with self._first_night_lock:
                self._first_night_inflight.discard(character_id)
                self._first_night_status[character_id] = "failed"
            try:
                log_event("GATE", "first_night_dropped", character_id=character_id, reason="concurrency_limit")
            except Exception:
                pass
            return
        t = threading.Thread(
            target=self._run_first_night,
            args=(character_id, user_id, char_name),
            daemon=True,
            name=f"first-night-{character_id[:8]}",
        )
        t.start()

    def _run_first_night(self, character_id: str, user_id: str, char_name: str) -> None:
        """后台 first-night：不持 World.lock 跑两次强制 AI；写回时才取短锁。

        成功：【同场】/【天道】行写入编年史（FIRST_NIGHT），玩家下次
        /大事记 可见。失败/超时/熔断/无内容：静默丢弃，绝不反写错误进
        玩家 feed、绝不抛错、绝不影响已建立的会话。
        """
        status = "failed"
        try:
            char = CharacterRepository.get_by_id(character_id)
            if char is None or char.status == CharacterStatus.DEAD or char.lifespan.is_dead():
                return
            dres: Dict[str, Any] = {}
            pro_item: Dict[str, Any] = {}
            try:
                from core.world_director import WorldDirector
                from core.npc_proactive import NpcProactiveEngine

                dres = WorldDirector.run_cycle(trigger="command", force=True) or {}
                pro = NpcProactiveEngine.maybe_engage(char, force=True)
                if isinstance(pro, list) and pro:
                    pro_item = pro[0] or {}
                elif isinstance(pro, dict):
                    pro_item = pro
            except Exception:
                dres = {}
                pro_item = {}
            lines = []
            if pro_item.get("text"):
                lines.append("【同场】" + str(pro_item.get("text"))[:120])
            if dres.get("ok") and dres.get("brief_hint"):
                lines.append(f"【天道】{dres.get('brief_hint')}")
            if lines:
                # MF-1：写回前重读当前行——AI 耗时期间角色可能已死，死者不写首夜行。
                # V-2 加固：写回取锁有界，拿不到则跳过本次写回并记 failed，不阻塞。
                _alive = False
                try:
                    _fresh = CharacterRepository.get_by_id(character_id)
                    _alive = (
                        _fresh is not None
                        and _fresh.status != CharacterStatus.DEAD
                        and not _fresh.lifespan.is_dead()
                    )
                except Exception:
                    _alive = False
                if _alive:
                    if self.lock.acquire(timeout=LOCK_ACQUIRE_TIMEOUT_SECONDS):
                        try:
                            ChronicleRepository.record("FIRST_NIGHT", char_name, "\n".join(lines))
                        except Exception:
                            pass
                        finally:
                            self.lock.release()
                        status = "done"
                    else:
                        try:
                            log_event("GATE", "first_night_write_skipped", character_id=character_id, reason="lock_busy")
                        except Exception:
                            pass
        except Exception:
            status = "failed"
        finally:
            with self._first_night_lock:
                self._first_night_inflight.discard(character_id)
                self._first_night_status[character_id] = status
            self._first_night_sem.release()

    def _settle_if_needed(self, char: Character, cause: str = "身死道消") -> Optional[Dict[str, Any]]:
        """死亡后一次性道统结算（account-death：资金归集步在钩子与道统结算之前，
        双入口 CLI/server 共用同一 sweep 实现；已结算行走迁移补扫 §5.2）。"""
        from core.wallet import (
            is_npc_user,
            sweep_death_funds,
            sweep_has_real_change,
            wallet_summary,
        )

        if getattr(char, "death_settled", False):
            # 迁移补扫（评审 M1b：以 server 守卫为准，与 CLI 双入口语义统一）：
            # 已结算行不再因“death_sweep ref 已存在”直接返回——sweep 内部处理
            # 残差（ref 已存在但行内仍有余额时以残差 ref 入账，见 core/wallet.py），
            # 故此处恒跑 sweep；仅当 sweep 确无真实变化（实际入账／作废／没收，
            # 见 sweep_has_real_change）时返回 None，步骤异常只记 PARTIAL 大事记。
            if is_npc_user(char.user_id or ""):
                return None
            account = LegacyRepository.get_or_create(char.user_id)
            details = sweep_death_funds(char, account)
            LegacyRepository.save(account)
            CharacterRepository.save(char)
            if details.get("errors"):
                ChronicleRepository.record(
                    "WALLET_SWEEP_PARTIAL", char.name,
                    f"【{char.name}】死亡资金补扫部分完成（WALLET_SWEEP_PARTIAL）："
                    + "；".join(f"{e.get('step')}:{e.get('error')}" for e in details["errors"])
                    + f"；钱包余额 {account.wallet_stones}。",
                )
            # QA-D1：changed 只认真实变化（实际入账／作废／没收），与 CLI 同口径
            # （core.wallet.sweep_has_real_change）。毛额退款／崩溃重放不再触发
            # backfilled 与 WALLET_SWEEP 大事记；步骤异常仍另记 PARTIAL 大事记，
            # 但不单独触发 backfilled。
            changed = sweep_has_real_change(details)
            if not changed:
                return None
            ChronicleRepository.record(
                "WALLET_SWEEP", char.name,
                f"【{char.name}】死亡资金补扫归集 {details['total']} 灵石，钱包余额 {account.wallet_stones}。",
            )
            return {"backfilled": True, "sweep": details, "wallet": wallet_summary(account)}
        account = LegacyRepository.get_or_create(char.user_id)
        char.status = CharacterStatus.DEAD
        # 资金归集（§2.3 步骤 1–4）：随身＋寄存、拍卖退款回起拍、议政票作废、当票没收
        sweep = sweep_death_funds(char, account)
        LegacyRepository.save(account)
        # 灵宠随主而殁（F01，一世循环）
        PetEngine.on_owner_death(char)
        # 洞府灵田随旧世荒废（F06，一世循环）
        FarmEngine.on_owner_death(char)
        # 委托链随旧世而散（F07，一世循环）
        QuestEngine.on_owner_death(char)
        # 诺言随旧世而散（F14，一世循环）：其未结诺全部消散，不判违约；
        # 被消散摘要经返回值注入 settle_death 写留痕（诺在 settle 前已消散）
        dissolved_promises = []
        try:
            dissolved_promises = PromiseEngine.on_owner_death(char) or []
        except Exception:
            dissolved_promises = []
        # 因果链随旧世而散（karma-event-chains §7.1）：紧随诺言钩子之后、
        # settle_death 之前；返回值只记日志，不注入 settle_death（不进留痕）。
        # 留痕口径（R1/MF-4）：server 侧不另记汇总编年史——latent 消散静默、
        # fermenting 消散由引擎 _dissipate 经 jianghu public 单记一条。
        try:
            from core.karma_chains import KarmaChainEngine

            KarmaChainEngine.on_owner_death(char)
        except Exception:
            pass
        if not char.death_cause:
            char.death_cause = cause
        settle = LegacyEngine.settle_death(
            account, char, death_cause=char.death_cause or cause,
            dissolved_promises=dissolved_promises,
        )
        LegacyRepository.save(account)
        CharacterRepository.save(char)
        # 评语润色（二期 §7.2 调用点）：结算完成落盘之后调度单飞守护
        # 线程异步润色一次；润色本身在线程内（锁外）执行，绝不在
        # settle_death 同步路径 / 登录路径 / tick 路径内跑。
        try:
            self._schedule_epitaph_polish(char.user_id)
        except Exception:
            pass
        if sweep.get("errors"):
            ChronicleRepository.record(
                "WALLET_SWEEP_PARTIAL", char.name,
                f"【{char.name}】死亡资金归集部分完成（WALLET_SWEEP_PARTIAL）："
                + "；".join(f"{e.get('step')}:{e.get('error')}" for e in sweep["errors"])
                + f"；钱包余额 {account.wallet_stones}。",
            )
        ChronicleRepository.record(
            "LEGACY_SETTLE", char.name,
            f"【{char.name}】{char.death_cause}，结转道统 {settle['points_gained']} 点；"
            f"资金归集 {sweep['total']} 灵石，钱包余额 {account.wallet_stones}。",
        )
        settle["sweep"] = sweep
        settle["wallet"] = wallet_summary(account)
        return settle

    def dead_payload(self, user_id: str, username: str = "", _deadline: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Web /login 死者分支（§2.6 行为变更）：登录只报死讯＋钱包，不自动建角。

        返回 None 表示现世角色存活或无角色（调用方走正常 join 流程）。
        会话 token 保持有效且可用于 /转世（session.character_id 指向死行）。

        login-latency-fix §2.2.2（修订 R1，三路出口）：先以 2 秒为界尝试取锁——
        （1）拿到锁：短临界区内结算（_settle_if_needed，含幂等守卫）+ 发 token，
        结算结果落盘后即释放锁；（2a）随后锁外快照组装，带
        settlement_pending: false、settled: true；（2b）拿不到锁：锁外回退，
        直接从 DB 读未结算快照返回，本次不结算，带 settlement_pending: true、
        settled: false、lock_fallback: true、session_issued: false，不发 token。
        """
        deadline = _deadline if _deadline is not None else time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
        # ---- 步 1（短临界区）：结算 + 发 token（纯 DB 读写）----
        try:
            with self._bounded_lock(deadline):
                char = CharacterRepository.get_by_user_id(user_id)
                if char is None or (char.status != CharacterStatus.DEAD and not char.lifespan.is_dead()):
                    return None
                settle = self._settle_if_needed(char, cause=char.death_cause or "身死道消")
                token = uuid.uuid4().hex
                self.sessions[token] = Session(token, user_id, char.id)
                try:
                    AuthSessionRepository.save(token, user_id, char.id, char.name)
                except Exception:
                    pass
                char_id = char.id
        except WorldBusyError:
            return self._dead_fallback_snapshot(user_id, username)
        # ---- 步 2（锁外快照）：重读结算后已落盘的数据 ----
        char = CharacterRepository.get_by_user_id(user_id)
        if char is None or char.id != char_id:
            # 结算与快照间隙角色已被转世：死者快照不再有效，调用方重走 join
            return None
        account = LegacyRepository.get_or_create(user_id)
        return self._dead_payload_dict(
            char, account, user_id, username,
            token=token,
            settlement=(settle or {}).get("sweep") if settle else None,
            lock_fallback=False, session_issued=True,
            settlement_pending=False, settled=True,
        )

    def _dead_fallback_snapshot(self, user_id: str, username: str = "") -> Optional[Dict[str, Any]]:
        """死者锁外回退快照（§2.2.2 2b）：本次不结算、不发 token、不写任何数据。

        钱包/道统字段取自 DB 当前已落盘值（未结算旧值），不得谎报为结算后值；
        道统行只读（LegacyRepository.get，缺行时用内存默认值，绝不创建）。
        活角色/无角色时返回 None（调用方走正常 join 流程）。
        """
        char = CharacterRepository.get_by_user_id(user_id)
        if char is None or (char.status != CharacterStatus.DEAD and not char.lifespan.is_dead()):
            return None
        account = LegacyRepository.get(user_id)
        if account is None:
            account = LegacyAccount(user_id=user_id)
        return self._dead_payload_dict(
            char, account, user_id, username,
            token=None, settlement=None,
            lock_fallback=True, session_issued=False,
            settlement_pending=True, settled=False,
        )

    def _dead_payload_dict(self, char, account, user_id: str, username: str, *,
                           token, settlement, lock_fallback: bool,
                           session_issued: bool, settlement_pending: bool,
                           settled: bool) -> Dict[str, Any]:
        """死者 payload 组装（结算路径与锁外回退路径共用，字段一致，仅标记不同）。"""
        from core.legacy import LegacyEngine as _LE
        from core.wallet import wallet_summary as _ws
        from core.inheritance import trace_summary as _trace_summary

        # S3：寄售在售单数（按 seller_user_id／seller_id 计 OPEN 单；取数失败置 0）
        try:
            from storage.db import MarketListingRepository as _MLR

            _open_count = sum(
                1
                for _lst in _MLR.list_all()
                if _lst.is_open()
                and ((_lst.seller_user_id or "") == user_id or _lst.seller_id == char.id)
            )
        except Exception:
            _open_count = 0
        # S4：最近一世享寿（settle 后 past_lives 末世即本世；已结算行同理）
        _last_life = account.past_lives[-1] if account.past_lives else None
        # 死亡仪式（game-feel-phase1 §4.4）：已结算路拼装 death 幕；
        # 锁忙回退路（未结算）ceremony=null——未结算不得演回望。
        _ceremony = None
        if settled:
            try:
                from core.ceremony import build_death_ceremony

                _ceremony = build_death_ceremony(char, account)
            except Exception:
                _ceremony = None
        return {
            "ok": True,
            "dead": True,
            "ceremony": _ceremony,
            "token": token,
            "user_id": user_id,
            "username": username,
            "character_id": char.id,
            "name": char.name,
            # 旧前端兼容（只增字段）：死者行仍有境界／位置／寿元余量可读
            "realm": char.realm.name,
            "location": char.location,
            "rem_years": round(char.lifespan.get_remaining_years(), 2),
            "legacy_points": account.points,
            "lives": account.total_lives,
            "is_new_life": False,
            "resumed": False,
            "death_cause": char.death_cause,
            "legacy": {
                "points": account.points,
                "lives": account.total_lives,
                "boosts": _LE.list_boosts(),
                "lifespan_lived": _last_life.lifespan_lived if _last_life else None,
                # 转世继承（只增）：前世列表（同 legacy_info 口径）与刚逝一世留痕摘要
                "past_lives": [
                    {
                        "name": p.name, "realm": p.realm, "cause": p.cause,
                        "points": p.points_gained, "lived": p.lifespan_lived,
                    }
                    for p in account.past_lives[-8:]
                ],
                "trace": (
                    _trace_summary(account.traces[-1])
                    if account.traces else None
                ),
            },
            "wallet": _ws(account),
            "settlement": settlement,
            "consignment_open_count": _open_count,
            "lock_fallback": lock_fallback,
            "session_issued": session_issued,
            "settlement_pending": settlement_pending,
            "settled": settled,
        }

    def legacy_info(self, token: str) -> Dict[str, Any]:
        char = self.get_char(token)
        if not char:
            return {"ok": False, "error": "会话无效"}
        account = LegacyRepository.get_or_create(char.user_id)
        boosts = []
        for k, cfg in LEGACY_BOOSTS.items():
            boosts.append({"key": k, "name": cfg["name"], "cost": cfg["cost"], "desc": cfg["desc"]})
        from core.inheritance import current_karma_shadow, trace_summary

        return {
            "ok": True,
            "points": account.points,
            "lives": account.total_lives,
            "earned": account.total_points_earned,
            "past_lives": [
                {
                    "name": p.name, "realm": p.realm, "cause": p.cause,
                    "points": p.points_gained, "lived": p.lifespan_lived,
                }
                for p in account.past_lives[-8:]
            ],
            # 转世继承（只增）：最近 8 世留痕摘要 + 当前角色本世被施加的影子清单
            "traces": [trace_summary(t) for t in account.traces[-8:]],
            "karma_shadow": current_karma_shadow(account),
            "boosts": boosts,
            "max_boosts": LEGACY_MAX_BOOSTS_PER_LIFE,
            "alive": char.status != CharacterStatus.DEAD and not char.lifespan.is_dead(),
            "death_cause": char.death_cause,
        }

    def reincarnate(self, token: str, name: Optional[str] = None, boosts: Optional[List[str]] = None) -> Dict[str, Any]:
        """转世：结算（若需）→ 新一世 → 消费道统点

        B1-2：拿锁改有界（_bounded_lock 口径）——锁被 tick 等长期占用时
        抛 WorldBusyError（HTTP 层 503 SERVER_BUSY），不许无界等待。
        已持锁线程（handle 分发）经 RLock 重入立即成功，口径不变。
        """
        _deadline = time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
        with self._bounded_lock(_deadline):
            session = self._session(token)
            if not session:
                return {"ok": False, "error": "会话无效"}
            old = CharacterRepository.get_by_user_id(session.user_id)
            if old and old.status != CharacterStatus.DEAD and not old.lifespan.is_dead():
                return {"ok": False, "error": "此世尚存，何须转世？可先 /道统 查看。"}

            settle = None
            if old is not None:
                settle = self._settle_if_needed(old, cause=old.death_cause or "身死道消")

            account = LegacyRepository.get_or_create(session.user_id)
            new_name = (name or "").strip()[:12] or (old.name if old else "转世者")
            # 避免同名冲突
            if CharacterRepository.get_by_name(new_name) and (not old or CharacterRepository.get_by_name(new_name).id != old.id):
                new_name = new_name[:8] + "·转"

            # 转世编排（spec §2.3/§2.4）：建角 → boosts → 按 bond_echo 与否选
            # retention/cap 施加因果影子 → 统一落盘。old_trace 须在 boosts 前
            # 捕获（settle 刚生成的留痕即 traces[-1]，boosts 不改 traces）。
            old_trace = account.traces[-1] if account.traces else None
            char = WorldClock.create_new_character(session.user_id, new_name)
            boost_res = LegacyEngine.apply_birth_boosts(
                char, account, list(boosts or []), old_trace=old_trace,
            )
            from config import (
                BOND_ECHO_CAP,
                BOND_ECHO_RETENTION,
                SHADOW_CAP,
                SHADOW_RETENTION,
            )
            from core.inheritance import apply_karma_shadow

            if boost_res.get("bond_echo"):
                _retention, _cap = BOND_ECHO_RETENTION, BOND_ECHO_CAP
            else:
                _retention, _cap = SHADOW_RETENTION, SHADOW_CAP
            karma_shadow = apply_karma_shadow(
                account, char, retention=_retention, cap=_cap,
            )
            # 出身生成（game-feel §3.10 时机二）：影子之后、统一 save 之前；
            # 纯规则毫秒级，失败不阻断转世。影子覆盖者由生成器排除。
            # 世仇选人（二期 §4.3）：apply_karma_shadow 之后、出身生成之前
            # 算出 vendetta 经新入参进 foe 名额（bounds/种子边走既有通道）。
            _vendetta = None
            try:
                from core.fate_thread import FateThreadEngine as _FTEr

                _vendetta = _FTEr.select_vendetta(account, char)
            except Exception:
                _vendetta = None
            try:
                from core.origin import OriginEngine

                OriginEngine.generate_for_new_life(char, account, vendetta=_vendetta)
            except Exception:
                pass
            # 命途建线（二期 §3.8 调用点②）：origin 之后、统一 save 之前，
            # 纯本地规则 + 既有仓储写，失败不阻断转世。
            try:
                from core.fate_thread import FateThreadEngine as _FTEr2

                _FTEr2.ensure_thread(char, account)
            except Exception:
                pass
            LegacyRepository.save(account)
            CharacterRepository.save(char)
            session.character_id = char.id
            try:
                AuthSessionRepository.save(token, session.user_id, char.id, char.name)
            except Exception:
                pass
            from core.wallet import wallet_summary as _ws

            wallet_block = _ws(account)
            ChronicleRepository.record(
                "REINCARNATE", char.name,
                f"真灵转世，【{char.name}】重踏仙途。"
                + (f"道统点化：{'、'.join(boost_res.get('applied') or [])}。" if boost_res.get("applied") else ""),
            )
            shadow_text = ""
            if karma_shadow:
                shadow_lines = "、".join(
                    f"{s['npc_name']} {s['value']:+d}" for s in karma_shadow
                )
                shadow_text = f"因果余绪及身：{shadow_lines}\n"
            # 转世仪式 + 出身卡（game-feel §3.11/§4.4，只增键）
            _origin_card = {
                "origin": getattr(char, "origin", None) or None,
                "prev_epitaph": (
                    getattr(old_trace, "life_epitaph", "") or "") if old_trace else "",
                "just_created": True,
            }
            _rebirth_ceremony = None
            try:
                from core.ceremony import build_rebirth_ceremony

                _rebirth_ceremony = build_rebirth_ceremony(
                    char, account,
                    karma_shadow=karma_shadow,
                    boosts_applied=boost_res.get("applied") or [],
                    legacy_points=account.points,
                )
            except Exception:
                _rebirth_ceremony = None
            return {
                "ok": True,
                "text": (
                    f"【真灵转世】{char.name} · {char.realm.name} · {char.location}\n"
                    f"自然寿元 {char.lifespan.birth_base:.0f} 岁\n"
                    f"{boost_res.get('message', '')}\n"
                    f"{shadow_text}"
                    f"道统池剩余 {account.points} 点（第 {account.total_lives + 1} 世）\n"
                    f"账户钱包 {wallet_block['balance']} 灵石（新角随身 {char.spirit_stones} 灵石）；"
                    f"入世后用 /钱包提取 <金额> 取用账户金额。"
                ),
                "karma_shadow": karma_shadow,
                "settle": {
                    "points_gained": (settle or {}).get("points_gained", 0),
                    "cause": (settle or {}).get("cause", ""),
                    "past_life": ((settle or {}).get("past_life") or {}).model_dump()
                    if (settle or {}).get("past_life") else None,
                } if settle else None,
                "boosts_applied": boost_res.get("applied") or [],
                "legacy_points": account.points,
                "wallet": wallet_block,
                "sweep": (settle or {}).get("sweep"),
                "name": char.name,
                "realm": char.realm.name,
                "location": char.location,
                "rem_years": round(char.lifespan.get_remaining_years(), 2),
                "origin_card": _origin_card,
                "ceremony": _rebirth_ceremony,
            }

    def _session(self, token: str) -> Optional[Session]:
        s = self.sessions.get(token)
        if s:
            return s
        # 内存无则从库恢复（重启后续玩）
        try:
            row = AuthSessionRepository.get(token)
        except Exception:
            row = None
        if not row:
            return None
        sess = Session(row["token"], row["user_id"], row["character_id"])
        self.sessions[token] = sess
        return sess

    def get_char(self, token: str) -> Optional[Character]:
        s = self._session(token)
        if not s:
            return None
        return CharacterRepository.get_by_user_id(s.user_id)

    # ---------------- 同场他人（事实包用） ----------------
    def others_at(self, character: Character) -> List[Character]:
        out = []
        for c in CharacterRepository.list_all_alive():
            if c.id != character.id and c.location == character.location:
                out.append(c)
        return out

    # ---------------- 指令路由（权威） ----------------
    def handle(self, token: str, command: str) -> Dict[str, Any]:
        """指令分发。B1-2：仅 /转世（含 /reborn）走有界拿锁——锁被长期
        占用时抛 WorldBusyError（HTTP 层转 503 SERVER_BUSY 诚实文案），
        不许无界等待；其余命令维持既有无界 with self.lock 不动。"""
        _parts = command.strip().split() if isinstance(command, str) else []
        _action0 = _parts[0].lower() if _parts else ""
        if _action0 in ("/reborn", "/转世"):
            _deadline = time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
            with self._bounded_lock(_deadline):
                return self._handle_locked(token, command)
        with self.lock:
            return self._handle_locked(token, command)

    def _handle_locked(self, token: str, command: str) -> Dict[str, Any]:
        """handle 实现体（调用方已持 World.lock；此处 RLock 重入无等待）。"""
        with self.lock:
            char = self.get_char(token)
            if not char:
                return {"ok": False, "error": "会话无效，请用账号密匙重新 /login"}
            session = self._session(token)
            parts = command.strip().split()
            if not parts:
                return {"ok": True, "text": ""}
            action = parts[0].lower()
            # 心魔待决优先
            if session and session.pending_heart_demon:
                hd = self.hd_sessions.get(session.pending_heart_demon)
                if hd and not hd.resolved:
                    raw = command.strip()
                    known = set()
                    for opt in hd.options:
                        known.add(opt.get("id", ""))
                        known.add(opt.get("label", ""))
                    free = None
                    choice = raw
                    # 数字选项
                    if raw.isdigit():
                        idx = int(raw) - 1
                        if 0 <= idx < len(hd.options):
                            choice = hd.options[idx].get("id", raw)
                    if choice not in known:
                        free = raw
                        choice = None
                    res = HeartDemonEngine.resolve(char, hd, choice_id=choice, free_text=free)
                    CharacterRepository.save(char)
                    session.pending_heart_demon = None
                    text = self._fmt_hd(res)
                    # 心魔致死（评审 S2：局内死亡响应带 sweep 与 death_cause）
                    if res.get("is_fatal") or char.status == CharacterStatus.DEAD:
                        _settle = self._settle_if_needed(char, cause="心魔道消")
                        return {
                            "ok": True,
                            "text": text,
                            "heart_demon": res,
                            "death": True,
                            "status": self._status_dict(char),
                            "legacy": self.legacy_info_id(char.user_id),
                            "sweep": (_settle or {}).get("sweep") if _settle else None,
                            "death_cause": char.death_cause,
                        }
                    # 心魔过关且未死 → 继续天劫
                    if not res.get("is_fatal") and char.realm.is_full and char.status != CharacterStatus.DEAD:
                        tmod = float(res.get("tribulation_mod") or 0.0)
                        _pend_before = len(getattr(char, "fate_pending", None) or [])
                        trib = BreakthroughEngine.attempt_breakthrough(char, use_pill=False, heart_mod=tmod)
                        CharacterRepository.save(char)
                        text += "\n\n" + trib.get("message", "")
                        trib_dead = bool(trib.get("is_fatal"))
                        if trib.get("success") and trib.get("is_major"):
                            try:
                                GoalEngine.on_breakthrough_major(char)
                            except Exception:
                                pass
                            # 判定式求值点 E3（§3.7）：与 on_breakthrough_major 同位
                            try:
                                from core.goals import evaluate_checked_goals

                                if evaluate_checked_goals(char):
                                    CharacterRepository.save(char)
                            except Exception:
                                pass
                            # 命途求值 T2（二期 §3.6）：与 E3 同位（出口二）
                            try:
                                from core.fate_thread import FateThreadEngine as _FTEh

                                if _FTEh.evaluate_for(char).get("changed"):
                                    CharacterRepository.save(char)
                            except Exception:
                                pass
                            # 传闻写入口（game-feel-phase2 §6）：大境界突破入池（出口②·心魔后继段）
                            try:
                                from core import rumors as _rumors_mod2

                                _rumors_mod2.note_breakthrough(
                                    char.name, char.realm.name, char.location)
                            except Exception:
                                pass
                        _trib_settle = None
                        if trib_dead:
                            _trib_settle = self._settle_if_needed(char, cause="渡劫陨落")
                        # 天劫/突破双幕（game-feel-phase3 §5.2 出口②）：
                        # 与出口①同协议——ceremony=天劫幕、ceremony_next=
                        # 突破幕（只增键）；致死时无第二幕
                        _trib_ceremony = None
                        _trib_ceremony_next = None
                        if trib.get("is_major"):
                            try:
                                from core.ceremony import build_tribulation_ceremony

                                _trib_ceremony = build_tribulation_ceremony(char, trib)
                            except Exception:
                                _trib_ceremony = None
                            if not trib.get("is_fatal"):
                                try:
                                    from core.ceremony import build_breakthrough_ceremony

                                    _trib_ceremony_next = build_breakthrough_ceremony(
                                        char, trib,
                                        fate_drawn=len(getattr(char, "fate_pending", None) or []) > _pend_before,
                                    )
                                except Exception:
                                    _trib_ceremony_next = None
                        return {
                            "ok": True,
                            "text": text,
                            "heart_demon": res,
                            "death": trib_dead,
                            "status": self._status_dict(char),
                            "legacy": self.legacy_info_id(char.user_id) if trib_dead else None,
                            "sweep": (_trib_settle or {}).get("sweep") if _trib_settle else None,
                            "death_cause": char.death_cause if trib_dead else None,
                            "ceremony": _trib_ceremony,
                            "ceremony_next": _trib_ceremony_next,
                            "tribulation": {
                                "success": trib.get("success"),
                                "fatal": trib_dead,
                                "new_realm": trib.get("new_realm"),
                            },
                        }
                    return {
                        "ok": True,
                        "text": text,
                        "heart_demon": res,
                        "status": self._status_dict(char),
                    }

            # ---------------- 免斜杠：会话中自由发言 / 无会话时智能路由 ----------------
            raw_cmd = command.strip()
            if raw_cmd and not raw_cmd.startswith("/") and not raw_cmd.startswith("「"):
                try:
                    from core import npc_chat as _nc

                    sess = _nc.get_session(char.id)
                    if sess:
                        return self.handle(token, f"/说 {raw_cmd}")
                except Exception:
                    pass
                # 无会话：尝试同场唯一/最像 NPC 对象自动开聊
                try:
                    from storage.db import CharacterRepository as CR
                    from core.npc_mind import _is_npc as _inpc
                    from core.here import list_here as _list_here_fn

                    here = _list_here_fn(char)
                    cands = []
                    for row in here:
                        nm = row.get("name") or ""
                        if not nm or nm == char.name:
                            continue
                        obj = CR.get_by_name(nm)
                        if not obj or obj.id == char.id:
                            continue
                        if obj.status == CharacterStatus.DEAD:
                            continue
                        if _inpc(obj) or not str(obj.user_id).startswith("npc_"):
                            cands.append(obj)
                    npcs = [c for c in cands if _inpc(c)]
                    pool = npcs or cands
                    pick = None
                    for c in pool:
                        if c.name and c.name in raw_cmd:
                            pick = c
                            break
                    if not pick and len(pool) == 1:
                        pick = pool[0]
                    if pick:
                        return self.handle(token, f"/交谈 {pick.name} {raw_cmd}")
                    if pool:
                        names = "、".join(c.name for c in pool[:6])
                        return {
                            "ok": False,
                            "error": (
                                f"同场可交谈：{names}。"
                                f"点击头像开聊，或说「我想和{pool[0].name}说…」，也可 /交谈 <道号>"
                            ),
                        }
                except Exception:
                    pass
                return {
                    "ok": False,
                    "error": "此处无人可交谈。可 /here 看同场，或用 /做 描述自由行动。",
                    "hint": "free_text",
                }

            # 生死门禁：道身已殒，唯可轮回转世或察看因果道统
            if char.status == CharacterStatus.DEAD or char.lifespan.is_dead():
                if char.status != CharacterStatus.DEAD:
                    char.status = CharacterStatus.DEAD
                    CharacterRepository.save(char)
                from core.character_integrity import CharacterIntegrity

                if action not in CharacterIntegrity.ALLOWED_DEAD_ACTIONS:
                    cause = char.death_cause or "寿尽道消"
                    return {
                        "ok": False,
                        "error": f"【道身已殒】修士 {char.name} 已坐化道消（死因：{cause}），不可再行世俗之事。请用 /转世 步入轮回，或用 /道统 查看前世余泽。",
                        "status": self._status_dict(char),
                        "dead": True,
                    }

            # 被擒门禁：身陷囹圄，不可自由迁跃行商
            if char.status == CharacterStatus.CAPTURED:
                from core.character_integrity import CharacterIntegrity

                if action not in CharacterIntegrity.ALLOWED_CAPTURED_ACTIONS:
                    return {
                        "ok": False,
                        "error": f"【身陷囹圄】修士 {char.name} 当前处于被擒状态，无法自由行动！请先 /自救、/认输 或等待营救。",
                        "status": self._status_dict(char),
                    }

            # 闭关锁定：洞府入定，只许观照/出关等只读敕令
            if char.status == CharacterStatus.MEDITATING:
                med_ok = (
                    "/look", "/地图", "look", "/道身",
                    "/here", "/同场",
                    "/who",
                    "/help", "/帮助",
                    "/emerge", "/出关",
                    "/legacy", "/道统",
                    "/goals", "/目标",
                    "/qi", "/灵气",
                    "/season", "/纪元",
                    # 天象查看（F13：纯只读观照，主题为纪元编号纯函数推导）
                    "/天象", "/omen",
                    "/agenda", "/议程",
                    "/roster", "/名录",
                    "/bounty", "/告示",
                    "/profile", "/人物", "/角色",
                    "/logout", "/下线",
                    # 灵宠管理（F01 spec：闭关中可管理，仅契约/放生不开）
                    "/灵宠", "/pets", "/pet",
                    "/喂养", "/feed",
                    "/出战", "/deploy",
                    "/休息", "/petrest",
                    # 心法查看（F02：只读观照；主修/辅修/卸功闭关中仍锁门，防结算前换功）
                    "/心法", "/xinfa",
                    # 行情查看（F03：只读观照；购买/出售闭关中仍锁门）
                    "/行情",
                    # 版图查看（F09：纯只读观照，查询零写盘）
                    "/版图", "/atlas",
                    # 飞升榜（F12：纯只读观照，查询零写盘）
                    "/飞升榜", "/ascend",
                    # 洞府查看（F06：纯只读观照；开辟/播种/收获/升级闭关中仍锁门）
                    "/洞府", "/cave",
                )
                if action not in med_ok:
                    prog = WorldClock.get_meditation_progress(char)
                    rem_h = max(0.0, float(prog.get("remaining_design_hours") or 0))
                    log_event("GATE", "meditate_block", name=char.name, cmd=action)
                    return {
                        "ok": False,
                        "error": (
                            f"【闭关锁门】{char.name} 正在洞府入定（约余 {rem_h:.1f} 小时），"
                            f"六识封闭：不可迁跃/斗法/交谈/行商。可 /出关 提前收功后再试。"
                        ),
                        "status": self._status_dict(char),
                        "meditating": True,
                    }

            if action in ("/look", "/地图", "look", "/道身"):
                try:
                    GoalEngine.sync_progress(char)
                except Exception:
                    pass
                text = self._look(char)
                try:
                    from core.hunt import _purge_expired, _load as _hl
                    from storage.db import WorldStateRepository as W

                    now = time.time()
                    _purge_expired(now)
                    for hid, rec in _hl().items():
                        tid = rec.get("target_id") if isinstance(rec, dict) else rec
                        if tid == char.id:
                            flag = f"hunt_warn:{char.id}"
                            if not W.get(flag):
                                W.set(flag, now)
                                text += "\n【天道示警】隐约察觉有人对你动了杀心……"
                            break
                except Exception:
                    pass
                try:
                    from core.player_echo import format_region_strip, player_echo_text

                    strip = format_region_strip(char)
                    if strip and "尚稳" not in strip:
                        text += f"\n【望气】{strip}"
                    labels = []
                    from core.player_echo import get_player_echo

                    e = get_player_echo(char)
                    labels = e.get("labels") or []
                    if labels:
                        text += f"\n【凶名】{'、'.join(labels)}"
                except Exception:
                    pass
                return {"ok": True, "text": text, "status": self._status_dict(char)}
            if action in ("/legacy", "/道统", "/前世"):
                info = self.legacy_info(token)
                if not info.get("ok"):
                    return info
                lines = [
                    f"道统点 {info['points']} · 累计 {info['lives']} 世 · 共得 {info['earned']}",
                    f"本世状态：{'存活' if info['alive'] else '已逝 ' + (info.get('death_cause') or '')}",
                    "出身兑换：",
                ]
                for b in info["boosts"]:
                    lines.append(f"  {b['key']} — {b['name']}（{b['cost']}点）{b['desc']}")
                if info["past_lives"]:
                    lines.append("前世：")
                    for p in info["past_lives"]:
                        lines.append(f"  {p['name']} {p['realm']} · {p['cause']} +{p['points']}点")
                # 前世因果段（转世继承）：无留痕/无因果时整段省略
                try:
                    from core.inheritance import causality_text

                    _account = LegacyRepository.get_or_create(char.user_id)
                    _causality = causality_text(_account)
                    if _causality:
                        lines.append(_causality)
                except Exception:
                    pass
                info["text"] = "\n".join(lines)
                return info
            if action in ("/墓碑",):
                # 墓碑查询（转世继承）：引擎同源文本，CLI 同命令同文案
                from core.inheritance import find_tombstone

                if len(parts) < 2 or not parts[1].strip():
                    return {"ok": False, "error": "用法：/墓碑 <道号>"}
                tomb = find_tombstone(parts[1].strip())
                if tomb is None:
                    return {"ok": True, "text": "江湖无此碑。"}
                from core.inheritance import tombstone_data

                return {
                    "ok": True,
                    "text": tomb,
                    "tombstone": tombstone_data(parts[1].strip()),
                }
            if action in ("/因果链", "/karma_chains"):
                # 因果链面板（AI 天道事件链）：引擎同源文本，CLI 同命令同文案；
                # 先惰性推进后呈现（照 /诺言 settle_due→panel_text 先例）；
                # 无参命令，附加词按邻近面板口径忽略不报错
                from core.karma_chains import KarmaChainEngine

                try:
                    KarmaChainEngine.advance_for(char)
                except Exception:
                    pass
                return {
                    "ok": True,
                    "text": KarmaChainEngine.panel_text(char),
                    "karma_chains": KarmaChainEngine.panel_data(char),
                }
            if action in ("/定相", "/gender"):
                # 定相（gallery-gameplay §3.3）：纯外观自选，assert_alive 门禁
                # 在引擎内；写路径以 CharacterRepository.save 收尾（§11）。
                from core import gallery as _gallery

                res = _gallery.set_gender(char, parts[1] if len(parts) > 1 else "")
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "定相失败"), "status": self._status_dict(char)}
                CharacterRepository.save(char)
                return {"ok": True, "text": res["message"], "status": self._status_dict(char)}
            if action in ("/图鉴", "/gallery"):
                # 图鉴面板（gallery-gameplay §8.5）：双端同源文本，读命令无门禁；
                # 先做一次派生合并（与 _status_dict 同口径）再呈现。
                from core import gallery as _gallery

                try:
                    _gallery.unlock_from_character(char)
                except Exception:
                    pass
                return {"ok": True, "text": _gallery.panel_text(char), "status": self._status_dict(char)}
            if action in ("/命格", "/fate"):
                # 命格（game-feel-phase1 §4.2）：无参查看、带参选择；仪式与
                # 命盘共用唯一选择函数 apply_fate_choice，写路径 save 收尾。
                from core.ceremony import (
                    apply_fate_choice,
                    fate_block,
                    fate_panel_text,
                )

                arg = parts[1] if len(parts) > 1 else ""
                if not arg:
                    return {
                        "ok": True,
                        "text": fate_panel_text(char),
                        "fate": fate_block(char),
                        "status": self._status_dict(char),
                    }
                res = apply_fate_choice(char, arg)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {
                    "ok": bool(res.get("success")),
                    "text": res.get("message", ""),
                    "fate": fate_block(char),
                    "status": self._status_dict(char),
                }
            if action in ("/命途", "/fate_thread"):
                # 命途主线（二期 §8.4）：无参面板（与 fate.thread 同源）、
                # 搁置/续走线级开关（§3.9，assert_alive 门禁沿道体守恒律）。
                from core.fate_thread import FateThreadEngine as _FTEm

                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("搁置", "续"):
                    from core.character_integrity import (
                        CharacterIntegrity,
                        CharacterIntegrityError,
                    )

                    try:
                        CharacterIntegrity.assert_alive(char)
                    except CharacterIntegrityError as _ie:
                        return {"ok": False, "error": str(_ie),
                                "status": self._status_dict(char)}
                    if sub == "搁置":
                        _sr = _FTEm.shelve_thread(char)
                    else:
                        _sr = _FTEm.resume_thread(char)
                        if _sr.get("success"):
                            CharacterRepository.save(char)
                    return {
                        "ok": bool(_sr.get("success")),
                        "text": _sr.get("message", ""),
                        "fate_thread": _FTEm.thread_status_dict(char),
                        "status": self._status_dict(char),
                    }
                return {
                    "ok": True,
                    "text": _FTEm.panel_text(char),
                    "fate_thread": _FTEm.thread_status_dict(char),
                    "status": self._status_dict(char),
                }
            if action in ("/回应", "/respond_drama"):
                # 主动戏剧回应（二期 §8.4/§5.3，集成裁决：A/B 两岗同名分发
                # 合并为本处单一分发）：后果落账在 DramaEngine.respond 内
                # （既有系统入口）；fight 经 fight_fn 转调既有 _fight 分发。
                from core.npc_proactive import DramaEngine as _DE

                if len(parts) < 2:
                    _pending = _DE.list_pending(char) or []
                    if _pending:
                        _lines = ["【待回应之事】"]
                        for _it in _pending:
                            _opts = "/".join(
                                str(o.get("key", "")) for o in (_it.get("options") or []))
                            _lines.append(
                                f"· {_it.get('id', '')} {_it.get('npc_name', '')}："
                                f"{_it.get('text', '')}（/回应 {_it.get('id', '')} <{_opts}>）")
                        return {"ok": True, "text": "\n".join(_lines),
                                "drama_pending": _pending,
                                "status": self._status_dict(char)}
                    return {"ok": True, "text": "眼下无人找上门，无待回应之事。",
                            "drama_pending": [],
                            "status": self._status_dict(char)}
                if len(parts) < 3:
                    return {"ok": False,
                            "error": "用法：/回应 <drama_id> <option_key>（事件不存在或选项非法均不落账）",
                            "status": self._status_dict(char)}
                _rr = _DE.respond(
                    char, parts[1], parts[2],
                    fight_fn=lambda _n: self._fight(char, _n))
                if not _rr.get("success"):
                    return {"ok": False, "error": _rr.get("error") or "回应失败。",
                            "status": self._status_dict(char)}
                CharacterRepository.save(char)
                if _rr.get("action") == "fight" and isinstance(_rr.get("fight"), dict):
                    return _rr["fight"]
                return {"ok": True, "text": _rr.get("message") or "已回应。",
                        "status": self._status_dict(char), "drama": _rr}
            if action in ("/寻宝", "/clue"):
                # 寻宝线索链推进（gallery-gameplay §5.3）：无参查看（纯读）、
                # 数字抉择、弃链；门禁在引擎内，写路径 save 收尾（§11）。
                from core.treasure_clue import TreasureClueEngine

                arg = parts[1] if len(parts) > 1 else ""
                if not arg:
                    ret = {"ok": True, "text": TreasureClueEngine.view_text(char), "status": self._status_dict(char)}
                    clue = TreasureClueEngine.view_data(char)
                    if clue is not None:
                        ret["clue"] = clue
                    return ret
                if arg == "弃":
                    res = TreasureClueEngine.abandon(char)
                else:
                    res = TreasureClueEngine.choose(char, arg)
                if res.get("changed"):
                    CharacterRepository.save(char)
                return {
                    "ok": bool(res.get("success")),
                    "text": res.get("message", ""),
                    "status": self._status_dict(char),
                }
            if action in ("/器灵", "/spirit"):
                # 法宝器灵面板/唤灵（gallery-gameplay §6）：无参面板同源文本；
                # 「唤 <器物名>」唤灵，门禁在引擎内，写路径 save 收尾（§11）。
                from core.artifact_spirit import (
                    ArtifactSpiritEngine,
                    panel_data as _spirit_data,
                    panel_text as _spirit_panel,
                )

                sub = parts[1] if len(parts) > 1 else ""
                if sub == "唤":
                    target_name = parts[2] if len(parts) > 2 else ""
                    if not target_name:
                        return {"ok": False, "error": "用法：/器灵 唤 <器物名>（须已穿戴且天品以上）", "status": self._status_dict(char)}
                    res = ArtifactSpiritEngine.awaken(char, target_name)
                    if res.get("changed"):
                        CharacterRepository.save(char)
                    _spirit_ret = {"ok": bool(res.get("success")), "text": res.get("message", ""), "status": self._status_dict(char)}
                    if res.get("changed"):
                        # 器灵认主幕（game-feel-phase3 §4.2 H-S1）：既有
                        # save 之后只增 ceremony；changed=False/失败不产幕
                        try:
                            from core.artifact_spirit import find_equipped as _find_eq
                            from core.ceremony import build_spirit_ceremony

                            _sp_item = _find_eq(char, target_name)
                            if _sp_item is not None:
                                _spirit_ret["ceremony"] = build_spirit_ceremony(
                                    char, _sp_item)
                        except Exception:
                            pass
                    return _spirit_ret
                ret = {"ok": True, "text": _spirit_panel(char), "status": self._status_dict(char)}
                sp = _spirit_data(char)
                if sp is not None:
                    ret["spirit"] = sp
                return ret
            if action in ("/温养", "/nourish"):
                # 温养（gallery-gameplay §6.4）：明价日限，门禁在引擎内。
                from core.artifact_spirit import ArtifactSpiritEngine

                res = ArtifactSpiritEngine.nourish(char, parts[1] if len(parts) > 1 else "")
                if res.get("changed"):
                    CharacterRepository.save(char)
                return {"ok": bool(res.get("success")), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/灵语", "/spirit_say"):
                # 灵语（gallery-gameplay §6.3）：AI 编排在引擎的 gateway 路径，
                # 不可用自动本地台词降级；门禁在引擎内，写路径 save 收尾。
                from core.artifact_spirit import ArtifactSpiritEngine

                words = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                res = ArtifactSpiritEngine.talk(char, words)
                if res.get("changed"):
                    CharacterRepository.save(char)
                _spirit_resp = {"ok": bool(res.get("success")), "text": res.get("message", ""), "status": self._status_dict(char)}
                if res.get("success"):
                    # 交谈结构化（chat-structure §B-8）：灵语正文与注记分型下发，
                    # 弹窗按字段渲染；不加 chat_open，命令框 /灵语 维持 feed 呈现。
                    _spirit_resp["chat_lines"] = [
                        _cl_npc(res.get("spirit_name") or "器灵", res.get("reply") or "")
                    ] + [_cl_sys(n) for n in (res.get("notes") or []) if str(n).strip()]
                    _spirit_resp["npc"] = res.get("spirit_name")
                    _spirit_resp["spirit_name"] = res.get("spirit_name")
                    _spirit_resp["item_name"] = res.get("item_name")
                return _spirit_resp
            if action in ("/wallet", "/钱包"):
                from core.wallet import wallet_panel_text
                from storage.db import AccountRepository as _AR

                account = LegacyRepository.get_or_create(char.user_id)
                text = wallet_panel_text(account, _AR.get_username(char.user_id))
                return {"ok": True, "text": text, "status": self._status_dict(char),
                        "wallet": self._status_dict(char)["wallet"]}
            if action in ("/wallet_withdraw", "/钱包提取"):
                if char.status == CharacterStatus.DEAD or char.lifespan.is_dead():
                    return {"ok": False, "error": "身死道消，钱包须转世重生后方可提取。"}
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/钱包提取 <金额>（正整数，不超过钱包余额）"}
                from core.wallet import withdraw_to_character

                account = LegacyRepository.get_or_create(char.user_id)
                res = withdraw_to_character(account, char, int(parts[1]))
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "提取失败")}
                LegacyRepository.save(account)
                CharacterRepository.save(char)
                return {"ok": True, "text": res["message"], "status": self._status_dict(char),
                        "wallet": self._status_dict(char)["wallet"]}
            if action in ("/reborn", "/转世"):
                boosts: List[str] = []
                new_name = None
                # /转世 [道号] [boost...]
                rest = parts[1:]
                for tok in rest:
                    if tok.startswith("heirloom:") and len(tok) > len("heirloom:"):
                        # 参数式遗物 token：heirloom:<物品名>（物品名无空格，整段透传引擎）
                        boosts.append(tok)
                    elif tok in LEGACY_BOOSTS:
                        boosts.append(tok)
                    elif tok.isdigit():
                        # 数字对应 boosts 列表顺序
                        keys = list(LEGACY_BOOSTS.keys())
                        i = int(tok) - 1
                        if 0 <= i < len(keys):
                            boosts.append(keys[i])
                    elif not new_name:
                        new_name = tok
                res = self.reincarnate(token, name=new_name, boosts=boosts)
                return res
            if action in ("/here", "/同场"):
                rows = list_here(char)
                # 图鉴事件点亮（gallery-gameplay §8.3）：同场组装时 NPC 原型 /
                # 已定相玩家人物图入图鉴；钩子失败不影响同场列表。
                try:
                    from core import gallery as _gallery

                    for _row in rows:
                        _other = CharacterRepository.get_by_id(_row.get("id", ""))
                        if _other is None:
                            continue
                        if _row.get("is_npc"):
                            _gallery.note_npc_encounter(char, _other)
                        else:
                            _gallery.note_player_encounter(char, _other)
                except Exception:
                    pass
                return {
                    "ok": True,
                    "text": format_here(char, rows),
                    "count": len(rows),
                    "here": rows,
                }
            if action in ("/profile", "/人物", "/角色"):
                target = None
                if len(parts) > 1:
                    target = CharacterRepository.get_by_name(parts[1])
                    if not target:
                        return {"ok": False, "error": f"查无此人：{parts[1]}"}
                prof = build_profile(char, target)
                return {
                    "ok": True,
                    "text": format_profile(char, prof),
                    "profile": prof,
                }
            if action in ("/roster", "/名录"):
                from core.npc_roster import roster_by_sect, seed_roster
                seed_roster()
                groups = roster_by_sect()
                lines = []
                for sect, members in groups.items():
                    lines.append(f"【{sect}】{len(members)}人")
                    for m in members:
                        lines.append(f"  · {m}")
                return {"ok": True, "text": "\n".join(lines), "count": sum(len(v) for v in groups.values())}
            if action in ("/who",):
                return {"ok": True, "text": self._who(), "who": self._who_data()}
            if action in ("/go", "/前往"):
                dest = parts[1] if len(parts) > 1 else ""
                res = self._go(char, dest)
                if res.get("ok"):
                    try:
                        from core.tasks import hook_note

                        n = hook_note(char, "move")
                        if n:
                            res["text"] = n + "\n" + (res.get("text") or "")
                    except Exception:
                        pass
                return res
            if action in ("/meditate", "/闭关", "/打坐"):
                hours = 1.0
                if len(parts) > 1:
                    try:
                        hours = float(parts[1])
                    except ValueError:
                        hours = 1.0
                return self._meditate(char, hours)
            if action in ("/emerge", "/出关"):
                return self._emerge(char)
            if action in ("/reclude", "/归隐"):
                hours = 72.0
                if len(parts) > 1:
                    try:
                        hours = float(parts[1])
                    except ValueError:
                        hours = 72.0
                res = ProtectionEngine.enter_reclusion(char, hours)
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("PROTECT", "enter_reclusion", name=char.name, hours=hours)
                return {"ok": res.get("success"), "text": res.get("message", ""), "protect": res}
            if action in ("/unreclude", "/出隐"):
                res = ProtectionEngine.exit_reclusion(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("PROTECT", "exit_reclusion", name=char.name)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/logout", "/下线"):
                return self.logout(token)
            if action in ("/任务", "/tasks", "/quest"):
                from core.tasks import handle_task_command, hook_note

                hook_note(char, "look_task")
                return handle_task_command(char, parts)
            if action in ("/goals", "/目标"):
                from core.tasks import hook_note

                n = hook_note(char, "look_task") or hook_note(char, "look_goals")
                GoalEngine.sync_progress(char)
                return {"ok": True, "text": GoalEngine.format_board(char), "goals": GoalEngine.list_for(char)}
            if action in ("/近况", "/briefing"):
                try:
                    from core.jianghu_sim import JianghuSimulator, format_offline_report
                    from core.briefing import briefing as build_briefing
                    from core.goals import evaluate_and_complete

                    try:
                        off = JianghuSimulator.simulate_offline()
                    except Exception:
                        off = {}
                    evaluate_and_complete(char)
                    CharacterRepository.save(char)
                    b = build_briefing(char)
                    text = b.get("text") or ""
                    if off.get("events"):
                        text = format_offline_report(off) + "\n\n" + text
                    return {
                        "ok": True,
                        "text": text,
                        "goals": b.get("goals") or [],
                        "related": b.get("related") or [],
                        "entry": b.get("entry"),
                    }
                except Exception as e:
                    return {"ok": False, "error": f"近况生成失败：{e}"}
            # action 已 lower()：大小写混合别名必须同时登记小写形式
            if action in ("/ailog", "/ai日志", "/ai_log"):
                from ai.calllog import tail_ai_calls, AI_LOG_PATH
                n = 8
                if len(parts) > 1 and parts[1].isdigit():
                    n = max(1, min(30, int(parts[1])))
                rows = tail_ai_calls(n)
                if not rows:
                    return {"ok": True, "text": f"暂无 AI 调用记录。\n日志文件：{AI_LOG_PATH}\n网页：ailog.html"}
                lines = [f"【AI 调用日志】最近 {len(rows)} 条（完整见 web/ailog.html 或 {AI_LOG_PATH}）"]
                for r in rows:
                    lines.append(
                        f"· {r.get('channel')} {r.get('model')} HTTP {r.get('http_status')} "
                        f"{r.get('duration_ms')}ms {r.get('status')} | "
                        f"{(r.get('prompt') or '')[:40]}…"
                    )
                return {"ok": True, "text": "\n".join(lines), "items": rows}
            if action in ("/ai", "/ai自检"):
                from ai.gateway import probe_ai_channel, ccswitch_runtime
                from config import LLM_API_BASE, LLM_MODEL, LLM_API_KEY, USE_CCSWITCH
                from core.world_director import director_quality_report

                rt = ccswitch_runtime() if USE_CCSWITCH else {}
                health = probe_ai_channel(force=True)
                ok = bool(health.get("ok"))
                mode = "CC Switch 本机代理" if USE_CCSWITCH else "OpenAI 兼容直连"
                base = rt.get("base") or LLM_API_BASE
                model = rt.get("model") or LLM_MODEL
                lines = [
                    f"【AI 自检】模式：{mode}",
                    f"地址：{base} · 模型：{model}",
                    f"对话测试：{'成功 ' + str(health.get('sample') or '') if ok else '失败 — ' + str(health.get('error') or '')}",
                    "",
                ]
                try:
                    q = director_quality_report()
                    lines.append(
                        f"【天道导演链路】{q.get('passed')}/{q.get('total')} 项通过 · "
                        f"真AI就绪={q.get('ready_for_ai_director')} · 本地降级={q.get('local_fallback_allowed')}"
                    )
                    for c in q.get("checks") or []:
                        mark = "✓" if c.get("ok") else "✗"
                        lines.append(f"  {mark} {c.get('name')}  {c.get('detail') or ''}")
                except Exception as e:
                    q = {}
                    lines.append(f"【天道导演链路】自检失败：{e}")
                lines += [
                    "",
                    "若用 CC Switch：.env 设 USE_CCSWITCH=1，并保持 CC Switch 在线、",
                    "当前 Claude 账号可用（在 CC Switch 界面切换账号）。",
                    "健康结果已写入 world_state，失败时交谈/事件会降级并提示。",
                    "网页 HUD：/world/director · 按钮：天道/势力/望气/世界弧/纪元回流",
                ]
                return {
                    "ok": True,
                    "text": "\n".join(lines),
                    "ai_ok": ok,
                    "ai_data": health,
                    "director_quality": q,
                }
            if action in ("/帮助", "/help", "/指令"):
                from core.command_catalog import format_help, search_commands

                kw = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
                text = format_help(kw)
                return {
                    "ok": True,
                    "text": text,
                    "commands": search_commands(kw, limit=40) if kw else search_commands("", limit=80),
                }
            if action in ("/qi", "/灵气"):
                return {"ok": True, "text": qi_mod.qi_status_text(), "qi": qi_mod.effective_density(1.0)}
            if action in ("/season", "/纪元"):
                # 纪元查询顺带惰性触发本纪元天象播报（幂等，F13）
                try:
                    from core.season_theme import SeasonThemeEngine

                    SeasonThemeEngine.ensure_announced()
                except Exception:
                    pass
                return {"ok": True, "text": season_status_text(), "season": season_info()}
            if action in ("/omen", "/天象"):
                # 纪元天象（F13）：当前纪元主题/修正/余天，纯规则推导；
                # 首次查询惰性播报本纪元天象（world_state 标记防重播）；
                # 推导异常时降级为静默口径文案，不阻断查询（与 _season_theme_summary 同口径）
                try:
                    from core.season_theme import SeasonThemeEngine

                    SeasonThemeEngine.ensure_announced()
                    return {
                        "ok": True,
                        "text": SeasonThemeEngine.panel_text(),
                        "season_theme": SeasonThemeEngine.summary(),
                    }
                except Exception:
                    return {
                        "ok": True,
                        "text": "【天象】天象沉静，天地无言，本纪元无天象加身。",
                        "season_theme": self._season_theme_summary(),
                    }
            if action in ("/rumors", "/传闻"):
                from core.rumors import format_rumor_board

                n = 8
                if len(parts) > 1 and parts[1].isdigit():
                    n = max(1, min(20, int(parts[1])))
                return {"ok": True, "text": format_rumor_board(n)}
            if action in ("/channel", "/频道"):
                from core.world_channel import WorldChannel, kind_cn

                n = 15
                if len(parts) > 1 and parts[1].isdigit():
                    n = max(1, min(40, int(parts[1])))
                rows = []
                for m in reversed(WorldChannel.recent(limit=n)):
                    row = {
                        "severity": m.level,
                        "type": m.kind,
                        "text": m.text,
                        "actor": m.actor,
                        "location": m.location,
                        "ts": m.ts,
                    }
                    cn = kind_cn(m.kind)
                    if cn:
                        row["type_cn"] = cn
                    rows.append(row)
                return {"ok": True, "text": WorldChannel.format_board(n), "channel": rows}
            if action in ("/notice", "/公告"):
                from core.world_channel import WorldChannel

                return {"ok": True, "text": WorldChannel.format_announcements(10)}
            if action in ("/gm",):
                from core.world_channel import check_gm_token, post_gm
                from config import GM_TOKEN as _GT

                if not _GT:
                    return {"ok": False, "error": "服务器未配置 GM_TOKEN。"}
                # /gm <token> <文案...>
                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/gm <token> <文案>"}
                if not check_gm_token(parts[1]):
                    return {"ok": False, "error": "天道未授你传讯之权。"}
                text = command.strip().split(None, 2)[2]
                msg = post_gm(text)
                try:
                    from core.name_registry import review_and_register

                    rev = review_and_register(text, source="gm_broadcast", author="GM")
                    extra = ""
                    if rev.get("registered"):
                        extra = "\n名物司已记入听闻册：" + "、".join(x["name"] for x in rev["registered"])
                    return {
                        "ok": True,
                        "text": f"【公告已发】{msg.text if msg else ''}{extra}",
                    }
                except Exception:
                    return {
                        "ok": True,
                        "text": f"【公告已发】{msg.text if msg else ''}",
                    }
            if action in ("/名物", "/mingwu"):
                from core.name_registry import format_board, materialize_location, get_heard

                if len(parts) >= 4 and parts[1] in ("物化", "locate"):
                    from core.world_channel import check_gm_token

                    if not check_gm_token(parts[2]):
                        return {"ok": False, "error": "天道未授你物化之权。用法：/名物 物化 <GM_TOKEN> <名称>"}
                    heard = get_heard("".join(parts[3:]))
                    if not heard:
                        return {"ok": False, "error": "听闻册无此名。"}
                    res = materialize_location(heard, player=char)
                    return {"ok": res.get("success"), "text": res.get("message", "")}
                if len(parts) >= 2 and parts[1] in ("物化", "locate"):
                    return {"ok": False, "error": "用法：/名物 物化 <GM_TOKEN> <名称>；玩家请用 /追查 <名>"}
                n = 15
                if len(parts) > 1 and parts[1].isdigit():
                    n = max(1, min(30, int(parts[1])))
                from core.name_registry import list_heard

                heard = list_heard(limit=n)
                ret = {"ok": True, "text": format_board(n)}
                if heard:
                    ret["relics"] = [
                        {
                            "name": r.get("name"),
                            "type": r.get("type"),
                            "status": r.get("status"),
                            "desc": r.get("desc"),
                            "source": r.get("source"),
                            "confidence": r.get("confidence"),
                        }
                        for r in heard
                    ]
                return ret
            if action in ("/追查", "/chase"):
                from core.name_registry import chase

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/追查 <听闻地点名>，先 /名物"}
                res = chase(char, "".join(parts[1:]))
                if res.get("success"):
                    CharacterRepository.save(char)
                return {
                    "ok": res.get("success"),
                    "text": res.get("message", ""),
                    "chased": res.get("chased"),
                    "new_location": res.get("location"),
                }
            if action in ("/奇遇"):
                from core.omen_scene import (
                    start_scene,
                    choose as omen_choose,
                    say as omen_say,
                    abandon as omen_abandon,
                    get_scene,
                )

                sub = parts[1] if len(parts) > 1 else ""
                # 弃
                if sub in ("弃", "abandon"):
                    res = omen_abandon(char)
                    return {
                        "ok": res.get("success"),
                        "text": res.get("message", ""),
                        "omen_open": False,
                        "omen_ended": True,
                        "omen_image": res.get("omen_image", ""),
                        "status": self._status_dict(char),
                    }
                # 选项
                if sub.isdigit():
                    res = omen_choose(char, sub)
                    # 命途求值 T4（二期 §3.6）：奇遇结算返回组装点
                    try:
                        from core.fate_thread import FateThreadEngine as _FTEo

                        if _FTEo.evaluate_for(char).get("changed"):
                            CharacterRepository.save(char)
                    except Exception:
                        pass
                    still_open = bool(get_scene(char.id))
                    from core.omen_scene import current_choices, scene_image_path

                    return {
                        "ok": res.get("success"),
                        "text": res.get("message", ""),
                        "omen_open": still_open,
                        "omen_inline": still_open,
                        "omen_choices": current_choices(char.id) if still_open else [],
                        "omen_ended": bool(res.get("ended")),
                        "omen_status": res.get("omen_status"),
                        "omen_image": scene_image_path(get_scene(char.id)) if still_open else res.get("omen_image", ""),
                        "status": self._status_dict(char),
                    }
                # 有进行中则渲染
                sc = get_scene(char.id)
                if sc:
                    from core.omen_scene import _render, current_choices, scene_image_path

                    return {
                        "ok": True,
                        "text": _render(sc, char),
                        "omen_open": True,
                        "omen_inline": True,
                        "omen_title": sc.get("title"),
                        "omen_choices": current_choices(char.id),
                        "omen_image": scene_image_path(sc),
                        "status": self._status_dict(char),
                    }
                return {
                    "ok": True,
                    "text": "【天机渺茫】机缘天定，不可强求……",
                    "omen_open": False,
                    "omen_inline": False,
                    "omen_image": "",
                    "status": self._status_dict(char),
                }
            if action in ("/omen_say", "/奇遇说"):
                from core.omen_scene import say as omen_say, get_scene

                words = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                if not get_scene(char.id):
                    return {
                        "ok": False,
                        "error": "当前无奇遇会话。可 /奇遇 开启。",
                        "omen_open": False,
                        "status": self._status_dict(char),
                    }
                try:
                    from core.name_guard import reject_player_creation

                    rej = reject_player_creation(words)
                    if rej:
                        return {"ok": False, "error": rej["message"], "status": self._status_dict(char)}
                except Exception:
                    pass
                res = omen_say(char, words)
                still_open = not bool(res.get("ended"))
                from core.omen_scene import current_choices, scene_image_path

                return {
                    "ok": res.get("success"),
                    "text": res.get("message", ""),
                    "omen_open": still_open,
                    "omen_inline": still_open,
                    "omen_choices": current_choices(char.id) if still_open else [],
                    "omen_ended": bool(res.get("ended")),
                    "omen_status": res.get("omen_status"),
                    "omen_image": scene_image_path(get_scene(char.id)) if still_open else res.get("omen_image", ""),
                    "intent": res.get("intent"),
                    "status": self._status_dict(char),
                }
            if action in ("/legend", "/传说", "/典籍"):
                from core.era_reentry import active_bias, format_era_board
                from core.legends import count_legends, format_legends, list_legends
                from core.era_reentry import TYPE_CN as _ERA_TYPE_CN

                season = None
                if len(parts) > 1 and parts[1].lstrip("-").isdigit():
                    season = int(parts[1])
                text = format_legends(season=season)
                try:
                    text += "\n\n" + format_era_board()
                except Exception:
                    pass
                _bias = active_bias()
                return {
                    "ok": True,
                    "text": text,
                    "legends": {
                        "legends": [
                            {
                                "title": r.title,
                                "text": r.text,
                                "season": r.season,
                                "actor": r.actor,
                                "weight": r.weight,
                            }
                            for r in list_legends(season=season, limit=12)
                        ],
                        "total": count_legends(season),
                        "active_bias": _bias,
                        "active_bias_cn": {_ERA_TYPE_CN.get(k, k): v for k, v in _bias.items()},
                    },
                }
            if action in ("/links", "/关系"):
                from core.collusion import format_links, links_of
                from storage.db import CharacterRepository as CR

                def _links_rows(owner):
                    rows = []
                    for l in links_of(owner.id)[:12]:
                        _oid, oname = l.other_side(owner.id)
                        rows.append(
                            {
                                "kind": l.link_type,
                                "name": oname,
                                "strength": l.strength,
                                "note": l.note or "",
                            }
                        )
                    return rows

                if len(parts) < 2:
                    return {"ok": True, "text": format_links(char), "links": _links_rows(char)}
                target = CR.find_alive_by_name("".join(parts[1:]))
                if not target:
                    return {"ok": False, "error": f"未寻得【{''.join(parts[1:])}】"}
                return {"ok": True, "text": format_links(target), "links": _links_rows(target)}
            if action in ("/apocalypse", "/大劫"):
                if len(parts) > 1 and parts[1] in ("结算", "settle"):
                    return self._settle_apocalypse()
                info = season_info()
                return {
                    "ok": True,
                    "text": (
                        season_status_text()
                        + "\n大劫降临后输入 /大劫 结算，未飞升者应劫转世并结转道统。"
                    ),
                    "season": info,
                }
            if action in ("/map", "/宝图", "/看宝图"):
                from core.treasure_system import TreasureEngine, calculate_fengshui_direction
                from core.world_grid import WorldGridEngine
                query = parts[1] if len(parts) > 1 else None
                res = TreasureEngine.read_map(char, query)
                # 线索链激活写在图实体内（随角色行落盘，gallery-gameplay §5.4）
                if res.get("chain_changed"):
                    CharacterRepository.save(char)
                ret = {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
                tmap = res.get("item") if res.get("success") else None
                if tmap is not None:
                    # 八卦/线索取纯规则 calculate_fengshui_direction（不复调含 AI
                    # 分支的 get_directional_guide，防两次 AI 调用与口径分叉；
                    # AI 关闭环境下两者逐字一致）。
                    md = tmap.custom_metadata or {}
                    target_node = WorldGridEngine.get_node(md.get("target_node_id", ""))
                    curr_node = WorldGridEngine.get_node(char.location)
                    guide = calculate_fengshui_direction(curr_node, target_node)
                    coords = None
                    if target_node is not None:
                        coords = list(getattr(target_node, "coordinates", (0, 0)))
                    ret["treasure_map"] = {
                        "name": tmap.name,
                        "tier": getattr(tmap, "tier", None),
                        "target_node": md.get("target_node_name"),
                        "target_node_id": md.get("target_node_id"),
                        "coords": coords,
                        "archetype": md.get("archetype"),
                        "archetype_cn": {
                            "combat": "凶地降妖",
                            "element_puzzle": "五行天机阵",
                            "ruin_hazard": "地渊残迹",
                        }.get(md.get("archetype"), md.get("archetype")),
                        "riddle": md.get("riddle_text"),
                        "clue": guide.get("clue"),
                        "bagua": guide.get("bagua"),
                        "rhyme": guide.get("rhyme"),
                    }
                return ret

            if action in ("/dig", "/挖宝"):
                from core.treasure_system import TreasureEngine
                from core.treasure_clue import TreasureClueEngine
                choice = parts[1] if len(parts) > 1 else None
                # 开匣前抓链快照：dig 耗图后链载体消亡，完成奖励钩子凭快照结算（§5.6）
                _chain_snap = TreasureClueEngine.snapshot_chain(char)
                res = TreasureEngine.dig(char, choice_id=choice)
                if res.get("success") and res.get("outcome"):
                    try:
                        _bonus = TreasureClueEngine.on_chest_opened(char, _chain_snap, res.get("outcome"))
                        if _bonus.get("message"):
                            res["message"] = (res.get("message") or "") + _bonus["message"]
                    except Exception:
                        pass
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("DECISION", "dig", name=char.name, outcome=res.get("outcome"))
                # 得宝幕（game-feel-phase3 §3.3 H-L1）：结算与 save 之后
                # 只增 ceremony（纯读拼装，失败降级为 None 不炸主流程）
                _loot_ceremony = None
                if res.get("success") and res.get("equipment"):
                    try:
                        from core.ceremony import (
                            build_loot_ceremony,
                            loot_ceremony_candidate,
                        )

                        _eq = res.get("equipment") or {}
                        if loot_ceremony_candidate(_eq.get("kind"), _eq.get("tier")):
                            _loot_ceremony = build_loot_ceremony(
                                char, _eq, source="treasure_dig")
                    except Exception:
                        _loot_ceremony = None
                return {
                    "ok": res.get("success"),
                    "text": res.get("message", ""),
                    "status": self._status_dict(char),
                    "ceremony": _loot_ceremony,
                    "equipment": res.get("equipment"),
                    "pill": res.get("pill"),
                    "stone_gain": res.get("stone_gain", 0),
                    "stone_loss": res.get("stone_loss", 0),
                    "wrong_location": res.get("wrong_location"),
                    "target_node_name": res.get("target_node_name"),
                    "target_node_id": res.get("target_node_id"),
                    "bagua": res.get("bagua"),
                    "direction_text": res.get("direction_text"),
                    "omen_inline": res.get("omen_inline"),
                    "omen_title": res.get("omen_title"),
                    "omen_choices": res.get("omen_choices"),
                }

            if action in ("/do", "/做", "/act", "/言行"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/做 <言行>"}
                from core.character_integrity import CharacterIntegrity, CharacterIntegrityError
                from core.name_guard import reject_player_creation
                from core.treasure_system import TreasureEngine
                from core.world_grid import WorldGridEngine

                try:
                    CharacterIntegrity.assert_alive(char)
                    CharacterIntegrity.assert_idle(char, action="/做")
                except CharacterIntegrityError as error:
                    return {"ok": False, "error": str(error), "status": self._status_dict(char)}
                free_text = command.strip().split(None, 1)[1].strip()
                maps = char.find_items_by_kind(ItemKind.TREASURE_MAP)
                # 仅当身上有宝图且玩家确实身处宝图目标节点时，才路由到挖宝 DM 破局
                if maps:
                    target_id = maps[0].custom_metadata.get("target_node_id", "")
                    target_name = maps[0].custom_metadata.get("target_node_name", "")
                    curr_node = WorldGridEngine.get_node(char.location)
                    if curr_node and (curr_node.id == target_id or curr_node.base_name == target_name):
                        from core.treasure_clue import TreasureClueEngine as _TCE

                        _chain_snap = _TCE.snapshot_chain(char)
                        res = TreasureEngine.resolve_free_action(char, free_text)
                        if res.get("success") and res.get("outcome"):
                            try:
                                _bonus = _TCE.on_chest_opened(char, _chain_snap, res.get("outcome"))
                                if _bonus.get("message"):
                                    res["message"] = (res.get("message") or "") + _bonus["message"]
                            except Exception:
                                pass
                        if res.get("success"):
                            CharacterRepository.save(char)
                            log_event("FREE_ACTION", "treasure_free", name=char.name, outcome=res.get("outcome"))
                        ret = {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
                        return self._append_natural_omen(char, ret, context="寻幽破局")
                rejection = reject_player_creation(free_text)
                if rejection:
                    log_event("GATE", "name_creation_rejected", name=char.name, sample=str(rejection.get("hits"))[:80])
                    return {"ok": False, "error": rejection["message"], "rejected": True}
                res = FreeActionEngine.resolve(char, free_text, others=self.others_at(char))
                if not res.get("ok"):
                    return {"ok": False, "error": res.get("error", "无果"), "status": self._status_dict(char)}
                CharacterRepository.save(char)
                spawned = res.get("spawned")
                if spawned:
                    CharacterRepository.save(spawned)
                ret = {
                    "ok": True,
                    "text": res.get("text", ""),
                    "intent": res.get("intent"),
                    "outcome": res.get("outcome"),
                    "spawned": bool(spawned),
                    "status": self._status_dict(char),
                }
                return self._append_natural_omen(char, ret, context="随心行止")


            if action in ("/equip", "/穿戴"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/穿戴 <装备名>"}
                item = command.strip().split(None, 1)[1]
                res = EquipEngine.equip(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/unequip", "/卸下"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/卸下 <装备名>"}
                item = command.strip().split(None, 1)[1]
                res = EquipEngine.unequip(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""),
                        "status": self._status_dict(char)}
            if action in ("/pets", "/pet", "/灵宠"):
                return {
                    "ok": True,
                    "text": PetEngine.panel_text(char),
                    "status": self._status_dict(char),
                    "pets": PetEngine.panel_data(char),
                }
            if action in ("/契约", "/contract"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/契约 <兽名>（先在 /灵宠 看待契约灵兽）"}
                item = command.strip().split(None, 1)[1]
                res = PetEngine.contract(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("DECISION", "pet_contract", name=char.name, species=char.pets[-1].species if char.pets else "")
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/喂养", "/feed"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/喂养 <宠名> [丹药名]"}
                from core.pets import split_feed_args

                pet_hint, pill = split_feed_args(
                    char, command.strip().split(None, 1)[1].split()
                )
                res = PetEngine.feed(char, pet_hint, pill)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/出战", "/deploy"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/出战 <宠名>"}
                item = command.strip().split(None, 1)[1]
                res = PetEngine.deploy(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/休息", "/petrest"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/休息 <宠名>"}
                item = command.strip().split(None, 1)[1]
                res = PetEngine.rest(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/放生", "/release"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/放生 <宠名>"}
                item = command.strip().split(None, 1)[1]
                res = PetEngine.release(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/cave", "/洞府"):
                return {
                    "ok": True,
                    "text": FarmEngine.panel_text(char),
                    "status": self._status_dict(char),
                }
            if action in ("/opencave", "/开辟"):
                res = FarmEngine.open_cave(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/sow", "/播种"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/播种 <种子名> [数量]"}
                seed_hint, sow_count = split_sow_args(parts[1:])
                res = FarmEngine.sow(char, seed_hint, sow_count)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/harvest", "/收获"):
                res = FarmEngine.harvest(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/upgradecave", "/升级洞府"):
                res = FarmEngine.upgrade_cave(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/quests", "/委托"):
                changed = QuestEngine.settle_expired(char)
                if changed:
                    CharacterRepository.save(char)
                return {
                    "ok": True,
                    "text": QuestEngine.panel_text(char),
                    "status": self._status_dict(char),
                    "quests": QuestEngine.panel_data(char),
                }
            if action in ("/acceptquest", "/接委托"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/接委托 <NPC名或编号>（先 /委托 查看）"}
                hint = command.strip().split(None, 1)[1]
                res = QuestEngine.accept(char, hint.strip())
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/deliver", "/交付"):
                res = QuestEngine.deliver(char)
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/abandonquest", "/弃委托"):
                res = QuestEngine.abandon(char)
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/promises", "/诺言"):
                changed = PromiseEngine.settle_due(char, actor_obj=char)
                if changed:
                    CharacterRepository.save(char)
                return {
                    "ok": True,
                    "text": PromiseEngine.panel_text(char),
                    "status": self._status_dict(char),
                    "promises": PromiseEngine.panel_data(char),
                }
            if action in ("/promise", "/许诺"):
                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/许诺 <对象名> 赠物 <物品名> | 抵达 <地点名> | 委托 | 不攻（唯指令立诺入账，交谈口头应承不算）"}
                target = CharacterRepository.get_by_name(parts[1])
                if not target:
                    return {"ok": False, "error": f"查无此人：{parts[1]}"}
                kind = PROMISE_KIND_ALIASES.get(parts[2]) or PROMISE_KIND_ALIASES.get(parts[2].lower())
                if not kind:
                    return {"ok": False, "error": "诺目须是规则四类之一：赠物 / 抵达 / 委托 / 不攻（自由口诺天道不记）"}
                param = parts[3] if len(parts) > 3 else ""
                res = PromiseEngine.make_promise(char, target, kind, param)
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/acceptpromise", "/应诺"):
                hint = parts[1] if len(parts) > 1 else ""
                res = PromiseEngine.accept(char, hint)
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/breakpromise", "/毁诺"):
                hint = parts[1] if len(parts) > 1 else ""
                res = PromiseEngine.break_promise(char, hint)
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/xinfa", "/心法"):
                return {
                    "ok": True,
                    "text": ArtSlotEngine.panel_text(char),
                    "status": self._status_dict(char),
                }
            if action in ("/主修", "/main_art"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/主修 <功法名>（须已习得，/心法 查看）"}
                item = command.strip().split(None, 1)[1]
                res = ArtSlotEngine.set_main(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/辅修", "/sub_art"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/辅修 <功法名>（须已习得，/心法 查看）"}
                item = command.strip().split(None, 1)[1]
                res = ArtSlotEngine.add_sub(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/卸功", "/remove_art"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/卸功 <功法名>（卸下主修或辅修）"}
                item = command.strip().split(None, 1)[1]
                res = ArtSlotEngine.remove(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/body", "/炼体", "/soul", "/炼神"):
                # 炼体/炼神双修（F10）：无参=面板；「修炼 [n]」=逐层精进（闭关不进白名单，天然锁门）
                track = "body" if action in ("/body", "/炼体") else "soul"
                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("修炼", "train"):
                    times = 1
                    if len(parts) > 2:
                        try:
                            times = int(parts[2])
                        except Exception:
                            times = 1
                    res = (BodySoulEngine.train_body(char, times) if track == "body"
                           else BodySoulEngine.train_soul(char, times))
                    if res.get("success"):
                        CharacterRepository.save(char)
                    return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
                if sub:
                    return {"ok": False, "error": f"用法：/{'炼体' if track == 'body' else '炼神'} 或 /{'炼体' if track == 'body' else '炼神'} 修炼 [次数]"}
                return {
                    "ok": True,
                    "text": BodySoulEngine.panel_text(char, track),
                    "status": self._status_dict(char),
                    "body_soul_detail": BodySoulEngine.detail_data(char),
                }
            if action in ("/demon", "/镇魔"):
                # 心魔长期状态（F16）：无参=面板（打开即惰性结算魔念）；服丹/静坐=镇压（闭关不进白名单，天然锁门）
                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("服丹", "pill"):
                    res = DemonStateEngine.suppress_pill(char)
                    if res.get("success"):
                        CharacterRepository.save(char)
                    return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
                if sub in ("静坐", "calm"):
                    res = DemonStateEngine.suppress_calm(char)
                    if res.get("success"):
                        CharacterRepository.save(char)
                    return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
                if sub:
                    return {"ok": False, "error": "用法：/镇魔 或 /镇魔 服丹 或 /镇魔 静坐"}
                text = DemonStateEngine.panel_text(char)
                CharacterRepository.save(char)  # 面板已 sync 魔念，落库锚点
                return {
                    "ok": True,
                    "text": text,
                    "status": self._status_dict(char),
                    "demon": DemonStateEngine.panel_data(char),
                }
            if action in ("/write_book", "/著书"):
                # 著书立说（F11）：无参=面板；「写」=燃寿著书（闭关不进白名单，天然锁门）
                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("写", "write"):
                    res = BookEngine.write_book(char)
                    if res.get("success"):
                        CharacterRepository.save(char)
                    return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
                if sub:
                    return {"ok": False, "error": "用法：/著书 或 /著书 写"}
                return {"ok": True, "text": BookEngine.panel_text(char), "status": self._status_dict(char)}
            if action in ("/read_book", "/研读"):
                # 研读（F11）：展卷所持手稿；首次研读结算收益与作者声望（引擎内幂等）
                hint = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                res = BookEngine.read_book(char, hint.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/rank", "/榜单", "/榜"):
                board = parts[1] if len(parts) > 1 else ""
                if not board:
                    return {
                        "ok": True,
                        "text": LeaderboardEngine.format_all(5),
                        "boards": LeaderboardEngine.public_boards(5),
                    }
                alias = {
                    "境界": "realm", "战力": "power", "凶名": "notoriety",
                    "道行": "daohang", "传奇": "fame", "资产": "assets",
                    "realm": "realm", "power": "power", "sin": "notoriety",
                    "dao": "daohang", "fame": "fame", "assets": "assets",
                }
                key = alias.get(board, board)
                ret = {"ok": True, "text": LeaderboardEngine.format_board(key), "board": key}
                pub = LeaderboardEngine.public_board(key)
                if pub.get("ok"):
                    ret["board_rows"] = pub["rows"]
                return ret
            if action in ("/ascend", "/飞升榜"):
                # 飞升榜（F12）：历世纪念碑，只读已落账前世，与现世六榜互不相干
                arg = parts[1] if len(parts) > 1 else None
                return {
                    "ok": True,
                    "text": AscensionEngine.panel_text(char, arg),
                    "ascend": AscensionEngine.board_rows(char, arg),
                }
            if action in ("/sect", "/宗门"):
                from core.sect import sect_board_data

                return {"ok": True, "text": format_sect_board(char), "sects": sect_board_data(char)}
            if action in ("/join_sect", "/拜入"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/拜入 <宗门>（须亲至总坛山门）"}
                res = join_sect(char, parts[1])
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("DECISION", "join_sect", name=char.name, sect=res.get("sect"))
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/leave_sect", "/叛门"):
                res = leave_sect(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/salary", "/领俸禄", "/俸禄"):
                res = claim_salary(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/promote", "/晋升"):
                res = promote(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/teach", "/传功"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/传功 <弟子道号>"}
                disciple = CharacterRepository.get_by_name(parts[1])
                if not disciple:
                    return {"ok": False, "error": f"查无此人：{parts[1]}"}
                res = transmit_teaching(char, disciple)
                if res.get("success"):
                    CharacterRepository.save(char)
                    CharacterRepository.save(disciple)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/adventure", "/探险"):
                target = ""
                if len(parts) > 1:
                    target = command.strip().split(None, 1)[1].strip()
                if not target:
                    return {"ok": True, "text": AdventureEngine.board_text(char),
                            "status": self._status_dict(char)}
                before_stones = char.spirit_stones
                try:
                    res = AdventureEngine.explore(char, target)
                except Exception as _adv_err:
                    if char.spirit_stones < before_stones:
                        char.spirit_stones = before_stones
                    CharacterRepository.save(char)
                    return {"ok": False, "error": f"大荒天机紊乱：{_adv_err}", "status": self._status_dict(char)}
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "探险失败"), "status": self._status_dict(char)}
                CharacterRepository.save(char)
                log_event(
                    "DECISION",
                    "adventure",
                    name=char.name,
                    target=res.get("target"),
                    win=res.get("combat_success"),
                    exp=res.get("exp_delta"),
                    loot=len(res.get("loot") or []),
                )
                payload = {
                    "ok": True,
                    "text": res.get("message", ""),
                    "adventure": res,
                    "status": self._status_dict(char),
                }
                return self._append_natural_omen(char, payload, context=f"大荒探险 · {res.get('target', '')}")
            if action in ("/配方", "/recipes"):
                from core.alchemy import book_data, format_book

                return {"ok": True, "text": format_book(char), "recipes": book_data(char)}
            if action in ("/炼丹", "/炼器"):
                kind = "pill" if "丹" in action else "equip"
                if len(parts) < 2:
                    return {"ok": False, "error": f"用法：{action} <配方名>，先 /配方"}
                from core.alchemy import craft

                res = craft(char, "".join(parts[1:]), kind)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {
                    "ok": res.get("success"),
                    "text": res.get("message", ""),
                    "crafted": res.get("crafted"),
                    "output": res.get("output"),
                }
            if action in ("/悟丹", "/悟器", "/forge", "/天工"):
                kind = "pill" if action in ("/悟丹",) or (action in ("/forge", "/天工") and len(parts) > 1 and parts[1] in ("丹药", "pill", "丹")) else "equip"
                if action in ("/悟器",):
                    kind = "equip"
                if action in ("/forge", "/天工") and len(parts) > 1:
                    mapping = {
                        "丹药": "pill", "pill": "pill", "丹": "pill",
                        "法宝": "equip", "装备": "equip", "equip": "equip", "器": "equip",
                    }
                    kind = mapping.get(parts[1], kind)
                hint = ""
                if len(parts) > 1:
                    rest = parts[1:]
                    if rest and rest[0] in ("丹药", "pill", "丹", "法宝", "装备", "equip", "器"):
                        rest = rest[1:]
                    hint = " ".join(rest)
                from core.alchemy import can_wu, mark_wu, learn_recipe, ingest_ai_recipe

                ok_w, why = can_wu(char)
                if not ok_w:
                    return {"ok": False, "error": why}
                # AI 悟方
                recipe = None
                try:
                    from ai.gateway import ai_available, _chat_json
                    from ai.play_prompts import forge_prompt
                    from config import ITEM_CATALOG as _IC

                    if ai_available():
                        data = _chat_json(
                            f"为修仙世界设计一张{'炼丹' if kind=='pill' else '炼器'}配方（不是直接给货）。\n"
                            f"理念：{hint or '随机'}\n"
                            f"可用材料仅限：{'、'.join(__import__('core.alchemy', fromlist=['x']).ALCHEMY_MATERIAL_POOL)}\n"
                            "输出 JSON：{\"name\":\"方名\",\"materials\":{\"百年灵芝\":1~3,\"妖兽内丹\":0~3},"
                            "\"stones_fee\":10~200,\"base_rate\":0.3~0.75,\"req_tier\":0~3,"
                            "\"output\":\"可选产出名\",\"pill_exp_mult\":0.1~0.4,\"power_bonus\":0.02~0.06,"
                            "\"lore\":\"40字\"}"
                        )
                        if data:
                            recipe = ingest_ai_recipe(data, kind)
                except Exception:
                    recipe = None
                if not recipe:
                    # 本地：抽一张未习得的默认配方
                    from core.alchemy import ensure_default_recipes, _all_recipes

                    known = ensure_default_recipes(char)
                    cand = [r for r in _all_recipes().values() if r["id"] not in known]
                    if cand:
                        recipe = random.choice(cand)
                if not recipe:
                    return {"ok": False, "error": "天机混沌，未能悟出新方。"}
                learn_recipe(char, recipe["id"])
                mark_wu(char)
                CharacterRepository.save(char)
                mats = "、".join(f"{k}×{v}" for k, v in recipe["materials"].items())
                return {
                    "ok": True,
                    "text": (
                        f"【悟得配方】{recipe['name']} → {recipe['output']}\n"
                        f"材料：{mats}；炉火 {recipe['stones_fee']}；基础成率 {recipe['base_rate']:.0%}\n"
                        f"备齐材料后 /炼{'丹' if recipe['kind']=='pill' else '器'} {recipe['name']}\n"
                        f"（悟方冷却 1 现实日）"
                    ),
                    "recipe": recipe,
                }
            if action in ("/gen_pill", "/生成丹药"):
                # 兼容旧指令 → 悟丹
                return self.handle(token, "/悟丹 " + (command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""))
            if action in ("/gen_equip", "/生成法宝"):
                return self.handle(token, "/悟器 " + (command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""))
            if action in ("/gen_monster", "/生成妖兽"):
                return {"ok": False, "error": "妖兽不可人造。可 /探险 遭遇，或 /悟丹 /悟器 开炉。"}
            if action in ("/secret", "/秘境"):
                if len(parts) > 1:
                    sub = parts[1]
                    if sub in ("探", "step", "推进"):
                        res = SecretRealmEngine.step(char)
                        if res.get("success"):
                            CharacterRepository.save(char)
                            if char.status == CharacterStatus.DEAD:
                                self._settle_if_needed(char, cause="秘境杀劫")
                        return {"ok": res.get("success"), "text": res.get("message", "")}
                    if sub in ("弃", "abandon"):
                        res = SecretRealmEngine.abandon(char)
                        return {"ok": res.get("success"), "text": res.get("message", "")}
                    res = SecretRealmEngine.enter(char, sub)
                    _scene_image = ""
                    if res.get("success"):
                        CharacterRepository.save(char)
                        try:
                            GoalEngine.add_opportunity(
                                char, res["chain"]["title"], "秘境探索进行中，/秘境 推进。"
                            )
                            CharacterRepository.save(char)
                        except Exception:
                            pass
                        # 图库（二期 §9.4）：秘境进入点亮其场景图，进入
                        # 返回只增 scene_image（无映射为空串，前端不渲染）。
                        try:
                            from core import gallery as _gallery_sr
                            from core.gallery_assets import scene_path_for_realm as _spr

                            _realm_name = (res.get("chain") or {}).get("realm_id") or sub
                            _gallery_sr.note_realm_visit(char, _realm_name)
                            _scene_image = _spr(_realm_name)
                        except Exception:
                            _scene_image = ""
                    return {"ok": res.get("success"), "text": res.get("message", ""), "scene_image": _scene_image}
                from core.secret_realm import realm_status as _realm_status

                return {
                    "ok": True,
                    "text": SecretRealmEngine.board_text(),
                    "realms": _realm_status(),
                }
            if action in ("/dungeon", "/禁地", "/锁妖塔", "/古窟"):
                from core.dungeon import DungeonEngine, DUNGEON_FLOORS
                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("叩关", "enter", "进", "开启"):
                    fl = 1
                    if len(parts) > 2 and parts[2].isdigit():
                        fl = int(parts[2])
                    res = DungeonEngine.start_dungeon(char, floor=fl)
                    # 图库（二期 §9.4）：副本进入点亮锁妖古窟场景图，
                    # 返回只增 scene_image（口径同秘境进入）。
                    _dg_scene_image = ""
                    if res.get("success"):
                        try:
                            from core import gallery as _gallery_dg
                            from core.gallery_assets import scene_path_for_realm as _spr_dg

                            _gallery_dg.note_realm_visit(char, "锁妖古窟")
                            _dg_scene_image = _spr_dg("锁妖古窟")
                        except Exception:
                            _dg_scene_image = ""
                    return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char), "scene_image": _dg_scene_image}
                if sub in ("撤离", "遁出", "retreat", "走"):
                    res = DungeonEngine.retreat(char)
                    return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
                if sub in ("深入", "下层", "next"):
                    res = DungeonEngine.advance_floor(char)
                    return {"ok": res.get("success"), "text": "踏入下一层！" if res.get("success") else res.get("message", ""), "status": self._status_dict(char)}
                if sub in ("探秘", "要穴", "explore", "node"):
                    res = DungeonEngine.interact_event(char)
                    return {"ok": res.get("success"), "text": "要穴探索完成！" if res.get("success") else res.get("message", ""), "status": self._status_dict(char)}
                sess = DungeonEngine.get_session(char.id)
                if sess and sess.get("active"):
                    return {"ok": True, "text": f"当前正身处【第{sess.get('floor', 1)}层】，状态：{sess.get('state')}。可用 /施法、/出招、/祭法宝、/撤离。", "status": self._status_dict(char)}
                return {"ok": True, "text": "【锁妖古窟】九幽镇妖之所，九重险地深藏造化。可用 /禁地 叩关 [层数] 启阵。", "status": self._status_dict(char)}

            if action in ("/cast", "/施法", "/神通"):
                from core.dungeon import DungeonEngine
                spell_key = parts[1] if len(parts) > 1 else "fire_blast"
                res = DungeonEngine.execute_combat_action(char, action="spell", spell_key=spell_key)
                logs_text = "\n".join(res.get("logs", [])) or res.get("message", "")
                return {"ok": res.get("success"), "text": logs_text, "status": self._status_dict(char)}

            if action in ("/cast_treasure", "/祭法宝", "/法宝大招"):
                from core.dungeon import DungeonEngine
                res = DungeonEngine.execute_combat_action(char, action="treasure")
                logs_text = "\n".join(res.get("logs", [])) or res.get("message", "")
                return {"ok": res.get("success"), "text": logs_text, "status": self._status_dict(char)}

            if action in ("/dungeon_attack", "/出招", "/斩击"):
                from core.dungeon import DungeonEngine
                res = DungeonEngine.execute_combat_action(char, action="attack")
                logs_text = "\n".join(res.get("logs", [])) or res.get("message", "")
                return {"ok": res.get("success"), "text": logs_text, "status": self._status_dict(char)}

            if action in ("/pick_boon", "/择道韵", "/领悟道韵"):
                from core.dungeon import DungeonEngine
                boon_key = parts[1] if len(parts) > 1 else ""
                res = DungeonEngine.choose_boon(char, boon_key)
                return {"ok": res.get("success"), "text": "道韵领悟圆满！" if res.get("success") else res.get("message", ""), "status": self._status_dict(char)}

            if action in ("/break", "/突破"):
                try:
                    from core.tasks import hook_note

                    n = hook_note(char, "look_breakthrough")
                    res = self._breakthrough(char, session)
                    if n:
                        res["text"] = n + "\n" + (res.get("text") or "")
                    return res
                except Exception:
                    return self._breakthrough(char, session)
            if action in ("/fight", "/斗法"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/斗法 <道号>"}
                return self._fight(char, parts[1])
            if action in ("/event", "/机缘"):
                return self._event(char)
            if action in ("/revenge", "/回访", "/因果"):
                rv = RevengeEngine.force_callback(char)
                if not rv:
                    return {"ok": True, "text": "账上暂无可供回访的血仇旧怨。"}
                CharacterRepository.save(char)
                if rv.get("spawned"):
                    CharacterRepository.save(rv["spawned"])
                return {"ok": True, "text": rv.get("text", ""), "event_id": rv.get("event_id")}
            if action in ("/tick", "/npc"):
                acted = NpcAgendaEngine.tick_world(max_npcs=3, force=True)
                if not acted:
                    return {"ok": True, "text": "诸位 NPC 皆在静观，世间无事。"}
                return {"ok": True, "text": "\n".join(r.get("text", "") for r in acted), "count": len(acted)}
            if action in ("/天道", "/heaven", "/导演"):
                from core.world_director import WorldDirector, handle_heaven_command
                from core.tasks import hook_note

                res = handle_heaven_command(action, parts)
                if "director" not in res:
                    res["director"] = WorldDirector.heaven_board_data()
                n = hook_note(char, "look_board")
                if n:
                    res["text"] = n + "\n" + (res.get("text") or "")
                return res
            if action in ("/世界弧", "/arc", "/弧"):
                from core.world_arc import arc_board_data, handle_arc_command

                res = handle_arc_command(parts)
                if "arc" not in res:
                    res["arcs"] = arc_board_data()
                return res
            if action in ("/世界弧应劫", "/弧应劫", "/应劫"):
                from core.world_arc import player_respond

                if len(parts) < 3:
                    return {
                        "ok": False,
                        "error": "用法：/世界弧应劫 <弧id> 应劫|避祸（先 /世界弧 查看）",
                    }
                return player_respond(parts[1].strip(), char, " ".join(parts[2:]))
            if action in ("/世情", "/worldinfo", "/世界演变", "/演变"):
                from core.schedule import format_world_schedule
                from core import rumors as _rum

                try:
                    _rum.maybe_ambient_tick(chance=0.05)
                except Exception:
                    pass
                offline_txt = ""
                try:
                    from core.jianghu_sim import format_offline_report, JianghuSimulator

                    # 轻量摘要：不在锁内跑重仿真（后台 tick 已负责演化）
                    try:
                        brief = JianghuSimulator.simulate_offline()
                        if brief.get("waves") or brief.get("events"):
                            offline_txt = format_offline_report(brief) + "\n\n"
                    except Exception:
                        offline_txt = ""
                except Exception:
                    offline_txt = ""
                simple = len(parts) > 1 and parts[1] in ("简", "simple")
                r = format_world_schedule(viewer_id=char.id, simple=simple)
                text = offline_txt + (r.get("text") or "")
                try:
                    from core.tasks import hook_note

                    n = hook_note(char, "look_schedule")
                    if n:
                        text = n + "\n" + text
                except Exception:
                    pass
                try:
                    import core.jianghu as _jh
                    text += "\n\n【江湖因果账】\n" + _jh.format_brief(4)
                except Exception:
                    pass
                return {
                    "ok": True,
                    "text": text,
                    "actions": r.get("actions"),
                    "evolution": r.get("evolution"),
                }
            if action in ("/追", "/follow"):
                from core.schedule import follow_action

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/追 <编号>，先 /世情"}
                res = follow_action(char, parts[1])
                return {"ok": res.get("success"), "text": res.get("message", "")}

            # ---------------- Wave2：师徒/结拜 ----------------
            if action in ("/拜师",):
                from core.social_bonds import propose_master

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/拜师 <道号>"}
                res = propose_master(char, "".join(parts[1:]))
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/确认拜师",):
                from core.social_bonds import confirm_master

                res = confirm_master(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/收徒",):
                from core.social_bonds import propose_disciple

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/收徒 <道号>（对方 /确认拜师）"}
                res = propose_disciple(char, "".join(parts[1:]))
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/出师",):
                from core.social_bonds import graduate

                res = graduate(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/结拜",):
                from core.social_bonds import propose_sworn

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/结拜 <道号>"}
                res = propose_sworn(char, "".join(parts[1:]))
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/结拜同意",):
                from core.social_bonds import accept_sworn

                res = accept_sworn(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/绝交",):
                from core.social_bonds import break_bond

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/绝交 <道号>"}
                res = break_bond(char, "".join(parts[1:]))
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/叛师",):
                from core.social_bonds import rebel_master

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/叛师 <师父道号>"}
                res = rebel_master(char, "".join(parts[1:]))
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/师门任务",):
                from core.social_bonds import format_master_task

                res = format_master_task(char)
                ret = {"ok": res.get("success"), "text": res.get("message", "")}
                if res.get("success"):
                    ret["sect_quests"] = {
                        "master": res.get("master"),
                        "task": res.get("task"),
                        "done": bool(res.get("done")),
                    }
                return ret
            if action in ("/交师门",):
                from core.social_bonds import submit_master_task

                res = submit_master_task(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/结义任务",):
                from core.social_bonds import format_sworn_task

                res = format_sworn_task(char)
                ret = {"ok": res.get("success"), "text": res.get("message", "")}
                if res.get("success"):
                    ret["sworn_quests"] = {
                        "partner": res.get("partner"),
                        "task": res.get("task"),
                        "done": bool(res.get("done")),
                    }
                return ret
            if action in ("/交结义",):
                from core.social_bonds import submit_sworn_task

                res = submit_sworn_task(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}

            # ---------------- Wave2：宗门贡献 ----------------
            if action in ("/贡献",):
                from core.sect_contrib import shop_data

                return {
                    "ok": True,
                    "text": (
                        f"【宗门贡献】{char.sect or '散修'} · {char.sect_contribution}\n"
                        + ("可 /上交 <货> · /兑换 · /宗门环" if char.sect else "先 /拜入 <宗门>")
                    ),
                    "contribution": {
                        "sect": char.sect or "散修",
                        "points": char.sect_contribution,
                        "catalog": shop_data(),
                    },
                }
            if action in ("/上交", "/donate"):
                from core.sect_contrib import donate_item

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/上交 <货名> [数量]"}
                qty = 1
                toks = parts[1:]
                if toks and toks[-1].isdigit():
                    qty = max(1, int(toks[-1]))
                    toks = toks[:-1]
                res = donate_item(char, "".join(toks), qty)
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/兑换",):
                from core.sect_contrib import format_shop, exchange, shop_data

                if len(parts) < 2:
                    return {
                        "ok": True,
                        "text": format_shop() + f"\n当前贡献：{char.sect_contribution}",
                        "contribution": {
                            "sect": char.sect or "散修",
                            "points": char.sect_contribution,
                            "catalog": shop_data(),
                        },
                    }
                res = exchange(char, "".join(parts[1:]))
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/宗门环", "/sectring"):
                from core.sect_contrib import format_ring

                return {"ok": True, "text": format_ring(char), "status": self._status_dict(char)}
            if action in ("/接宗门环", "/accepring"):
                from core.sect_contrib import accept_theme

                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/接宗门环 <1|2|3>"}
                res = accept_theme(char, int(parts[1]))
                if res.get("success") and res.get("hook") == "hunt":
                    pass
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/宗门势", "/sectpower"):
                from core.sect_contrib import sect_power_data, sect_powerboard

                return {"ok": True, "text": sect_powerboard(), "sect_power": sect_power_data()}
            if action in ("/势力", "/faction"):
                from core.faction import board_data as _faction_board_data, handle_faction_command

                res = handle_faction_command(parts, char)
                sub = (parts[1].strip().lower() if len(parts) > 1 else "")
                if res.get("ok") and sub not in ("令", "missions"):
                    res["factions"] = _faction_board_data(char)
                return res
            if action in ("/望气", "/echo", "/天象"):
                from core.player_echo import handle_echo_command
                from core.tasks import hook_note

                res = handle_echo_command(parts, char)
                n = hook_note(char, "look_echo")
                if n:
                    res["text"] = n + "\n" + (res.get("text") or "")
                return res
            if action in ("/纪元回流", "/era", "/史笔回流"):
                from core.era_reentry import era_board_data, handle_era_command

                res = handle_era_command(parts)
                res["era_flow"] = era_board_data()
                return res
            if action in ("/宗门令", "/sectorder", "/势力令"):
                from core.faction import handle_faction_command, list_missions

                res = handle_faction_command(["/势力", "令"], char)
                if res.get("ok"):
                    # 与 handle_faction_command 内部同源取令（本宗优先，无则全宗）。
                    ms = list_missions(sect=getattr(char, "sect", "") or "", status="open")
                    if not ms:
                        ms = list_missions(status="open")
                    res["sect_orders"] = [
                        {
                            "id": m.get("id"),
                            "sect": m.get("sect"),
                            "title": m.get("title"),
                            "kind": m.get("kind"),
                            "reward_contrib": m.get("reward_contrib"),
                        }
                        for m in ms
                    ]
                return res
            if action in ("/接宗门令", "/acceptorder"):
                from core.faction import handle_accept_mission

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/接宗门令 <令id>（/势力 或 /宗门令 查看）"}
                return handle_accept_mission(char, parts[1].strip())
            if action in ("/交宗门令", "/doneorder"):
                from core.faction import handle_complete_mission

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/交宗门令 <令id>"}
                return handle_complete_mission(char, parts[1].strip())
            if action in ("/议政", "/council"):
                from core.council import CouncilEngine

                ret = {"ok": True, "text": CouncilEngine.panel_text(char)}
                council = CouncilEngine.panel_data(char)
                if council is not None:
                    ret["council"] = council
                return ret
            if action in ("/投票", "/vote"):
                from core.council import CouncilEngine

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/投票 支持|反对"}
                res = CouncilEngine.vote(char, parts[1])
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/游说", "/lobby"):
                from core.council import CouncilEngine

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/游说 <长老名>"}
                res = CouncilEngine.lobby(char, "".join(parts[1:]))
                if res.get("success") or res.get("dirty"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}

            # ---------------- Wave2：除凶 ----------------
            if action in ("/除凶", "/hunt"):
                from core.hunt import format_board, list_board_rows, my_target

                t = my_target(char)
                extra = f"\n你接的令：【{t.name}】@ {t.location}" if t else "\n你未接令。"
                return {"ok": True, "text": format_board() + extra, "hunt": list_board_rows()}
            # /接令 消歧：纯数字编号是悬赏板既有接令（下方 handler），非数字道号才是除凶接令
            _is_bounty_claim = action == "/接令" and len(parts) >= 2 and parts[1].isdigit()
            if action in ("/接除凶", "/接令") and not _is_bounty_claim:
                from core.hunt import accept

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/接令 <凶犯道号>（纯数字编号为悬赏板接令）"}
                res = accept(char, "".join(parts[1:]))
                if res.get("success"):
                    try:
                        from core.sect_contrib import sync_ring

                        sync_ring(char, "hunt")
                    except Exception:
                        pass
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/弃除凶", "/弃令"):
                from core.hunt import abandon

                res = abandon(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/追凶", "/track"):
                from core.hunt import track

                res = track(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/反悬赏",):
                from core.hunt import place_counter

                res = place_counter(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/围剿",):
                from core.hunt import announce_siege

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/围剿 <道号>"}
                res = announce_siege(char, "".join(parts[1:]))
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/talk", "/交谈"):
                try:
                    from core import npc_chat

                    if len(parts) < 2:
                        panel = npc_chat.format_chat_panel(char.id)
                        return {"ok": True, "text": panel}
                    target_name = parts[1]
                    words = " ".join(parts[2:]) if len(parts) > 2 else ""
                    target = CharacterRepository.get_by_name(target_name)
                    if not target:
                        try:
                            from core.here import list_here as _lh

                            rows = _lh(char)
                        except Exception:
                            rows = []
                        nearby = [x.get("name") for x in rows if target_name in (x.get("name") or "")]
                        if len(nearby) == 1:
                            target = CharacterRepository.get_by_name(nearby[0])
                        elif nearby:
                            return {"ok": False, "error": f"道号不精确，同场有：{'、'.join(nearby[:6])}。请用完整道号。"}
                        else:
                            here_names = [x.get("name") for x in rows][:8]
                            hint = ("同场有：" + "、".join(here_names)) if here_names else "此地暂无其他修士，先 /前往 或 /同场"
                            return {"ok": False, "error": f"查无此人：{target_name}。{hint}"}
                    if target.id == char.id:
                        return {"ok": False, "error": "自言自语？"}
                    opened = npc_chat.open_session(char, target)
                    if not opened.get("success"):
                        return {"ok": False, "error": opened.get("message", "无法交谈")}
                    # 图鉴事件点亮（gallery-gameplay §8.3）：交谈开启成功点亮
                    # 该 NPC 原型图；钩子失败不影响交谈。
                    try:
                        from core.npc_mind import _is_npc as _is_npc_fn

                        if _is_npc_fn(target):
                            from core import gallery as _gallery

                            _gallery.note_npc_encounter(char, target)
                    except Exception:
                        pass
                    from core.npc_mind import _is_npc
                    is_target_npc = _is_npc(target)

                    # 头像下发（gallery-gameplay §10.3-5）：与同场 list_here
                    # 共用一处解析，交谈开启各返回点统一带 avatar（完整路径）。
                    from core.here import avatar_path_for_character as _avatar_fn

                    _target_avatar = _avatar_fn(target)

                    # 旧账行数据（二期 §8.3，只增 old_account）：与该 NPC
                    # 相关的未了诺言数 / 发酵中因果（总数 + 与他相关数 +
                    # 最近到期）/ 最近一条该 NPC 的 RELATION summary；
                    # 数据全为既有账只读拼装，失败即 None（前端不渲染）。
                    _old_account = None
                    try:
                        from core.promises import PromiseEngine as _PEo
                        from core.karma_chains import KarmaChainEngine as _KCEo

                        _open_n = 0
                        for _p in _PEo._involving(char.id):
                            _pst = (
                                _p.status.value if hasattr(_p.status, "value")
                                else str(_p.status))
                            if _pst in ("PENDING", "ACTIVE") and target.id in (
                                _p.promiser_id, _p.promisee_id
                            ):
                                _open_n += 1
                        _summ_o = _KCEo.status_summary(char)
                        _with_npc = 0
                        try:
                            from storage.db import KarmaChainRepository as _KCRo

                            _with_npc = sum(
                                1 for _c in _KCRo.list_by_player(char.id)
                                if _c.counterparty_id == target.id
                                and _c.status == "fermenting")
                        except Exception:
                            _with_npc = 0
                        _last_rel = ""
                        try:
                            from core.relations import (
                                relations_recent_and_marks as _rrmo,
                            )

                            _recent_o, _marks_o = _rrmo(
                                char.id, recent_limit=30, pool=30)
                            for _it_o in _recent_o:
                                if _it_o.get("npc_id") == target.id:
                                    _last_rel = _it_o.get("summary") or ""
                                    break
                        except Exception:
                            _last_rel = ""
                        _old_account = {
                            "open_promises": _open_n,
                            "fermenting_chains": int(_summ_o.get("fermenting") or 0),
                            "chains_with_npc": _with_npc,
                            "nearest_chain_game_days": _summ_o.get(
                                "nearest_mature_game_days"),
                            "last_relation": _last_rel,
                        }
                    except Exception:
                        _old_account = None

                    greet = (
                        f"【会话开始】与【{target.name}】交谈中。\n"
                        f"用 /说 <内容> 继续，/挂断 结束；聊天窗可直接打字。"
                    )
                    if words:
                        if not is_target_npc:
                            from core.npc_chat import deliver_player_message
                            deliver_player_message(char, target, words)
                            log_event("DECISION", "talk_player", name=char.name, target=target.name, words_len=len(words))
                            return {
                                "ok": True,
                                "text": greet + f"\n\n【神识传音】你向同道【{target.name}】传音：“{words}” 灵念已达，静候回音。",
                                "chat_lines": _cl_text_lines(greet) + [
                                    _cl_sys(f"【神识传音】你向同道【{target.name}】传音：“{words}” 灵念已达，静候回音。")
                                ],
                                "chat_open": True,
                                "npc": target.name,
                                "avatar": _target_avatar,
                                "is_player": True,
                                "source": "player_direct",
                                "old_account": _old_account,
                            }
                        res = NpcDialogueEngine.talk(target, char, words)
                        log_event("DECISION", "talk", name=char.name, target=target.name, words_len=len(words), source=res.get("source"))
                        if not res.get("ok"):
                            # 会话已开启但引擎失败（S-1）：带 sys 行，弹窗可见时呈现原因，不冒充开启成功
                            return {"ok": False, "error": res.get("error", "无法交谈"),
                                    "chat_lines": [_cl_sys(res.get("error", "无法交谈"))]}
                        try:
                            rec = npc_chat.get_session(char.id)
                            if rec:
                                rec.setdefault("messages", []).append({"who": char.name, "text": words, "ts": time.time()})
                                rec.setdefault("messages", []).append({"who": target.name, "text": res.get("text", ""), "ts": time.time()})
                                from storage.db import WorldStateRepository as W

                                d = W.get(npc_chat._KEY) or {}
                                d[char.id] = rec
                                W.set(npc_chat._KEY, d)
                        except Exception:
                            pass
                        return {
                            "ok": True,
                            "text": greet + "\n\n" + res.get("text", ""),
                            "chat_lines": _cl_text_lines(greet)
                            + [_cl_sys(res.get("header") or f"【{target.name}】")]
                            + [_cl_npc(target.name, res.get("line") or "")]
                            + _cl_bystanders(res.get("bystanders")),
                            "chat_open": True,
                            "npc": target.name,
                            "avatar": _target_avatar,
                            "attitude": res.get("attitude"),
                            "source": res.get("source"),
                            "bystanders": res.get("bystanders") or [],
                            "old_account": _old_account,
                        }
                    history_msgs = opened.get("session", {}).get("messages", [])
                    return {
                        "ok": True,
                        "text": greet + "\n\n（可开口：直接在聊天窗打字，无需 /说）",
                        "chat_lines": _cl_text_lines(greet)
                        + [_cl_sys("（可开口：直接在聊天窗打字，无需 /说）")],
                        "chat_open": True,
                        "npc": target.name,
                        "avatar": _target_avatar,
                        "is_player": not is_target_npc,
                        "messages": history_msgs[-10:],
                        "old_account": _old_account,
                    }
                except Exception as _talk_ex:
                    return {"ok": False, "error": f"交谈异常：{type(_talk_ex).__name__}: {_talk_ex}"}
            if action in ("/说", "/say"):
                from core import npc_chat
                from ai.play_prompts import npc_talk_prompt
                from ai.gateway import _chat_json, ai_available
                from core.npc_personas import persona_prompt_block, ensure_persona_bio
                from core.npc_mind import ensure_mind, attitude_toward, ATTITUDE_LABELS
                from core.memory import ensure_bio

                words = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                try:
                    from core.name_guard import reject_player_creation

                    rej = reject_player_creation(words)
                    if rej:
                        return {"ok": False, "error": rej["message"], "rejected": True, "chat_open": True,
                                "chat_lines": [_cl_sys(rej["message"])]}
                except Exception:
                    pass
                said = npc_chat.player_say(char, words)
                if not said.get("success"):
                    return {"ok": False, "error": said.get("message", "无法发言"), "chat_ended": said.get("ended"),
                            "chat_lines": _cl_text_lines(said.get("message", "无法发言"))}
                rec = said["session"]
                npc = said["npc"]
                from core.npc_mind import _is_npc
                is_target_npc = _is_npc(npc)

                # 头像下发（gallery-gameplay §10.3-5）：与同场 list_here
                # 共用一处解析，本分支各 chat_open 返回点统一带 avatar。
                from core.here import avatar_path_for_character as _avatar_fn

                _npc_avatar = _avatar_fn(npc)

                # 会话中若离地/死亡/被擒则终止
                if npc.location != char.location or npc.status == CharacterStatus.DEAD:
                    npc_chat.close_session(char.id, "对方已不在同场，会话终止。", by="system")
                    return {"ok": False, "error": "对方已不在同场，会话终止。", "chat_ended": True,
                            "chat_lines": [_cl_sys("对方已不在同场，会话终止。")]}
                if npc.status == CharacterStatus.CAPTURED:
                    npc_chat.close_session(char.id, f"【{npc.name}】已被擒。", by="system")
                    return {"ok": False, "error": f"【{npc.name}】已被擒，会话终止。", "chat_ended": True,
                            "chat_lines": [_cl_sys(f"【{npc.name}】已被擒，会话终止。")]}

                if not is_target_npc:
                    # 真人同道：绝不走 AI，直接返回成功与双方历史
                    return {
                        "ok": True,
                        "text": f"【神识传音】你向同道【{npc.name}】传音：“{words}” 灵念已达，静候回音。",
                        "chat_lines": [
                            _cl_sys(f"【神识传音】你向同道【{npc.name}】传音：“{words}” 灵念已达，静候回音。")
                        ],
                        "chat_open": True,
                        "chat_ended": False,
                        "npc": npc.name,
                        "avatar": _npc_avatar,
                        "is_player": True,
                        "source": "player_direct",
                    }

                # 会话内动作：自由文本 → 意图 → 规则落账
                from core import chat_actions as CA

                act = CA.execute_chat_action(char, npc, words, use_ai_classify=True, session=rec)
                if act.get("need_dialogue"):
                    pass  # 走下方既有对话链路
                else:
                    if act.get("ok"):
                        CharacterRepository.save(char)
                        if act.get("action") in ("attack", "steal", "kidnap", "gift", "trade"):
                            try:
                                CharacterRepository.save(npc)
                            except Exception:
                                pass
                        if act.get("ended"):
                            npc_chat.apply_npc_reply(
                                char.id,
                                act.get("text", "")[:200],
                                will_continue=False,
                                attitude_delta=0,
                                hangup_reason=act.get("hangup_reason") or "会话终止。",
                            )
                            return {
                                "ok": True,
                                "text": act.get("text", ""),
                                "chat_lines": [
                                    _cl_npc(npc.name, ln)
                                    for ln in str(act.get("text", "")).split("\n")
                                    if ln.strip()
                                ],
                                "chat_open": False,
                                "chat_ended": True,
                                "npc": npc.name,
                                "avatar": _npc_avatar,
                                "action": act.get("action") or "action",
                            }
                        # 未结束：玩家发言已由 player_say 记入，这里只追加动作结果
                        _record = npc_chat.get_session(char.id)
                        if _record:
                            try:
                                from storage.db import WorldStateRepository as W

                                d = W.get(npc_chat._KEY) or {}
                                rec2 = d.get(char.id) or _record
                                rec2.setdefault("messages", []).append({"who": npc.name, "text": act.get("text", ""), "ts": time.time()})
                                w = int(rec2.get("willingness") or 50)
                                w = max(0, min(100, w + int(act.get("attitude_delta") or 0)))
                                rec2["willingness"] = w
                                rec2["updated_at"] = time.time()
                                d[char.id] = rec2
                                W.set(npc_chat._KEY, d)
                            except Exception:
                                pass
                        return {
                            "ok": True,
                            "text": act.get("text", ""),
                            "chat_lines": [
                                _cl_npc(npc.name, ln)
                                for ln in str(act.get("text", "")).split("\n")
                                if ln.strip()
                            ],
                            "chat_open": True,
                            "chat_ended": False,
                            "npc": npc.name,
                            "avatar": _npc_avatar,
                            "action": act.get("action") or "action",
                        }
                    # 动作被规则拒绝：会话仍开，展示原因
                    return {
                        "ok": False,
                        "error": act.get("error", "无法完成该动作"),
                        "chat_lines": [_cl_sys(act.get("error", "无法完成该动作"))],
                        "chat_open": True,
                        "chat_ended": False,
                        "npc": npc.name,
                        "avatar": _npc_avatar,
                        "action": act.get("action") or "action",
                    }

                mind = ensure_mind(npc)
                att = attitude_toward(npc, char.id)
                att_cn = ATTITUDE_LABELS.get(att.get("label", "neutral"), "中立")
                ensure_bio(npc)
                ensure_persona_bio(npc)
                try:
                    from storage.db import CharacterBioRepository as CBR

                    bio = CBR.get(npc.id) or ""
                except Exception:
                    bio = ""
                try:
                    from core.npc_personas import character_card_block, player_persona_block
                    from core.lorebook import lore_prompt_block
                    from core.npc_chat import chat_memory_lines

                    persona = character_card_block(npc) or persona_prompt_block(npc)
                    lore_blk = lore_prompt_block(char, npc, player_words=said["player_text"])
                    mem_blk = chat_memory_lines(char.id, npc.id, limit=2)
                    pcard = player_persona_block(char)
                except Exception:
                    persona = persona_prompt_block(npc)
                    lore_blk = mem_blk = pcard = ""
                hist = npc_chat.history_lines(rec, 10)
                will_hint = int(rec.get("willingness") or 50)

                line = ""
                will_cont = True
                d_att = 0
                hang = ""
                source = "local"
                if ai_available():
                    try:
                        prompt = (
                            "你是修仙世界 NPC，正在进行连续交谈。只输出 JSON。\n"
                            + persona
                            + "\n"
                            + ((pcard + "\n") if pcard else "")
                            + f"你是 {npc.name}（{npc.realm.name}，{npc.sect or '散修'}·{npc.sect_rank}）\n"
                            + f"性格：{mind.get('personality')}\n小传：{bio}\n"
                            + f"对【{char.name}】态度：{att_cn}（值 {att.get('value',0)}）；续聊意愿 {will_hint}/100\n"
                            + f"所在：{npc.location}\n"
                            + ((lore_blk + "\n") if lore_blk else "")
                            + ((mem_blk + "\n") if mem_blk else "")
                            + f"近日对话：\n{hist}\n"
                            + f"对方刚说：{said['player_text']}\n"
                            + "若你不愿继续，will_continue=false，并可在 hangup_reason 写一句作别（也可空则用默认）。\n"
                            + "attitude_delta -5~5。\n"
                            + "输出：{\"line\":\"台词<=80字\",\"will_continue\":true/false,"
                            + "\"attitude_delta\":0,\"hangup_reason\":\"\"}"
                        )
                        data = _chat_json(prompt)
                        if data:
                            line = str(data.get("line") or "")[:200]
                            will_cont = bool(data.get("will_continue", True))
                            try:
                                d_att = max(-5, min(5, int(data.get("attitude_delta") or 0)))
                            except Exception:
                                d_att = 0
                            hang = str(data.get("hangup_reason") or "")
                            source = "ai"
                    except Exception:
                        line = ""
                if not line:
                    loc = npc_chat.local_hangup_or_reply(npc, char, rec)
                    line = loc["line"]
                    will_cont = loc["will_continue"]
                    d_att = int(loc.get("attitude_delta") or 0)
                    hang = loc.get("hangup_reason") or ""
                    source = "local"

                # 呈现清洗（chat-structure §C）：line 入会话记录与响应前统一清洗，
                # 仅剥 markdown 残留/规范换行，不改台词内容与结算。
                from core.dialogue_text import clean_dialogue_text as _cleanDlg

                line = _cleanDlg(line)
                out = npc_chat.apply_npc_reply(char.id, line, will_cont, d_att, hang)
                if d_att:
                    try:
                        from core.npc_mind import shift_attitude

                        shift_attitude(npc, char.id, d_att, reason="会话")
                        CharacterRepository.save(npc)
                    except Exception:
                        pass
                banter_text = ""
                banter_list: list = []
                try:
                    from core.scene_banter import maybe_banter, format_banter, append_banter_to_session

                    banter_list = maybe_banter(
                        char, npc, transcript_tail=f"{said['player_text']}\n{line}"
                    )
                    if banter_list:
                        banter_text = "\n" + _cleanDlg(format_banter(banter_list))
                        if not out.get("ended"):
                            append_banter_to_session(char.id, banter_list)
                except Exception:
                    banter_text = ""
                _say_lines = [_cl_npc(npc.name, out.get("line", line))] + _cl_bystanders(banter_list)
                if out.get("ended"):
                    if out.get("end_reason"):
                        _say_lines.append(_cl_sys(out["end_reason"]))
                    _say_lines.append(_cl_sys("（继续发送将不会得到回应；可重新 /交谈）"))
                payload = {
                    "ok": True,
                    "text": (out.get("message", line) or "") + banter_text,
                    "chat_lines": _say_lines,
                    "chat_open": not out.get("ended"),
                    "chat_ended": bool(out.get("ended")),
                    "npc": npc.name,
                    "avatar": _npc_avatar,
                    "source": source,
                    "bystanders": banter_list,
                }
                if not out.get("ended"):
                    return self._append_natural_omen(char, payload, context="与NPC交谈", in_chat_npc=npc)
                return payload
            if action in ("/挂断", "/hangup"):
                from core import npc_chat

                rec = npc_chat.close_session(char.id, "你拱手作别，结束了交谈。", by="player")
                if not rec:
                    return {"ok": False, "error": "当前无进行中的会话。"}
                mem = ""
                try:
                    mem = npc_chat.chat_memory_lines(char.id, rec.get("npc_id") or "")
                except Exception:
                    mem = ""
                text = f"【挂断】与【{rec.get('npc_name')}】的会话已结束。"
                if mem:
                    text += "\n" + mem
                return {"ok": True, "text": text, "chat_ended": True, "npc": rec.get("npc_name"),
                        "chat_lines": _cl_text_lines(text)}
            if action in ("/释放", "/release"):
                from core.chat_actions import release_captive

                name = "".join(parts[1:]) if len(parts) > 1 else ""
                res = release_captive(char, name)
                if not res.get("ok"):
                    return {"ok": False, "error": res.get("error", "无法释放")}
                return {"ok": True, "text": res.get("message", "已释放。")}
            if action in ("/chatpanel", "/会话"):
                from core import npc_chat

                return {"ok": True, "text": npc_chat.format_chat_panel(char.id)}
            if action in ("/agenda", "/议程"):
                rows = NpcAgendaEngine.list_agendas()
                if not rows:
                    return {"ok": True, "text": "暂无 NPC 议程档案。"}
                lines = ["【NPC 议程】主约60% · 副随tick · 进度5换新"]
                for a in rows[:20]:
                    sec = f" 副:{a.get('secondary_cn')}" if a.get("secondary_cn") else ""
                    lines.append(
                        f"· {a['npc_name']}：{a.get('agenda_cn', a['agenda_type'])} — "
                        f"{a.get('note','')[:24]}（{a.get('progress',0)}/5{sec}）"
                    )
                return {"ok": True, "text": "\n".join(lines), "agendas": [
                    {
                        "name": a["npc_name"],
                        "type": a.get("agenda_cn") or a.get("agenda_type"),
                        "note": a.get("note", ""),
                        "progress": a.get("progress", 0),
                        "secondary": a.get("secondary_cn", ""),
                    }
                    for a in rows[:20]
                ]}
            if action in ("/bounty", "/告示"):
                return {"ok": True, "text": self._bounty_board(), "bounties": self._bounty_rows()}
            if action in ("/market", "/坊市"):
                return {"ok": True, "text": self._market(char), "status": self._status_dict(char)}
            if action in ("/行情",):
                return {
                    "ok": True,
                    "text": MarketEngine.trade_board(char.location),
                    "prices": MarketEngine.trade_board_data(char.location),
                }
            if action in ("/atlas", "/版图"):
                arg = parts[1] if len(parts) > 1 else None
                ret = {"ok": True, "text": AtlasEngine.panel_text(char, arg)}
                if not arg:
                    ret["atlas"] = AtlasEngine.atlas_data(char)
                return ret
            if action in ("/buy", "/购买"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/购买 <货名> [数量]，先 /坊市 看货单"}
                qty = 1
                name_parts = parts[1:]
                if name_parts and name_parts[-1].isdigit():
                    qty = max(1, int(name_parts[-1]))
                    name_parts = name_parts[:-1]
                item = "".join(name_parts) if len(name_parts) > 1 else (name_parts[0] if name_parts else "")
                # 支持货名带空格：把剩余 token 重新拼回（去掉数量）
                raw_item = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                if raw_item:
                    # 去掉末尾数量
                    toks = raw_item.split()
                    if toks and toks[-1].isdigit():
                        toks = toks[:-1]
                    item = "".join(toks) if len(toks) > 1 else (toks[0] if toks else item)
                from config import ITEM_CATALOG
                if item not in ITEM_CATALOG:
                    # 模糊匹配
                    for k in ITEM_CATALOG:
                        if item and (item in k or k in item):
                            item = k
                            break
                res = MarketEngine.buy_from_guild(char, item, qty)
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("DECISION", "buy", name=char.name, item=item, qty=qty)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/sell", "/出售"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/出售 <货名> [数量]"}
                qty = 1
                toks = command.strip().split(None, 1)[1].split() if len(command.strip().split(None, 1)) > 1 else []
                if toks and toks[-1].isdigit():
                    qty = max(1, int(toks[-1]))
                    toks = toks[:-1]
                item = "".join(toks) if len(toks) > 1 else (toks[0] if toks else "")
                res = MarketEngine.sell_to_guild(char, item, qty)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""),
                        "status": self._status_dict(char)}
            if action in ("/use", "/服用"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/服用 <丹药名>"}
                item = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                res = MarketEngine.use_pill(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                    try:
                        from core.tasks import hook_note

                        n = hook_note(char, "use_pill")
                        if n:
                            res["message"] = n + "\n" + (res.get("message") or "")
                    except Exception:
                        pass
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/deposit", "/寄存"):
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/寄存 <数量>"}
                res = MarketEngine.deposit_stones(char, int(parts[1]))
                CharacterRepository.save(char)
                return {"ok": res["success"], "text": res["message"], "status": self._status_dict(char)}
            if action in ("/withdraw", "/支取"):
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/支取 <灵石数量>"}
                res = MarketEngine.withdraw_stones(char, int(parts[1]))
                if res["success"]:
                    CharacterRepository.save(char)
                return {"ok": res["success"], "text": res["message"], "status": self._status_dict(char)}
            if action in ("/灵泉", "/spring", "/汲取"):
                exp_add = 200
                char.realm.current_exp = min(char.realm.max_exp, char.realm.current_exp + exp_add)
                try:
                    dew = ItemEntity.create(
                        name="玄冰玉露",
                        kind=ItemKind.PILL,
                        quality=3,
                        description="洞府玄冰九曲灵泉孕育的灵露，饮之清心涤滤，修为倍增。"
                    )
                    char.add_item_entity(dew)
                except Exception:
                    char.inventory.append("玄冰玉露")
                CharacterRepository.save(char)
                return {
                    "ok": True,
                    "text": f"【洞府灵泉 · 汲取】你引地阴玄水入体，炼化玄冰灵露，周天真元+{exp_add}！得获【玄冰玉露】一份入纳戒。",
                    "status": self._status_dict(char)
                }
            if action in ("/草园", "/herbs", "/采药", "/灵草"):
                is_rush = len(parts) > 1 and ("催熟" in parts[1] or "加速" in parts[1])
                cost = 50 if is_rush else 0
                if is_rush and char.spirit_stones < cost:
                    return {"ok": False, "error": f"催熟灵草需注入地脉 50 灵石，当前随身灵石不足（仅余 {char.spirit_stones}）。"}
                if is_rush:
                    char.spirit_stones -= cost
                herb_name = "千年紫菁芝草" if is_rush else "紫菁芝草"
                try:
                    herb = ItemEntity.create(
                        name=herb_name,
                        kind=ItemKind.MATERIAL,
                        quality=4 if is_rush else 2,
                        description="紫菁九叶草园培育出的珍稀芝草，炼制九转还魂丹之主材。"
                    )
                    char.add_item_entity(herb)
                except Exception:
                    char.inventory.append(herb_name)
                CharacterRepository.save(char)
                msg = f"【紫菁草园 · 催熟采收】消耗 {cost} 灵石灌注地脉灵泉，芝草瞬息成熟！采得【{herb_name}】入纳戒。" if is_rush else f"【紫菁草园 · 采摘】你小心翼翼采摘成熟芝草，得获【{herb_name}】入纳戒。"
                return {
                    "ok": True,
                    "text": msg,
                    "status": self._status_dict(char)
                }
            if action in ("/灵鹤", "/crane", "/探路"):
                # 1. 领取云巢暂存机缘
                if len(parts) > 1 and parts[1] in ("领取", "收纳", "取回", "claim"):
                    if not char.crane_pending_item:
                        return {
                            "ok": False,
                            "error": "青羽仙鹤云巢灵囊中并无可领取的机缘仙物。",
                            "status": self._status_dict(char),
                        }
                    if char.is_bag_full():
                        return {
                            "ok": False,
                            "error": f"百宝纳戒乾坤已满（{len(char.items)}/{char.MAX_BAG_SLOTS}），请先前往纳戒移出、佩戴或出售旧物，腾出空位后再来领取！",
                            "status": self._status_dict(char),
                        }
                    p_data = dict(char.crane_pending_item)
                    try:
                        p_item = ItemEntity.model_validate(p_data)
                    except Exception:
                        p_item = ItemEntity.create(
                            name=p_data.get("name", "仙鹤机缘"),
                            kind=p_data.get("kind", "material"),
                            quality=p_data.get("tier", 3),
                            description=p_data.get("lore", "青羽仙鹤暂留于云巢的仙物。")
                        )
                    char.add_item_entity(p_item)
                    claimed_name = p_item.name
                    char.crane_pending_item = None
                    CharacterRepository.save(char)
                    return {
                        "ok": True,
                        "text": f"【仙鹤云巢 · 取回机缘】你自青羽仙鹤灵囊中取下【{claimed_name}】，已妥善收入百宝纳戒！仙鹤振翅轻啼，重回栖息待命态。",
                        "status": self._status_dict(char),
                    }

                # 2. 检查仙鹤身上是否有未领仙物（不可携宝再飞）
                if char.crane_pending_item:
                    p_name = char.crane_pending_item.get("name", "机缘仙物")
                    return {
                        "ok": False,
                        "error": f"青羽仙鹤云巢中尚有衔回的【{p_name}】未取！请先输入 /灵鹤 领取 或在洞府灵兽台领取后再敕令启程！",
                        "status": self._status_dict(char),
                    }

                dest = parts[1] if len(parts) > 1 else "落霞密林"
                cost_map = {"落霞密林": 10, "黑风绝渊赤焰": 30, "南海碧波古墟": 50, "落霞山": 10}
                cost = cost_map.get(dest, 10)
                if (char.spirit_stones or 0) < cost:
                    return {
                        "ok": False,
                        "error": f"随身灵石不足 {cost}，无法派遣仙鹤！",
                        "status": self._status_dict(char),
                    }
                char.spirit_stones = max(0, (char.spirit_stones or 0) - cost)

                try:
                    from core.treasure_system import TreasureEngine
                    roll = random.random()
                    if roll < 0.45:
                        loot_item = TreasureEngine.generate_treasure_map(char, tier=2, preferred_target=dest)
                    elif roll < 0.75:
                        loot_item = ItemEntity.create(
                            name="千年离火晶石",
                            kind=ItemKind.MATERIAL,
                            quality=3,
                            description="青羽仙鹤深入地脉火海，以纯阳神念衔出的地火精华，温热纯澈！",
                        )
                    else:
                        loot_item = ItemEntity.create(
                            name="青鸾灵羽",
                            kind=ItemKind.MATERIAL,
                            quality=3,
                            description="青羽仙鹤巡弋途中偶遇异鸟拾得的神禽遗羽，蕴含风雷道韵。",
                        )
                except Exception as err:
                    loot_item = ItemEntity.create(
                        name="仙鹤衔回的机缘玉符",
                        kind=ItemKind.MATERIAL,
                        quality=2,
                        description="青羽仙鹤探路衔回的机缘玉符。",
                    )

                # 3. 满格暂存分流判定
                if char.is_bag_full():
                    item_dict = loot_item.model_dump() if hasattr(loot_item, "model_dump") else (loot_item.__dict__ if hasattr(loot_item, "__dict__") else {"name": loot_item.name})
                    # 补齐关键展示字段
                    item_dict["name"] = loot_item.name
                    item_dict["tier"] = getattr(loot_item, "tier", 3)
                    item_dict["tierName"] = ["凡品", "人品", "地品", "天品", "仙品"][min(4, max(0, getattr(loot_item, "tier", 3) - 1))]
                    item_dict["slotCn"] = "天机秘宝图卷" if "图" in loot_item.name else "灵宝异物"
                    item_dict["lore"] = getattr(loot_item, "lineage_lore", "") or getattr(loot_item, "description", "")
                    char.crane_pending_item = item_dict
                    CharacterRepository.save(char)
                    return {
                        "ok": True,
                        "text": f"【镇山仙鹤 · 探路归巢】消耗 {cost} 灵石。仙鹤巡弋【{dest}】衔回【{loot_item.name}】，因百宝纳戒乾坤已满（{len(char.items)}/{char.MAX_BAG_SLOTS}），仙物已稳妥暂留于云巢灵囊中！腾出空间后输入 /灵鹤 领取。",
                        "status": self._status_dict(char),
                        "overflow": True,
                    }

                char.add_item_entity(loot_item)
                CharacterRepository.save(char)
                return {
                    "ok": True,
                    "text": f"【镇山仙鹤 · 探路巡弋】消耗 {cost} 灵石。青羽仙鹤翱翔于【{dest}】上空，破开云雾，神识传音报捷，带回【{loot_item.name}】已存入纳戒！",
                    "status": self._status_dict(char),
                    "overflow": False,
                }
            if action in ("/scan", "/探查"):
                results = CombatEngine.scan_surroundings(
                    char, CharacterRepository.list_all_alive()
                )
                lines = ["【神识外放】扫视四方……"]
                if not results:
                    lines.append("方圆周遭暂无可辨灵压。")
                for r in results:
                    lines.append(r.get("description") or f"· {r.get('clarity')}")
                return {"ok": True, "text": "\n".join(lines), "scan": results}
            if action in ("/place_bounty", "/挂赏"):
                if len(parts) < 3:
                    return {
                        "ok": False,
                        "error": "用法：/挂赏 <道号> <赏金> [缘由]（句末加「匿」匿名）",
                    }
                target_name = parts[1]
                try:
                    reward = int(parts[2])
                except ValueError:
                    return {"ok": False, "error": "赏金必须是整数灵石"}
                anonymous = False
                reason_tokens = parts[3:]
                if reason_tokens and reason_tokens[-1] in ("匿", "匿名", "anon"):
                    anonymous = True
                    reason_tokens = reason_tokens[:-1]
                reason = " ".join(reason_tokens) if reason_tokens else "血海深仇"
                target = CharacterRepository.get_by_name(target_name)
                if not target:
                    return {"ok": False, "error": f"查无此人：{target_name}"}
                active = BountyEngine.count_active_for_target(
                    BountyRepository.list_all(), target.id
                )
                if active >= BOUNTY_MAX_PER_TARGET:
                    return {
                        "ok": False,
                        "error": f"【{target_name}】头上已有 {active} 张血令（上限 {BOUNTY_MAX_PER_TARGET}）",
                    }
                res = BountyEngine.place_bounty(char, target, reward, reason, anonymous)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "挂赏失败")}
                CharacterRepository.save(char)
                BountyRepository.save(res["bounty"])
                if res.get("link"):
                    KarmaLinkRepository.save(res["link"])
                ChronicleRepository.record(
                    "BOUNTY",
                    char.name,
                    f"【{res['bounty'].issuer_display()}】悬赏 {reward} 灵石取【{target.name}】性命！缘由：{reason}",
                )
                return {"ok": True, "text": res["message"]}
            if action in ("/claim_bounty", "/接令"):
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/接令 <告示编号>（先 /告示）"}
                idx = int(parts[1]) - 1
                board = BountyEngine.list_board(BountyRepository.list_all())
                if idx < 0 or idx >= len(board):
                    return {"ok": False, "error": "告示编号不存在"}
                bounty = board[idx]
                res = BountyEngine.claim_bounty(char, bounty)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "接令失败")}
                BountyRepository.save(bounty)
                ChronicleRepository.record(
                    "BOUNTY_CLAIM",
                    char.name,
                    f"猎手【{char.name}】接令追杀【{bounty.target_name}】，赏金 {bounty.reward} 灵石！",
                )
                return {"ok": True, "text": res["message"]}
            if action in ("/list_item", "/寄售", "/摆摊"):
                # 合并分流：空参仅 /摆摊 开地摊面板（分支）；/寄售、/list_item
                # 空参维持 main 的用法错误（双端 parity 钉死口径）
                if len(parts) == 1 and action == "/摆摊":
                    my_open = [l for l in MarketListingRepository.list_all() if l.seller_id == char.id and l.is_open()]
                    earnings = getattr(char, "stall_earnings", 0)
                    lines = [f"【我的坊市地摊 · 聚宝法座】当前挂牌 {len(my_open)}/8 件，待提取收益：{earnings} 灵石。"]
                    for idx, l in enumerate(my_open, 1):
                        lines.append(f"  {idx}. 【{l.item_name}】标价 {l.price} 灵石 (序号: {l.id})")
                    lines.append("指令：/摆摊 <物品名> <价格> 挂牌，/撤回 <编号/物品名> 撤回，/收益 提取灵石，/招徕 招揽修士。")
                    return {"ok": True, "text": "\n".join(lines), "status": self._status_dict(char)}

                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/摆摊 <货物名> <价格>"}
                try:
                    price = int(parts[-1])
                except ValueError:
                    return {"ok": False, "error": "价格必须是整数灵石"}
                item_name = "".join(parts[1:-1]) if len(parts) > 3 else parts[1]
                raw = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                if raw:
                    toks = raw.split()
                    if toks and toks[-1].isdigit():
                        toks = toks[:-1]
                    item_name = "".join(toks) if len(toks) > 1 else (toks[0] if toks else item_name)
                my_open = [
                    l for l in MarketListingRepository.list_all()
                    if l.seller_id == char.id and l.is_open()
                ]
                if len(my_open) >= 8:
                    return {"ok": False, "error": "地摊法座已满（上限 8 件），请先 /撤回 腾挪摊位！"}
                listing, res = MarketEngine.list_item(char, item_name, price)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "摆摊挂牌失败")}
                MarketListingRepository.save(listing)
                # 著书立说（F11）：手稿上架 → 书目转 listed 并绑定单号
                if item_name == BOOK_ITEM:
                    BookEngine.on_listing_created(char, listing.id)
                CharacterRepository.save(char)
                ChronicleRepository.record(
                    "MARKET", char.name, f"【{char.name}】在九霄坊市摆摊挂牌【{item_name}】标价 {price} 灵石。"
                )
                return {"ok": True, "text": res["message"], "status": self._status_dict(char)}

            if action in ("/buy_listing", "/买寄售"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/买寄售 <编号或ID>"}
                open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
                target_id = parts[1]
                listing = None
                if target_id.isdigit():
                    idx = int(target_id) - 1
                    if 0 <= idx < len(open_l):
                        listing = open_l[idx]
                if not listing:
                    for l in open_l:
                        if l.id == target_id or l.item_name == target_id:
                            listing = l
                            break
                if not listing:
                    return {"ok": False, "error": f"寄售货物【{target_id}】不存在或已下架。"}
                # 著书立说（F11）：手稿一人至多持一本，买家已持有则不成交
                if listing.item_name == BOOK_ITEM and not BookEngine.buyer_can_hold(char):
                    return {"ok": False, "error": "怀中已有一部手稿，先将它流通出去再买新的。"}
                res = MarketEngine.buy_listing(char, listing)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "购买失败")}
                # 著书立说（F11）：手稿成交 → 书目过户买家
                if listing.item_name == BOOK_ITEM:
                    BookEngine.on_listing_sold(listing.id, char)
                seller = CharacterRepository.get_by_name(listing.seller_name)
                MarketEngine.complete_sale_payment(listing, seller, to_stall_earnings=True)
                MarketListingRepository.save(listing)
                CharacterRepository.save(char)
                if seller:
                    CharacterRepository.save(seller)
                ChronicleRepository.record(
                    "MARKET_BUY",
                    char.name,
                    f"【{char.name}】购得寄售【{listing.item_name}】，付 {listing.price} 灵石。",
                )
                return {"ok": True, "text": res["message"], "status": self._status_dict(char)}

            if action in ("/cancel_listing", "/撤单", "/撤回"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/撤回 <编号或物品名>"}
                open_l = [l for l in MarketListingRepository.list_all() if l.seller_id == char.id and l.is_open()]
                target = parts[1]
                listing = None
                if target.isdigit():
                    idx = int(target) - 1
                    if 0 <= idx < len(open_l):
                        listing = open_l[idx]
                if not listing:
                    for l in open_l:
                        if l.id == target or l.item_name == target or target in l.item_name:
                            listing = l
                            break
                if not listing:
                    return {"ok": False, "error": f"未找到可撤回的挂牌货物【{target}】。"}
                res = MarketEngine.cancel_listing(char, listing)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "撤回失败")}
                MarketListingRepository.save(listing)
                # 著书立说（F11）：手稿撤单 → 书目回 held
                if listing.item_name == BOOK_ITEM:
                    BookEngine.on_listing_cancelled(listing.id)
                CharacterRepository.save(char)
                return {"ok": True, "text": res["message"], "status": self._status_dict(char)}

            if action in ("/pawn", "/典当"):
                from core.pawn import PawnEngine
                from storage.db import PawnTicketRepository

                if len(parts) < 2:
                    return {"ok": True, "text": PawnEngine.panel_text(char)}
                item_name = "".join(parts[1:])
                ticket, res = PawnEngine.pawn_item(char, item_name)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "典当失败")}
                PawnTicketRepository.save(ticket)
                CharacterRepository.save(char)
                ChronicleRepository.record(
                    "PAWN", char.name,
                    f"【{char.name}】典当【{item_name}】得 {res['principal']} 灵石。",
                )
                return {"ok": True, "text": res["message"]}
            if action in ("/redeem", "/赎回"):
                from core.pawn import PawnEngine
                from storage.db import PawnTicketRepository

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/赎回 <物品名>（先 /典当 查看当票）"}
                item_name = "".join(parts[1:])
                ticket, res = PawnEngine.redeem_item(char, item_name)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "赎回失败")}
                PawnTicketRepository.save(ticket)
                CharacterRepository.save(char)
                return {"ok": True, "text": res["message"], "status": self._status_dict(char)}

            if action in ("/收益", "/提取收益"):
                earnings = getattr(char, "stall_earnings", 0)
                if earnings <= 0:
                    return {"ok": False, "error": "地摊聚宝法座中暂无待提取的灵石收益。", "status": self._status_dict(char)}
                char.spirit_stones += earnings
                char.stall_earnings = 0
                CharacterRepository.save(char)
                return {
                    "ok": True,
                    "text": f"【地摊收益交割】成功提取 {earnings} 灵石划归纳戒！随身灵石增至 {char.spirit_stones}。",
                    "status": self._status_dict(char),
                }

            if action in ("/捡漏", "/盲匣", "/解石"):
                COST = 80
                if char.spirit_stones < COST:
                    return {"ok": False, "error": f"购买古修残宝盲匣需 {COST} 灵石，囊中仅余 {char.spirit_stones}。"}
                if char.is_bag_full():
                    return {"ok": False, "error": "百宝纳戒乾坤已满（64/64），请先腾挪纳戒空间再行解石捡漏！"}
                char.spirit_stones -= COST
                roll = random.random()
                if roll < 0.15:
                    loot = ItemEntity.create(
                        name="太古遗迹真仙古卷",
                        kind=ItemKind.RELIC,
                        tier=4,
                        description="自万载锈蚀盲匣中开出的太古真仙玉简，道韵天成，万金难求！",
                        slot="trinket",
                    )
                    quality_text = "【天阶重宝 · 金光冲霄】"
                elif roll < 0.45:
                    loot = ItemEntity.create(
                        name="古修断纹玄阴剑",
                        kind=ItemKind.EQUIP,
                        tier=3,
                        description="上古剑修遗留佩剑，剑身残留凌厉破煞剑气，重见天日！",
                        slot="weapon",
                    )
                    quality_text = "【地品灵宝 · 剑气森然】"
                elif roll < 0.75:
                    loot = ItemEntity.create(
                        name="千年雪魄定颜丹",
                        kind=ItemKind.CONSUMABLE,
                        tier=2,
                        description="封存在玄冰灵盒中的上古灵丹，药香四溢，沁人心脾。",
                    )
                    quality_text = "【人品灵丹 · 异香扑鼻】"
                else:
                    loot = ItemEntity.create(
                        name="斑驳温润古玉残片",
                        kind=ItemKind.MATERIAL,
                        tier=1,
                        description="被岁月风蚀的古修士佩玉残片，质地温润，可作熔炼原材。",
                    )
                    quality_text = "【凡阶残宝 · 质地温润】"

                char.add_item_entity(loot)
                CharacterRepository.save(char)
                # 得宝幕（game-feel-phase3 §3.3 H-L2）：入包与 save 之后
                # 只增 ceremony；实际只有 tier4 relic 一档可达门槛
                _loot_ceremony = None
                try:
                    from core.ceremony import (
                        build_loot_ceremony,
                        loot_ceremony_candidate,
                    )

                    _kind = loot.kind.value if hasattr(loot.kind, "value") else str(loot.kind)
                    if loot_ceremony_candidate(_kind, loot.tier):
                        _loot_ceremony = build_loot_ceremony(char, {
                            "uid": loot.uid,
                            "name": loot.name,
                            "kind": _kind,
                            "tier": loot.tier,
                            "tier_name": loot.tier_name,
                            "slot": loot.slot,
                            "affixes": [
                                {"name": a.name, "desc": a.desc}
                                for a in (loot.affixes or [])
                            ],
                            "lore": loot.lineage_lore,
                        }, source="blind_box")
                except Exception:
                    _loot_ceremony = None
                return {
                    "ok": True,
                    "text": f"【古修残宝 · 当场解石】消耗 {COST} 灵石切开锈蚀盲匣！{quality_text}，获【{loot.name}】（{loot.tier_name}）！已收入百宝纳戒首格。",
                    "status": self._status_dict(char),
                    "loot": loot.name,
                    "ceremony": _loot_ceremony,
                }

            if action in ("/招徕", "/招徕修士"):
                my_open = [l for l in MarketListingRepository.list_all() if l.seller_id == char.id and l.is_open()]
                if not my_open:
                    return {"ok": False, "error": "道友的地摊空空如也，请先挂牌仙物再行摇铃招徕！"}
                npc_list = ["青阳散人", "百花仙子", "玄溟剑尊", "万宝楼采办", "百草仙姑", "落魄散修", "金丹邪修"]
                npc = random.choice(npc_list)
                target_listing = random.choice(my_open)
                roll = random.random()
                if roll < 0.40:
                    target_listing.status = ListingStatus.SOLD
                    MarketEngine.complete_sale_payment(target_listing, char, to_stall_earnings=True)
                    MarketListingRepository.save(target_listing)
                    CharacterRepository.save(char)
                    text = (
                        f"【仙商买办 · 豪爽全款】过路修士【{npc}】神念扫过摊位，赞道：“妙哉！此【{target_listing.item_name}】正合老夫所需！”\n"
                        f"当场支付 {target_listing.price} 灵石全款买下！灵石已划入地摊聚宝法座待提取收益。"
                    )
                    return {"ok": True, "text": text, "status": self._status_dict(char), "trade": "sold"}
                elif roll < 0.80:
                    discount_rate = round(random.uniform(0.70, 0.90), 2)
                    offer_price = max(1, int(target_listing.price * discount_rate))
                    text = (
                        f"【散修议价 · 诚心讨价】散修【{npc}】在摊位前流连良久，摩挲着【{target_listing.item_name}】说道：\n"
                        f"“道友，此物标价 {target_listing.price} 灵石稍显昂贵，在下囊中羞涩，愿出 {offer_price} 灵石割爱，道友可愿成全？”\n"
                        f"输入 /还价 成交 {target_listing.id} {offer_price} 割爱，或 /还价 拒绝 {target_listing.id} 谢绝。"
                    )
                    return {
                        "ok": True,
                        "text": text,
                        "status": self._status_dict(char),
                        "haggle": True,
                        "npc": npc,
                        "listing_id": target_listing.id,
                        "item_name": target_listing.item_name,
                        "original_price": target_listing.price,
                        "offer_price": offer_price,
                    }
                else:
                    comments = [
                        f"“此【{target_listing.item_name}】道韵颇醇，可惜老夫灵石皆换了避雷符，惜哉惜哉。”",
                        f"“九霄坊市今日好生热闹，道友这摊位风水极佳，必有大能惠顾！”",
                        f"“听闻十方大荒深处有古魔出世，多备些灵丹才是正道啊……”",
                    ]
                    text = f"【修士过路 · 驻足品评】路过修士【{npc}】驻足观摩，摇头叹道：{random.choice(comments)}"
                    return {"ok": True, "text": text, "status": self._status_dict(char), "trade": "pass"}

            if action in ("/还价", "/议价"):
                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/还价 成交 <编号/ID> <价格> 或 /还价 拒绝 <编号/ID>"}
                decision = parts[1]
                listing_id = parts[2]
                open_l = [l for l in MarketListingRepository.list_all() if l.seller_id == char.id and l.is_open()]
                listing = None
                for l in open_l:
                    if l.id == listing_id or l.item_name == listing_id:
                        listing = l
                        break
                if not listing:
                    return {"ok": False, "error": f"未找到摊位在售货物【{listing_id}】。"}

                if decision in ("成交", "同意", "accept"):
                    price = listing.price
                    if len(parts) >= 4 and parts[3].isdigit():
                        price = int(parts[3])
                    listing.status = ListingStatus.SOLD
                    listing.price = price
                    MarketEngine.complete_sale_payment(listing, char, to_stall_earnings=True)
                    MarketListingRepository.save(listing)
                    CharacterRepository.save(char)
                    return {
                        "ok": True,
                        "text": f"【议价成交 · 结下善缘】道友应允折价割爱，以 {price} 灵石将【{listing.item_name}】售出！灵石已记入地摊待提取收益。",
                        "status": self._status_dict(char),
                    }
                else:
                    return {
                        "ok": True,
                        "text": f"【谢绝还价】道友婉拒了过路修士的折价请求，【{listing.item_name}】依旧以原价 {listing.price} 灵石挂牌在摊位上。",
                        "status": self._status_dict(char),
                    }

            # ---------------- 当面交易 ----------------
            if action in ("/trade", "/交易") and len(parts) >= 2:
                from core.trade import TradeEngine

                res = TradeEngine.open_trade(char, "".join(parts[1:]))
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "无法发起交易")}
                ret = {"ok": True, "text": res["message"]}
                if res.get("session") is not None:
                    ret["trade"] = TradeEngine.trade_session_dict(res["session"], char.id)
                return ret
            if action in ("/trade", "/交易"):
                from core.trade import TradeEngine

                res = TradeEngine.view(char)
                ret = {"ok": res.get("success"), "text": res.get("message", "")}
                if res.get("session") is not None:
                    ret["trade"] = TradeEngine.trade_session_dict(res["session"], char.id)
                return ret
            if action in ("/trade_offer", "/交易出"):
                from core.trade import TradeEngine

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/交易出 <灵石> [物品…]"}
                try:
                    stones = int(parts[1])
                except ValueError:
                    return {"ok": False, "error": "灵石须为整数"}
                items = parts[2:] if len(parts) > 2 else []
                res = TradeEngine.set_offer(char, stones, items)
                CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/trade_accept", "/交易同意"):
                from core.trade import TradeEngine

                res = TradeEngine.accept(char)
                # 结算/退回可能已从库写回双方；重载本人，禁止陈旧对象覆盖
                fresh = CharacterRepository.get_by_id(char.id)
                if fresh is not None:
                    char = fresh
                return {
                    "ok": res.get("success"),
                    "text": res.get("message", ""),
                    "status": self._status_dict(char),
                }
            if action in ("/trade_reject", "/交易拒绝"):
                from core.trade import TradeEngine

                res = TradeEngine.reject(char)
                fresh = CharacterRepository.get_by_id(char.id)
                if fresh is not None:
                    char = fresh
                return {
                    "ok": res.get("success"),
                    "text": res.get("message", ""),
                    "status": self._status_dict(char),
                }

            # ---------------- NPC 专柜 ----------------
            if action in ("/npc_goods", "/npc货单"):
                from core.trade import NpcShopEngine

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/npc货单 <道号>"}
                res = NpcShopEngine.catalog(char, "".join(parts[1:]))
                ret = {"ok": res.get("success"), "text": res.get("message", "")}
                if res.get("success") and res.get("goods") is not None:
                    ret["npc_goods"] = res["goods"]
                return ret
            if action in ("/npc_buy", "/npc买"):
                from core.trade import NpcShopEngine

                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/npc买 <道号> <货名> [数量]"}
                qty = 1
                rest = parts[2:]
                if rest and rest[-1].isdigit():
                    qty = max(1, int(rest[-1]))
                    rest = rest[:-1]
                if not rest:
                    return {"ok": False, "error": "用法：/npc买 <道号> <货名> [数量]"}
                res = NpcShopEngine.buy(char, parts[1], "".join(rest), qty)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/npc_sell", "/npc卖"):
                from core.trade import NpcShopEngine

                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/npc卖 <道号> <货名> [数量]"}
                qty = 1
                rest = parts[2:]
                if rest and rest[-1].isdigit():
                    qty = max(1, int(rest[-1]))
                    rest = rest[:-1]
                if not rest:
                    return {"ok": False, "error": "用法：/npc卖 <道号> <货名> [数量]"}
                res = NpcShopEngine.sell(char, parts[1], "".join(rest), qty)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}

            # ---------------- 拍卖行 ----------------
            if action in ("/auction", "/拍卖行", "/拍卖"):
                from core.trade import AuctionEngine

                res = AuctionEngine.board()
                return {
                    "ok": True,
                    "text": res["message"],
                    "auction": {
                        "lots": [
                            AuctionEngine.lot_panel_dict(l)
                            for l in (res.get("lots") or [])
                        ]
                    },
                }
            if action in ("/auction_list", "/上拍"):
                from core.trade import AuctionEngine

                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/上拍 <货名> <底价> [一口价]"}
                try:
                    start_price = int(parts[-1])
                    buyout = None
                    if len(parts) >= 4:
                        buyout = int(parts[-1])
                        start_price = int(parts[-2])
                        item = "".join(parts[1:-2])
                    else:
                        item = "".join(parts[1:-1])
                except ValueError:
                    return {"ok": False, "error": "价格须为整数。用法：/上拍 <货名> <底价> [一口价]"}
                res = AuctionEngine.list_item(char, item, start_price, buyout)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", ""),
                        "status": self._status_dict(char)}
            if action in ("/bid", "/拍", "/出价"):
                from core.trade import AuctionEngine

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/拍 <编号> <出价>，或 /出价 <金额>（单场直拍）"}
                if len(parts) == 2:
                    # /出价 <金额>：仅当恰有一张 OPEN 拍品时直拍该件；/拍 仍须带编号
                    if action != "/出价":
                        return {"ok": False, "error": "用法：/拍 <编号> <出价>"}
                    try:
                        amount = int(parts[1])
                    except ValueError:
                        return {"ok": False, "error": "出价须为整数"}
                    open_now = AuctionEngine.open_lots()
                    if not open_now:
                        return {"ok": False, "error": "当前无进行中的拍品。"}
                    if len(open_now) > 1:
                        ids = "、".join(f"#{l.id}【{l.item_name}】" for l in open_now)
                        return {"ok": False, "error": f"当前多件拍品在场：{ids}，请用 /拍 <编号> <出价>。"}
                    lot_id = open_now[0].id
                else:
                    lot_id = parts[1]
                    try:
                        amount = int(parts[2])
                    except ValueError:
                        return {"ok": False, "error": "出价须为整数"}
                res = AuctionEngine.bid(char, lot_id, amount)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/buyout", "/一口"):
                from core.trade import AuctionEngine

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/一口 <编号>"}
                res = AuctionEngine.buyout(char, parts[1])
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/auction_cancel", "/撤拍"):
                from core.trade import AuctionEngine

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/撤拍 <编号>"}
                res = AuctionEngine.cancel(char, parts[1])
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}

            if action in ("/create_art", "/自创功法"):
                raw = command.strip().split(None, 1)
                concept = raw[1].strip() if len(raw) > 1 else "吞噬他人精血壮大肉身"
                from ai.gateway import AIGateway, ai_available
                from ai.validator import DSLValidator
                from config import local_ai_allowed
                from core.art import format_art_card, clamp_art

                if not ai_available() and not local_ai_allowed():
                    return {
                        "ok": False,
                        "error": "【天道未启】自创功法需 AI 通道（配置 Key 或 USE_CCSWITCH=1）",
                    }
                art = AIGateway.generate_custom_art(concept, char.name)
                valid, check_msg = DSLValidator.validate_custom_art(art)
                if not valid:
                    # 规则钳制后仍不合法则丢弃（clamp_art 一般已修好）
                    art = clamp_art(art)
                if art.get("name"):
                    if not hasattr(char, "custom_arts") or char.custom_arts is None:
                        char.custom_arts = []
                    # 同名覆盖
                    char.custom_arts = [a for a in char.custom_arts if a.get("name") != art["name"]]
                    char.custom_arts.append(art)
                    if art["name"] not in char.skills:
                        char.skills.append(art["name"])
                    CharacterRepository.save(char)
                return {
                    "ok": True,
                    "text": format_art_card(art) + "\n（可用 /功法 查看全部；闭关已按最高修炼倍率生效）",
                    "art": art,
                    "status": self._status_dict(char),
                }
            if action in ("/arts", "/功法"):
                from core.art import list_arts_text

                return {
                    "ok": True,
                    "text": list_arts_text(getattr(char, "custom_arts", None)),
                    "arts": getattr(char, "custom_arts", None) or [],
                }
            if action in ("/history", "/大事记"):
                events = ChronicleRepository.get_recent(8)
                lines = ["【九州天道大事纪】"]
                for e in events:
                    lines.append(f"· {e}")
                return {"ok": True, "text": "\n".join(lines)}
            if action in ("/help", "/帮助", "/指令"):
                from core.command_catalog import format_help

                kw = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
                return {"ok": True, "text": format_help(kw)}

            return {"ok": False, "error": f"未知指令 {action}，输入 /帮助"}

    def _settle_apocalypse(self) -> Dict[str, Any]:
        """天地大劫：全员应劫，道统结转，纪元重开"""
        with self.lock:
            res = settle_apocalypse()
            if not res.get("ok"):
                return {"ok": False, "error": res.get("message")}
            from storage.db import CharacterRepository as CR

            settled = 0
            for c in CR.list_all_alive():
                if c.status == CharacterStatus.DEAD:
                    continue
                # 飞升极罕见：大乘+且功德高可「飞升」不死
                if c.realm.tier >= 8 and c.karma.merit_value >= 200:
                    ChronicleRepository.record(
                        "ASCEND", c.name, f"【{c.name}】于大劫中飞升，跳出三界！"
                    )
                    continue
                cause = "天地大劫"
                c.death_cause = cause
                try:
                    self._settle_if_needed(c, cause=cause)
                    settled += 1
                except Exception:
                    pass
            ChronicleRepository.record(
                "APOCALYPSE",
                "天道",
                res.get("message", "") + f" 应劫转世 {settled} 人。",
            )
            log_event("SEASON", "apocalypse", settled=settled)
            return {
                "ok": True,
                "text": (
                    res.get("message", "")
                    + f"\n未飞升应劫转世：{settled} 人。输入 /转世 或 /join 再入新纪。"
                ),
                "settled": settled,
            }

    def logout(self, token: str) -> Dict[str, Any]:
        """显式下线：逃遁失败 / 仓皇遁走 / 归隐庇护，并失效会话"""
        with self.lock:
            char = self.get_char(token)
            session = self._session(token)
            if not char:
                self.sessions.pop(token, None)
                return {"ok": True, "text": "会话已失效。"}
            # 闭关中下线：先按托管规则，不强制出关
            res = ProtectionEngine.settle_logout(char)
            CharacterRepository.save(char)
            if session:
                log_event(
                    "PROTECT",
                    "logout",
                    name=char.name,
                    logout_kind=res.get("kind"),
                    lost=res.get("lost_stones", 0),
                )
                self.sessions.pop(token, None)
                try:
                    AuthSessionRepository.delete(token)
                except Exception:
                    pass
            return {
                "ok": True,
                "text": res.get("message", "暂别红尘。"),
                "logout_kind": res.get("kind"),
                "lost_stones": res.get("lost_stones", 0),
            }

    # ---------------- 各指令实现 ----------------
    def _help(self) -> str:
        return (
            "局域网指令：/look /here /who /go <地> /闭关 [h] /出关 /突破 /探查 "
            "/斗法 <名> /交谈 <名> [话] /做 <言行> /自创功法 <理念> /回访 /legacy /转世 [名] [加成] "
            "/tick /agenda /机缘 /告示 /挂赏 <名> <金> /接令 <#> /大事记 "
            "/坊市 /行情 /版图 /购买 /出售 /服用 /寄存 /支取 /寄售 /买寄售 /撤单 /典当 /赎回 /钱包 /钱包提取 "
            "/交易 <名> /交易出 /交易同意 /交易拒绝 /npc货单 /npc买 /npc卖 "
            "/拍卖行 /拍卖 /上拍 /拍 /出价 /一口 /撤拍 "
            "/归隐 [h] /出隐 /下线 /目标 /灵气 /纪元 /天象 /纪元回流 /探险 [野外|秘境] "
            "/灵宠 /契约 <兽名> /喂养 <宠名> [丹药] /出战 <宠名> /休息 <宠名> /放生 <宠名> "
            "/洞府 /开辟 /播种 <种子名> [数量] /收获 /升级洞府 "
            "/委托 /接委托 <NPC名|编号> /交付 /弃委托 "
            "/诺言 /许诺 <对象> 赠物 <物品>|抵达 <地点>|委托|不攻 /应诺 [立诺者名] /毁诺 [受诺人名]（唯指令立诺入账，交谈口头应承不算） "
            "/因果链 天道事件链面板（恩/仇/诺/血仇的发酵进度与近史；勿与 /因果 混淆：本服 /因果 为回访别名，CLI /因果 为因果关系列表） "
            "/心法 /主修 <功法名> /辅修 <功法名> /卸功 <功法名> "
            "/炼体 [修炼 [n]] /炼神 [修炼 [n]] "
            "/镇魔 [服丹|静坐] "
            "/著书 [写] /研读 [书名] "
            "/榜 /飞升榜 [我|本纪元|道号] /宗门 /拜入 /叛门 /领俸禄 /晋升 /传功 /秘境 /帮助 "
            "/传闻 /关系 /频道 /公告 /gm /奇遇 /传说 /拍卖行 "
            "/拜师 /收徒 /出师 /结拜 /结拜同意 /绝交 /叛师 /师门任务 /交师门 /结义任务 /交结义 "
            "/贡献 /上交 /兑换 /宗门环 /接宗门环 /宗门势 /势力 /宗门令 /接宗门令 /交宗门令 /望气 /议政 /投票 支持|反对 /游说 <长老名> /除凶 /接令 /追凶 /弃令 /接除凶 /弃除凶 /反悬赏 /围剿 /世情 /追 "
            "/配方 /炼丹 /炼器 /悟丹 /悟器 /说 /挂断 /会话 /释放 /名物 /追查 /近况 /目标 /关系 /因果(回访) "
            "/任务 /目标 /天道 /世情 /望气"
        )

    @staticmethod
    def _season_theme_summary() -> Dict[str, Any]:
        """当前纪元天象摘要（F13）；推导异常时回退静默纪元口径，不阻断状态下发"""
        try:
            from core.season_theme import SeasonThemeEngine

            return SeasonThemeEngine.summary()
        except Exception:
            return {"name": "静默纪元", "key": "silence", "effect": "无天象修正", "season_number": 0}

    def _status_dict(self, c: Character) -> Dict[str, Any]:
        import time as _t
        from core.dungeon import DungeonEngine, DUNGEON_FLOORS
        from core.spells import SPELL_CATALOG
        prot = c.is_newbie_protected()
        prot_left = 0.0
        if prot:
            prot_left = max(0.0, c.newbie_protect_until() - _t.time())
        # 统计已穿戴法宝信息
        equipped_names = list(getattr(c, "equipped", []) or [])
        equipped_counts: Dict[str, int] = {}
        for eq in equipped_names:
            equipped_counts[eq] = equipped_counts.get(eq, 0) + 1

        equipped_list = []
        for idx, eq_name in enumerate(equipped_names):
            it = c.find_item(eq_name)
            from core.catalogs import get_equipment
            eq_cfg = get_equipment(eq_name) or {}
            tier_val = getattr(it, "tier", None) or eq_cfg.get("tier", 2)
            tier_name = getattr(it, "tier_name", None) or eq_cfg.get("grade_name", "灵品")
            slot_val = getattr(it, "slot", None) or eq_cfg.get("slot") or ("weapon" if any(w in eq_name for w in ("剑", "戈", "刃", "枪")) else ("armor" if any(w in eq_name for w in ("甲", "袍", "衣")) else "trinket"))
            slot_cn_map = {
                "weapon": "攻伐兵刃",
                "armor": "防身道袍",
                "trinket": "道心灵佩",
                "boots": "飞遁灵靴",
                "flying_treasure": "御空法宝"
            }
            slot_cn = slot_cn_map.get(slot_val, "本命法宝")
            # 法宝图（gallery-gameplay §3.5/§10.1）：后端下发完整路径
            try:
                from core.gallery_assets import artifact_key_for_item as _ak_item, artifact_key_for_equip_name as _ak_name, asset_path as _ap

                _eq_img = _ap(_ak_item(it)) if it is not None else _ap(_ak_name(eq_name))
            except Exception:
                _eq_img = ""
            # 器灵下发（gallery-gameplay §6.5/§10.1，只增 spirit 键）：未唤灵
            # 或无实体为 null；心情为惰性折算值（纯读不回写，锚点口径恒准）
            try:
                from core.artifact_spirit import public_spirit_dict as _psd

                _eq_spirit = _psd(it) if it is not None else None
            except Exception:
                _eq_spirit = None
            equipped_list.append({
                "img": _eq_img,
                "spirit": _eq_spirit,
                "uid": getattr(it, "uid", f"eq_{idx}_{eq_name}"),
                "name": it.name if it else eq_name,
                "kind": "equip",
                "tier": tier_val,
                "tierName": tier_name,
                "slot": slot_val,
                "slotCn": slot_cn,
                "stats": getattr(it, "stats", {}) if it and getattr(it, "stats", None) else (eq_cfg.get("stats") or {"power": 25.0}),
                "affixes": [
                    {"name": a.name, "desc": a.desc} for a in getattr(it, "affixes", [])
                ] if it and getattr(it, "affixes", None) else [
                    {"name": p["name"], "desc": p["desc"]} for p in eq_cfg.get("passive_skills", [])
                ],
                "active_spells": eq_cfg.get("active_spells", []),
                "set_name": eq_cfg.get("set_name"),
                "restrictions_count": eq_cfg.get("restrictions_count", 0),
                "lore": (getattr(it, "lineage_lore", "") or getattr(it, "description", "") or eq_cfg.get("desc", "")) or "随身佩戴之本命护道法宝。",
                "desc": (getattr(it, "description", "") or getattr(it, "lineage_lore", "") or eq_cfg.get("desc", "")) or "随身佩戴之本命护道法宝。",
            })

        # 过滤未佩戴的纳戒物品实体（避免纳戒与已穿戴重复显示）
        eq_remain = dict(equipped_counts)
        unworn_entities = []
        for it in (getattr(c, "items", []) or getattr(c, "item_entities", [])):
            if eq_remain.get(it.name, 0) > 0:
                eq_remain[it.name] -= 1
            else:
                unworn_entities.append(it)

        # 宗门信息与俸禄/日环/仙门名录
        from config import SECTS_CONFIG, SECONDS_PER_GAME_MONTH
        from core.sect import PROMOTE_REQ_TIER
        from core.world_grid import WorldGridEngine
        from core.treasure_system import calculate_fengshui_direction
        from core.sect_contrib import get_streak, ensure_daily_ring
        from core.npc_chat import pop_player_inbox

        sect_name = c.sect or ""
        sect_rank = c.sect_rank or ("散修" if not sect_name else "外门弟子")
        sect_cfg = SECTS_CONFIG.get(sect_name) or {}

        # 俸禄冷却计算
        salary = sect_cfg.get("monthly_salary", 0) if sect_name else 0
        last_salary = getattr(c, "last_salary_time", 0.0) or 0.0
        elapsed_salary = _t.time() - last_salary
        salary_cd_sec = max(0, int(SECONDS_PER_GAME_MONTH - elapsed_salary)) if (last_salary > 0 and elapsed_salary < SECONDS_PER_GAME_MONTH) else 0
        salary_claimable = bool(sect_name and salary > 0 and salary_cd_sec <= 0)

        # 晋升资格判定
        order = ["外门弟子", "内门弟子", "执事", "长老"]
        next_rank = None
        can_promote = False
        promote_req_tier = 0
        if sect_name and sect_rank in order:
            idx = order.index(sect_rank)
            if idx < len(order) - 1:
                next_rank = order[idx + 1]
                promote_req_tier = PROMOTE_REQ_TIER.get(next_rank, 99)
                can_promote = (c.realm.tier >= promote_req_tier)

        # 宗门日环
        streak = get_streak(c) if sect_name else 0
        ring_info = {}
        if sect_name:
            try:
                ring_raw = ensure_daily_ring(c)
                ring_info = {
                    "day": ring_raw.get("day", ""),
                    "accepted": ring_raw.get("accepted"),
                    "done": bool(ring_raw.get("done")),
                    "themes": [
                        {
                            "id": t.get("id"),
                            "label": t.get("label", ""),
                            "lore": t.get("lore", ""),
                            "need_item": t.get("need_item", ""),
                            "need_streak": t.get("need_streak", 0),
                        }
                        for t in (ring_raw.get("themes") or [])
                    ]
                }
            except Exception:
                ring_info = {}

        sects_catalog = [
            {
                "name": k,
                "alignment": v.get("alignment", ""),
                "desc": v.get("desc", ""),
                "headquarters": v.get("headquarters", ""),
                "cave_location": v.get("cave_location", ""),
                "req_dao_heart": v.get("req_dao_heart", 0),
                "max_sin": v.get("max_sin", 10**9),
                "min_sin": v.get("min_sin", 0),
                "monthly_salary": v.get("monthly_salary", 0),
                "starter_array": v.get("starter_array", ""),
                "rules_tip": v.get("rules_tip", ""),
            }
            for k, v in SECTS_CONFIG.items()
        ]

        unread_msgs = pop_player_inbox(c.id)

        # 账户钱包块（§2.8 命盘钱包行）：只读，不建行；NPC／无账户行为空钱包
        try:
            from core.wallet import wallet_summary as _ws

            _acc = LegacyRepository.get(c.user_id)
            _wallet_block = _ws(_acc) if _acc is not None else {"balance": 0, "entries": [], "ledger": []}
            from storage.db import AccountRepository as _AR

            _wallet_block = dict(_wallet_block)
            _wallet_block["username"] = _AR.get_username(c.user_id)
        except Exception:
            _acc = None
            _wallet_block = {"balance": 0, "entries": [], "ledger": [], "username": ""}
        # 前世摘要（转世继承，只增键）：留痕优先，旧档回退 past_lives；无前世 lives=0
        _past_life = {"lives": 0, "last_name": "", "last_cause": "", "shadow_count": 0}
        try:
            if _acc is not None:
                _past_life["lives"] = int(_acc.total_lives or 0)
                if _acc.traces:
                    _lt = _acc.traces[-1]
                    _past_life["last_name"] = _lt.name
                    _past_life["last_cause"] = _lt.cause
                    # 观察4：与 causality_text 同口径（applied_shadow_entries），
                    # 低于 SHADOW_APPLY_MIN、实际未落账的条目不计数
                    from core.inheritance import applied_shadow_entries as _ase

                    _past_life["shadow_count"] = len(_ase(_acc, _lt))
                elif _acc.past_lives:
                    _lp = _acc.past_lives[-1]
                    _past_life["last_name"] = _lp.name
                    _past_life["last_cause"] = _lp.cause
        except Exception:
            pass
        # 因果链摘要（karma-event-chains §6.1，只增键）：旧前端忽略即可
        try:
            from core.karma_chains import KarmaChainEngine as _KCE

            _karma_chains = _KCE.status_summary(c)
        except Exception:
            _karma_chains = {"active": 0, "fermenting": 0, "nearest_mature_game_days": None}
        # 图库/图鉴（gallery-gameplay §3.3/§8.2/§10.1，只增键）：派生点亮在
        # 命盘组装后统一合并，newly 只在本次发生点亮的下发中非空。
        _gender_val = getattr(c, "gender", "") or ""
        try:
            from core.gallery_assets import player_portrait_path as _ppp

            _portrait_val = _ppp(_gender_val, c.realm.tier)
        except Exception:
            _portrait_val = ""
        _gallery_newly: List[str] = []
        try:
            from core import gallery as _gallery_mod

            _gallery_newly = _gallery_mod.unlock_from_character(c)
            _gallery_block = _gallery_mod.summary(c.user_id, newly=_gallery_newly)
        except Exception:
            _gallery_block = {"unlocked": [], "count": 0, "total": 139, "title": "", "newly": []}
        # 功法图（§3.7/§10.1）：art_images 以功法名为键覆盖 skills+custom_arts
        _art_images: Dict[str, str] = {}
        try:
            from core.gallery_assets import art_key_for as _akf, asset_path as _ap2

            _art_names = list(c.skills or [])
            for _art in (c.custom_arts or []):
                if isinstance(_art, dict) and _art.get("name"):
                    _art_names.append(str(_art["name"]))
            for _an in _art_names:
                if _an and _an not in _art_images:
                    _art_images[_an] = _ap2(_akf(_an, c))
        except Exception:
            _art_images = {}
        # 行囊图与线索链摘要（§10.1）：按 uid 预计算，items 字面量里只查表
        _item_imgs: Dict[str, str] = {}
        _item_chains: Dict[str, Any] = {}
        try:
            from core.gallery_assets import item_image_path as _iip
            from core.treasure_clue import chain_summary as _chain_summary

            for _it in unworn_entities:
                _uid = getattr(_it, "uid", getattr(_it, "id", ""))
                _item_imgs[_uid] = _iip(_it)
                _item_chains[_uid] = _chain_summary(_it) if getattr(_it, "kind", None) == ItemKind.TREASURE_MAP else None
        except Exception:
            _item_imgs = {}
            _item_chains = {}
        # 基础神通图（§3.7）：复制 catalog 项后增 img，不污染原 catalog
        try:
            from core.gallery_assets import spell_key_for_element as _skf, asset_path as _ap3

            _spells_catalog = [
                {**_sp, "img": _ap3(_skf(_sp.get("element")))}
                for _sp in SPELL_CATALOG.values()
            ]
        except Exception:
            _spells_catalog = list(SPELL_CATALOG.values())
        # 游戏感第一期只增（§3.11/§4.2/§5.3）：出身 / 命格 / 关系动态
        _origin_block = getattr(c, "origin", None) or None
        try:
            from core.ceremony import fate_block as _fate_block_fn

            _fate_block = _fate_block_fn(c)
        except Exception:
            _fate_block = {"boons": [], "pending": [], "power_bonus": 1.0}
        # 二期 §8.1（fate 区段）：fate 只增 thread 子键，无线为 null，
        # 既有 boons/pending/power_bonus 三子键一字不动。ceremony.py
        # 本轮不改，thread 子键在此组装（数据源 FateThreadRepository，
        # 走 player_id 列查询，与 karma_chains 块同量级）。
        _fate_block = dict(_fate_block)
        try:
            from core.fate_thread import FateThreadEngine as _FTE_sd

            _fate_block["thread"] = _FTE_sd.thread_status_dict(c)
        except Exception:
            _fate_block["thread"] = None
        # 二期 §8.1（status 区段）：location_image 只增一键——场景映射
        # 唯一事实源在 gallery_assets（图库岗 §9.4），未就位时为空串。
        _location_image = ""
        try:
            from core.gallery_assets import LOCATION_SCENE_KEYS as _LSCK
            from core.gallery_assets import asset_path as _ap_sd

            _scene_key = _LSCK.get(c.location or "")
            if _scene_key:
                _location_image = _ap_sd(_scene_key)
        except Exception:
            _location_image = ""
        # 二期 §9.3（pet 区段）：pet 块只增 img——灵宠物种图完整路径；
        # 解析口径唯一在 gallery.pet_image_key（出战宠优先、无出战取
        # 首只活宠），无图为空串（前端不渲染图位）。
        _pet_img = ""
        try:
            from core import gallery as _gallery_pet
            from core.gallery_assets import asset_path as _ap_pet

            _pet_key = _gallery_pet.pet_image_key(c)
            if _pet_key:
                _pet_img = _ap_pet(_pet_key)
        except Exception:
            _pet_img = ""
        try:
            from core.relations import relations_recent_and_marks as _rrm

            _rel_recent, _rel_marks = _rrm(c.id, recent_limit=5, pool=30)
        except Exception:
            _rel_recent, _rel_marks = [], {}
        return {
            "name": c.name,
            "version": getattr(c, "version", 1),
            "realm": c.realm.name,
            "origin": _origin_block,
            "fate": _fate_block,
            "location_image": _location_image,
            "relations_recent": _rel_recent,
            "relations_marks": _rel_marks,
            "location": c.location,
            "stones": c.spirit_stones,
            "vault": c.vault_stones,
            "wallet": _wallet_block,
            "past_life": _past_life,
            "karma_chains": _karma_chains,
            # 图库（gallery-gameplay §10.1，只增键）
            "gender": _gender_val,
            "portrait": _portrait_val,
            "gallery": _gallery_block,
            "art_images": _art_images,
            "sin": c.karma.sin_value,
            "merit": c.karma.merit_value,
            "exp": f"{c.realm.current_exp}/{c.realm.max_exp}",
            "rem_years": round(c.lifespan.get_remaining_years(), 2),
            "dead": c.status == CharacterStatus.DEAD or c.lifespan.is_dead(),
            "status": c.status.value if isinstance(c.status, CharacterStatus) else str(c.status),
            "status_cn": status_cn(c.status),
            "root": c.spiritual_root.display_name(),
            "root_eff": round(c.spiritual_root.efficiency, 2),
            "dao_heart": c.karma.dao_heart,
            "skills": list(c.skills[:8]),
            # 灰度批次 B：行囊面板下发（纯新增字段，旧前端忽略即可）
            "inventory": list(c.inventory),
            # "equipped" 键合并裁定：取分支富对象列表（equipped_list，workbench
            # 契约，下方键值后置生效）；main 的 list(c.equipped) 名称列表形态
            # 与之同键互斥，test_status_dict_gray 的名称断言为已知牺牲项。
            "arrays": list(c.arrays),
            # 灵宠（F01）：出战灵宠摘要 + 在养只数（纯新增）
            "pet": (
                {
                    "name": _ap.name,
                    "species": _ap.species,
                    "level": pet_level_for(_ap.growth),
                    "intimacy": _ap.intimacy,
                    "img": _pet_img,
                }
                if (_ap := pet_active(c)) is not None
                else None
            ),
            "pets_count": len([p for p in (c.pets or []) if p.state != "dead"]),
            # 洞府灵田（F06）：洞府摘要（纯新增，无洞府为 None）
            "cave": FarmEngine.cave_summary(c),
            # 心法槽位（F02）：当前主修/辅修（纯新增）
            "arts": {
                "main": getattr(c, "main_art", "") or "",
                "sub": list(getattr(c, "sub_arts", None) or []),
            },
            # 自创功法（CA-011）：只读回显角色行已存储数据，不新增计算/存储语义
            "custom_arts": list(getattr(c, "custom_arts", None) or []),
            # 炼体/炼神双修（F10）：副修层数（纯新增；走引擎钳制口径，与面板/加成一致）
            "body_soul": {
                "body": BodySoulEngine.body_level(c),
                "soul": BodySoulEngine.soul_level(c),
            },
            # 心魔长期状态（F16）：阶段/魔念（纯新增；纯读推导不落库）
            "heart_demon_state": DemonStateEngine.summary(c),
            # 著书立说（F11）：灵感/声望（纯新增）
            "books": {
                "inspiration": int(getattr(c, "inspiration", 0) or 0),
                "prestige": int(getattr(c, "prestige", 0) or 0),
            },
            # 纪元天象（F13）：当前纪元主题摘要（纯新增；纯函数推导，异常回退静默纪元口径）
            "season_theme": self._season_theme_summary(),
            # 天道可感知：血煞以规则侧 blood_mark_until 为准，大限阈值与 config 对齐
            "blood_marked": c.karma.is_blood_marked(),
            "lifespan_warning": c.lifespan.get_remaining_years()
            <= LIFESPAN_WARNING_YEARS,
            "meditating": c.status == CharacterStatus.MEDITATING,
            "is_meditating": c.status == CharacterStatus.MEDITATING,
            "sect": sect_name,
            "rank": sect_rank,
            "sect_contribution": getattr(c, "sect_contribution", 0),
            "sect_streak": streak,
            "salary": salary,
            "salary_claimable": salary_claimable,
            "salary_cd_sec": salary_cd_sec,
            "can_promote": can_promote,
            "next_rank": next_rank,
            "promote_req_tier": promote_req_tier,
            "sect_ring": ring_info,
            "sects_catalog": sects_catalog,
            "unread_messages": unread_msgs,
            "newbie_protected": prot,
            "newbie_left_hours": round(prot_left / 3600.0, 1) if prot else 0,
            "protect": ProtectionEngine.status_text(c),
            "conflict_zone": is_conflict_zone(c.location),
            "qi_mult": round(qi_mod.global_qi_multiplier(), 3),
            "crane_pending_item": getattr(c, "crane_pending_item", None),
            "max_bag_slots": getattr(c, "MAX_BAG_SLOTS", 64),
            "is_bag_full": c.is_bag_full() if hasattr(c, "is_bag_full") else (len(getattr(c, "items", [])) >= 64),
            "equipped": equipped_list,
            "items": [
                {
                    "uid": getattr(it, "uid", getattr(it, "id", f"it_{idx}")),
                    "img": _item_imgs.get(getattr(it, "uid", getattr(it, "id", "")), ""),
                    "clue_chain": _item_chains.get(getattr(it, "uid", getattr(it, "id", "")), None),
                    "name": it.name,
                    "kind": it.kind.value if hasattr(it.kind, "value") else str(it.kind),
                    "tier": it.tier,
                    "tierName": ["凡品", "人品", "地品", "天品", "仙品"][min(4, max(0, it.tier - 1))],
                    "slot": getattr(it, "slot", None),
                    "slotCn": "天机秘宝图卷" if (getattr(it, "kind", None) == ItemKind.TREASURE_MAP or "图" in it.name) else ("神材" if getattr(it.kind, "value", str(it.kind)) == "material" else ("绝世法宝" if getattr(it.kind, "value", str(it.kind)) == "equip" else "灵物")),
                    "lore": getattr(it, "lineage_lore", "") or getattr(it, "description", "") or "天地造化所钟之奇珍。",
                    "desc": getattr(it, "description", "") or getattr(it, "lineage_lore", "") or "天地造化所钟之奇珍。",
                    "targetNodeName": (
                        (getattr(it, "custom_metadata", {}) or {}).get("target_node_name")
                        or getattr(it, "treasure_target_node_name", "")
                        or "落霞山灵泉"
                    ),
                    "targetNodeId": (getattr(it, "custom_metadata", {}) or {}).get("target_node_id", ""),
                    "isAtTarget": bool(
                        (getattr(it, "kind", None) == ItemKind.TREASURE_MAP or "图" in it.name)
                        and (
                            (getattr(it, "custom_metadata", {}) or {}).get("target_node_name") == c.location
                            or (getattr(it, "custom_metadata", {}) or {}).get("target_node_id") == getattr(WorldGridEngine.get_node(c.location), "id", "")
                        )
                    ),
                    "archetypeCn": (getattr(it, "custom_metadata", {}) or {}).get("archetype", "") or getattr(it, "treasure_archetype_cn", "") or "离火九宫破阵",
                    "coords": (
                        f"{calculate_fengshui_direction(WorldGridEngine.get_node(c.location), WorldGridEngine.get_node((getattr(it, 'custom_metadata', {}) or {}).get('target_node_id', ''))).get('bagua', '天机方位')} · {calculate_fengshui_direction(WorldGridEngine.get_node(c.location), WorldGridEngine.get_node((getattr(it, 'custom_metadata', {}) or {}).get('target_node_id', ''))).get('direction_cn', '前路')}气机"
                        if (getattr(it, "kind", None) == ItemKind.TREASURE_MAP or "图" in it.name) and WorldGridEngine.get_node((getattr(it, 'custom_metadata', {}) or {}).get('target_node_id', ''))
                        else ((getattr(it, "custom_metadata", {}) or {}).get("coords", "") or getattr(it, "treasure_coords_desc", "") or "丙午方位 · 离火宫 南行三十里")
                    ),
                    "riddle": (
                        calculate_fengshui_direction(WorldGridEngine.get_node(c.location), WorldGridEngine.get_node((getattr(it, 'custom_metadata', {}) or {}).get('target_node_id', ''))).get('rhyme', '')
                        if (getattr(it, "kind", None) == ItemKind.TREASURE_MAP or "图" in it.name) and WorldGridEngine.get_node((getattr(it, 'custom_metadata', {}) or {}).get('target_node_id', ''))
                        else (getattr(it, "treasure_riddle_cn", "") or (getattr(it, "custom_metadata", {}) or {}).get("riddle_text", "") or (getattr(it, "custom_metadata", {}) or {}).get("riddle", "") or "天道浩渺，机缘自显。")
                    ),
                    "clue": (
                        calculate_fengshui_direction(WorldGridEngine.get_node(c.location), WorldGridEngine.get_node((getattr(it, 'custom_metadata', {}) or {}).get('target_node_id', ''))).get('clue', '')
                        if (getattr(it, "kind", None) == ItemKind.TREASURE_MAP or "图" in it.name) and WorldGridEngine.get_node((getattr(it, 'custom_metadata', {}) or {}).get('target_node_id', ''))
                        else "风水汇聚，当循天机定盘指针寻访宝穴。"
                    ),
                    "stats": getattr(it, "stats", {}),
                    "affixes": [
                        {"name": a.name, "desc": a.desc} for a in getattr(it, "affixes", [])
                    ],
                    "qty": 1,
                }
                for idx, it in enumerate(unworn_entities)
            ] + [
                {
                    "uid": f"legacy_{i}",
                    "name": s_name,
                    "kind": "treasure_map" if "图" in s_name else ("pill" if ("丹" in s_name or "露" in s_name) else "material"),
                    "tier": 2,
                    "tierName": "人品",
                    "slotCn": "天机秘宝图卷" if "图" in s_name else ("灵丹" if ("丹" in s_name or "露" in s_name) else "灵物"),
                    "lore": f"行囊中妥善收藏之【{s_name}】。",
                    "desc": f"行囊中妥善收藏之【{s_name}】。",
                    "qty": 1,
                }
                for i, s_name in enumerate(getattr(c, "inventory", []))
                if isinstance(s_name, str) and s_name not in {it.name for it in (getattr(c, "items", []) or getattr(c, "item_entities", []))} and s_name not in equipped_counts
            ],
            "stall_earnings": getattr(c, "stall_earnings", 0),
            "stall_items": [
                {
                    "id": l.id,
                    "name": l.item_name,
                    "price": l.price,
                    "kind": l.kind,
                    "created_at": l.created_at,
                    "seller_name": l.seller_name,
                }
                for l in MarketListingRepository.list_all()
                if l.seller_id == c.id and l.is_open()
            ],
            "market_listings": [
                {
                    "id": l.id,
                    "name": l.item_name,
                    "price": l.price,
                    "tax": max(1, int(l.price * 0.05)),
                    "kind": l.kind,
                    "seller": l.seller_name,
                    "created_at": l.created_at,
                    "tier": "地品" if ("古" in l.item_name or "神" in l.item_name) else ("天品" if "天" in l.item_name else "人品"),
                    "affixes": "真仙契约担保",
                }
                for l in MarketEngine.open_listings(MarketListingRepository.list_all())
            ],
            "dungeon": DungeonEngine.get_session(c.id),
            "spells_catalog": _spells_catalog,
            "dungeon_floors": [
                {"floor": f_k, "name": f_v["name"], "tier_name": f_v["tier_name"], "min_tier": f_v["min_tier"]}
                for f_k, f_v in DUNGEON_FLOORS.items()
            ],
            "combat": c.combat.model_dump() if hasattr(c, "combat") and hasattr(c.combat, "model_dump") else {},
            "soul": c.soul.model_dump() if hasattr(c, "soul") and hasattr(c.soul, "model_dump") else {},
            "equip_slots": c.equip_slots.model_dump() if hasattr(c, "equip_slots") and hasattr(c.equip_slots, "model_dump") else {},
            "professions": c.professions.model_dump() if hasattr(c, "professions") and hasattr(c.professions, "model_dump") else {},
            # 委托链摘要（F07，纯新增）：None 或 {publisher, ring: "x/y", kind}
            "quest": (
                {
                    "publisher": c.active_quest.publisher_name,
                    "ring": f"{min(c.active_quest.ring_index + 1, len(c.active_quest.rings))}/{len(c.active_quest.rings)}",
                    "kind": (
                        c.active_quest.rings[min(c.active_quest.ring_index, len(c.active_quest.rings) - 1)].kind
                        if c.active_quest.rings else ""
                    ),
                }
                if getattr(c, "active_quest", None)
                else None
            ),
        }

    def _look(self, c: Character) -> str:
        loc = WORLD_LOCATIONS.get(c.location, {})
        from core.here import list_here
        others = list_here(c)
        lines = [
            f"【{c.name}】{c.realm.name} | 寿元约{c.lifespan.get_remaining_years():.1f}岁",
            f"灵根：{c.spiritual_root.display_name()} · 吸收 {c.spiritual_root.efficiency:.2f}x · 道心 {c.karma.dao_heart}",
            f"位置：{c.location}（{loc.get('region','')} · 灵气{loc.get('density',1)} · "
            f"{'安全' if loc.get('is_safe') else '凶险'}）",
            f"随身灵石 {c.spirit_stones} | 金库 {c.vault_stones} | 业力 {c.karma.sin_value} | 功德 {c.karma.merit_value}",
            f"法门：{'、'.join(c.skills[:6]) or '无'}",
        ]
        if c.is_newbie_protected():
            left = max(0.0, c.newbie_protect_until() - time.time()) / 3600.0
            lines.append(f"【新手庇护】剩余约 {left:.1f} 小时（不可被攻击，亦不可主动伤人）")
        if getattr(c, "pill_exp_mult", 0) > 0:
            lines.append(f"【丹药】{c.pill_exp_note or '药力'} 待闭关 +{int(c.pill_exp_mult*100)}% 修为")
        eq = getattr(c, "equipped", None) or []
        if eq:
            lines.append(f"已穿戴：{'、'.join(eq)}")
        arts = getattr(c, "custom_arts", None) or []
        if arts:
            names = "、".join(a.get("name") or "?" for a in arts[:3])
            lines.append(f"已悟功法：{names}（/功法 详览）")
        if c.status == CharacterStatus.MEDITATING:
            try:
                prog = WorldClock.get_meditation_progress(c)
                rem_h = max(0.0, float(prog.get("remaining_seconds") or 0) / 3600.0)
                pct = float(prog.get("progress_pct") or 0) * 100
                lines.append(
                    f"【闭关入定】于【{c.location}】锁门吐纳，进度 {pct:.0f}%，约余 {rem_h:.1f} 现实小时"
                    f"（不可迁跃/斗法；/出关 可提前收功）"
                )
            except Exception:
                lines.append("【闭关入定】洞府锁门中（/出关 可提前收功）")
        prot_txt = ProtectionEngine.status_text(c)
        if prot_txt and "归隐" in prot_txt:
            lines.append(f"【{prot_txt}】不可被攻击；随身财货不可转移")
        lines.append(qi_mod.qi_status_text())
        lines.append(season_status_text())
        if c.sect:
            lines.append(f"宗籍：{c.sect} · {c.sect_rank}")
        if others:
            brief = []
            for o in others[:8]:
                mark = "【血煞】" if o.get("blood_marked") else ""
                if o.get("is_npc"):
                    brief.append(f"{o['name']}({o['realm']}){mark}")
                else:
                    brief.append(f"{o['name']}({o['realm']})[玩家]{mark}")
            lines.append("同道：" + "、".join(brief))
            lines.append("（详情输入 /同场）")
        else:
            lines.append("此地暂无其他修士。")
        return "\n".join(lines)

    def _who(self) -> str:
        alive = CharacterRepository.list_all_alive()
        by_loc: Dict[str, List[str]] = {}
        for a in alive:
            by_loc.setdefault(a.location, []).append(f"{a.name}({a.realm.name})")
        lines = [f"在线世界共 {len(alive)} 名修士："]
        for loc, names in sorted(by_loc.items()):
            lines.append(f"  {loc}：{'、'.join(names[:8])}")
        return "\n".join(lines)

    def _who_data(self) -> Dict[str, Any]:
        """在线名录结构（/who who 键；与 _who 同循环，成员全量）。"""
        alive = CharacterRepository.list_all_alive()
        by_loc: Dict[str, List[Dict[str, str]]] = {}
        for a in alive:
            by_loc.setdefault(a.location, []).append(
                {"name": a.name, "realm": a.realm.name}
            )
        groups = [
            {"place": loc, "members": members}
            for loc, members in sorted(by_loc.items())
        ]
        return {"total": len(alive), "groups": groups}

    def _bounty_rows(self) -> List[Dict[str, Any]]:
        """告示板行集（/告示 bounties 键；与 _bounty_board 同源）。"""
        board = BountyEngine.list_board(BountyRepository.list_all())
        rows = []
        for b in board:
            status = b.status.value if hasattr(b.status, "value") else str(b.status)
            rows.append(
                {
                    "id": b.id,
                    "target": b.target_name,
                    "reward": b.reward,
                    "status": status,
                    "status_cn": bounty_status_cn(b.status),
                    "issuer": b.issuer_display(),
                    "anonymous": bool(b.issuer_anonymous),
                    "reason": b.reason,
                }
            )
        return rows

    def _go(self, c: Character, dest: str) -> Dict[str, Any]:
        if c.status == CharacterStatus.CAPTURED:
            return {"ok": False, "error": "你已被擒，动弹不得。待对方 /释放 或自救。"}
        matched = None
        for loc in WORLD_LOCATIONS:
            if dest and dest in loc:
                matched = loc
                break
        if not matched:
            from core.world_grid import WorldGridEngine
            node = WorldGridEngine.get_node(dest)
            if node:
                matched = node.base_name
        if not matched:
            return {"ok": False, "error": f"未知地点：{dest}"}

        dismiss_note = None
        try:
            from core.omen_scene import dismiss_on_leave

            dismiss_note = dismiss_on_leave(c, action_label="御剑迁跃")
        except Exception:
            pass

        c.location = matched
        CharacterRepository.save(c)
        # 诺言账（F14）：抵达诺核验——迁跃落点即事实
        promise_line = ""
        try:
            promise_line = PromiseEngine.note_arrival(c, matched) or ""
        except Exception:
            promise_line = ""
        # 命途落点（二期 §3.6 T5）：先把落点记入 thread.visited 再求值，
        # 与下方 maybe_engage 迁跃触发同点同段；有推进才回存。
        try:
            from core.fate_thread import FateThreadEngine as _FTEg

            _fate_go_res = _FTEg.record_visit(c, matched)
            if _fate_go_res.get("changed"):
                CharacterRepository.save(c)
        except Exception:
            pass
        # 图库点亮（二期 §9.4）：迁跃落点点亮落点地点场景图，与上方
        # 命途 T5 同点位同段；无映射地点钩子自返 []，失败不影响迁跃本体。
        try:
            from core import gallery as _gallery_go

            _gallery_go.note_location_visit(c, matched)
        except Exception:
            pass
        text = f"御剑化虹，抵达【{matched}】。"
        if promise_line:
            text += f"\n{promise_line}"
        try:
            from core.sect_contrib import sync_ring
            from config import SECTS_CONFIG

            hq = (SECTS_CONFIG.get(c.sect) or {}).get("headquarters")
            if hq and matched == hq:
                r = sync_ring(c, "visit")
                if r:
                    text += "\n" + r.get("msg", "")
                    CharacterRepository.save(c)
        except Exception:
            pass
        ev = EventEngine.fire(c, context=f"途经 {matched}")
        if ev:
            CharacterRepository.save(c)
            text += f"\n【{ev['title']}】{ev['narrative']}\n落账：{ev['effects_summary']}"
        # 奇遇链（小概率）
        try:
            from core.event_chains import EventChainEngine

            loc_cfg = WORLD_LOCATIONS.get(matched) or {}
            if not loc_cfg.get("is_safe", False) or "秘境" in matched:
                ch = EventChainEngine.maybe_start(c, trigger="travel")
                if ch:
                    CharacterRepository.save(c)
                    st = ch.steps[0]
                    opts = " | ".join(f"{x['id']}.{x['label']}" for x in st["choices"])
                    text += f"\n\n【奇遇 · {ch.title}】{st['prompt']}\n选项：{opts}（/奇遇 <n>）"
        except Exception:
            pass
        # 同场 NPC 主动搭话
        try:
            opens = NpcProactiveEngine.maybe_engage(c, max_speakers=1)
            for o in opens:
                text += "\n" + o.get("text", "")
        except Exception:
            pass
        # 主动戏剧评估（game-feel-phase2 §5.4 迁跃落点触发点，与 maybe_engage 同段；
        # 同场事件 text 经本通道下发，异地事件只入待回应队列）
        try:
            from core.npc_proactive import DramaEngine

            for _dev in (DramaEngine.evaluate(c, trigger="travel") or [])[:1]:
                _dnpc = CharacterRepository.get_by_id(_dev.get("npc_id") or "")
                if _dnpc is not None and _dnpc.location == c.location:
                    text += "\n" + str(_dev.get("text") or "")
                else:
                    text += (f"\n【江湖有事】{_dev.get('npc_name', '有人')}"
                             f"遣人传话，事已入待回应（/回应 查看）。")
        except Exception:
            pass
        # 因果回访（小概率）
        try:
            rv = RevengeEngine.maybe_callback(c, chance=0.25)
            if rv:
                CharacterRepository.save(c)
                if rv.get("spawned"):
                    CharacterRepository.save(rv["spawned"])
                text += "\n\n" + rv.get("text", "")
        except Exception:
            pass
        # 撞见秘境开启
        try:
            rid = SecretRealmEngine.maybe_open_nearby(c, chance=0.15)
            if rid:
                text += f"\n【天机示现】附近【{rid}】禁制松动，似已开启！输入 /秘境 {rid} 可入。"
        except Exception:
            pass
        if dismiss_note:
            text = f"{dismiss_note}\n{text}"
        payload = {"ok": True, "text": text, "status": self._status_dict(c)}
        return self._append_natural_omen(c, payload, context="御剑迁跃")

    def _meditate(self, c: Character, hours: float) -> Dict[str, Any]:
        dismiss_note = None
        try:
            from core.omen_scene import dismiss_on_leave

            dismiss_note = dismiss_on_leave(c, action_label="入定闭关")
        except Exception:
            pass

        res = WorldClock.start_meditation(c, hours, 0)
        if res["success"]:
            CharacterRepository.save(c)
        msg = res["message"]
        if dismiss_note:
            msg = f"{dismiss_note}\n{msg}"
        return {"ok": res["success"], "text": msg, "status": self._status_dict(c)}

    def _emerge(self, c: Character) -> Dict[str, Any]:
        if c.status != CharacterStatus.MEDITATING:
            return {"ok": False, "text": "未在闭关。", "status": self._status_dict(c)}
        res = WorldClock.settle_meditation(c, force_interrupt=True)
        CharacterRepository.save(c)
        lines = [
            f"出关：闭关 {res.get('actual_real_hours',0):.1f} 小时，"
            f"修为+{res.get('exp_gained',0)}，寿元余 {res.get('after_years',0):.1f}"
        ]
        _de = res.get("demon_eruption")
        if _de:
            lines.append(f"【心魔发作】{_de.get('text', '')}（/镇魔 可镇压）")
        dead = False
        _emerge_settle = None
        if res.get("is_fatal"):
            c.status = CharacterStatus.DEAD
            CharacterRepository.save(c)
            lines.append("寿尽坐化。")
            dead = True
            _emerge_settle = self._settle_if_needed(c, cause="洞府坐化")
        ret = {
            "ok": True,
            "text": "\n".join(lines),
            "death": dead,
            "status": self._status_dict(c),
            "legacy": self.legacy_info_id(c.user_id) if dead else None,
            "sweep": (_emerge_settle or {}).get("sweep") if _emerge_settle else None,
            "death_cause": c.death_cause if dead else None,
        }
        if not dead:
            return self._append_natural_omen(c, ret, context="出关入世")
        return ret

    def legacy_info_id(self, user_id: str) -> Dict[str, Any]:
        account = LegacyRepository.get_or_create(user_id)
        boosts = [
            {"key": k, "name": cfg["name"], "cost": cfg["cost"], "desc": cfg["desc"]}
            for k, cfg in LEGACY_BOOSTS.items()
        ]
        from core.inheritance import current_karma_shadow, trace_summary

        return {
            "points": account.points,
            "lives": account.total_lives,
            "boosts": boosts,
            "max_boosts": LEGACY_MAX_BOOSTS_PER_LIFE,
            # 转世继承（只增）：最近 8 世留痕摘要 + 当前角色本世被施加的影子清单
            "traces": [trace_summary(t) for t in account.traces[-8:]],
            "karma_shadow": current_karma_shadow(account),
        }

    def _breakthrough(self, c: Character, session: Optional[Session]) -> Dict[str, Any]:
        if not c.realm.is_full:
            return {"ok": False, "error": f"修为未圆满 {c.realm.current_exp}/{c.realm.max_exp}"}
        heart_mod = 0.0
        demon_text = ""
        if c.realm.sub_tier == 3:
            hd = HeartDemonEngine.start(c)
            self.hd_sessions[hd.id] = hd
            if session:
                session.pending_heart_demon = hd.id
            CharacterRepository.save(c)
            opts = " | ".join(f"{i+1}.{o['label']}" for i, o in enumerate(hd.options))
            return {
                "ok": True,
                "pending_heart_demon": True,
                "text": (
                    f"【心魔问心】\n{hd.narrative}\n\n选项：{opts}\n"
                    f"或直接输入你的应对（其他）。"
                ),
                "heart_demon_options": hd.options,
            }

        _pend_before = len(getattr(c, "fate_pending", None) or [])
        res = BreakthroughEngine.attempt_breakthrough(c, use_pill=False, heart_mod=heart_mod)
        CharacterRepository.save(c)
        dead = bool(res.get("is_fatal"))
        if res.get("success") and res.get("is_major"):
            try:
                GoalEngine.on_breakthrough_major(c)
                CharacterRepository.save(c)
            except Exception:
                pass
            # 判定式求值点 E3（§3.7）：与 on_breakthrough_major 同位追加
            try:
                from core.goals import evaluate_checked_goals

                if evaluate_checked_goals(c):
                    CharacterRepository.save(c)
            except Exception:
                pass
            # 命途求值 T2（二期 §3.6）：与 E3 同位（出口一）
            try:
                from core.fate_thread import FateThreadEngine as _FTEb

                if _FTEb.evaluate_for(c).get("changed"):
                    CharacterRepository.save(c)
            except Exception:
                pass
            try:
                from core.player_echo import record_player_breakthrough

                record_player_breakthrough(c, realm_name=c.realm.name)
            except Exception:
                pass
            # 传闻写入口（game-feel-phase2 §6）：大境界突破入池（出口①）
            try:
                from core import rumors as _rumors_mod

                _rumors_mod.note_breakthrough(c.name, c.realm.name, c.location)
            except Exception:
                pass
            # 大境界突破：尝试触发天道导演（仍受冷却）+ 惊动天道
            try:
                from core.world_director import WorldDirector, note_player_event

                note_player_event("breakthrough", character=c, location=c.location, detail=c.realm.name)
                WorldDirector.run_cycle(trigger="breakthrough", force=False)
            except Exception:
                pass
        _bt_settle = None
        if dead:
            _bt_settle = self._settle_if_needed(c, cause="渡劫陨落")
        # 天劫/突破双幕（game-feel-phase3 §5.2 出口①）：is_major 才演——
        # ceremony=天劫幕（第一幕），ceremony_next=突破幕（第二幕，只增
        # 键，builder 与 beats 不改）；致死时无第二幕。纯读拼装，任一
        # 拼装失败只缺该幕。
        _bt_ceremony = None
        _bt_ceremony_next = None
        if res.get("is_major"):
            try:
                from core.ceremony import build_tribulation_ceremony

                _bt_ceremony = build_tribulation_ceremony(c, res)
            except Exception:
                _bt_ceremony = None
            if not res.get("is_fatal"):
                try:
                    from core.ceremony import build_breakthrough_ceremony

                    _bt_ceremony_next = build_breakthrough_ceremony(
                        c, res,
                        fate_drawn=len(getattr(c, "fate_pending", None) or []) > _pend_before,
                    )
                except Exception:
                    _bt_ceremony_next = None
        return {
            "ok": True,
            "text": res.get("message", ""),
            "success": res.get("success"),
            "fatal": dead,
            "death": dead,
            "status": self._status_dict(c),
            "legacy": self.legacy_info_id(c.user_id) if dead else None,
            "sweep": (_bt_settle or {}).get("sweep") if _bt_settle else None,
            "death_cause": c.death_cause if dead else None,
            "ceremony": _bt_ceremony,
            "ceremony_next": _bt_ceremony_next,
        }

    def _fight(self, c: Character, target_name: str) -> Dict[str, Any]:
        from core.character_integrity import CharacterIntegrity, CharacterIntegrityError

        try:
            CharacterIntegrity.assert_alive(c)
            CharacterIntegrity.assert_idle(c, action="/斗法")
        except CharacterIntegrityError as error:
            return {"ok": False, "error": str(error)}
        target = CharacterRepository.get_by_name(target_name)
        if not target:
            return {"ok": False, "error": f"查无此人：{target_name}"}
        if target.id == c.id:
            return {"ok": False, "error": "不可自残"}
        if target.location != c.location:
            return {"ok": False, "error": f"目标不在【{c.location}】，先 /go 过去"}
        res = CombatFateEngine.resolve_ambush(c, target, use_ai=True, context="局域网斗法")
        if not res.get("success"):
            log_event("DECISION", "fight_blocked", attacker=c.name, target=target.name, reason=res.get("message"))
            return {"ok": False, "error": res.get("message", "无法动手")}
        log_event(
            "DECISION",
            "fight_resolved",
            attacker=c.name,
            target=target.name,
            outcome=res.get("outcome"),
            target_died=bool(res.get("target_died")),
        )
        CharacterRepository.save(c)
        CharacterRepository.save(target)
        spawned = res.get("spawned")
        if spawned:
            CharacterRepository.save(spawned)
        text = res.get("report") or res.get("narrative", "")
        if spawned:
            text += f"\n⚠【{spawned.name}】已入世于【{spawned.location}】"
        if res.get("target_died"):
            ChronicleRepository.record("KILL", c.name, f"【{c.name}】斩杀【{target.name}】")
            open_bounties = BountyRepository.list_open_for_target(target.id)
            if open_bounties:
                payment = BountyEngine.settle_on_kill(c, target, open_bounties)
                BountyRepository.save_many(open_bounties)
                CharacterRepository.save(c)
                if payment.get("message"):
                    text += "\n" + payment["message"]
        return {
            "ok": True,
            "text": text,
            "outcome": res.get("outcome"),
            "target_died": res.get("target_died"),
            "status": self._status_dict(c),
        }

    def _append_natural_omen(
        self,
        char: Character,
        payload: Dict[str, Any],
        context: str = "",
        in_chat_npc: Optional[Character] = None,
    ) -> Dict[str, Any]:
        """为日常行为结果追加自然奇遇检定"""
        try:
            if not payload.get("ok", True):
                return payload
            from core.omen_scene import maybe_trigger_natural_omen

            omen = maybe_trigger_natural_omen(char, context=context, in_chat_npc=in_chat_npc)
            if omen and omen.get("triggered"):
                if in_chat_npc:
                    payload["omen_chat"] = omen
                    payload["text"] = (payload.get("text") or "") + "\n\n" + (omen.get("text") or "")
                    # 交谈结构化（chat-structure §B-9）：弹窗内奇遇以 sys 行追加，
                    # 与 text 拼接同步，前端不再从 text 里拆奇遇段。
                    if isinstance(payload.get("chat_lines"), list):
                        payload["chat_lines"] = payload["chat_lines"] + [
                            _cl_sys(omen.get("text") or "")
                        ]
                else:
                    payload["omen_inline"] = bool(omen.get("omen_inline", True))
                    payload["omen_title"] = omen.get("omen_title") or omen.get("title")
                    payload["omen_choices"] = omen.get("omen_choices") or []
                    payload["omen_image"] = omen.get("omen_image", "")
                    payload["text"] = (payload.get("text") or "") + "\n\n" + (omen.get("text") or "")
                payload["status"] = self._status_dict(char)
        except Exception:
            pass
        return payload

    def _event(self, c: Character) -> Dict[str, Any]:
        from core.omen_scene import get_scene

        sc = get_scene(c.id)
        if sc:
            from core.omen_scene import _render, current_choices

            return {
                "ok": True,
                "text": _render(sc, c),
                "omen_open": True,
                "omen_inline": True,
                "omen_title": sc.get("title"),
                "omen_choices": current_choices(c.id),
                "status": self._status_dict(c),
            }
        return {
            "ok": True,
            "text": "【天机渺茫】机缘天定，不可强求……",
            "omen_open": False,
            "omen_inline": False,
            "status": self._status_dict(c),
        }

    def _bounty_board(self) -> str:
        board = BountyEngine.list_board(BountyRepository.list_all())
        if not board:
            return "告示栏空空如也。"
        lines = ["【坊市告示榜】"]
        for i, b in enumerate(board, 1):
            lines.append(f"{i}. 目标【{b.target_name}】 赏{b.reward} {bounty_status_cn(b.status)} 苦主:{b.issuer_display()}")
        return "\n".join(lines)

    def _market(self, c: Character) -> str:
        goods = MarketEngine.catalog(c.location)
        region = MarketEngine.region_of(c.location)
        lines = [
            f"【坊市 · {region}】金库 {c.vault_stones} | 随身 {c.spirit_stones}",
            "商会货单（当地市价，回收为市价五折）：",
        ]
        # F09：查看者宗门主导当地时注脚（货单价仍为市价单点，折扣只落成交）
        try:
            if c.sect and AtlasEngine.dominant_sect(region) == c.sect:
                lines.append(f"（本宗【{c.sect}】主导此地：向商会购货成交价九五折，货单为市价。）")
        except Exception:
            pass
        for g in goods:
            grade = f"·{g['grade']}" if g.get("grade") else ""
            slot = f"·{g['slot']}" if g.get("slot") else ""
            tag = ""
            if g.get("origin") == region:
                tag = " 【产地价】"
            elif g.get("origin") and (g.get("factor") or 1.0) > 1.001:
                tag = f"（产{g['origin']}，涨{(g['factor'] - 1.0) * 100:.0f}%）"
            elif g.get("origin"):
                tag = f"（产{g['origin']}）"
            lines.append(f"  · {g['name']}{grade}{slot}  {g['price']} 灵石{tag}  {g.get('desc','')}")
        lines.append("各地价差见 /行情：产地贱买、远方高价回收，即是跑商。")
        try:
            open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
            if open_l:
                lines.append("玩家寄售：")
                for i, l in enumerate(open_l, 1):
                    lines.append(f"  {i}. {l.item_name}  {l.price} 灵石  卖家:{l.seller_name}")
            else:
                lines.append("玩家寄售：（空）")
        except Exception:
            pass
        try:
            from core.trade import AuctionEngine

            # 坊市摘要是只读呈现：只推进排期/结算，不触发 NPC 跟价（react 触发点仅拍卖看板与世界 tick）
            board = AuctionEngine.board(react=False)
            lots = board.get("lots") or []
            if lots:
                lines.append("拍卖行：")
                for l in lots:
                    lines.append("  · " + l.board_line())
            else:
                lines.append("拍卖行：（空）")
        except Exception:
            pass
        lines.append(
            "通道：/购买 /出售 /服用 /寄存 /支取 | "
            "/寄售 /买寄售 /撤单 | /典当 /赎回 | "
            "/交易 <名> · /交易出 · /交易同意 · /交易拒绝 | "
            "/npc货单 /npc买 /npc卖 | "
            "/拍卖行 · /拍卖 · /上拍 · /拍 · /出价 · /一口 · /撤拍"
        )
        return "\n".join(lines)

    def _fmt_hd(self, res: Dict[str, Any]) -> str:
        return (
            f"【问心已定】{res.get('outcome')} · 天劫修正 {res.get('tribulation_mod',0):+.2f}\n"
            f"{res.get('narrative','')}\n落账：{res.get('effects_summary','')}"
        )


# 全局世界单例（服务器进程内）
WORLD = World(auto_tick=False)
