"""图库扩充二期（spec: game-feel-phase2 §9，验收 GL-01~GL-14 代码侧）。

分工口径：
- 解析/映射/分组类纯函数测试必须全绿（GL-02 映射半、GL-03~GL-11 主体）。
- 依赖图片文件存在的断言（GL-01 三方一致、GL-02 文件半、GL-12 托管、
  GL-13 单张大小）已按定稿写死：资产岗图片未到位前如实失败，
  失败清单即缺图清单，不削弱断言、不造假占位。
- world.py / omen_scene / treasure_system 侧的下发与调用接线属集成项，
  以 xfail(strict=False) 契约测试钉住，集成落地后自动转 XPASS 提示。
"""
import http.client
import os
import sys
import threading
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from core.clock import WorldClock
from core import gallery
from core.gallery_assets import GALLERY_ASSET_KEYS
from storage.db import init_db, WorldStateRepository

init_db()

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "web" / "assets"


def _tag():
    return uuid.uuid4().hex[:8]


def _player():
    return WorldClock.create_new_character(f"gf2_{_tag()}", f"鉴客{_tag()}")


def _cleanup(user_id):
    WorldStateRepository.delete(gallery.ATLAS_KEY_PREFIX + str(user_id))


# ---------------------------------------------------------------------------
# GL-01 三方一致（待资产：磁盘文件未到位前 disk 半如实失败）
# ---------------------------------------------------------------------------
def test_gl01_total_139_and_per_category_counts():
    from collections import Counter

    assert len(GALLERY_ASSET_KEYS) == 139
    counts = Counter(k.split("/")[0] for k in GALLERY_ASSET_KEYS)
    assert counts == {
        "portraits": 61, "artifacts": 20, "arts": 10, "maps": 8,
        "pets": 4, "scenes": 15, "omen": 6, "goods": 15,
    }
    portraits = {k for k in GALLERY_ASSET_KEYS if k.startswith("portraits/")}
    assert sum(1 for k in portraits if k.startswith(("portraits/male-", "portraits/female-"))) == 20
    assert sum(1 for k in portraits if k in {
        "portraits/npc-laodao", "portraits/npc-shanggu",
        "portraits/npc-nvxiu", "portraits/npc-shaonian"}) == 4


def test_gl01_disk_matches_keys_both_ways():
    """【待资产】资产岗 101 张新图未到位：本断言失败清单即缺图清单。"""
    disk = {
        str(p.relative_to(ASSETS_DIR))[:-len(".webp")]
        for p in ASSETS_DIR.rglob("*.webp")
    }
    assert disk == set(GALLERY_ASSET_KEYS), (
        f"仅磁盘有: {sorted(disk - set(GALLERY_ASSET_KEYS))}；"
        f"仅常量有(缺图): {sorted(set(GALLERY_ASSET_KEYS) - disk)}"
    )


# ---------------------------------------------------------------------------
# GL-02 NPC 对号（映射半纯函数全绿；文件半待资产）
# ---------------------------------------------------------------------------
def test_gl02_uid_key_roundtrip_all_37():
    from core.gallery_assets import (
        NPC_SINGLE_UIDS, npc_single_key_for_uid, npc_uid_for_single_key)
    from core.npc_roster import ROSTER

    assert len(NPC_SINGLE_UIDS) == 37
    assert {r["uid"] for r in ROSTER} == set(NPC_SINGLE_UIDS)
    keys = set()
    for row in ROSTER:
        key = npc_single_key_for_uid(row["uid"])
        assert key in GALLERY_ASSET_KEYS, row["uid"]
        assert npc_uid_for_single_key(key) == row["uid"], row["uid"]
        keys.add(key)
    assert len(keys) == 37
    # 定稿样例（§9.1 表）
    assert npc_single_key_for_uid("npc_qy_01") == "portraits/npc-qy-01"
    assert npc_single_key_for_uid("npc_sh_01") == "portraits/npc-sh-01"
    assert npc_single_key_for_uid("npc_wd_08") == "portraits/npc-wd-08"
    assert npc_single_key_for_uid("") == ""
    assert npc_uid_for_single_key("arts/fire") == ""


def test_gl02_each_npc_file_exists():
    """【待资产】37 张单人图文件由资产岗生产，未到位前如实失败。"""
    from core.gallery_assets import NPC_SINGLE_UIDS, npc_single_key_for_uid

    missing = [npc_single_key_for_uid(u) for u in NPC_SINGLE_UIDS
               if not (ASSETS_DIR / f"{npc_single_key_for_uid(u)}.webp").is_file()]
    assert missing == [], f"缺单人图文件: {missing}"


def test_gl02_dynamic_npc_falls_back_to_archetype():
    from core.gallery_assets import npc_avatar_key_for_character

    dyn = WorldClock.create_new_character("npc_dyn_x", "无名散修")
    dyn.sect = "四海散修商会"
    assert npc_avatar_key_for_character(dyn) == "portraits/npc-shanggu"
    # §9.1 写死口径为「角色名命中 ROSTER」：同名在册者返回单人键
    dyn2 = WorldClock.create_new_character("npc_dyn_y", "苏婉清")
    assert npc_avatar_key_for_character(dyn2) == "portraits/npc-qy-06"
    # ROSTER 外名字一律回退原型四键（动态 NPC 兜底），且不进单人键
    dyn3 = WorldClock.create_new_character("npc_dyn_z", "路人甲")
    assert npc_avatar_key_for_character(dyn3) in {
        "portraits/npc-laodao", "portraits/npc-shanggu",
        "portraits/npc-nvxiu", "portraits/npc-shaonian"}


# ---------------------------------------------------------------------------
# GL-03 解析优先级：ROSTER 三原型类各一 → 单人键；相遇点亮单人键
# ---------------------------------------------------------------------------
def test_gl03_roster_npcs_resolve_to_single_keys():
    from core.gallery_assets import npc_avatar_key_for_character

    cases = {"玄清子": "portraits/npc-qy-01",   # 老道原型类
             "金满堂": "portraits/npc-sh-01",   # 商贾原型类
             "苏婉清": "portraits/npc-qy-06",   # 女修原型类
             "赵小满": "portraits/npc-qy-08"}   # 少年原型类
    for name, expected in cases.items():
        npc = WorldClock.create_new_character(f"npc_gl03_{_tag()}", name)
        assert npc_avatar_key_for_character(npc) == expected, name


def test_gl03_encounter_unlocks_single_not_archetype():
    viewer = _player()
    try:
        npc = WorldClock.create_new_character("npc_gl03_m", "金满堂")
        newly = gallery.note_npc_encounter(viewer, npc)
        assert newly == ["portraits/npc-sh-01"]
        assert "portraits/npc-shanggu" not in gallery.get_atlas(viewer.user_id)["unlocked"]
    finally:
        _cleanup(viewer.user_id)


# ---------------------------------------------------------------------------
# GL-04 玩家立绘 20 组合矩阵 + 仪式 asset_key
# ---------------------------------------------------------------------------
def test_gl04_portrait_matrix_20_and_clamps():
    from core.gallery_assets import (
        PLACEHOLDER_PORTRAIT, player_portrait_key, player_portrait_path,
        realm_key_for_tier)

    expected = ["fanren", "lianqi", "zhuji", "jindan", "yuanying",
                "huashen", "lianxu", "heti", "dacheng", "dujie"]
    for gender in ("male", "female"):
        for tier, rk in enumerate(expected):
            assert realm_key_for_tier(tier) == rk
            assert player_portrait_key(gender, tier) == f"portraits/{gender}-{rk}"
            assert player_portrait_path(gender, tier) == f"/assets/portraits/{gender}-{rk}.webp"
    assert realm_key_for_tier(10) == "dujie" and realm_key_for_tier(99) == "dujie"
    assert realm_key_for_tier("bad") == "lianqi"  # 非法值回退沿现状
    assert player_portrait_key("", 3) is None
    assert player_portrait_path("", 3) == PLACEHOLDER_PORTRAIT


def test_gl04_ceremony_asset_key_uses_new_realms():
    from core.ceremony import build_breakthrough_ceremony

    for tier, rk in ((7, "heti"), (8, "dacheng"), (9, "dujie")):
        c = _player()
        gallery.set_gender(c, "男")
        c.realm.tier = tier
        cere = build_breakthrough_ceremony(c, {"success": True, "new_realm": c.realm.name})
        assert cere["beats"][0]["asset_key"] == f"portraits/male-{rk}", tier


# ---------------------------------------------------------------------------
# GL-05 法宝：66 件目录枚举 + 保留键合成名 + forge 生成器物
# ---------------------------------------------------------------------------
def test_gl05_catalog_66_distribution_hard_assertions():
    from collections import Counter

    from core.catalogs.equipments import EQUIPMENT_CATALOG
    from core.gallery_assets import artifact_key_for

    uniq = {}
    for cfg in EQUIPMENT_CATALOG.values():
        uniq[cfg["name"]] = cfg
    assert len(uniq) == 66
    dist = Counter()
    for cfg in uniq.values():
        k = artifact_key_for(cfg["name"], subtype=cfg.get("subtype"), slot=cfg.get("slot"))
        assert k in GALLERY_ASSET_KEYS, cfg["name"]
        dist[k] += 1
    assert dist["artifacts/armor"] == 14
    assert dist["artifacts/boots"] == 9
    assert dist["artifacts/cauldron"] == 0 and dist["artifacts/gourd"] == 0
    # 改映射后同归零的保留键（F4 口径，目录无此名器物）
    assert dist["artifacts/mirror"] == 0 and dist["artifacts/pagoda"] == 0
    assert sum(dist.values()) == 66


def test_gl05_reserved_keys_by_synthetic_names():
    from core.gallery_assets import artifact_key_for

    assert artifact_key_for("九转炼丹鼎") == "artifacts/cauldron"
    assert artifact_key_for("紫金葫芦") == "artifacts/gourd"
    assert artifact_key_for("镇海宝镜") == "artifacts/mirror"
    assert artifact_key_for("镇狱宝塔") == "artifacts/pagoda"
    assert artifact_key_for("芭蕉扇") == "artifacts/fan"


def test_gl05_new_kinds_by_subtype_and_name():
    from core.gallery_assets import artifact_key_for, artifact_key_for_equip_name

    assert artifact_key_for("无名物", subtype="重铠") == "artifacts/armor"
    assert artifact_key_for("无名物", subtype="灵靴") == "artifacts/boots"
    assert artifact_key_for("无名物", subtype="飞舟") == "artifacts/vessel"
    assert artifact_key_for("无名物", subtype="剑匣") == "artifacts/case"
    assert artifact_key_for("无名物", subtype="破空梭") == "artifacts/shuttle"
    assert artifact_key_for("无名物", subtype="护身符") == "artifacts/talisman"
    # 目录实体：战刃经 subtype 先行命中 blade（§9.5 定稿注）
    assert artifact_key_for_equip_name("万劫幽冥血刃") == "artifacts/blade"
    assert artifact_key_for_equip_name("太乙玄天戈") == "artifacts/spear"
    assert artifact_key_for_equip_name("青竹灵蜂刺") == "artifacts/needle"
    assert artifact_key_for_equip_name("七星斩妖剑匣") == "artifacts/case"


def test_gl05_forge_generated_item_resolves_by_name_keyword():
    from core.items import ItemFactory
    from core.gallery_assets import artifact_key_for_item

    item = ItemFactory.create_equip("九转炼丹鼎", tier=3, slot="trinket")
    assert artifact_key_for_item(item) == "artifacts/cauldron"


# ---------------------------------------------------------------------------
# GL-06 功法：风专图 / 御剑术负例 / 神魂专图
# ---------------------------------------------------------------------------
def test_gl06_wind_and_spirit_arts():
    from core.gallery_assets import art_key_for
    from core.models import Element

    c = _player()
    c.spiritual_root.elements = [Element.WIND]
    assert art_key_for("吐纳术", c) == "arts/wind"      # 风灵根兜底
    assert art_key_for("御风诀") == "arts/wind"          # 风关键字
    assert art_key_for("岚影步") == "arts/wind"          # 岚关键字
    assert art_key_for("御剑术") == "arts/sword"         # 负例：不含风字仍剑图
    assert art_key_for("炼魂大法") == "arts/spirit"      # 魂关键字
    assert art_key_for("神念化形诀") == "arts/spirit"    # 神念关键字


# ---------------------------------------------------------------------------
# GL-07 宝图：稀有度逐档 / 原型键 / 回退链 / 读图点亮与负例
# ---------------------------------------------------------------------------
def test_gl07_rarity_and_archetype_keys():
    from core.gallery_assets import map_key_for, map_key_for_tier

    assert [map_key_for_tier(t) for t in (1, 2, 3, 4, 5)] == [
        "maps/map-common", "maps/map-fine", "maps/map-rare",
        "maps/map-ancient", "maps/map-celestial"]
    assert map_key_for(3, "element_puzzle") == "maps/arch-puzzle"
    assert map_key_for(3, "combat") == "maps/arch-combat"
    assert map_key_for(3, "ruin_hazard") == "maps/arch-hazard"
    assert map_key_for(3, None) == "maps/map-rare"        # 未知 archetype 回退稀有度
    assert map_key_for(5, "unknown_arch") == "maps/map-celestial"
    assert map_key_for(2) == "maps/map-fine"              # 兼容壳


def test_gl07_item_image_always_rarity_and_read_unlocks_archetype():
    from core.items import ItemFactory

    viewer = _player()
    try:
        tmap = ItemFactory.create_treasure_map("node_x", "某地", tier=5, archetype="combat")
        from core.gallery_assets import item_image_key

        assert item_image_key(tmap) == "maps/map-celestial"  # 行囊恒稀有度键
        # 未读图前原型键不点亮（负例）
        assert gallery.note_map_read(viewer.user_id, 5, None) == []
        assert gallery.get_atlas(viewer.user_id)["unlocked"] == {}
        newly = gallery.note_map_read(viewer.user_id, 5, "combat")
        assert newly == ["maps/arch-combat"]
    finally:
        _cleanup(viewer.user_id)


# ---------------------------------------------------------------------------
# GL-08 灵宠：四物种键 / derive / 呈现辅助
# ---------------------------------------------------------------------------
def test_gl08_pet_keys_and_derive():
    from core.gallery_assets import pet_key_for_species
    from core.models import SpiritPet

    assert pet_key_for_species("青鳞蟒") == "pets/pet-qinglinmang"
    assert pet_key_for_species("疾风隼") == "pets/pet-jifengxun"
    assert pet_key_for_species("玄甲龟") == "pets/pet-xuanjiagui"
    assert pet_key_for_species("寻宝鼠") == "pets/pet-xunbaoshu"
    assert pet_key_for_species("AI生成兽") == ""

    c = _player()
    c.pets = [
        SpiritPet(species="玄甲龟", name="阿甲", active=True, state="follow"),
        SpiritPet(species="青鳞蟒", name="小青", active=False, state="dead"),
    ]
    keys = set(gallery.derive_keys_from_character(c))
    assert "pets/pet-xuanjiagui" in keys
    assert "pets/pet-qinglinmang" not in keys  # 已殁不点亮
    assert gallery.pet_image_key(c) == "pets/pet-xuanjiagui"  # 出战宠优先
    c.pets[0].active = False
    assert gallery.pet_image_key(c) == "pets/pet-xuanjiagui"  # 无出战取首只活宠


# ---------------------------------------------------------------------------
# GL-09 场景：映射表 15 键逐项 / 到访点亮（world 下发为集成项见 xfail）
# ---------------------------------------------------------------------------
def test_gl09_scene_mapping_table_all_15():
    from core.gallery_assets import (
        LOCATION_SCENE_KEYS, REALM_SCENE_KEYS, scene_key_for_location,
        scene_key_for_realm, scene_path_for_location)

    loc_expected = {
        "青云坊市客栈": "scenes/market-inn", "青云宗外门山门": "scenes/qingyun-gate",
        "宗门玄元洞府": "scenes/xuanyuan-cave", "落霞山灵泉": "scenes/luoxia-spring",
        "黑水沼泽": "scenes/heishui-swamp", "万剑仙门峰": "scenes/wanjian-peak",
        "洗剑池洞天": "scenes/xijian-pool", "九幽天魔宗坛": "scenes/jiuyou-altar",
        "黑风绝渊": "scenes/heifeng-abyss", "万星古岛": "scenes/wanxing-isle",
    }
    for name, key in loc_expected.items():
        assert scene_key_for_location(name) == key, name
    # 变体键同图（§9.4 / UI-05）
    assert scene_key_for_location("落霞山灵泉(野外)") == "scenes/luoxia-spring"
    assert scene_key_for_location("黑风绝渊(大凶)") == "scenes/heifeng-abyss"
    realm_expected = {
        "落霞古洞": "scenes/realm-luoxia-cave", "剑冢残碑": "scenes/realm-sword-tomb",
        "万星遗迹残址": "scenes/realm-wanxing-ruins", "幽冥鬼市": "scenes/realm-ghost-market",
        "锁妖古窟": "scenes/dungeon-entrance",
    }
    for name, key in realm_expected.items():
        assert scene_key_for_realm(name) == key, name
    assert len(set(LOCATION_SCENE_KEYS.values()) | set(REALM_SCENE_KEYS.values())) == 15
    assert scene_key_for_location("古修士洞府残址") == ""  # 无映射为空
    assert scene_path_for_location("万星古岛") == "/assets/scenes/wanxing-isle.webp"
    assert scene_path_for_location("古修士洞府残址") == ""


def test_gl09_visit_unlocks_scene_key():
    viewer = _player()
    try:
        assert gallery.note_location_visit(viewer, "黑水沼泽") == ["scenes/heishui-swamp"]
        assert gallery.note_location_visit(viewer, "黑水沼泽") == []  # 只增不重
        assert gallery.note_realm_visit(viewer, "幽冥鬼市") == ["scenes/realm-ghost-market"]
        assert gallery.note_location_visit(viewer, "古修士洞府残址") == []
    finally:
        _cleanup(viewer.user_id)


# ---------------------------------------------------------------------------
# GL-10 补足包：奇遇键表 / 丹药八类 / 材料七类 / 生成丹药负例
# ---------------------------------------------------------------------------
def test_gl10_omen_asset_keys_for_six_scripts():
    from core.gallery_assets import omen_key_for_script

    assert omen_key_for_script("black_market") == "omen/black-market"
    assert omen_key_for_script("orphan_trust") == "omen/orphan-trust"
    assert omen_key_for_script("spring_dispute") == "omen/spring-dispute"
    assert omen_key_for_script("stele") == "omen/stele"
    assert omen_key_for_script("escort_deal") == "omen/escort-deal"
    assert omen_key_for_script("inn_whisper") == "omen/inn-whisper"
    assert omen_key_for_script("ai_generated_script") == ""


def test_gl10_pill_and_material_keys():
    from core.gallery_assets import (
        goods_key_for_name, material_key_for_category, pill_key_for_type)
    from core.items import ItemFactory

    for pill_type, key in {
        "breakthrough": "goods/pill-breakthrough", "cultivation": "goods/pill-cultivation",
        "recovery": "goods/pill-recovery", "lifespan": "goods/pill-lifespan",
        "soul_purity": "goods/pill-soul", "detox": "goods/pill-detox",
        "root_purify": "goods/pill-root", "combat_buff": "goods/pill-combat",
    }.items():
        assert pill_key_for_type(pill_type) == key, pill_type
    for cat, key in {
        "herb": "goods/mat-herb", "ore": "goods/mat-ore", "metal": "goods/mat-metal",
        "beast": "goods/mat-beast", "liquid": "goods/mat-liquid",
        "wood": "goods/mat-wood", "aura": "goods/mat-aura",
    }.items():
        assert material_key_for_category(cat) == key, cat
    # 名字级解析各一例（目录实名）
    assert goods_key_for_name("聚气丹") == "goods/pill-cultivation"
    assert goods_key_for_name("筑基丹") == "goods/pill-breakthrough"
    assert goods_key_for_name("凝气草") == "goods/mat-herb"
    assert goods_key_for_name("妖兽内丹") == "goods/mat-beast"
    # 实体级分发 + 生成丹药负例（目录外名字、无 pill_type → "" 不报错）
    pill = ItemFactory.from_legacy_name("聚气丹")
    from core.gallery_assets import item_image_key

    assert item_image_key(pill) == "goods/pill-cultivation"
    fake = ItemFactory.from_legacy_name("自创无名丹")
    assert item_image_key(fake) == ""
    assert goods_key_for_name("目录外材料") == ""


def test_gl10_derive_unlocks_goods_from_items_and_inventory_names():
    from core.items import ItemFactory

    c = _player()
    try:
        c.add_item_entity(ItemFactory.from_legacy_name("聚气丹"))
        c.inventory = ["凝气草"]
        keys = set(gallery.derive_keys_from_character(c))
        assert "goods/pill-cultivation" in keys
        assert "goods/mat-herb" in keys
    finally:
        _cleanup(c.user_id)


# ---------------------------------------------------------------------------
# GL-11 图鉴：分组计数/组序 / 称号五档边界 / 点亮零数值
# ---------------------------------------------------------------------------
def test_gl11_groups_order_counts_and_total():
    names = [n for n, _ in gallery.GALLERY_GROUPS]
    assert names == ["人物·男相", "人物·女相", "人物·NPC单人", "人物·NPC原型",
                     "法宝", "功法", "藏宝图", "灵宠", "场景·地点", "场景·秘境",
                     "奇遇", "丹药", "材料"]
    assert [len(k) for _, k in gallery.GALLERY_GROUPS] == [
        10, 10, 37, 4, 20, 10, 8, 4, 10, 5, 6, 8, 7]
    all_keys = [k for _, ks in gallery.GALLERY_GROUPS for k in ks]
    assert set(all_keys) == set(GALLERY_ASSET_KEYS) and len(all_keys) == 139
    assert set(gallery.KEY_CN) == set(GALLERY_ASSET_KEYS)
    viewer = _player()
    try:
        assert gallery.summary(viewer.user_id)["total"] == 139
    finally:
        _cleanup(viewer.user_id)


def test_gl11_title_boundaries_five_tiers():
    assert gallery.highest_title(9) == ""
    assert gallery.highest_title(10) == "初窥门径"
    assert gallery.highest_title(39) == "初窥门径"
    assert gallery.highest_title(40) == "博览群真"
    assert gallery.highest_title(79) == "博览群真"
    assert gallery.highest_title(80) == "洞鉴乾坤"
    assert gallery.highest_title(119) == "洞鉴乾坤"
    assert gallery.highest_title(120) == "博物通览"
    assert gallery.highest_title(138) == "博物通览"
    assert gallery.highest_title(139) == "图录大成"


def test_gl11_unlock_all_is_zero_numeric():
    c = _player()
    try:
        before = (c.spirit_stones, c.realm.current_exp, c.karma.sin_value,
                  c.karma.merit_value, c.karma.dao_heart, c.social.dao_title)
        gallery.unlock(c.user_id, sorted(GALLERY_ASSET_KEYS))
        after = (c.spirit_stones, c.realm.current_exp, c.karma.sin_value,
                 c.karma.merit_value, c.karma.dao_heart, c.social.dao_title)
        assert before == after
        s = gallery.summary(c.user_id)
        assert s["count"] == 139 and s["title"] == "图录大成"
    finally:
        _cleanup(c.user_id)


# ---------------------------------------------------------------------------
# GL-12 托管（待资产：新目录文件未到位前如实失败）
# ---------------------------------------------------------------------------
class _Server:
    httpd = None
    port = None

    @classmethod
    def start(cls):
        if cls.httpd is None:
            from http.server import ThreadingHTTPServer

            from server.app import GameHandler

            cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), GameHandler)
            cls.port = cls.httpd.server_address[1]
            t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
            t.start()
        return cls.port


def teardown_module(module):
    if _Server.httpd is not None:
        _Server.httpd.shutdown()
        _Server.httpd = None
    try:
        from server.world import WORLD

        WORLD.stop_tick()
    except Exception:
        pass


def _get_raw(path):
    port = _Server.start()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        conn.close()


def test_gl12_new_directories_served_with_cache_headers():
    """【待资产】新目录各取一键应 200+webp+缓存头；文件未到位前失败。"""
    for key in ("pets/pet-xuanjiagui", "scenes/market-inn", "omen/stele",
                "goods/pill-soul", "portraits/npc-qy-01",
                "portraits/male-fanren", "maps/map-celestial"):
        status, headers, body = _get_raw(f"/assets/{key}.webp")
        assert status == 200, key
        assert headers.get("Content-Type") == "image/webp", key
        assert headers.get("Cache-Control") == "public, max-age=3600", key
        assert body == (ASSETS_DIR / f"{key}.webp").read_bytes(), key


def test_gl12_new_directory_unregistered_and_traversal_blocked():
    """新目录未登记键 404、穿越仍拦（G-7 扩展口径，文件无关、应全绿）。"""
    for path in ("/assets/pets/pet-nope.webp", "/assets/scenes/nope.webp",
                 "/assets/omen/nope.webp", "/assets/goods/nope.webp",
                 "/assets/pets/../config.py", "/assets/%2e%2e/config.py",
                 "/assets/goods/%2e%2e%2fconfig.py",
                 "/assets/scenes/market-inn.png"):
        status, _, _ = _get_raw(path)
        assert status != 200, path


# ---------------------------------------------------------------------------
# GL-13 资产规格（待资产：新增 101 张未到位前如实失败）
# ---------------------------------------------------------------------------
def test_gl13_new_assets_within_120kb():
    """【待资产】新增资产单张 ≤120KB；文件缺失即计入失败清单。"""
    # 新增 101 键按二期键定义枚举（存量 38 键 §9.11 不追溯）
    added = [k for k in sorted(GALLERY_ASSET_KEYS) if _is_phase2_new_key(k)]
    assert len(added) == 101, len(added)
    bad = []
    for key in added:
        fp = ASSETS_DIR / f"{key}.webp"
        if not fp.is_file() or fp.stat().st_size > 120 * 1024:
            bad.append(key)
    assert bad == [], f"缺失或超 120KB 的新增资产: {bad}"


def _is_phase2_new_key(key: str) -> bool:
    if key.split("/")[0] in ("pets", "scenes", "omen", "goods"):
        return True
    if key.startswith("portraits/npc-") and key not in {
            "portraits/npc-laodao", "portraits/npc-shanggu",
            "portraits/npc-nvxiu", "portraits/npc-shaonian"}:
        return True
    if key in {"portraits/male-fanren", "portraits/female-fanren",
               "portraits/male-heti", "portraits/female-heti",
               "portraits/male-dacheng", "portraits/female-dacheng",
               "portraits/male-dujie", "portraits/female-dujie"}:
        return True
    if key.startswith("artifacts/") and key.split("/")[1] in {
            "armor", "boots", "staff", "vessel", "blade", "spear",
            "case", "needle", "shuttle", "talisman"}:
        return True
    if key in {"arts/wind", "arts/spirit", "maps/map-celestial",
               "maps/arch-puzzle", "maps/arch-combat", "maps/arch-hazard"}:
        return True
    return False


# ---------------------------------------------------------------------------
# GL-14 §9.2 九处修订销账（源码级）：修订后串在、旧串不在
# ---------------------------------------------------------------------------
def test_gl14_nine_revisions_present_in_existing_tests():
    assets_src = (ROOT / "tests" / "test_gallery_assets.py").read_text(encoding="utf-8")
    atlas_src = (ROOT / "tests" / "test_gallery_atlas.py").read_text(encoding="utf-8")
    front_src = (ROOT / "tests" / "test_gallery_frontend_contract.py").read_text(encoding="utf-8")
    # 1/2 G-3
    assert 'player_portrait_path("male", 0) == "/assets/portraits/male-fanren.webp"' in assets_src
    assert 'player_portrait_path("female", 7) == "/assets/portraits/female-heti.webp"' in assets_src
    assert 'player_portrait_path("male", 0) == "/assets/portraits/male-lianqi.webp"' not in assets_src
    # 3 G-1
    assert "len(GALLERY_ASSET_KEYS) == 139" in assets_src
    # 4 C-3 / 5 C-4 / 6 C-5
    assert "portraits/female-fanren" in atlas_src
    assert 'newly == ["portraits/npc-sh-01"]' in atlas_src
    assert "博物通览" in atlas_src and "博物通览" in front_src
    # 7 G-5
    assert 'artifact_key_for("无名物", slot="armor") == "artifacts/armor"' in assets_src
    assert 'artifact_key_for("无名物", subtype="法杖") == "artifacts/staff"' in assets_src
    # 8 map tier5 / 9 wind
    assert 'map_key_for_tier(5) == "maps/map-celestial"' in assets_src
    assert 'art_key_for("吐纳术", c) == "arts/wind"' in assets_src


# ---------------------------------------------------------------------------
# 待集成契约（world.py / omen_scene / treasure_system 接线，非本岗文件）
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=False, reason="待集成：world.py 须下发 location_image/scene_image 与 pet.img（§8.1/§9.3/§9.4），调用 note_location_visit/note_realm_visit/note_map_read 的接线亦在彼处")
def test_integration_world_side_wiring_present():
    world_src = (ROOT / "server" / "world.py").read_text(encoding="utf-8")
    assert "location_image" in world_src
    assert "scene_image" in world_src
    assert "note_location_visit" in world_src


@pytest.mark.xfail(strict=False, reason="待集成：core/omen_scene.OMEN_SCRIPT_IMAGES 六值须改指 omen/* 专图键（§9.8），本岗只提供 gallery_assets.OMEN_SCRIPT_ASSET_KEYS 事实源")
def test_integration_omen_script_images_point_to_dedicated_keys():
    from core.omen_scene import script_image_key

    assert script_image_key("black_market") == "omen/black-market"
    assert script_image_key("orphan_trust") == "omen/orphan-trust"
    assert script_image_key("spring_dispute") == "omen/spring-dispute"
    assert script_image_key("stele") == "omen/stele"
    assert script_image_key("escort_deal") == "omen/escort-deal"
    assert script_image_key("inn_whisper") == "omen/inn-whisper"
