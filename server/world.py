"""
局域网权威世界：内存态 + 与 SQLite 角色同步
多玩家共用一界；所有写操作在此串行化
"""
from __future__ import annotations

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
from core.legacy import LegacyEngine
from core.here import list_here, format_here
from core.profile import build_profile, format_profile
from core.npc_proactive import NpcProactiveEngine
from core.bounty import BountyEngine, bounty_status_cn
from core.market import MarketEngine
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
from core.season import settle_apocalypse
from core import forge as forge_mod
from config import (
    WORLD_LOCATIONS,
    NPC_TICK_INTERVAL_SECONDS,
    LEGACY_BOOSTS,
    LEGACY_MAX_BOOSTS_PER_LIFE,
    BOUNTY_MAX_PER_TARGET,
    MARKET_MAX_LISTINGS,
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


class World:
    """进程内权威世界（局域网单服）"""

    def __init__(self, auto_tick: bool = True):
        init_db()
        self.lock = threading.RLock()
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
                with self.lock:
                    try:
                        from core.jianghu_sim import JianghuSimulator

                        JianghuSimulator.simulate_offline()
                    except Exception:
                        pass
                    NpcAgendaEngine.tick_world(max_npcs=3, force=False)
                    # 天道导演：AI 主导走向（冷却在 run_cycle 内）
                    try:
                        from core.world_director import WorldDirector

                        WorldDirector.run_cycle(trigger="timer", force=False)
                    except Exception:
                        pass
                    # M2 世界弧推进
                    try:
                        from core import world_arc

                        world_arc.tick_world(max_advance=2)
                    except Exception:
                        pass
                    # M3 势力：关系衰减 + 自动令/围剿
                    try:
                        from core import faction

                        faction.tick_world()
                    except Exception:
                        pass
                    # M4：玩家回写衰减
                    try:
                        from core import player_echo

                        player_echo.decay_echoes()
                    except Exception:
                        pass
                    # M5：纪元回流 tick
                    try:
                        from core import era_reentry

                        era_reentry.tick()
                    except Exception:
                        pass
            except Exception:
                continue

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
    def join(self, name: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            uid = (user_id or "").strip()
            char = None
            resumed = False
            # 1) 浏览器账号 ID
            if uid:
                char = CharacterRepository.get_by_user_id(uid)
            # 2) 按道号找回仍存活的玩家号（换设备/清缓存）
            if (not char or char.status == CharacterStatus.DEAD or char.lifespan.is_dead()):
                by_name = CharacterRepository.get_by_name(name)
                if by_name and by_name.status != CharacterStatus.DEAD and not by_name.lifespan.is_dead():
                    uid_n = str(by_name.user_id or "")
                    if uid_n and not (uid_n.startswith("npc_") or uid_n.startswith("ai_npc_")):
                        char = by_name
                        uid = uid_n
                        resumed = True
            is_new_life = False
            if not char or char.status == CharacterStatus.DEAD or char.lifespan.is_dead():
                # 已死：结算道统（若尚未结算），再新一世
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
            newbie_feed = ""
            first_night = None
            try:
                from core.tasks import ensure_tasks, format_task_board

                ensure_tasks(char)
            except Exception:
                pass
            if is_new_life:
                newbie_feed = (
                    "【初入道】打开 /任务：十步学会说话、买卖、迁跃、修炼与观照天道；"
                    "每步有赏。也可直接 /天道 /世情。新手庇护 72 小时。"
                )
                # 第一晚爽点：天道有感 + 同场有人 + 一件小结果
                try:
                    from core.world_director import WorldDirector
                    from core.npc_proactive import NpcProactiveEngine

                    seed_roster()
                    dres = WorldDirector.run_cycle(trigger="command", force=True)
                    pro = NpcProactiveEngine.maybe_engage(char, force=True)
                    pro_item = {}
                    if isinstance(pro, list) and pro:
                        pro_item = pro[0] or {}
                    elif isinstance(pro, dict):
                        pro_item = pro
                    first_night = {
                        "director": {
                            "ok": bool(dres.get("ok")),
                            "count": dres.get("count") or 0,
                            "hint": dres.get("brief_hint") or "",
                            "source": dres.get("source") or "",
                            "text": dres.get("brief_hint") or "",
                        },
                        "proactive": pro_item,
                    }
                    if pro_item.get("text"):
                        newbie_feed += "\n【同场】" + str(pro_item.get("text"))[:120]
                    if dres.get("ok") and dres.get("brief_hint"):
                        newbie_feed += f"\n【天道】{dres.get('brief_hint')}"
                except Exception as _fn_ex:
                    first_night = {"error": str(_fn_ex)[:80]}
            token = uuid.uuid4().hex
            self.sessions[token] = Session(token, uid, char.id)
            try:
                AuthSessionRepository.save(token, uid, char.id, char.name)
            except Exception:
                pass
            account = LegacyRepository.get_or_create(uid)
            return {
                "token": token,
                "user_id": uid,
                "character_id": char.id,
                "name": char.name,
                "realm": char.realm.name,
                "location": char.location,
                "rem_years": round(char.lifespan.get_remaining_years(), 2),
                "legacy_points": account.points,
                "lives": account.total_lives,
                "newbie_feed": newbie_feed,
                "first_night": first_night,
                "is_new_life": is_new_life,
                "resumed": resumed and not is_new_life,
            }

    def _settle_if_needed(self, char: Character, cause: str = "身死道消") -> Optional[Dict[str, Any]]:
        """死亡后一次性道统结算"""
        if getattr(char, "death_settled", False):
            return None
        account = LegacyRepository.get_or_create(char.user_id)
        char.status = CharacterStatus.DEAD
        if not char.death_cause:
            char.death_cause = cause
        settle = LegacyEngine.settle_death(account, char, death_cause=char.death_cause or cause)
        LegacyRepository.save(account)
        CharacterRepository.save(char)
        ChronicleRepository.record(
            "LEGACY_SETTLE", char.name,
            f"【{char.name}】{char.death_cause}，结转道统 {settle['points_gained']} 点。",
        )
        return settle

    def legacy_info(self, token: str) -> Dict[str, Any]:
        char = self.get_char(token)
        if not char:
            return {"ok": False, "error": "会话无效"}
        account = LegacyRepository.get_or_create(char.user_id)
        boosts = []
        for k, cfg in LEGACY_BOOSTS.items():
            boosts.append({"key": k, "name": cfg["name"], "cost": cfg["cost"], "desc": cfg["desc"]})
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
            "boosts": boosts,
            "max_boosts": LEGACY_MAX_BOOSTS_PER_LIFE,
            "alive": char.status != CharacterStatus.DEAD and not char.lifespan.is_dead(),
            "death_cause": char.death_cause,
        }

    def reincarnate(self, token: str, name: Optional[str] = None, boosts: Optional[List[str]] = None) -> Dict[str, Any]:
        """转世：结算（若需）→ 新一世 → 消费道统点"""
        with self.lock:
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

            char = WorldClock.create_new_character(session.user_id, new_name)
            boost_res = LegacyEngine.apply_birth_boosts(char, account, list(boosts or []))
            LegacyRepository.save(account)
            CharacterRepository.save(char)
            session.character_id = char.id
            ChronicleRepository.record(
                "REINCARNATE", char.name,
                f"真灵转世，【{char.name}】重踏仙途。"
                + (f"道统点化：{'、'.join(boost_res.get('applied') or [])}。" if boost_res.get("applied") else ""),
            )
            return {
                "ok": True,
                "text": (
                    f"【真灵转世】{char.name} · {char.realm.name} · {char.location}\n"
                    f"自然寿元 {char.lifespan.birth_base:.0f} 岁\n"
                    f"{boost_res.get('message', '')}\n"
                    f"道统池剩余 {account.points} 点（第 {account.total_lives + 1} 世）"
                ),
                "settle": {
                    "points_gained": (settle or {}).get("points_gained", 0),
                    "cause": (settle or {}).get("cause", ""),
                    "past_life": ((settle or {}).get("past_life") or {}).model_dump()
                    if (settle or {}).get("past_life") else None,
                } if settle else None,
                "boosts_applied": boost_res.get("applied") or [],
                "legacy_points": account.points,
                "name": char.name,
                "realm": char.realm.name,
                "location": char.location,
                "rem_years": round(char.lifespan.get_remaining_years(), 2),
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
        with self.lock:
            char = self.get_char(token)
            if not char:
                return {"ok": False, "error": "会话无效，请重新 /join"}
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
                    # 心魔致死
                    if res.get("is_fatal") or char.status == CharacterStatus.DEAD:
                        self._settle_if_needed(char, cause="心魔道消")
                        return {
                            "ok": True,
                            "text": text,
                            "heart_demon": res,
                            "death": True,
                            "status": self._status_dict(char),
                            "legacy": self.legacy_info_id(char.user_id),
                        }
                    # 心魔过关且未死 → 继续天劫
                    if not res.get("is_fatal") and char.realm.is_full and char.status != CharacterStatus.DEAD:
                        tmod = float(res.get("tribulation_mod") or 0.0)
                        trib = BreakthroughEngine.attempt_breakthrough(char, use_pill=False, heart_mod=tmod)
                        CharacterRepository.save(char)
                        text += "\n\n" + trib.get("message", "")
                        trib_dead = bool(trib.get("is_fatal"))
                        if trib.get("success") and trib.get("is_major"):
                            try:
                                GoalEngine.on_breakthrough_major(char)
                            except Exception:
                                pass
                        if trib_dead:
                            self._settle_if_needed(char, cause="渡劫陨落")
                        return {
                            "ok": True,
                            "text": text,
                            "heart_demon": res,
                            "death": trib_dead,
                            "status": self._status_dict(char),
                            "legacy": self.legacy_info_id(char.user_id) if trib_dead else None,
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
                    "/agenda", "/议程",
                    "/roster", "/名录",
                    "/bounty", "/告示",
                    "/profile", "/人物", "/角色",
                    "/logout", "/下线",
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
            if action in ("/legacy", "/道统"):
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
                info["text"] = "\n".join(lines)
                return info
            if action in ("/reborn", "/转世"):
                boosts: List[str] = []
                new_name = None
                # /转世 [道号] [boost...]
                rest = parts[1:]
                for tok in rest:
                    if tok in LEGACY_BOOSTS:
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
                return {"ok": True, "text": self._who()}
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
                return {"ok": True, "text": season_status_text(), "season": season_info()}
            if action in ("/rumors", "/传闻"):
                from core.rumors import format_rumor_board

                n = 8
                if len(parts) > 1 and parts[1].isdigit():
                    n = max(1, min(20, int(parts[1])))
                return {"ok": True, "text": format_rumor_board(n)}
            if action in ("/channel", "/频道"):
                from core.world_channel import WorldChannel

                n = 15
                if len(parts) > 1 and parts[1].isdigit():
                    n = max(1, min(40, int(parts[1])))
                return {"ok": True, "text": WorldChannel.format_board(n)}
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
                return {"ok": True, "text": format_board(n)}
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
            if action in ("/omen", "/奇遇"):
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
                        "status": self._status_dict(char),
                    }
                # 选项
                if sub.isdigit():
                    res = omen_choose(char, sub)
                    return {
                        "ok": res.get("success"),
                        "text": res.get("message", ""),
                        "omen_open": bool(get_scene(char.id)),
                        "omen_ended": bool(res.get("ended")),
                        "omen_status": res.get("omen_status"),
                        "status": self._status_dict(char),
                    }
                # 有进行中则渲染
                sc = get_scene(char.id)
                if sc:
                    from core.omen_scene import _render

                    return {
                        "ok": True,
                        "text": _render(sc, char),
                        "omen_open": True,
                        "omen_title": sc.get("title"),
                        "status": self._status_dict(char),
                    }
                # 无则尝试新开（保持旧：也可先跑 EventChain）
                res = start_scene(char)
                if not res.get("success"):
                    # 退回旧链逻辑
                    from core.event_chains import EventChainEngine

                    if not EventChainEngine.active_for(char.id):
                        ch = EventChainEngine.maybe_start(char, trigger="force", force=True)
                        if ch:
                            CharacterRepository.save(char)
                            st = ch.steps[0]
                            opts = " | ".join(f"{x['id']}.{x['label']}" for x in st["choices"])
                            return {
                                "ok": True,
                                "text": (
                                    f"【奇遇 · {ch.title}】{st['prompt']}\n"
                                    f"选项：{opts}\n（/奇遇 <n> 推进）"
                                ),
                                "omen_open": True,
                                "status": self._status_dict(char),
                            }
                    ev = EventEngine.fire(char, force=True, context="主动推演")
                    if not ev:
                        return {"ok": True, "text": "天机混沌，无事发生。", "status": self._status_dict(char)}
                    CharacterRepository.save(char)
                    return {
                        "ok": True,
                        "text": f"【{ev['title']}】\n{ev['narrative']}\n落账：{ev['effects_summary']}",
                        "status": self._status_dict(char),
                    }
                CharacterRepository.save(char)
                return {
                    "ok": True,
                    "text": res.get("message", ""),
                    "omen_open": True,
                    "omen_title": res.get("scene", {}).get("title"),
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
                return {
                    "ok": res.get("success"),
                    "text": res.get("message", ""),
                    "omen_open": not bool(res.get("ended")),
                    "omen_ended": bool(res.get("ended")),
                    "omen_status": res.get("omen_status"),
                    "intent": res.get("intent"),
                    "status": self._status_dict(char),
                }
            if action in ("/legend", "/传说", "/典籍"):
                from core.legends import format_legends
                from core.era_reentry import format_era_board

                season = None
                if len(parts) > 1 and parts[1].lstrip("-").isdigit():
                    season = int(parts[1])
                text = format_legends(season=season)
                try:
                    text += "\n\n" + format_era_board()
                except Exception:
                    pass
                return {"ok": True, "text": text}
            if action in ("/links", "/关系"):
                from core.collusion import format_links
                from storage.db import CharacterRepository as CR

                if len(parts) < 2:
                    return {"ok": True, "text": format_links(char)}
                target = CR.find_alive_by_name("".join(parts[1:]))
                if not target:
                    return {"ok": False, "error": f"未寻得【{''.join(parts[1:])}】"}
                return {"ok": True, "text": format_links(target)}
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
            if action in ("/dig", "/挖宝"):
                res = DigEngine.dig(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("DECISION", "dig", name=char.name, outcome=res.get("outcome"))
                return {"ok": res.get("success"), "text": res.get("message", ""), "status": self._status_dict(char)}
            if action in ("/equip", "/穿戴"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/穿戴 <装备名>"}
                item = command.strip().split(None, 1)[1]
                res = EquipEngine.equip(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/unequip", "/卸下"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/卸下 <装备名>"}
                item = command.strip().split(None, 1)[1]
                res = EquipEngine.unequip(char, item.strip())
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/rank", "/榜单", "/榜"):
                board = parts[1] if len(parts) > 1 else ""
                if not board:
                    return {"ok": True, "text": LeaderboardEngine.format_all(5)}
                alias = {
                    "境界": "realm", "战力": "power", "凶名": "notoriety",
                    "道行": "daohang", "传奇": "fame", "资产": "assets",
                    "realm": "realm", "power": "power", "sin": "notoriety",
                    "dao": "daohang", "fame": "fame", "assets": "assets",
                }
                key = alias.get(board, board)
                return {"ok": True, "text": LeaderboardEngine.format_board(key), "board": key}
            if action in ("/sect", "/宗门"):
                return {"ok": True, "text": format_sect_board(char)}
            if action in ("/join_sect", "/拜入"):
                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/拜入 <宗门>（须亲至总坛山门）"}
                res = join_sect(char, parts[1])
                if res.get("success"):
                    CharacterRepository.save(char)
                    log_event("DECISION", "join_sect", name=char.name, sect=res.get("sect"))
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/leave_sect", "/叛门"):
                res = leave_sect(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/salary", "/领俸禄", "/俸禄"):
                res = claim_salary(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/promote", "/晋升"):
                res = promote(char)
                if res.get("success"):
                    CharacterRepository.save(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
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
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/adventure", "/探险"):
                target = ""
                if len(parts) > 1:
                    target = command.strip().split(None, 1)[1].strip()
                if not target:
                    return {"ok": True, "text": AdventureEngine.board_text(char)}
                res = AdventureEngine.explore(char, target)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "探险失败")}
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
                return {
                    "ok": True,
                    "text": res.get("message", ""),
                    "adventure": res,
                    "status": self._status_dict(char),
                }
            if action in ("/配方", "/recipes"):
                from core.alchemy import format_book

                return {"ok": True, "text": format_book(char)}
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
                    if res.get("success"):
                        CharacterRepository.save(char)
                        try:
                            GoalEngine.add_opportunity(
                                char, res["chain"]["title"], "秘境探索进行中，/秘境 推进。"
                            )
                            CharacterRepository.save(char)
                        except Exception:
                            pass
                    return {"ok": res.get("success"), "text": res.get("message", "")}
                return {"ok": True, "text": SecretRealmEngine.board_text()}
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
                from core.world_director import handle_heaven_command
                from core.tasks import hook_note

                res = handle_heaven_command(action, parts)
                n = hook_note(char, "look_board")
                if n:
                    res["text"] = n + "\n" + (res.get("text") or "")
                return res
            if action in ("/世界弧", "/arc", "/弧"):
                from core.world_arc import handle_arc_command

                return handle_arc_command(parts)
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
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/交师门",):
                from core.social_bonds import submit_master_task

                res = submit_master_task(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/结义任务",):
                from core.social_bonds import format_sworn_task

                res = format_sworn_task(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/交结义",):
                from core.social_bonds import submit_sworn_task

                res = submit_sworn_task(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}

            # ---------------- Wave2：宗门贡献 ----------------
            if action in ("/贡献",):
                return {
                    "ok": True,
                    "text": (
                        f"【宗门贡献】{char.sect or '散修'} · {char.sect_contribution}\n"
                        + ("可 /上交 <货> · /兑换 · /宗门环" if char.sect else "先 /拜入 <宗门>")
                    ),
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
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/兑换",):
                from core.sect_contrib import format_shop, exchange

                if len(parts) < 2:
                    return {"ok": True, "text": format_shop() + f"\n当前贡献：{char.sect_contribution}"}
                res = exchange(char, "".join(parts[1:]))
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/宗门环", "/sectring"):
                from core.sect_contrib import format_ring

                return {"ok": True, "text": format_ring(char)}
            if action in ("/接宗门环", "/accepring"):
                from core.sect_contrib import accept_theme

                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/接宗门环 <1|2|3>"}
                res = accept_theme(char, int(parts[1]))
                if res.get("success") and res.get("hook") == "hunt":
                    pass
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/宗门势", "/sectpower"):
                from core.sect_contrib import sect_powerboard

                return {"ok": True, "text": sect_powerboard()}
            if action in ("/势力", "/faction"):
                from core.faction import handle_faction_command, format_faction_board

                return handle_faction_command(parts, char)
            if action in ("/望气", "/echo", "/天象"):
                from core.player_echo import handle_echo_command
                from core.tasks import hook_note

                res = handle_echo_command(parts, char)
                n = hook_note(char, "look_echo")
                if n:
                    res["text"] = n + "\n" + (res.get("text") or "")
                return res
            if action in ("/纪元回流", "/era", "/史笔回流"):
                from core.era_reentry import handle_era_command

                return handle_era_command(parts)
            if action in ("/宗门令", "/sectorder", "/势力令"):
                from core.faction import handle_faction_command

                return handle_faction_command(["/势力", "令"], char)
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

            # ---------------- Wave2：除凶 ----------------
            if action in ("/除凶", "/hunt"):
                from core.hunt import format_board, my_target

                t = my_target(char)
                extra = f"\n你接的令：【{t.name}】@ {t.location}" if t else "\n你未接令。"
                return {"ok": True, "text": format_board() + extra}
            if action in ("/接除凶",):
                from core.hunt import accept

                if len(parts) < 2:
                    return {"ok": False, "error": "用法：/接除凶 <道号>"}
                res = accept(char, "".join(parts[1:]))
                if res.get("success"):
                    try:
                        from core.sect_contrib import sync_ring

                        sync_ring(char, "hunt")
                    except Exception:
                        pass
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/弃除凶",):
                from core.hunt import abandon

                res = abandon(char)
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
                    greet = (
                        f"【会话开始】与【{target.name}】交谈中。\n"
                        f"用 /说 <内容> 继续，/挂断 结束；聊天窗可直接打字。"
                    )
                    if words:
                        res = NpcDialogueEngine.talk(target, char, words)
                        log_event("DECISION", "talk", name=char.name, target=target.name, words_len=len(words), source=res.get("source"))
                        if not res.get("ok"):
                            return {"ok": False, "error": res.get("error", "无法交谈")}
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
                            "chat_open": True,
                            "npc": target.name,
                            "attitude": res.get("attitude"),
                            "source": res.get("source"),
                            "bystanders": res.get("bystanders") or [],
                        }
                    return {
                        "ok": True,
                        "text": greet + "\n\n（可开口：直接在聊天窗打字，无需 /说）",
                        "chat_open": True,
                        "npc": target.name,
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
                        return {"ok": False, "error": rej["message"], "rejected": True, "chat_open": True}
                except Exception:
                    pass
                said = npc_chat.player_say(char, words)
                if not said.get("success"):
                    return {"ok": False, "error": said.get("message", "无法发言"), "chat_ended": said.get("ended")}
                rec = said["session"]
                npc = said["npc"]
                # 会话中若离地/死亡/被擒则终止
                if npc.location != char.location or npc.status == CharacterStatus.DEAD:
                    npc_chat.close_session(char.id, "对方已不在同场，会话终止。", by="system")
                    return {"ok": False, "error": "对方已不在同场，会话终止。", "chat_ended": True}
                if npc.status == CharacterStatus.CAPTURED:
                    npc_chat.close_session(char.id, f"【{npc.name}】已被擒。", by="system")
                    return {"ok": False, "error": f"【{npc.name}】已被擒，会话终止。", "chat_ended": True}

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
                                "chat_open": False,
                                "chat_ended": True,
                                "npc": npc.name,
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
                            "chat_open": True,
                            "chat_ended": False,
                            "npc": npc.name,
                            "action": act.get("action") or "action",
                        }
                    # 动作被规则拒绝：会话仍开，展示原因
                    return {
                        "ok": False,
                        "error": act.get("error", "无法完成该动作"),
                        "chat_open": True,
                        "chat_ended": False,
                        "npc": npc.name,
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
                        banter_text = "\n" + format_banter(banter_list)
                        if not out.get("ended"):
                            append_banter_to_session(char.id, banter_list)
                except Exception:
                    banter_text = ""
                log_event("DECISION", "chat", name=char.name, target=npc.name, source=source, ended=bool(out.get("ended")))
                return {
                    "ok": True,
                    "text": (out.get("message", line) or "") + banter_text,
                    "chat_open": not out.get("ended"),
                    "chat_ended": bool(out.get("ended")),
                    "npc": npc.name,
                    "source": source,
                    "bystanders": banter_list,
                }
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
                return {"ok": True, "text": text, "chat_ended": True, "npc": rec.get("npc_name")}
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
                return {"ok": True, "text": self._bounty_board()}
            if action in ("/market", "/坊市"):
                return {"ok": True, "text": self._market(char)}
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
                return {"ok": res.get("success"), "text": res.get("message", "")}
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
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/deposit", "/寄存"):
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/寄存 <数量>"}
                res = MarketEngine.deposit_stones(char, int(parts[1]))
                CharacterRepository.save(char)
                return {"ok": res["success"], "text": res["message"]}
            if action in ("/withdraw", "/支取"):
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/支取 <灵石数量>"}
                res = MarketEngine.withdraw_stones(char, int(parts[1]))
                if res["success"]:
                    CharacterRepository.save(char)
                return {"ok": res["success"], "text": res["message"]}
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
            if action in ("/list_item", "/寄售"):
                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/寄售 <货物名> <价格>"}
                try:
                    price = int(parts[-1])
                except ValueError:
                    return {"ok": False, "error": "价格必须是整数灵石"}
                item_name = "".join(parts[1:-1]) if len(parts) > 3 else parts[1]
                # 支持带空格货名：去掉末尾价格后拼回
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
                if len(my_open) >= MARKET_MAX_LISTINGS:
                    return {"ok": False, "error": f"寄售栏已满（上限 {MARKET_MAX_LISTINGS}），请先 /撤单"}
                listing, res = MarketEngine.list_item(char, item_name, price)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "寄售失败")}
                MarketListingRepository.save(listing)
                CharacterRepository.save(char)
                ChronicleRepository.record(
                    "MARKET", char.name, f"【{char.name}】寄售【{item_name}】标价 {price} 灵石。"
                )
                return {"ok": True, "text": res["message"]}
            if action in ("/buy_listing", "/买寄售"):
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/买寄售 <编号>（先 /坊市）"}
                open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(open_l):
                    return {"ok": False, "error": "寄售编号不存在"}
                listing = open_l[idx]
                res = MarketEngine.buy_listing(char, listing)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "购买失败")}
                seller = CharacterRepository.get_by_name(listing.seller_name)
                MarketEngine.complete_sale_payment(listing, seller)
                MarketListingRepository.save(listing)
                CharacterRepository.save(char)
                if seller:
                    CharacterRepository.save(seller)
                ChronicleRepository.record(
                    "MARKET_BUY",
                    char.name,
                    f"【{char.name}】购得寄售【{listing.item_name}】，付 {listing.price} 灵石。",
                )
                return {"ok": True, "text": res["message"]}
            if action in ("/cancel_listing", "/撤单"):
                if len(parts) < 2 or not parts[1].isdigit():
                    return {"ok": False, "error": "用法：/撤单 <编号>"}
                open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(open_l):
                    return {"ok": False, "error": "寄售编号不存在"}
                listing = open_l[idx]
                res = MarketEngine.cancel_listing(char, listing)
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "撤单失败")}
                MarketListingRepository.save(listing)
                CharacterRepository.save(char)
                return {"ok": True, "text": res["message"]}

            # ---------------- 当面交易 ----------------
            if action in ("/trade", "/交易") and len(parts) >= 2:
                from core.trade import TradeEngine

                res = TradeEngine.open_trade(char, "".join(parts[1:]))
                if not res.get("success"):
                    return {"ok": False, "error": res.get("message", "无法发起交易")}
                return {"ok": True, "text": res["message"]}
            if action in ("/trade", "/交易"):
                from core.trade import TradeEngine

                res = TradeEngine.view(char)
                return {"ok": res.get("success"), "text": res.get("message", "")}
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
                return {"ok": res.get("success"), "text": res.get("message", "")}
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
            if action in ("/auction", "/拍卖行"):
                from core.trade import AuctionEngine

                res = AuctionEngine.board()
                return {"ok": True, "text": res["message"]}
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
                return {"ok": res.get("success"), "text": res.get("message", "")}
            if action in ("/bid", "/拍"):
                from core.trade import AuctionEngine

                if len(parts) < 3:
                    return {"ok": False, "error": "用法：/拍 <编号> <出价>"}
                try:
                    amount = int(parts[2])
                except ValueError:
                    return {"ok": False, "error": "出价须为整数"}
                res = AuctionEngine.bid(char, parts[1], amount)
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
            if action in ("/do", "/做", "/言行"):
                raw = command.strip().split(" ", 1)
                if len(raw) < 2:
                    return {"ok": False, "error": "用法：/做 <言行>"}
                # 玩家不得口述造物（自创功法除外）
                try:
                    from core.name_guard import reject_player_creation

                    rej = reject_player_creation(raw[1])
                    if rej:
                        log_event("GATE", "name_creation_rejected", name=char.name, sample=str(rej.get("hits"))[:80])
                        return {"ok": False, "error": rej["message"], "rejected": True}
                except Exception:
                    pass
                others = self.others_at(char)
                res = FreeActionEngine.resolve(char, raw[1], others=others)
                if not res.get("ok"):
                    return {"ok": False, "error": res.get("error", "无果")}
                CharacterRepository.save(char)
                spawned = res.get("spawned")
                if spawned:
                    CharacterRepository.save(spawned)
                return {
                    "ok": True,
                    "text": res.get("text", ""),
                    "intent": res.get("intent"),
                    "outcome": res.get("outcome"),
                    "spawned": bool(spawned),
                }
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
            "/坊市 /购买 /出售 /服用 /寄存 /支取 /寄售 /买寄售 /撤单 "
            "/交易 <名> /交易出 /交易同意 /交易拒绝 /npc货单 /npc买 /npc卖 "
            "/拍卖行 /上拍 /拍 /一口 /撤拍 "
            "/归隐 [h] /出隐 /下线 /目标 /灵气 /纪元 /探险 [野外|秘境] "
            "/榜 /宗门 /拜入 /叛门 /领俸禄 /晋升 /传功 /秘境 /帮助 "
            "/传闻 /关系 /频道 /公告 /gm /奇遇 /传说 /纪元回流 /拍卖行 "
            "/拜师 /收徒 /出师 /结拜 /结拜同意 /绝交 /叛师 /师门任务 /交师门 /结义任务 /交结义 "
            "/贡献 /上交 /兑换 /宗门环 /接宗门环 /宗门势 /势力 /宗门令 /接宗门令 /交宗门令 /望气 /除凶 /接除凶 /弃除凶 /反悬赏 /围剿 /世情 /追 "
            "/配方 /炼丹 /炼器 /悟丹 /悟器 /说 /挂断 /会话 /释放 /名物 /追查 /近况 /目标 /关系 /因果(回访) "
            "/任务 /目标 /天道 /世情 /望气"
        )

    def _status_dict(self, c: Character) -> Dict[str, Any]:
        import time as _t
        prot = c.is_newbie_protected()
        prot_left = 0.0
        if prot:
            prot_left = max(0.0, c.newbie_protect_until() - _t.time())
        return {
            "name": c.name,
            "realm": c.realm.name,
            "location": c.location,
            "stones": c.spirit_stones,
            "vault": c.vault_stones,
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
            "meditating": c.status == CharacterStatus.MEDITATING,
            "sect": c.sect or "",
            "rank": c.sect_rank or "",
            "newbie_protected": prot,
            "newbie_left_hours": round(prot_left / 3600.0, 1) if prot else 0,
            "protect": ProtectionEngine.status_text(c),
            "conflict_zone": is_conflict_zone(c.location),
            "qi_mult": round(qi_mod.global_qi_multiplier(), 3),
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

    def _go(self, c: Character, dest: str) -> Dict[str, Any]:
        if c.status == CharacterStatus.CAPTURED:
            return {"ok": False, "error": "你已被擒，动弹不得。待对方 /释放 或自救。"}
        matched = None
        for loc in WORLD_LOCATIONS:
            if dest and dest in loc:
                matched = loc
                break
        if not matched:
            return {"ok": False, "error": f"未知地点：{dest}"}
        c.location = matched
        CharacterRepository.save(c)
        text = f"御剑化虹，抵达【{matched}】。"
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
        return {"ok": True, "text": text, "status": self._status_dict(c)}

    def _meditate(self, c: Character, hours: float) -> Dict[str, Any]:
        res = WorldClock.start_meditation(c, hours, 0)
        if res["success"]:
            CharacterRepository.save(c)
        return {"ok": res["success"], "text": res["message"]}

    def _emerge(self, c: Character) -> Dict[str, Any]:
        if c.status != CharacterStatus.MEDITATING:
            return {"ok": False, "text": "未在闭关。"}
        res = WorldClock.settle_meditation(c, force_interrupt=True)
        CharacterRepository.save(c)
        lines = [
            f"出关：闭关 {res.get('actual_real_hours',0):.1f}h，"
            f"修为+{res.get('exp_gained',0)}，寿元余 {res.get('after_years',0):.1f}"
        ]
        dead = False
        if res.get("is_fatal"):
            c.status = CharacterStatus.DEAD
            CharacterRepository.save(c)
            lines.append("寿尽坐化。")
            dead = True
            self._settle_if_needed(c, cause="洞府坐化")
        return {
            "ok": True,
            "text": "\n".join(lines),
            "death": dead,
            "status": self._status_dict(c),
            "legacy": self.legacy_info_id(c.user_id) if dead else None,
        }

    def legacy_info_id(self, user_id: str) -> Dict[str, Any]:
        account = LegacyRepository.get_or_create(user_id)
        boosts = [
            {"key": k, "name": cfg["name"], "cost": cfg["cost"], "desc": cfg["desc"]}
            for k, cfg in LEGACY_BOOSTS.items()
        ]
        return {
            "points": account.points,
            "lives": account.total_lives,
            "boosts": boosts,
            "max_boosts": LEGACY_MAX_BOOSTS_PER_LIFE,
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

        res = BreakthroughEngine.attempt_breakthrough(c, use_pill=False, heart_mod=heart_mod)
        CharacterRepository.save(c)
        dead = bool(res.get("is_fatal"))
        if res.get("success") and res.get("is_major"):
            try:
                GoalEngine.on_breakthrough_major(c)
                CharacterRepository.save(c)
            except Exception:
                pass
            try:
                from core.player_echo import record_player_breakthrough

                record_player_breakthrough(c, realm_name=c.realm.name)
            except Exception:
                pass
            # 大境界突破：尝试触发天道导演（仍受冷却）+ 惊动天道
            try:
                from core.world_director import WorldDirector, note_player_event

                note_player_event("breakthrough", character=c, location=c.location, detail=c.realm.name)
                WorldDirector.run_cycle(trigger="breakthrough", force=False)
            except Exception:
                pass
        if dead:
            self._settle_if_needed(c, cause="渡劫陨落")
        return {
            "ok": True,
            "text": res.get("message", ""),
            "success": res.get("success"),
            "fatal": dead,
            "death": dead,
            "status": self._status_dict(c),
            "legacy": self.legacy_info_id(c.user_id) if dead else None,
        }

    def _fight(self, c: Character, target_name: str) -> Dict[str, Any]:
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
        return {"ok": True, "text": text, "outcome": res.get("outcome"), "target_died": res.get("target_died")}

    def _event(self, c: Character) -> Dict[str, Any]:
        # 优先尝试通用奇遇链（force）；已有链则走旧单发事件
        try:
            from core.event_chains import EventChainEngine

            if not EventChainEngine.active_for(c.id):
                ch = EventChainEngine.maybe_start(c, trigger="force", force=True)
                if ch:
                    CharacterRepository.save(c)
                    st = ch.steps[0]
                    opts = " | ".join(f"{x['id']}.{x['label']}" for x in st["choices"])
                    return {
                        "ok": True,
                        "text": (
                            f"【奇遇 · {ch.title}】{st['prompt']}\n"
                            f"选项：{opts}\n（/奇遇 <n> 推进）"
                        ),
                        "omen": ch.model_dump(),
                    }
        except Exception:
            pass
        ev = EventEngine.fire(c, force=True, context="主动推演")
        if not ev:
            return {"ok": True, "text": "天机混沌，无事发生。"}
        CharacterRepository.save(c)
        return {
            "ok": True,
            "text": f"【{ev['title']}】\n{ev['narrative']}\n落账：{ev['effects_summary']}",
            "event": ev,
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
        goods = MarketEngine.catalog()
        lines = [
            f"【坊市】金库 {c.vault_stones} | 随身 {c.spirit_stones}",
            "商会货单：",
        ]
        for g in goods:
            grade = f"·{g['grade']}" if g.get("grade") else ""
            slot = f"·{g['slot']}" if g.get("slot") else ""
            lines.append(f"  · {g['name']}{grade}{slot}  {g['price']} 灵石  {g.get('desc','')}")
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

            board = AuctionEngine.board()
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
            "/寄售 /买寄售 /撤单 | "
            "/交易 <名> · /交易出 · /交易同意 · /交易拒绝 | "
            "/npc货单 /npc买 /npc卖 | "
            "/拍卖行 · /上拍 · /拍 · /一口 · /撤拍"
        )
        return "\n".join(lines)

    def _fmt_hd(self, res: Dict[str, Any]) -> str:
        return (
            f"【问心已定】{res.get('outcome')} · 天劫修正 {res.get('tribulation_mod',0):+.2f}\n"
            f"{res.get('narrative','')}\n落账：{res.get('effects_summary','')}"
        )


# 全局世界单例（服务器进程内）
WORLD = World(auto_tick=False)
