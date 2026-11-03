"""F02 心法槽位：装配/互斥/上限/冷却/卸功/修炼与斗法加成/旧档兼容/双端全链路"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

import copy
import random

from core.clock import WorldClock
from core.models import Character, CharacterStatus
from core.combat import CombatEngine
from core.art_slots import (
    ArtSlotEngine,
    ART_MAIN_MEDITATION_BONUS,
    ART_SLOT_COOLDOWN_SECONDS,
    ART_SUB_MAX,
    ART_SUB_POWER_BONUS_CAP,
    ART_SUB_POWER_BONUS_EACH,
)
from server.world import WORLD

WORLD.stop_tick()

T0 = 1_700_000_000.0  # 固定时间锚（冷却用注入 now，不 sleep）


def _uniq(base: str) -> str:
    return f"arts{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _char(name="心法客", skills=None):
    c = WorldClock.create_new_character(_uniq("u_"), _uniq(name))
    if skills is not None:
        c.skills = list(skills)
    return c


# ---------------- 旧档兼容 ----------------

def test_legacy_character_defaults_empty_slots():
    c = _char()
    data = c.model_dump()
    for k in ("main_art", "sub_arts", "art_slot_changed_at"):
        data.pop(k, None)
    old = Character.model_validate(data)  # 旧档 JSON 无新字段
    assert old.main_art == "" and old.sub_arts == [] and old.art_slot_changed_at == 0.0
    assert ArtSlotEngine.meditation_mult(old) == 1.0
    assert ArtSlotEngine.power_bonus(old) == 1.0
    print("✓ 旧档反序列化默认空槽，加成因子恒 1.0")


# ---------------- 装配规则 ----------------

def test_equip_unlearned_rejected():
    c = _char()
    r = ArtSlotEngine.set_main(c, "九天玄功", now=T0)
    assert not r["success"] and "未习得" in r["message"]
    assert c.main_art == "" and c.art_slot_changed_at == 0.0  # 失败零副作用
    r = ArtSlotEngine.add_sub(c, "九天玄功", now=T0)
    assert not r["success"]
    print("✓ 未习得功法装配被拒且无副作用")


def test_fuzzy_ambiguity_rejected():
    c = _char(skills=["御剑术", "御剑诀", "吐纳术"])
    r = ArtSlotEngine.set_main(c, "御剑", now=T0)
    assert not r["success"] and "多门功法" in r["message"]
    r = ArtSlotEngine.set_main(c, "御剑诀", now=T0)
    assert r["success"] and c.main_art == "御剑诀"
    print("✓ 子串多义报错、全名可装配")


def test_main_uniqueness_and_sub_moves_to_main():
    c = _char()
    assert ArtSlotEngine.set_main(c, "御剑术", now=T0)["success"]
    r = ArtSlotEngine.set_main(c, "御剑术", now=T0 + ART_SLOT_COOLDOWN_SECONDS + 1)
    assert not r["success"] and "已是主修" in r["message"]
    # 吐纳术先入辅修，冷却后扶正为主修：应自动移出辅修（槽位互斥单点维护）
    t1 = T0 + ART_SLOT_COOLDOWN_SECONDS + 1
    assert ArtSlotEngine.add_sub(c, "吐纳术", now=t1)["success"]
    t2 = t1 + ART_SLOT_COOLDOWN_SECONDS + 1
    r = ArtSlotEngine.set_main(c, "吐纳术", now=t2)
    assert r["success"] and c.main_art == "吐纳术" and c.sub_arts == []
    print("✓ 主修唯一、重复设主修拒绝、辅修扶正自动移槽")


def test_sub_cap_and_conflicts():
    c = _char(skills=["吐纳术", "御剑术", "裂空诀", "焚天功"])
    assert ArtSlotEngine.set_main(c, "吐纳术", now=T0)["success"]
    t = T0
    for name in ("御剑术", "裂空诀"):
        t += ART_SLOT_COOLDOWN_SECONDS + 1
        assert ArtSlotEngine.add_sub(c, name, now=t)["success"], name
    assert len(c.sub_arts) == ART_SUB_MAX
    t += ART_SLOT_COOLDOWN_SECONDS + 1
    r = ArtSlotEngine.add_sub(c, "焚天功", now=t)
    assert not r["success"] and "已满" in r["message"]
    r = ArtSlotEngine.add_sub(c, "吐纳术", now=t)
    assert not r["success"] and "主修" in r["message"]
    r = ArtSlotEngine.add_sub(c, "御剑术", now=t)
    assert not r["success"] and "已在辅修" in r["message"]
    print("✓ 辅修上限 2、主修冲突、重复装配均拒绝")


def test_cooldown_blocks_then_expires():
    c = _char()
    assert ArtSlotEngine.set_main(c, "御剑术", now=T0)["success"]  # 首次免冷却
    r = ArtSlotEngine.add_sub(c, "吐纳术", now=T0 + 60)
    assert not r["success"] and "心法未稳" in r["message"]
    assert c.sub_arts == []  # 冷却拦截零副作用
    r = ArtSlotEngine.remove(c, "御剑术", now=T0 + 60)
    assert not r["success"]
    r = ArtSlotEngine.add_sub(c, "吐纳术", now=T0 + ART_SLOT_COOLDOWN_SECONDS + 1)
    assert r["success"]
    print("✓ 冷却拦截装配与卸功、到期后可再调整")


def test_remove_slots():
    c = _char()
    assert ArtSlotEngine.set_main(c, "御剑术", now=T0)["success"]
    t1 = T0 + ART_SLOT_COOLDOWN_SECONDS + 1
    assert ArtSlotEngine.add_sub(c, "吐纳术", now=t1)["success"]
    t2 = t1 + ART_SLOT_COOLDOWN_SECONDS + 1
    r = ArtSlotEngine.remove(c, "吐纳术", now=t2)
    assert r["success"] and c.sub_arts == [] and c.main_art == "御剑术"
    t3 = t2 + ART_SLOT_COOLDOWN_SECONDS + 1
    r = ArtSlotEngine.remove(c, "御剑术", now=t3)
    assert r["success"] and c.main_art == ""
    t4 = t3 + ART_SLOT_COOLDOWN_SECONDS + 1
    r = ArtSlotEngine.remove(c, "御剑术", now=t4)
    assert not r["success"] and "未装配" in r["message"]
    print("✓ 卸功主修/辅修生效、未装配卸功报错")


def test_dead_character_rejected():
    c = _char()
    c.status = CharacterStatus.DEAD
    assert not ArtSlotEngine.set_main(c, "御剑术", now=T0)["success"]
    assert not ArtSlotEngine.add_sub(c, "御剑术", now=T0)["success"]
    assert not ArtSlotEngine.remove(c, "御剑术", now=T0)["success"]
    print("✓ 死亡角色心法操作全拒")


# ---------------- 加成数值 ----------------

def test_power_bonus_and_cap():
    c = _char(skills=["吐纳术", "御剑术", "裂空诀", "焚天功"])
    p0 = CombatEngine.calculate_power(c)
    c.sub_arts = ["御剑术"]
    p1 = CombatEngine.calculate_power(c)
    assert abs(p1 / p0 - (1.0 + ART_SUB_POWER_BONUS_EACH)) < 1e-9, (p0, p1)
    c.sub_arts = ["御剑术", "裂空诀"]
    p2 = CombatEngine.calculate_power(c)
    assert abs(p2 / p0 - (1.0 + ART_SUB_POWER_BONUS_CAP)) < 1e-9
    c.sub_arts = ["御剑术", "裂空诀", "焚天功"]  # 脏数据三门也只到封顶
    p3 = CombatEngine.calculate_power(c)
    assert abs(p3 / p0 - (1.0 + ART_SUB_POWER_BONUS_CAP)) < 1e-9
    c.sub_arts = []
    c.main_art = "吐纳术"  # 主修不给斗法加成
    assert abs(CombatEngine.calculate_power(c) / p0 - 1.0) < 1e-9
    print("✓ 斗法辅修 +3%/门、+6% 封顶、主修不影响战力")


def _settle_gain(c_snapshot, with_main: bool) -> float:
    """同一角色快照、同一随机种子下结算一次闭关，返回 exp_gained"""
    c = Character.model_validate(copy.deepcopy(c_snapshot))
    if with_main:
        c.main_art = "吐纳术"
    start = WorldClock.start_meditation(c, hours_planned=2.0, stones_to_pledge=0)
    assert start["success"], start
    random.seed(20261104)
    res = WorldClock.settle_meditation(c, force_interrupt=False, now=time.time() + 7200.0)
    assert res["success"], res
    return float(res["exp_gained"])


def test_meditation_main_bonus_numeric():
    c = _char()
    snap = c.model_dump()
    g0 = _settle_gain(snap, with_main=False)
    g1 = _settle_gain(snap, with_main=True)
    assert g0 > 0
    ratio = g1 / g0
    assert abs(ratio - (1.0 + ART_MAIN_MEDITATION_BONUS)) < 0.02, (g0, g1, ratio)
    print(f"✓ 闭关主修加成数值生效：无主修 {g0:.1f} → 主修 {g1:.1f}（×{ratio:.3f}）")


def test_unarmed_slots_old_behavior():
    """未装配时引擎因子恒等 1.0，且 power 与无槽位字段角色一致"""
    c = _char()
    assert ArtSlotEngine.meditation_mult(c) == 1.0
    assert ArtSlotEngine.power_bonus(c) == 1.0
    panel = ArtSlotEngine.panel_text(c)
    assert "主修：（空）" in panel and "吐纳术" in panel
    print("✓ 未装配面板与因子均为旧行为")


# ---------------- 双端全链路 ----------------

def test_world_handle_arts_chain():
    from storage.db import init_db, CharacterRepository
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    r = w.join(_uniq("心法链路客"))
    tok = r["token"]
    res = w.handle(tok, "/心法")
    assert res.get("ok") and "心法槽位" in (res.get("text") or "")
    assert (res.get("status") or {}).get("arts") == {"main": "", "sub": []}
    res = w.handle(tok, "/主修 御剑术")
    assert res.get("ok"), res
    assert (res.get("status") or {}).get("arts", {}).get("main") == "御剑术"
    # 紧接着装辅修应被冷却拦截（handle 层透传引擎裁决）
    res = w.handle(tok, "/辅修 吐纳术")
    assert not res.get("ok") and "心法未稳" in (res.get("text") or res.get("error") or "")
    # 把冷却时间戳拨回过去后可继续全链路
    char = w.get_char(tok)
    char.art_slot_changed_at = time.time() - ART_SLOT_COOLDOWN_SECONDS - 5
    CharacterRepository.save(char)
    res = w.handle(tok, "/辅修 吐纳术")
    assert res.get("ok"), res
    char = w.get_char(tok)
    char.art_slot_changed_at = time.time() - ART_SLOT_COOLDOWN_SECONDS - 5
    CharacterRepository.save(char)
    res = w.handle(tok, "/卸功 吐纳术")
    assert res.get("ok"), res
    assert (res.get("status") or {}).get("arts") == {"main": "御剑术", "sub": []}
    res = w.handle(tok, "/主修 不存在的功法")
    assert not res.get("ok")
    print("✓ World.handle 全链路：面板/主修/冷却/辅修/卸功/status.arts")


def test_cli_engine_chain():
    """CLI 与 LAN 共用同一引擎与存档语义：直接以 CLI 的调用方式验证一轮"""
    c = _char()
    assert ArtSlotEngine.set_main(c, "吐纳术", now=T0)["success"]
    assert ArtSlotEngine.panel_text(c, now=T0).count("主修：吐纳术") == 1
    t1 = T0 + ART_SLOT_COOLDOWN_SECONDS + 1
    assert ArtSlotEngine.add_sub(c, "御剑术", now=t1)["success"]
    # 序列化往返（CLI 读档路径与 LAN 同一 CharacterRepository JSON 结构）
    back = Character.model_validate(copy.deepcopy(c.model_dump()))
    assert back.main_art == "吐纳术" and back.sub_arts == ["御剑术"]
    assert ArtSlotEngine.meditation_mult(back) == 1.0 + ART_MAIN_MEDITATION_BONUS
    print("✓ CLI 同引擎链路与存档往返一致")
