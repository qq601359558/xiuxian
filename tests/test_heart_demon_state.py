"""
F16 心魔长期状态机测试：魔念播种/惰性推导/发作/镇压/入魔 + 无种旧行为不变
"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.heart_demon_state as dmod
from core.heart_demon_state import DemonStateEngine as D
from core.heart_demon import HeartDemonEngine, HeartDemonSession
from core.clock import WorldClock
from core.models import Character, CharacterStatus


class FakeRng:
    """确定性 rng：按队列吐 random() 值，耗尽后恒 0.99"""

    def __init__(self, values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99


def _uniq(base: str) -> str:
    return f"f16{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _char(name="镇魔客"):
    return WorldClock.create_new_character(_uniq("u_"), _uniq(name))


def _seeded(seed=50.0, dao=50, sin=0):
    """已落库魔念 + 已建基线的角色（锚点=当下，sin 基线对齐，无待推导增量）"""
    c = _char()
    c.demon_seed = seed
    c.karma.dao_heart = dao
    c.karma.sin_value = sin
    D.sync(c)  # 首同步建基线，seed 原样保留
    assert c.demon_anchor_at > 0
    return c


# ---------------- 阶段与推导 ----------------

def test_stage_thresholds():
    assert D.stage_for(0.0) == 0
    assert D.stage_for(0.5) == 1
    assert D.stage_for(39.9) == 1
    assert D.stage_for(40.0) == 2
    assert D.stage_for(89.9) == 2
    assert D.stage_for(90.0) == 3
    assert D.stage_for(999.0) == 3
    print("✓ 阶段阈值：0 无种 / <40 蛰伏 / <90 滋长 / ≥90 临发")


def test_first_sync_baseline_no_retroactive():
    c = _char()
    c.karma.sin_value = 200  # 存量杀业
    c.karma.blood_mark_until = time.time() + 86400.0  # 存量血煞
    assert D.effective_seed(c) == 0.0  # 从未同步：不推导
    D.sync(c)
    assert c.demon_seed == 0.0  # 只建基线，落库魔念不追溯
    assert c.demon_sin_seen == 200
    c.karma.blood_mark_until = 0.0  # 血煞散去后阶段恒无种（锚点后时长路另有专测）
    assert D.stage(c) == 0
    print("✓ 首同步只建基线：存量杀业/血煞不追溯播种（老玩家无种不变）")


def test_sin_growth_and_dao_suppression():
    # 道心 0（压制 ×1.0）：新积业力 100 → 魔念 +50 → 滋长
    c = _seeded(seed=0.0, dao=0, sin=0)
    c.karma.sin_value = 100
    assert abs(D.effective_seed(c) - 50.0) < 1e-9
    assert D.stage(c) == 2
    # 道心 100（压制 ×0.25）：同等杀业只 +12.5
    c2 = _seeded(seed=0.0, dao=100, sin=0)
    c2.karma.sin_value = 100
    assert abs(D.effective_seed(c2) - 12.5) < 1e-9
    # 炼神有效道心（F10）：本体 50 + 炼神 10 层(+20) = 70 → 压制 ×0.5
    c3 = _seeded(seed=0.0, dao=50, sin=0)
    c3.soul_level = 10
    c3.karma.sin_value = 100
    assert abs(D.effective_seed(c3) - 25.0) < 1e-9
    print("✓ 杀业增量推导：×0.5 系数 + 有效道心压制（含炼神加值）三档断言")


def test_blood_duration_growth():
    c = _seeded(seed=0.0, dao=0, sin=0)
    now = time.time()
    # 血煞自锚点起覆盖整 1 现实日 → +2.0 魔念（道心 0 无压制）
    c.karma.blood_mark_until = c.demon_anchor_at + 86400.0
    assert abs(D.effective_seed(c, now=c.demon_anchor_at + 86400.0) - 2.0) < 1e-6
    # 血煞已散（截止早于锚点）→ 不计
    c.karma.blood_mark_until = c.demon_anchor_at - 10.0
    assert D.effective_seed(c, now=now) == 0.0
    print("✓ 血煞缠身时长路：覆盖 1 日 +2 魔念；已散不计")


def test_blood_duration_starts_at_mark_not_anchor():
    # 评审 M1 回归：血煞在锚点之后第 10 天才沾染（until = 起算 + 3 游戏年 = +3 现实日），
    # 第 11 天推导只应计 1 天覆盖（+2），不得按锚点起算的 11 天（+22）高估
    c = _seeded(seed=0.0, dao=0, sin=0)
    t0 = c.demon_anchor_at
    c.karma.blood_mark_until = t0 + 13 * 86400.0  # 起算 = t0+10d，截止 = t0+13d
    assert abs(D.effective_seed(c, now=t0 + 11 * 86400.0) - 2.0) < 1e-6
    # now 超过截止：覆盖封顶为标记全程 3 天 → +6，不再增长
    assert abs(D.effective_seed(c, now=t0 + 30 * 86400.0) - 6.0) < 1e-6
    print("✓ 血煞覆盖起点还原标记起算点（M1）：锚点后沾染不高估、过截止封顶")


def test_sync_idempotent():
    c = _seeded(seed=10.0, dao=0, sin=0)
    c.karma.sin_value = 40
    s1 = D.sync(c)
    s2 = D.sync(c)
    assert s1 == s2 == 30.0  # 10 + 40×0.5，重复 sync 增量为 0
    print("✓ sync 幂等：同刻重复落库增量为 0")


# ---------------- 播种 ----------------

def test_backlash_seeding_rng_gate():
    c = _seeded(seed=0.0, dao=0)  # 播种概率 0.60
    r = D.on_blood_backlash(c, rng=FakeRng([0.0]))
    assert r["seeded"] is True and c.demon_seed == 25.0 and D.stage(c) == 1
    c2 = _seeded(seed=0.0, dao=0)
    r2 = D.on_blood_backlash(c2, rng=FakeRng([0.99]))
    assert r2["seeded"] is False and c2.demon_seed == 0.0
    # 道心 100 → 概率 0.30：0.29 中 / 0.31 不中
    c3 = _seeded(seed=0.0, dao=100)
    assert D.on_blood_backlash(c3, rng=FakeRng([0.29]))["seeded"] is True
    c4 = _seeded(seed=0.0, dao=100)
    assert D.on_blood_backlash(c4, rng=FakeRng([0.31]))["seeded"] is False
    print("✓ 血煞反噬播种：概率门注入 rng 确定性 + 道心压制概率（0.60→0.30）")


def test_backlash_event_hook_via_fire(monkeypatch):
    # 经 EventEngine.fire 真实落账：patch gateway 出空 → 本地模板；patch 模板为血煞反噬；
    # 播种钩子计数（patch heart_demon_state 模块内引擎类方法）
    import core.events as ev_mod
    calls = []
    monkeypatch.setattr(
        ev_mod.AIGateway, "generate_world_event", staticmethod(lambda *a, **kw: None)
    )
    monkeypatch.setattr(
        dmod.DemonStateEngine, "on_blood_backlash",
        staticmethod(lambda c, **kw: calls.append(c.id) or {"seeded": True}),
    )
    backlash = {"type": "crisis", "title": "血煞反噬", "narrative": "旧伤复发，杀气冲撞识海。",
                "effects": {"sin": 5, "dao_heart": -5}}
    monkeypatch.setattr(ev_mod.EventEngine, "_local_event", staticmethod(lambda c, t: dict(backlash)))
    c = _seeded(seed=0.0, dao=50)
    sin_before = c.karma.sin_value
    ev = ev_mod.EventEngine.fire(c, etype="crisis", force=True)
    assert ev is not None and ev["title"] == "血煞反噬"
    assert c.karma.sin_value == sin_before + 5  # 事件本身既有落账不变
    assert calls == [c.id]  # 落账后播种钩子恰一次
    # 非反噬标题不触发钩子
    calls.clear()
    other = {"type": "crisis", "title": "妖兽扑杀", "narrative": "妖兽扑来。", "effects": {"exp": 10}}
    monkeypatch.setattr(ev_mod.EventEngine, "_local_event", staticmethod(lambda c, t: dict(other)))
    ev2 = ev_mod.EventEngine.fire(c, etype="crisis", force=True)
    assert ev2 is not None and calls == []
    print("✓ fire 落账钩子：血煞反噬恰触发一次播种、他题不触发、事件原落账不变")


# ---------------- 无种旧行为（关键回归） ----------------

def test_no_seed_breakthrough_session_not_eruption():
    c = _char()
    c.karma.sin_value = 80  # 既有问心测试同款高业力，但从未播种
    session = HeartDemonEngine.start(c)
    assert session.eruption is False
    res = HeartDemonEngine.resolve(c, session, choice_id="cut")
    assert res["success"] is True
    assert res.get("demon") is None  # 非发作场次零追加
    assert c.demon_seed == 0.0
    print("✓ 无种者突破问心：eruption 恒 False、resolve 零追加（旧行为钉死）")


def test_no_seed_meditation_no_eruption():
    c = _char()
    assert D.resolve_meditation_eruption(c, rng=FakeRng([0.0, 0.0])) is None
    c2 = _seeded(seed=20.0)  # 蛰伏亦不发作
    assert D.resolve_meditation_eruption(c2, rng=FakeRng([0.0, 0.0])) is None
    print("✓ 无种/蛰伏：闭关发作检查恒 None（rng 全 0 亦不发作）")


# ---------------- 突破发作 ----------------

def test_eruption_roll_gates():
    c1 = _seeded(seed=20.0)  # 蛰伏
    assert D.roll_eruption(c1, "breakthrough", rng=FakeRng([0.0])) is False
    c2 = _seeded(seed=50.0)  # 滋长 0.35
    assert D.roll_eruption(c2, "breakthrough", rng=FakeRng([0.34])) is True
    assert D.roll_eruption(c2, "breakthrough", rng=FakeRng([0.36])) is False
    c3 = _seeded(seed=100.0)  # 临发 0.65
    assert D.roll_eruption(c3, "breakthrough", rng=FakeRng([0.64])) is True
    assert D.roll_eruption(c3, "breakthrough", rng=FakeRng([0.66])) is False
    print("✓ 发作概率门：滋长 0.35 / 临发 0.65 边界注入断言")


def test_eruption_start_flag_with_patched_rng(monkeypatch):
    monkeypatch.setattr(dmod, "random", FakeRng([0.0]))
    c = _seeded(seed=50.0)
    session = HeartDemonEngine.start(c)
    assert session.eruption is True
    print("✓ start 发作标记：滋长 + rng 命中 → session.eruption=True")


def test_apply_eruption_outcome_paths():
    # pass：滋长 50 → 回落一阶 39（蛰伏）
    c = _seeded(seed=50.0)
    info = D.apply_eruption_outcome(c, "pass")
    assert c.demon_seed == 39.0 and info["stage_after"] == 1
    # wound：+5
    c = _seeded(seed=50.0)
    D.apply_eruption_outcome(c, "wound")
    assert c.demon_seed == 55.0
    # fail（阶段<3）：+15
    c = _seeded(seed=50.0)
    D.apply_eruption_outcome(c, "fail")
    assert c.demon_seed == 65.0
    # 临发 fail → 入魔档：道心 −20、业力 +40、魔念恰为原值（不低于临发下限、不双计）
    c = _seeded(seed=100.0, dao=60, sin=10)
    info = D.apply_eruption_outcome(c, "dao_crack")
    assert info["possessed"] is True
    assert c.karma.dao_heart == 40
    assert c.karma.sin_value == 50
    assert c.demon_seed == 100.0  # 评审 M2 回归：入魔 +40 业力不得再折算 +20 魔念
    D.sync(c)
    assert abs(c.demon_seed - 100.0) < 0.01  # 业力基线已吸收，再 sync 不双计
    # 临界 90 入魔：魔念恰 90（临发下限）
    c = _seeded(seed=90.0, dao=60, sin=0)
    D.apply_eruption_outcome(c, "fail")
    assert c.demon_seed == 90.0
    print("✓ 发作后果：pass 回落 / wound +5 / fail +15 / 临发 fail 入魔（道心−20·业力+40·魔念不双计）")


def test_eruption_resolve_integration(monkeypatch):
    # patch heart_demon 实际引用的 AIGateway 类对象（F10 类身份分裂教训）
    import core.heart_demon as hd_mod

    def fake_judge(character, narrative, label, is_free_text=False, facts=None):
        return {"outcome": "pass", "effects": {}, "tribulation_mod": 0.0,
                "narrative": "魔影退散。", "source": "local"}

    monkeypatch.setattr(hd_mod.AIGateway, "judge_heart_demon_choice", staticmethod(fake_judge))
    c = _seeded(seed=50.0)
    session = HeartDemonSession(
        id="hd_test_f16", character_id=c.id, narrative="魔影幢幢",
        options=[{"id": "cut", "label": "斩念"}], created_at=time.time(), eruption=True,
    )
    res = HeartDemonEngine.resolve(c, session, choice_id="cut")
    assert res["success"] is True and res["outcome"] == "pass"
    assert res["demon"] is not None and res["demon"]["stage_after"] == 1
    assert c.demon_seed == 39.0
    print("✓ 发作场次 resolve 集成：既有判定走完后追加阶段回落")


# ---------------- 闭关发作（规则内斗） ----------------

def test_meditation_duel_outcomes():
    # pass：道心 90 → p=0.45+0.24=0.69；rolls [发作 0.0, 内斗 0.0]
    c = _seeded(seed=50.0, dao=90)
    info = D.resolve_meditation_eruption(c, rng=FakeRng([0.0, 0.0]))
    assert info["outcome"] == "pass" and c.demon_seed == 39.0 and c.karma.dao_heart == 92
    # wound：道心 50 → p=0.45；rolls [0.0, 0.60]（0.45 ≤ r < 0.80）
    c = _seeded(seed=50.0, dao=50)
    info = D.resolve_meditation_eruption(c, rng=FakeRng([0.0, 0.60]))
    assert info["outcome"] == "wound" and c.karma.dao_heart == 42 and c.demon_seed == 55.0
    # fail（滋长）：rolls [0.0, 0.99]
    c = _seeded(seed=50.0, dao=50)
    info = D.resolve_meditation_eruption(c, rng=FakeRng([0.0, 0.99]))
    assert info["outcome"] == "fail" and c.karma.dao_heart == 35 and c.demon_seed == 65.0
    assert info["possessed"] is False
    # 发作门未命中：滋长概率 0.25，roll 0.30 → 不发作、零变更
    c = _seeded(seed=50.0, dao=50)
    assert D.resolve_meditation_eruption(c, rng=FakeRng([0.30])) is None
    assert c.demon_seed == 50.0 and c.karma.dao_heart == 50
    print("✓ 闭关内斗三档：pass 回落+道心2 / wound 道心−8·魔念+5 / fail 道心−15·魔念+15；未发作零变更")


def test_meditation_duel_possessed_at_stage3():
    c = _seeded(seed=100.0, dao=50, sin=0)
    info = D.resolve_meditation_eruption(c, rng=FakeRng([0.0, 0.99]))
    assert info["possessed"] is True and info["outcome"] == "fail"
    assert c.karma.dao_heart == 30 and c.karma.sin_value == 40
    assert c.demon_seed == 100.0  # M2：入魔后魔念恰原值
    print("✓ 临发闭关内斗大败 → 入魔档（道心−20 至 30、业力+40）")


def test_meditation_duel_stage3_pass_boundary():
    # 临发胜率含 −0.12 阶段罚：道心 50 → p=0.33；roll 0.32 恰 pass、回落至临发下限−1=89
    c = _seeded(seed=100.0, dao=50)
    info = D.resolve_meditation_eruption(c, rng=FakeRng([0.0, 0.32]))
    assert info["outcome"] == "pass" and c.demon_seed == 89.0
    # roll 0.34 已过胜率线 → 落入 wound 档（0.33 ≤ r < 0.68）
    c = _seeded(seed=100.0, dao=50)
    info = D.resolve_meditation_eruption(c, rng=FakeRng([0.0, 0.34]))
    assert info["outcome"] == "wound"
    print("✓ 临发内斗胜率边界：p=0.33 两侧分档精确")


def test_settle_meditation_eruption_integration(monkeypatch):
    monkeypatch.setattr(dmod, "random", FakeRng([0.0, 0.0]))  # 发作命中 + 内斗 pass
    c = _seeded(seed=50.0, dao=90)
    res_start = WorldClock.start_meditation(c, hours_planned=1.0)
    assert res_start["success"] is True
    start = c.meditation.start_time
    res = WorldClock.settle_meditation(c, force_interrupt=True, now=start + 3600.0)
    assert res["success"] is True
    de = res.get("demon_eruption")
    assert de is not None and de["outcome"] == "pass", res
    assert c.demon_seed == 39.0
    print("✓ settle_meditation 集成：发作结果并入结算 dict，魔念回落落账")


def test_settle_meditation_no_seed_key_neutral():
    c = _char()
    res_start = WorldClock.start_meditation(c, hours_planned=1.0)
    assert res_start["success"] is True
    start = c.meditation.start_time
    res = WorldClock.settle_meditation(c, force_interrupt=True, now=start + 3600.0)
    assert res["success"] is True and res.get("demon_eruption") is None
    print("✓ 无种者闭关结算：demon_eruption 恒 None（旧行为）")


# ---------------- 镇压 ----------------

def test_suppress_pill():
    c = _seeded(seed=50.0)
    c.inventory = ["百年灵芝"]
    c.spirit_stones = 100
    r = D.suppress_pill(c)
    assert r["success"] is True
    assert c.demon_seed == 15.0 and c.spirit_stones == 70 and "百年灵芝" not in c.inventory
    # 无灵芝：拒绝且零扣费
    c2 = _seeded(seed=50.0)
    c2.spirit_stones = 100
    r2 = D.suppress_pill(c2)
    assert r2["success"] is False and c2.spirit_stones == 100 and c2.demon_seed == 50.0
    # 灵石不足：拒绝且不扣灵芝
    c3 = _seeded(seed=50.0)
    c3.inventory = ["百年灵芝"]
    c3.spirit_stones = 10
    r3 = D.suppress_pill(c3)
    assert r3["success"] is False and c3.inventory == ["百年灵芝"] and c3.spirit_stones == 10
    # 魔念 30 服丹 → 归零除种
    c4 = _seeded(seed=30.0)
    c4.inventory = ["百年灵芝"]
    c4.spirit_stones = 30
    r4 = D.suppress_pill(c4)
    assert r4["success"] is True and c4.demon_seed == 0.0 and r4["stage_after"] == 0
    # 无种服丹：拒绝不扣
    c5 = _seeded(seed=0.0)
    c5.inventory = ["百年灵芝"]
    c5.spirit_stones = 100
    assert D.suppress_pill(c5)["success"] is False and c5.inventory == ["百年灵芝"]
    print("✓ 服丹镇魔：−35 落账/资源不足零扣费/归零除种/无种拒绝，全断言")


def test_suppress_calm():
    # 有效道心不足 50 → 拒绝
    c = _seeded(seed=50.0, dao=40)
    assert D.suppress_calm(c)["success"] is False and c.demon_seed == 50.0
    # 炼神补足有效道心：本体 40 + 炼神 10 层 = 60 ≥ 50 → 可静坐
    c.soul_level = 10
    r = D.suppress_calm(c)
    assert r["success"] is True and c.demon_seed == 30.0
    # 冷却中再静坐 → 拒绝且不再降阶（防重复降阶）
    r2 = D.suppress_calm(c)
    assert r2["success"] is False and c.demon_seed == 30.0
    # 冷却过后可再行
    r3 = D.suppress_calm(c, now=c.demon_calm_at + 20 * 3600.0 + 1.0)
    assert r3["success"] is True and c.demon_seed == 10.0
    print("✓ 静坐镇魔：有效道心门（含炼神）/−20/20h 冷却防重复降阶")


def test_suppress_dead_rejected():
    c = _seeded(seed=50.0)
    c.status = CharacterStatus.DEAD
    c.inventory = ["百年灵芝"]
    c.spirit_stones = 100
    assert D.suppress_pill(c)["success"] is False
    assert D.suppress_calm(c)["success"] is False
    assert c.demon_seed == 50.0 and c.spirit_stones == 100
    print("✓ 死亡角色镇魔双路拒绝、零变更")


def test_possessed_caps_floor():
    c = _seeded(seed=100.0, dao=10, sin=0)
    D.apply_eruption_outcome(c, "fail")
    assert c.karma.dao_heart == 0  # −20 钳至 0，不为负
    assert c.karma.sin_value == 40  # 恰 caps 单次幅度
    print("✓ 入魔档钳制：道心 −20 触底 0、业力 +40 恰 caps")


# ---------------- 面板 / 旧档 / 双端 ----------------

def test_panel_and_summary():
    c = _seeded(seed=50.0, dao=50, sin=30)
    s = D.summary(c)
    assert s == {"stage": 2, "stage_name": "滋长", "seed": 50}
    t = D.panel_text(c)
    assert "滋长" in t and "服丹" in t and "静坐" in t
    c0 = _char()
    assert D.summary(c0)["stage"] == 0 and "无种" in D.panel_text(c0)
    print("✓ 面板/摘要：阶段与镇压路径齐备；无种口径明示")


def test_legacy_character_defaults():
    c = _char()
    data = c.model_dump()
    for k in ("demon_seed", "demon_anchor_at", "demon_sin_seen", "demon_calm_at"):
        data.pop(k, None)
    old = Character.model_validate(data)  # 旧档 JSON 无 F16 字段
    assert old.demon_seed == 0.0 and old.demon_anchor_at == 0.0
    assert old.demon_sin_seen == 0 and old.demon_calm_at == 0.0
    assert D.stage(old) == 0
    print("✓ 旧档反序列化：四字段默认 0、阶段无种")


def test_world_handle_demon_chain():
    from storage.db import init_db, CharacterRepository
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    r = w.join(_uniq("镇魔链路客"))
    tok = r["token"]
    try:
        res = w.handle(tok, "/镇魔")
        assert res.get("ok") and "心魔" in (res.get("text") or ""), res
        assert (res.get("status") or {}).get("heart_demon_state", {}).get("stage") == 0
        # 种魔后服丹全链路
        char = w.get_char(tok)
        char.demon_seed = 50.0
        char.inventory = ["百年灵芝"]
        char.spirit_stones = 100
        CharacterRepository.save(char)
        res = w.handle(tok, "/镇魔")
        assert (res.get("status") or {}).get("heart_demon_state", {}).get("stage") == 2, res
        res = w.handle(tok, "/镇魔 服丹")
        assert res.get("ok"), res
        char = w.get_char(tok)
        assert char.demon_seed == 15.0 and char.spirit_stones == 70
        # 闭关锁门：面板与镇压一并拦截
        char.status = CharacterStatus.MEDITATING
        CharacterRepository.save(char)
        for cmd in ("/镇魔", "/镇魔 服丹", "/镇魔 静坐"):
            res = w.handle(tok, cmd)
            assert not res.get("ok") and "闭关锁门" in (res.get("error") or ""), (cmd, res)
    finally:
        try:
            char = w.get_char(tok)
            char.status = CharacterStatus.DEAD
            char.lifespan.death_timestamp = 0.0
            CharacterRepository.save(char)
        except Exception:
            pass
    print("✓ World.handle 全链路：面板/status 透出/服丹落账/闭关锁门 + 零残留")
