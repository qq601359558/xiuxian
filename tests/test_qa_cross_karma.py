"""QA 审计 · 域4 因果账 + 域6.1 除凶令洗清终态（探索性测试，失败即缺陷证据）"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core import hunt
from core.atlas import AtlasEngine
from core.clock import WorldClock
from core.models import CharacterStatus, QuestChain, QuestRing
from core.quests import QuestEngine, QUEST_REWARD_MERIT
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"   # 东荒·青州
REGION_A = "东荒·青州"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, loc=LOC_A, sin=0, sect=None, npc=False):
    prefix = "npc_qa_" if npc else "qa_"
    c = WorldClock.create_new_character(f"{prefix}{name}_{_tag()}", f"QA{name}{_tag()}")
    c.location = loc
    if sect:
        c.sect = sect
    if sin:
        c.karma.add_sin(sin)
    CharacterRepository.save(c)
    return c


def _cleanup_hunt(*chars):
    ids = {c.id for c in chars if c}
    if ids:
        orders = hunt._load_orders()
        for tid in list(orders.keys()):
            if tid in ids:
                orders.pop(tid, None)
        hunt._save_orders(orders)
        d = hunt._load()
        for hid in list(d.keys()):
            rec = d[hid]
            tid = rec.get("target_id") if isinstance(rec, dict) else rec
            if hid in ids or tid in ids:
                d.pop(hid, None)
        hunt._save(d)
    for c in chars:
        if c is None:
            continue
        live = CharacterRepository.get_by_id(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


def _merit(cid):
    return CharacterRepository.get_by_id(cid).karma.merit_value


def _sin(cid):
    return CharacterRepository.get_by_id(cid).karma.sin_value


# ---------------- 域4.1 settle_kill 业力账：spec −20 vs 实际落账 ----------------

def test_settle_kill_sin_delta_matches_spec():
    """hunt spec（既有口径）：击杀者功德 +40 / 业力 −20。
    猎手 sin=100 时结算，落账业力应恰 −20 → 80。
    疑似点：add_merit(40) 自带业力消解 −20（40//2），与显式 −20 叠加。"""
    victim = _char("账凶", sin=120)
    hunter = _char("账猎", sin=100)
    try:
        assert hunt.accept(CharacterRepository.get_by_id(hunter.id), victim.name)["success"]
        m0, s0 = _merit(hunter.id), _sin(hunter.id)
        assert s0 == 100
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(hunter.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None
        assert _merit(hunter.id) == m0 + 40, f"功德应 +40，实际 {_merit(hunter.id) - m0}"
        got = _sin(hunter.id)
        assert got == s0 - 20, (
            f"业力按 spec 应 −20 → {s0 - 20}，实际 {got}（总消解 {s0 - got}）；"
            f"settle_kill 返回值自报 sin_reduced={res.get('sin_reduced')}"
        )
    finally:
        _cleanup_hunt(victim, hunter)


# ---------------- 域6.1 凶犯洗清后被击杀：令应消散、无协剿 ----------------

def test_washed_target_kill_dissolves_order_no_assist():
    """hunt spec：凶犯血煞到期+业力降至阈值下（洗清），令须消散并清猎手记录。
    场景：发令+两名猎手接令后、任何看板/追凶访问之前，凶犯洗清，随即被主猎手击杀。
    期望：令 DISSOLVED、同场协剿者功德 +0。"""
    victim = _char("洗凶", sin=120)
    killer = _char("洗猎主", loc=LOC_A)
    assist = _char("洗猎协", loc=LOC_A)
    try:
        assert hunt.accept(CharacterRepository.get_by_id(killer.id), victim.name)["success"]
        assert hunt.accept(CharacterRepository.get_by_id(assist.id), victim.name)["success"]
        order = hunt.get_order(victim.id)
        assert order and order["status"] == hunt.ORDER_OPEN
        # 洗清：业力归 0、血煞标记清除（不经任何看板/追凶/接令访问点）
        v = CharacterRepository.get_by_id(victim.id)
        v.karma.sin_value = 0
        v.karma.blood_mark_until = 0.0
        CharacterRepository.save(v)
        assert not hunt.is_marked(CharacterRepository.get_by_id(victim.id))
        a0 = _merit(assist.id)
        res = hunt.settle_kill(
            CharacterRepository.get_by_id(killer.id),
            CharacterRepository.get_by_id(victim.id),
        )
        assert res is not None, "主猎手旧口径结算应成立（其猎手记录仍指向凶犯）"
        after = hunt.get_order(victim.id)
        assert after["status"] == hunt.ORDER_DISSOLVED, (
            f"洗清后击杀：令应 DISSOLVED（spec），实际 {after['status']}；"
            f"协剿发放 {res.get('assists')}"
        )
        assert _merit(assist.id) == a0, f"洗清后协剿不应发功德，实际 +{_merit(assist.id) - a0}"
    finally:
        _cleanup_hunt(victim, killer, assist)


# ---------------- 域4.2 委托整链完成：四路钩子各恰一次 ----------------

def test_quest_completion_hooks_fire_exactly_once():
    """一次整链交付应同时且恰一次触发：委托奖（灵石+功德5）、灵感 +2（F11）、
    版图 quest +6（F09，当环交付区域）。快照前后差对账。"""
    pub = _char("委翁", npc=True)
    player = _char("委客", sect="青云宗")
    key = f"sect_atlas:{REGION_A}"
    atlas_before_raw = WorldStateRepository.get(key)
    try:
        ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=pub.id,
                         deliver_npc_name=pub.name, item_name="聚灵草", need=1)
        now = time.time()
        player.active_quest = QuestChain(
            publisher_id=pub.id, publisher_name=pub.name, rings=[ring], ring_index=0,
            accepted_at=now, expires_at=now + 86400, reward_stones=100,
            reward_merit=QUEST_REWARD_MERIT,
        )
        player.inventory.append("聚灵草")
        player.inspiration = 0
        CharacterRepository.save(player)
        inf0 = AtlasEngine.influence_map(REGION_A).get("青云宗", 0.0)
        s0, m0, insp0 = player.spirit_stones, player.karma.merit_value, player.inspiration
        live = CharacterRepository.get_by_id(player.id)
        res = QuestEngine.deliver(live)
        assert res["success"], res
        CharacterRepository.save(live)  # deliver 为 dirty 模式：调用方落库（与 world/cli 同口径）
        after = CharacterRepository.get_by_id(player.id)
        assert after.spirit_stones - s0 == 100, f"委托灵石应 +100，实际 {after.spirit_stones - s0}"
        assert after.karma.merit_value - m0 == QUEST_REWARD_MERIT, (
            f"委托功德应 +{QUEST_REWARD_MERIT}，实际 {after.karma.merit_value - m0}"
        )
        assert after.inspiration - insp0 == 2, f"灵感应 +2，实际 {after.inspiration - insp0}"
        inf1 = AtlasEngine.influence_map(REGION_A).get("青云宗", 0.0)
        assert abs((inf1 - inf0) - 6.0) < 0.1, f"版图 quest 应 +6，实际 {inf1 - inf0}"
        # 链已清：二次交付必须失败且零发放（幂等复核）
        res2 = QuestEngine.deliver(CharacterRepository.get_by_id(player.id))
        assert not res2["success"]
        after2 = CharacterRepository.get_by_id(player.id)
        assert after2.spirit_stones == after.spirit_stones and after2.inspiration == after.inspiration
    finally:
        if atlas_before_raw is None:
            WorldStateRepository.delete(key)
        else:
            WorldStateRepository.set(key, atlas_before_raw)
        _cleanup_hunt(pub, player)
