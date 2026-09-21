"""
NPC 心智：性格、态度、多议程权重、对话
「像真人」的最小可行层：稳定人设 + 对玩家态度 + 会按态度说话
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character, CharacterStatus
from storage.db import (
    NpcMindRepository,
    NpcAgendaRepository,
    CharacterRepository,
    EventLedgerRepository,
    CharacterBioRepository,
)
from core.memory import ensure_bio, record_event, compress_events_for_prompt
from ai.gate import gate
from ai.gateway import ai_ready, ai_block_reason
from ai.audit import write_audit
from config import WORLD_LOCATIONS


PERSONALITIES = [
    "谨慎多疑", "豪爽仗义", "阴鸷记仇", "贪财好利",
    "清高自持", "市侩圆滑", "莽撞好斗", "淡泊避世",
]

ATTITUDE_LABELS = {
    "hostile": "仇视",
    "wary": "戒备",
    "neutral": "中立",
    "friendly": "友善",
    "ally": "亲近",
}


def _is_npc(c: Character) -> bool:
    uid = str(c.user_id)
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def ensure_mind(npc: Character) -> Dict[str, Any]:
    """保证 NPC 有性格；按状态给确定性默认人设"""
    mind = NpcMindRepository.get(npc.id)
    if mind:
        return mind

    if npc.karma.sin_value >= 120:
        personality = "阴鸷记仇"
    elif npc.karma.merit_value >= 80:
        personality = "豪爽仗义"
    elif npc.spirit_stones >= 900:
        personality = "贪财好利"
    elif npc.sect == "青云宗":
        personality = "清高自持"
    elif npc.sect == "九幽天魔宗":
        personality = "莽撞好斗"
    elif npc.sect == "四海散修商会":
        personality = "市侩圆滑"
    else:
        # 稳定哈希选一个，避免同一 NPC 每次变人
        personality = PERSONALITIES[hash(npc.id) % len(PERSONALITIES)]

    traits = {
        "greed": 0.8 if "贪" in personality else 0.3,
        "caution": 0.8 if "谨慎" in personality or "淡泊" in personality else 0.4,
        "wrath": 0.8 if "记仇" in personality or "好斗" in personality else 0.2,
    }
    NpcMindRepository.upsert(npc.id, personality, traits, {})
    return NpcMindRepository.get(npc.id) or {
        "personality": personality, "traits": traits, "attitudes": {}
    }


def attitude_toward(npc: Character, other_id: str) -> Dict[str, Any]:
    mind = ensure_mind(npc)
    att = (mind.get("attitudes") or {}).get(other_id)
    if att:
        return att
    return {"value": 0, "label": "neutral"}


def shift_attitude(npc: Character, other_id: str, delta: int, reason: str = "") -> Dict[str, Any]:
    mind = ensure_mind(npc)
    cur = ((mind.get("attitudes") or {}).get(other_id) or {}).get("value", 0)
    new_v = int(cur) + int(delta)
    result = NpcMindRepository.set_attitude(npc.id, other_id, new_v)
    if reason:
        try:
            record_event(
                type="ATTITUDE",
                actor=npc,
                summary=f"{npc.name}对目标态度变化：{reason}（{result.get('label')}）",
                location=npc.location,
                effects_digest=f"attitude {cur}->{new_v}",
            )
        except Exception:
            pass
    return result


def on_kill_update_attitudes(attacker: Character, defender: Character):
    """击杀后：死者亲友（同宗/同地）对凶手态度恶化；凶手对死者记仇标记"""
    shift_attitude(attacker, defender.id, -80, reason=f"斩杀{defender.name}")
    for c in CharacterRepository.list_all_alive():
        if c.id in (attacker.id, defender.id):
            continue
        if not _is_npc(c):
            continue
        related = False
        if c.sect and c.sect == defender.sect:
            related = True
        if c.location == defender.location:
            related = True
        if related:
            # 同门/同场更恨
            delta = -45 if c.sect == defender.sect else -20
            # 性格：记仇加成
            mind = ensure_mind(c)
            if "记仇" in (mind.get("personality") or ""):
                delta -= 15
            shift_attitude(c, attacker.id, delta, reason=f"因{defender.name}之死")


# 性格 → 偏好副议程（按顺序优先，避开主目标）
PERSONALITY_AGENDA_PREF = {
    "谨慎多疑": [
        ("survive", 22, "副：避祸保命，少沾因果"),
        ("social", 18, "副：只听墙角，不轻易表态"),
    ],
    "豪爽仗义": [
        ("social", 25, "副：结交同道，替人平事"),
        ("patrol", 18, "副：路见不平搭把手"),
    ],
    "阴鸷记仇": [
        ("revenge", 28, "副：暗中记账，伺机寻仇"),
        ("scheme", 0, ""),  # 占位忽略
        ("social", 12, "副：打听仇家下落"),
    ],
    "贪财好利": [
        ("treasure", 28, "副：估价灵材，寻找买卖"),
        ("social", 15, "副：套近乎谈生意"),
    ],
    "清高自持": [
        ("seclusion", 25, "副：闭关清修，不问世事"),
        ("patrol", 15, "副：例行巡视道场"),
    ],
    "市侩圆滑": [
        ("social", 26, "副：四处走动，贩卖消息"),
        ("treasure", 18, "副：低买高卖攒灵石"),
    ],
    "莽撞好斗": [
        ("patrol", 26, "副：找人切磋，以战养战"),
        ("revenge", 14, "副：谁惹我就打回去"),
    ],
    "淡泊避世": [
        ("seclusion", 26, "副：吐纳观云，不争不抢"),
        ("survive", 16, "副：远离是非之地"),
    ],
}


def _secondary_for_personality(personality: str, primary: str) -> List[Dict[str, Any]]:
    prefs = PERSONALITY_AGENDA_PREF.get(personality) or [
        ("social", 20, "副：市井走动"),
        ("survive", 15, "副：谨慎求存"),
    ]
    out = []
    for ag_type, weight, note in prefs:
        if not ag_type or ag_type == primary or ag_type not in (
            "revenge", "treasure", "seclusion", "patrol", "social", "survive"
        ):
            continue
        out.append({"agenda_type": ag_type, "weight": int(weight), "note": note})
        if len(out) >= 2:
            break
    # 不足两条则补通用
    if len(out) < 2:
        for fallback in ("social", "survive", "treasure"):
            if fallback == primary or any(x["agenda_type"] == fallback for x in out):
                continue
            out.append({"agenda_type": fallback, "weight": 12, "note": "副：随缘而动"})
            if len(out) >= 2:
                break
    return out


def multi_agenda_pack(npc: Character) -> Dict[str, Any]:
    """
    主议程 + 副议程（权重），tick 时按权重抽一条执行。
    主议程在 npc_agendas；副议程放 extra_json，按性格生成。
    """
    ag = NpcAgendaRepository.get(npc.id)
    if not ag:
        from core.npc_agenda import ensure_agenda
        ag = ensure_agenda(npc)

    extra = ag.get("extra") or {}
    secondary = extra.get("secondary") or []
    if not secondary:
        mind = ensure_mind(npc)
        personality = mind.get("personality") or ""
        secondary = _secondary_for_personality(personality, ag.get("agenda_type") or "")
        extra = dict(extra)
        extra["secondary"] = secondary
        extra["personality"] = personality
        NpcAgendaRepository.upsert(
            npc_id=npc.id,
            npc_name=npc.name,
            agenda_type=ag["agenda_type"],
            target_hint=ag.get("target_hint", ""),
            note=ag.get("note", ""),
            state=ag.get("state", "active"),
            last_tick=ag.get("last_tick", 0),
            progress=ag.get("progress", 0),
            extra=extra,
        )
        ag = NpcAgendaRepository.get(npc.id) or ag

    return {
        "primary": {"agenda_type": ag.get("agenda_type"), "note": ag.get("note", ""), "weight": 60},
        "secondary": (ag.get("extra") or {}).get("secondary") or [],
        "personality": (ag.get("extra") or {}).get("personality") or "",
        "agenda_row": ag,
    }


def pick_agenda_for_tick(npc: Character) -> Dict[str, Any]:
    """按权重选本 tick 议程（主 60% 权重大头）；天道导演态势可规则偏置"""
    pack = multi_agenda_pack(npc)
    options = [pack["primary"]] + list(pack["secondary"])
    # 导演控局：血煞潮/宗门紧张/大劫预兆 → 注入高权重候选（结算仍走规则）
    try:
        from core.world_director import agenda_bias_for_npc

        bias = agenda_bias_for_npc(npc)
        if bias:
            options = [
                {
                    "agenda_type": bias["agenda_type"],
                    "note": bias["note"],
                    "weight": 55,
                }
            ] + options
    except Exception:
        pass
    weights = [max(1, int(o.get("weight") or 10)) for o in options]
    chosen = random.choices(options, weights=weights, k=1)[0]
    return chosen


# ---------------- 对话 ----------------
class NpcDialogueEngine:
    """与 NPC 交谈：性格 + 态度 + 近账 → 一句话回应"""

    @staticmethod
    def talk(
        npc: Character,
        player: Character,
        player_words: str = "",
    ) -> Dict[str, Any]:
        if npc.status == CharacterStatus.DEAD:
            return {"ok": False, "error": "斯人已逝，无可交谈。"}
        if npc.location != player.location:
            return {
                "ok": False,
                "error": f"【{npc.name}】不在【{player.location}】，无法当面交谈。",
            }

        mind = ensure_mind(npc)
        att = attitude_toward(npc, player.id)
        att_cn = ATTITUDE_LABELS.get(att.get("label", "neutral"), "中立")
        ensure_bio(npc)
        bio = CharacterBioRepository.get(npc.id) or ""
        events = EventLedgerRepository.query_for_memory(npc.id, limit=3)
        ev_lines = compress_events_for_prompt(events, max_items=2)
        words = gate.sanitize_player_text(player_words)[:120]

        loc_info = WORLD_LOCATIONS.get(npc.location, {})
        from config import LLM_API_KEY, local_ai_allowed, ITEM_CATALOG
        from ai.gateway import ai_available

        # 职分 / 花名册备注（丹铺掌柜等关键身份必须进 prompt）
        role = npc.sect_rank or "散修"
        roster_note = ""
        try:
            from core.npc_roster import ROSTER
            for row in ROSTER:
                if row.get("name") == npc.name:
                    roster_note = row.get("note") or ""
                    if row.get("rank"):
                        role = row["rank"]
                    break
        except Exception:
            pass

        # 玩家侧：灵石/行囊，谈买卖时才有意义
        inv_brief = "、".join(player.inventory[:8]) or "无"
        # 货单摘要（谈交易时给 AI 可卖什么，避免「不卖这个」）
        goods_brief = "、".join(f"{n}({c['price']}灵石)" for n, c in list(ITEM_CATALOG.items())[:8])
        # 时间
        try:
            from core.season import season_status_text
            time_brief = season_status_text()
        except Exception:
            time_brief = "天道纪元"

        data = None
        if ai_available():
            try:
                from core.npc_personas import (
                    persona_prompt_block,
                    ensure_persona_bio,
                    character_card_block,
                    example_lines,
                    player_persona_block,
                )

                ensure_persona_bio(npc)
                card = character_card_block(npc)
                examples = " / ".join(example_lines(npc))
                player_card = player_persona_block(player)
            except Exception:
                card, examples, player_card = "", "", ""
            try:
                from core.lorebook import lore_prompt_block
                from core.npc_chat import chat_memory_lines

                lore = lore_prompt_block(player, npc, player_words=words)
                chat_mem = chat_memory_lines(player.id, npc.id, limit=2)
            except Exception:
                lore, chat_mem = "", ""
            try:
                import core.jianghu as jianghu
                from ai.facts import build_fact_pack
                from ai.router import invoke as ai_invoke

                facts = build_fact_pack(
                    npc,
                    others=[player],
                    jianghu_events=jianghu.events_for_prompt(3),
                    recent_ledger=ev_lines,
                )
                result = ai_invoke(
                    "npc_talk",
                    facts=facts,
                    payload={
                        "name": npc.name,
                        "realm": npc.realm.name,
                        "sect": npc.sect or "散修",
                        "role": role,
                        "roster_note": roster_note,
                        "persona": card or persona_prompt_block(npc),
                        "card": card or persona_prompt_block(npc),
                        "examples": examples,
                        "player_card": player_card,
                        "lore": lore,
                        "chat_memory": chat_mem,
                        "personality": mind.get("personality"),
                        "bio": bio,
                        "player": player.name,
                        "att_cn": att_cn,
                        "att_value": att.get("value", 0),
                        "player_realm": player.realm.name,
                        "stones": player.spirit_stones,
                        "inv": inv_brief,
                        "location": npc.location,
                        "safe_cn": "安全" if loc_info.get("is_safe", True) else "凶险",
                        "goods": goods_brief,
                        "time_brief": time_brief,
                        "events": "；".join(ev_lines) or "无",
                        "words": words or "（拱手一礼，未多言）",
                    },
                    actor_id=npc.id,
                )
                if result.get("ok"):
                    data = result.get("data")
            except Exception:
                data = None
        if data and data.get("line"):
            line = str(data["line"])[:200]
            try:
                delta = int(data.get("attitude_delta") or 0)
            except (TypeError, ValueError):
                delta = 0
            delta = max(-10, min(10, delta))
            source = "ai"
        else:
            # 配置了 Key 却失败：不要静默用固定模板冒充 AI
            if ai_available() and not local_ai_allowed():
                return {
                    "ok": False,
                    "error": (
                        "【造化未应】AI 网关无响应或鉴权失败。"
                        "若用 CC Switch：.env 设 USE_CCSWITCH=1 并保证 CC Switch 在线、账号健康；"
                        "或检查 LLM_API_*。详情见 data/server.log。"
                    ),
                }
            # 本地兜底也按职分给「本行买卖」语气
            pers = mind.get("personality") or ""
            if any(k in words for k in ("丹", "药", "买", "卖", "价", "灵石")) and (
                "掌柜" in role or "丹" in roster_note or "药" in roster_note
            ):
                try:
                    from config import ITEM_CATALOG
                    pills = [n for n, c in ITEM_CATALOG.items() if c.get("kind") == "pill"]
                    pill_s = "、".join(pills[:4]) or "聚气丹、筑基丹"
                    line = f"{npc.name}拨弄药瓶：「{pill_s} 都在架上，官人要哪味？也可直接 /购买。」"
                    delta = 1
                    source = "local"
                except Exception:
                    line, delta = NpcDialogueEngine._local_line(npc, player, att, mind, words)
                    source = "local_fallback"
            else:
                line, delta = NpcDialogueEngine._local_line(npc, player, att, mind, words)
                source = "local_fallback"

        if delta:
            att = shift_attitude(npc, player.id, delta, reason="交谈")

        try:
            eid = record_event(
                type="TALK",
                actor=npc,
                target=player,
                summary=f"{npc.name}对{player.name}：{line[:40]}",
                location=npc.location,
                effects_digest=f"attitude {delta:+d}" if delta else "",
            )
        except Exception:
            eid = ""

        # 同场插话（群聊式）
        banter_lines: List[Dict[str, Any]] = []
        try:
            from core.scene_banter import maybe_banter, format_banter

            banter_lines = maybe_banter(player, npc, transcript_tail=f"{player.name}:{words}\n{npc.name}:{line}")
        except Exception:
            banter_lines = []
        text = f"【{npc.name}·{mind.get('personality')}·{ATTITUDE_LABELS.get(att.get('label'),'中立')}】\n「{line}」"
        if banter_lines:
            try:
                from core.scene_banter import format_banter

                text += "\n" + format_banter(banter_lines)
            except Exception:
                pass

        return {
            "ok": True,
            "npc": npc.name,
            "personality": mind.get("personality"),
            "attitude": att.get("label", "neutral"),
            "attitude_cn": ATTITUDE_LABELS.get(att.get("label", "neutral"), "中立"),
            "attitude_delta": delta,
            "line": line,
            "source": source,
            "event_id": eid,
            "bystanders": banter_lines,
            "text": text,
        }

    @staticmethod
    def _local_line(npc, player, att, mind, words) -> Tuple[str, int]:
        """无 AI 兜底：态度 + 性格 + 玩家原话，避免同类问题永远同一句"""
        label = att.get("label", "neutral")
        pers = mind.get("personality") or ""
        w = (words or "").strip()
        brief = w[:20] + ("…" if len(w) > 20 else "")
        # 用原话哈希在多套模板里选，避免「可有买卖」和「聚气丹怎么卖」撞句
        seed = sum(ord(ch) for ch in w) if w else 0

        def pick(*opts):
            return opts[seed % len(opts)]

        # —— 挑衅 ——
        if any(k in w for k in ("杀", "找死", "滚", "废物", "挑衅", "动手")):
            if label == "hostile" or "好斗" in pers or "记仇" in pers:
                return pick(
                    f"{npc.name}眼中杀意一闪：「就凭你这句话，今日便是你的死期。」",
                    f"{npc.name}按住兵刃：「好，我成全你。」",
                ), -5
            if "谨慎" in pers or "淡泊" in pers:
                return f"{npc.name}退开半步：「阁下自重，贫道不想沾因果。」", -3
            return pick(
                f"{npc.name}面色一沉：「说话客气些。」",
                f"{npc.name}盯着你：「『{brief}』——你再说一遍？」",
            ), -2

        # —— 买卖（必须回显具体问法，禁止固定句）——
        if any(k in w for k in ("买", "卖", "灵石", "价钱", "价格", "多少", "交易", "生意", "收购", "出售")):
            item_hint = ""
            try:
                from config import ITEM_CATALOG

                for iname in ITEM_CATALOG:
                    if iname in w or (len(iname) >= 3 and iname[:3] in w):
                        item_hint = iname
                        break
            except Exception:
                pass
            if item_hint:
                try:
                    from config import ITEM_CATALOG

                    price = ITEM_CATALOG[item_hint]["price"]
                    if "怎么卖" in w or "多少" in w or "价" in w:
                        if "贪" in pers or "市侩" in pers:
                            return pick(
                                f"{npc.name}拨了拨算盘：「{item_hint}？市价 {price} 灵石，你要几件？」",
                                f"{npc.name}笑道：「{item_hint} {price} 灵石一件，量大可议。」",
                            ), 1
                        return f"{npc.name}摇头：「{item_hint} 我这里不走货，去商会货单看。」", 0
                    if "卖" in w and "怎么" not in w:
                        if "贪" in pers or "市侩" in pers:
                            return f"{npc.name}挑眉：「你出{item_hint}？先验货，成色好我收。」", 1
                        return f"{npc.name}摆手：「我不收散户的货。」", 0
                except Exception:
                    pass
            # 无具体货名：区分买/卖/询价
            wants_sell = ("卖" in w and "怎么" not in w) or "出售" in w or "出货" in w
            wants_price = "多少" in w or "价钱" in w or "价格" in w or "怎么卖" in w
            if "贪" in pers or "市侩" in pers:
                if wants_sell:
                    return pick(
                        f"{npc.name}搓手：「你卖什么？『{brief}』——报个数。」",
                        f"{npc.name}眼睛一亮：「有货出手？我收，细说成色。」",
                    ), 2
                if wants_price:
                    return pick(
                        f"{npc.name}报出一串数：「看货论价。你问『{brief}』，得先说清楚哪一件。」",
                        f"{npc.name}笑道：「价钱好说——你要买的是『{brief}』里的哪样？」",
                    ), 1
                return pick(
                    f"{npc.name}眼睛一亮：「道友有货？『{brief}』我听着有戏，细说。」",
                    f"{npc.name}压低声音：「买卖我最爱做。『{brief}』——进店详谈？」",
                    f"{npc.name}拍胸脯：「我这价钱公道。你提『{brief}』，是买是卖？」",
                ), 2
            if "谨慎" in pers:
                return f"{npc.name}皱眉：「『{brief}』……坊市耳目多，交易少沾为妙。」", 0
            return pick(
                f"{npc.name}摇头：「我囊中羞涩，『{brief}』这种买卖免谈。」",
                f"{npc.name}道：「买卖请去商会，我只旁听。」",
            ), 0

        # —— 打听消息 ——
        if any(k in w for k in ("打听", "消息", "下落", "哪里", "可知", "听说", "何处")):
            if "市侩" in pers or "贪" in pers:
                return pick(
                    f"{npc.name}压低声音：「打听『{brief}』是要花钱的……你出多少？」",
                    f"{npc.name}捻须：「消息有，价也有。你问『{brief}』，先付定金。」",
                ), 1
            if "谨慎" in pers:
                return f"{npc.name}左右看了看：「『{brief}』……隔墙有耳，此处不是说话的地方。」", 0
            if label == "hostile":
                return f"{npc.name}冷笑：「问我『{brief}』？你也配。」", -1
            return pick(
                f"{npc.name}想了想：「『{brief}』略知一二，你想问哪一桩？」",
                f"{npc.name}道：「你提『{brief}』……容我回忆片刻。」",
            ), 1

        # —— 客套 ——
        if any(k in w for k in ("道友", "幸会", "有礼", "请教", "拜见", "你好", "别来无恙")):
            if label == "hostile":
                return f"{npc.name}不接礼，冷冷道：「少来这套。」", 0
            if label == "wary" and ("谨慎" in pers or "记仇" in pers):
                return f"{npc.name}拱手回了半礼，眼神仍戒备：「有事？」", 0
            if "豪爽" in pers:
                return f"{npc.name}抱拳回礼：「{player.name}道友客气！来，坐。」", 2
            return f"{npc.name}微微还礼：「{player.name}道友安好。」", 1

        if any(k in w for k in ("秘境", "机缘", "古洞", "遗迹")):
            return pick(
                f"{npc.name}目光微动：「你也在盯『{brief}』？入内各凭本事。」",
                f"{npc.name}低声道：「禁制松动的事，我也听说了。」",
            ), 0

        if any(k in w for k in ("宗门", "拜入", "入门", "山门")):
            return f"{npc.name}上下打量你：「拜山须亲至总坛。你提『{brief}』——有报酬么？」", 1

        # —— 空话 ——
        if not w:
            if label == "hostile":
                return f"{npc.name}目光阴冷：「{player.name}，你还敢出现在我面前？」", 0
            if label == "ally":
                return f"{npc.name}拱手：「原来是{player.name}，有事尽管开口。」", 0
            if "贪" in pers:
                return f"{npc.name}搓了搓手指：「道友可是有灵石上的买卖？」", 1
            if "谨慎" in pers:
                return f"{npc.name}后退半步：「阁下面生，所为何来？」", -1
            if "豪爽" in pers:
                return f"{npc.name}朗声一笑：「相逢即是缘，坐下来喝一杯？」", 2
            if "记仇" in pers:
                return f"{npc.name}皮笑肉不笑：「有话快说，我耐心有限。」", -1
            return f"{npc.name}微微颔首：「{player.name}道友，别来无恙？」", 0

        # —— 未命中关键词：必须回显原话 ——
        if label == "hostile":
            return f"{npc.name}不耐烦地打断：「『{brief}』——说重点。」", 0
        if "谨慎" in pers:
            return pick(
                f"{npc.name}沉吟片刻：「你提及『{brief}』……我需想想。」",
                f"{npc.name}道：「『{brief}』此事体大，改日再谈。」",
            ), 0
        if "豪爽" in pers:
            return pick(
                f"{npc.name}大笑：「好！『{brief}』这事我记下了。」",
                f"{npc.name}拍你肩膀：「『{brief}』？痛快！说下去。」",
            ), 1
        if "贪" in pers:
            return f"{npc.name}眯眼：「『{brief}』？若与灵石有关，倒可谈谈。」", 0
        return pick(
            f"{npc.name}颔首：「道友所言『{brief}』，我已知悉。」",
            f"{npc.name}应道：「嗯，『{brief}』——然后呢？」",
        ), 0
