"""
会话内动作：自由文本 → 意图分类 → 规则落账 + NPC 响应
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

from config import ITEM_CATALOG, WORLD_LOCATIONS
from core.models import Character, CharacterStatus
from storage.db import CharacterRepository

INTENTS = ("dialogue", "gift", "attack", "steal", "kidnap", "trade")

_KW = {
    "kidnap": ["挟持", "擒住", "擒拿", "绑起来", "绑走", "掳走", "拿下", "生擒", "绑"],
    "attack": ["偷袭", "伏击", "斩杀", "灭杀", "拍死", "一掌", "一拳", "动手", "拍", "打", "杀", "斩"],
    "steal": ["顺走", "窃取", "摸走", "偷走", "偷", "摸"],
    "gift": ["奉上", "孝敬", "递给", "递上", "送上", "送给", "赠", "赠上"],
    "trade": ["交易", "出价", "买下", "购买", "换你", "卖我", "买", "卖", "换"],
}

# 长词优先，避免「打」误吞「一掌拍过去」
_pairs: List[Tuple[int, str, str]] = []
for _intent, _words in _KW.items():
    for _w in _words:
        _pairs.append((len(_w), _w, _intent))
_pairs.sort(reverse=True)


def classify_local(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    for _ln, w, intent in _pairs:
        if w in t:
            return {"intent": intent, "target_item": _extract_item(t), "stones": _extract_stones(t)}
    return {"intent": "dialogue", "target_item": "", "stones": 0}


def classify_ai(text: str, player: Character, npc: Character) -> Dict[str, Any]:
    """AI 分类；失败回退本地关键词。"""
    try:
        from ai.gateway import _chat_json, ai_available

        if not ai_available():
            return classify_local(text)
        inv = "、".join(player.inventory[:12]) or "无"
        prompt = (
            "你是修仙游戏意图分类器。只输出 JSON。\n"
            "intent 必须是：dialogue|gift|attack|steal|kidnap|trade 之一。\n"
            "gift：赠/递物品；attack：动手斗法；steal：偷窃；kidnap：擒拿绑人；trade：出价买卖；其余 dialogue。\n"
            f"玩家：{player.name} 行囊：{inv}\n"
            f"对象：{npc.name}\n"
            f"原文：{text[:180]}\n"
            '输出：{"intent":"...","target_item":"","stones":0}'
        )
        data = _chat_json(prompt)
        if not data:
            return classify_local(text)
        intent = str(data.get("intent") or "").strip().lower()
        if intent not in INTENTS:
            intent = "dialogue"
        item = str(data.get("target_item") or "").strip()[:40]
        try:
            stones = int(data.get("stones") or 0)
        except Exception:
            stones = 0
        return {"intent": intent, "target_item": item, "stones": max(0, stones)}
    except Exception:
        return classify_local(text)


def _extract_item(text: str) -> str:
    # 《名》或「名」或常见 catalog 子串
    m = re.search(r"[《「]([^》」]{1,20})[》」]", text)
    if m:
        return m.group(1).strip()
    for name in ITEM_CATALOG:
        if name in text:
            return name
    # 行囊模糊：聚气丹 / 灵芝 等两字以上
    m = re.search(r"([一-鿿]{2,8}(?:丹|草|芝|剑|符|石|液|果|木|铁|玉))", text)
    return m.group(1) if m else ""


def _extract_stones(text: str) -> int:
    m = re.search(r"(\d+)\s*灵石", text)
    if m:
        try:
            return max(0, int(m.group(1)))
        except Exception:
            return 0
    m = re.search(r"灵石\s*(\d+)", text)
    if m:
        try:
            return max(0, int(m.group(1)))
        except Exception:
            return 0
    return 0


def _match_inventory(player: Character, hint: str) -> Optional[str]:
    if not hint:
        return None
    inv = player.inventory or []
    if hint in inv:
        return hint
    hits = [x for x in inv if hint in x or x in hint]
    if len(hits) == 1:
        return hits[0]
    return None


def _loc_safe(location: str) -> bool:
    loc = WORLD_LOCATIONS.get(location) or {}
    return bool(loc.get("is_safe", False))


def _polish(npc: Character, player: Character, action: str, fallback: str) -> str:
    try:
        from ai.gateway import _chat_json, ai_available

        if not ai_available():
            return fallback
        data = _chat_json(
            "你是修仙 NPC，对方刚对你做了动作。只输出 JSON。\n"
            f"你是 {npc.name}；对方 {player.name} 动作类型：{action}\n"
            f"背景句：{fallback}\n"
            '输出：{"line":"台词<=60字"}'
        )
        line = str((data or {}).get("line") or "").strip()
        return line[:120] if line else fallback
    except Exception:
        return fallback


def do_gift(player: Character, npc: Character, item_hint: str, stones: int) -> Dict[str, Any]:
    item = _match_inventory(player, item_hint)
    stones = min(stones, max(0, player.spirit_stones))
    if not item and stones <= 0:
        return {
            "ok": False,
            "error": "要赠什么？说清物品名（行囊中有）或「N 灵石」。",
        }
    if item_hint and not item and stones <= 0:
        return {"ok": False, "error": f"行囊中无【{item_hint}】。现有：{'、'.join(player.inventory[:8]) or '空'}。"}
    if item:
        player.inventory.remove(item)
    if stones > 0:
        player.spirit_stones -= stones
    try:
        CharacterRepository.save(player)
    except Exception:
        pass
    try:
        from core.npc_mind import shift_attitude

        delta = 5 + (3 if stones >= 50 else 0) + (2 if item else 0)
        shift_attitude(npc, player.id, delta, reason="会话赠礼")
    except Exception:
        delta = 5
    parts = []
    if item:
        parts.append(f"【{item}】")
    if stones:
        parts.append(f"{stones} 灵石")
    gave = "、".join(parts)
    line = _polish(npc, player, "gift", f"「{npc.name}」接过{gave}，神色稍缓：「道友有心了。」")
    return {
        "ok": True,
        "action": "gift",
        "text": f"【赠礼】你将{gave}递给【{npc.name}】。\n{line}",
        "ended": False,
        "attitude_delta": delta,
    }


def do_trade(player: Character, npc: Character, item_hint: str, stones: int) -> Dict[str, Any]:
    try:
        from core.npc_mind import attitude_toward

        att = attitude_toward(npc, player.id)
        v = int(att.get("value") or 0)
    except Exception:
        v = 0
    if v < -20:
        line = _polish(npc, player, "trade", f"「{npc.name}」冷笑：「与你做买卖？免了。」")
        return {"ok": True, "action": "trade", "text": f"【交易被拒】\n{line}", "ended": False}

    item = item_hint or ""
    catalog_item = None
    for name in ITEM_CATALOG:
        if item and (name == item or item in name or name in item):
            catalog_item = name
            break
    if not catalog_item and item:
        for name in ITEM_CATALOG:
            if name in (item_hint or ""):
                catalog_item = name
                break

    if catalog_item:
        base = int(ITEM_CATALOG[catalog_item].get("price") or 0)
        mult = 0.85 if v >= 30 else (1.0 if v >= 0 else 1.15)
        price = max(1, int(base * mult))
        # 玩家出价低于对方要价 → 拒绝，禁止压价白嫖
        if stones > 0 and stones < price:
            return {
                "ok": False,
                "error": f"【{catalog_item}】作价 {price} 灵石，你只出 {stones}，【{npc.name}】摇头不卖。",
            }
        if player.spirit_stones < price:
            return {
                "ok": False,
                "error": f"【{catalog_item}】作价 {price} 灵石，你随身仅有 {player.spirit_stones}。",
            }
        player.spirit_stones -= price
        player.inventory.append(catalog_item)
        try:
            CharacterRepository.save(player)
        except Exception:
            pass
        try:
            from core.npc_mind import shift_attitude

            shift_attitude(npc, player.id, 3, reason="会话成交")
        except Exception:
            pass
        line = _polish(npc, player, "trade", f"「{npc.name}」收下灵石，递来【{catalog_item}】：「货讫两清。」")
        return {
            "ok": True,
            "action": "trade",
            "text": f"【成交】以 {price} 灵石购得【{catalog_item}】。\n{line}",
            "ended": False,
        }

    # 无具体货：出灵石换态度/人情
    if stones <= 0:
        return {
            "ok": False,
            "error": "交易需点明想买的货，或出价「N 灵石」。",
        }
    if player.spirit_stones < stones:
        return {"ok": False, "error": f"随身仅有 {player.spirit_stones} 灵石。"}
    player.spirit_stones -= stones
    try:
        CharacterRepository.save(player)
    except Exception:
        pass
    try:
        from core.npc_mind import shift_attitude

        shift_attitude(npc, player.id, 4, reason="会话人情")
    except Exception:
        pass
    line = _polish(npc, player, "trade", f"「{npc.name}」掂了掂灵石：「此事好说。」")
    return {
        "ok": True,
        "action": "trade",
        "text": f"【人情】奉上 {stones} 灵石。\n{line}",
        "ended": False,
    }


def do_steal(player: Character, npc: Character, rec: Dict[str, Any]) -> Dict[str, Any]:
    if _loc_safe(player.location):
        return {
            "ok": False,
            "error": f"【{player.location}】乃安全大阵之内，不可行窃。",
        }
    if npc.spirit_stones <= 0:
        return {
            "ok": False,
            "error": f"【{npc.name}】储物袋空空如也，无从下手。",
        }
    p = 0.35 + 0.08 * (player.realm.tier - npc.realm.tier)
    if player.stealth_active:
        p += 0.15
    p = max(0.1, min(0.85, p))
    if random.random() < p:
        loot = max(1, int(npc.spirit_stones * random.uniform(0.2, 0.4)))
        npc.spirit_stones -= loot
        player.spirit_stones += loot
        try:
            CharacterRepository.save(player)
            CharacterRepository.save(npc)
        except Exception:
            pass
        try:
            from core.npc_mind import shift_attitude

            shift_attitude(npc, player.id, -15, reason="会话行窃")
        except Exception:
            pass
        line = _polish(npc, player, "steal", f"（{npc.name}似未察觉，袖中却是一紧。）")
        return {
            "ok": True,
            "action": "steal",
            "text": f"【行窃】你神不知鬼不觉摸走 {loot} 灵石。\n{line}",
            "ended": False,
        }
    # 失败
    try:
        from core.npc_mind import shift_attitude

        shift_attitude(npc, player.id, -25, reason="行窃败露")
    except Exception:
        pass
    if random.random() < 0.5:
        atk = do_attack(player, npc, context=f"行窃败露：{player.name}被发现")
        atk["text"] = f"【行窃败露】被【{npc.name}】当场拿住手腕！\n" + atk.get("text", "")
        atk["action"] = "steal"
        # 攻击被安全区/庇护拒绝时仍结束会话（对方已翻脸）
        if not atk.get("ok"):
            atk["ok"] = True
            atk["ended"] = True
            atk["hangup_reason"] = f"行窃败露，【{npc.name}】与你绝交。"
            atk["text"] = (
                f"【行窃败露】被【{npc.name}】当场拿住手腕！\n"
                + atk.get("error", "对方怒目而视，不再理你。")
            )
        return atk
    line = _polish(npc, player, "steal", f"「{npc.name}」猛地扣住你手腕：「道友这是何意？」拂袖不再理你。")
    return {
        "ok": True,
        "action": "steal",
        "text": f"【行窃败露】\n{line}\n【会话已终】对方不再理你。",
        "ended": True,
        "hangup_reason": f"行窃败露，【{npc.name}】与你绝交。",
    }


def do_kidnap(player: Character, npc: Character, rec: Dict[str, Any]) -> Dict[str, Any]:
    if _loc_safe(player.location):
        return {
            "ok": False,
            "error": f"【{player.location}】安全大阵之内，不可擒人。",
        }
    if npc.status == CharacterStatus.DEAD:
        return {"ok": False, "error": "死者不可擒。"}
    if npc.status == CharacterStatus.CAPTURED:
        return {"ok": False, "error": f"【{npc.name}】已被擒。"}
    willing = int(rec.get("willingness") or 50) if rec else 50
    tier_gap = player.realm.tier - npc.realm.tier
    if tier_gap < 1 and willing >= 20:
        return {
            "ok": False,
            "error": "境界未形成压制，且对方谈兴尚存，难以得手。可先激怒或提升境界。",
        }
    p = 0.25 + 0.12 * tier_gap
    p = max(0.1, min(0.75, p))
    if random.random() < p:
        npc.status = CharacterStatus.CAPTURED
        npc.captor_id = player.id
        player.karma.add_sin(40)
        try:
            CharacterRepository.save(player)
            CharacterRepository.save(npc)
        except Exception:
            pass
        try:
            from core.npc_mind import shift_attitude

            shift_attitude(npc, player.id, -50, reason="被擒")
        except Exception:
            pass
        line = _polish(npc, player, "kidnap", f"「{npc.name}」奋力挣扎，终被制住：「你……！」")
        return {
            "ok": True,
            "action": "kidnap",
            "text": f"【擒拿】你制住【{npc.name}】，业力 +40。\n{line}\n（可用 /释放 让其脱困）",
            "ended": True,
            "hangup_reason": f"你将【{npc.name}】擒住。",
        }
    try:
        from core.npc_mind import shift_attitude

        shift_attitude(npc, player.id, -40, reason="擒拿未遂")
    except Exception:
        pass
    atk = do_attack(player, npc, context=f"擒拿未遂：{player.name}动手")
    atk["text"] = f"【擒拿未遂】\n" + atk.get("text", "")
    atk["action"] = "kidnap"
    # 攻击被拒时也结束会话
    if not atk.get("ok"):
        atk["ok"] = True
        atk["ended"] = True
        atk["hangup_reason"] = f"擒拿未遂，【{npc.name}】与你反目。"
        atk["text"] = (
            f"【擒拿未遂】\n" + atk.get("error", "对方挣脱，怒而离去。")
        )
    return atk


def do_attack(player: Character, npc: Character, context: str = "") -> Dict[str, Any]:
    from core.combat_fate import CombatFateEngine

    res = CombatFateEngine.resolve_ambush(player, npc, context=context or "会话中动手")
    if not res.get("success"):
        return {
            "ok": False,
            "error": res.get("message", "无法动手"),
            "action": "attack",
        }
    text = res.get("report") or res.get("message") or "双方交手。"
    if isinstance(text, list):
        text = "\n".join(str(x) for x in text)
    return {
        "ok": True,
        "action": "attack",
        "text": f"【动手】{text}",
        "ended": True,
        "hangup_reason": "话不投机，当场动手。",
    }


def release_captive(player: Character, target_name: str = "") -> Dict[str, Any]:
    name = (target_name or "").strip()
    if not name:
        # 默认：同场被自己擒住的第一人
        for c in CharacterRepository.list_all_alive():
            if c.location == player.location and c.status == CharacterStatus.CAPTURED and c.captor_id == player.id:
                name = c.name
                break
    if not name:
        return {"ok": False, "error": "用法：/释放 <道号>（同场且由你擒住）"}
    t = CharacterRepository.get_by_name(name)
    if not t:
        return {"ok": False, "error": f"查无此人：{name}"}
    if t.status != CharacterStatus.CAPTURED:
        return {"ok": False, "error": f"【{t.name}】未被擒。"}
    if t.captor_id != player.id:
        return {"ok": False, "error": f"【{t.name}】不是你擒的。"}
    if t.location != player.location:
        return {"ok": False, "error": "须同场才能释放。"}
    t.status = CharacterStatus.IDLE
    t.captor_id = None
    try:
        from core.npc_mind import shift_attitude

        shift_attitude(t, player.id, 5, reason="开释")
    except Exception:
        pass
    CharacterRepository.save(t)
    return {"ok": True, "message": f"【释放】你解开【{t.name}】束缚，其自行离去。"}


def execute_chat_action(
    player: Character,
    npc: Character,
    text: str,
    *,
    use_ai_classify: bool = True,
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """分类并执行；返回统一 dict（ok/action/text/ended/error...）"""
    if npc.status == CharacterStatus.CAPTURED:
        return {"ok": False, "error": f"【{npc.name}】已被擒，无从交谈。"}
    if use_ai_classify:
        cls = classify_ai(text, player, npc)
    else:
        cls = classify_local(text)
    intent = cls.get("intent") or "dialogue"
    item = cls.get("target_item") or ""
    stones = int(cls.get("stones") or 0)
    rec = session or {}

    if intent == "gift":
        return do_gift(player, npc, item, stones)
    if intent == "trade":
        return do_trade(player, npc, item, stones)
    if intent == "steal":
        return do_steal(player, npc, rec)
    if intent == "kidnap":
        return do_kidnap(player, npc, rec)
    if intent == "attack":
        return do_attack(player, npc, context=text)
    return {"ok": True, "action": "dialogue", "need_dialogue": True, "intent": "dialogue"}
