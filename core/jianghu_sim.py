"""
江湖仿真结算引擎（规则唯一权威）。

议程不是文案：每条议程必须尝试
  选目标 → 改状态/夺财/结仇/突破/遁走 → 级联 → 因果账。
AI 仅可在结算完成后改写叙事，禁止驱动数值。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import WORLD_LOCATIONS, KARMA_KILL_LOWER_TIER, KARMA_KILL_SAME_TIER
from core.models import Character, CharacterStatus
from storage.db import CharacterRepository, NpcAgendaRepository, WorldStateRepository

_OFFLINE_TS_KEY = "jianghu_sim_last_ts"
# 离线追赶：按现实秒折算「仿真波次」
_OFFLINE_WAVE_SECONDS = 30 * 60.0  # 每 30 分钟现实时间一波
_OFFLINE_MAX_WAVES = 8
_OFFLINE_MAX_ACTIONS = 20

_SAFE_RETREAT = "青云坊市客栈"


def _is_npc(c: Character) -> bool:
    uid = str(getattr(c, "user_id", "") or "")
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def _alive(c: Character) -> bool:
    return (
        c is not None
        and c.status != CharacterStatus.DEAD
        and not c.lifespan.is_dead()
    )


def _loc_safe(name: str) -> bool:
    return bool(WORLD_LOCATIONS.get(name, {}).get("is_safe", True))


def _power(c: Character) -> float:
    from core.combat import CombatEngine

    return CombatEngine.calculate_power(c)


class JianghuSimulator:
    """议程规则结算 + 击杀级联 + 离线追赶"""

    # ---------------- 目标获取 ----------------

    @staticmethod
    def revenge_targets(npc: Character) -> List[Tuple[Character, str]]:
        """仇边/血煞相关目标，优先同图。返回 (角色, 因由)"""
        out: List[Tuple[Character, str]] = []
        try:
            from core.collusion import links_of

            for link in links_of(npc.id):
                if link.link_type not in ("仇", "血仇"):
                    continue
                oid, oname = link.other_side(npc.id)
                other = CharacterRepository.get_by_id(oid) or CharacterRepository.find_alive_by_name(onname)
                if other and _alive(other) and other.id != npc.id:
                    out.append((other, link.note or f"与{other.name}有仇"))
        except Exception:
            pass
        # 无仇边时：若自己血煞，仇视「代天除凶」的高功德者；否则同图高业力
        if not out and npc.karma.is_blood_marked():
            for c in CharacterRepository.list_all_alive():
                if c.id == npc.id or not _alive(c) or not _is_npc(c):
                    continue
                if c.location == npc.location and c.karma.merit_value >= 40:
                    out.append((c, "对方功德昭彰，恐为除凶之人"))
                    break
        # 同图排序优先
        out.sort(key=lambda x: 0 if x[0].location == npc.location else 1)
        return out[:3]

    @staticmethod
    def treasure_targets(npc: Character) -> List[Tuple[Character, str]]:
        out = []
        for c in CharacterRepository.list_all_alive():
            if c.id == npc.id or not _alive(c):
                continue
            if not _is_npc(c) and c.spirit_stones < 200:
                continue
            if c.spirit_stones >= 300 or (c.inventory if hasattr(c, "inventory") else []):
                reason = f"身携灵石{c.spirit_stones}"
                if c.location == npc.location:
                    reason += "·同图"
                out.append((c, reason))
        out.sort(key=lambda x: (0 if x[0].location == npc.location else 1, -x[0].spirit_stones))
        return out[:3]

    @staticmethod
    def patrol_targets(npc: Character) -> List[Tuple[Character, str]]:
        out = []
        for c in CharacterRepository.list_all_alive():
            if c.id == npc.id or not _alive(c):
                continue
            if c.karma.is_blood_marked() or c.karma.sin_value >= 80:
                tag = "血煞" if c.karma.is_blood_marked() else "重业"
                if c.location == npc.location:
                    out.insert(0, (c, f"{tag}缠身，同图"))
                else:
                    out.append((c, f"{tag}·{c.location}"))
        return out[:3]

    @staticmethod
    def acquire_target(npc: Character, ag_type: str, ag: Dict[str, Any]) -> Optional[Tuple[Character, str]]:
        hint = (ag.get("target_hint") or "").strip()
        # 显式 hint 优先
        if hint:
            t = CharacterRepository.find_alive_by_name(hint)
            if t and _alive(t) and t.id != npc.id:
                return t, f"议程指向【{hint}】"
            # hint 可能是宗门名
            for c in CharacterRepository.list_all_alive():
                if _alive(c) and c.sect == hint and c.id != npc.id:
                    return c, f"宗门【{hint}】之人"
        if ag_type == "revenge":
            ts = JianghuSimulator.revenge_targets(npc)
            return ts[0] if ts else None
        if ag_type == "treasure":
            ts = JianghuSimulator.treasure_targets(npc)
            return ts[0] if ts else None
        if ag_type == "patrol":
            ts = JianghuSimulator.patrol_targets(npc)
            return ts[0] if ts else None
        if ag_type == "survive" and npc.karma.sin_value >= 80:
            ts = JianghuSimulator.patrol_targets(npc)  # 猎手可能在盯
            return None  # survive 不主动选目标，只求生
        return None

    # ---------------- 规则结算 ----------------

    @staticmethod
    def resolve_agenda(
        npc: Character,
        ag_type: str,
        ag: Dict[str, Any],
        *,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        结算一条议程。返回：
          acted, action, narrative, notes, outcome, target_id, effects,
          progress_delta, new_location, cascade_notes
        effects 仅含规则白名单字段（exp/stones/sin/merit/status 等由调用方应用）
        """
        t = now or time.time()
        loc = npc.location
        safe = _loc_safe(loc)
        picked = JianghuSimulator.acquire_target(npc, ag_type, ag)
        target, why = (picked if picked else (None, ""))
        notes: List[str] = []
        cascade_notes: List[str] = []
        effects: Dict[str, Any] = {}
        outcome = "idle"
        action = "stay"
        narrative = ""
        new_location = None
        pdelta = 0
        acted = False

        # ---------- 寻仇 ----------
        if ag_type == "revenge":
            if target is None:
                if random.random() < 0.45:
                    acted = True
                    action = "scheme"
                    pdelta = 1
                    narrative = f"{npc.name}四下打听仇家行踪，袖中剑意森然，却暂无确切下落。"
                    outcome = "snoop"
                else:
                    narrative = f"{npc.name}按剑静坐，仇怨压在心头。"
            elif target.location != loc:
                # 追击：小概率赶往仇家所在
                if random.random() < 0.55 and target.location in WORLD_LOCATIONS:
                    acted = True
                    action = "move"
                    new_location = target.location
                    pdelta = 1
                    outcome = "pursue"
                    narrative = f"{npc.name}闻【{target.name}】人在【{target.location}】，裹粮追去。"
                    notes.append(f"追踪{target.name}→{target.location}")
                else:
                    acted = True
                    action = "scheme"
                    pdelta = 1
                    outcome = "snoop"
                    narrative = f"{npc.name}打探【{target.name}】下落（{why}），杀心愈盛。"
            elif safe:
                # 安全区不可动武：只能盯梢/记仇
                acted = True
                action = "scheme"
                pdelta = 1
                outcome = "stare"
                narrative = f"{npc.name}在【{loc}】盯了【{target.name}】半晌，碍于大阵禁制按剑未发。"
                notes.append("安全区对峙")
                cascade_notes.append("仇怨加深（安全区）")
                try:
                    from core.collusion import ensure_link
                    ensure_link(npc, target, "仇", note=f"安全区对峙于{loc}", now=t)
                except Exception:
                    pass
            else:
                # 野外结算：战力对决
                acted = True
                ap = _power(npc) * (1.25 if npc.karma.is_blood_marked() else 1.0)
                # 天道导演/世界弧：地点热度
                try:
                    from core.world_director import location_heat_for

                    heat = location_heat_for(loc, getattr(npc, "sect", "") or "")
                    ap *= max(1.0, min(1.5, heat))
                except Exception:
                    pass
                # M3 敌对宗门战力修正
                try:
                    from core.faction import hostile_power_bonus

                    ap *= hostile_power_bonus(getattr(npc, "sect", "") or "", getattr(target, "sect", "") or "")
                except Exception:
                    pass
                dp = _power(target)
                # 闭关中更易被偷袭
                if target.status == CharacterStatus.MEDITATING:
                    ap *= 1.2
                ratio = ap / max(1.0, ap + dp)
                win = random.random() < ratio
                if win:
                    loot = int(target.spirit_stones * random.uniform(0.55, 0.8))
                    target.spirit_stones = max(0, target.spirit_stones - loot)
                    npc.spirit_stones += loot
                    target.status = CharacterStatus.DEAD
                    try:
                        target.lifespan.death_timestamp = 0.0
                        target.death_cause = f"被{npc.name}寻仇所斩"
                    except Exception:
                        pass
                    sin = KARMA_KILL_SAME_TIER if target.realm.tier >= npc.realm.tier else KARMA_KILL_LOWER_TIER
                    npc.karma.add_sin(sin)
                    action = "scheme"
                    pdelta = 3
                    outcome = "kill"
                    narrative = (
                        f"{npc.name}于【{loc}】截住仇家【{target.name}】，"
                        f"一场厮杀后将其斩落，夺灵石 {loot}。"
                    )
                    notes.append(f"斩{target.name}夺{loot}灵石业力+{sin}")
                    cascade_notes.extend(
                        JianghuSimulator.cascade_kill(npc, target, location=loc, loot=loot)
                    )
                    effects = {"stones_gain_npc": loot, "sin": sin, "kill": target.id}
                else:
                    # 失败：受伤或对方遁走
                    if random.random() < 0.35:
                        # 自己负伤
                        burn = random.uniform(1.0, 4.0)
                        try:
                            npc.lifespan.burn_lifespan(burn)
                        except Exception:
                            pass
                        action = "scheme"
                        pdelta = 1
                        outcome = "wounded"
                        narrative = f"{npc.name}伏击【{target.name}】失手，反被震伤，燃寿约{burn:.1f}岁遁走。"
                        notes.append("寻仇失败受伤")
                    else:
                        # 对方遁走
                        dest = _pick_hideout(target)
                        if dest and dest != target.location:
                            old = target.location
                            target.location = dest
                            notes.append(f"{target.name}遁往{dest}")
                        action = "scheme"
                        pdelta = 1
                        outcome = "escaped"
                        narrative = f"{npc.name}寻【{target.name}】晦气，对方见机得快，遁出【{loc}】。"
                    try:
                        from core.collusion import ensure_link
                        ensure_link(npc, target, "仇", note=f"寻仇未果于{loc}", now=t)
                    except Exception:
                        pass
                    cascade_notes.append("仇边加深")

        # ---------- 夺宝 ----------
        elif ag_type == "treasure":
            if target is None:
                if random.random() < 0.4:
                    acted = True
                    action = "scheme"
                    pdelta = 1
                    outcome = "scout_market"
                    narrative = f"{npc.name}乔装入市，暗中估价灵材，盘算下手时机。"
                else:
                    narrative = f"{npc.name}紧了紧储物袋，未敢妄动。"
            elif target.location != loc:
                if random.random() < 0.4 and target.location in WORLD_LOCATIONS:
                    acted = True
                    action = "move"
                    new_location = target.location
                    pdelta = 1
                    outcome = "chase_loot"
                    narrative = f"{npc.name}盯上【{target.name}】的身家，悄然缀往【{target.location}】。"
                else:
                    acted = True
                    action = "scheme"
                    pdelta = 1
                    outcome = "scout"
                    narrative = f"{npc.name}打听【{target.name}】行囊虚实（{why}）。"
            elif safe:
                # 坊市只能「巧取」：小概率交易压价/顺手牵羊被喝止
                if random.random() < 0.25 and target.spirit_stones > 0:
                    steal = min(target.spirit_stones, random.randint(5, 40))
                    target.spirit_stones -= steal
                    npc.spirit_stones += steal
                    acted = True
                    action = "scheme"
                    pdelta = 1
                    outcome = "pickpocket"
                    narrative = f"{npc.name}在坊市人潮中顺走【{target.name}】灵石 {steal}，手法极快。"
                    notes.append(f"市井窃取{steal}灵石")
                    try:
                        from core.collusion import ensure_link
                        ensure_link(target, npc, "仇", note="坊市失窃", now=t)
                        cascade_notes.append("失主记仇")
                    except Exception:
                        pass
                else:
                    acted = True
                    action = "talk"
                    pdelta = 1
                    outcome = "haggle"
                    narrative = f"{npc.name}在坊市与【{target.name}】攀谈压价，未撕破脸。"
            else:
                acted = True
                ap = _power(npc)
                dp = _power(target) * 1.1  # 守方微优
                win = random.random() < (ap / max(1.0, ap + dp))
                if win and target.spirit_stones > 0:
                    loot = int(target.spirit_stones * random.uniform(0.3, 0.65))
                    target.spirit_stones = max(0, target.spirit_stones - loot)
                    npc.spirit_stones += loot
                    npc.karma.add_sin(25)
                    action = "scheme"
                    pdelta = 2
                    outcome = "rob"
                    narrative = f"{npc.name}在【{loc}】拦路夺了【{target.name}】灵石 {loot}，天理昭昭业力上身。"
                    notes.append(f"拦路夺宝{loot}灵石")
                    try:
                        from core.collusion import ensure_link
                        ensure_link(target, npc, "仇", note="拦路抢劫", now=t)
                        cascade_notes.append("苦主结仇")
                    except Exception:
                        pass
                    effects = {"loot": loot, "sin": 25}
                else:
                    # 失败被击退
                    if random.random() < 0.25:
                        target.status = CharacterStatus.DEAD
                        try:
                            target.death_cause = f"反抗{npc.name}夺宝时力竭"
                        except Exception:
                            pass
                        # 夺宝者未必得财
                        loot = 0
                        npc.karma.add_sin(30)
                        outcome = "rob_kill"
                        narrative = f"{npc.name}强夺【{target.name}】未果，缠斗中竟将对方打杀，只得空手，业力+30。"
                        cascade_notes.extend(
                            JianghuSimulator.cascade_kill(npc, target, location=loc, loot=0)
                        )
                    else:
                        outcome = "rob_fail"
                        narrative = f"{npc.name}欲夺【{target.name}】财货，被对方警觉喝退。"
                        notes.append("夺宝失败")
                    action = "scheme"
                    pdelta = 1

        # ---------- 闭关求突破 ----------
        elif ag_type == "seclusion":
            acted = True
            action = "train"
            if npc.realm.is_full:
                from core.breakthrough import BreakthroughEngine

                # NPC 无丹，走规则天劫
                res = BreakthroughEngine.attempt_breakthrough(npc, use_pill=False)
                if res.get("success"):
                    pdelta = 3
                    outcome = "breakthrough"
                    narrative = f"{npc.name}闭关功成，引动天机突破至【{npc.realm.name}】！"
                    notes.append(f"突破→{npc.realm.name}")
                    cascade_notes.append(f"境界跃迁：{npc.name}")
                    try:
                        from core.world_channel import WorldChannel

                        WorldChannel.post(
                            "break",
                            f"【天象】{npc.name} 于闭关中突破 {npc.realm.name}，灵气如潮。",
                            level="info",
                        )
                    except Exception:
                        pass
                else:
                    if res.get("is_fatal"):
                        npc.status = CharacterStatus.DEAD
                        try:
                            npc.death_cause = "天劫下身死道消"
                        except Exception:
                            pass
                        pdelta = 3
                        outcome = "tribulation_die"
                        narrative = f"{npc.name}强行冲击更高境界，天劫轰落，身死道消。"
                        cascade_notes.append("天劫陨落")
                    else:
                        gain = random.randint(20, 60)
                        npc.realm.current_exp = min(npc.realm.max_exp, npc.realm.current_exp + gain)
                        pdelta = 1
                        outcome = "tribulation_fail"
                        narrative = f"{npc.name}天劫未过，跌回洞府温养道基（修为+{gain}）。"
                        notes.append("天劫失败")
            else:
                gain = random.randint(40, 120)
                before = npc.realm.current_exp
                npc.realm.current_exp = min(npc.realm.max_exp, npc.realm.current_exp + gain)
                pdelta = 1
                outcome = "cultivate"
                narrative = f"{npc.name}闭关吐纳，真元鼓荡，修为+{gain}（{before}→{npc.realm.current_exp}）。"
                notes.append(f"修为+{gain}")

        # ---------- 巡守 ----------
        elif ag_type == "patrol":
            if target is None:
                acted = True
                action = "talk"
                pdelta = 1
                outcome = "patrol_clear"
                narrative = f"{npc.name}在【{loc}】一带巡守，未见血煞踪迹。"
            elif target.location != loc:
                acted = True
                action = "move"
                new_location = target.location if target.location in WORLD_LOCATIONS else loc
                pdelta = 1
                outcome = "patrol_deploy"
                narrative = f"{npc.name}接报【{target.name}】现于【{target.location}】，提剑赶去。"
            elif safe:
                acted = True
                action = "talk"
                pdelta = 1
                outcome = "patrol_watch"
                narrative = f"{npc.name}于坊市盘问【{target.name}】，对方血气内敛，暂未动手。"
                notes.append("安全区监视")
            else:
                acted = True
                ap = _power(npc) * 1.05  # 正道围剿微优
                dp = _power(target)
                win = random.random() < (ap / max(1.0, ap + dp))
                if win:
                    loot = int(target.spirit_stones * 0.4)
                    target.spirit_stones = max(0, target.spirit_stones - loot)
                    npc.spirit_stones += loot
                    target.status = CharacterStatus.DEAD
                    try:
                        target.death_cause = f"被{npc.name}巡守围杀"
                    except Exception:
                        pass
                    # 除凶减业力
                    if target.karma.sin_value >= 80 or target.karma.is_blood_marked():
                        npc.karma.add_merit(40)
                        notes.append("除凶功德+40")
                    action = "talk"
                    pdelta = 3
                    outcome = "patrol_kill"
                    narrative = f"{npc.name}于【{loc}】围杀血煞之徒【{target.name}】，为民除害。"
                    cascade_notes.extend(
                        JianghuSimulator.cascade_kill(npc, target, location=loc, loot=loot)
                    )
                    effects = {"kill": target.id, "merit": 40}
                else:
                    dest = _pick_hideout(target)
                    if dest:
                        target.location = dest
                        notes.append(f"{target.name}突围遁往{dest}")
                    outcome = "patrol_fail"
                    action = "talk"
                    pdelta = 1
                    narrative = f"{npc.name}缉拿【{target.name}】未果，对方遁入荒野。"
                try:
                    from core.world_channel import WorldChannel

                    if outcome == "patrol_kill":
                        WorldChannel.post(
                            "kill",
                            f"【除凶】{npc.name} 于 {loc} 围杀 {target.name}。",
                            level="major",
                        )
                except Exception:
                    pass

        # ---------- 结交打探 ----------
        elif ag_type == "social":
            acted = random.random() < 0.7
            action = "talk"
            pdelta = 1
            outcome = "gossip"
            try:
                import core.jianghu as jianghu
                from core import rumors

                evs = jianghu.list_recent(limit=6)
                if evs:
                    ev = random.choice(evs)
                    line = ev.get("summary") or ""
                    narrative = f"{npc.name}在【{loc}】与人闲话：「{line[:40]}」眉间隐有忧色。"
                    try:
                        rumors.add_rumor(f"坊间传：{line[:50]}", origin=npc.name, truth=0.6)
                    except Exception:
                        pass
                else:
                    narrative = f"{npc.name}与人闲话近日天象，未得要领。"
            except Exception:
                narrative = f"{npc.name}市井打探机缘消息。"
            if not acted:
                narrative = f"{npc.name}独坐饮茶，未与人多言。"
                action = "stay"
                pdelta = 0
                outcome = "idle"

        # ---------- 避劫求生 ----------
        elif ag_type == "survive":
            acted = True
            if loc != _SAFE_RETREAT and random.random() < 0.65:
                action = "move"
                new_location = _SAFE_RETREAT
                pdelta = 1
                outcome = "flee_safe"
                narrative = f"{npc.name}血债在身，连夜遁入【{_SAFE_RETREAT}】大阵庇护。"
                notes.append(f"遁入安全区")
            elif npc.spirit_stones >= 50 and random.random() < 0.4:
                # 破财消灾
                pay = min(npc.spirit_stones, random.randint(20, 80))
                npc.spirit_stones -= pay
                reduce_sin = min(10, pay // 10)
                if reduce_sin > 0:
                    npc.karma.sin_value = max(0, npc.karma.sin_value - reduce_sin)
                action = "scheme"
                pdelta = 1
                outcome = "bribe"
                narrative = f"{npc.name}向坊市势力孝敬 {pay} 灵石，求个容身，业力略减。"
                notes.append(f"破财{pay}消业{reduce_sin}")
            else:
                npc.stealth_active = True
                action = "stay"
                pdelta = 1
                outcome = "hide"
                narrative = f"{npc.name}敛息匿迹，藏于【{loc}】阴影之中。"
                notes.append("开启敛息")

        # ---------- 未识别 ----------
        else:
            acted = random.random() < 0.3
            narrative = f"{npc.name}于【{loc}】随缘而动。"
            outcome = "misc"

        return {
            "acted": acted,
            "action": action,
            "narrative": narrative,
            "notes": notes,
            "cascade_notes": cascade_notes,
            "outcome": outcome,
            "target_id": target.id if target else None,
            "target_name": target.name if target else None,
            "target_reason": why,
            "effects": effects,
            "progress_delta": pdelta,
            "new_location": new_location,
            "agenda": ag_type,
        }

    # ---------------- 级联 ----------------

    @staticmethod
    def cascade_kill(killer: Character, victim: Character, *, location: str, loot: int = 0) -> List[str]:
        """击杀后的江湖涟漪：仇边/宗门/传闻/频道/除凶榜"""
        notes: List[str] = []
        t = time.time()
        try:
            from core.collusion import ensure_link
            from core import rumors
            from core.npc_mind import on_kill_update_attitudes

            ensure_link(killer, victim, "仇", note=f"斩杀于{location}", now=t)
            try:
                on_kill_update_attitudes(killer, victim)
            except Exception:
                pass
            try:
                rumors.note_kill(killer.name, victim.name, location)
            except Exception:
                pass
            # 同宗记仇 + 默认议程改寻仇
            if victim.sect:
                for c in CharacterRepository.list_all_alive():
                    if c.id in (killer.id, victim.id) or not _alive(c):
                        continue
                    if c.sect == victim.sect:
                        ensure_link(c, killer, "仇", note=f"同门{victim.name}被斩", now=t)
                        if _is_npc(c):
                            try:
                                NpcAgendaRepository.upsert(
                                    npc_id=c.id,
                                    npc_name=c.name,
                                    agenda_type="revenge",
                                    target_hint=killer.name,
                                    note=f"为同门{victim.name}复仇",
                                    state="active",
                                    last_tick=0.0,
                                    progress=0,
                                )
                                notes.append(f"{c.name}议程→寻仇{killer.name}")
                            except Exception:
                                pass
                notes.append(f"宗门【{victim.sect}】记恨")
            # 血煞/高业力：除凶榜可见
            try:
                from core.hunt import is_marked

                if is_marked(killer):
                    notes.append("凶手已上除凶榜")
            except Exception:
                pass
            # 玩家杀 NPC / NPC 杀玩家：频道
            try:
                from core.world_channel import WorldChannel
                from config import CHANNEL_KILL_MIN_TIER

                major = (
                    victim.realm.tier >= CHANNEL_KILL_MIN_TIER
                    or victim.karma.is_blood_marked()
                    or not _is_npc(killer)
                    or not _is_npc(victim)
                )
                if major:
                    WorldChannel.post(
                        "kill",
                        f"【血雨】{killer.name} 于 {location} 斩 {victim.name}"
                        + (f"，夺灵石 {loot}" if loot else "")
                        + "，天机显影。",
                        level="major",
                    )
                    notes.append("世界频道血雨")
            except Exception:
                pass
            # 因果账（调用方也可能再写，这里写级联专用）
            try:
                import core.jianghu as jianghu

                jianghu.append_event(
                    kind="kill",
                    actor_ids=[killer.id],
                    actor_names=[killer.name],
                    target_ids=[victim.id],
                    location=location,
                    summary=f"{killer.name} 于 {location} 斩 {victim.name}",
                    rule_result={"loot": loot, "cascade": notes, "victim_sect": victim.sect},
                    narrative="",
                    ref_ids=[killer.id, victim.id],
                    source="rule",
                )
            except Exception:
                pass
        except Exception as e:
            notes.append(f"级联部分失败:{e}")
        return notes

    # ---------------- 离线追赶 ----------------

    @staticmethod
    def mark_sim_ts(ts: Optional[float] = None) -> None:
        try:
            WorldStateRepository.set(_OFFLINE_TS_KEY, ts or time.time())
        except Exception:
            pass

    @staticmethod
    def last_sim_ts() -> float:
        try:
            v = WorldStateRepository.get(_OFFLINE_TS_KEY)
            return float(v or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def simulate_offline(
        *,
        now: Optional[float] = None,
        max_waves: int = _OFFLINE_MAX_WAVES,
        max_actions: int = _OFFLINE_MAX_ACTIONS,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        玩家不在时推进江湖。按 last_sim_ts 折算波次；每波结算若干 NPC。
        返回 {waves, actions, events, deaths, breakthroughs, texts}
        """
        t = now or time.time()
        last = JianghuSimulator.last_sim_ts()
        if last <= 0:
            JianghuSimulator.mark_sim_ts(t)
            return {"waves": 0, "actions": 0, "events": [], "note": "首次对时，记下此刻江湖。"}
        elapsed = max(0.0, t - last)
        waves = int(elapsed // _OFFLINE_WAVE_SECONDS)
        if force:
            waves = max(waves, 1)
        waves = max(0, min(max_waves, waves))
        if waves <= 0:
            return {
                "waves": 0,
                "actions": 0,
                "events": [],
                "elapsed_sec": elapsed,
                "note": f"离线 {elapsed/60:.0f} 分钟，未满一波（约{_OFFLINE_WAVE_SECONDS/60:.0f}分钟/波）。",
            }

        from core.npc_agenda import list_npc_characters, ensure_agenda, AGENDA_TYPES
        from core.npc_mind import pick_agenda_for_tick

        events: List[str] = []
        actions = 0
        deaths = 0
        breakthroughs = 0

        npcs = list_npc_characters(limit=24)
        for w in range(waves):
            if actions >= max_actions:
                break
            random.shuffle(npcs)
            for npc in npcs[:6]:
                if actions >= max_actions:
                    break
                if not _alive(npc):
                    continue
                try:
                    ag = ensure_agenda(npc)
                    chosen = pick_agenda_for_tick(npc)
                    ag_type = chosen.get("agenda_type") or ag.get("agenda_type") or "social"
                    res = JianghuSimulator.resolve_agenda(npc, ag_type, ag, now=t)
                    if not res.get("acted"):
                        continue
                    actions += 1
                    # 应用位移与保存
                    if res.get("new_location") and res["new_location"] in WORLD_LOCATIONS:
                        npc.location = res["new_location"]
                    try:
                        CharacterRepository.save(npc)
                        if res.get("target_id"):
                            tgt = CharacterRepository.get_by_id(res["target_id"])
                            if tgt:
                                CharacterRepository.save(tgt)
                                if tgt.status == CharacterStatus.DEAD:
                                    deaths += 1
                    except Exception:
                        pass
                    if res.get("outcome") in ("breakthrough",):
                        breakthroughs += 1
                    if npc.status == CharacterStatus.DEAD:
                        deaths += 1
                    # 因果账（受预算）
                    try:
                        import core.jianghu as jianghu

                        jianghu.append_event(
                            kind="npc_agenda",
                            actor_ids=[npc.id],
                            actor_names=[npc.name],
                            target_ids=[res["target_id"]] if res.get("target_id") else [],
                            location=npc.location,
                            summary=f"{npc.name}({AGENDA_TYPES.get(ag_type, ag_type)}) {res['narrative'][:50]}",
                            rule_result={
                                "outcome": res["outcome"],
                                "action": res["action"],
                                "offline_wave": w,
                                "notes": res.get("notes"),
                                "cascade": res.get("cascade_notes"),
                            },
                            narrative=res["narrative"][:200],
                            source="rule",
                            enforce_budget=True,
                            now=t,
                        )
                    except Exception:
                        pass
                    # 议程进度
                    try:
                        pd = int(res.get("progress_delta") or 0)
                        new_p = int(ag.get("progress") or 0) + pd
                        if new_p >= 5 or res.get("outcome") in ("kill", "breakthrough", "tribulation_die"):
                            from core.npc_agenda import default_agenda_for

                            d = default_agenda_for(npc)
                            NpcAgendaRepository.upsert(
                                npc_id=npc.id,
                                npc_name=npc.name,
                                agenda_type=d["agenda_type"],
                                target_hint=d.get("target_hint", ""),
                                note=d.get("note", ""),
                                state="active",
                                last_tick=t,
                                progress=0,
                            )
                        else:
                            NpcAgendaRepository.mark_tick(
                                npc.id,
                                last_action=f"offline:{res['action']}",
                                progress=new_p,
                            )
                    except Exception:
                        pass
                    events.append(
                        f"【波次{w+1}】{npc.name}·{AGENDA_TYPES.get(ag_type, ag_type)}：{res['narrative'][:80]}"
                    )
                except Exception:
                    continue

        JianghuSimulator.mark_sim_ts(t)
        return {
            "waves": waves,
            "actions": actions,
            "events": events,
            "deaths": deaths,
            "breakthroughs": breakthroughs,
            "elapsed_sec": elapsed,
            "note": f"离线 {elapsed/3600:.1f} 小时，推进 {waves} 波、{actions} 次行动。",
        }


def _pick_hideout(c: Character) -> Optional[str]:
    candidates = [n for n, v in WORLD_LOCATIONS.items() if v.get("is_safe") and n != c.location]
    if not candidates:
        return None
    return random.choice(candidates)


def format_offline_report(rep: Dict[str, Any]) -> str:
    if not rep:
        return "江湖无事。"
    lines = [rep.get("note") or "离线结算完成。"]
    evs = rep.get("events") or []
    if evs:
        lines.append("── 离线期间江湖 ──")
        for e in evs[:12]:
            lines.append("  " + e)
        if len(evs) > 12:
            lines.append(f"  …另有 {len(evs)-12} 条")
    if rep.get("deaths"):
        lines.append(f"（陨落 {rep['deaths']} 人）")
    if rep.get("breakthroughs"):
        lines.append(f"（突破 {rep['breakthroughs']} 人）")
    return "\n".join(lines)
