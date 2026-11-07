"""
仪式演出后端（game-feel-phase1 §4）：纯读拼装、零 AI、零导演调用。

- 命格（F5 修正口径）：借 DAO_BOON_CATALOG / AFFIX_POOL 的身份与文案，
  数值走 config.FATE_BOON_POWER，生效点为 CombatEngine.calculate_power
  乘子链尾（FateBoonEngine.power_bonus，无命格恒 1.0）。
- 待选状态机（口径 K2）：大境界突破成功时在裁决引擎内抽定落盘
  （Character.fate_pending，FIFO ≤2），选择走唯一函数 apply_fate_choice，
  仪式内外等价（C2）。
- ceremony 结构只增于既有响应，不落库（命格待选除外，它是结算的一部分）。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from config import FATE_BOON_MAX, FATE_BOON_POWER, FATE_BOON_POWER_CAP
from core.models import Character

# 词缀命格按灵根首元素过滤表（§4.2 定稿，按 stat_key 亲和）
AFFIX_BY_ELEMENT: Dict[str, List[str]] = {
    "金": ["破煞", "固元"],
    "木": ["生光", "凝神"],
    "水": ["凝神", "生光"],
    "火": ["嗜血", "破煞"],
    "土": ["固元", "凝神"],
    "风": ["破煞"],
    "雷": ["破煞", "嗜血"],
    "冰": ["凝神", "破煞"],
}

_FAIL_LINES = {
    "DEATH": "劫雷贯顶，道基尽碎——此身之事，已由天道另行收束。",
    "BASE_COLLAPSE": "雷火焚脉，道基崩摧，境界跌落——命还在，路还长。",
    "HEART_DEMON": "心魔乘隙，道心重挫——这一关，败给了心里的那个自己。",
    "WOUNDED": "神雷震体，经脉受创——功败垂成，调养之后再图。",
}

_TRIBULATION_PRELUDES = [
    "劫云自九天压下，{realm}的门槛就在雷光之间。",
    "天穹低鸣，劫气如潮——{realm}之关，到了。",
    "灵机倒卷，雷纹游走，这一劫避无可避。",
]


def fate_pool_for(character: Character) -> List[Dict[str, Any]]:
    """命格候选池（§4.2）：DAO_BOON 5 键 + 按灵根首元素过滤的词缀子集。"""
    from core.dungeon import DAO_BOON_CATALOG
    from core.items import AFFIX_POOL

    pool: List[Dict[str, Any]] = []
    for key, cfg in DAO_BOON_CATALOG.items():
        pool.append({
            "key": key,
            "name": cfg.get("name", key),
            "desc": cfg.get("desc", ""),
            "icon": cfg.get("icon", "✦"),
            "source": "dao",
        })
    elems: List[str] = []
    try:
        elems = [e.value for e in character.spiritual_root.elements]
    except Exception:
        elems = []
    first = elems[0] if elems else ""
    for affix_name in AFFIX_BY_ELEMENT.get(first, []):
        cfg = AFFIX_POOL.get(affix_name) or {}
        stat_key = cfg.get("stat_key") or ""
        if not stat_key:
            continue
        pool.append({
            "key": f"fate_{stat_key}",
            "name": affix_name,
            "desc": cfg.get("desc", ""),
            "icon": "✦",
            "source": "affix",
        })
    return pool


def draw_fate_pending(character: Character, *, rng=None) -> Optional[Dict[str, Any]]:
    """大境界成功分支尾部抽定（§4.2）：pending <2 时抽 3 个不重复候选
    （剔除已选 key）append 一抽；已满 2 抽返回 None（不抽）。"""
    pending = getattr(character, "fate_pending", None)
    if pending is None:
        character.fate_pending = pending = []
    if len(pending) >= 2:
        return None
    chosen_keys = {b.get("key") for b in (character.fate_boons or [])}
    pool = [c for c in fate_pool_for(character) if c["key"] not in chosen_keys]
    if len(pool) < 3:
        return None
    r = rng or random
    candidates = r.sample(pool, 3)
    draw = {
        "candidates": candidates,
        "from_tier": int(character.realm.tier),
        "drawn_at": time.time(),
    }
    pending.append(draw)
    return draw


def apply_fate_choice(character: Character, key: str) -> Dict[str, Any]:
    """唯一选择函数（§4.2）：只许取最老一抽（FIFO）中的 key；
    校验失败零副作用。仪式与命盘走同一命令同一函数。"""
    key = (key or "").strip()
    pending = getattr(character, "fate_pending", None) or []
    if not pending:
        return {"success": False, "message": "眼下并无待选命格。突破大境界成功时天道自会抽定。"}
    if len(getattr(character, "fate_boons", None) or []) >= FATE_BOON_MAX:
        return {"success": False, "message": f"命格已满（{FATE_BOON_MAX}），天道不容贪求。"}
    draw = pending[0]
    cand = None
    for c in draw.get("candidates") or []:
        if c.get("key") == key:
            cand = c
            break
    if cand is None:
        names = "、".join(
            f"{c.get('name')}（/命格 {c.get('key')}）" for c in draw.get("candidates") or [])
        return {"success": False, "message": f"此抽候选为：{names}。请从中择一。"}
    character.fate_pending = pending[1:]
    boon = {
        "key": cand["key"],
        "name": cand.get("name", cand["key"]),
        "from_tier": draw.get("from_tier", character.realm.tier),
        "chosen_at": time.time(),
    }
    character.fate_boons = list(character.fate_boons or []) + [boon]
    return {
        "success": True,
        "message": f"【命格既定】{boon['name']} 入命，自此随身。（/命格 查看）",
        "boon": boon,
    }


def fate_block(character: Character) -> Dict[str, Any]:
    """status 只增 fate 块（§6 总表）：已选 + 待选原样下发。"""
    return {
        "boons": list(getattr(character, "fate_boons", None) or []),
        "pending": list(getattr(character, "fate_pending", None) or []),
        "power_bonus": FateBoonEngine.power_bonus(character),
    }


def fate_panel_text(character: Character) -> str:
    """ /命格 无参文本（server/CLI 同源）。"""
    lines = ["【命格】突破大境界时天道抽定，三选其一，既定随身。"]
    boons = getattr(character, "fate_boons", None) or []
    if boons:
        lines.append("已定命格：")
        for b in boons:
            lines.append(f"· {b.get('name')}（{b.get('key')}）— 自{b.get('from_tier', '?')}阶得")
    else:
        lines.append("已定命格：暂无。")
    pending = getattr(character, "fate_pending", None) or []
    if pending:
        draw = pending[0]
        lines.append(f"待选（第 1 抽 / 共 {len(pending)} 抽）：")
        for c in draw.get("candidates") or []:
            lines.append(f"· {c.get('icon', '✦')} {c.get('name')} — {c.get('desc', '')}（/命格 {c.get('key')}）")
    else:
        lines.append("待选：暂无（突破大境界成功后抽定）。")
    return "\n".join(lines)


class FateBoonEngine:
    """命格战力乘子（§4.2）：连乘 config 表，FATE_BOON_POWER_CAP 截断。"""

    @staticmethod
    def power_bonus(character: Character) -> float:
        try:
            mult = 1.0
            for b in (getattr(character, "fate_boons", None) or []):
                mult *= float(FATE_BOON_POWER.get(b.get("key"), 1.0))
            return min(FATE_BOON_POWER_CAP, mult)
        except Exception:
            return 1.0


# ---------------- 仪式拼装（纯读，零 AI） ----------------

def _portrait_asset(character: Character, tier: int) -> Optional[str]:
    try:
        from core.gallery_assets import player_portrait_key

        return player_portrait_key(getattr(character, "gender", "") or "", tier)
    except Exception:
        return None


def build_breakthrough_ceremony(
    character: Character, attempt_result: Dict[str, Any], *, fate_drawn: bool = False,
) -> Dict[str, Any]:
    """突破幕（§4.2）：挂两条服务端出口，条件 is_major。"""
    success = bool(attempt_result.get("success"))
    new_realm = attempt_result.get("new_realm") or character.realm.name
    beats: List[Dict[str, Any]] = []
    demon_line = ""
    try:
        from core.heart_demon_state import DemonStateEngine

        s = DemonStateEngine.summary(character)
        if s.get("stage", 0) > 0:
            demon_line = f"心魔【{s.get('stage_name', '')}】（魔念 {s.get('seed', 0)}）在识海边缘低语。"
    except Exception:
        demon_line = ""
    target_tier = character.realm.tier if success else character.realm.tier + 1
    # 确定性选句：crc32 稳定哈希（内置 hash() 对 str 进程级盐化，不可复算）
    import zlib

    prelude_tpl = _TRIBULATION_PRELUDES[
        zlib.crc32(f"{character.id}:{target_tier}".encode("utf-8")) % len(_TRIBULATION_PRELUDES)]
    prelude_text = prelude_tpl.format(realm=new_realm)
    if demon_line:
        prelude_text += demon_line
    beats.append({
        "stage": "prelude",
        "text": prelude_text,
        "asset_key": _portrait_asset(character, target_tier),
        "choices": None,
    })
    if success:
        reveal_text = (
            f"【渡劫功成】晋【{new_realm}】，寿元 +{attempt_result.get('lifespan_gained', 0)} 岁。"
        )
    else:
        reveal_text = _FAIL_LINES.get(
            str(attempt_result.get("fail_tier") or ""),
            "渡劫功败垂成——命还在，路还长。",
        )
    beats.append({"stage": "reveal", "text": reveal_text, "asset_key": None, "choices": None})
    after_text = "雷云散尽，天地复归清明。"
    choices = None
    if success and fate_drawn:
        pending = getattr(character, "fate_pending", None) or []
        if pending:
            choices = list(pending[-1].get("candidates") or [])
            after_text = "天道垂鉴，命格三选其一——此刻不选，日后于命盘 /命格 择定亦可。"
    beats.append({"stage": "aftermath", "text": after_text, "asset_key": None, "choices": choices})
    return {
        "kind": "breakthrough",
        "beats": beats,
        "result_ref": {
            "success": success,
            "is_major": True,
            "new_realm": attempt_result.get("new_realm"),
            "lifespan_gained": attempt_result.get("lifespan_gained", 0.0),
            "fail_tier": attempt_result.get("fail_tier"),
            "fate_drawn": bool(fate_drawn),
            "fate_pending_count": len(getattr(character, "fate_pending", None) or []),
        },
        "skippable": True,
    }


def build_death_ceremony(character: Character, account) -> Optional[Dict[str, Any]]:
    """死亡幕（§4.4）：数据源全部已落账（traces[-1] 等）；无 trace 返回 None。"""
    traces = getattr(account, "traces", None) or []
    if not traces:
        return None
    trace = traces[-1]
    beats: List[Dict[str, Any]] = []
    prelude_lines: List[str] = []
    if getattr(trace, "fate_summary", ""):
        prelude_lines.append(trace.fate_summary)
    shadow = getattr(trace, "shadow", None) or []
    if shadow:
        top = max(shadow, key=lambda e: abs(e.value))
        prelude_lines.append(
            f"{top.npc_name} 与你的前世态度 {top.value:+d}，恩怨随影入轮回")
    prelude_lines.append(
        f"未了之诺 {len(getattr(trace, 'open_promises', None) or [])} 条 · "
        f"因果余绪 {len(shadow)} 条")
    beats.append({"stage": "prelude", "text": "\n".join(prelude_lines),
                  "asset_key": None, "choices": None})
    from core.inheritance import tombstone_text

    beats.append({"stage": "reveal", "text": tombstone_text(trace),
                  "asset_key": None, "choices": None})
    epitaph = getattr(trace, "life_epitaph", "") or ""
    after = "死讯已入江湖传闻，世人自有公论。"
    if epitaph:
        after += f"\n一生评语：{epitaph}"
    beats.append({"stage": "aftermath", "text": after, "asset_key": None, "choices": None})
    return {
        "kind": "death",
        "beats": beats,
        "result_ref": {
            "cause": trace.cause,
            "points_gained": trace.points_gained,
            "lifespan_lived": trace.lifespan_lived,
            "life_no": trace.life_no,
            "epitaph_present": bool(epitaph),
        },
        "skippable": True,
    }


def build_rebirth_ceremony(
    new_char: Character, account, *, karma_shadow: List[Dict[str, Any]],
    boosts_applied: List[str], legacy_points: int,
) -> Dict[str, Any]:
    """转世幕（§4.4）：呈现已结算的影子/抉择/新出身，不新增二次确认。"""
    beats: List[Dict[str, Any]] = []
    traces = getattr(account, "traces", None) or []
    prev_epitaph = ""
    if traces:
        prev_epitaph = getattr(traces[-1], "life_epitaph", "") or ""
    prelude = "真灵越过忘川，前尘如雾渐散。"
    if prev_epitaph:
        prelude += f"\n前世曰：{prev_epitaph}"
    beats.append({"stage": "prelude", "text": prelude, "asset_key": None, "choices": None})
    reveal_lines: List[str] = []
    if karma_shadow:
        reveal_lines.append("因果余绪及身：" + "、".join(
            f"{s.get('npc_name')} {s.get('value', 0):+d}" for s in karma_shadow))
    if boosts_applied:
        reveal_lines.append(f"道统点化已生效：{'、'.join(boosts_applied)}（余 {legacy_points} 点）")
    else:
        reveal_lines.append(f"本世未兑换道统传承（余 {legacy_points} 点）。")
    beats.append({"stage": "reveal", "text": "\n".join(reveal_lines),
                  "asset_key": None, "choices": None})
    origin = getattr(new_char, "origin", None) or {}
    after = "新一世，自此开局。"
    if origin:
        after = (
            f"出身：{origin.get('family_text', '')}。"
            f"落点{origin.get('birthplace', new_char.location)}，随身灵石 {origin.get('stones_final', new_char.spirit_stones)}。"
        )
    beats.append({"stage": "aftermath", "text": after, "asset_key": None, "choices": None})
    return {
        "kind": "rebirth",
        "beats": beats,
        "result_ref": {
            "name": new_char.name,
            "realm": new_char.realm.name,
            "legacy_points": legacy_points,
            "boosts_applied": list(boosts_applied or []),
            "shadow_count": len(karma_shadow or []),
            "origin_signature": origin.get("signature", "") if origin else "",
        },
        "skippable": True,
    }
