"""F10 炼体/炼神双修：消耗/升层/战力/寿元封顶/有效道心判定点/神识/零扣费/上限/共存封顶/双端链路/旧档兼容"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import SECONDS_PER_GAME_YEAR
from core.clock import WorldClock
from core.models import (
    Character, CharacterStatus, Element, RootType, SpiritualRoot, SpiritPet,
)
from core.combat import CombatEngine
from core.body_soul import (
    BodySoulEngine,
    BODY_ITEM, SOUL_ITEM,
    BODY_MAX_LEVEL, SOUL_MAX_LEVEL,
    BODY_POWER_CAP, BODY_LIFESPAN_PER_LEVEL, BODY_LIFESPAN_TOTAL_CAP,
    SOUL_DAO_HEART_CAP, SOUL_SENSE_PER_LEVEL,
    material_count_for, next_cost,
)
from server.world import WORLD

WORLD.stop_tick()


def _uniq(base: str) -> str:
    return f"bs{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _char(name="副修客"):
    return WorldClock.create_new_character(_uniq("u_"), _uniq(name))


def _stock(c, body_items=0, soul_items=0, stones=0):
    c.inventory = [BODY_ITEM] * body_items + [SOUL_ITEM] * soul_items
    c.spirit_stones = stones
    return c


# ---------------- 旧档兼容 / 未修炼 = 旧行为 ----------------

def test_legacy_character_defaults_and_neutral_factors():
    c = _char()
    data = c.model_dump()
    for k in ("body_level", "soul_level"):
        data.pop(k, None)
    old = Character.model_validate(data)  # 旧档 JSON 无新字段
    assert old.body_level == 0 and old.soul_level == 0
    assert BodySoulEngine.power_bonus(old) == 1.0
    assert BodySoulEngine.sense_bonus(old) == 0
    assert BodySoulEngine.dao_heart_bonus(old) == 0
    assert BodySoulEngine.effective_dao_heart(old) == old.karma.dao_heart
    print("✓ 旧档反序列化默认 0 层，各因子恒旧行为")


def test_cost_table_shape():
    # 材料分段：1,1,1,2,2,2,3,3,3,4 → 满层共 22
    assert [material_count_for(L) for L in range(1, 11)] == [1, 1, 1, 2, 2, 2, 3, 3, 3, 4]
    assert sum(material_count_for(L) for L in range(1, 11)) == 22
    assert next_cost("body", 0) == {"item": BODY_ITEM, "item_count": 1, "stones": 20}
    assert next_cost("soul", 9) == {"item": SOUL_ITEM, "item_count": 4, "stones": 150}
    assert next_cost("body", BODY_MAX_LEVEL) is None
    assert next_cost("soul", SOUL_MAX_LEVEL) is None
    print("✓ 成本表：材料分段 22 枚满层，满层无下一层成本")


# ---------------- 炼体：消耗与战力 ----------------

def test_body_train_consumes_and_levels():
    c = _stock(_char(), body_items=5, stones=1000)
    res = BodySoulEngine.train_body(c, 1)
    assert res["success"] and res["levels_gained"] == 1
    assert c.body_level == 1
    assert c.inventory.count(BODY_ITEM) == 4          # L1 耗内丹 1
    assert c.spirit_stones == 1000 - 20                # L1 耗灵石 20
    res = BodySoulEngine.train_body(c, 3)              # L2:1/40, L3:1/60, L4:2/80 → 恰好三层全过
    assert res["success"] and res["levels_gained"] == 3
    assert c.body_level == 4
    assert c.inventory.count(BODY_ITEM) == 0
    assert c.spirit_stones == 1000 - 20 - 40 - 60 - 80
    # 再炼一层：L5 需内丹 2、现有 0 → 失败零扣费
    res = BodySoulEngine.train_body(c, 1)
    assert not res["success"] and c.body_level == 4 and c.spirit_stones == 800
    print("✓ 炼体逐层精确扣费；批量逐层校验，材料见底即停且零扣费")


def test_body_power_scales_and_caps():
    c = _char()
    p0 = CombatEngine.calculate_power(c)
    c.body_level = 3
    p3 = CombatEngine.calculate_power(c)
    assert abs(p3 / p0 - 1.03) < 1e-9, (p0, p3)
    c.body_level = BODY_MAX_LEVEL
    p10 = CombatEngine.calculate_power(c)
    assert abs(p10 / p0 - (1.0 + BODY_POWER_CAP)) < 1e-9
    c.body_level = 99  # 脏数据：读取钳制，不超发
    assert BodySoulEngine.power_bonus(c) == 1.0 + BODY_POWER_CAP
    assert abs(CombatEngine.calculate_power(c) / p0 - 1.10) < 1e-9
    print("✓ 炼体战力 +1%/层、满层恰 +10%，脏层数钳制不超发")


def test_body_lifespan_gain_and_total_cap():
    c = _stock(_char(), body_items=30, stones=5000)
    death0 = c.lifespan.death_timestamp
    gain0 = c.lifespan.accumulated_gain
    res = BodySoulEngine.train_body(c, BODY_MAX_LEVEL)
    assert res["success"] and c.body_level == BODY_MAX_LEVEL
    delta_years = (c.lifespan.death_timestamp - death0) / SECONDS_PER_GAME_YEAR
    assert BODY_LIFESPAN_TOTAL_CAP == 10.0  # 常量一致性钉死（防误改常量静默改口径）
    assert abs(delta_years - 10.0) < 1e-6, delta_years
    assert abs((c.lifespan.accumulated_gain - gain0) - 10.0) < 1e-6
    # 满层再炼：拒绝且寿元不动
    death1 = c.lifespan.death_timestamp
    res = BodySoulEngine.train_body(c, 1)
    assert not res["success"] and "圆满" in res["message"]
    assert c.lifespan.death_timestamp == death1
    # 逐层口径：单层恰 +1 岁
    c2 = _stock(_char(), body_items=3, stones=500)
    d0 = c2.lifespan.death_timestamp
    BodySoulEngine.train_body(c2, 1)
    assert abs((c2.lifespan.death_timestamp - d0) / SECONDS_PER_GAME_YEAR
               - BODY_LIFESPAN_PER_LEVEL) < 1e-6
    print("✓ 炼体增寿 +1 岁/层、满层总量恰 +10 岁封顶，满层拒炼不发寿")


# ---------------- 资源不足零扣费 ----------------

def test_insufficient_resources_zero_charge():
    c = _stock(_char(), body_items=0, soul_items=0, stones=0)
    snap = (list(c.inventory), c.spirit_stones, c.body_level, c.soul_level,
            c.lifespan.death_timestamp)
    assert not BodySoulEngine.train_body(c, 1)["success"]
    assert not BodySoulEngine.train_soul(c, 1)["success"]
    assert (list(c.inventory), c.spirit_stones, c.body_level, c.soul_level,
            c.lifespan.death_timestamp) == snap
    # 有材料无灵石：同样零扣费（材料不被吞）
    c2 = _stock(_char(), body_items=5, stones=10)
    assert not BodySoulEngine.train_body(c2, 1)["success"]
    assert c2.inventory.count(BODY_ITEM) == 5 and c2.spirit_stones == 10 and c2.body_level == 0
    # 灵石只够一层：批量 5 次只升 1 层，余量精确
    c3 = _stock(_char(), body_items=10, stones=25)
    res = BodySoulEngine.train_body(c3, 5)
    assert res["success"] and res["levels_gained"] == 1
    assert c3.spirit_stones == 5 and c3.inventory.count(BODY_ITEM) == 9
    print("✓ 资源不足零扣费（含材料不吞）；批量按可付层数停层")


def test_dead_rejected():
    c = _stock(_char(), body_items=5, soul_items=5, stones=1000)
    c.status = CharacterStatus.DEAD
    snap = (list(c.inventory), c.spirit_stones, c.lifespan.death_timestamp)
    assert not BodySoulEngine.train_body(c, 1)["success"]
    assert not BodySoulEngine.train_soul(c, 1)["success"]
    assert c.body_level == 0 and c.soul_level == 0
    assert (list(c.inventory), c.spirit_stones, c.lifespan.death_timestamp) == snap
    # 寿元已到期（status 尚未结算）同样拒炼——与突破引擎双查口径对齐
    c2 = _stock(_char(), body_items=5, stones=1000)
    c2.lifespan.death_timestamp = time.time() - 1
    assert not BodySoulEngine.train_body(c2, 1)["success"]
    assert c2.body_level == 0 and c2.inventory.count(BODY_ITEM) == 5
    print("✓ 死亡/寿元到期角色双轨拒炼，零变更")


# ---------------- 炼神：有效道心与判定点 ----------------

def test_soul_train_and_effective_dao_heart():
    c = _stock(_char(), soul_items=22, stones=2000)
    c.karma.dao_heart = 50
    res = BodySoulEngine.train_soul(c, SOUL_MAX_LEVEL)
    assert res["success"] and c.soul_level == SOUL_MAX_LEVEL
    assert c.inventory.count(SOUL_ITEM) == 0
    assert c.spirit_stones == 2000 - 825  # 字面值钉死：Σ15×L (L=1..10) = 825
    assert BodySoulEngine.dao_heart_bonus(c) == SOUL_DAO_HEART_CAP == 20
    assert BodySoulEngine.effective_dao_heart(c) == 70
    assert c.karma.dao_heart == 50  # 本体不被副修污染
    # 有效道心钳 100
    c.karma.dao_heart = 95
    assert BodySoulEngine.effective_dao_heart(c) == 100
    # 脏层数钳制
    c.soul_level = 99
    assert BodySoulEngine.dao_heart_bonus(c) == 20
    assert BodySoulEngine.sense_bonus(c) == SOUL_SENSE_PER_LEVEL * SOUL_MAX_LEVEL
    print("✓ 炼神满层：灵芝 22 枚+灵石 825，有效道心 +20 封顶、本体不变、钳 100")


def test_breakthrough_penalty_uses_effective_dao_heart():
    """判定点①：突破心魔惩罚——捕获最终成功率，炼神 10 层应恰减免 10%"""
    from ai.gateway import AIGateway
    from core.breakthrough import BreakthroughEngine

    def _prob(soul_level):
        c = _char()
        c.realm.tier, c.realm.sub_tier = 1, 3
        c.realm.current_exp = c.realm.max_exp
        c.karma.dao_heart = 50
        c.karma.sin_value = 0
        c.karma.merit_value = 0
        c.skills = ["吐纳术", "御剑术"]
        c.soul_level = soul_level
        return BreakthroughEngine.attempt_breakthrough(c)

    orig = AIGateway.judge_tribulation
    AIGateway.judge_tribulation = staticmethod(
        lambda character, prob, target: {
            "success": True, "source": "test", "reason": "", "adj_prob": prob,
        }
    )
    try:
        r0 = _prob(0)
        r10 = _prob(SOUL_MAX_LEVEL)
    finally:
        AIGateway.judge_tribulation = orig
    assert r0["success"] and r10["success"], (r0, r10)
    # base 0.35；本体道心 50 → 惩罚 (80-50)*0.005=0.15 → 20.0%
    assert abs(r0["prob_pct"] - 20.0) < 0.11, r0
    # 有效道心 70 → 惩罚 0.05 → 30.0%（恰 +10%）
    assert abs(r10["prob_pct"] - 30.0) < 0.11, r10
    assert abs((r10["prob_pct"] - r0["prob_pct"]) - 10.0) < 0.21
    print("✓ 突破判定点：炼神满层使心魔惩罚减免恰 10% 成功率")


def test_heart_demon_death_gate_uses_effective_dao_heart():
    """判定点②：心魔 death 门——本体道心 15 时，无炼神则殁、炼神满层（有效 35）则降 fail"""
    import config
    import core.heart_demon as hd
    from core.heart_demon import HeartDemonEngine, HeartDemonSession

    # 注意：test_ai_required 会 reload(ai.gateway) 造成类身份分裂，
    # 必须 patch heart_demon 模块实际引用的 AIGateway 类对象（其 resolve 真正使用者），
    # 并按 test_cli_parity 先例临时打开本地 AI 降级（resolve 的 ai_ready 门），用后恢复。
    old_flag = config.ALLOW_LOCAL_AI
    config.ALLOW_LOCAL_AI = True
    orig = hd.AIGateway.judge_heart_demon_choice
    hd.AIGateway.judge_heart_demon_choice = staticmethod(
        lambda character, narrative, label, is_free_text=False, facts=None: {
            "outcome": "death", "effects": {}, "tribulation_mod": 0.0,
            "narrative": "心魔噬心", "source": "test",
        }
    )
    try:
        def _run(soul_level):
            c = _char()
            c.karma.dao_heart = 15
            c.soul_level = soul_level
            sess = HeartDemonSession(
                id=f"hd_{c.id}", character_id=c.id, narrative="魔音灌耳",
                options=[], created_at=time.time(),
            )
            return c, HeartDemonEngine.resolve(c, sess, choice_id="yield")

        c0, r0 = _run(0)
        assert r0.get("is_fatal") and c0.status == CharacterStatus.DEAD, r0
        c10, r10 = _run(SOUL_MAX_LEVEL)
        assert r10.get("outcome") == "fail" and not r10.get("is_fatal"), r10
        assert c10.status != CharacterStatus.DEAD
    finally:
        hd.AIGateway.judge_heart_demon_choice = orig
        config.ALLOW_LOCAL_AI = old_flag
    print("✓ 心魔 death 门：有效道心 35>20 时 death 降为 fail，不致死")


def test_sense_bonus_changes_scan_clarity():
    """判定点③：神识探查——基线探不到的二阶目标，炼神满层 +30 后浮现 VAGUE"""
    scanner = _char("探查者")
    scanner.spiritual_root = SpiritualRoot(
        root_type=RootType.TRUE, elements=[Element.WOOD], efficiency=1.0)
    scanner.realm.tier, scanner.realm.sub_tier = 1, 0  # s_sense 基线 100
    target = _char("隐匿者")
    target.realm.tier, target.realm.sub_tier = 2, 0    # c_hide 120 → 基线 delta -20 不可见
    target.stealth_active = False
    assert CombatEngine.scan_surroundings(scanner, [target]) == []
    scanner.soul_level = SOUL_MAX_LEVEL                # +30 → delta 10 → VAGUE
    hits = CombatEngine.scan_surroundings(scanner, [target])
    assert len(hits) == 1 and hits[0]["clarity"] == "VAGUE", hits
    print("✓ 神识探查：炼神满层 +30 使不可见目标浮现为 VAGUE")


# ---------------- 与灵宠/心法槽位共存不叠爆 ----------------

def test_stacking_with_pet_and_art_slots():
    c = _char()
    c.skills = ["吐纳术", "御剑术", "裂风斩"]
    p0 = CombatEngine.calculate_power(c)
    c.sub_arts = ["吐纳术", "裂风斩"]                    # 心法辅修环 ×1.06
    p1 = CombatEngine.calculate_power(c)
    assert abs(p1 / p0 - 1.06) < 1e-9, (p0, p1)
    pet = SpiritPet(species="玄甲龟", name="玄甲龟", growth=900,
                    intimacy=50, active=True, state="follow")
    c.pets = [pet]                                       # 灵宠环 ×1.10（满级封顶）
    p2 = CombatEngine.calculate_power(c)
    assert abs(p2 / p1 - 1.10) < 1e-9, (p1, p2)
    c.body_level = BODY_MAX_LEVEL                        # 炼体环 ×1.10（独立封顶）
    p3 = CombatEngine.calculate_power(c)
    assert abs(p3 / p2 - (1.0 + BODY_POWER_CAP)) < 1e-9, (p2, p3)
    assert abs(p3 / p0 - 1.06 * 1.10 * 1.10) < 1e-9      # 三环各守封顶，无额外叠爆
    print("✓ 共存断言：心法 ×1.06 × 灵宠 ×1.10 × 炼体 ×1.10，各环独立封顶")


# ---------------- 面板 ----------------

def test_panel_text_contents():
    c = _stock(_char(), body_items=2, stones=100)
    t = BodySoulEngine.panel_text(c, "body")
    assert "炼体" in t and "下一层" in t and BODY_ITEM in t
    c.body_level = BODY_MAX_LEVEL
    assert "圆满" in BodySoulEngine.panel_text(c, "body")
    t2 = BodySoulEngine.panel_text(c, "soul")
    assert "炼神" in t2 and "有效道心" in t2 and SOUL_ITEM in t2
    print("✓ 面板：层数/成效/下一层成本与库存对照齐备")


# ---------------- 双端链路（server handle + 闭关锁门） ----------------

def test_world_handle_body_soul_chain():
    from storage.db import init_db, CharacterRepository
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    r = w.join(_uniq("副修链路客"))
    tok = r["token"]
    try:
        res = w.handle(tok, "/炼体")
        assert res.get("ok") and "炼体" in (res.get("text") or ""), res
        assert (res.get("status") or {}).get("body_soul") == {"body": 0, "soul": 0}
        # 无资源修炼：失败零变更
        res = w.handle(tok, "/炼体 修炼")
        assert not res.get("ok"), res
        # 备齐资源后全链路
        char = w.get_char(tok)
        char.inventory = [BODY_ITEM] * 3 + [SOUL_ITEM] * 3
        char.spirit_stones = 1000
        CharacterRepository.save(char)
        res = w.handle(tok, "/炼体 修炼 2")
        assert res.get("ok"), res
        assert (res.get("status") or {}).get("body_soul", {}).get("body") == 2
        res = w.handle(tok, "/炼神 修炼")
        assert res.get("ok"), res
        assert (res.get("status") or {}).get("body_soul", {}).get("soul") == 1
        res = w.handle(tok, "/炼神")
        assert res.get("ok") and "炼神" in (res.get("text") or "")
        # 闭关锁门：查看与修炼一并拦截（防临场刷加成，与 F02/F06 同口径）
        char = w.get_char(tok)
        char.status = CharacterStatus.MEDITATING
        CharacterRepository.save(char)
        for cmd in ("/炼体", "/炼体 修炼", "/炼神", "/炼神 修炼"):
            res = w.handle(tok, cmd)
            assert not res.get("ok") and "闭关锁门" in (res.get("error") or ""), (cmd, res)
    finally:
        # 零残留：自造角色置死，避免污染其他文件的随机抽取
        try:
            char = w.get_char(tok)
            char.status = CharacterStatus.DEAD
            char.lifespan.death_timestamp = 0.0
            CharacterRepository.save(char)
        except Exception:
            pass
    print("✓ World.handle 全链路：面板/修炼/批量/status.body_soul/闭关锁门")
