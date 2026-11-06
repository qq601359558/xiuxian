"""
图库资产键与确定性解析（spec: gallery-gameplay §3 / §4）。

四段式之「资产键 + 解析规则」收口处：38 张定稿资产的相对键以
GALLERY_ASSET_KEYS 为唯一事实源，供 /assets/ 托管常量闸（§4）与
图鉴全集（§8）共用。全部解析函数为纯函数：同输入同输出、不依赖
AI、不按名字猜性别（NPC 只走 §3.4 显式名单 + 角色规则）。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# §3.1 资产清单（38 键，相对 web/assets/ 的路径，前端引用写作 /assets/<键>）
# ---------------------------------------------------------------------------
REALM_KEYS = ["lianqi", "zhuji", "jindan", "yuanying", "huashen", "lianxu"]

_PORTRAIT_KEYS = (
    [f"portraits/male-{r}" for r in REALM_KEYS]
    + [f"portraits/female-{r}" for r in REALM_KEYS]
    + [
        "portraits/npc-laodao",
        "portraits/npc-shanggu",
        "portraits/npc-nvxiu",
        "portraits/npc-shaonian",
    ]
)
_ARTIFACT_KEYS = [
    f"artifacts/{k}"
    for k in ("sword", "cauldron", "banner", "orb", "mirror", "bell", "pagoda", "gourd", "fan", "seal")
]
_ART_KEYS = [
    f"arts/{k}"
    for k in ("metal", "wood", "water", "fire", "earth", "thunder", "sword", "ice")
]
_MAP_KEYS = [f"maps/map-{r}" for r in ("common", "fine", "rare", "ancient")]

#: 38 项定稿资产键集合（托管白名单 + 图鉴全集，§3.1 三处一致以此为准）
GALLERY_ASSET_KEYS = frozenset(_PORTRAIT_KEYS + _ARTIFACT_KEYS + _ART_KEYS + _MAP_KEYS)

#: 未定相玩家的人物图占位（§3.3：不猜性别，用既有修行图）
PLACEHOLDER_PORTRAIT = "/images/cultivator_meditating.png"

#: §3.4-1 女修显式名单（ROSTER 中身份可考为女修者，仅此 7 名，禁按名字扩充）
NPC_FEMALE_NAMES = frozenset({"苏婉清", "青萝", "骨姬", "毒娘子", "柳三娘", "海娘子", "小环"})

#: §3.4-2 商贾宗门名
NPC_MERCHANT_SECT = "四海散修商会"

#: §3.4-3 老道 rank 关键字
NPC_ELDER_RANK_WORDS = ("掌门", "宗主", "太上", "长老", "护法")


def asset_path(relative_key: str) -> str:
    """相对资产键 → 前端可用的完整路径（拼装只此一处，§3.3/§10.5）。

    相对键不带扩展名（与 GALLERY_ASSET_KEYS / 图鉴键同口径），完整路径
    须带 .webp 后缀才过 §4 托管正则闸（/assets/.../<key>.webp）。
    """
    return f"/assets/{relative_key}.webp"


def realm_key_for_tier(tier: Any) -> str:
    """§3.2：tier 0 按 lianqi、tier ≥7 封顶 lianxu。"""
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 1
    t = max(1, min(6, t))
    return REALM_KEYS[t - 1]


# ---------------------------------------------------------------------------
# §3.3 玩家人物图
# ---------------------------------------------------------------------------
def player_portrait_key(gender: str, tier: Any) -> Optional[str]:
    """已定相 → portraits/{male|female}-{realm}；未定相返回 None（占位）。"""
    g = (gender or "").strip().lower()
    if g not in ("male", "female"):
        return None
    return f"portraits/{g}-{realm_key_for_tier(tier)}"


def player_portrait_path(gender: str, tier: Any) -> str:
    """命盘 portrait 键的完整路径：未定相为既有占位图路径。"""
    key = player_portrait_key(gender, tier)
    return asset_path(key) if key else PLACEHOLDER_PORTRAIT


# ---------------------------------------------------------------------------
# §3.4 NPC 头像（显式名单 + 角色规则，顺序即优先级，命中即停）
# ---------------------------------------------------------------------------
def _roster_names() -> frozenset:
    try:
        from core.npc_roster import ROSTER

        return frozenset(str(r.get("name") or "") for r in ROSTER)
    except Exception:
        return frozenset()


def resolve_npc_archetype(
    name: str,
    sect: Optional[str] = None,
    rank: str = "",
    tier: Any = 1,
    *,
    in_roster: Optional[bool] = None,
) -> str:
    """返回 NPC 原型键（npc-laodao / npc-shanggu / npc-nvxiu / npc-shaonian）。

    规则（§3.4）：① ROSTER 内女修名单 → nvxiu（动态 NPC 永不进 nvxiu）；
    ② 宗门为四海散修商会 → shanggu；③ rank 含掌门/宗主/太上/长老/护法
    或 tier ≥4 → laodao；④ 其余 → shaonian。
    """
    nm = (name or "").strip()
    if in_roster is None:
        in_roster = nm in _roster_names()
    if in_roster and nm in NPC_FEMALE_NAMES:
        return "npc-nvxiu"
    if (sect or "") == NPC_MERCHANT_SECT:
        return "npc-shanggu"
    rk = rank or ""
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 1
    if any(w in rk for w in NPC_ELDER_RANK_WORDS) or t >= 4:
        return "npc-laodao"
    return "npc-shaonian"


def npc_avatar_key_for_character(char: Any) -> str:
    """对 Character（NPC）解析头像相对键。ROSTER 角色以花名册 rank 为准
    （角色行 sect_rank 可能被编制补写覆盖，花名册是编制事实源）。"""
    name = getattr(char, "name", "") or ""
    rank = getattr(char, "sect_rank", "") or ""
    in_roster = False
    try:
        from core.npc_roster import ROSTER

        for row in ROSTER:
            if row.get("name") == name:
                in_roster = True
                rank = row.get("rank") or rank
                break
    except Exception:
        pass
    archetype = resolve_npc_archetype(
        name,
        sect=getattr(char, "sect", None),
        rank=rank,
        tier=getattr(getattr(char, "realm", None), "tier", 1),
        in_roster=in_roster,
    )
    return f"portraits/{archetype}"


def npc_avatar_path_for_character(char: Any) -> str:
    return asset_path(npc_avatar_key_for_character(char))


def roster_archetype_table() -> dict:
    """ROSTER 全员原型解析结果 {name: archetype}（G-4 枚举/报告用）。"""
    from core.npc_roster import ROSTER

    out = {}
    for row in ROSTER:
        out[row["name"]] = resolve_npc_archetype(
            row["name"],
            sect=row.get("sect"),
            rank=row.get("rank") or "",
            tier=row.get("tier", 1),
            in_roster=True,
        )
    return out


# ---------------------------------------------------------------------------
# §3.5 法宝图（关键字 → subtype → 槽位兜底，三级确定性规则）
# ---------------------------------------------------------------------------
_NAME_KEYWORD_RULES = [
    (("镜",), "mirror"),
    (("鼎", "炉"), "cauldron"),
    (("葫芦",), "gourd"),
    (("扇",), "fan"),
    (("塔",), "pagoda"),
    (("铃", "钟"), "bell"),
    (("幡", "旗"), "banner"),
    (("印", "玺"), "seal"),
    (("珠", "戒"), "orb"),
    (("剑", "刃", "戈", "枪", "刺", "匣", "刀"), "sword"),
]

_SUBTYPE_RULES = {
    "飞剑": "sword", "法剑": "sword", "重剑": "sword", "战刃": "sword",
    "灵刺": "sword", "长戈": "sword", "长枪": "sword", "剑匣": "sword",
    "法杖": "orb",
    "灵幡": "banner",
    "宝珠": "orb", "骨戒": "orb",
    "宝铃": "bell",
    "灵佩": "seal", "护身符": "seal",
}

_SLOT_FALLBACK = {
    "weapon": "sword",
    "trinket": "orb",
    "flying_treasure": "pagoda",
    "armor": "mirror",
    "boots": "fan",
}


def artifact_key_for(name: str, subtype: Optional[str] = None, slot: Optional[str] = None) -> str:
    """器物 → 法宝图相对键（artifacts/<kind>），任意器物恰得一键。"""
    nm = name or ""
    for words, kind in _NAME_KEYWORD_RULES:
        if any(w in nm for w in words):
            return f"artifacts/{kind}"
    if subtype and subtype in _SUBTYPE_RULES:
        return f"artifacts/{_SUBTYPE_RULES[subtype]}"
    if slot and slot in _SLOT_FALLBACK:
        return f"artifacts/{_SLOT_FALLBACK[slot]}"
    return "artifacts/sword"


def artifact_key_for_item(item: Any) -> str:
    """ItemEntity → 法宝图键：目录 subtype 按器物名查 EQUIPMENT_CATALOG。"""
    name = getattr(item, "name", "") or ""
    subtype = None
    try:
        from core.catalogs import get_equipment

        cfg = get_equipment(name) or {}
        subtype = cfg.get("subtype")
        slot = getattr(item, "slot", None) or cfg.get("slot")
    except Exception:
        slot = getattr(item, "slot", None)
    return artifact_key_for(name, subtype=subtype, slot=slot)


def artifact_key_for_equip_name(name: str) -> str:
    """已穿戴器物名（可能无实体）→ 法宝图键，走目录 subtype/槽位。"""
    subtype = None
    slot = None
    try:
        from core.catalogs import get_equipment

        cfg = get_equipment(name) or {}
        subtype = cfg.get("subtype")
        slot = cfg.get("slot")
    except Exception:
        pass
    return artifact_key_for(name, subtype=subtype, slot=slot)


# ---------------------------------------------------------------------------
# §3.7 功法图（名字关键字 → 灵根兜底）与宝图图（tier 直取）
# ---------------------------------------------------------------------------
_ART_NAME_RULES = [
    (("雷", "霆"), "thunder"),
    (("冰", "寒", "霜"), "ice"),
    (("剑",), "sword"),
    (("金", "庚"), "metal"),
    (("木", "青", "长生"), "wood"),
    (("水", "泉"), "water"),
    (("火", "炎", "焚"), "fire"),
    (("土", "岳", "罡"), "earth"),
]

_ELEMENT_TO_ART = {
    "金": "metal", "木": "wood", "水": "water", "火": "fire", "土": "earth",
    "雷": "thunder", "冰": "ice", "风": "sword",
    # spells_catalog 的 element 字段为英文键，直取同名
    "metal": "metal", "wood": "wood", "water": "water", "fire": "fire",
    "earth": "earth", "thunder": "thunder", "ice": "ice", "wind": "sword",
}


def art_key_for_element(element: Any) -> Optional[str]:
    """灵根元素（中文 Element 值或英文 element 键）→ 功法图键名（无前缀）。"""
    if element is None:
        return None
    v = getattr(element, "value", element)
    return _ELEMENT_TO_ART.get(str(v))


def art_key_for(art_name: str, char: Any = None) -> str:
    """功法名 → 功法图相对键（arts/<school>）。

    顺序（§3.7）：名字关键字 → 修士灵根首元素兜底 → earth。
    char 可为 None（无灵根信息时走最终兜底）。
    """
    nm = art_name or ""
    for words, kind in _ART_NAME_RULES:
        if any(w in nm for w in words):
            return f"arts/{kind}"
    if char is not None:
        root = getattr(char, "spiritual_root", None)
        elements: Iterable = getattr(root, "elements", None) or []
        for el in elements:
            kind = art_key_for_element(el)
            if kind:
                return f"arts/{kind}"
            break  # 只认首元素
    return "arts/earth"


def spell_key_for_element(element: Any) -> str:
    """基础神通按其 element 字段直取（§3.7 注）；未知元素兜底 earth。"""
    kind = art_key_for_element(element)
    return f"arts/{kind}" if kind else "arts/earth"


_MAP_RARITY_BY_TIER = {1: "map-common", 2: "map-fine", 3: "map-rare"}


def map_key_for_tier(tier: Any) -> str:
    """宝图图相对键：1→common、2→fine、3→rare、≥4→ancient（§3.7）。"""
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 2
    return f"maps/{_MAP_RARITY_BY_TIER.get(t, 'map-ancient' if t >= 4 else 'map-fine')}"


def item_image_key(item: Any) -> str:
    """命盘 items/equipped 的 img 相对键分发（§10.1）：equip→§3.5、
    treasure_map→§3.7、其余 kind→空串（前端不渲染图位）。"""
    kind = getattr(item, "kind", None)
    kind_val = getattr(kind, "value", kind)
    if kind_val == "equip":
        return artifact_key_for_item(item)
    if kind_val == "treasure_map":
        return map_key_for_tier(getattr(item, "tier", 2))
    return ""


def item_image_path(item: Any) -> str:
    key = item_image_key(item)
    return asset_path(key) if key else ""
