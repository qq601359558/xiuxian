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
    "trade": [
        "交易", "出价", "买下", "购买", "换你", "卖我", "买", "卖", "换",
        "卖你", "卖给", "出售", "卖出", "收购", "收不收", "作价", "开价",
        "货单", "有何货", "有什么货", "可卖", "多少钱",
    ],
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


def _npc_trade_role(npc: Character) -> str:
    """shop：可按货单买卖；person：散修私易；hostile：敌对拒商"""
    try:
        from core.npc_personas import get_persona

        role = (get_persona(npc) or {}).get("role") or ""
        note = ""
        try:
            from core.npc_roster import ROSTER

            for row in ROSTER:
                if row.get("name") == npc.name:
                    note = row.get("note") or ""
                    role = role or row.get("rank") or ""
                    break
        except Exception:
            pass
        blob = f"{role} {note} {npc.sect_rank or ''} {npc.sect or ''}"
        if any(k in blob for k in ("掌柜", "会长", "伙计", "商会", "丹铺", "牙人", "镖头")):
            return "shop"
        if any(k in blob for k in ("宗主", "魔修", "妖修")):
            return "person"
    except Exception:
        pass
    if npc.sect and "商会" in npc.sect:
        return "shop"
    return "person"


def _extract_qty(text: str) -> int:
    t = text or ""
    m = re.search(r"(\d+)\s*[个颗枚件份张套]", t)
    if m:
        try:
            return max(1, min(20, int(m.group(1))))
        except Exception:
            return 1
    m = re.search(r"(?:买|购|卖|出售)[^\d]{0,12}(\d+)", t)
    if m:
        try:
            n = int(m.group(1))
            if 1 <= n <= 20:
                return n
        except Exception:
            pass
    # 句末小数量：卖你xx 2 / 买xx3
    for n in reversed(re.findall(r"(\d+)", t)):
        try:
            ni = int(n)
        except Exception:
            continue
        if 1 <= ni <= 20:
            return ni
        if ni > 20:
            break
    return 1


def _is_selling(text: str) -> bool:
    t = (text or "")
    return any(k in t for k in ("卖你", "卖给", "出售", "卖出", "卖给你", "你收不", "收不收", "变现"))


def _is_asking_goods(text: str) -> bool:
    t = (text or "")
    return any(k in t for k in ("有什么货", "有何货", "货单", "可卖什么", "卖什么", "店里有什么", "货架"))


def _match_catalog(item_hint: str) -> Optional[str]:
    if not item_hint:
        return None
    for name in ITEM_CATALOG:
        if name == item_hint or item_hint in name or name in item_hint:
            return name
    return None


def _shop_stock_preview(npc: Character, limit: int = 6) -> List[str]:
    """按职分给一小撮可卖货（去重，非全货单灌屏）"""
    try:
        from core.npc_personas import get_persona

        role = (get_persona(npc) or {}).get("role") or ""
    except Exception:
        role = npc.sect_rank or ""
    pills, mats, arrs = [], [], []
    seen = set()
    for name, cfg in ITEM_CATALOG.items():
        if name in seen:
            continue
        kind = cfg.get("kind")
        if kind == "pill":
            pills.append(name)
        elif kind == "array":
            arrs.append(name)
        else:
            mats.append(name)
        seen.add(name)
    blob = role + (npc.name or "") + (npc.sect or "")
    if any(k in blob for k in ("丹", "药")):
        out = pills[:limit]
    elif "阵" in role or "剑" in (npc.sect or ""):
        out = arrs[:limit] or mats[:limit]
    elif any(k in role for k in ("掌柜", "会长")) or "商会" in (npc.sect or ""):
        out = []
        for src in (pills, mats, arrs):
            if src:
                out.append(src[0])
        for x in pills + mats + arrs:
            if x not in out:
                out.append(x)
            if len(out) >= limit:
                break
        out = out[:limit]
    else:
        out = (mats[:3] + pills[:2] + arrs[:1])[:limit]
    # 保底去重
    final = []
    for n in out:
        if n not in final:
            final.append(n)
    return final[:limit]


def do_trade(player: Character, npc: Character, item_hint: str, stones: int, text: str = "") -> Dict[str, Any]:
    """会话内交易：买货单 / 卖行囊 / 问货单 / 人情；规则落账"""
    try:
        from core.npc_mind import attitude_toward

        att = attitude_toward(npc, player.id)
        v = int(att.get("value") or 0)
    except Exception:
        v = 0
    role = _npc_trade_role(npc)
    try:
        from core.npc_mind import attitude_toward as _at

        if _at(npc, player.id).get("label") == "hostile" or v < -20:
            line = _polish(npc, player, "trade", f"「{npc.name}」冷笑：「与你做买卖？免了。」")
            return {"ok": True, "action": "trade", "text": f"【交易被拒】\n{line}", "ended": False}
    except Exception:
        if v < -20:
            line = _polish(npc, player, "trade", f"「{npc.name}」冷笑：「与你做买卖？免了。」")
            return {"ok": True, "action": "trade", "text": f"【交易被拒】\n{line}", "ended": False}

    # —— 问货单 ——
    if _is_asking_goods(text) or (not item_hint and not stones and any(k in (text or "") for k in ("货", "什么价", "多少钱"))):
        stock = _shop_stock_preview(npc)
        if not stock:
            return {
                "ok": True,
                "action": "trade",
                "text": f"【货架】「{npc.name}」摊手：「我这里没现货，大货请 /坊市 商会。」",
                "ended": False,
            }
        if role == "shop":
            lines = [f"「{npc.name}」亮出货架："]
            for n in stock:
                p = ITEM_CATALOG.get(n, {}).get("price") or 0
                lines.append(f"  · {n} · {p} 灵石起")
            lines.append("（可说：买下聚气丹 / 我出N灵石 / 卖你妖兽内丹）")
        else:
            lines = [
                f"「{npc.name}」道：「我不做柜台生意，若有缘法倒可私易。」",
                "可试：「卖你行囊中的货」或「这货多少钱」；系统货单请开 /坊市。",
            ]
        return {"ok": True, "action": "trade", "text": "\n".join(lines), "ended": False}

    qty = _extract_qty(text or "")
    item = item_hint or ""
    catalog_item = _match_catalog(item)

    # —— 玩家卖给 NPC ——
    if _is_selling(text) or (item and ("卖" in (text or "")) and catalog_item is None):
        inv_item = _match_inventory(player, item) or _match_catalog(item)
        if not inv_item:
            # 行囊模糊再试
            inv_item = _match_inventory(player, item_hint)
        if not inv_item:
            have = "、".join(player.inventory[:8]) or "空空如也"
            return {
                "ok": False,
                "error": f"要卖什么？行囊现有：{have}。可说「卖你聚气丹」。",
            }
        qty = max(1, min(qty, player.inventory.count(inv_item) if inv_item in player.inventory else 1))
        if role == "shop":
            # 走商会回收价（含恐慌系数）
            try:
                from core.market import MarketEngine

                sold_total = 0
                for _i in range(qty):
                    res = MarketEngine.sell_to_guild(player, inv_item, 1)
                    if not res.get("success"):
                        return {"ok": False, "error": res.get("message", "无法售出。")}
                    sold_total += int(res.get("gain") or res.get("total") or 0)
                CharacterRepository.save(player)
                line = _polish(npc, player, "trade", f"「{npc.name}」验货点灵石：「作价 {sold_total}，两清。」")
                return {
                    "ok": True,
                    "action": "trade",
                    "text": f"【售出】{inv_item}×{qty}，得灵石 {sold_total}。\n{line}",
                    "ended": False,
                }
            except Exception as e:
                return {"ok": False, "error": f"柜台结算失败：{e}"}
        # 私易：回收价更低
        try:
            cfg = ITEM_CATALOG.get(inv_item) or {"price": 20}
            from config import MARKET_SELL_BACK_RATE
            from core.player_echo import market_sell_mult

            base = max(1, int(int(cfg.get("price") or 20) * MARKET_SELL_BACK_RATE * market_sell_mult()))
            mult = 0.7 if v < 0 else (0.85 if v < 25 else 0.95)
            price = max(1, int(base * mult))
            got = 0
            for _i in range(qty):
                if inv_item not in player.inventory:
                    break
                player.inventory.remove(inv_item)
                player.spirit_stones += price
                got += price
            CharacterRepository.save(player)
            line = _polish(npc, player, "trade", f"「{npc.name}」压价收下：「私易作价 {price} 灵石一件，别声张。」")
            return {
                "ok": True,
                "action": "trade",
                "text": f"【私易售出】{inv_item}×{qty}，得 {got} 灵石。\n{line}",
                "ended": False,
            }
        except Exception as e:
            return {"ok": False, "error": f"私易失败：{e}"}

    # —— 买货 ——
    if catalog_item:
        cfg = ITEM_CATALOG[catalog_item]
        base = int(cfg.get("price") or 0)
        try:
            from core.player_echo import market_buy_mult

            panic_m = market_buy_mult()
        except Exception:
            panic_m = 1.0
        if role == "shop":
            mult = 0.90 if v >= 40 else (0.95 if v >= 20 else 1.0)
            unit = max(1, int(base * mult * panic_m))
        else:
            # 非柜台：托人/转手加价
            mult = 1.25 if v >= 0 else 1.4
            unit = max(1, int(base * mult * panic_m))
        total = unit * qty
        if stones > 0 and stones < unit:
            return {
                "ok": False,
                "error": f"【{catalog_item}】作价 {unit} 灵石/件，你只出 {stones}，【{npc.name}】摇头不卖。",
            }
        if player.spirit_stones < total:
            return {
                "ok": False,
                "error": f"【{catalog_item}】×{qty} 需 {total} 灵石，你随身仅有 {player.spirit_stones}。",
            }
        # 货源：柜台走货单；非柜台也允许「代购到手」（同一规则发物）
        player.spirit_stones -= total
        kind = cfg.get("kind")
        for _i in range(qty):
            if kind == "array":
                if catalog_item not in player.arrays:
                    player.arrays.append(catalog_item)
                else:
                    player.inventory.append(catalog_item)
            else:
                player.inventory.append(catalog_item)
        CharacterRepository.save(player)
        try:
            from core.npc_mind import shift_attitude

            shift_attitude(npc, player.id, 3, reason="会话成交")
        except Exception:
            pass
        who = "柜台" if role == "shop" else "转手"
        line = _polish(
            npc,
            player,
            "trade",
            f"「{npc.name}」收下灵石递来【{catalog_item}×{qty}】：「货讫两清。」",
        )
        return {
            "ok": True,
            "action": "trade",
            "text": f"【成交·{who}】{catalog_item}×{qty}，单价 {unit}，共付 {total} 灵石。\n{line}",
            "ended": False,
            "item_name": catalog_item,
            "qty": qty,
            "total": total,
        }

    # 无具体货：出灵石换态度/人情
    if stones <= 0:
        return {
            "ok": False,
            "error": (
                "交易需点明货名（如：买下聚气丹 / 卖你妖兽内丹），"
                "或说「有什么货」看货架，或出价「N 灵石」作人情。"
            ),
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
            from core.player_echo import record_player_sin

            record_player_sin(player, 40, reason="擒拿")
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
        return do_trade(player, npc, item, stones, text=text)
    if intent == "steal":
        return do_steal(player, npc, rec)
    if intent == "kidnap":
        return do_kidnap(player, npc, rec)
    if intent == "attack":
        return do_attack(player, npc, context=text)
    return {"ok": True, "action": "dialogue", "need_dialogue": True, "intent": "dialogue"}
