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
    newer_pending_count = 0
    if success and fate_drawn:
        pending = getattr(character, "fate_pending", None) or []
        if pending:
            # MF-2 修复：唯一选择函数 apply_fate_choice 只认最老一抽
            # （pending[0]，FIFO 写死），仪式 choices 必须与之同抽——
            # 此前取 pending[-1]（最新一抽）致仪式内选择必被拒。
            choices = list(pending[0].get("candidates") or [])
            newer_pending_count = len(pending) - 1
            after_text = "天道垂鉴，命格三选其一——此刻不选，日后于命盘 /命格 择定亦可。"
            if newer_pending_count > 0:
                after_text += (
                    f"（按天道次序先择此抽；另有 {newer_pending_count} 抽更新的"
                    "待选命格，将在本抽择定后依次呈上。）")
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
            # MF-2 只增字段：呈现抽（pending[0]）之外尚待选的新抽数
            "fate_pending_newer_count": newer_pending_count,
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


# ---------------- game-feel-phase3 新增三幕（§3/§4/§5） ----------------
# 三幕与既有三幕同契约：纯读拼装（已结算数据 + 本地模板）、不落库、
# skippable=True、beats 三段、choices 恒 null（命格候选是全仓唯一合法
# choices 形状，新三幕无仪式内落账选择，不得借用 /命格 通道）。

_LOOT_PRELUDES_EQUIP = [
    "匣盖未启，{name}的锋芒已透匣而出，{place}的灵气为之一凝。",
    "土层之下宝光冲霄——尚未见物，先闻其鸣。",
    "掘至深处，一道清光破土而起，照得四周纤毫毕现。",
]
_LOOT_PRELUDES_RELIC = [
    "地脉深处传来一声悠远的嗡鸣，仿佛有古物在黑暗中醒来。",
    "匣中之物尚未露面，{place}的风先静了——重宝出世，万籁低头。",
]

_TRIB_PRELUDE_BY_BAND = {
    "low": "劫云初聚，天光微暗——{realm}的第一道门槛，伴着雷声到了。",
    "mid": "九天之上劫云层层叠压，电蛇在云腹中游走——{realm}之劫，声势已成。",
    "high": "天穹裂开一线，劫气如瀑倾泻而下——{realm}的天劫，是刻在命数里的一关。",
}
_TRIB_REVEAL_FAIL = {
    "DEATH": "劫雷贯顶而下，护体灵光只撑了一瞬，便如琉璃般层层碎裂。",
    "BASE_COLLAPSE": "雷火顺经脉窜入丹田，道基在轰鸣中崩开裂口。",
    "HEART_DEMON": "劫雷未至，幻象先行——雷声里混着旧人旧事的声音，一齐涌上心头。",
    "WOUNDED": "神雷当头劈落，虽以法宝硬抗，余劲仍震得经脉寸寸发麻。",
}
_TRIB_CONCLUSION_FAIL = {
    "DEATH": "雷声止歇之处，只余劫灰——这一劫，此身没能渡过。",
    "BASE_COLLAPSE": "劫云散去，道基已损——这一劫，败在了根基上。",
    "HEART_DEMON": "雷云压顶之时道心先乱——这一劫，败给了心里的那个自己。",
    "WOUNDED": "最后一道雷擦身而过——这一劫，只差一线。",
}
_TRIB_AFTER_FAIL = {
    "BASE_COLLAPSE": "劫后余烬未冷，先稳住道基，再谈来日。",
    "HEART_DEMON": "劫云虽散，心魔未消——调息压念，来日再战。",
    "WOUNDED": "劫后经脉震荡，宜静养些时日，再图破境。",
}


def loot_ceremony_candidate(kind: Any, tier: Any) -> bool:
    """得宝幕门槛谓词（§3.2 定死）：equip tier≥4 或 relic tier≥3。

    equip 线与器灵 SPIRIT_MIN_TIER=4 同一品阶线；relic 本身即稀世
    重宝语义，线取 tier≥3（覆盖地渊遗迹的恒 tier3 头奖）。其余
    kind 任意 tier 均不触发。
    """
    k = getattr(kind, "value", kind)
    try:
        t = int(tier)
    except (TypeError, ValueError):
        return False
    return (k == "equip" and t >= 4) or (k == "relic" and t >= 3)


def _artifact_asset(name: str, slot: Optional[str] = None, item: Any = None) -> Optional[str]:
    """法宝图键：经 gallery 解析且必须落在资产全集内，否则 None。"""
    try:
        from core.gallery_assets import (
            GALLERY_ASSET_KEYS,
            artifact_key_for,
            artifact_key_for_item,
        )

        key = artifact_key_for_item(item) if item is not None else artifact_key_for(
            name, slot=slot)
        return key if key in GALLERY_ASSET_KEYS else None
    except Exception:
        return None


def build_loot_ceremony(
    character: Character, equip_info: Dict[str, Any], *, source: str = "treasure_dig",
) -> Dict[str, Any]:
    """得宝幕（§3.4）：入参为已落账的获得物摘要（dig 的 equipment
    dict 原样形状，或盲匣路由实体组装的同形状 dict），纯读拼装。"""
    import zlib

    kind = str(getattr(equip_info.get("kind"), "value", equip_info.get("kind")) or "")
    try:
        tier = int(equip_info.get("tier") or 0)
    except (TypeError, ValueError):
        tier = 0
    name = str(equip_info.get("name") or "无名法宝")
    uid = str(equip_info.get("uid") or "")
    tier_name = str(equip_info.get("tier_name") or equip_info.get("tierName") or "")
    slot = equip_info.get("slot")
    affixes = [a for a in (equip_info.get("affixes") or []) if isinstance(a, dict)]
    affixes_text = "、".join(str(a.get("name") or "") for a in affixes if a.get("name"))
    lore = str(equip_info.get("lore") or "")
    asset_key = _artifact_asset(name, slot=slot)

    pool = _LOOT_PRELUDES_RELIC if kind == "relic" else _LOOT_PRELUDES_EQUIP
    idx = zlib.crc32(uid.encode("utf-8")) % len(pool) if uid else 0
    prelude_text = pool[idx].format(
        name=name, place=getattr(character, "location", "") or "此地")
    beats: List[Dict[str, Any]] = [{
        "stage": "prelude", "text": prelude_text,
        "asset_key": asset_key, "choices": None,
    }]
    reveal_lines = [f"【{name}】（{tier_name}）"]
    if affixes:
        for a in affixes:
            reveal_lines.append(f"{a.get('name', '')}：{a.get('desc', '')}")
    elif kind == "relic" and lore:
        reveal_lines.append(lore)
    else:
        reveal_lines.append(f"品阶【{tier_name}】，灵光内蕴，一看便知不是凡物。")
    beats.append({
        "stage": "reveal", "text": "\n".join(reveal_lines),
        "asset_key": asset_key, "choices": None,
    })
    after_lines = ["已入纳戒，行囊之中自此多了一件压箱底的宝物。"]
    if kind == "equip" and tier >= 4:
        after_lines.append(
            "此宝灵性已萌——穿戴之后，可凭 /器灵 唤 唤醒其器灵（须先穿戴）。")
    if kind == "relic":
        after_lines.append("稀世重宝现世，此物来历非凡，江湖中怕是要多些打探的目光。")
    beats.append({
        "stage": "aftermath", "text": "\n".join(after_lines),
        "asset_key": None, "choices": None,
    })
    return {
        "kind": "loot",
        "beats": beats,
        "result_ref": {
            "uid": uid,
            "name": name,
            "kind": kind,
            "tier": tier,
            "tier_name": tier_name,
            "slot": slot,
            "source": source,
            "affixes_text": affixes_text,
        },
        "skippable": True,
    }


_SPIRIT_PRELUDES = [
    "【{name}】的器纹自尾至首逐段亮起，如沉睡多年的眼睛缓缓睁开。",
    "一声轻鸣自【{name}】深处传来——不是金铁之声，是初醒之灵的第一声呼吸。",
]


def build_spirit_ceremony(character: Character, item: Any) -> Dict[str, Any]:
    """器灵认主幕（§4.2）：挂 awaken 的 changed=True 之后，纯读
    spirit 落账拼装；第一句话走本地性格台词池（零 AI，X4 口径）。"""
    import zlib

    from core.artifact_spirit import (
        PERSONALITIES,
        get_spirit,
        public_spirit_dict,
        stage_for,
    )

    spirit = get_spirit(item) or {}
    pub = public_spirit_dict(item) or {}
    name = str(getattr(item, "name", "") or "")
    tier = int(getattr(item, "tier", 0) or 0)
    tier_name = str(getattr(item, "tier_name", "") or "")
    uid = str(getattr(item, "uid", "") or "")
    asset_key = _artifact_asset(name, item=item)

    idx = zlib.crc32(uid.encode("utf-8")) % len(_SPIRIT_PRELUDES) if uid else 0
    beats: List[Dict[str, Any]] = [{
        "stage": "prelude",
        "text": _SPIRIT_PRELUDES[idx].format(name=name) + f"（{tier_name}）",
        "asset_key": asset_key, "choices": None,
    }]
    personality = str(spirit.get("personality") or "")
    personality_cn = pub.get("personality_cn") or PERSONALITIES.get(
        personality, {}).get("cn", "")
    spirit_name = str(spirit.get("name") or "")
    line = ""
    try:
        from core.artifact_spirit import _local_line

        line, _tone = _local_line(item, spirit, time.time())
    except Exception:
        line = ""
    pool = list(PERSONALITIES.get(personality, {}).get("lines") or [])
    if (not line or "沉睡" in line) and pool:
        # awaken 时点 mood=60 恒不沉睡；此分支只是 C3 兜底，不得空白幕
        line = pool[zlib.crc32(uid.encode("utf-8")) % len(pool)] if uid else pool[0]
    reveal_text = (
        f"器灵「{spirit_name}」（{personality_cn}·萌生）自器身中睁开眼睛。\n"
        f"它的第一句话是：「{line}」"
    )
    beats.append({
        "stage": "reveal", "text": reveal_text,
        "asset_key": asset_key, "choices": None,
    })
    beats.append({
        "stage": "aftermath",
        "text": "器灵自此常驻此宝：命盘法宝卡可见其名号与状态；"
                "/温养 可滋养它成长，/灵语 可与它说话。",
        "asset_key": None, "choices": None,
    })
    return {
        "kind": "spirit",
        "beats": beats,
        "result_ref": {
            "item_uid": uid,
            "item_name": name,
            "tier": tier,
            "spirit_name": spirit_name,
            "personality": personality,
            "personality_cn": personality_cn,
            "stage": stage_for(int(spirit.get("growth") or 0), tier),
            "mood": int(spirit.get("mood") or 0),
        },
        "skippable": True,
    }


def build_tribulation_ceremony(
    character: Character, attempt_result: Dict[str, Any],
) -> Dict[str, Any]:
    """天劫幕（§5.4）：与突破幕同源同闸（attempt.is_major），纯读
    attempt 返回 + char 只读字段拼装。此幕演劫、突破幕演果：成败的
    境界/寿元数字留给突破幕 result_ref，本幕不重复报数。"""
    from config import REALM_NAMES

    success = bool(attempt_result.get("success"))
    is_fatal = bool(attempt_result.get("is_fatal"))
    fail_tier = attempt_result.get("fail_tier") or None
    cur_tier = int(character.realm.tier)
    target_tier = cur_tier if success else cur_tier + 1
    pre_tier = target_tier - 1 if success else cur_tier
    if success:
        target_name = attempt_result.get("new_realm") or character.realm.name
    elif 0 <= target_tier < len(REALM_NAMES):
        target_name = REALM_NAMES[target_tier]
    else:
        target_name = character.realm.name

    band = "low" if target_tier <= 2 else ("mid" if target_tier <= 4 else "high")
    beats: List[Dict[str, Any]] = [{
        "stage": "prelude",
        "text": _TRIB_PRELUDE_BY_BAND[band].format(realm=target_name),
        "asset_key": _portrait_asset(character, pre_tier),
        "choices": None,
    }]
    if success:
        thunder_line = "劫雷九重，一重凶过一重——最后一道紫雷落下时，云层为之裂开。"
    else:
        thunder_line = _TRIB_REVEAL_FAIL.get(
            str(fail_tier or ""), "劫雷轰然劈落，护体灵光剧烈震荡。")
    demon_line = ""
    try:
        from core.heart_demon_state import DemonStateEngine

        s = DemonStateEngine.summary(character)
        if s.get("stage", 0) > 0:
            demon_line = (
                f"心魔【{s.get('stage_name', '')}】（魔念 {s.get('seed', 0)}）"
                "在劫雷间隙窥伺，道心与之相抗。")
    except Exception:
        demon_line = ""
    if not demon_line:
        demon_line = "劫雷之下，道心守一。"
    if success:
        verdict_line = "劫云为之让路——这一劫，渡过去了。"
    else:
        verdict_line = _TRIB_CONCLUSION_FAIL.get(
            str(fail_tier or ""), "劫云未散，这一劫没能渡过。")
    beats.append({
        "stage": "reveal",
        "text": "\n".join([thunder_line, demon_line, verdict_line]),
        "asset_key": None, "choices": None,
    })
    if success:
        after_text = (
            "雷音已传四方，江湖中又多了一位渡劫功成者。"
            if target_tier >= 2 else "劫云散尽，天地复归清明。")
    elif is_fatal:
        after_text = "此身已殁，归府之仪将于再入轮回时续演——前尘种种，自有天道收束。"
    else:
        after_text = _TRIB_AFTER_FAIL.get(
            str(fail_tier or ""), "劫后余烬未冷，先稳住根基，再谈来日。")
    beats.append({
        "stage": "aftermath", "text": after_text,
        "asset_key": None, "choices": None,
    })
    return {
        "kind": "tribulation",
        "beats": beats,
        "result_ref": {
            "success": success,
            "is_major": True,
            "is_fatal": is_fatal,
            "fail_tier": fail_tier,
            "new_realm": attempt_result.get("new_realm") or character.realm.name,
            "target_tier": target_tier,
            "prob_pct": attempt_result.get("prob_pct"),
            "judge_source": attempt_result.get("judge_source"),
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
