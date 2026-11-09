"""
法宝器灵（spec: gallery-gameplay §6，S 组）：挂器物实体的长线陪伴。

状态落 ItemEntity.custom_metadata["spirit"]（随器物流转，不挂人、不进
npc_chat 会话系统）；四维 = 名字/性格（hash(uid) 确定性）/心情/成长。
数值全部规则定：温养明价与日限、成长封顶、心情惰性衰减、战力加成
（通灵 +2% / 化形 +3%、多灵取最高、心情 ≥40 才生效，接入
CombatEngine.calculate_power 的乘子链，与 art_slots 同层）。
对话借 npc_chat 的「AI 出词 + 本地降级」形态：LLM 只产台词与四值基调
枚举，台词外的任何数字一律丢弃；AI 不可用走本地性格台词池。

【Spec 缺口注记】任务书提及的「护主/闹脾气/沉睡」关键节点事件在
gallery-gameplay.md §6 中并无触发阈值与结算定义（全文仅有 §6.4
「阶段晋升记 chronicle」与「心情跌破 20 面板警示」两处事件口径）。
本实现按该既有口径落三个呈现级事件（零新增数值，见
_spirit_event_label / _note_mood_events）：晋升 = 灵光护主（chronicle）、
心情跌破 20 = 闹脾气（面板警示 + chronicle 一次）、心情归 0 = 沉睡
（对话只回沉睡句、加成自然归零）。阈值若需调整须回主策岗改 Spec。
"""
from __future__ import annotations

import hashlib
import random
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from core.character_integrity import CharacterIntegrity, CharacterIntegrityError

# ---- §6 写死数字 ---------------------------------------------------------
SPIRIT_MIN_TIER = 4
NOURISH_COST = {4: 30, 5: 50}
NOURISH_GROWTH = 10
NOURISH_GROWTH_HALF = 5 # 缺目录材料时效力减半
NOURISH_MOOD = 8
TALK_GROWTH_DAILY = 2 # 每日首次对话成长
TALK_MOOD_DAILY = 3
GROWTH_CAP = {4: 100, 5: 150}
STAGE_TONGLING_GROWTH = 50 # ≥50 通灵
STAGE_HUAXING_GROWTH = 100 # ≥100 且 tier 5 才化形（tier 4 封顶即通灵满阶）
MOOD_DECAY_PER_DAY = 5
MOOD_BONUS_MIN = 40 # 心情 ≥40 加成才生效
MOOD_TANTRUM_BELOW = 20 # 跌破 20：闹脾气警示
POWER_BONUS = {1: 0.02, 2: 0.03} # 通灵 +2% / 化形 +3%（萌生 0）
TONES = ("pleased", "calm", "teasing", "sullen")

#: 性格六型（§6.2）：键 → (中文, 名字池, 本地台词池)
PERSONALITIES: Dict[str, Dict[str, Any]] = {
"lingli": {
"cn": "凌厉",
"names": ["霜儿", "断鸿", "寒锋", "绝影"],
"lines": [
"剑鸣即吾声。主人若战，吾必先鸣。",
"莫要迟疑，出鞘之时自见分晓。",
"锋芒不敛，方为利器。吾不喜温吞。",
"你今日的剑意，比昨日利了三分。",
],
"lines_high": [
"吾形已凝，愿随主人踏遍九霄，剑指之处无退路。",
"这一战，吾与你同进退——护主，是吾化形后唯一的执念。",
],
},
"wenrun": {
"cn": "温润",
"names": ["小璇", "润玉", "清晏", "温言"],
"lines": [
"主人莫急，灵气流转自有其时。",
"今日器身温润，想是主人心境平和之故。",
"我在这儿呢，一直都在。",
"温养之情，点滴都记在器纹里了。",
],
"lines_high": [
"化形之后，终于能与主人并肩看这山河了。",
"主人安好，吾便安好，此心如玉，护你周全。",
],
},
"jiaohua": {
"cn": "狡黠",
"names": ["狸奴", "小诡", "青媚", "灵狸"],
"lines": [
"嘻嘻，主人猜猜，我方才偷看了什么？",
"想要我出力？先说句好听的来听听。",
"那件旧法器方才抖了一下，是怕我呢。",
"主人身上有秘密，我可都闻得出来。",
],
"lines_high": [
"化形啦化形啦——这下逗主人的法子又多了一百种。",
"别看我爱闹，真到了险处，护主我可从不含糊。",
],
},
    "chenwen": {
        "cn": "沉稳",
        "names": ["玄钧", "老砚", "镇岳", "默翁"],
        "lines": [
            "器在人在，余者皆虚妄。",
            "主人今日气息沉稳，是好事。",
            "老朽守器多年，不急这一时。",
            "风浪再大，器心不动。",
        ],
        "lines_high": [
            "化形非为炫耀，是为在主人危难时，多挡一分。",
            "山岳无言，却从不曾退后半步。",
        ],
    },
    "zhiji": {
        "cn": "稚气",
        "names": ["团团", "小铃", "芽儿", "呦呦"],
        "lines": [
            "主人主人，今天也带我出去玩嘛！",
            "我数过啦，器身上有好多亮晶晶的纹路！",
            "你不理我，我就……我就自己跟自己说话。",
            "灵石的味道，闻起来像月亮！",
        ],
        "lines_high": [
            "我长大啦！化形之后，我要保护主人，不许别人欺负你！",
            "嘿嘿，护主这种事，我可是很认真的哦。",
        ],
    },
    "cangsang": {
        "cn": "沧桑",
        "names": ["残雪", "故渊", "迟暮", "沧翁"],
        "lines": [
            "旧主们的面孔，都淡了。只剩器纹还记得。",
            "岁月蚀器不蚀心。主人珍重。",
            "我见过太多离散。这一世，愿长久些。",
            "莫问来历。来历都在锈色里了。",
        ],
        "lines_high": [
            "化形再醒，故人已远。唯愿护得今主一世平安。",
            "这把老骨头，还能再为主人挡一次风雨。",
        ],
    },
}
PERSONALITY_ORDER = ["lingli", "wenrun", "jiaohua", "chenwen", "zhiji", "cangsang"]

_SLOT_ORDER = ("weapon", "armor", "trinket", "boots", "flying_treasure")


def _today_str(now: Optional[float] = None) -> str:
    return date.fromtimestamp(now if now is not None else time.time()).isoformat()


def _digest(uid: str) -> bytes:
    return hashlib.sha256(f"artifact-spirit:{uid}".encode("utf-8")).digest()


def personality_for_uid(uid: str) -> str:
    """性格由 hash(uid)%6 定（§6.2），同器恒同性格。"""
    return PERSONALITY_ORDER[_digest(uid)[0] % len(PERSONALITY_ORDER)]


def name_for_uid(uid: str, personality: str) -> str:
    pool = PERSONALITIES[personality]["names"]
    return pool[_digest(uid)[1] % len(pool)]


def growth_cap(tier: Any) -> int:
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 4
    return GROWTH_CAP[5] if t >= 5 else GROWTH_CAP[4]


def nourish_cost(tier: Any) -> int:
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 4
    return NOURISH_COST[5] if t >= 5 else NOURISH_COST[4]


def stage_for(growth: int, tier: Any) -> int:
    """阶段由 growth 推导（不单独落账）：萌生 0 / 通灵 1 / 化形 2。

    化形须 growth ≥100 且 tier ≥5；tier 4 封顶 100 即通灵满阶（§6.4
    明写的不对称，是品阶天花板而非 bug）。
    """
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 4
    if growth >= STAGE_HUAXING_GROWTH and t >= 5:
        return 2
    if growth >= STAGE_TONGLING_GROWTH:
        return 1
    return 0


STAGE_CN = {0: "萌生", 1: "通灵", 2: "化形"}


# ---------------------------------------------------------------------------
# 器物与器灵状态读写
# ---------------------------------------------------------------------------
def get_spirit(item: Any) -> Optional[Dict[str, Any]]:
    """已唤灵则返回 spirit dict（活引用，改后随角色行落盘）；否则 None。"""
    if item is None:
        return None
    sp = (getattr(item, "custom_metadata", None) or {}).get("spirit")
    if isinstance(sp, dict) and sp.get("awakened"):
        return sp
    return None


def equipped_items(char: Any) -> List[Any]:
    """已穿戴器物实体（§6.1：equipped 名单或任一 equip_slots 槽位），
    保持穿戴序、按 uid 去重。"""
    out: List[Any] = []
    used = set()
    items = list(getattr(char, "items", []) or [])

    def _take(name: str) -> None:
        if not name:
            return
        for it in items:
            if getattr(it, "uid", None) in used:
                continue
            if getattr(it, "name", "") == name:
                used.add(it.uid)
                out.append(it)
                return

    for name in getattr(char, "equipped", []) or []:
        _take(name)
    slots = getattr(char, "equip_slots", None)
    for slot in _SLOT_ORDER:
        _take(getattr(slots, slot, None) or "")
    return out


def _is_equip(item: Any) -> bool:
    kind = getattr(item, "kind", None)
    return getattr(kind, "value", kind) == "equip"


def find_equipped(char: Any, item_name: str = "") -> Optional[Any]:
    """在已穿戴器物里按名找（空名返回 None）；精确名优先，其次包含匹配。"""
    eq = equipped_items(char)
    q = (item_name or "").strip()
    if not q:
        return None
    for it in eq:
        if it.name == q:
            return it
    for it in eq:
        if q in it.name:
            return it
    return None


def default_spirit_item(char: Any) -> Optional[Any]:
    """默认对象（/灵语、/温养 缺省）：已唤灵已穿戴中 tier 最高者，
    并列取穿戴序在先者（§6.3）。"""
    best = None
    for it in equipped_items(char):
        if get_spirit(it) is None:
            continue
        if best is None or int(getattr(it, "tier", 0) or 0) > int(getattr(best, "tier", 0) or 0):
            best = it
    return best


def effective_mood(spirit: Dict[str, Any], now: Optional[float] = None) -> int:
    """心情惰性推导：距 last_touch_at 每满 1 现实日 -5，钳 0~100（§6.4）。"""
    t = now if now is not None else time.time()
    mood = int(spirit.get("mood") or 0)
    anchor = float(spirit.get("last_touch_at") or 0.0)
    if anchor > 0:
        days = int((t - anchor) // 86400)
        if days > 0:
            mood -= MOOD_DECAY_PER_DAY * days
    return max(0, min(100, mood))


def _fold_mood(spirit: Dict[str, Any], now: float) -> int:
    """把惰性衰减折算回落盘值并刷新互动锚（写路径调用）。"""
    mood = effective_mood(spirit, now)
    spirit["mood"] = mood
    spirit["last_touch_at"] = now
    return mood


def spirit_event_label(spirit: Dict[str, Any], now: Optional[float] = None) -> str:
    """呈现级事件标签（缺口注记见模块 docstring）：沉睡 / 闹脾气 / ""。"""
    mood = effective_mood(spirit, now)
    if mood <= 0:
        return "沉睡"
    if mood < MOOD_TANTRUM_BELOW:
        return "闹脾气"
    return ""


def _chronicle(actor_name: str, summary: str) -> None:
    try:
        from storage.db import ChronicleRepository

        ChronicleRepository.record("SPIRIT", actor_name, summary[:120])
    except Exception:
        pass

def _note_mood_events(char: Any, item: Any, spirit: Dict[str, Any], now: float) -> List[str]:
    """心情跨档事件（每档只记一次，档位存 spirit.mood_event_stage）：
    跌破 20 → 闹脾气；归 0 → 沉睡。回升过 20 后重置，可再次触发。"""
    mood = effective_mood(spirit, now)
    stage = int(spirit.get("mood_event_stage") or 0)
    notes: List[str] = []
    if mood <= 0 and stage < 2:
        spirit["mood_event_stage"] = 2
        _chronicle(char.name, f"【器灵沉睡】{char.name} 的【{item.name}】器灵「{spirit.get('name')}」灵光黯淡，沉入长眠——久未温养对话之故。")
        notes.append("器灵灵光黯淡，已沉入沉睡（心情归零）。温养可唤醒它。")
    elif mood < MOOD_TANTRUM_BELOW and stage < 1:
        spirit["mood_event_stage"] = 1
        _chronicle(char.name, f"【器灵闹脾气】{char.name} 的【{item.name}】器灵「{spirit.get('name')}」心情低落，闹起了脾气。")
        notes.append("器灵心情跌落谷底，正在闹脾气——加成暂歇，温养或陪它说说话吧。")
    elif mood >= MOOD_TANTRUM_BELOW and stage:
        spirit["mood_event_stage"] = 0
    return notes


def _note_stage_up(char: Any, item: Any, spirit: Dict[str, Any], old_stage: int, new_stage: int) -> List[str]:
    """阶段晋升（护主节点）：chronicle 一条 + 呈现一句，无数值发放（§6.4）。"""
    if new_stage <= old_stage:
        return []
    _chronicle(
        char.name,
        f"【器灵护主】{char.name} 的【{item.name}】器灵「{spirit.get('name')}」晋升【{STAGE_CN[new_stage]}】，灵光护主，战力自此得其加持。",
    )
    return [f"器灵「{spirit.get('name')}」晋升【{STAGE_CN[new_stage]}】——灵光护主，自此战力得其加持（无其他发放）。"]


def public_spirit_dict(item: Any, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """命盘 equipped[].spirit 下发（§6.5）：未唤灵/无实体为 None。"""
    spirit = get_spirit(item)
    if spirit is None:
        return None
    tier = int(getattr(item, "tier", 4) or 4)
    growth = int(spirit.get("growth") or 0)
    stage = stage_for(growth, tier)
    try:
        from core.gallery_assets import artifact_key_for_item, asset_path

        img = asset_path(artifact_key_for_item(item))
    except Exception:
        img = ""
    return {
        "name": spirit.get("name") or "",
        "personality_cn": PERSONALITIES.get(spirit.get("personality") or "", {}).get("cn", ""),
        "stage_cn": STAGE_CN[stage],
        "stage": stage,
        "mood": effective_mood(spirit, now),
        "growth": growth,
        "img": img,
    }


# ---------------------------------------------------------------------------
# 唤灵（S-1）
# ---------------------------------------------------------------------------
def awaken(char: Any, item_name: str, now: Optional[float] = None) -> Dict[str, Any]:
    """唤灵：tier≥4 且已穿戴的 equip 一生一次（spirit.awakened 为闸门）。

    门禁 assert_alive + assert_idle（§11）；一次性、无费用。
    """
    t = now if now is not None else time.time()
    try:
        CharacterIntegrity.assert_alive(char, now=t)
        CharacterIntegrity.assert_idle(char, action="/器灵")
    except CharacterIntegrityError as e:
        return {"success": False, "message": str(e), "changed": False}
    item = find_equipped(char, item_name)
    if item is None:
        any_item = char.find_item(item_name) if item_name else None
        if any_item is not None and _is_equip(any_item):
            return {"success": False, "changed": False,
                    "message": f"【{any_item.name}】尚未穿戴——器灵只寄于已穿戴的法宝（§6.1）。先穿戴再唤灵。"}
        return {"success": False, "changed": False,
                "message": "未找到这件已穿戴的法宝。/器灵 查看可唤灵的穿戴法宝。"}
    if not _is_equip(item) or int(getattr(item, "tier", 0) or 0) < SPIRIT_MIN_TIER:
        return {"success": False, "changed": False,
                "message": f"【{item.name}】品阶未至天品（tier≥4），灵性未萌，不可唤灵。"}
    existing = get_spirit(item)
    if existing is not None:
        return {"success": True, "changed": False,
                "message": f"【{item.name}】的器灵「{existing.get('name')}」早已苏醒，不必再唤（四维不重置）。\n" + panel_text(char, now=t)}
    personality = personality_for_uid(str(item.uid))
    spirit = {
        "awakened": True,
        "name": name_for_uid(str(item.uid), personality),
        "personality": personality,
        "growth": 0,
        "mood": 60,
        "last_touch_at": t,
        "last_nourish_date": "",
        "last_talk_date": "",
        "nourish_count": 0,
        "talk_count": 0,
        "awakened_by": char.id,
        "awakened_by_name": char.name,
        "mood_event_stage": 0,
    }
    item.custom_metadata["spirit"] = spirit
    _chronicle(char.name, f"【唤灵】{char.name} 唤醒【{item.name}】的器灵「{spirit['name']}」（{PERSONALITIES[personality]['cn']}）。")
    try:
        from core import gallery as _gallery

        _gallery.unlock_from_character(char)  # §6.1 图鉴相关点亮（法宝图派生口径）
    except Exception:
        pass
    return {
        "success": True,
        "changed": True,
        "message": (
            f"【唤灵】{item.name} 灵光乍现——器灵「{spirit['name']}」苏醒，性格【{PERSONALITIES[personality]['cn']}】，"
            f"阶段【萌生】，心情 60。\n以 /温养 滋养它、/灵语 与它说话；它随器而行，器在，灵便在。"
        ),
    }


# ---------------------------------------------------------------------------
# 温养（S-2/S-3）
# ---------------------------------------------------------------------------
def _catalog_material(item: Any) -> Tuple[str, int]:
    """目录 repair_materials 的首个材料（名, 需量）；无目录/无配方 → ("", 0)。"""
    try:
        from core.catalogs import get_equipment

        cfg = get_equipment(item.name) or {}
        mats = cfg.get("repair_materials") or {}
        if isinstance(mats, dict) and mats:
            name, count = next(iter(mats.items()))
            return str(name), max(1, int(count or 1))
    except Exception:
        pass
    return "", 0


def _has_material(char: Any, mat_name: str, count: int) -> bool:
    held_entities = len([it for it in (char.items or []) if it.name == mat_name])
    held_names = list(char.inventory or []).count(mat_name)
    return max(held_entities, held_names) >= count


def _consume_material(char: Any, mat_name: str, count: int) -> bool:
    """消耗材料 count 件（实体优先；remove_item_entity 同步删 inventory 一条）。

    inventory 与 items 同名双写，计数以实体为准；仅名字持有（legacy）时
    删 inventory。不足返回 False 且零消耗（调用方先以 _has_material 预检）。
    """
    held_entities = [it for it in (char.items or []) if it.name == mat_name]
    if len(held_entities) >= count:
        for it in held_entities[:count]:
            char.remove_item_entity(it.uid)
        return True
    if list(char.inventory or []).count(mat_name) >= count:
        for _ in range(count):
            char.inventory.remove(mat_name)
        return True
    return False


def nourish(char: Any, item_name: str = "", now: Optional[float] = None) -> Dict[str, Any]:
    """温养：明价（tier4 30 / tier5 50 灵石）、每器 1 次/现实日。

    门禁 assert_alive + assert_currency（轻行为不调 assert_idle，§6.4）。
    目录有 repair_materials 时另耗材料：有材全效（成长 +10），缺材只扣
    灵石、成长 +5 并明示。重复/不足一律零副作用。
    """
    t = now if now is not None else time.time()
    try:
        CharacterIntegrity.assert_alive(char, now=t)
    except CharacterIntegrityError as e:
        return {"success": False, "message": str(e), "changed": False}
    item = find_equipped(char, item_name) if item_name else default_spirit_item(char)
    if item is None:
        return {"success": False, "changed": False,
                "message": "没有已唤灵的已穿戴法宝可温养。先 /器灵 唤 醒一件天品以上法宝。"}
    spirit = get_spirit(item)
    if spirit is None:
        return {"success": False, "changed": False,
                "message": f"【{item.name}】尚未唤灵。先 /器灵 唤 {item.name}。"}
    today = _today_str(t)
    if spirit.get("last_nourish_date") == today:
        return {"success": False, "changed": False,
                "message": f"【{item.name}】的器灵今日已温养过（每器每日一次），灵石未动。明日再来。"}
    tier = int(getattr(item, "tier", 4) or 4)
    cost = nourish_cost(tier)
    try:
        CharacterIntegrity.assert_currency(char, cost)
    except CharacterIntegrityError as e:
        return {"success": False, "message": str(e), "changed": False}

    mat_name, mat_count = _catalog_material(item)
    full = True
    mat_note = ""
    if mat_name:
        if _has_material(char, mat_name, mat_count):
            _consume_material(char, mat_name, mat_count)
            mat_note = f"另耗材料【{mat_name}】×{mat_count}。"
        else:
            full = False
            mat_note = f"缺材温养：无【{mat_name}】可耗，效力减半（成长 +{NOURISH_GROWTH_HALF}）。"
    CharacterIntegrity.deduct_currency(char, cost)

    old_stage = stage_for(int(spirit.get("growth") or 0), tier)
    _fold_mood(spirit, t)
    gain = NOURISH_GROWTH if full else NOURISH_GROWTH_HALF
    spirit["growth"] = min(growth_cap(tier), int(spirit.get("growth") or 0) + gain)
    spirit["mood"] = min(100, int(spirit.get("mood") or 0) + NOURISH_MOOD)
    spirit["last_nourish_date"] = today
    spirit["nourish_count"] = int(spirit.get("nourish_count") or 0) + 1
    new_stage = stage_for(int(spirit["growth"]), tier)
    notes = _note_stage_up(char, item, spirit, old_stage, new_stage)
    notes += _note_mood_events(char, item, spirit, t)
    msg = (
        f"【温养】灵石 -{cost}。{mat_note}器灵「{spirit.get('name')}」成长 +{gain}"
        f"（{spirit['growth']}/{growth_cap(tier)}，{STAGE_CN[new_stage]}）、心情 +{NOURISH_MOOD}（{spirit['mood']}）。"
    )
    if notes:
        msg += "\n" + "\n".join(notes)
    return {"success": True, "changed": True, "message": msg}


# ---------------------------------------------------------------------------
# 对话（S-4）：AI 只出词与基调枚举，数值规则定；本地台词池降级
# ---------------------------------------------------------------------------
def _local_line(item: Any, spirit: Dict[str, Any], now: float) -> Tuple[str, str]:
    """本地降级台词：按 personality × stage 出句，tone 恒 calm（§6.3）。"""
    if effective_mood(spirit, now) <= 0:
        return "（器灵沉睡不醒，只余器身微光浮动。）", "calm"
    persona = PERSONALITIES.get(spirit.get("personality") or "", {})
    lines = list(persona.get("lines") or ["……"])
    tier = int(getattr(item, "tier", 4) or 4)
    if stage_for(int(spirit.get("growth") or 0), tier) >= 2:
        lines += persona.get("lines_high") or []
    rng = random.Random(f"spirit-line:{item.uid}:{spirit.get('talk_count')}:{_today_str(now)}")
    return rng.choice(lines), "calm"


def generate_spirit_reply(char: Any, item: Any, spirit: Dict[str, Any],
                          text: str, history: List[Dict[str, str]],
                          now: Optional[float] = None) -> Optional[Tuple[str, str]]:
    """AI 路径：经 ai.gateway 生成一句话 + 基调枚举；失败/非法返回 None。

    只取 line 与 tone 两字段，其余字段（含 LLM 给出的任何数字）一律丢弃。
    测试可 monkeypatch 本函数模拟 AI 态/伪造数字返回。
    """
    t = now if now is not None else time.time()
    try:
        from ai.gateway import _chat_json, ai_ready

        if not ai_ready():
            return None
        persona = PERSONALITIES.get(spirit.get("personality") or "", {})
        tier = int(getattr(item, "tier", 4) or 4)
        hist = "；".join(f"{h.get('who')}:{h.get('text')}" for h in (history or [])[-6:])
        prompt = (
            "你是修仙法宝的器灵，只输出 JSON。\n"
            f"法宝：{item.name}（{getattr(item, 'tier_name', '')}）；器灵名：{spirit.get('name')}；"
            f"性格：{persona.get('cn', '')}；阶段：{STAGE_CN[stage_for(int(spirit.get('growth') or 0), tier)]}；"
            f"心情：{effective_mood(spirit, t)}/100。\n"
            f"近况对话：{hist or '无'}\n主人对你说：{text[:120]}\n"
            '以器灵口吻回一句话（40 字内），并给出心情基调 tone（pleased/calm/teasing/sullen 四选一）。\n'
            '输出：{"line":"...","tone":"calm"}。禁止输出任何数值字段。'
        )
        data = _chat_json(prompt, timeout=10.0)
        if not isinstance(data, dict):
            return None
        line = str(data.get("line") or "").strip()[:120]
        tone = str(data.get("tone") or "").strip().lower()
        if not line or tone not in TONES:
            return None
        return line, tone
    except Exception:
        return None


_CTX_KEY_PREFIX = "spirit_chat:"


def _load_context(char_id: str, item_uid: str) -> List[Dict[str, str]]:
    try:
        from storage.db import WorldStateRepository

        raw = WorldStateRepository.get(f"{_CTX_KEY_PREFIX}{char_id}:{item_uid}") or []
        if isinstance(raw, list):
            return [h for h in raw if isinstance(h, dict)][-12:]
    except Exception:
        pass
    return []


def _save_context(char_id: str, item_uid: str, history: List[Dict[str, str]]) -> None:
    try:
        from storage.db import WorldStateRepository

        WorldStateRepository.set(f"{_CTX_KEY_PREFIX}{char_id}:{item_uid}", history[-12:])
    except Exception:
        pass


def talk(char: Any, raw_text: str, now: Optional[float] = None) -> Dict[str, Any]:
    """灵语：对象解析（「<器物名> · <话>」或缺省最高 tier）、规则结算。

    门禁 assert_alive + assert_idle（§6.4 定死）。每日首次对话成长 +2、
    心情 +3；后续只叙事。AI 不可用走本地台词池，结算不受影响。
    """
    t = now if now is not None else time.time()
    try:
        CharacterIntegrity.assert_alive(char, now=t)
        CharacterIntegrity.assert_idle(char, action="/灵语")
    except CharacterIntegrityError as e:
        return {"success": False, "message": str(e), "changed": False}
    text = (raw_text or "").strip()
    item = None
    if "·" in text:
        head, _, rest = text.partition("·")
        cand = find_equipped(char, head.strip())
        if cand is not None and get_spirit(cand) is not None:
            item = cand
            text = rest.strip()
    if item is None:
        item = default_spirit_item(char)
    if item is None:
        return {"success": False, "changed": False,
                "message": "你还没有已唤灵的器灵。先以 /器灵 唤 醒一件已穿戴的天品以上法宝，再来 /灵语。"}
    if not text:
        return {"success": False, "changed": False,
                "message": "用法：/灵语 <想说的话>（或 /灵语 <器物名> · <话> 指定器灵）"}
    spirit = get_spirit(item)
    tier = int(getattr(item, "tier", 4) or 4)

    history = _load_context(char.id, str(item.uid))
    history.append({"who": char.name, "text": text[:200]})
    reply = generate_spirit_reply(char, item, spirit, text, history, now=t)
    if reply is None:
        line, tone = _local_line(item, spirit, t)
        source = "local"
    else:
        line, tone = reply
        source = "ai"
    history.append({"who": spirit.get("name") or "器灵", "text": line})
    _save_context(char.id, str(item.uid), history)

    old_stage = stage_for(int(spirit.get("growth") or 0), tier)
    _fold_mood(spirit, t)
    today = _today_str(t)
    growth_note = ""
    if spirit.get("last_talk_date") != today:
        before = int(spirit.get("growth") or 0)
        spirit["growth"] = min(growth_cap(tier), before + TALK_GROWTH_DAILY)
        spirit["mood"] = min(100, int(spirit.get("mood") or 0) + TALK_MOOD_DAILY)
        spirit["last_talk_date"] = today
        growth_note = f"（今日初语：成长 +{int(spirit['growth']) - before}、心情 +{TALK_MOOD_DAILY}）"
    spirit["talk_count"] = int(spirit.get("talk_count") or 0) + 1
    new_stage = stage_for(int(spirit["growth"]), tier)
    notes = _note_stage_up(char, item, spirit, old_stage, new_stage)
    notes += _note_mood_events(char, item, spirit, t)
    persona_cn = PERSONALITIES.get(spirit.get("personality") or "", {}).get("cn", "")
    msg = f"【灵语 · {item.name}】{spirit.get('name')}（{persona_cn}·{STAGE_CN[new_stage]}）：{line}"
    if growth_note:
        msg += "\n" + growth_note
    if notes:
        msg += "\n" + "\n".join(notes)
    return {
        "success": True,
        "changed": True,
        "message": msg,
        "reply": line,
        "tone": tone,
        "source": source,
        "item_name": item.name,
        "spirit_name": spirit.get("name"),
    }


# ---------------------------------------------------------------------------
# 战力加成（S-5）与面板
# ---------------------------------------------------------------------------
def panel_text(char: Any, now: Optional[float] = None) -> str:
    """器灵面板（/器灵，双端同源文本）：已穿戴法宝的器灵四维与入口。"""
    t = now if now is not None else time.time()
    lines = ["【器灵】寄于已穿戴法宝之灵（随器而行，不随人）。"]
    eq = equipped_items(char)
    if not eq:
        lines.append("当前未穿戴任何法宝。")
        return "\n".join(lines)
    any_spirit = False
    for it in eq:
        tier = int(getattr(it, "tier", 0) or 0)
        spirit = get_spirit(it)
        if spirit is None:
            if _is_equip(it) and tier >= SPIRIT_MIN_TIER:
                lines.append(f"· 【{it.name}】（{getattr(it, 'tier_name', '')}）灵性已萌，未唤灵——/器灵 唤 {it.name}")
            else:
                lines.append(f"· 【{it.name}】（{getattr(it, 'tier_name', '')}）品阶未至天品，无灵。")
            continue
        any_spirit = True
        growth = int(spirit.get("growth") or 0)
        stage = stage_for(growth, tier)
        mood = effective_mood(spirit, t)
        label = spirit_event_label(spirit, t)
        persona_cn = PERSONALITIES.get(spirit.get("personality") or "", {}).get("cn", "")
        line = (
            f"· 【{it.name}】器灵「{spirit.get('name')}」（{persona_cn}）"
            f"｜阶段 {STAGE_CN[stage]}｜成长 {growth}/{growth_cap(tier)}｜心情 {mood}"
        )
        if spirit.get("awakened_by_name") and spirit.get("awakened_by_name") != char.name:
            line += f"｜此灵曾随旧主【{spirit.get('awakened_by_name')}】，今随器归你"
        if label == "沉睡":
            line += "｜【沉睡中】久未照拂，灵光黯淡——/温养 可唤醒"
        elif label == "闹脾气":
            line += "｜【闹脾气】心情过低，加成暂歇——/温养 或 /灵语 安抚"
        elif mood < MOOD_BONUS_MIN and stage >= 1:
            line += "｜心情不足 40，器灵怠工（加成不生效）"
        lines.append(line)
    if any_spirit:
        lines.append("操作：/温养 [器物名] 滋养（每日一次）｜/灵语 <话> 交谈（可 /灵语 <器物名> · <话> 指定）")
    return "\n".join(lines)


def panel_data(char: Any, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """器灵面板行集（/器灵 spirit 键；与 panel_text 同源）。

    未穿戴任何法宝时返回 None（调用方不下发 spirit 键）。
    """
    eq = equipped_items(char)
    if not eq:
        return None
    items = []
    awakenable: List[str] = []
    for it in eq:
        tier = int(getattr(it, "tier", 0) or 0)
        spirit = get_spirit(it)
        can_awaken = _is_equip(it) and tier >= SPIRIT_MIN_TIER and spirit is None
        if can_awaken:
            awakenable.append(it.name)
        items.append(
            {
                "name": it.name,
                "tier": tier,
                "tier_name": getattr(it, "tier_name", ""),
                "spirit": dict(spirit) if spirit else None,
                "can_awaken": can_awaken,
            }
        )
    return {"items": items, "awakenable": awakenable}


class ArtifactSpiritEngine:
    """器灵规则引擎门面（唤灵/温养/对话/加成/面板）。"""

    awaken = staticmethod(awaken)
    nourish = staticmethod(nourish)
    talk = staticmethod(talk)
    panel_text = staticmethod(panel_text)

    @staticmethod
    def power_bonus(char: Any, now: Optional[float] = None) -> float:
        """战力乘子：已穿戴已唤灵器灵中只取最高一件；心情 <40 不生效。"""
        best = 0.0
        for it in equipped_items(char):
            spirit = get_spirit(it)
            if spirit is None:
                continue
            if effective_mood(spirit, now) < MOOD_BONUS_MIN:
                continue
            stage = stage_for(int(spirit.get("growth") or 0), int(getattr(it, "tier", 4) or 4))
            best = max(best, POWER_BONUS.get(stage, 0.0))
        return 1.0 + best
