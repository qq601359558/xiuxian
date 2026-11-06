"""F07 NPC 委托链：生成/接取/三环核验/发奖幂等/过期/弃链/双端/旧档兼容"""
import os
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core.clock import WorldClock
from core.models import Character, CharacterStatus, QuestChain, QuestRing
from core.quests import (
    QuestEngine,
    reward_stones_for,
    QUEST_REWARD_STONES_CAP,
    QUEST_REWARD_MERIT,
    QUEST_ACCEPT_COOLDOWN_SECONDS,
    QUEST_CHAIN_TTL_SECONDS,
)
from core.adventure import AdventureEngine
from storage.db import CharacterRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"
LOC_B = "落霞山灵泉"


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _tag() -> str:
    # 显示名后缀：测试库跨轮累积，按名接取/断言须避免与往轮同名角色撞车
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name="跑环客", stones=500, location=LOC_A):
    c = WorldClock.create_new_character(f"quest_{_uniq(name)}", f"{name}{_tag()}")
    c.spirit_stones = stones
    c.location = location
    CharacterRepository.save(c)
    return c


def _npc(name="委托翁", location=LOC_A, tier=1):
    c = WorldClock.create_new_character(f"npc_quest_{_uniq(name)}", f"{name}{_tag()}")
    c.location = location
    c.realm.tier = tier
    CharacterRepository.save(c)
    return c


def _chain(publisher, rings, reward=100):
    now = time.time()
    return QuestChain(
        publisher_id=publisher.id, publisher_name=publisher.name,
        rings=rings, ring_index=0, accepted_at=now,
        expires_at=now + QUEST_CHAIN_TTL_SECONDS,
        reward_stones=reward, reward_merit=QUEST_REWARD_MERIT,
    )


class _FixedRng:
    def __init__(self, v):
        self.v = v

    def random(self):
        return self.v


# ---------------- 生成 ----------------

def test_generate_chain_structure():
    pub = _npc("结构翁")
    others = [_npc("甲某", LOC_B), _npc("乙某", LOC_B)]
    for seed in range(12):
        ch = QuestEngine.generate_chain(pub, _char(), rng=random.Random(seed), others=others)
        assert 2 <= len(ch.rings) <= 4, len(ch.rings)
        kinds = [r.kind for r in ch.rings]
        assert all(k in ("deliver", "fetch", "slay") for k in kinds)
        assert all(a != b for a, b in zip(kinds, kinds[1:])), kinds  # 相邻不同 kind
        for r in ch.rings:
            if r.kind == "deliver":
                assert r.deliver_npc_id in {o.id for o in others}  # 送信目标必为他人
            if r.kind == "fetch":
                assert r.deliver_npc_id == pub.id and r.item_name
            if r.kind == "slay":
                assert r.deliver_npc_id == pub.id and 1 <= r.need <= 2
        assert ch.reward_stones == min(QUEST_REWARD_STONES_CAP, len(ch.rings) * 30 + pub.realm.tier * 10)
        assert ch.reward_merit == QUEST_REWARD_MERIT
        assert ch.accepted_at == 0.0  # 接取前为预览态
    print("✓ 链生成结构（2–4 环/相邻不同/目标可核验/定价公式）")


def test_generate_chain_without_others_has_no_deliver():
    pub = _npc("孤绝翁")
    for seed in range(6):
        ch = QuestEngine.generate_chain(pub, _char(), rng=random.Random(seed), others=[])
        assert all(r.kind != "deliver" for r in ch.rings)
        assert 2 <= len(ch.rings) <= 4
    print("✓ 无其他 NPC 时不生成送信环")


def test_reward_cap():
    pub = _npc("高境翁", tier=9)
    assert reward_stones_for(pub, 4) == QUEST_REWARD_STONES_CAP
    low = _npc("低境翁", tier=1)
    assert reward_stones_for(low, 2) == 70
    print("✓ 奖励封顶口径")


# ---------------- 接取 ----------------

def test_offers_and_accept_by_name_and_number():
    pub = _npc("可接翁", LOC_A)
    _npc("远方客", LOC_B)
    p = _char("接取客")
    offers = QuestEngine.offers_for(p, rng=random.Random(3))
    assert any(n.id == pub.id for n, _ in offers)
    # 缓存一致：二次 offers 链 id 不变
    again = QuestEngine.offers_for(p, rng=random.Random(99))
    assert {c.id for _, c in again} == {c.id for _, c in offers}
    res = QuestEngine.accept(p, pub.name, rng=random.Random(3))
    assert res["success"], res
    assert p.active_quest is not None and p.active_quest.publisher_id == pub.id
    assert p.active_quest.expires_at - p.active_quest.accepted_at == QUEST_CHAIN_TTL_SECONDS
    # 已有链时再接 → 拒绝
    res2 = QuestEngine.accept(p, pub.name)
    assert not res2["success"] and "已有" in res2["message"]
    # 编号接取（另一名玩家）
    p2 = _char("编号客")
    res3 = QuestEngine.accept(p2, "1", rng=random.Random(5))
    assert res3["success"], res3
    # 查无此人
    p3 = _char("扑空客")
    res4 = QuestEngine.accept(p3, "不存在的某人")
    assert not res4["success"]
    print("✓ offers 缓存一致 / 按名与编号接取 / 重复接取拒绝")


def test_abandon_and_cooldown():
    pub = _npc("弃链翁", LOC_A)
    _npc("远方贰", LOC_B)
    p = _char("弃链客")
    assert QuestEngine.accept(p, pub.name, rng=random.Random(1))["success"]
    res = QuestEngine.abandon(p)
    assert res["success"] and p.active_quest is None
    assert p.quest_cooldown_until > time.time()
    # 冷却内再接被拒；无链再弃被拒
    assert not QuestEngine.accept(p, pub.name)["success"]
    assert not QuestEngine.abandon(p)["success"]
    p.quest_cooldown_until = 0.0
    assert QuestEngine.accept(p, pub.name, rng=random.Random(2))["success"]
    print("✓ 弃链清链+冷却 / 冷却内拒接")

# ---------------- 三环核验 ----------------

def test_deliver_ring_wrong_then_right_location():
    pub = _npc("发信翁", LOC_A)
    tgt = _npc("收信翁", LOC_B)
    p = _char("信使客", location=LOC_A)
    ring = QuestRing(kind="deliver", desc="送信", deliver_npc_id=tgt.id, deliver_npc_name=tgt.name)
    p.active_quest = _chain(pub, [ring], reward=90)
    stones0 = p.spirit_stones
    res = QuestEngine.deliver(p)  # 人在 A、收信人在 B
    assert not res["success"] and "当面交付" in res["message"]
    assert p.active_quest is not None and p.active_quest.ring_index == 0
    assert p.spirit_stones == stones0
    p.location = LOC_B
    res2 = QuestEngine.deliver(p, rng=_FixedRng(0.99))
    assert res2["success"] and res2.get("completed"), res2
    assert p.active_quest is None
    assert p.spirit_stones == stones0 + 90
    print("✓ 送信环：错地点失败、对地点推进并结链发赏")


def test_fetch_ring_deducts_one():
    pub = _npc("寻药翁", LOC_A)
    p = _char("寻物客", location=LOC_A)
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=pub.id,
                     deliver_npc_name=pub.name, item_name="妖兽内丹", need=1)
    p.active_quest = _chain(pub, [ring], reward=80)
    res = QuestEngine.deliver(p)  # 无物
    assert not res["success"] and "行囊中无" in res["message"]
    p.inventory.extend(["妖兽内丹", "妖兽内丹"])
    res2 = QuestEngine.deliver(p, rng=_FixedRng(0.99))
    assert res2["success"] and res2.get("completed")
    assert p.inventory.count("妖兽内丹") == 1  # 只扣 1 件
    print("✓ 寻物环：无物失败、有物扣 1 推进")


def test_slay_ring_hook_and_progress():
    pub = _npc("除妖翁", LOC_A)
    p = _char("除妖客", location=LOC_A)
    ring = QuestRing(kind="slay", desc="除妖", deliver_npc_id=pub.id,
                     deliver_npc_name=pub.name, need=2)
    p.active_quest = _chain(pub, [ring], reward=70)
    res = QuestEngine.deliver(p)
    assert not res["success"] and "0/2" in res["message"]
    QuestEngine.note_adventure_win(p)
    assert ring.progress == 1
    assert not QuestEngine.deliver(p)["success"]
    QuestEngine.note_adventure_win(p)
    QuestEngine.note_adventure_win(p)  # 超额计数被封顶
    assert ring.progress == 2
    res2 = QuestEngine.deliver(p, rng=_FixedRng(0.99))
    assert res2["success"] and res2.get("completed")
    print("✓ 除妖环：钩子计数/封顶/未满拒交/满后推进")


def test_slay_counts_real_adventure_wins():
    import config
    import ai.gateway as gw
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    gw.LLM_API_KEY = ""
    gw.USE_CCSWITCH = False
    pub = _npc("验妖翁", LOC_A)
    p = _char("实战客", location=LOC_A, stones=5000)
    p.born_at = time.time() - 100 * 3600  # 出新手保护，免干扰
    ring = QuestRing(kind="slay", desc="除妖", deliver_npc_id=pub.id,
                     deliver_npc_name=pub.name, need=2)
    p.active_quest = _chain(pub, [ring], reward=70)
    wins = 0
    for _ in range(40):
        if ring.progress >= 2:
            break
        p.adventure_cd_until = 0.0
        res = AdventureEngine.explore(p, "野外", use_ai=False)
        assert res["success"]
        if res.get("combat_success"):
            wins += 1
        # 钩子计数与真实胜场严格一致（封顶 need）
        assert ring.progress == min(wins, 2), (wins, ring.progress)
    assert ring.progress == 2 and wins >= 2
    print("✓ 除妖环与真实探险胜负逐场对账")


# ---------------- 完成发奖 / 幂等 / 态度 / 线索 ----------------

def test_completion_rewards_once_attitude_and_clue():
    from core.npc_mind import attitude_toward
    pub = _npc("谢仪翁", LOC_A)
    p = _char("领赏客", location=LOC_A, stones=200)
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=pub.id,
                     deliver_npc_name=pub.name, item_name="聚灵草", need=1)
    p.active_quest = _chain(pub, [ring], reward=100)
    p.inventory.append("聚灵草")
    merit0 = p.karma.merit_value
    res = QuestEngine.deliver(p, rng=_FixedRng(0.99))  # 不触发线索
    assert res["success"] and res.get("completed")
    assert p.spirit_stones == 300 and p.karma.merit_value == merit0 + QUEST_REWARD_MERIT
    assert "裂风斩" not in p.skills
    # 重复交付：无链扑空，绝不重发
    res2 = QuestEngine.deliver(p)
    assert not res2["success"] and p.spirit_stones == 300
    # 态度 +8（既有 npc_mind 口径）
    assert attitude_toward(pub, p.id)["value"] == 8
    # 线索命中：概率门内授予池中第一门未习得功法
    p2 = _char("线索客", location=LOC_A, stones=200)
    p2.active_quest = _chain(pub, [ring.model_copy()], reward=100)
    p2.inventory.append("聚灵草")
    res3 = QuestEngine.deliver(p2, rng=_FixedRng(0.1))
    assert res3["success"] and "裂风斩" in p2.skills
    print("✓ 发奖只发一次 / 功德到账 / 态度+8 / 功法线索概率门")


def test_multi_ring_chain_advances_in_order():
    pub = _npc("连环翁", LOC_A)
    tgt = _npc("连环收信", LOC_B)
    p = _char("连环客", location=LOC_A)
    rings = [
        QuestRing(kind="fetch", desc="先寻物", deliver_npc_id=pub.id,
                  deliver_npc_name=pub.name, item_name="灵谷", need=1),
        QuestRing(kind="deliver", desc="再送信", deliver_npc_id=tgt.id, deliver_npc_name=tgt.name),
    ]
    p.active_quest = _chain(pub, rings, reward=120)
    p.inventory.append("灵谷")
    r1 = QuestEngine.deliver(p, rng=_FixedRng(0.99))
    assert r1["success"] and r1.get("advanced") and p.active_quest.ring_index == 1
    assert p.spirit_stones == 500  # 逐环不发奖
    p.location = LOC_B
    r2 = QuestEngine.deliver(p, rng=_FixedRng(0.99))
    assert r2["success"] and r2.get("completed") and p.spirit_stones == 620
    print("✓ 多环顺序推进，奖励只在全链完成时发放")


# ---------------- 过期 / 陨落 / 面板 ----------------

def test_expired_chain_voided_via_deliver_and_panel():
    pub = _npc("过期翁", LOC_A)
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=pub.id,
                     deliver_npc_name=pub.name, item_name="灵谷", need=1)
    p = _char("过期客", location=LOC_A)
    ch = _chain(pub, [ring.model_copy()])
    ch.expires_at = time.time() - 10
    p.active_quest = ch
    res = QuestEngine.deliver(p)
    assert not res["success"] and res.get("dirty") and p.active_quest is None
    # 面板路径：settle 先行
    p2 = _char("过期客二", location=LOC_A)
    ch2 = _chain(pub, [ring.model_copy()])
    ch2.expires_at = time.time() - 10
    p2.active_quest = ch2
    assert QuestEngine.settle_expired(p2) is True and p2.active_quest is None
    txt = QuestEngine.panel_text(p2)
    assert "NPC 委托" in txt
    print("✓ 过期链在交付与面板两路径惰性作废")


def test_dead_target_voids_chain():
    pub = _npc("短命翁", LOC_A)
    p = _char("送终客", location=LOC_A, stones=300)
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=pub.id,
                     deliver_npc_name=pub.name, item_name="灵谷", need=1)
    p.active_quest = _chain(pub, [ring], reward=100)
    p.inventory.append("灵谷")
    pub.status = CharacterStatus.DEAD
    CharacterRepository.save(pub)
    res = QuestEngine.deliver(p)
    assert not res["success"] and res.get("dirty") and p.active_quest is None
    assert p.spirit_stones == 300 and "灵谷" in p.inventory  # 作废不扣物不发奖
    print("✓ 交付对象陨落 → 作废无赏无罚不扣物")


def test_panel_shows_offers_and_progress():
    pub = _npc("面板翁", LOC_A)
    _npc("面板远客", LOC_B)
    p = _char("面板客", location=LOC_A)
    txt = QuestEngine.panel_text(p, rng=random.Random(7))
    assert pub.name in txt and "接委托" in txt
    assert QuestEngine.accept(p, pub.name, rng=random.Random(7))["success"]
    txt2 = QuestEngine.panel_text(p)
    assert "委托进行中" in txt2 and "交付" in txt2
    print("✓ 面板：可接列表与进行中进度")


# ---------------- 双端 / 旧档 ----------------

def test_server_handle_flow_and_meditation_lock():
    npc = _npc("服内翁", LOC_A)
    _npc("服内远客", LOC_B)
    r = WORLD.join(f"委托服客{_uniq('')}")
    tok = r["token"]
    char = WORLD.get_char(tok)
    npc.location = char.location
    CharacterRepository.save(npc)
    res = WORLD.handle(tok, "/委托")
    assert res["ok"] and npc.name in res["text"], res
    res = WORLD.handle(tok, f"/接委托 {npc.name}")
    assert res["ok"], res
    # 强制改造成单环寻物并交付（链路验证：handle→引擎→落库）
    char = WORLD.get_char(tok)
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=npc.id,
                     deliver_npc_name=npc.name, item_name="聚灵草", need=1)
    char.active_quest = _chain(npc, [ring], reward=66)
    char.inventory.append("聚灵草")
    stones0 = char.spirit_stones
    CharacterRepository.save(char)
    res = WORLD.handle(tok, "/交付")
    assert res["ok"], res
    char = WORLD.get_char(tok)
    assert char.active_quest is None and char.spirit_stones == stones0 + 66
    assert res["status"]["quest"] is None
    # 闭关锁门：四指令均不在白名单
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    for cmd in ("/委托", "/接委托 某人", "/交付", "/弃委托"):
        res = WORLD.handle(tok, cmd)
        assert res["ok"] is False and "闭关锁门" in (res.get("error") or ""), (cmd, res)
    char.status = CharacterStatus.IDLE
    CharacterRepository.save(char)
    print("✓ server handle 全链路 + 闭关锁门")


def test_cli_source_parity():
    src = (Path(__file__).resolve().parent.parent / "cli" / "main.py").read_text(encoding="utf-8")
    for token in ("/委托", "/接委托", "/交付", "/弃委托", "QuestEngine.accept", "QuestEngine.deliver", "QuestEngine.abandon"):
        assert token in src, token
    print("✓ CLI 源码对齐（双端同引擎）")


def test_old_save_compat():
    c = _char("旧档客")
    data = c.model_dump()
    data.pop("active_quest", None)
    data.pop("quest_cooldown_until", None)
    old = Character.model_validate(data)
    assert old.active_quest is None and old.quest_cooldown_until == 0.0
    assert QuestEngine.panel_text(old)  # 无链角色面板正常
    assert not QuestEngine.deliver(old)["success"]
    assert not QuestEngine.abandon(old)["success"]
    # 链模型往返序列化
    ch = _chain(_npc("往返翁"), [QuestRing(kind="slay", desc="除妖", need=2, progress=1)])
    rt = QuestChain.model_validate(ch.model_dump())
    assert rt.rings[0].progress == 1 and rt.reward_stones == ch.reward_stones
    print("✓ 旧档反序列化兼容 / 链模型往返")


# ---------------- 评审整改回归（M1 / S5） ----------------

def test_unknown_ring_kind_fails_closed():
    pub = _npc("异环翁", LOC_A)
    p = _char("异环客", location=LOC_A, stones=300)
    ring = QuestRing(kind="bogus", desc="未知环", deliver_npc_id=pub.id, deliver_npc_name=pub.name)
    p.active_quest = _chain(pub, [ring], reward=100)
    res = QuestEngine.deliver(p)
    assert not res["success"] and res.get("dirty")
    assert p.active_quest is None and p.spirit_stones == 300  # 作废不发奖
    print("✓ 未知环种 fail-closed 作废（评审 M1）")


def test_dead_rejections_have_no_side_effects():
    pub = _npc("死拒翁", LOC_A)
    p = _char("死拒客", location=LOC_A)
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=pub.id,
                     deliver_npc_name=pub.name, item_name="灵谷", need=1)
    ch = _chain(pub, [ring])
    ch.expires_at = time.time() - 5  # 已过期：DEAD 校验须前置于结算，死人指令零副作用
    p.active_quest = ch
    p.status = CharacterStatus.DEAD
    cd0 = p.quest_cooldown_until
    for res in (QuestEngine.accept(p, pub.name), QuestEngine.deliver(p), QuestEngine.abandon(p)):
        assert not res["success"] and not res.get("dirty"), res
    assert p.active_quest is ch and p.quest_cooldown_until == cd0  # 链未被结算动过
    print("✓ DEAD 前置拒绝且零副作用（accept/deliver/abandon）")


def test_server_handle_completes_the_accepted_chain():
    npc = _npc("全程翁", LOC_A)
    _npc("全程远客", LOC_B)
    r = WORLD.join(f"委托全程客{_uniq('')}")
    tok = r["token"]
    char = WORLD.get_char(tok)
    npc.location = char.location
    CharacterRepository.save(npc)
    res = WORLD.handle(tok, f"/接委托 {npc.name}")
    assert res["ok"], res
    char = WORLD.get_char(tok)
    reward = char.active_quest.reward_stones
    stones0 = char.spirit_stones
    # 不换链：按接到的链逐环构造核验条件，经 handle /交付 真推进到完结
    for _ in range(6):
        char = WORLD.get_char(tok)
        if char.active_quest is None:
            break
        ring = char.active_quest.rings[char.active_quest.ring_index]
        if ring.kind == "fetch":
            char.inventory.append(ring.item_name)
        elif ring.kind == "slay":
            ring.progress = ring.need
        target = CharacterRepository.get_by_id(ring.deliver_npc_id)
        char.location = target.location
        CharacterRepository.save(char)
        res = WORLD.handle(tok, "/交付")
        assert res["ok"], res
    char = WORLD.get_char(tok)
    assert char.active_quest is None
    assert char.spirit_stones == stones0 + reward
    print("✓ server handle 接取的原链全程交付落库")
