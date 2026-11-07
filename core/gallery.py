"""
图鉴（spec: gallery-gameplay §8）：账户级收集，WorldState KV 落点。

键 gallery_atlas:{user_id}，值 {"unlocked": {<asset_key>: <ts>}, "titles": [...]}。
点亮唯一写入口为合并式 unlock（只增不减、全集外脏键清除）；派生型点亮
由命盘快照推导（derive_keys_from_character），事件型点亮（NPC 原型 /
奇遇配图）走 unlock 同一入口。奖励口径定死：只给展示称号、零数值，
称号不写入 dao_title（§8.4）。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

from core.gallery_assets import (
    GALLERY_ASSET_KEYS,
    REALM_KEYS,
    artifact_key_for_equip_name,
    artifact_key_for_item,
    art_key_for,
    asset_path,
    map_key_for_tier,
)

ATLAS_KEY_PREFIX = "gallery_atlas:"

#: 里程碑称号（§8.4）：点亮数阈值 → 展示称号，零数值奖励
GALLERY_TITLES = [
    (10, "初窥门径"),
    (20, "博览群真"),
    (30, "洞鉴乾坤"),
    (38, "图录大成"),
]

#: 图鉴分组（panel 文本与前端展示表同序）
GALLERY_GROUPS = [
    ("人物·男相", [f"portraits/male-{r}" for r in REALM_KEYS]),
    ("人物·女相", [f"portraits/female-{r}" for r in REALM_KEYS]),
    ("人物·NPC原型", ["portraits/npc-laodao", "portraits/npc-shanggu", "portraits/npc-nvxiu", "portraits/npc-shaonian"]),
    ("法宝", [f"artifacts/{k}" for k in ("sword", "cauldron", "banner", "orb", "mirror", "bell", "pagoda", "gourd", "fan", "seal")]),
    ("功法", [f"arts/{k}" for k in ("metal", "wood", "water", "fire", "earth", "thunder", "sword", "ice")]),
    ("藏宝图", [f"maps/map-{r}" for r in ("common", "fine", "rare", "ancient")]),
]

KEY_CN = {
    **{f"portraits/male-{r}": f"男相·{cn}" for r, cn in zip(REALM_KEYS, ("练气", "筑基", "金丹", "元婴", "化神", "炼虚"))},
    **{f"portraits/female-{r}": f"女相·{cn}" for r, cn in zip(REALM_KEYS, ("练气", "筑基", "金丹", "元婴", "化神", "炼虚"))},
    "portraits/npc-laodao": "NPC·老道",
    "portraits/npc-shanggu": "NPC·商贾",
    "portraits/npc-nvxiu": "NPC·女修",
    "portraits/npc-shaonian": "NPC·少年",
    "artifacts/sword": "法宝·剑",
    "artifacts/cauldron": "法宝·鼎炉",
    "artifacts/banner": "法宝·幡旗",
    "artifacts/orb": "法宝·珠戒",
    "artifacts/mirror": "法宝·镜",
    "artifacts/bell": "法宝·铃钟",
    "artifacts/pagoda": "法宝·塔",
    "artifacts/gourd": "法宝·葫芦",
    "artifacts/fan": "法宝·扇",
    "artifacts/seal": "法宝·印玺",
    "arts/metal": "功法·金",
    "arts/wood": "功法·木",
    "arts/water": "功法·水",
    "arts/fire": "功法·火",
    "arts/earth": "功法·土",
    "arts/thunder": "功法·雷",
    "arts/sword": "功法·剑",
    "arts/ice": "功法·冰",
    "maps/map-common": "宝图·凡图",
    "maps/map-fine": "宝图·良图",
    "maps/map-rare": "宝图·珍图",
    "maps/map-ancient": "宝图·古图",
}


def _kv_get(user_id: str) -> Dict[str, Any]:
    from storage.db import WorldStateRepository

    raw = WorldStateRepository.get(ATLAS_KEY_PREFIX + str(user_id)) or {}
    if not isinstance(raw, dict):
        return {"unlocked": {}, "titles": []}
    unlocked = raw.get("unlocked") or {}
    if not isinstance(unlocked, dict):
        unlocked = {}
    titles = raw.get("titles") or []
    if not isinstance(titles, list):
        titles = []
    return {"unlocked": dict(unlocked), "titles": list(titles)}


def _titles_for_count(count: int) -> List[str]:
    return [title for threshold, title in GALLERY_TITLES if count >= threshold]


def highest_title(count: int) -> str:
    titles = _titles_for_count(count)
    return titles[-1] if titles else ""


def get_atlas(user_id: str) -> Dict[str, Any]:
    """读图鉴（脏键不计数；本函数纯读不落盘，清除动作在 unlock 合并时做）。"""
    data = _kv_get(user_id)
    unlocked = {k: v for k, v in data["unlocked"].items() if k in GALLERY_ASSET_KEYS}
    return {
        "unlocked": unlocked,
        "titles": _titles_for_count(len(unlocked)),
    }


def summary(user_id: str, newly: Optional[List[str]] = None) -> Dict[str, Any]:
    """命盘 gallery 块（§10.1）：unlocked 相对键列表 / count / total / title / newly。"""
    atlas = get_atlas(user_id)
    keys = sorted(atlas["unlocked"].keys())
    return {
        "unlocked": keys,
        "count": len(keys),
        "total": len(GALLERY_ASSET_KEYS),
        "title": highest_title(len(keys)),
        "newly": list(newly or []),
    }


def unlock(user_id: str, keys: Iterable[str], now: Optional[float] = None,
           actor_name: str = "") -> List[str]:
    """合并式点亮（唯一写入口）：与存量取并集、只增不减、清除全集外脏键。

    返回本次新点亮的键列表。无变化时不写 KV。里程碑新称号达成时记一条
    chronicle（仅留痕，零数值，§8.4）。
    """
    if not user_id or str(user_id).startswith(("npc_", "ai_npc_")):
        return []
    from storage.db import WorldStateRepository

    t = now if now is not None else time.time()
    data = _kv_get(user_id)
    before = {k: v for k, v in data["unlocked"].items() if k in GALLERY_ASSET_KEYS}
    had_dirty = len(before) != len(data["unlocked"])
    merged = dict(before)
    newly: List[str] = []
    for key in keys or []:
        if key in GALLERY_ASSET_KEYS and key not in merged:
            merged[key] = t
            newly.append(key)
    if not newly and not had_dirty:
        return []
    old_titles = set(_titles_for_count(len(before)))
    new_titles = _titles_for_count(len(merged))
    WorldStateRepository.set(
        ATLAS_KEY_PREFIX + str(user_id),
        {"unlocked": merged, "titles": new_titles},
    )
    gained = [title for title in new_titles if title not in old_titles]
    if gained:
        try:
            from storage.db import ChronicleRepository

            ChronicleRepository.record(
                "GALLERY", actor_name or str(user_id),
                f"图鉴点亮 {len(merged)}/{len(GALLERY_ASSET_KEYS)}，得图鉴称号【{gained[-1]}】（仅展示，无数值）。",
            )
        except Exception:
            pass
    return newly


# ---------------------------------------------------------------------------
# 派生型点亮（§8.2/§8.3）：从角色当前事实推导，不在各业务引擎散埋钩子
# ---------------------------------------------------------------------------
def derive_keys_from_character(char: Any) -> List[str]:
    keys: List[str] = []

    # 本人人物图：已定相后点亮当前及以下全部境界的本性别图
    gender = (getattr(char, "gender", "") or "").strip().lower()
    tier = int(getattr(getattr(char, "realm", None), "tier", 0) or 0)
    if gender in ("male", "female") and tier >= 1:
        for t in range(1, min(6, tier) + 1):
            keys.append(f"portraits/{gender}-{REALM_KEYS[t - 1]}")

    # 法宝图 / 宝图图：行囊实体 + 已穿戴（实体优先，穿戴名走目录解析）
    seen_equip_names = set()
    for item in getattr(char, "items", []) or []:
        kind_val = getattr(getattr(item, "kind", None), "value", getattr(item, "kind", None))
        if kind_val == "equip":
            keys.append(artifact_key_for_item(item))
            seen_equip_names.add(getattr(item, "name", ""))
        elif kind_val == "treasure_map":
            keys.append(map_key_for_tier(getattr(item, "tier", 2)))
    for eq_name in getattr(char, "equipped", []) or []:
        if eq_name and eq_name not in seen_equip_names:
            keys.append(artifact_key_for_equip_name(eq_name))

    # 功法图：已习得 + 自创 + 主修/辅修
    art_names: List[str] = list(getattr(char, "skills", []) or [])
    for art in getattr(char, "custom_arts", []) or []:
        if isinstance(art, dict) and art.get("name"):
            art_names.append(str(art["name"]))
    if getattr(char, "main_art", ""):
        art_names.append(str(char.main_art))
    art_names.extend(str(a) for a in (getattr(char, "sub_arts", None) or []))
    for name in art_names:
        if name:
            keys.append(art_key_for(name, char))

    # 基础五神通：spells_catalog 呈现即点亮其五行键（§8.3）
    try:
        from core.spells import SPELL_CATALOG
        from core.gallery_assets import spell_key_for_element

        for spell in SPELL_CATALOG.values():
            keys.append(spell_key_for_element(spell.get("element")))
    except Exception:
        pass

    return keys


def unlock_from_character(char: Any, now: Optional[float] = None) -> List[str]:
    """命盘组装后的派生合并（§8.2）；钩子语义：失败不影响主流程由调用方兜底。"""
    return unlock(
        str(getattr(char, "user_id", "") or ""),
        derive_keys_from_character(char),
        now=now,
        actor_name=getattr(char, "name", "") or "",
    )


# ---------------------------------------------------------------------------
# 事件型点亮钩子（§8.3）：NPC 原型 / 同场玩家 / 奇遇配图（第二段调用）
# ---------------------------------------------------------------------------
def note_npc_encounter(viewer: Any, npc: Any, now: Optional[float] = None) -> List[str]:
    """与 NPC 交谈开启成功或同场组装时点亮其原型图。"""
    from core.gallery_assets import npc_avatar_key_for_character

    return unlock(
        str(getattr(viewer, "user_id", "") or ""),
        [npc_avatar_key_for_character(npc)],
        now=now,
        actor_name=getattr(viewer, "name", "") or "",
    )


def note_player_encounter(viewer: Any, other: Any, now: Optional[float] = None) -> List[str]:
    """同场遇到已定相玩家时，按其 gender+realm 点亮其人物图（§8.3）。"""
    from core.gallery_assets import player_portrait_key

    key = player_portrait_key(
        getattr(other, "gender", "") or "",
        getattr(getattr(other, "realm", None), "tier", 1),
    )
    if not key:
        return []
    return unlock(
        str(getattr(viewer, "user_id", "") or ""),
        [key],
        now=now,
        actor_name=getattr(viewer, "name", "") or "",
    )


def note_omen_image(user_id: str, asset_key: str, now: Optional[float] = None,
                    actor_name: str = "") -> List[str]:
    """奇遇配图点亮接口（§8.3 事件型）：奇遇本体在第二段，本段只留合并入口；
    仅接受全集内键，AI 剧本配图是否点亮由第二段按 §7.2 裁定后调用。"""
    if asset_key not in GALLERY_ASSET_KEYS:
        return []
    return unlock(user_id, [asset_key], now=now, actor_name=actor_name)


# ---------------------------------------------------------------------------
# /定相（§3.3）与 /图鉴 面板（§8.5，双端同源文本）
# ---------------------------------------------------------------------------
def set_gender(char: Any, arg: str) -> Dict[str, Any]:
    """定相：assert_alive 门禁（§11，不调 assert_idle）；落盘由调用方 save。"""
    from core.character_integrity import CharacterIntegrity, CharacterIntegrityError

    try:
        CharacterIntegrity.assert_alive(char)
    except CharacterIntegrityError as e:
        return {"success": False, "message": str(e)}
    a = (arg or "").strip().lower()
    if a in ("男", "male", "m"):
        char.gender = "male"
        cn = "男相"
    elif a in ("女", "female", "f"):
        char.gender = "female"
        cn = "女相"
    else:
        return {"success": False, "message": "用法：/定相 男|女"}
    from core.gallery_assets import player_portrait_path

    portrait = player_portrait_path(char.gender, char.realm.tier)
    return {
        "success": True,
        "message": f"已定{cn}。命盘人物图随境界而变，当前为【{char.realm.name}】之相（{portrait}）。改相无碍修行，可随时再 /定相。",
    }


def panel_text(char: Any) -> str:
    """图鉴面板文本（/图鉴，CLI 与 server 同源）。读命令无门禁（§8.5）。"""
    user_id = str(getattr(char, "user_id", "") or "")
    atlas = get_atlas(user_id)
    unlocked = atlas["unlocked"]
    count = len(unlocked)
    title = highest_title(count)
    lines = [
        f"【天道图鉴】进度 {count}/{len(GALLERY_ASSET_KEYS)}"
        + (f" · 当前称号：{title}（仅展示）" if title else " · 尚未得图鉴称号（10 张起）"),
    ]
    for group_name, group_keys in GALLERY_GROUPS:
        got = [k for k in group_keys if k in unlocked]
        lines.append(f"\n■ {group_name}（{len(got)}/{len(group_keys)}）")
        for key in group_keys:
            cn = KEY_CN.get(key, key)
            mark = "◆ 已点亮" if key in unlocked else "◇ 未点亮"
            lines.append(f"  {mark} {cn}（{asset_path(key)}）")
    lines.append("\n点亮之法：定相后随境界自明、纳戒藏品自录、同场交谈识人、奇遇逢图留痕。图鉴只记眼界，不予数值。")
    return "\n".join(lines)
