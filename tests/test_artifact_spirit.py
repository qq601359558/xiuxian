"""法宝器灵（spec: gallery-gameplay §6，验收 S-1~S-7）。

状态挂器物实体 custom_metadata["spirit"]；数值以落盘口径的内存实体值为准：
温养 tier4 30 / tier5 50 灵石、成长 +10（缺材 +5）、心情 +8、每器每日一次；
成长封顶 tier4 100（通灵满阶）/ tier5 150（化形）；战力通灵 +2% / 化形 +3%
只取最高一件、心情 ≥40 生效、心情 -5/日惰性衰减。AI 对话以 monkeypatch
模拟可用/关断两态，关断走本地性格台词池且结算一致。
"""
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from core import artifact_spirit as sp
from core.artifact_spirit import ArtifactSpiritEngine, get_spirit, panel_text
from core.clock import WorldClock
from core.items import ItemFactory
from core.models import CharacterStatus
from storage.db import init_db, ChronicleRepository

init_db()

DAY = 86400.0


def _tag():
    return uuid.uuid4().hex[:8]


def _player(stones=500):
    c = WorldClock.create_new_character(f"sp_{_tag()}", f"御灵客{_tag()}")
    c.spirit_stones = stones
    return c


def _equip(char, name="镇海宝镜", tier=4, slot="trinket", equip=True):
    it = ItemFactory.create_equip(name, tier=tier, slot=slot)
    char.add_item_entity(it)
    if equip:
        char.equipped.append(it.name)
    return it


def _awakened(char, name="镇海宝镜", tier=4, slot="trinket"):
    it = _equip(char, name=name, tier=tier, slot=slot)
    res = ArtifactSpiritEngine.awaken(char, it.name)
    assert res["success"], res
    return it


# ---------------------------------------------------------------------------
# S-1 资格与唤灵 / 确定性
# ---------------------------------------------------------------------------
def test_s1_eligibility_and_awaken():
    c = _player()
    # tier 3 已穿戴 → 拒
    low = _equip(c, name="青锋利剑", tier=3, slot="weapon")
    res = ArtifactSpiritEngine.awaken(c, low.name)
    assert not res["success"] and get_spirit(low) is None
    # tier 4 未穿戴 → 拒
    bag = _equip(c, name="紫金葫芦", tier=4, slot="trinket", equip=False)
    res = ArtifactSpiritEngine.awaken(c, bag.name)
    assert not res["success"] and "未穿戴" in res["message"] and get_spirit(bag) is None
    # tier 4 已穿戴 → 成功落盘
    it = _equip(c)
    res = ArtifactSpiritEngine.awaken(c, it.name)
    assert res["success"] and res["changed"]
    spirit = get_spirit(it)
    assert spirit["awakened"] and spirit["name"]
    assert spirit["personality"] in sp.PERSONALITIES
    assert spirit["awakened_by_name"] == c.name
    assert spirit["growth"] == 0 and spirit["mood"] == 60
    # 确定性：同 uid 恒同性格/名字（跨角色重算一致）
    assert sp.personality_for_uid(it.uid) == spirit["personality"]
    assert sp.name_for_uid(it.uid, spirit["personality"]) == spirit["name"]
    # 重复唤灵不重置四维
    spirit["growth"] = 33
    res = ArtifactSpiritEngine.awaken(c, it.name)
    assert res["success"] and not res["changed"] and spirit["growth"] == 33


def test_s1_awaken_via_equip_slots_flying_treasure():
    c = _player()
    it = _equip(c, name="破空宝梭", tier=5, slot="weapon", equip=False)
    c.equip_slots.flying_treasure = it.name  # 槽位穿戴（不在 equipped 名单）
    res = ArtifactSpiritEngine.awaken(c, it.name)
    assert res["success"], res
    assert get_spirit(it) is not None


# ---------------------------------------------------------------------------
# S-2 温养账
# ---------------------------------------------------------------------------
def test_s2_nourish_tier4_cost_growth_mood_and_daily_limit():
    now = time.time()
    c = _player(stones=500)
    it = _awakened(c)
    spirit = get_spirit(it)
    res = ArtifactSpiritEngine.nourish(c, now=now)
    assert res["success"] and c.spirit_stones == 470  # tier4 -30
    assert spirit["growth"] == 10 and spirit["mood"] == 68
    # 同日第二次：零扣费被拒
    res = ArtifactSpiritEngine.nourish(c, now=now + 3600)
    assert not res["success"] and c.spirit_stones == 470 and spirit["growth"] == 10
    # 次日可再温养
    res = ArtifactSpiritEngine.nourish(c, now=now + DAY)
    assert res["success"] and spirit["growth"] == 20 and c.spirit_stones == 440


def test_s2_nourish_tier5_cost_50():
    c = _player(stones=500)
    it = _awakened(c, name="混沌神塔", tier=5, slot="trinket")
    res = ArtifactSpiritEngine.nourish(c)
    assert res["success"] and c.spirit_stones == 450
    assert get_spirit(it)["growth"] == 10


def test_s2_nourish_material_full_and_missing_half():
    # 斩仙剑：目录 tier4，repair_materials {太乙精金: 1}
    c = _player(stones=500)
    it = _awakened(c, name="斩仙剑", tier=4, slot="weapon")
    spirit = get_spirit(it)
    # 缺材：成长 +5、文案明示、灵石照扣
    res = ArtifactSpiritEngine.nourish(c)
    assert res["success"] and spirit["growth"] == 5
    assert "缺材" in res["message"] and c.spirit_stones == 470
    # 有材：材料被耗、成长 +10
    c2 = _player(stones=500)
    it2 = _awakened(c2, name="斩仙剑", tier=4, slot="weapon")
    mat = ItemFactory.create_equip("太乙精金", tier=1, slot="trinket")
    # 材料以实体入包（create_equip 的 kind 恒为 equip 不影响按名消耗口径）
    c2.add_item_entity(mat)
    res = ArtifactSpiritEngine.nourish(c2)
    assert res["success"] and get_spirit(it2)["growth"] == 10
    assert all(x.name != "太乙精金" for x in c2.items)
    assert c2.spirit_stones == 470


def test_s2_nourish_insufficient_stones_zero_side_effect():
    c = _player(stones=10)
    it = _awakened(c)
    spirit = get_spirit(it)
    res = ArtifactSpiritEngine.nourish(c)
    assert not res["success"]
    assert c.spirit_stones == 10 and spirit["growth"] == 0 and spirit["mood"] == 60
    assert spirit["last_nourish_date"] == ""


# ---------------------------------------------------------------------------
# S-3 成长封顶与阶段 / 晋升留痕无数值发放
# ---------------------------------------------------------------------------
def test_s3_growth_caps_and_stages():
    now = time.time()
    c = _player(stones=5000)
    it = _awakened(c)
    spirit = get_spirit(it)
    spirit["growth"] = 95
    ArtifactSpiritEngine.nourish(c, now=now)
    assert spirit["growth"] == 100  # tier4 封顶
    assert sp.stage_for(spirit["growth"], 4) == 1  # 封顶即通灵，不化形
    ArtifactSpiritEngine.nourish(c, now=now + DAY)
    assert spirit["growth"] == 100  # 不再涨

    c5 = _player(stones=5000)
    it5 = _awakened(c5, name="混沌神塔", tier=5, slot="trinket")
    sp5 = get_spirit(it5)
    assert sp.stage_for(99, 5) == 1 and sp.stage_for(100, 5) == 2
    sp5["growth"] = 145
    ArtifactSpiritEngine.nourish(c5, now=now)
    assert sp5["growth"] == 150 and sp.stage_for(150, 5) == 2


def test_s3_stage_up_chronicle_and_no_numeric_grant():
    now = time.time()
    c = _player(stones=500)
    exp0 = c.realm.current_exp
    it = _awakened(c)
    spirit = get_spirit(it)
    spirit["growth"] = 45
    before = "\n".join(ChronicleRepository.get_recent(300))
    res = ArtifactSpiritEngine.nourish(c, now=now)  # 45+10=55 跨 50 晋升通灵
    assert spirit["growth"] == 55
    assert "晋升" in res["message"] and "护主" in res["message"]
    after = "\n".join(ChronicleRepository.get_recent(300))
    assert after.count("器灵护主") > before.count("器灵护主")
    # 无数值发放：修为不变、灵石只扣温养价
    assert c.realm.current_exp == exp0 and c.spirit_stones == 470


# ---------------------------------------------------------------------------
# S-4 对话与降级
# ---------------------------------------------------------------------------
def test_s4_talk_local_fallback_and_daily_growth(monkeypatch):
    monkeypatch.setattr(sp, "generate_spirit_reply", lambda *a, **k: None)
    c = _player()
    it = _awakened(c)
    spirit = get_spirit(it)
    res = ArtifactSpiritEngine.talk(c, "你好呀")
    assert res["success"] and res["source"] == "local"
    pool = sp.PERSONALITIES[spirit["personality"]]["lines"]
    assert res["reply"] in pool  # 本地台词按 personality 出句
    assert spirit["growth"] == 2 and spirit["mood"] == 63  # 每日首次 +2/+3
    res = ArtifactSpiritEngine.talk(c, "再说一句")
    assert res["success"] and spirit["growth"] == 2  # 当日后续只叙事


def test_s4_talk_ai_numbers_discarded(monkeypatch):
    import ai.gateway as gw

    monkeypatch.setattr(gw, "ai_ready", lambda: True)
    monkeypatch.setattr(gw, "_chat_json", lambda prompt, timeout=10.0: {
        "line": "吾乃器灵，听凭主人差遣。", "tone": "pleased",
        "growth": 9999, "mood": -50, "stones": 777,  # 伪造数字：一律丢弃
    })
    c = _player()
    it = _awakened(c)
    spirit = get_spirit(it)
    stones0 = c.spirit_stones
    res = ArtifactSpiritEngine.talk(c, "在吗")
    assert res["success"] and res["source"] == "ai" and res["tone"] == "pleased"
    assert res["reply"] == "吾乃器灵，听凭主人差遣。"
    # 数值只按规则动：成长 +2、心情 +3、灵石不动
    assert spirit["growth"] == 2 and spirit["mood"] == 63
    assert c.spirit_stones == stones0


def test_s4_talk_specified_item_by_separator():
    c = _player()
    it1 = _awakened(c, name="镇海宝镜", tier=4)
    it2 = _awakened(c, name="混沌神塔", tier=5, slot="weapon")
    res = ArtifactSpiritEngine.talk(c, "镇海宝镜 · 你好")
    assert res["success"] and res["item_name"] == "镇海宝镜"
    assert get_spirit(it1)["talk_count"] == 1 and get_spirit(it2)["talk_count"] == 0
    # 缺省对象 = tier 最高者
    res = ArtifactSpiritEngine.talk(c, "默认找谁")
    assert res["item_name"] == "混沌神塔"


# ---------------------------------------------------------------------------
# S-5 心情衰减与战力加成
# ---------------------------------------------------------------------------
def test_s5_mood_decay_lazy():
    now = time.time()
    c = _player()
    it = _awakened(c)
    spirit = get_spirit(it)
    spirit["mood"] = 60
    spirit["last_touch_at"] = now - 3 * DAY
    assert sp.effective_mood(spirit, now) == 45  # -5/日 × 3
    assert "45" in panel_text(c, now=now)
    spirit["last_touch_at"] = now - 30 * DAY
    assert sp.effective_mood(spirit, now) == 0  # 钳 0


def test_s5_power_bonus_max_only_mood_gate_and_stages():
    c = _player()
    it1 = _awakened(c, name="镇海宝镜", tier=4)
    it2 = _awakened(c, name="紫金葫芦", tier=4, slot="weapon")
    s1, s2 = get_spirit(it1), get_spirit(it2)
    assert ArtifactSpiritEngine.power_bonus(c) == 1.0  # 萌生无加成
    s1["growth"] = 60  # 通灵
    s2["growth"] = 60
    assert ArtifactSpiritEngine.power_bonus(c) == 1.02  # 两件通灵只取最高：2% 非 4%
    s1["mood"] = 30  # 心情 <40 怠工
    s2["mood"] = 30
    assert ArtifactSpiritEngine.power_bonus(c) == 1.0
    # 化形 +3%（tier5）
    c5 = _player()
    it5 = _awakened(c5, name="混沌神塔", tier=5, slot="trinket")
    get_spirit(it5)["growth"] = 120
    assert ArtifactSpiritEngine.power_bonus(c5) == 1.03


def test_s5_power_bonus_integrates_combat_engine():
    from core.combat import CombatEngine

    c = _player()
    it = _awakened(c)
    spirit = get_spirit(it)
    base = CombatEngine.calculate_power(c)
    spirit["growth"] = 60  # 通灵，心情 60 ≥40
    boosted = CombatEngine.calculate_power(c)
    assert abs(boosted / base - 1.02) < 1e-9


# ---------------------------------------------------------------------------
# S-6 随器流转
# ---------------------------------------------------------------------------
def test_s6_spirit_follows_item_to_new_owner():
    a = _player()
    it = _awakened(a, name="镇海宝镜", tier=4)
    spirit = get_spirit(it)
    spirit["growth"] = 42
    # 交易：器物实体整体转手（卸下 → 移交 → 新主穿戴）
    a.equipped.remove(it.name)
    a.remove_item_entity(it.uid)
    b = _player()
    b.add_item_entity(it)
    b.equipped.append(it.name)
    moved = get_spirit(it)
    assert moved is not None and moved["growth"] == 42
    assert moved["awakened_by_name"] == a.name
    text = panel_text(b)
    assert "曾随旧主" in text and a.name in text
    # 同名新器物（uid 不同）无器灵，不继承
    fresh = ItemFactory.create_equip("镇海宝镜", tier=4, slot="trinket")
    assert fresh.uid != it.uid and get_spirit(fresh) is None


# ---------------------------------------------------------------------------
# S-7 门禁
# ---------------------------------------------------------------------------
def test_s7_gates_zero_side_effect():
    c = _player()
    it = _awakened(c)
    spirit = get_spirit(it)
    c.status = CharacterStatus.MEDITATING
    res = ArtifactSpiritEngine.talk(c, "在吗")
    assert not res["success"] and spirit["talk_count"] == 0
    it2 = _equip(c, name="破空宝梭", tier=5, slot="weapon")
    res = ArtifactSpiritEngine.awaken(c, it2.name)
    assert not res["success"] and get_spirit(it2) is None
    c.status = CharacterStatus.IDLE
    c.spirit_stones = 5
    res = ArtifactSpiritEngine.nourish(c)
    assert not res["success"] and c.spirit_stones == 5 and spirit["growth"] == 0
    c.status = CharacterStatus.DEAD
    res = ArtifactSpiritEngine.awaken(c, it.name)
    assert not res["success"]


# ---------------------------------------------------------------------------
# 心情事件（§6.4 口径落点：闹脾气 / 沉睡；Spec 未定阈值，见模块缺口注记）
# ---------------------------------------------------------------------------
def test_spirit_mood_events_tantrum_and_dormant(monkeypatch):
    monkeypatch.setattr(sp, "generate_spirit_reply", lambda *a, **k: None)
    now = time.time()
    c = _player()
    it = _awakened(c)
    spirit = get_spirit(it)
    # 闹脾气：心情跌破 20 经互动折算触发一次，面板有警示
    spirit["mood"] = 15
    spirit["last_touch_at"] = now
    assert sp.spirit_event_label(spirit, now) == "闹脾气"
    res = ArtifactSpiritEngine.talk(c, "别生气", now=now)
    assert "闹脾气" in res["message"] and spirit["mood_event_stage"] == 1
    res = ArtifactSpiritEngine.talk(c, "还在吗", now=now)
    assert "闹脾气" not in res["message"]  # 同档不重复记
    # 沉睡：心情归 0，对话只回沉睡句、加成为 0
    spirit["mood"] = 0
    spirit["growth"] = 60
    assert sp.spirit_event_label(spirit, now) == "沉睡"
    assert ArtifactSpiritEngine.power_bonus(c, now=now) == 1.0
    res = ArtifactSpiritEngine.talk(c, "醒醒", now=now)
    assert "沉睡不醒" in res["reply"]


def test_public_spirit_dict_shape():
    c = _player()
    it = _awakened(c)
    d = sp.public_spirit_dict(it)
    assert d["name"] and d["personality_cn"] and d["stage_cn"] == "萌生"
    assert d["mood"] == 60 and d["growth"] == 0
    assert d["img"].startswith("/assets/artifacts/") and d["img"].endswith(".webp")
    plain = _equip(c, name="凡铁剑", tier=2, slot="weapon")
    assert sp.public_spirit_dict(plain) is None


def test_status_dict_equipped_spirit_key():
    """命盘 equipped[].spirit 只增键下发（§6.5/§10.1）：唤灵后为四维 dict，
    未唤灵器物为 null。"""
    from server.world import WORLD

    c = _player()
    it = _awakened(c)
    plain = _equip(c, name="凡铁剑", tier=2, slot="weapon")
    st = WORLD._status_dict(c)
    by_name = {e["name"]: e for e in st["equipped"]}
    assert by_name[it.name]["spirit"]["name"] == get_spirit(it)["name"]
    assert by_name[it.name]["spirit"]["stage_cn"] == "萌生"
    assert by_name[plain.name]["spirit"] is None
