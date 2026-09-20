"""
外出探险：打怪升级 + AI 叙事 + 规则掉落（梦幻西游式单次结算）
规则权威：成功率/掉落概率/数值上限；AI 写故事与事件，不可改概率。
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import (
    SECRET_REALMS,
    WORLD_LOCATIONS,
    ADVENTURE_FEE,
    ADVENTURE_COOLDOWN_MIN,
    ADVENTURE_EXP_BASE,
    ADVENTURE_EXP_MAX_MULT,
    ADVENTURE_EXP_FAIL_PCT,
    ADVENTURE_STONES_BASE,
    ADVENTURE_LIFESPAN_BURN_MAX,
    ADVENTURE_LOOT_P,
    ADVENTURE_LOOT_MAX,
    ADVENTURE_HERBS,
    ADVENTURE_PILLS,
    ADVENTURE_EQUIPS,
    EVENT_EFFECT_CAPS,
    ITEM_CATALOG,
    time_scale,
)
from core.models import Character, CharacterStatus
from core.combat import CombatEngine
from core.qi import global_qi_multiplier
from core.season import season_status_text


def _wild_target() -> Dict[str, Any]:
    return {
        "id": "野外",
        "name": "野外",
        "location": None,
        "min_tier": 1,
        "danger": 0.22,
        "desc": "坊市外围山野，妖兽与散修出没，收益平平。",
    }


def resolve_target(name: str) -> Optional[Dict[str, Any]]:
    name = (name or "").strip()
    if not name or name in ("野外", "山野", "wild"):
        return _wild_target()
    if name in SECRET_REALMS:
        cfg = SECRET_REALMS[name]
        return {
            "id": name,
            "name": name,
            "location": cfg.get("location"),
            "min_tier": cfg.get("min_tier", 1),
            "danger": cfg.get("danger", 0.3),
            "desc": cfg.get("desc", ""),
        }
    for rid, cfg in SECRET_REALMS.items():
        if name and (name in rid or rid in name):
            return {
                "id": rid,
                "name": rid,
                "location": cfg.get("location"),
                "min_tier": cfg.get("min_tier", 1),
                "danger": cfg.get("danger", 0.3),
                "desc": cfg.get("desc", ""),
            }
    # 地名当野外凶域
    if name in WORLD_LOCATIONS:
        loc = WORLD_LOCATIONS[name]
        return {
            "id": name,
            "name": name,
            "location": name,
            "min_tier": 1,
            "danger": 0.25 if loc.get("is_safe") else 0.55,
            "desc": loc.get("desc", ""),
        }
    return None


def list_targets() -> List[Dict[str, Any]]:
    rows = [_wild_target()]
    for rid, cfg in SECRET_REALMS.items():
        rows.append(
            {
                "id": rid,
                "name": rid,
                "location": cfg.get("location"),
                "min_tier": cfg.get("min_tier", 1),
                "danger": cfg.get("danger", 0.3),
                "desc": cfg.get("desc", ""),
            }
        )
    return rows


def _success_prob(c: Character, target: Dict[str, Any]) -> float:
    danger = float(target.get("danger") or 0.3)
    min_tier = int(target.get("min_tier") or 1)
    power = max(1.0, CombatEngine.calculate_power(c))
    base = 1.0 - danger
    tier_bonus = (c.realm.tier - min_tier) * 0.08
    power_bonus = math.log10(power + 1.0) * 0.05
    p = base + tier_bonus + power_bonus
    return max(0.15, min(0.92, p))


def _exp_caps(c: Character, target: Dict[str, Any], success: bool) -> Tuple[int, int]:
    """返回 (gain_max, loss_max)"""
    danger = max(0.1, float(target.get("danger") or 0.3))
    if success:
        gain = int(ADVENTURE_EXP_BASE * (1.0 + c.realm.tier) * danger * ADVENTURE_EXP_MAX_MULT)
        gain = max(20, gain)
        return gain, 0
    loss = int(c.realm.current_exp * ADVENTURE_EXP_FAIL_PCT) + 10
    return 0, max(10, loss)


def _stones_cap(c: Character, target: Dict[str, Any]) -> int:
    danger = max(0.1, float(target.get("danger") or 0.3))
    return int(ADVENTURE_STONES_BASE * (1.0 + c.realm.tier * 0.5) * danger)


def _roll_loot(success: bool, rng: random.Random) -> List[Dict[str, Any]]:
    """规则掉落；藏宝图概率很低；至多 ADVENTURE_LOOT_MAX 件"""
    if not success:
        return []
    loot: List[Dict[str, Any]] = []
    kinds = []
    for kind, p in ADVENTURE_LOOT_P.items():
        if rng.random() < p:
            kinds.append(kind)
    rng.shuffle(kinds)
    for kind in kinds[:ADVENTURE_LOOT_MAX]:
        if kind == "herb":
            loot.append({"kind": "herb", "name": rng.choice(ADVENTURE_HERBS), "qty": 1})
        elif kind == "pill":
            loot.append({"kind": "pill", "name": rng.choice(ADVENTURE_PILLS), "qty": 1})
        elif kind == "equip":
            # 稀有度：凡品多，人品少，地/天更少
            r = random.random()
            pool = [x for x in ADVENTURE_EQUIPS]
            if r < 0.75:
                pick = [x for x in pool if (ITEM_CATALOG.get(x) or {}).get("grade") == "凡品"]
            elif r < 0.92:
                pick = [x for x in pool if (ITEM_CATALOG.get(x) or {}).get("grade") == "人品"]
            else:
                pick = ["赤霄剑", "玄龟甲", "避尘珠"]
            loot.append({"kind": "equip", "name": random.choice(pick or pool), "qty": 1})
        elif kind == "map":
            loot.append({"kind": "map", "name": "藏宝图", "qty": 1})
    return loot


def _local_narrative(c: Character, target: Dict[str, Any], success: bool) -> str:
    n = target["name"]
    if success:
        return (
            f"{c.name}踏入【{n}】，与妖兽短兵相接。剑光过处血雾散尽，"
            f"于残骸间拾得机缘，负伤而归。"
        )
    return (
        f"{c.name}深入【{n}】，禁制与妖潮齐至，护体罡气崩碎，"
        f"狼狈遁出，元气大伤。"
    )


class AdventureEngine:
    """外出探险裁决"""

    @staticmethod
    def board_text(c: Optional[Character] = None) -> str:
        lines = ["【外出探险】可：/探险 野外 · /探险 <秘境名>（先 /前往 亦可）"]
        for t in list_targets():
            need = f"需境界{t['min_tier']}+" if c and c.realm.tier < t["min_tier"] else ""
            loc = t.get("location") or "任意"
            lines.append(
                f"· {t['name']} @ {loc} 危险{int(t['danger']*100)}% {need}\n  {t['desc']}"
            )
        lines.append(f"盘缠 {ADVENTURE_FEE} 灵石/次 · 藏宝图掉率约 {int(ADVENTURE_LOOT_P['map']*100)}%")
        return "\n".join(lines)

    @staticmethod
    def explore(
        c: Character,
        target_name: str = "野外",
        *,
        now: Optional[float] = None,
        use_ai: bool = True,
    ) -> Dict[str, Any]:
        t = now if now is not None else time.time()
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，不可探险。"}
        if c.status == CharacterStatus.MEDITATING:
            return {"success": False, "message": "闭关锁门，不可外出。请先 /出关。"}
        if c.offline_protected_until > t or c.reclusion_active:
            return {"success": False, "message": "归隐庇护中不可探险，请先 /出隐。"}
        cd = getattr(c, "adventure_cd_until", 0.0)
        if cd > t:
            return {"success": False, "message": f"气息未平，还需 {int(cd - t)} 秒方可再探。"}
        if c.spirit_stones < ADVENTURE_FEE:
            return {
                "success": False,
                "message": f"盘缠不足，外出需 {ADVENTURE_FEE} 灵石（囊中 {c.spirit_stones}）。",
            }

        target = resolve_target(target_name)
        if not target:
            return {"success": False, "message": f"未知探险目标：{target_name}。输入 /探险 查看列表。"}

        # 可选：自动迁跃到秘境入口
        travel_note = ""
        if target.get("location") and c.location != target["location"]:
            c.location = target["location"]
            travel_note = f"先至【{target['location']}】。"

        c.spirit_stones -= ADVENTURE_FEE
        p = _success_prob(c, target)
        # 规则骰（权威）
        roll = random.random()
        rule_success = roll < p

        gain_max, loss_max = _exp_caps(c, target, rule_success)
        stones_cap = _stones_cap(c, target)
        qi = global_qi_multiplier()

        ai_prop = None
        if use_ai:
            try:
                from ai.gateway import ai_available, _chat_json

                if ai_available():
                    inv = "、".join(c.inventory[:8]) or "无"
                    ai_prop = _chat_json(
                        "你是修仙世界「外出探险」叙事裁决。只输出严格 JSON。\n"
                        f"修士：{c.name}（{c.realm.name}）战力约{int(CombatEngine.calculate_power(c))} "
                        f"灵石{c.spirit_stones} 行囊：{inv}\n"
                        f"目标：{target['name']} @ {target.get('location') or '山野'} "
                        f"危险度{target['danger']} 门槛境界{target['min_tier']}+\n"
                        f"时令：{season_status_text()} 全服灵气稀释 {qi:.2f}x\n"
                        f"规则先验成功率 {p:.2f}；规则已判定本局成败为 "
                        f"{'成功' if rule_success else '失败'}（你必须服从）。\n"
                        "输出 JSON：\n"
                        "{\"success\":bool,\"narrative\":\"80-160字\","
                        "\"exp_delta\":int,\"stones_delta\":int,\"lifespan_years\":float,"
                        "\"events\":[{\"title\":\"\",\"text\":\"\",\"sin\":0,\"merit\":0,"
                        "\"attitude_npc\":\"\",\"attitude_delta\":0}]}"
                        "\n硬约束：success 必须与规则判定一致；"
                        f"成功时 exp_delta 在 0~{gain_max}，失败时在 -{loss_max}~0；"
                        f"stones_delta 在 ±{stones_cap}；lifespan_years 在 -1.5~0.5；"
                        "events 至多 1 条，不得虚构不在场人物重大事件。"
                        "loot 由规则独立掷骰，你不要输出 loot。"
                    )
            except Exception:
                ai_prop = None

        success = rule_success
        exp_delta = 0
        stones_delta = 0
        lifespan_years = 0.0
        events: List[Dict[str, Any]] = []
        narrative = ""
        source = "rule"

        if ai_prop and ai_prop.get("narrative"):
            narrative = str(ai_prop["narrative"])[:400]
            source = "ai"
            try:
                exp_delta = int(ai_prop.get("exp_delta") or 0)
            except Exception:
                exp_delta = 0
            try:
                stones_delta = int(ai_prop.get("stones_delta") or 0)
            except Exception:
                stones_delta = 0
            try:
                lifespan_years = float(ai_prop.get("lifespan_years") or 0.0)
            except Exception:
                lifespan_years = 0.0
            evs = ai_prop.get("events") or []
            if isinstance(evs, list) and evs:
                events = evs[:1]
            # success 以规则为准
            success = rule_success
        else:
            narrative = _local_narrative(c, target, success)
            source = "local"
            if success:
                exp_delta = random.randint(gain_max // 2, gain_max)
                stones_delta = random.randint(0, stones_cap)
            else:
                exp_delta = -random.randint(loss_max // 2, loss_max)
                stones_delta = -random.randint(0, stones_cap // 2)

        # 钳制
        if success:
            exp_delta = max(0, min(gain_max, exp_delta))
        else:
            exp_delta = max(-loss_max, min(0, exp_delta))
        stones_delta = max(-stones_cap, min(stones_cap, stones_delta))
        lifespan_years = max(-ADVENTURE_LIFESPAN_BURN_MAX, min(0.5, lifespan_years))
        if not success and lifespan_years > 0:
            lifespan_years = min(0.0, lifespan_years)

        # 规则掉落
        loot = _roll_loot(success, random.Random())
        # 若 AI 瞎给 loot 我们已忽略

        # 落账
        before_exp = c.realm.current_exp
        c.realm.current_exp = max(0, min(c.realm.max_exp, c.realm.current_exp + exp_delta))
        actual_exp = c.realm.current_exp - before_exp
        c.spirit_stones = max(0, c.spirit_stones + stones_delta)
        if lifespan_years < 0:
            c.lifespan.burn_lifespan(-lifespan_years)
        elif lifespan_years > 0:
            c.lifespan.add_lifespan(lifespan_years)

        loot_lines = []
        for item in loot:
            name = item["name"]
            for _ in range(int(item.get("qty") or 1)):
                c.inventory.append(name)
            loot_lines.append(name)

        ev_summaries = []
        for ev in events:
            title = str(ev.get("title") or "途中异事")
            text = str(ev.get("text") or "")[:120]
            try:
                sin = int(ev.get("sin") or 0)
            except Exception:
                sin = 0
            try:
                merit = int(ev.get("merit") or 0)
            except Exception:
                merit = 0
            sin = max(-EVENT_EFFECT_CAPS.get("sin", 40), min(EVENT_EFFECT_CAPS.get("sin", 40), sin))
            merit = max(-EVENT_EFFECT_CAPS.get("merit", 40), min(EVENT_EFFECT_CAPS.get("merit", 40), merit))
            if sin > 0:
                c.karma.add_sin(sin)
            if merit > 0:
                c.karma.add_merit(merit)
            npc_name = str(ev.get("attitude_npc") or "").strip()
            att_d = int(ev.get("attitude_delta") or 0)
            if npc_name and att_d:
                try:
                    from storage.db import CharacterRepository
                    from core.npc_mind import shift_attitude
                    npc = CharacterRepository.get_by_name(npc_name)
                    if npc and npc.id != c.id:
                        shift_attitude(npc, c.id, max(-10, min(10, att_d)), reason="探险事件")
                except Exception:
                    pass
            ev_summaries.append(f"【{title}】{text}")

        c.adventure_cd_until = t + ADVENTURE_COOLDOWN_MIN * 60.0 / max(0.001, time_scale())
        if success:
            try:
                from core.sect_contrib import sync_ring

                sync_ring(c, "explore", now=t)
            except Exception:
                pass

        lines = [
            travel_note + narrative if travel_note else narrative,
            (
                f"【探险{'成功' if success else '失败'}】"
                f"修为 {actual_exp:+d} · 灵石 {stones_delta:+d}"
                + (f" · 寿元 {lifespan_years:+.2f}" if lifespan_years else "")
            ),
        ]
        if loot_lines:
            lines.append("拾获：" + "、".join(loot_lines))
        else:
            lines.append("此行无额外拾获。" if success else "败走山门，一无所获。")
        lines.extend(ev_summaries)
        # 探险成功小概率奇遇链
        if success:
            try:
                from core.event_chains import EventChainEngine

                ch = EventChainEngine.maybe_start(c, trigger="adventure")
                if ch:
                    st = ch.steps[0]
                    opts = " | ".join(f"{x['id']}.{x['label']}" for x in st["choices"])
                    lines.append(f"\n【奇遇 · {ch.title}】{st['prompt']}\n选项：{opts}（/奇遇 <n>）")
            except Exception:
                pass
        lines.append(f"（盘缠已耗 {ADVENTURE_FEE} 灵石 · 下次可探约 {ADVENTURE_COOLDOWN_MIN:.0f} 设计分钟后）")

        return {
            "success": True,
            "combat_success": success,
            "source": source,
            "message": "\n".join(lines),
            "narrative": narrative,
            "target": target["name"],
            "exp_delta": actual_exp,
            "stones_delta": stones_delta,
            "lifespan_years": lifespan_years,
            "loot": loot,
            "events": ev_summaries,
            "prob": round(p, 3),
        }
