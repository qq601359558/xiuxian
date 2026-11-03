"""F01 灵宠系统：契约/喂养/出战/助战/放生/遇兽/死亡/旧档兼容"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core.clock import WorldClock
from core.models import Character, CharacterStatus
from core.combat import CombatEngine
from core.adventure import AdventureEngine
import core.pets as pets_mod
from core.pets import (
    PetEngine,
    active_pet,
    level_for,
    PET_CONTRACT_STONES,
    PET_FEED_STONES,
    PET_MAX_OWNED,
)
from server.world import WORLD

WORLD.stop_tick()


def _char(name="驭兽者", stones=500):
    c = WorldClock.create_new_character(f"pet_{name}", name)
    c.spirit_stones = stones
    return c


def _contract(c, species="青鳞蟒"):
    c.pending_pet_species = species
    res = PetEngine.contract(c, species)
    assert res["success"], res
    return res["pet"]


def test_contract_success_and_cost():
    c = _char()
    s0 = c.spirit_stones
    pet = _contract(c, "青鳞蟒")
    assert c.spirit_stones == s0 - PET_CONTRACT_STONES
    assert c.pending_pet_species == ""
    assert pet in c.pets and pet.state == "rest" and pet.active is False
    assert pet.intimacy == 10
    print("✓ 契约成功：扣灵石、入册、待契约清空")


def test_contract_failures():
    c = _char()
    # 无待契约
    res = PetEngine.contract(c, "青鳞蟒")
    assert not res["success"]
    # 兽名不符
    c.pending_pet_species = "玄甲龟"
    res = PetEngine.contract(c, "青鳞蟒")
    assert not res["success"] and c.pending_pet_species == "玄甲龟"
    # 灵石不足：不扣石、不清待契约
    c.spirit_stones = PET_CONTRACT_STONES - 1
    res = PetEngine.contract(c, "玄甲龟")
    assert not res["success"]
    assert c.spirit_stones == PET_CONTRACT_STONES - 1
    assert c.pending_pet_species == "玄甲龟" and len(c.pets) == 0
    # 闭关中拒绝
    c.spirit_stones = 500
    c.status = CharacterStatus.MEDITATING
    res = PetEngine.contract(c, "玄甲龟")
    assert not res["success"]
    print("✓ 契约失败分支：无待契约/名不符/灵石不足/闭关")


def test_contract_limit_three():
    c = _char(stones=9999)
    for sp in ("青鳞蟒", "玄甲龟", "寻宝鼠"):
        _contract(c, sp)
    assert len(c.pets) == PET_MAX_OWNED
    c.pending_pet_species = "疾风隼"
    res = PetEngine.contract(c, "疾风隼")
    assert not res["success"] and len(c.pets) == PET_MAX_OWNED
    print("✓ 限养 3 只：第 4 只契约被拒")


def test_feed_stones_growth_and_level():
    c = _char()
    pet = _contract(c)
    s0 = c.spirit_stones
    res = PetEngine.feed(c, pet.name)
    assert res["success"], res
    assert c.spirit_stones == s0 - PET_FEED_STONES
    assert pet.growth == pets_mod.PET_FEED_STONES_GROWTH
    assert pet.intimacy == 10 + pets_mod.PET_FEED_STONES_INTIMACY
    # 成长攒满一级阈值 → 等级提升
    pet.growth = pets_mod.PET_GROWTH_PER_LEVEL - pets_mod.PET_FEED_STONES_GROWTH
    PetEngine.feed(c, pet.name)
    assert level_for(pet.growth) == 2
    print("✓ 灵石喂养：成长/亲密增加并升级")


def test_feed_pill_and_failures():
    c = _char()
    pet = _contract(c)
    c.inventory.append("聚气丹")
    res = PetEngine.feed(c, pet.name, "聚气丹")
    assert res["success"], res
    assert "聚气丹" not in c.inventory
    assert pet.growth == pets_mod.PET_FEED_PILL_GROWTH
    # 非丹药/无丹药/灵石不足
    assert not PetEngine.feed(c, pet.name, "青锋剑")["success"]
    assert not PetEngine.feed(c, pet.name, "筑基丹")["success"]
    c.spirit_stones = PET_FEED_STONES - 1
    assert not PetEngine.feed(c, pet.name)["success"]
    assert not PetEngine.feed(c, "不存在的宠")["success"]
    print("✓ 丹药喂养消耗丹药；失败分支齐全")


def test_deploy_uniqueness_and_rest():
    c = _char(stones=9999)
    p1 = _contract(c, "青鳞蟒")
    p2 = _contract(c, "玄甲龟")
    assert PetEngine.deploy(c, p1.name)["success"]
    assert active_pet(c) is p1 and p1.state == "follow"
    assert PetEngine.deploy(c, p2.name)["success"]
    actives = [p for p in c.pets if p.active]
    assert actives == [p2] and p1.state == "rest"
    assert PetEngine.rest(c, p2.name)["success"]
    assert active_pet(c) is None and p2.state == "rest"
    print("✓ 出战唯一性：换宠自动退前宠；休息清出战")


def test_power_bonus_rules():
    c = _char()
    base = CombatEngine.calculate_power(c)
    pet = _contract(c, "青鳞蟒")
    PetEngine.deploy(c, pet.name)
    # 初始亲密 10 < 20：不出力
    assert PetEngine.power_bonus(c) == 1.0
    assert CombatEngine.calculate_power(c) == base
    pet.intimacy = 50
    pet.growth = 400  # 5 级 → +7%
    assert abs(PetEngine.power_bonus(c) - 1.07) < 1e-9
    boosted = CombatEngine.calculate_power(c)
    assert abs(boosted / base - 1.07) < 1e-6
    # 封顶 +10%
    pet.growth = 5000
    assert abs(PetEngine.power_bonus(c) - 1.10) < 1e-9
    # 探宝宠减半
    c2 = _char("探宝者")
    mouse = _contract(c2, "寻宝鼠")
    PetEngine.deploy(c2, mouse.name)
    mouse.intimacy = 50
    mouse.growth = 400
    assert abs(PetEngine.power_bonus(c2) - 1.035) < 1e-9
    print("✓ 助战加成：亲密门槛/等级公式/+10% 封顶/探宝减半，且已接入斗法战力")


def test_release_removes_pet():
    c = _char(stones=9999)
    p1 = _contract(c, "青鳞蟒")
    _contract(c, "玄甲龟")
    PetEngine.deploy(c, p1.name)
    res = PetEngine.release(c, p1.name)
    assert res["success"]
    assert p1 not in c.pets and len(c.pets) == 1
    assert active_pet(c) is None
    assert not PetEngine.release(c, p1.name)["success"]
    print("✓ 放生：移除灵宠且出战位清空")


def test_encounter_roll_and_flee():
    import random as _random

    c = _char()
    old_chance = pets_mod.PET_ENCOUNTER_CHANCE
    old_flee = pets_mod.PET_PENDING_FLEE_CHANCE
    try:
        pets_mod.PET_ENCOUNTER_CHANCE = 1.0
        sp = PetEngine.maybe_encounter(c, _random.Random(7))
        assert sp in pets_mod.PET_SPECIES and c.pending_pet_species == sp
        # 已有待契约时不重复触发；遁走概率拉满 → 清空
        pets_mod.PET_PENDING_FLEE_CHANCE = 1.0
        assert PetEngine.maybe_encounter(c, _random.Random(7)) is None
        assert c.pending_pet_species == ""
    finally:
        pets_mod.PET_ENCOUNTER_CHANCE = old_chance
        pets_mod.PET_PENDING_FLEE_CHANCE = old_flee
    print("✓ 遇兽骰：命中写入待契约；待契约期间可遁走")


def test_adventure_hook_sets_pending():
    import random as _random

    c = _char(stones=9999)
    old_chance = pets_mod.PET_ENCOUNTER_CHANCE
    pets_mod.PET_ENCOUNTER_CHANCE = 1.0
    try:
        seen = None
        for _ in range(12):
            c.adventure_cd_until = 0.0
            res = AdventureEngine.explore(c, "野外", use_ai=False)
            assert res.get("success"), res
            if res.get("pet_encounter"):
                seen = res["pet_encounter"]
                break
            if c.pending_pet_species:
                seen = c.pending_pet_species
                break
        assert seen and c.pending_pet_species == seen
    finally:
        pets_mod.PET_ENCOUNTER_CHANCE = old_chance
    print("✓ 探险钩子：成功结算后灵兽现踪并写入待契约")


def test_owner_death_marks_pets_dead():
    c = _char(stones=9999)
    p1 = _contract(c, "青鳞蟒")
    PetEngine.deploy(c, p1.name)
    c.pending_pet_species = "玄甲龟"
    PetEngine.on_owner_death(c)
    assert p1.state == "dead" and p1.active is False
    assert c.pending_pet_species == ""
    # 已殁灵宠不可再操作
    assert not PetEngine.deploy(c, p1.name)["success"]
    assert not PetEngine.feed(c, p1.name)["success"]
    panel = PetEngine.panel_text(c)
    assert "已殁" in panel
    print("✓ 主人死亡：灵宠殁、出战清零、待契约散去、不可再操作")


def test_old_save_without_pets_fields():
    c = _char()
    data = c.model_dump()
    data.pop("pets")
    data.pop("pending_pet_species")
    revived = Character.model_validate(data)
    assert revived.pets == [] and revived.pending_pet_species == ""
    # 新档 JSON 往返
    again = Character.model_validate(c.model_dump())
    assert again.pets == []
    print("✓ 旧档兼容：无 pets 字段的角色 JSON 可反序列化")


def test_world_handle_pet_commands():
    from storage.db import init_db, CharacterRepository
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    r = w.join("灵宠链路客")
    tok = r["token"]
    char = w.get_char(tok)
    char.spirit_stones = 999
    char.pending_pet_species = "青鳞蟒"
    CharacterRepository.save(char)

    res = w.handle(tok, "/契约 青鳞蟒")
    assert res.get("ok"), res
    res = w.handle(tok, "/灵宠")
    assert res.get("ok") and "青鳞蟒" in (res.get("text") or "")
    res = w.handle(tok, "/喂养 青鳞蟒")
    assert res.get("ok"), res
    res = w.handle(tok, "/出战 青鳞蟒")
    assert res.get("ok"), res
    st = res.get("status") or {}
    assert st.get("pet", {}).get("name") == "青鳞蟒", st.get("pet")
    assert st.get("pets_count") == 1
    res = w.handle(tok, "/休息 青鳞蟒")
    assert res.get("ok") and (res.get("status") or {}).get("pet") is None
    res = w.handle(tok, "/放生 青鳞蟒")
    assert res.get("ok"), res
    res = w.handle(tok, "/灵宠")
    assert "尚未养有灵宠" in (res.get("text") or "")
    print("✓ World.handle 全链路：契约/面板/喂养/出战/status/休息/放生")
