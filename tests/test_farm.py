"""F06 灵田/洞府经营：开辟/播种/生长/收获/闭关加成/升级/死亡/旧档兼容/双端链路"""
import copy
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core.clock import WorldClock
from core.models import Character, CharacterStatus
from core.farm import (
    FarmEngine,
    meditation_mult,
    plots_capacity,
    split_sow_args,
    CAVE_MAX_LEVEL,
    CAVE_OPEN_COST,
    CAVE_UPGRADE_COST,
    CAVE_WITHER_SECONDS,
    FARM_CROPS,
)
from server.world import WORLD

WORLD.stop_tick()

T0 = 1_800_000_000.0  # 固定时间锚（注入 now 用）


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time()) % 100000}"


def _char(name="耕道者", stones=2000):
    c = WorldClock.create_new_character(f"farm_{name}", name)
    c.spirit_stones = stones
    return c


def _open(c, now=T0):
    res = FarmEngine.open_cave(c, now=now)
    assert res["success"], res
    return res


class _MaxRng:
    """产量掷骰桩：恒取区间上界（确定性断言用）"""

    def randint(self, a, b):
        return b


# ---------------- 开辟 ----------------

def test_open_cave_success_cost_and_plots():
    c = _char()
    s0 = c.spirit_stones
    res = _open(c)
    assert c.cave_level == 1
    assert c.spirit_stones == s0 - CAVE_OPEN_COST
    assert plots_capacity(c) == 2 and len(c.farm_plots) == 2
    assert all(not p.crop for p in c.farm_plots)
    # 重复开辟拒绝且不扣费
    res2 = FarmEngine.open_cave(c, now=T0)
    assert not res2["success"] and c.spirit_stones == s0 - CAVE_OPEN_COST
    print("✓ 开辟成功：扣 300、1 级、2 块地；重复开辟拒绝")


def test_open_cave_insufficient_stones():
    c = _char(stones=CAVE_OPEN_COST - 1)
    res = FarmEngine.open_cave(c, now=T0)
    assert not res["success"] and "灵石" in res["message"]
    assert c.cave_level == 0 and c.spirit_stones == CAVE_OPEN_COST - 1
    print("✓ 开辟灵石不足：拒绝且不扣费")


def test_open_cave_requires_safe_location():
    c = _char()
    # 找一个非安全地点（冲突/野外）
    from config import WORLD_LOCATIONS

    unsafe = next(n for n, v in WORLD_LOCATIONS.items() if not v.get("is_safe"))
    c.location = unsafe
    res = FarmEngine.open_cave(c, now=T0)
    assert not res["success"] and "安全" in res["message"]
    assert c.cave_level == 0
    print(f"✓ 开辟限定安全区：{unsafe} 被拒")


# ---------------- 播种 ----------------

def test_sow_requires_cave_and_seed():
    c = _char()
    res = FarmEngine.sow(c, "聚灵草种子", now=T0)
    assert not res["success"]  # 无洞府
    _open(c)
    res = FarmEngine.sow(c, "聚灵草种子", now=T0)
    assert not res["success"] and "并无" in res["message"]  # 无种子
    c.inventory.append("聚气丹")
    res = FarmEngine.sow(c, "聚气丹", now=T0)
    assert not res["success"] and "不是可播种" in res["message"]  # 不可种
    assert "聚气丹" in c.inventory  # 失败不消耗
    print("✓ 播种前置：无洞府/无种子/不可种物品均拒绝且不消耗")


def test_sow_consumes_seed_and_sets_maturity():
    c = _char()
    _open(c)
    c.inventory += ["聚灵草种子", "聚灵草种子"]
    res = FarmEngine.sow(c, "聚灵草种子", now=T0)
    assert res["success"] and res["sown"] == 1
    assert c.inventory.count("聚灵草种子") == 1
    p = c.farm_plots[0]
    assert p.crop == "聚灵草种子" and p.planted_at == T0
    assert p.matures_at == T0 + FARM_CROPS["聚灵草种子"]["grow_seconds"]
    print("✓ 播种：耗种 1 颗、成熟时间 = 种下 + 生长时长")


def test_sow_partial_when_land_or_seed_short():
    c = _char()
    _open(c)  # 2 块地
    c.inventory += ["灵谷种子"] * 5
    res = FarmEngine.sow(c, "灵谷种子", count=5, now=T0)
    assert res["success"] and res["sown"] == 2  # 空地不足 → 部分成功
    assert c.inventory.count("灵谷种子") == 3
    res2 = FarmEngine.sow(c, "灵谷种子", now=T0)
    assert not res2["success"]  # 无空地
    print("✓ 批量播种：空地不足时部分成功并明示，无空地拒绝")


def test_split_sow_args():
    assert split_sow_args(["聚灵草种子"]) == ("聚灵草种子", 1)
    assert split_sow_args(["聚灵草种子", "3"]) == ("聚灵草种子", 3)
    assert split_sow_args(["聚灵草种子", "x"]) == ("聚灵草种子 x", 1)
    assert split_sow_args(["聚灵草种子", "0"]) == ("聚灵草种子 0", 1)  # 0 不拆
    # Unicode 数字：isdigit 为真但不可 int()，不得抛错（评审 M1 回归）
    assert split_sow_args(["灵谷种子", "²"]) == ("灵谷种子 ²", 1)
    assert split_sow_args(["灵谷种子", "①"]) == ("灵谷种子 ①", 1)
    print("✓ 播种参数解析：末尾正整数才拆作数量，Unicode 数字不崩")


def test_sow_ambiguous_hint_rejected():
    c = _char()
    _open(c)
    c.inventory += ["聚灵草种子", "灵谷种子"]
    res = FarmEngine.sow(c, "种子", now=T0)  # 泛词同时相合两种种子
    assert not res["success"] and "不止一种" in res["message"]
    assert c.inventory.count("聚灵草种子") == 1 and c.inventory.count("灵谷种子") == 1
    assert all(not p.crop for p in c.farm_plots)  # 未误种
    # 写全名仍可播；单一种子相合的简称可播
    assert FarmEngine.sow(c, "灵谷种子", now=T0)["success"]
    print("✓ 播种多义防误种：泛词拒绝并列候选，全名/唯一简称可播")


def test_dirty_cave_level_capped():
    c = _char()
    c.cave_level = 5  # 脏数据（超封顶）
    assert plots_capacity(c) == 6
    assert abs(meditation_mult(c) - 1.05) < 1e-12
    assert not FarmEngine.upgrade_cave(c, now=T0)["success"]
    st = FarmEngine.cave_summary(c, now=T0)
    assert st["plots_total"] == 6
    print("✓ 脏数据：cave_level 超封顶时容量/加成按 3 级口径钳制")


# ---------------- 收获 ----------------

def test_harvest_immature_rejected_then_mature_yields():
    c = _char()
    _open(c)
    c.inventory.append("灵谷种子")
    FarmEngine.sow(c, "灵谷种子", now=T0)
    res = FarmEngine.harvest(c, now=T0 + 60)
    assert not res["success"] and "尚无成熟" in res["message"]
    assert c.farm_plots[0].crop == "灵谷种子"  # 未收不清空
    grow = FARM_CROPS["灵谷种子"]["grow_seconds"]
    res = FarmEngine.harvest(c, now=T0 + grow + 1, rng=_MaxRng())
    assert res["success"], res
    assert res["gained"] == {"灵谷": FARM_CROPS["灵谷种子"]["yield_max"]}
    assert c.inventory.count("灵谷") == FARM_CROPS["灵谷种子"]["yield_max"]
    assert c.farm_plots[0].crop == ""  # 收后地块清空
    print("✓ 收获：未成熟拒绝，成熟按产量入囊并清地")


def test_harvest_yield_within_range():
    c = _char()
    _open(c)
    c.inventory += ["聚灵草种子", "聚灵草种子"]
    FarmEngine.sow(c, "聚灵草种子", count=2, now=T0)
    grow = FARM_CROPS["聚灵草种子"]["grow_seconds"]
    res = FarmEngine.harvest(c, now=T0 + grow + 1, rng=random.Random(7))
    lo, hi = FARM_CROPS["聚灵草种子"]["yield_min"], FARM_CROPS["聚灵草种子"]["yield_max"]
    assert res["success"] and lo * 2 <= res["gained"]["聚灵草"] <= hi * 2
    print("✓ 收获产量落在作物区间内（两块合计）")


def test_harvest_overripe_reduces_yield():
    c = _char()
    _open(c)
    c.inventory.append("灵芝种子")
    FarmEngine.sow(c, "灵芝种子", now=T0)
    grow = FARM_CROPS["灵芝种子"]["grow_seconds"]
    late = T0 + grow + CAVE_WITHER_SECONDS + 10
    res = FarmEngine.harvest(c, now=late, rng=_MaxRng())
    expect = max(1, FARM_CROPS["灵芝种子"]["yield_max"] - 1)
    assert res["success"] and res["gained"] == {"百年灵芝": expect}
    assert "过熟" in res["message"]
    print("✓ 过熟减产：成熟后超 24h 产量 -1（下限 1）并标注")


# ---------------- 闭关加成 ----------------

def test_meditation_mult_values():
    c = _char()
    assert meditation_mult(c) == 1.0
    c.cave_level = 1
    assert abs(meditation_mult(c) - 1.02) < 1e-12
    c.cave_level = 2
    assert abs(meditation_mult(c) - 1.04) < 1e-12
    c.cave_level = 3
    assert abs(meditation_mult(c) - 1.05) < 1e-12
    print("✓ 洞府加成乘子：无洞府 1.0 / 1 级 1.02 / 2 级 1.04 / 3 级 1.05 封顶")


def _settle_gain(snapshot, mutate):
    c = Character.model_validate(copy.deepcopy(snapshot))
    mutate(c)
    c.realm.tier = 4  # 提高境界使 max_exp 足够大，防修为封顶扭曲倍率（各变体同口径）
    start = WorldClock.start_meditation(c, hours_planned=2.0, stones_to_pledge=0)
    assert start["success"], start
    random.seed(20261104)
    res = WorldClock.settle_meditation(c, force_interrupt=False, now=time.time() + 7200.0)
    assert res["success"], res
    return float(res["exp_gained"])


def test_settle_meditation_cave_bonus_and_chain():
    base = _char()
    snap = base.model_dump()
    g_none = _settle_gain(snap, lambda c: None)
    g_cave1 = _settle_gain(snap, lambda c: setattr(c, "cave_level", 1))
    g_cave3 = _settle_gain(snap, lambda c: setattr(c, "cave_level", 3))
    g_main = _settle_gain(snap, lambda c: setattr(c, "main_art", "吐纳术"))
    g_both = _settle_gain(
        snap, lambda c: (setattr(c, "main_art", "吐纳术"), setattr(c, "cave_level", 3))
    )
    assert g_none > 0
    assert abs(g_cave1 / g_none - 1.02) < 0.03, (g_none, g_cave1)
    assert abs(g_cave3 / g_none - 1.05) < 0.03, (g_none, g_cave3)
    # 与心法主修连乘口径：1.10 × 1.05 = 1.155（非叠加相加）
    assert abs(g_main / g_none - 1.10) < 0.03, (g_none, g_main)
    assert abs(g_both / g_none - 1.155) < 0.04, (g_none, g_both)
    print("✓ 闭关结算：洞府 +2%/+5% 生效；与心法主修按连乘 1.10×1.05 叠加")


# ---------------- 升级 ----------------

def test_upgrade_costs_plots_and_cap():
    c = _char(stones=5000)
    _open(c)
    res = FarmEngine.upgrade_cave(c, now=T0)
    assert res["success"] and c.cave_level == 2
    assert c.spirit_stones == 5000 - CAVE_OPEN_COST - CAVE_UPGRADE_COST[2]
    assert plots_capacity(c) == 4 and len(c.farm_plots) == 4
    res = FarmEngine.upgrade_cave(c, now=T0)
    assert res["success"] and c.cave_level == 3
    assert c.spirit_stones == 5000 - CAVE_OPEN_COST - CAVE_UPGRADE_COST[2] - CAVE_UPGRADE_COST[3]
    assert plots_capacity(c) == 6
    res = FarmEngine.upgrade_cave(c, now=T0)
    assert not res["success"] and "圆满" in res["message"]  # 满级拒绝
    print("✓ 升级：成本 500/900 递增、地块 2→4→6、满级拒绝")


def test_upgrade_keeps_crops_and_insufficient():
    c = _char(stones=1000)
    _open(c)  # 余 700
    c.inventory.append("灵谷种子")
    FarmEngine.sow(c, "灵谷种子", now=T0)
    res = FarmEngine.upgrade_cave(c, now=T0)  # 升 2 级需 500，余 200
    assert res["success"]
    assert c.farm_plots[0].crop == "灵谷种子"  # 升级保留已有作物
    res = FarmEngine.upgrade_cave(c, now=T0)  # 升 3 级需 900，灵石不足
    assert not res["success"] and c.cave_level == 2
    print("✓ 升级保留在种作物；灵石不足拒绝")


# ---------------- 死亡 / 门禁 / 兼容 ----------------

def test_death_wastes_farm_and_new_life_has_no_cave():
    c = _char()
    _open(c)
    c.inventory.append("灵谷种子")
    FarmEngine.sow(c, "灵谷种子", now=T0)
    FarmEngine.on_owner_death(c)
    assert c.cave_level == 1  # 遗容保留等级
    assert all(not p.crop for p in c.farm_plots)  # 作物荒废
    new = WorldClock.create_new_character(f"farm_newlife_{_uniq('x')}", "转世者")
    assert new.cave_level == 0 and new.farm_plots == []
    print("✓ 死亡：灵田荒废（等级留遗容）；新世角色无洞府")


def test_dead_and_meditating_guards():
    c = _char()
    _open(c)
    c.inventory.append("灵谷种子")
    c.status = CharacterStatus.MEDITATING
    assert not FarmEngine.sow(c, "灵谷种子", now=T0)["success"]
    assert not FarmEngine.harvest(c, now=T0)["success"]
    assert not FarmEngine.upgrade_cave(c, now=T0)["success"]
    assert "洞府灵田" in FarmEngine.panel_text(c, now=T0)  # 查看放行
    c.status = CharacterStatus.DEAD
    assert not FarmEngine.sow(c, "灵谷种子", now=T0)["success"]
    assert not FarmEngine.open_cave(c, now=T0)["success"]
    assert "荒废" in FarmEngine.panel_text(c, now=T0)  # 遗容可看
    print("✓ 门禁：闭关/死亡管理类拒绝，查看放行（死亡为荒废遗容）")


def test_old_save_compat():
    c = _char()
    data = c.model_dump()
    data.pop("cave_level")
    data.pop("farm_plots")
    revived = Character.model_validate(data)
    assert revived.cave_level == 0 and revived.farm_plots == []
    assert meditation_mult(revived) == 1.0
    # 带洞府存档往返
    _open(c)
    c.inventory.append("灵谷种子")
    FarmEngine.sow(c, "灵谷种子", now=T0)
    again = Character.model_validate(c.model_dump())
    assert again.cave_level == 1 and again.farm_plots[0].crop == "灵谷种子"
    print("✓ 旧档兼容：无 cave 字段可反序列化；带洞府往返不丢作物")


# ---------------- 双端链路 ----------------

def test_world_handle_farm_chain():
    from storage.db import init_db, CharacterRepository
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    r = w.join(_uniq("洞府链路客"))
    tok = r["token"]
    char = w.get_char(tok)
    char.spirit_stones = 2000
    CharacterRepository.save(char)

    res = w.handle(tok, "/购买 灵谷种子 2")
    assert res.get("ok"), res  # 种子经坊市入囊（目录集成）
    res = w.handle(tok, "/开辟")
    assert res.get("ok"), res
    st = res.get("status") or {}
    assert (st.get("cave") or {}).get("level") == 1, st.get("cave")
    res = w.handle(tok, "/播种 灵谷种子 2")
    assert res.get("ok"), res
    res = w.handle(tok, "/收获")
    assert not res.get("ok")  # 未成熟
    # 注入成熟时间后收获（惰性结算）
    char = w.get_char(tok)
    for p in char.farm_plots:
        if p.crop:
            p.matures_at = time.time() - 1
    CharacterRepository.save(char)
    res = w.handle(tok, "/收获")
    assert res.get("ok"), res
    char = w.get_char(tok)
    assert char.inventory.count("灵谷") >= 2
    res = w.handle(tok, "/洞府")
    assert res.get("ok") and "洞府灵田" in (res.get("text") or "")
    res = w.handle(tok, "/升级洞府")
    assert res.get("ok") and (res.get("status") or {}).get("cave", {}).get("level") == 2
    print("✓ World.handle 全链路：购买种子/开辟/播种/收获/面板/升级 + status.cave")


def test_world_handle_meditation_gate():
    from storage.db import init_db, CharacterRepository
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    r = w.join(_uniq("洞府闭关客"))
    tok = r["token"]
    char = w.get_char(tok)
    char.spirit_stones = 2000
    CharacterRepository.save(char)
    assert w.handle(tok, "/开辟").get("ok")
    char = w.get_char(tok)
    char.inventory.append("灵谷种子")
    start = w.handle(tok, "/闭关 1")
    assert start.get("ok"), start
    res = w.handle(tok, "/洞府")
    assert res.get("ok"), res  # 查看在白名单
    res = w.handle(tok, "/播种 灵谷种子")
    assert not res.get("ok") and "闭关锁门" in (res.get("error") or res.get("text") or "")
    res = w.handle(tok, "/收获")
    assert not res.get("ok")
    print("✓ 闭关门禁：/洞府 查看放行，播种/收获锁门")


def test_cli_source_parity():
    root = Path(__file__).resolve().parent.parent
    cli = (root / "cli" / "main.py").read_text(encoding="utf-8")
    srv = (root / "server" / "world.py").read_text(encoding="utf-8")
    for cmd in ("/洞府", "/开辟", "/播种", "/收获", "/升级洞府"):
        assert cmd in cli and cmd in srv, cmd
    print("✓ 双端源码对齐：五指令在 CLI 与 server 均有接入")
