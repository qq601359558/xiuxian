"""图鉴（spec: gallery-gameplay §8，验收 C-1~C-5/C-7/C-8 后端部分）。

落点 WorldState KV gallery_atlas:{user_id}（账户级）；派生点亮以角色
事实推导、事件点亮走统一 unlock；称号只展示零数值、不写 dao_title。
隔离方式：唯一 user_id 前缀，KV 键用例后删除。
"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from core.clock import WorldClock
from core import gallery
from core.gallery_assets import GALLERY_ASSET_KEYS
from core.items import ItemFactory, ItemKind
from storage.db import init_db, WorldStateRepository

init_db()


def _tag():
    return uuid.uuid4().hex[:8]


def _player():
    uid = f"ga_{_tag()}"
    c = WorldClock.create_new_character(uid, f"鉴客{_tag()}")
    return c


def _cleanup(user_id):
    WorldStateRepository.delete(gallery.ATLAS_KEY_PREFIX + str(user_id))


# ---------------------------------------------------------------------------
# C-1 KV 落点与兼容
# ---------------------------------------------------------------------------
def test_c1_empty_atlas_and_kv_structure():
    c = _player()
    try:
        s = gallery.summary(c.user_id)
        assert s["count"] == 0 and s["total"] == 139 and s["unlocked"] == []  # §9.2 表第3行总账连带：total 随常量 38→139
        newly = gallery.unlock(c.user_id, ["arts/fire"])
        assert newly == ["arts/fire"]
        raw = WorldStateRepository.get(gallery.ATLAS_KEY_PREFIX + c.user_id)
        assert set(raw["unlocked"].keys()) == {"arts/fire"}
        assert isinstance(raw["titles"], list)
    finally:
        _cleanup(c.user_id)


def test_c1_unlock_idempotent_and_foreign_keys_rejected():
    c = _player()
    try:
        assert gallery.unlock(c.user_id, ["arts/fire"]) == ["arts/fire"]
        assert gallery.unlock(c.user_id, ["arts/fire"]) == []  # 只增不重
        assert gallery.unlock(c.user_id, ["bogus/key", "/etc/passwd"]) == []
        assert gallery.summary(c.user_id)["count"] == 1
    finally:
        _cleanup(c.user_id)


# ---------------------------------------------------------------------------
# C-2 派生点亮（行囊/穿戴/功法/宝图/基础神通）
# ---------------------------------------------------------------------------
def test_c2_derived_unlock_from_inventory():
    c = _player()
    try:
        c.add_item_entity(ItemFactory.create_equip("照妖镜", tier=3, slot="trinket"))
        c.add_item_entity(ItemFactory.create_equip("青锋剑", tier=2, slot="weapon"))
        for tier in (1, 2, 3, 4):
            c.add_item_entity(ItemFactory.create_treasure_map("node_x", "某地", tier=tier))
        newly = set(gallery.unlock_from_character(c))
        assert "artifacts/mirror" in newly
        assert "artifacts/sword" in newly
        for k in ("maps/map-common", "maps/map-fine", "maps/map-rare", "maps/map-ancient"):
            assert k in newly, k
        # 基础五神通呈现即点亮五行
        for k in ("arts/metal", "arts/wood", "arts/water", "arts/fire", "arts/earth"):
            assert k in newly, k
        # 已习得功法：御剑术（剑关键字）
        assert "arts/sword" in newly
        # 第二次合并无新点亮
        assert gallery.unlock_from_character(c) == []
    finally:
        _cleanup(c.user_id)


# ---------------------------------------------------------------------------
# C-3 本人图点亮（本性别当前及以下、异性不点亮）
# ---------------------------------------------------------------------------
def test_c3_self_portraits_by_gender_and_tier():
    c = _player()
    try:
        gallery.set_gender(c, "女")
        c.realm.tier = 3
        keys = set(gallery.derive_keys_from_character(c))
        # §9.2 契约变更表第4行：tier3 点亮集合另含 fanren（§9.2 派生口径）
        assert {"portraits/female-fanren", "portraits/female-lianqi", "portraits/female-zhuji", "portraits/female-jindan"} <= keys
        assert "portraits/female-yuanying" not in keys
        assert not any(k.startswith("portraits/male-") for k in keys)
        # 未定相不点亮任何本人图
        c2 = _player()
        assert not any("portraits/male-" in k or "portraits/female-" in k
                       for k in gallery.derive_keys_from_character(c2))
    finally:
        _cleanup(c.user_id)


# ---------------------------------------------------------------------------
# C-4 事件点亮（NPC 原型 / 同场玩家）
# ---------------------------------------------------------------------------
def test_c4_event_unlock_npc_and_player():
    viewer = _player()
    try:
        npc = WorldClock.create_new_character("npc_ga_merchant", "金满堂")
        npc.sect = "四海散修商会"
        npc.sect_rank = "会长"
        newly = gallery.note_npc_encounter(viewer, npc)
        # §9.2 契约变更表第5行：金满堂命中 ROSTER → 点亮单人键（§9.1）
        assert newly == ["portraits/npc-sh-01"]

        other = _player()
        gallery.set_gender(other, "女")
        other.realm.tier = 2
        newly = gallery.note_player_encounter(viewer, other)
        assert newly == ["portraits/female-zhuji"]
        # 未定相玩家不点亮
        plain = _player()
        assert gallery.note_player_encounter(viewer, plain) == []
        # 奇遇配图接口：全集内键可点亮、全集外拒绝
        assert gallery.note_omen_image(viewer.user_id, "maps/map-ancient") == ["maps/map-ancient"]
        assert gallery.note_omen_image(viewer.user_id, "maps/map-nope") == []
    finally:
        _cleanup(viewer.user_id)


# ---------------------------------------------------------------------------
# C-5 零数值奖励 + 称号四档
# ---------------------------------------------------------------------------
def test_c5_titles_are_display_only_zero_numeric():
    c = _player()
    try:
        c.spirit_stones = 500
        c.realm.current_exp = 100
        before = (
            c.spirit_stones, c.realm.current_exp, c.lifespan.death_timestamp,
            c.karma.sin_value, c.karma.merit_value, c.karma.dao_heart,
            c.social.dao_title,
        )
        keys = sorted(GALLERY_ASSET_KEYS)
        # §9.2 契约变更表第6行：称号按 §9.10 新五档 (10/40/80/120/139) 修订
        gallery.unlock(c.user_id, keys[:10])
        assert gallery.summary(c.user_id)["title"] == "初窥门径"
        gallery.unlock(c.user_id, keys[:40])
        assert gallery.summary(c.user_id)["title"] == "博览群真"
        gallery.unlock(c.user_id, keys[:80])
        assert gallery.summary(c.user_id)["title"] == "洞鉴乾坤"
        gallery.unlock(c.user_id, keys[:120])
        assert gallery.summary(c.user_id)["title"] == "博物通览"
        gallery.unlock(c.user_id, keys)
        s = gallery.summary(c.user_id)
        assert s["count"] == 139 and s["title"] == "图录大成"
        after = (
            c.spirit_stones, c.realm.current_exp, c.lifespan.death_timestamp,
            c.karma.sin_value, c.karma.merit_value, c.karma.dao_heart,
            c.social.dao_title,
        )
        assert before == after  # 全程零数值、称号不入 dao_title
        assert gallery.highest_title(9) == ""
        assert gallery.highest_title(10) == "初窥门径"
    finally:
        _cleanup(c.user_id)


# ---------------------------------------------------------------------------
# C-7 跨世保留（账户级：同 user_id 新角色读同一图鉴）
# ---------------------------------------------------------------------------
def test_c7_atlas_survives_new_character_same_account():
    c = _player()
    try:
        gallery.unlock(c.user_id, ["arts/ice", "artifacts/fan"])
        reborn = WorldClock.create_new_character(c.user_id, "转世鉴客")
        s = gallery.summary(reborn.user_id)
        assert s["count"] == 2
        assert set(s["unlocked"]) == {"arts/ice", "artifacts/fan"}
    finally:
        _cleanup(c.user_id)


# ---------------------------------------------------------------------------
# C-8 脏键清理
# ---------------------------------------------------------------------------
def test_c8_dirty_keys_ignored_and_cleaned_on_merge():
    c = _player()
    key = gallery.ATLAS_KEY_PREFIX + c.user_id
    try:
        WorldStateRepository.set(key, {"unlocked": {"bogus/key": 1.0, "arts/fire": 2.0}, "titles": []})
        s = gallery.summary(c.user_id)
        assert s["count"] == 1 and s["unlocked"] == ["arts/fire"]
        gallery.unlock(c.user_id, ["arts/ice"])
        raw = WorldStateRepository.get(key)
        assert "bogus/key" not in raw["unlocked"]
        assert set(raw["unlocked"].keys()) == {"arts/fire", "arts/ice"}
    finally:
        _cleanup(c.user_id)


def test_panel_text_progress_and_groups():
    c = _player()
    try:
        gallery.unlock(c.user_id, ["arts/fire"])
        text = gallery.panel_text(c)
        assert "1/139" in text  # §9.2 表第3行总账连带：面板进度分母随常量 38→139
        assert "法宝" in text and "藏宝图" in text and "NPC" in text
    finally:
        _cleanup(c.user_id)
