"""
秘境与事件链：限时开启 → 探索步进 → 机缘/杀劫落账
可接可拒；拒绝/错过不惩罚。
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any, Dict, List, Optional

from config import SECRET_REALMS, EVENT_CHAIN_MAX_STEPS, WORLD_LOCATIONS
from core.models import Character, CharacterStatus
from core.events import EventEngine
from core.qi import global_qi_multiplier
from storage.db import WorldStateRepository

# 进程内缓存；权威在 world_state（重启不失忆）
_REALM_TS_KEY = "secret_realm_open_ts"
_CHAINS_KEY = "secret_realm_chains"
_loaded = False

# 进程内秘境开启记录（realm_id -> last_open_ts）
_realm_open_ts: Dict[str, float] = {}
# 进行中的探索链 character_id -> chain dict
_active_chains: Dict[str, Dict[str, Any]] = {}


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    try:
        _realm_open_ts.update(WorldStateRepository.get(_REALM_TS_KEY, {}) or {})
        _active_chains.update(WorldStateRepository.get(_CHAINS_KEY, {}) or {})
    except Exception:
        pass
    _loaded = True


def _persist_realm_ts() -> None:
    try:
        WorldStateRepository.set(_REALM_TS_KEY, dict(_realm_open_ts))
    except Exception:
        pass


def _persist_chains() -> None:
    try:
        WorldStateRepository.set(_CHAINS_KEY, dict(_active_chains))
    except Exception:
        pass


def realm_status(now: Optional[float] = None) -> List[Dict[str, Any]]:
    _ensure_loaded()
    t = now if now is not None else time.time()
    rows = []
    for rid, cfg in SECRET_REALMS.items():
        last = _realm_open_ts.get(rid, 0.0)
        interval = cfg.get("open_interval_hours", 6.0) * 3600.0
        is_open = (t - last) >= interval
        remain = 0.0 if is_open else (interval - (t - last)) / 3600.0
        rows.append(
            {
                "id": rid,
                "name": rid,
                "location": cfg.get("location"),
                "desc": cfg.get("desc", ""),
                "min_tier": cfg.get("min_tier", 1),
                "danger": cfg.get("danger", 0.3),
                "is_open": is_open,
                "remain_hours": round(remain, 2),
            }
        )
    return rows


def _maybe_open_realm(rid: str, now: float) -> bool:
    _ensure_loaded()
    cfg = SECRET_REALMS.get(rid)
    if not cfg:
        return False
    last = _realm_open_ts.get(rid, 0.0)
    interval = cfg.get("open_interval_hours", 6.0) * 3600.0
    if (now - last) >= interval:
        _realm_open_ts[rid] = now
        _persist_realm_ts()
        return True
    return False


def director_force_open(rid: str, now: Optional[float] = None) -> bool:
    """天道导演：使秘境进入「可开启」状态（is_open=True），不绕过探索规则。

    语义：realm_status.is_open = (now - last_open_ts) >= interval。
    故「提前开启」应把 last 调到 now-interval（或更早），而不是写成 now。
    """
    _ensure_loaded()
    t = now if now is not None else time.time()
    cfg = SECRET_REALMS.get(rid)
    if not cfg:
        return False
    interval = float(cfg.get("open_interval_hours", 6.0)) * 3600.0
    # 令 (t - last) >= interval
    _realm_open_ts[rid] = t - interval
    _persist_realm_ts()
    try:
        from core.world_channel import WorldChannel
        from storage.db import WorldStateRepository as WSR

        cd = WSR.get("realm_broadcast_cd") or {}
        last = float(cd.get(rid) or 0.0)
        if t - last > 1800:
            cd[rid] = t
            WSR.set("realm_broadcast_cd", cd)
            WorldChannel.post(
                "realm",
                f"【天道导演】{rid} 禁制提前松动，限时开启。",
                level="major",
                actor="director",
                location=cfg.get("location") or "",
                now=t,
                skip_limit=True,
            )
    except Exception:
        pass
    return True


class SecretRealmEngine:
    @staticmethod
    def board_text() -> str:
        rows = realm_status()
        lines = ["【秘境天机】限时开启，可接可拒；错过还有下次。"]
        for r in rows:
            state = "已开启" if r["is_open"] else f"约 {r['remain_hours']:.1f} 小时后开启"
            lines.append(
                f"· {r['name']}（{r['location']}）门槛境界 {r['min_tier']}+ "
                f"危险 {int(r['danger']*100)}% — {state}\n  {r['desc']}"
            )
        return "\n".join(lines)

    @staticmethod
    def enter(c: Character, realm_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        _ensure_loaded()
        t = now if now is not None else time.time()
        cfg = SECRET_REALMS.get(realm_id)
        if not cfg:
            # 模糊匹配
            for rid, c2 in SECRET_REALMS.items():
                if realm_id and realm_id in rid:
                    realm_id, cfg = rid, c2
                    break
        if not cfg:
            return {"success": False, "message": f"无此秘境：{realm_id}。/秘境 可览。"}

        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消。"}
        if c.status == CharacterStatus.MEDITATING:
            return {"success": False, "message": "闭关中不可探秘境。"}
        if c.id in _active_chains:
            return {"success": False, "message": "你已有一场探索未结。"}

        _maybe_open_realm(realm_id, t)
        last = _realm_open_ts.get(realm_id, 0.0)
        interval = cfg.get("open_interval_hours", 6.0) * 3600.0
        if (t - last) < 0:  # never
            pass
        # 若刚打开或本周期内
        if realm_id not in _realm_open_ts:
            _realm_open_ts[realm_id] = t
            _persist_realm_ts()
        # 开启判定：允许在 interval 内重复进入（冷却刚过则刷新）
        if (t - _realm_open_ts.get(realm_id, 0)) > interval:
            _realm_open_ts[realm_id] = t
            _persist_realm_ts()

        if c.realm.tier < cfg.get("min_tier", 1):
            return {
                "success": False,
                "message": f"境界不足，【{realm_id}】需境界 {cfg.get('min_tier')}+（现 {c.realm.name}）。",
            }

        loc = cfg.get("location")
        if loc and c.location != loc:
            return {
                "success": False,
                "message": f"须亲至【{loc}】入口。当前【{c.location}】。",
            }

        chain = {
            "id": uuid.uuid4().hex[:8],
            "realm_id": realm_id,
            "step": 1,
            "max_steps": EVENT_CHAIN_MAX_STEPS,
            "danger": cfg.get("danger", 0.3),
            "started_at": t,
            "title": f"秘境·{realm_id}",
        }
        _active_chains[c.id] = chain
        _persist_chains()
        try:
            from core.world_channel import WorldChannel
            from storage.db import WorldStateRepository as WSR

            # 世界级开启才播：同一秘境 30 分钟内只播一次
            cd = WSR.get("realm_broadcast_cd") or {}
            last = float(cd.get(realm_id) or 0.0)
            if t - last > 1800:
                cd[realm_id] = t
                WSR.set("realm_broadcast_cd", cd)
                WorldChannel.post(
                    "realm",
                    f"【天机】{realm_id} 禁制松动，限时开启。",
                    level="major",
                    actor=c.name,
                    location=loc or "",
                )
        except Exception:
            pass
        return {
            "success": True,
            "chain": chain,
            "message": (
                f"【秘境开启】{c.name} 踏入【{realm_id}】。\n"
                f"{cfg.get('desc','')}\n"
                f"共约 {EVENT_CHAIN_MAX_STEPS} 处关隘，/探秘 可推进，随时可弃（无惩罚）。"
            ),
        }

    @staticmethod
    def step(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        _ensure_loaded()
        t = now if now is not None else time.time()
        chain = _active_chains.get(c.id)
        if not chain:
            return {"success": False, "message": "并无进行中的秘境探索。可 /秘境 查看。"}

        cfg = SECRET_REALMS.get(chain["realm_id"], {})
        danger = chain.get("danger", 0.3)
        # 业力提高遇劫概率
        roll_danger = danger + min(0.2, c.karma.sin_value * 0.0003)
        is_last = chain["step"] >= chain["max_steps"]

        if random.random() < roll_danger and not (c.arrays and random.random() < 0.25):
            # 危机
            loss_years = round(random.uniform(0.5, 2.5) * danger, 1)
            stones_loss = int(c.spirit_stones * random.uniform(0.05, 0.20) * danger)
            c.lifespan.burn_lifespan(loss_years)
            c.spirit_stones = max(0, c.spirit_stones - stones_loss)
            if c.lifespan.is_dead(t):
                c.status = CharacterStatus.DEAD
                c.death_cause = c.death_cause or "秘境杀劫"
                _active_chains.pop(c.id, None)
                _persist_chains()
                return {
                    "success": True,
                    "kind": "death",
                    "message": (
                        f"【秘境杀劫】第 {chain['step']} 处禁制反噬，"
                        f"寿元 -{loss_years}，身死道消。"
                    ),
                }
            if is_last:
                _active_chains.pop(c.id, None)
            else:
                chain["step"] += 1
            _persist_chains()
            return {
                "success": True,
                "kind": "crisis",
                "message": (
                    f"【秘境杀劫】第 {chain['step']} 处阵纹噬人，"
                    f"寿元 -{loss_years} 岁，散落灵石 {stones_loss}。"
                    + ("已闯出出口。" if is_last else "尚可继续 /探秘。")
                ),
            }

        # 机缘
        qi = global_qi_multiplier()
        exp = int(random.randint(60, 180) * (1 + c.realm.tier * 0.3) * qi)
        stones = random.randint(20, 120)
        c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp)
        c.spirit_stones += stones
        reward_line = f"修为 +{exp}，灵石 +{stones}"
        if random.random() < 0.15:
            c.karma.add_merit(8)
            reward_line += "，功德 +8"

        if is_last:
            _active_chains.pop(c.id, None)
            kind = "complete"
            msg = f"【秘境功成】{chain['title']} 已走通，{reward_line}。"
            try:
                from core.social_bonds import mark_graduate_credit

                mark_graduate_credit(c)
            except Exception:
                pass
        else:
            chain["step"] += 1
            kind = "fortune"
            msg = (
                f"【秘境机缘】第 {chain['step']-1} 处得手，{reward_line}。"
                f"继续 /探秘 或收手离去。"
            )
        _persist_chains()
        return {"success": True, "kind": kind, "message": msg, "chain": _active_chains.get(c.id)}

    @staticmethod
    def abandon(c: Character) -> Dict[str, Any]:
        _ensure_loaded()
        chain = _active_chains.pop(c.id, None)
        if not chain:
            return {"success": False, "message": "本无探索。"}
        _persist_chains()
        return {
            "success": True,
            "message": f"【抽身而退】放弃【{chain['title']}】，天道不罪。",
        }

    @staticmethod
    def active_chain(c: Character) -> Optional[Dict[str, Any]]:
        _ensure_loaded()
        return _active_chains.get(c.id)

    @staticmethod
    def maybe_open_nearby(c: Character, chance: float = 0.2) -> Optional[str]:
        """游历时小概率撞见秘境开启（推送目标）"""
        _ensure_loaded()
        if random.random() >= chance:
            return None
        for rid, cfg in SECRET_REALMS.items():
            if cfg.get("location") == c.location:
                if _maybe_open_realm(rid, time.time()):
                    return rid
        return None
