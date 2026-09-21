"""
天工造化：AI 生成丹药/法宝/妖兽，库内去重
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Set

from config import ITEM_CATALOG, SECRET_REALMS, ADVENTURE_EQUIPS, ADVENTURE_PILLS
from storage.db import GeneratedNameRepository
from ai.gateway import _chat_json, ai_available

_PILL_A = ["凝", "聚", "回", "养", "破", "洗", "固", "温", "淬", "安"]
_PILL_B = ["气", "神", "血", "魂", "骨", "灵", "丹", "露", "膏", "散"]
_PILL_C = ["丹", "露", "丸", "散", "膏"]
_EQ_A = ["青", "玄", "赤", "白", "紫", "墨", "金", "寒", "烈", "幽"]
_EQ_B = ["锋", "霄", "冥", "光", "煞", "灵", "铁", "影", "雷", "霜"]
_EQ_C = ["剑", "刀", "甲", "佩", "镜", "印", "珠", "盾", "镯", "冠"]
_MON_A = ["噬", "裂", "焚", "蚀", "噬", "缠", "啸", "噬"]
_MON_B = ["血", "骨", "炎", "霜", "雷", "雾", "影", "煞"]
_MON_C = ["蟒", "蝠", "蛛", "猿", "蛟", "雕", "狼", "蛛"]


def exclusion_names() -> Set[str]:
    names = set(ITEM_CATALOG.keys())
    names |= set(SECRET_REALMS.keys())
    try:
        from core.npc_roster import ROSTER
        names |= {r["name"] for r in ROSTER}
    except Exception:
        pass
    try:
        names |= GeneratedNameRepository.all_names()
    except Exception:
        pass
    return names


def _local_name(kind: str, banned: Set[str]) -> str:
    import uuid

    for _ in range(40):
        if kind == "pill":
            n = random.choice(_PILL_A) + random.choice(_PILL_B) + random.choice(_PILL_C)
        elif kind == "equip":
            n = random.choice(_EQ_A) + random.choice(_EQ_B) + random.choice(_EQ_C)
        else:
            n = random.choice(_MON_A) + random.choice(_MON_B) + random.choice(_MON_C)
        if n not in banned:
            return n
    # 兜底：短哈希后缀，避免库内「无名pillXX」反复撞名
    return f"无名{kind}{uuid.uuid4().hex[:4]}"


def _clamp_pill(data: Dict[str, Any], banned: Set[str]) -> Dict[str, Any]:
    name = str(data.get("name") or "").strip()[:12]
    if not name or name in banned:
        name = _local_name("pill", banned)
    try:
        mult = float(data.get("pill_exp_mult") or 0.15)
    except Exception:
        mult = 0.15
    mult = max(0.08, min(0.50, mult))
    grade = data.get("grade") or ("凡品" if mult < 0.25 else "人品" if mult < 0.45 else "地品")
    try:
        price = int(data.get("price") or (30 + int(mult * 400)))
    except Exception:
        price = 30
    price = max(10, min(2000, price))
    desc = str(data.get("desc") or f"{grade}丹。下次闭关修为 +{int(mult*100)}%。")[:80]
    return {
        "kind": "pill",
        "name": name,
        "grade": grade,
        "pill_exp_mult": round(mult, 2),
        "price": price,
        "desc": desc,
    }


def _clamp_equip(data: Dict[str, Any], banned: Set[str]) -> Dict[str, Any]:
    name = str(data.get("name") or "").strip()[:12]
    if not name or name in banned:
        name = _local_name("equip", banned)
    slot = str(data.get("slot") or "weapon")
    if slot not in ("weapon", "armor", "trinket"):
        slot = "weapon"
    try:
        bonus = float(data.get("power_bonus") or 0.03)
    except Exception:
        bonus = 0.03
    bonus = max(0.02, min(0.12, bonus))
    grade = data.get("grade") or ("凡品" if bonus < 0.045 else "人品" if bonus < 0.07 else "地品" if bonus < 0.11 else "天品")
    try:
        price = int(data.get("price") or (80 + int(bonus * 3000)))
    except Exception:
        price = 80
    price = max(30, min(8000, price))
    desc = str(data.get("desc") or f"{grade}法物。战力 +{int(bonus*100)}%。")[:80]
    return {
        "kind": "equip",
        "name": name,
        "slot": slot,
        "grade": grade,
        "power_bonus": round(bonus, 3),
        "price": price,
        "desc": desc,
    }


def _clamp_monster(data: Dict[str, Any], banned: Set[str]) -> Dict[str, Any]:
    name = str(data.get("name") or "").strip()[:12]
    if not name or name in banned:
        name = _local_name("monster", banned)
    try:
        tier = int(data.get("tier") or 1)
    except Exception:
        tier = 1
    tier = max(1, min(5, tier))
    try:
        danger = float(data.get("danger") or 0.3)
    except Exception:
        danger = 0.3
    danger = max(0.15, min(0.85, danger))
    desc = str(data.get("desc") or f"阶妖兽，盘踞山野。")[:80]
    return {
        "kind": "monster",
        "name": name,
        "tier": tier,
        "danger": round(danger, 2),
        "desc": desc,
    }


def forge(kind: str, hint: str = "") -> Dict[str, Any]:
    """kind: pill|equip|monster"""
    kind = (kind or "").strip().lower()
    if kind not in ("pill", "equip", "monster"):
        return {"success": False, "error": "类型须为 pill|equip|monster"}
    banned = exclusion_names()
    # 同类型禁名也要提醒 AI
    sample = list(banned)[:40]
    label = {"pill": "丹药", "equip": "法宝", "monster": "妖兽"}[kind]
    data = None
    if ai_available():
        try:
            from ai.play_prompts import forge_prompt

            prompt = forge_prompt(kind, hint, "、".join(sample))
        except Exception:
            if kind == "pill":
                schema = '{"name":"2~8字中文名","grade":"凡品|人品|地品","pill_exp_mult":0.08~0.5,"price":int,"desc":"功效"}'
            elif kind == "equip":
                schema = '{"name":"...","slot":"weapon|armor|trinket","grade":"...","power_bonus":0.02~0.12,"price":int,"desc":"..."}'
            else:
                schema = '{"name":"...","tier":1~5,"danger":0.15~0.85,"desc":"..."}'
            prompt = (
                f"为修仙世界生成一种新的{label}。理念提示：{hint or '随机'}\n"
                f"禁止使用这些已有名称：{'、'.join(sample)}\n"
                f"输出 JSON：{schema}\n硬约束：name 不得与禁止列表重复；数值落在括号区间内。"
            )
        data = _chat_json(prompt)
    if kind == "pill":
        obj = _clamp_pill(data or {}, banned)
    elif kind == "equip":
        obj = _clamp_equip(data or {}, banned)
    else:
        obj = _clamp_monster(data or {}, banned)

    name = obj["name"]
    # 二次撞名
    if name in banned:
        obj["name"] = _local_name(kind, banned)
        name = obj["name"]

    saved = GeneratedNameRepository.save(name, kind, obj)
    # 并入运行时货单，便于购买/穿戴
    if kind in ("pill", "equip"):
        ITEM_CATALOG[name] = {k: v for k, v in obj.items() if k != "kind"}
        ITEM_CATALOG[name]["kind"] = kind

    lines = [f"【天工造化】{label} · {obj.get('grade','')} —— {name}"]
    if kind == "pill":
        lines.append(f"下次闭关修为 +{int(obj['pill_exp_mult']*100)}% · 售价 {obj['price']} 灵石")
    elif kind == "equip":
        slot_cn = {"weapon": "武器", "armor": "护甲", "trinket": "饰品"}.get(obj["slot"], obj["slot"])
        lines.append(f"{slot_cn} · 战力 +{int(obj['power_bonus']*100)}% · 售价 {obj['price']} 灵石")
    else:
        lines.append(f"境界约 t{obj['tier']} · 危险 {int(obj['danger']*100)}%")
    lines.append(obj.get("desc") or "")
    lines.append("（名称已落库去重，后续不会再生成同名）")
    return {
        "success": True,
        "message": "\n".join(x for x in lines if x),
        "item": obj,
        "saved": saved,
    }


def list_generated(kind: str = "") -> List[Dict[str, Any]]:
    if kind:
        return GeneratedNameRepository.list_kind(kind)
    out = []
    for k in ("pill", "equip", "monster"):
        out.extend(GeneratedNameRepository.list_kind(k, 10))
    return out
