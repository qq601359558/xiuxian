"""
图库资产键与确定性解析（spec: gallery-gameplay §3 / §4；二期扩充见
game-feel-phase2 §9）。

四段式之「资产键 + 解析规则」收口处：139 张定稿资产的相对键以
GALLERY_ASSET_KEYS 为唯一事实源，供 /assets/ 托管常量闸（§9.9）与
图鉴全集（§9.10）共用。全部解析函数为纯函数：同输入同输出、不依赖
AI、不按名字猜性别（NPC 只走 §3.4 显式名单 + 角色规则；二期单人图
只按 ROSTER uid 对号，见 §9.1）。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# §3.1 资产清单（139 键，相对 web/assets/ 的路径，前端引用写作 /assets/<键>）
# 二期总账（game-feel-phase2 §9.9）：玩家立绘 20 + NPC 原型 4 + NPC 单人
# 37 + 法宝 20 + 功法 10 + 藏宝图 8 + 灵宠 4 + 场景 15 + 奇遇 6 + 丹药/
# 材料 15 = 139。
# ---------------------------------------------------------------------------
#: 玩家立绘境界键（§9.2 由 6 扩为 10：补 fanren/heti/dacheng/dujie）
REALM_KEYS = [
    "fanren", "lianqi", "zhuji", "jindan", "yuanying",
    "huashen", "lianxu", "heti", "dacheng", "dujie",
]

#: NPC 单人图 uid 全表（§9.1 定稿 37 人，与 core.npc_roster.ROSTER 的 uid
#: 一一对应；键由 npc_single_key_for_uid 映射生成，禁止手抄键名防漂移，
#: GL-02 以 ROSTER 全量枚举断言三方一致）
NPC_SINGLE_UIDS = (
    "npc_qy_01", "npc_qy_02", "npc_qy_03", "npc_qy_04", "npc_qy_05",
    "npc_qy_06", "npc_qy_07", "npc_qy_08", "npc_qy_09",
    "npc_wj_01", "npc_wj_02", "npc_wj_03", "npc_wj_04", "npc_wj_05",
    "npc_wj_06", "npc_wj_07",
    "npc_jy_01", "npc_jy_02", "npc_jy_03", "npc_jy_04", "npc_jy_05",
    "npc_jy_06", "npc_jy_07",
    "npc_sh_01", "npc_sh_02", "npc_sh_03", "npc_sh_04", "npc_sh_05",
    "npc_sh_06",
    "npc_wd_01", "npc_wd_02", "npc_wd_03", "npc_wd_04", "npc_wd_05",
    "npc_wd_06", "npc_wd_07", "npc_wd_08",
)


def npc_single_key_for_uid(uid: Any) -> str:
    """§9.1：uid → NPC 单人键。slug = uid 去 "npc_" 前缀后 "_" 换 "-"。

    例：npc_qy_01 → portraits/npc-qy-01（uid 原样含下划线会被 /assets/
    正则闸 [a-z0-9-]+ 拦死，故去下划线映射为满足正则的最小变更，F3）。
    空/非法 uid 返回 ""（不配图不报错）。
    """
    u = str(uid or "").strip()
    if not u:
        return ""
    body = u[len("npc_"):] if u.startswith("npc_") else u
    slug = body.replace("_", "-")
    if not slug:
        return ""
    return f"portraits/npc-{slug}"


def npc_uid_for_single_key(key: Any) -> str:
    """§9.1：NPC 单人键 → uid，与 npc_single_key_for_uid 互为逆运算。

    例：portraits/npc-qy-01 → npc_qy_01。非 portraits/npc-* 键返回 ""。
    （原型键 portraits/npc-laodao 等形式上也可逆推，但其结果不是 ROSTER
    uid，调用方须以 NPC_SINGLE_UIDS / ROSTER 为准校验。）
    """
    k = str(key or "").strip()
    prefix = "portraits/npc-"
    if not k.startswith(prefix):
        return ""
    slug = k[len(prefix):]
    if not slug:
        return ""
    return "npc_" + slug.replace("-", "_")


_NPC_SINGLE_KEYS = [npc_single_key_for_uid(u) for u in NPC_SINGLE_UIDS]

_PORTRAIT_KEYS = (
    [f"portraits/male-{r}" for r in REALM_KEYS]
    + [f"portraits/female-{r}" for r in REALM_KEYS]
    + [
        "portraits/npc-laodao",
        "portraits/npc-shanggu",
        "portraits/npc-nvxiu",
        "portraits/npc-shaonian",
    ]
    + _NPC_SINGLE_KEYS
)
#: 法宝器型（§9.5 由 10 补齐至 20）
_ARTIFACT_KINDS = (
    "sword", "cauldron", "banner", "orb", "mirror", "bell", "pagoda",
    "gourd", "fan", "seal",
    "armor", "boots", "staff", "vessel", "blade", "spear", "case",
    "needle", "shuttle", "talisman",
)
_ARTIFACT_KEYS = [f"artifacts/{k}" for k in _ARTIFACT_KINDS]
#: 功法（§9.6 由 8 补至 10：wind 风 / spirit 神魂）
_ART_KINDS = (
    "metal", "wood", "water", "fire", "earth", "thunder", "sword", "ice",
    "wind", "spirit",
)
_ART_KEYS = [f"arts/{k}" for k in _ART_KINDS]
#: 藏宝图（§9.7 由 4 补至 8：celestial 仙档 + 原型 3）
_MAP_KEYS = (
    [f"maps/map-{r}" for r in ("common", "fine", "rare", "ancient", "celestial")]
    + [f"maps/arch-{a}" for a in ("puzzle", "combat", "hazard")]
)

# ---------------------------------------------------------------------------
# §9.3 灵宠图 4 张（物种名 → 显式 slug 表，禁止运行时拼音推导）
# ---------------------------------------------------------------------------
PET_ASSET_SLUGS = {
    "青鳞蟒": "qinglinmang",
    "疾风隼": "jifengxun",
    "玄甲龟": "xuanjiagui",
    "寻宝鼠": "xunbaoshu",
}
_PET_KEYS = [f"pets/pet-{slug}" for slug in PET_ASSET_SLUGS.values()]


def pet_key_for_species(species: Any) -> str:
    """§9.3：灵宠物种 → 灵宠图相对键；物种不在表内返回 ""（不配图）。"""
    slug = PET_ASSET_SLUGS.get(str(species or "").strip())
    return f"pets/pet-{slug}" if slug else ""


# ---------------------------------------------------------------------------
# §9.4 地点场景图 15 张（地点 10 + 秘境/副本 5；映射表为唯一事实源）
# ---------------------------------------------------------------------------
LOCATION_SCENE_KEYS = {
    "青云坊市客栈": "scenes/market-inn",
    "青云宗外门山门": "scenes/qingyun-gate",
    "宗门玄元洞府": "scenes/xuanyuan-cave",
    "落霞山灵泉": "scenes/luoxia-spring",
    "落霞山灵泉(野外)": "scenes/luoxia-spring",
    "黑水沼泽": "scenes/heishui-swamp",
    "万剑仙门峰": "scenes/wanjian-peak",
    "洗剑池洞天": "scenes/xijian-pool",
    "九幽天魔宗坛": "scenes/jiuyou-altar",
    "黑风绝渊": "scenes/heifeng-abyss",
    "黑风绝渊(大凶)": "scenes/heifeng-abyss",
    "万星古岛": "scenes/wanxing-isle",
}
REALM_SCENE_KEYS = {
    "落霞古洞": "scenes/realm-luoxia-cave",
    "剑冢残碑": "scenes/realm-sword-tomb",
    "万星遗迹残址": "scenes/realm-wanxing-ruins",
    "幽冥鬼市": "scenes/realm-ghost-market",
    "锁妖古窟": "scenes/dungeon-entrance",
}
_SCENE_KEYS = sorted(set(LOCATION_SCENE_KEYS.values()) | set(REALM_SCENE_KEYS.values()))


def scene_key_for_location(location: Any) -> str:
    """§9.4：地点名 → 场景图相对键；无映射返回 ""（前端不渲染图位）。"""
    return LOCATION_SCENE_KEYS.get(str(location or "").strip(), "")


def scene_key_for_realm(realm_name: Any) -> str:
    """§9.4：秘境/副本名 → 场景图相对键；无映射返回 ""。

    锁妖古窟各层名（「锁妖古窟 · 幽暗外穴」等）以入口图为代表，按前缀命中。
    """
    name = str(realm_name or "").strip()
    if name in REALM_SCENE_KEYS:
        return REALM_SCENE_KEYS[name]
    if name.startswith("锁妖古窟"):
        return REALM_SCENE_KEYS["锁妖古窟"]
    return ""


def scene_path_for_location(location: Any) -> str:
    """地点场景图完整路径（/assets/...）；无映射为空串（§8.1 下发口径）。"""
    key = scene_key_for_location(location)
    return asset_path(key) if key else ""


def scene_path_for_realm(realm_name: Any) -> str:
    """秘境场景图完整路径；无映射为空串（§9.4 scene_image 下发口径）。"""
    key = scene_key_for_realm(realm_name)
    return asset_path(key) if key else ""


# ---------------------------------------------------------------------------
# §9.8 补足包：奇遇专图 6（slug = script_id 的 "_" 换 "-"）
# ---------------------------------------------------------------------------
OMEN_SCRIPT_ASSET_KEYS = {
    "black_market": "omen/black-market",
    "orphan_trust": "omen/orphan-trust",
    "spring_dispute": "omen/spring-dispute",
    "stele": "omen/stele",
    "escort_deal": "omen/escort-deal",
    "inn_whisper": "omen/inn-whisper",
}
_OMEN_KEYS = list(OMEN_SCRIPT_ASSET_KEYS.values())


def omen_key_for_script(script_id: Any) -> str:
    """§9.8：预置奇遇剧本 id → 专图相对键；AI 剧本/未知 id 返回 ""。

    注：core/omen_scene.OMEN_SCRIPT_IMAGES 仍指借代键，其六值改指本表
    专图键属奇遇模块的集成项（本模块只提供唯一事实源，不越界改彼处）。
    """
    return OMEN_SCRIPT_ASSET_KEYS.get(str(script_id or "").strip(), "")


# ---------------------------------------------------------------------------
# §9.8 补足包：丹药分类图 8 + 材料分类图 7（显式 slug 表）
# ---------------------------------------------------------------------------
PILL_ASSET_SLUGS = {
    "breakthrough": "pill-breakthrough",
    "cultivation": "pill-cultivation",
    "recovery": "pill-recovery",
    "lifespan": "pill-lifespan",
    "soul_purity": "pill-soul",
    "detox": "pill-detox",
    "root_purify": "pill-root",
    "combat_buff": "pill-combat",
}
MATERIAL_ASSET_SLUGS = {
    "herb": "mat-herb",
    "ore": "mat-ore",
    "metal": "mat-metal",
    "beast": "mat-beast",
    "liquid": "mat-liquid",
    "wood": "mat-wood",
    "aura": "mat-aura",
}
_GOODS_KEYS = (
    [f"goods/{s}" for s in PILL_ASSET_SLUGS.values()]
    + [f"goods/{s}" for s in MATERIAL_ASSET_SLUGS.values()]
)


def pill_key_for_type(pill_type: Any) -> str:
    """§9.8：pill_type → 丹药分类图相对键；未知类型返回 ""（不配图）。"""
    slug = PILL_ASSET_SLUGS.get(str(pill_type or "").strip())
    return f"goods/{slug}" if slug else ""


def material_key_for_category(category: Any) -> str:
    """§9.8：材料 category → 材料分类图相对键；未知分类返回 ""。"""
    slug = MATERIAL_ASSET_SLUGS.get(str(category or "").strip())
    return f"goods/{slug}" if slug else ""


def _catalog_entry_for_name(name: str) -> dict:
    try:
        from config import ITEM_CATALOG

        cfg = ITEM_CATALOG.get((name or "").strip()) or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def goods_key_for_name(name: Any) -> str:
    """§9.8：物品名 → goods 分类图键（丹药按 pill_type、材料按 category）。

    经 ITEM_CATALOG 按名查（O(1)）；查不到或非丹药/材料返回 ""
    （生成丹药无 pill_type 即属查不到，不配图、不报错）。
    """
    cfg = _catalog_entry_for_name(str(name or ""))
    if not cfg:
        return ""
    if cfg.get("pill_type") or cfg.get("kind") == "pill" or cfg.get("category") == "pill":
        return pill_key_for_type(cfg.get("pill_type"))
    return material_key_for_category(cfg.get("category"))


#: 139 项定稿资产键集合（托管白名单 + 图鉴全集，§9.9 三处一致以此为准）
GALLERY_ASSET_KEYS = frozenset(
    _PORTRAIT_KEYS + _ARTIFACT_KEYS + _ART_KEYS + _MAP_KEYS
    + _PET_KEYS + _SCENE_KEYS + _OMEN_KEYS + _GOODS_KEYS
)

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
    须带 .webp 后缀才过 §9.9 托管正则闸（/assets/.../<key>.webp）。
    """
    return f"/assets/{relative_key}.webp"


def realm_key_for_tier(tier: Any) -> str:
    """§9.2 新口径：tier 0→fanren、1–9 逐档直取、>9 钳 dujie。

    不再借图：tier 0 不再按 lianqi、tier ≥7 不再封顶借 lianxu。
    非法值回退沿现状（t=1 → lianqi）；负值钳到 fanren。
    """
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 1
    t = max(0, min(9, t))
    return REALM_KEYS[t]


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
# §9.1 变更：ROSTER 命中者优先单人键，原型解析保留为动态 NPC 兜底。
# ---------------------------------------------------------------------------
def _roster_names() -> frozenset:
    try:
        from core.npc_roster import ROSTER

        return frozenset(str(r.get("name") or "") for r in ROSTER)
    except Exception:
        return frozenset()


def _roster_row_for_name(name: str) -> Optional[dict]:
    try:
        from core.npc_roster import ROSTER

        for row in ROSTER:
            if row.get("name") == name:
                return row
    except Exception:
        pass
    return None


def npc_single_key_for_name(name: Any) -> str:
    """§9.1：人名命中 ROSTER → 其 uid 的单人键；未命中返回 ""。"""
    row = _roster_row_for_name((name or "").strip())
    if not row:
        return ""
    return npc_single_key_for_uid(row.get("uid"))


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
    或 tier ≥4 → laodao；④ 其余 → shaonian。二期起本函数只作兜底
    （§9.1），规则一字未改。
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
    """对 Character（NPC）解析头像相对键。

    §9.1 优先级（写死）：角色名命中 ROSTER → 返回其 uid 的单人键；
    未命中（动态/无名 NPC）→ 回退原型解析（resolve_npc_archetype，
    以花名册 rank 为准——角色行 sect_rank 可能被编制补写覆盖，
    花名册是编制事实源）。
    """
    name = getattr(char, "name", "") or ""
    single = npc_single_key_for_name(name)
    if single:
        return single
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
# §9.5 修正：专器关键字组先行；subtype 其次；剑组关键字（剑/刃）退为
# subtype 之后的兜底组——使目录内「血刃/惊神刃」以 subtype 战刃先行
# 命中 blade（§9.5 定稿注），而生成器物无 subtype 时仍按名归 sword。
# ---------------------------------------------------------------------------
_NAME_KEYWORD_RULES = [
    (("镜",), "mirror"),
    (("鼎", "炉"), "cauldron"),
    (("葫芦",), "gourd"),
    (("塔",), "pagoda"),
    (("铃", "钟"), "bell"),
    (("幡", "旗"), "banner"),
    (("印", "玺"), "seal"),
    (("珠", "戒"), "orb"),
    (("扇",), "fan"),
    (("杖",), "staff"),
    (("刀",), "blade"),
    (("梭",), "shuttle"),
    (("舟", "舰", "鸢"), "vessel"),
    (("匣",), "case"),
    (("符",), "talisman"),
    (("戈", "枪"), "spear"),
    (("刺",), "needle"),
]

#: 剑组关键字兜底（§9.5：刃留 sword 组尾作生成器物兜底；枪/刺已改归
#: spear/needle 专器组，不在此列）
_NAME_SWORD_FALLBACK_RULES = [
    (("剑", "刃"), "sword"),
]

_SUBTYPE_RULES = {
    "飞剑": "sword", "法剑": "sword", "重剑": "sword",
    "战刃": "blade",
    "灵刺": "needle", "长戈": "spear", "长枪": "spear", "剑匣": "case",
    "法杖": "staff",
    "飞舟": "vessel", "巨舰": "vessel", "木鸢": "vessel",
    "破空梭": "shuttle",
    "重铠": "armor", "道袍": "armor", "软甲": "armor", "护腕": "armor",
    "灵靴": "boots", "战靴": "boots", "草履": "boots", "破虚神履": "boots",
    "灵幡": "banner",
    "宝珠": "orb", "骨戒": "orb",
    "宝铃": "bell",
    "灵佩": "seal", "护身符": "talisman",
}

_SLOT_FALLBACK = {
    "weapon": "sword",
    "trinket": "orb",
    "flying_treasure": "pagoda",
    "armor": "armor",
    "boots": "boots",
}


def artifact_key_for(name: str, subtype: Optional[str] = None, slot: Optional[str] = None) -> str:
    """器物 → 法宝图相对键（artifacts/<kind>），任意器物恰得一键。

    顺序（§9.5）：专器名字关键字 → subtype → 剑组名字关键字兜底 →
    槽位兜底 → sword。cauldron/gourd/mirror/pagoda 为关键字保留键：
    目录命中可为 0，只由生成器物等名字命中（F4 口径）。
    """
    nm = name or ""
    for words, kind in _NAME_KEYWORD_RULES:
        if any(w in nm for w in words):
            return f"artifacts/{kind}"
    if subtype and subtype in _SUBTYPE_RULES:
        return f"artifacts/{_SUBTYPE_RULES[subtype]}"
    for words, kind in _NAME_SWORD_FALLBACK_RULES:
        if any(w in nm for w in words):
            return f"artifacts/{kind}"
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
# §9.6：风关键字置于剑组之前、神魂关键字置于金组之前；风灵根改指 wind。
# §9.7：宝图 tier5 独立 celestial 键 + archetype 原型键与回退链。
# ---------------------------------------------------------------------------
_ART_NAME_RULES = [
    (("雷", "霆"), "thunder"),
    (("冰", "寒", "霜"), "ice"),
    (("风", "岚"), "wind"),
    (("魂", "神念"), "spirit"),
    (("剑",), "sword"),
    (("金", "庚"), "metal"),
    (("木", "青", "长生"), "wood"),
    (("水", "泉"), "water"),
    (("火", "炎", "焚"), "fire"),
    (("土", "岳", "罡"), "earth"),
]

_ELEMENT_TO_ART = {
    "金": "metal", "木": "wood", "水": "water", "火": "fire", "土": "earth",
    "雷": "thunder", "冰": "ice", "风": "wind",
    # spells_catalog 的 element 字段为英文键，直取同名
    "metal": "metal", "wood": "wood", "water": "water", "fire": "fire",
    "earth": "earth", "thunder": "thunder", "ice": "ice", "wind": "wind",
}


def art_key_for_element(element: Any) -> Optional[str]:
    """灵根元素（中文 Element 值或英文 element 键）→ 功法图键名（无前缀）。"""
    if element is None:
        return None
    v = getattr(element, "value", element)
    return _ELEMENT_TO_ART.get(str(v))


def art_key_for(art_name: str, char: Any = None) -> str:
    """功法名 → 功法图相对键（arts/<school>）。

    顺序（§3.7/§9.6）：名字关键字 → 修士灵根首元素兜底 → earth。
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


_MAP_RARITY_BY_TIER = {1: "map-common", 2: "map-fine", 3: "map-rare", 4: "map-ancient"}

#: §9.7 原型键：TreasureArchetype 值 → 相对键后缀（枚举源
#: core/treasure_system.TreasureArchetype 三值定稿）
_MAP_ARCHETYPE_KEYS = {
    "element_puzzle": "arch-puzzle",
    "combat": "arch-combat",
    "ruin_hazard": "arch-hazard",
}


def _archetype_value(archetype: Any) -> str:
    """archetype 归一：接受枚举值/成员名/带 .value 的对象，输出小写值串。"""
    if archetype is None:
        return ""
    v = getattr(archetype, "value", archetype)
    s = str(v).strip()
    if s in _MAP_ARCHETYPE_KEYS:
        return s
    low = s.lower()
    for key in _MAP_ARCHETYPE_KEYS:
        if low == key or low.endswith("." + key) or low == key.upper().lower():
            return key
    # 成员名形态（ELEMENT_PUZZLE 等）
    name_map = {"element_puzzle": "element_puzzle", "combat": "combat", "ruin_hazard": "ruin_hazard"}
    return name_map.get(low, "")


def map_archetype_key_for(archetype: Any) -> str:
    """§9.7：archetype → 原型相对键；未知 archetype 返回 ""。"""
    v = _archetype_value(archetype)
    if not v:
        return ""
    return f"maps/{_MAP_ARCHETYPE_KEYS[v]}"


def map_key_for_tier(tier: Any) -> str:
    """宝图稀有度相对键：1 common / 2 fine / 3 rare / 4 ancient / ≥5 celestial（§9.7）。"""
    try:
        t = int(tier)
    except (TypeError, ValueError):
        t = 2
    if t >= 5:
        return "maps/map-celestial"
    return f"maps/{_MAP_RARITY_BY_TIER.get(t, 'map-ancient' if t >= 4 else 'map-fine')}"


def map_key_for(tier: Any, archetype: Any = None) -> str:
    """§9.7：宝图呈现解析。archetype 已知 → 原型键；回退链写死：
    原型键 ∉ 全集 → 稀有度键 → maps/map-common。

    archetype=None 时即 map_key_for_tier 的兼容壳（行囊/命盘恒走此路）。
    """
    arch = map_archetype_key_for(archetype)
    if arch:
        if arch in GALLERY_ASSET_KEYS:
            return arch
        rarity = map_key_for_tier(tier)
        return rarity if rarity in GALLERY_ASSET_KEYS else "maps/map-common"
    return map_key_for_tier(tier)


def treasure_map_archetype_of(item: Any) -> str:
    """宝图实体 → archetype 值串：custom_metadata.archetype 优先，
    其次 archetype 属性；无则 ""。"""
    meta = getattr(item, "custom_metadata", None) or {}
    if isinstance(meta, dict) and meta.get("archetype"):
        return _archetype_value(meta.get("archetype"))
    for attr in ("archetype", "treasure_archetype"):
        v = getattr(item, attr, None)
        if v:
            return _archetype_value(v)
    return ""


def item_image_key(item: Any) -> str:
    """命盘 items/equipped 的 img 相对键分发（§10.1 + §9.7/§9.8）：
    equip→§9.5、treasure_map→稀有度键（恒走，§9.7）、pill→丹药分类图
    （按目录 pill_type，查不到返回 ""）、material/herb→材料分类图
    （按名查目录 category）、其余 kind→空串（前端不渲染图位）。"""
    kind = getattr(item, "kind", None)
    kind_val = getattr(kind, "value", kind)
    if kind_val == "equip":
        return artifact_key_for_item(item)
    if kind_val == "treasure_map":
        return map_key_for_tier(getattr(item, "tier", 2))
    if kind_val == "pill":
        pill_type = getattr(item, "pill_type", None)
        meta = getattr(item, "custom_metadata", None) or {}
        if not pill_type and isinstance(meta, dict):
            pill_type = meta.get("pill_type")
        if pill_type:
            return pill_key_for_type(pill_type)
        return goods_key_for_name(getattr(item, "name", ""))
    if kind_val in ("material", "herb"):
        return goods_key_for_name(getattr(item, "name", ""))
    return ""


def item_image_path(item: Any) -> str:
    key = item_image_key(item)
    return asset_path(key) if key else ""
