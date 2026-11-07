"""图库资产与托管（spec: gallery-gameplay §3/§4，验收 G-1~G-7 后端部分）。

- G-1：后端常量 GALLERY_ASSET_KEYS 与 web/assets/ 磁盘文件双向一致（38 键）
- G-2/G-6：/assets/ 真实 HTTP 200 + image/webp + 字节一致 + 缓存头
- G-7：≥8 种穿越/未登记变体一律非 200（含磁盘预置未登记文件仍 404）
- G-3/G-4/G-5：人物图 / NPC 原型 / 法宝图解析枚举与确定性
"""
import http.client
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from http.server import ThreadingHTTPServer

from server.app import GameHandler
from server.world import WORLD

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "web" / "assets"


class _Server:
    httpd = None
    port = None

    @classmethod
    def start(cls):
        if cls.httpd is None:
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


def _get(path):
    port = _Server.start()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


# ---------------------------------------------------------------------------
# G-1 常量集与磁盘双向一致
# ---------------------------------------------------------------------------
def test_g1_asset_keys_match_disk_both_ways():
    from core.gallery_assets import GALLERY_ASSET_KEYS

    assert len(GALLERY_ASSET_KEYS) == 139  # §9.2 契约变更表第3行：38→139（§9.9 总账）
    disk = {
        str(p.relative_to(ASSETS_DIR))[:-len(".webp")]
        for p in ASSETS_DIR.rglob("*.webp")
    }
    assert disk == set(GALLERY_ASSET_KEYS), (
        f"仅磁盘有: {disk - set(GALLERY_ASSET_KEYS)}；仅常量有: {set(GALLERY_ASSET_KEYS) - disk}"
    )


# ---------------------------------------------------------------------------
# G-2 / G-6 全图可取 + 缓存头
# ---------------------------------------------------------------------------
def test_g2_all_assets_served_with_webp_and_cache_headers():
    from core.gallery_assets import GALLERY_ASSET_KEYS

    for key in sorted(GALLERY_ASSET_KEYS):
        status, headers, body = _get(f"/assets/{key}.webp")
        assert status == 200, key
        assert headers.get("Content-Type") == "image/webp", key
        assert headers.get("Cache-Control") == "public, max-age=3600", key
        assert body == (ASSETS_DIR / f"{key}.webp").read_bytes(), key


def test_g6_page_routes_still_no_cache():
    status, headers, _ = _get("/")
    assert status == 200
    assert headers.get("Cache-Control") == "no-cache"


# ---------------------------------------------------------------------------
# G-7 托管安全：穿越与未登记一律非 200
# ---------------------------------------------------------------------------
def test_g7_traversal_and_unregistered_variants_blocked():
    variants = [
        "/assets/../config.py",
        "/assets/%2e%2e/config.py",
        "/assets/portraits/%2e%2e%2fconfig.py",
        "/assets/portraits/male-lianqi.WEBP",
        "/assets/portraits//male-lianqi.webp",
        "/assets\\portraits\\male-lianqi.webp",
        "/assets/portraits/male-lianqi.webp/extra",
        "/assets/portraits/male-lianqi.png",
        "/assets/portraits/nested/male-lianqi.webp",
    ]
    for path in variants:
        status, _, body = _get_raw(path)
        assert status != 200, path
        assert b"male-lianqi" not in body or status == 404, path


def test_g7_unregistered_file_on_disk_still_404():
    """双闸关键断言：正则合法但不在常量集的文件，即使磁盘存在也 404。"""
    ghost = ASSETS_DIR / "portraits" / "male-foo.webp"
    ghost.write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
    try:
        status, _, _ = _get_raw("/assets/portraits/male-foo.webp")
        assert status == 404
    finally:
        ghost.unlink()


def test_g7_prototype_still_unreachable():
    status, _, _ = _get("/prototype.html")
    assert status == 404


# ---------------------------------------------------------------------------
# G-3 人物图解析
# ---------------------------------------------------------------------------
def test_g3_player_portrait_matrix_and_clamps():
    from core.gallery_assets import player_portrait_path, PLACEHOLDER_PORTRAIT

    realms = ["lianqi", "zhuji", "jindan", "yuanying", "huashen", "lianxu", "heti", "dacheng", "dujie"]
    for gender in ("male", "female"):
        for tier, rk in enumerate(realms, start=1):
            assert player_portrait_path(gender, tier) == f"/assets/portraits/{gender}-{rk}.webp"
    # §9.2 契约变更表第1/2行：tier 0 → fanren（不再借 lianqi）；
    # tier 7 → heti（不再封顶借 lianxu），另补 tier 8/9/10+ 三例
    assert player_portrait_path("male", 0) == "/assets/portraits/male-fanren.webp"
    assert player_portrait_path("female", 7) == "/assets/portraits/female-heti.webp"
    assert player_portrait_path("male", 8) == "/assets/portraits/male-dacheng.webp"
    assert player_portrait_path("female", 9) == "/assets/portraits/female-dujie.webp"
    assert player_portrait_path("male", 12) == "/assets/portraits/male-dujie.webp"
    # 未定相不猜：占位图
    assert player_portrait_path("", 3) == PLACEHOLDER_PORTRAIT


def test_g3_set_gender_and_old_save_compat():
    from core.clock import WorldClock
    from core import gallery

    c = WorldClock.create_new_character("ga_test_gender", "定相客")
    assert c.gender == ""
    res = gallery.set_gender(c, "女")
    assert res["success"] and c.gender == "female"
    res = gallery.set_gender(c, "男")
    assert res["success"] and c.gender == "male"
    res = gallery.set_gender(c, "猫")
    assert not res["success"] and c.gender == "male"

    # 旧存档（无 gender 字段）零迁移可读
    data = c.model_dump()
    data.pop("gender", None)
    from core.models import Character

    old = Character.model_validate(data)
    assert old.gender == ""


# ---------------------------------------------------------------------------
# G-4 NPC 原型枚举
# ---------------------------------------------------------------------------
def test_g4_roster_archetype_enumeration():
    from core.gallery_assets import roster_archetype_table, NPC_FEMALE_NAMES
    from core.npc_roster import ROSTER

    table = roster_archetype_table()
    assert len(table) == len(ROSTER) == 37
    assert set(table.values()) <= {"npc-laodao", "npc-shanggu", "npc-nvxiu", "npc-shaonian"}
    for name in NPC_FEMALE_NAMES:
        assert table[name] == "npc-nvxiu", name
    # 商会成员（非女修名单者）全中 shanggu
    for row in ROSTER:
        if row["sect"] == "四海散修商会" and row["name"] not in NPC_FEMALE_NAMES:
            assert table[row["name"]] == "npc-shanggu", row["name"]
    # 名单外疑似女修名不扩名单：小雀儿（商会→商贾）、白霜（万剑执事→少年兜底）
    assert table["小雀儿"] == "npc-shanggu"
    assert table["白霜"] == "npc-shaonian"


def test_g4_dynamic_npc_never_nvxiu():
    from core.gallery_assets import resolve_npc_archetype

    # 动态 NPC 即使同名也不进 nvxiu（无性别事实源）
    assert resolve_npc_archetype("苏婉清", sect="青云宗", rank="内门弟子", tier=1, in_roster=False) == "npc-shaonian"


# ---------------------------------------------------------------------------
# G-5 法宝图解析枚举
# ---------------------------------------------------------------------------
def test_g5_equipment_catalog_all_resolve_deterministically():
    from core.catalogs.equipments import EQUIPMENT_CATALOG
    from core.gallery_assets import artifact_key_for, GALLERY_ASSET_KEYS

    artifact_keys = {k for k in GALLERY_ASSET_KEYS if k.startswith("artifacts/")}
    assert len(EQUIPMENT_CATALOG) == 132
    for cfg in EQUIPMENT_CATALOG.values():
        k1 = artifact_key_for(cfg["name"], subtype=cfg.get("subtype"), slot=cfg.get("slot"))
        k2 = artifact_key_for(cfg["name"], subtype=cfg.get("subtype"), slot=cfg.get("slot"))
        assert k1 in artifact_keys, cfg["name"]
        assert k1 == k2, cfg["name"]


def test_g5_name_keyword_priority_for_absent_subtypes():
    from core.gallery_assets import artifact_key_for

    assert artifact_key_for("镇海宝镜") == "artifacts/mirror"
    assert artifact_key_for("九转炼丹鼎") == "artifacts/cauldron"
    assert artifact_key_for("紫金葫芦") == "artifacts/gourd"
    assert artifact_key_for("芭蕉扇") == "artifacts/fan"
    # 关键字优先于 subtype/槽位
    assert artifact_key_for("照妖镜", subtype="宝珠", slot="weapon") == "artifacts/mirror"
    # subtype 二级、槽位三级、无信息兜底 sword
    # §9.2 契约变更表第7行（§9.5）：法杖→staff、armor→armor、boots→boots（不再借代）
    assert artifact_key_for("无名物", subtype="法杖") == "artifacts/staff"
    assert artifact_key_for("无名物", slot="armor") == "artifacts/armor"
    assert artifact_key_for("无名物", slot="boots") == "artifacts/boots"
    assert artifact_key_for("无名物", slot="flying_treasure") == "artifacts/pagoda"
    assert artifact_key_for("无名物") == "artifacts/sword"


# ---------------------------------------------------------------------------
# §3.7 功法图 / 宝图图解析
# ---------------------------------------------------------------------------
def test_art_and_map_key_resolution():
    from core.clock import WorldClock
    from core.gallery_assets import art_key_for, map_key_for_tier
    from core.models import Element

    assert art_key_for("玄冰诀") == "arts/ice"  # 冰序在水前（刻意裁定）
    assert art_key_for("霹雳雷法") == "arts/thunder"
    assert art_key_for("御剑术") == "arts/sword"
    assert art_key_for("焚天功") == "arts/fire"
    # 灵根兜底：名字无关键字时取首元素
    c = WorldClock.create_new_character("ga_test_art", "功法客")
    c.spiritual_root.elements = [Element.THUNDER]
    assert art_key_for("吐纳术", c) == "arts/thunder"
    c.spiritual_root.elements = [Element.WIND]
    assert art_key_for("吐纳术", c) == "arts/wind"  # §9.2 契约变更表第9行：风有专图（§9.6）
    # 无灵根信息 → earth
    assert art_key_for("吐纳术") == "arts/earth"
    # 宝图 rarity
    assert map_key_for_tier(1) == "maps/map-common"
    assert map_key_for_tier(2) == "maps/map-fine"
    assert map_key_for_tier(3) == "maps/map-rare"
    assert map_key_for_tier(4) == "maps/map-ancient"
    assert map_key_for_tier(5) == "maps/map-celestial"  # §9.2 契约变更表第8行：tier5 独立键（§9.7）
