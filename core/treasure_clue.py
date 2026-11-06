"""
寻宝线索链（spec: gallery-gameplay §5）：挂图实体的前置线索阶段。

状态落 ItemEntity.custom_metadata["clue_chain"]（随图走、旧图缺省即未
激活）；终局开匣仍走现行 TreasureEngine.dig，本模块只提供：激活
（/宝图 顺带）、推进抉择（/寻宝）、开匣后完成奖励钩子。链层数值独立
小账（§5.5）：单步/单链惩罚子顶、完成奖励 XOR（seed=图 uid 的 hash
定支）、激活与奖励的现实日上限，计数落 WorldState KV
treasure_chain_daily:{char_id}。全部生成由 seed 确定性派生，重复操作
不重抽、不重发（§5.6：settled / bonus_paid 先落盘再发奖，at-most-once）。
"""
from __future__ import annotations

import hashlib
import random
import time
from datetime import date
from typing import Any, Dict, List, Optional

from core.character_integrity import CharacterIntegrity, CharacterIntegrityError
from core.items import ItemKind

# ---- §5.5 写死数字 -------------------------------------------------------
DAILY_ACTIVATION_MAX = 3
STEP_PENALTY_CAPS = {"stones": 20, "exp": 30, "dao_heart": 3, "sin": 5}
CHAIN_PENALTY_CAPS = {"stones": 40, "exp": 60, "dao_heart": 5, "sin": 10}
GUARDIAN_POWER_BASE = 60
GUARDIAN_POWER_PER_TIER = 45
BYPASS_COST_STONES = 20
BONUS_STONES_PER_TIER = 15
BONUS_STONES_CAP = 60
BONUS_EXP_PER_TIER = 30
BONUS_EXP_CAP = 120
DAILY_BONUS_STONES_CAP = 120
DAILY_BONUS_EXP_CAP = 240

DAILY_KEY_PREFIX = "treasure_chain_daily:"
DONE_KEY_PREFIX = "treasure_chain_done:"

#: dig / 自由破局成功且可发链完成奖励的 outcome（§5.3）
CHEST_BONUS_OUTCOMES = frozenset({
    "perfect_solve", "brute_force", "combat_victory", "scar_created",
    "free_action_success",
})

_KIND_CN = {"guardian": "守卫", "trap": "陷阱", "riddle": "谜题"}
# 五行相克（A 克 B）：标准五行克制环
_KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
_TRAP_ELEMENTS = ["金", "木", "水", "火", "土"]

_RIDDLE_TEMPLATES = [
    "残碑苔痕掩旧字，唯余一句谶语：{hint}。碑下三道阵纹流转，须择其一而行。",
    "古修手札残页自图背浮现：{hint}。页角三枚灵印未干，点中真印者过关。",
    "地脉回声如人低语：{hint}。声止处三扇石门并立，门楣各刻一象。",
]
_RIDDLE_HINTS = [
    "「潮信有期，月满则亏，盈者先退」",
    "「薪尽火传，灰下有星，寒者后至」",
    "「山不转路转，影不移心移，静者得先」",
    "「金声玉振，始条理而终条理，鸣者为尊」",
]
_RIDDLE_OPTIONS = [
    ["逐盈满之纹而行", "候月亏之纹而行", "弃纹听风而行"],
    ["扑灰寻星而行", "添薪助燃而行", "覆土灭火而行"],
    ["移山开路而行", "静候影移而行", "逐影疾行而行"],
    ["静听金声而行", "掩耳疾行而行", "碎玉止声而行"],
]
# 每组选项的正确下标（与 _RIDDLE_HINTS 的语义对应：亏/星/静/鸣）
_RIDDLE_ANSWERS = [1, 0, 1, 0]

_GUARDIAN_TEXT = "前方古道有守卫盘踞，煞气隐现。抉择：/寻宝 1 斗（战力检定）｜/寻宝 2 避（灵石20买路）｜/寻宝 3 退（不结算）"
_TRAP_TEXT = "脚下阵纹暗亮，此地设有五行陷阱（{element}象）。抉择：/寻宝 1 破阵（以灵根生克解之）｜/寻宝 2 硬闯（必付小额代价）｜/寻宝 3 退（不结算）"
_RIDDLE_TEXT_HEAD = "谜题当前，答对免罚、答错向前失败（每步只许答一次）。抉择：/寻宝 1|2|3"


def _today_str(now: Optional[float] = None) -> str:
    return date.fromtimestamp(now if now is not None else time.time()).isoformat()


def _daily_state(char_id: str, now: Optional[float] = None) -> Dict[str, Any]:
    from storage.db import WorldStateRepository

    raw = WorldStateRepository.get(DAILY_KEY_PREFIX + str(char_id)) or {}
    today = _today_str(now)
    if not isinstance(raw, dict) or raw.get("date") != today:
        return {"date": today, "starts": 0, "bonus_stones": 0, "bonus_exp": 0}
    return {
        "date": today,
        "starts": int(raw.get("starts") or 0),
        "bonus_stones": int(raw.get("bonus_stones") or 0),
        "bonus_exp": int(raw.get("bonus_exp") or 0),
    }


def _save_daily_state(char_id: str, state: Dict[str, Any]) -> None:
    from storage.db import WorldStateRepository

    WorldStateRepository.set(DAILY_KEY_PREFIX + str(char_id), state)


def steps_for_tier(tier: Any) -> int:
    """§5.1：common/fine 2 步、rare/ancient 3 步（tier 1/2→2，≥3→3）。"""
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 2
    return 2 if t <= 2 else 3


def bonus_branch_for_seed(seed: str) -> str:
    """§5.5：完成奖励支由 hash(seed) 定，激活时写死、不可变、不可操纵。"""
    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    return "stones" if digest[0] % 2 == 0 else "exp"


def bonus_amount(branch: str, tier: Any) -> int:
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 2
    if branch == "stones":
        return min(BONUS_STONES_CAP, BONUS_STONES_PER_TIER * t)
    return min(BONUS_EXP_CAP, BONUS_EXP_PER_TIER * t)


def _generate_steps(tmap: Any, char: Any) -> List[Dict[str, Any]]:
    """seed=图 uid 确定性生成全部线索步（节点/类型/谜题正解同图同链可复现）。"""
    seed = str(tmap.uid)
    rng = random.Random(f"clue-chain:{seed}")
    from core.world_grid import WorldGridEngine

    nodes = WorldGridEngine.list_nodes()
    target_id = (tmap.custom_metadata or {}).get("target_node_id", "")
    curr = WorldGridEngine.get_node(getattr(char, "location", "") or "")
    curr_id = curr.id if curr else ""
    pool = [n for n in nodes if n.id != target_id and n.id != curr_id]
    # 非安全区优先（§5.1），同类内由 rng 定序
    unsafe = [n for n in pool if not n.is_safe]
    safe = [n for n in pool if n.is_safe]
    rng.shuffle(unsafe)
    rng.shuffle(safe)
    ordered = unsafe + safe

    n_steps = steps_for_tier(getattr(tmap, "tier", 2))
    kinds = ["guardian", "trap", "riddle"]
    rng.shuffle(kinds)
    steps: List[Dict[str, Any]] = []
    for i in range(n_steps):
        node = ordered[i % len(ordered)] if ordered else curr
        kind = kinds[i % len(kinds)]
        step: Dict[str, Any] = {
            "node_id": node.id if node else "",
            "node_name": node.base_name if node else "",
            "kind": kind,
            "riddle_text": "",
            "settled": False,
            "outcome": "",
        }
        if kind == "riddle":
            tpl_i = rng.randrange(len(_RIDDLE_TEMPLATES))
            hint_i = rng.randrange(len(_RIDDLE_HINTS))
            step["riddle_text"] = _RIDDLE_TEMPLATES[tpl_i].format(hint=_RIDDLE_HINTS[hint_i])
            step["options"] = list(_RIDDLE_OPTIONS[hint_i])
            step["answer"] = _RIDDLE_ANSWERS[hint_i]
        elif kind == "trap":
            step["trap_element"] = _TRAP_ELEMENTS[rng.randrange(len(_TRAP_ELEMENTS))]
            step["riddle_text"] = _TRAP_TEXT.format(element=step["trap_element"])
        else:
            step["riddle_text"] = _GUARDIAN_TEXT
        steps.append(step)
    return steps


def get_chain(tmap: Any) -> Optional[Dict[str, Any]]:
    chain = (getattr(tmap, "custom_metadata", None) or {}).get("clue_chain")
    return chain if isinstance(chain, dict) else None


def chain_summary(tmap: Any) -> Optional[Dict[str, Any]]:
    """命盘 items 宝图项的 clue_chain 摘要（§10.1）；未激活为 None。"""
    chain = get_chain(tmap)
    if not chain:
        return None
    steps = chain.get("steps") or []
    idx = int(chain.get("step_index") or 0)
    current = steps[idx] if 0 <= idx < len(steps) else None
    return {
        "status": chain.get("status", ""),
        "step": min(idx + 1, len(steps)) if steps else 0,
        "total_steps": len(steps),
        "current_node_name": (current or {}).get("node_name", "") if current else "",
    }


def _current_step_text(chain: Dict[str, Any]) -> str:
    steps = chain.get("steps") or []
    idx = int(chain.get("step_index") or 0)
    total = len(steps)
    status = chain.get("status")
    if status == "awaiting_chest":
        return "线索已尽，宝图真穴已明。赴宝图目标节点 /挖宝 开匣，另有线索完成之赏。"
    if status == "completed":
        return "此图线索链已走完并开匣结案。"
    if status == "abandoned":
        return "此图线索链已弃，图本身仍可直赴目标 /挖宝（不可再激活新链）。"
    if idx >= total:
        return "线索已尽，赴宝图目标节点 /挖宝 开匣。"
    step = steps[idx]
    lines = [
        f"【寻宝线索】第 {idx + 1}/{total} 线索 · {_KIND_CN.get(step.get('kind'), '线索')} @【{step.get('node_name')}】",
        str(step.get("riddle_text") or ""),
    ]
    if step.get("kind") == "riddle":
        opts = step.get("options") or []
        lines.append(_RIDDLE_TEXT_HEAD)
        for i, opt in enumerate(opts):
            lines.append(f"  {i + 1}. {opt}")
    lines.append("赴该节点后以 /寻宝 1|2|3 抉择；异地 /寻宝 只看谶语不结算。")
    return "\n".join(lines)


class TreasureClueEngine:
    """线索链裁决引擎（规则唯一权威；叙事为本地模板，AI 不可用零影响）。"""

    # ------------------------------------------------------------------
    # 激活（/宝图 顺带，§5.3）
    # ------------------------------------------------------------------
    @staticmethod
    def maybe_activate_on_read(char: Any, tmap: Any, now: Optional[float] = None) -> Dict[str, Any]:
        """read_map 路径挂接：未激活且未达日限时顺带激活并返回追加文本段。

        返回 {text, changed}：changed=True 表示链已写入图实体，调用方须
        CharacterRepository.save(char) 落盘。门禁：assert_alive（§11）。
        已激活只读返回进度；已弃/已完明示不可再激活；达日限只读不激活。
        """
        chain = get_chain(tmap)
        if chain:
            return {"text": "\n\n" + _current_step_text(chain), "changed": False}
        try:
            CharacterIntegrity.assert_alive(char, now=now)
        except CharacterIntegrityError as e:
            return {"text": "", "changed": False, "error": str(e)}
        daily = _daily_state(char.id, now)
        if daily["starts"] >= DAILY_ACTIVATION_MAX:
            return {
                "text": f"\n\n【寻宝线索】今日已激活 {DAILY_ACTIVATION_MAX} 条线索链（现实日上限），此图只读不激活，明日再来。",
                "changed": False,
            }
        seed = str(tmap.uid)
        chain = {
            "version": 1,
            "status": "active",
            "seed": seed,
            "steps": _generate_steps(tmap, char),
            "step_index": 0,
            "activated_at": now if now is not None else time.time(),
            "activated_by": char.id,
            "completed_at": 0.0,
            "bonus_branch": bonus_branch_for_seed(seed),
            "bonus_paid": False,
            "penalties": {"stones": 0, "exp": 0, "dao_heart": 0, "sin": 0},
        }
        tmap.custom_metadata["clue_chain"] = chain
        daily["starts"] += 1
        _save_daily_state(char.id, daily)
        return {
            "text": (
                f"\n\n【寻宝线索 · 已激活】此图暗藏 {len(chain['steps'])} 条线索，走完再开匣另有完成之赏"
                f"（奖励支已由天机定死，不可改）。\n" + _current_step_text(chain)
            ),
            "changed": True,
        }

    @staticmethod
    def activate(char: Any, tmap: Any, now: Optional[float] = None) -> Dict[str, Any]:
        """显式激活入口（测试/直调）：语义同 maybe_activate_on_read。"""
        return TreasureClueEngine.maybe_activate_on_read(char, tmap, now=now)

    # ------------------------------------------------------------------
    # 查看 / 放弃
    # ------------------------------------------------------------------
    @staticmethod
    def _find_chain_map(char: Any, want_active: bool = True) -> Optional[Any]:
        maps = char.find_items_by_kind(ItemKind.TREASURE_MAP)
        fallback = None
        for m in maps:
            chain = get_chain(m)
            if not chain:
                continue
            if chain.get("status") in ("active", "awaiting_chest"):
                return m
            if fallback is None:
                fallback = m
        return None if want_active else (fallback or (maps[0] if maps else None))

    @staticmethod
    def view_text(char: Any) -> str:
        tmap = TreasureClueEngine._find_chain_map(char, want_active=False)
        if not tmap:
            return "行囊中并无藏宝图。先 /宝图 研读宝图即可激活其寻宝线索链。"
        chain = get_chain(tmap)
        if not chain:
            return "此图尚未激活线索链。/宝图 研读即可激活（每日至多 3 条）。"
        return f"【{tmap.name}】\n" + _current_step_text(chain)

    @staticmethod
    def abandon(char: Any, now: Optional[float] = None) -> Dict[str, Any]:
        """弃链：status=abandoned，该图不可再激活（§5.3 裁定）；图保留可直挖。"""
        try:
            CharacterIntegrity.assert_alive(char, now=now)
            CharacterIntegrity.assert_idle(char, action="/寻宝")
        except CharacterIntegrityError as e:
            return {"success": False, "message": str(e), "changed": False}
        tmap = TreasureClueEngine._find_chain_map(char)
        chain = get_chain(tmap) if tmap else None
        if not tmap or not chain or chain.get("status") not in ("active", "awaiting_chest"):
            return {"success": False, "message": "当前没有进行中的线索链可弃。", "changed": False}
        chain["status"] = "abandoned"
        return {
            "success": True,
            "changed": True,
            "message": "已弃此图线索链。此图不可再激活新链，但仍可直赴目标节点 /挖宝 开匣。",
        }

    # ------------------------------------------------------------------
    # 推进抉择（/寻宝 1|2|3，§5.3）
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_penalty(char: Any, chain: Dict[str, Any], want: Dict[str, int]) -> Dict[str, int]:
        """按单步子顶与单链累计子顶截断后落账（寿元恒 0）；返回实际落账量。"""
        penalties = chain.setdefault("penalties", {"stones": 0, "exp": 0, "dao_heart": 0, "sin": 0})
        applied: Dict[str, int] = {}
        for key in ("stones", "exp", "dao_heart", "sin"):
            want_amt = max(0, min(int(want.get(key, 0)), STEP_PENALTY_CAPS[key]))
            room = max(0, CHAIN_PENALTY_CAPS[key] - int(penalties.get(key, 0)))
            amt = min(want_amt, room)
            applied[key] = amt
            penalties[key] = int(penalties.get(key, 0)) + amt
        if applied["stones"]:
            char.spirit_stones = max(0, char.spirit_stones - applied["stones"])
        if applied["exp"]:
            char.realm.current_exp = max(0, char.realm.current_exp - applied["exp"])
        if applied["dao_heart"]:
            char.karma.dao_heart = max(0, char.karma.dao_heart - applied["dao_heart"])
        if applied["sin"]:
            char.karma.sin_value += applied["sin"]
        return applied

    @staticmethod
    def _penalty_text(applied: Dict[str, int]) -> str:
        parts = []
        if applied.get("stones"):
            parts.append(f"灵石 -{applied['stones']}")
        if applied.get("exp"):
            parts.append(f"修为 -{applied['exp']}")
        if applied.get("dao_heart"):
            parts.append(f"道心 -{applied['dao_heart']}")
        if applied.get("sin"):
            parts.append(f"业力 +{applied['sin']}")
        return "；".join(parts)

    @staticmethod
    def _settle_step(char: Any, chain: Dict[str, Any], step: Dict[str, Any], idx: int,
                     outcome: str, narrative: str, applied: Dict[str, int]) -> Dict[str, Any]:
        """先写 settled/outcome 并推进 step_index（随角色行落盘），再回叙事。"""
        step["settled"] = True
        step["outcome"] = outcome
        chain["step_index"] = idx + 1
        total = len(chain.get("steps") or [])
        done = chain["step_index"] >= total
        if done:
            chain["status"] = "awaiting_chest"
        pen_text = TreasureClueEngine._penalty_text(applied)
        msg = f"【线索结算 · {outcome}】{narrative}"
        if pen_text:
            msg += f"\n落账：{pen_text}（寿元无损）。"
        if done:
            msg += "\n\n" + _current_step_text(chain)
        else:
            msg += f"\n进度：第 {chain['step_index']}/{total} 线索已结。\n\n" + _current_step_text(chain)
        return {
            "success": True,
            "changed": True,
            "settled": True,
            "outcome": outcome,
            "message": msg,
        }

    @staticmethod
    def choose(char: Any, choice: str, now: Optional[float] = None) -> Dict[str, Any]:
        """在当前步所指节点作出抉择。异地不结算不推进（方位指引同 dig 范式）；
        结算先写 settled/outcome/penalties（调用方随角色行落盘）再回叙事。"""
        try:
            CharacterIntegrity.assert_alive(char, now=now)
            CharacterIntegrity.assert_idle(char, action="/寻宝")
        except CharacterIntegrityError as e:
            return {"success": False, "message": str(e), "changed": False}

        tmap = TreasureClueEngine._find_chain_map(char)
        chain = get_chain(tmap) if tmap else None
        if not tmap or not chain:
            return {"success": False, "message": "当前没有进行中的线索链。先 /宝图 激活一张宝图的线索。", "changed": False}
        if chain.get("status") == "awaiting_chest":
            return {"success": True, "message": _current_step_text(chain), "changed": False}
        if chain.get("status") != "active":
            return {"success": False, "message": _current_step_text(chain), "changed": False}

        chain.setdefault("penalties", {"stones": 0, "exp": 0, "dao_heart": 0, "sin": 0})
        steps = chain.get("steps") or []
        idx = int(chain.get("step_index") or 0)
        if idx >= len(steps):
            chain["status"] = "awaiting_chest"
            return {"success": True, "message": _current_step_text(chain), "changed": True}
        step = steps[idx]
        if step.get("settled"):
            # 幂等：已结算步只回摘要，不二次扣罚（§5.6-2）
            return {
                "success": True,
                "changed": False,
                "message": f"此步已结算（{step.get('outcome')}），进度 {idx}/{len(steps)}。\n" + _current_step_text(chain),
            }

        # 地点门禁：不在本步节点 → 方位指引、零落盘变化
        from core.world_grid import WorldGridEngine
        from core.treasure_system import calculate_fengshui_direction

        curr_node = WorldGridEngine.get_node(char.location)
        # 步节点以 node_name 为准解析（角色 location 全仓为地名字符串口径，
        # 与 dig 的 target_node_name 比对同范式）；node_id 仅作兜底。
        # 注：手工/存量步数据可能出现 id 与 name 不一致，此时以 name 为准，
        # 否则地点门禁会被错误的 id 误放行。
        step_node = WorldGridEngine.get_node(step.get("node_name", "")) or WorldGridEngine.get_node(step.get("node_id", ""))
        if not curr_node or not step_node or curr_node.id != step_node.id:
            guide = calculate_fengshui_direction(curr_node, step_node)
            return {
                "success": False,
                "wrong_location": True,
                "changed": False,
                "message": (
                    f"尚未抵达本步线索之地【{step.get('node_name')}】。\n"
                    f"方位卦象：【{guide.get('bagua')}】{guide.get('clue', '')}\n"
                    f"抵达后再 /寻宝 1|2|3 抉择，此行不结算、不推进。"
                ),
            }

        choice = (choice or "").strip()
        kind = step.get("kind")
        tier = int(getattr(tmap, "tier", 2) or 2)
        outcome = ""
        narrative = ""
        penalty: Dict[str, int] = {}

        if choice == "3" and kind in ("guardian", "trap"):
            return {
                "success": True,
                "changed": False,
                "message": "你暂且退开，未作抉择。此步未结算、无惩罚，他日可再来。",
            }

        if kind == "guardian":
            if choice == "1":  # 斗
                from core.combat import CombatEngine

                power = CombatEngine.calculate_power(char)
                guardian_power = GUARDIAN_POWER_BASE + tier * GUARDIAN_POWER_PER_TIER
                if power >= guardian_power:
                    outcome = "win"
                    narrative = f"你仗剑而上，战力（{int(power)}）压过守卫（{guardian_power}），守卫抱拳退开，让出古道。"
                else:
                    outcome = "fail_forward"
                    penalty = {"exp": 30, "dao_heart": 3, "sin": 5}
                    narrative = f"守卫战力（{guardian_power}）胜你一筹（{int(power)}），你负伤遁过其侧——路是通了，人也狼狈。"
            elif choice == "2":  # 避：买路 20 灵石（计入灵石惩罚顶，§9）
                try:
                    CharacterIntegrity.assert_currency(char, BYPASS_COST_STONES)
                except CharacterIntegrityError:
                    return {
                        "success": False,
                        "changed": False,
                        "message": f"灵石不足 {BYPASS_COST_STONES}，买路不可选（零副作用）。可 /寻宝 1 斗或 /寻宝 3 退。",
                    }
                room = max(0, CHAIN_PENALTY_CAPS["stones"] - int(chain["penalties"].get("stones", 0)))
                cost = min(BYPASS_COST_STONES, room)
                if cost:
                    CharacterIntegrity.deduct_currency(char, cost)
                    chain["penalties"]["stones"] = int(chain["penalties"].get("stones", 0)) + cost
                outcome = "bypass"
                narrative = f"你奉上灵石 {cost} 买路，守卫掂了掂，侧身让开古道。"
                applied = {"stones": cost, "exp": 0, "dao_heart": 0, "sin": 0}
                return TreasureClueEngine._settle_step(char, chain, step, idx, outcome, narrative, applied)
            else:
                return {"success": False, "changed": False, "message": "守卫当前：/寻宝 1 斗｜/寻宝 2 避（灵石20）｜/寻宝 3 退。"}
        elif kind == "trap":
            trap_element = step.get("trap_element") or "土"
            if choice == "1":  # 破阵：灵根首元素生克
                elements = getattr(getattr(char, "spiritual_root", None), "elements", None) or []
                player_element = getattr(elements[0], "value", str(elements[0])) if elements else ""
                if _KE.get(player_element) == trap_element:
                    outcome = "win"
                    narrative = f"你以{player_element}克{trap_element}，阵纹应手而解，陷阱无声熄灭。"
                elif _KE.get(trap_element) == player_element:
                    outcome = "fail_forward"
                    penalty = {"exp": 30, "dao_heart": 3, "sin": 5}
                    narrative = f"陷阱之{trap_element}反克你灵根{player_element}，阵光倒卷，你踉跄穿过，代价不轻。"
                else:
                    outcome = "bypass"
                    penalty = {"exp": 15}
                    narrative = f"你灵根{player_element}与陷阱之{trap_element}互不相克，费一番手脚绕开阵眼（修为小损）。"
            elif choice == "2":  # 硬闯：必付小额惩罚
                outcome = "bypass"
                penalty = {"stones": 10, "exp": 15}
                narrative = "你硬闯阵纹，衣袂尽裂、灵石散落，总算穿了过去。"
            else:
                return {"success": False, "changed": False, "message": "陷阱当前：/寻宝 1 破阵｜/寻宝 2 硬闯｜/寻宝 3 退。"}
        elif kind == "riddle":
            if choice not in ("1", "2", "3"):
                return {"success": False, "changed": False, "message": _current_step_text(chain)}
            answer = int(step.get("answer") or 0)
            if int(choice) - 1 == answer:
                outcome = "win"
                narrative = "灵印微光一闪，谜题应声而解，前路豁然开朗。"
            else:
                outcome = "fail_forward"
                penalty = {"exp": 30, "dao_heart": 3}
                narrative = "灵印骤暗，谶语反噬心神——答错了。此步只许答一次，你带着教训向前。（不可重答）"
        else:
            return {"success": False, "changed": False, "message": "未知线索类型。"}

        applied = TreasureClueEngine._apply_penalty(char, chain, penalty)
        return TreasureClueEngine._settle_step(char, chain, step, idx, outcome, narrative, applied)

    # ------------------------------------------------------------------
    # 终局完成奖励钩子（§5.3/§5.6）：dig 成功后由服务端两处出口调用
    # ------------------------------------------------------------------
    @staticmethod
    def snapshot_chain(char: Any) -> Optional[Dict[str, Any]]:
        """开匣前抓取链快照（dig 会耗图，链载体随之消亡，须先留底）。

        配对口径（MF-1）：快照只绑行囊首图——TreasureEngine.dig 与
        resolve_free_action 恒消耗 find_items_by_kind()[0]，且服务端两处
        出口都是快照紧贴 dig 调用、中间无背包变更，故首图即被耗图。
        不得再用 _find_chain_map 扫首个 active/awaiting 链：首图无链而
        次图 awaiting 时会错配发奖并烧掉次图链的 DONE 锚（奖励永失）。
        """
        import copy

        maps = char.find_items_by_kind(ItemKind.TREASURE_MAP)
        tmap = maps[0] if maps else None
        if not tmap:
            return None
        chain = get_chain(tmap)
        if not chain:
            return None
        return {
            "map_uid": str(tmap.uid),
            "map_tier": int(getattr(tmap, "tier", 2) or 2),
            "chain": copy.deepcopy(chain),
        }

    @staticmethod
    def on_chest_opened(char: Any, snapshot: Optional[Dict[str, Any]],
                        outcome: str, now: Optional[float] = None) -> Dict[str, Any]:
        """开匣成功钩子：链 awaiting_chest 时发放完成奖励并置 completed。

        幂等（§5.6-3）：treasure_chain_done:{图uid} 先落盘（bonus_paid 锚）
        再发奖，at-most-once；重入直接短路。奖励按完成者计日顶（§5.5）。
        无链/未走完/outcome 不在白名单 → 零动作（无链直挖零回归）。
        """
        if not snapshot or outcome not in CHEST_BONUS_OUTCOMES:
            return {"paid": False, "message": ""}
        chain = snapshot.get("chain") or {}
        if chain.get("status") != "awaiting_chest" or chain.get("bonus_paid"):
            return {"paid": False, "message": ""}
        from storage.db import WorldStateRepository

        map_uid = snapshot["map_uid"]
        done_key = DONE_KEY_PREFIX + map_uid
        if WorldStateRepository.get(done_key):
            return {"paid": False, "message": ""}
        tier = snapshot["map_tier"]
        branch = chain.get("bonus_branch") or bonus_branch_for_seed(snapshot["map_uid"])
        amount = bonus_amount(branch, tier)
        # 先落盘终态锚再发奖（at-most-once）
        WorldStateRepository.set(done_key, {
            "bonus_paid": True,
            "branch": branch,
            "amount_planned": amount,
            "completed_at": now if now is not None else time.time(),
            "completed_by": char.id,
        })
        daily = _daily_state(char.id, now)
        if branch == "stones":
            room = max(0, DAILY_BONUS_STONES_CAP - daily["bonus_stones"])
            pay = min(amount, room)
            if pay:
                char.spirit_stones += pay
                daily["bonus_stones"] += pay
                _save_daily_state(char.id, daily)
            msg = (
                f"\n\n【寻宝线索 · 完成奖励】线索链走完且开匣功成，天机赐赏灵石 +{pay}。"
                if pay else
                "\n\n【寻宝线索 · 完成】线索链已结案；今日灵石完成奖励已达上限 120，本次不发奖。"
            )
        else:
            room = max(0, DAILY_BONUS_EXP_CAP - daily["bonus_exp"])
            pay = min(amount, room)
            if pay:
                char.realm.current_exp = min(char.realm.max_exp, char.realm.current_exp + pay)
                daily["bonus_exp"] += pay
                _save_daily_state(char.id, daily)
            msg = (
                f"\n\n【寻宝线索 · 完成奖励】线索链走完且开匣功成，天机赐赏修为 +{pay}。"
                if pay else
                "\n\n【寻宝线索 · 完成】线索链已结案；今日修为完成奖励已达上限 240，本次不发奖。"
            )
        return {"paid": pay > 0, "branch": branch, "amount": pay, "message": msg}
