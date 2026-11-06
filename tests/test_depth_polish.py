"""
depth-polish：师门任务/叛师/日环主题/除凶限时/反悬赏/世情追
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository, KarmaLinkRepository
from core.clock import WorldClock
from core.models import CharacterStatus
from core import social_bonds as sb
from core import sect_contrib as sc
from core import hunt
from core.schedule import format_world_schedule, follow_action, _ACTIONS_KEY


def _p(name, tier=1, stones=300, loc="青云坊市客栈", sect=None):
    c = WorldClock.create_new_character(f"dp_{name}", name)
    c.realm.tier = tier
    c.spirit_stones = stones
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    if sect:
        c.sect = sect
        c.sect_rank = "外门弟子"
    CharacterRepository.save(c)
    return c


def test_master_task_and_rebel():
    init_db()
    WorldStateRepository.delete(sb._PENDING_KEY)
    WorldStateRepository.delete(sb._DAILY_KEY)
    m = _p("严师", tier=3)
    d = _p("劣徒", tier=1)
    sb.propose_master(d, "严师")
    sb.confirm_master(CharacterRepository.get_by_id(m.id))
    # 师门任务
    res = sb.format_master_task(CharacterRepository.get_by_id(d.id))
    assert res["success"] is True
    # 叛师
    r = sb.rebel_master(CharacterRepository.get_by_id(d.id), "严师")
    assert r["success"] is True, r
    assert any(l.link_type == "怨" for l in sb.links_between(m.id, d.id))
    print("✓ 师门任务+叛师")


def test_graduate_credit():
    init_db()
    WorldStateRepository.delete(sb._PENDING_KEY)
    WorldStateRepository.delete(sb._CREDIT_KEY)
    m = _p("考官", tier=3)
    d = _p("考生", tier=1)
    sb.propose_master(d, "考官")
    sb.confirm_master(CharacterRepository.get_by_id(m.id))
    assert sb.graduate(CharacterRepository.get_by_id(d.id))["success"] is False
    sb.mark_graduate_credit(CharacterRepository.get_by_id(d.id))
    # credit 单独还不够——需 strength 或境界；credit 在 graduate 里未直接用，测 has
    assert sb.has_graduate_credit(CharacterRepository.get_by_id(d.id))
    # 抬 strength
    for l in sb.links_between(m.id, d.id):
        if l.link_type == "师徒":
            l.strength = 3
            KarmaLinkRepository.save(l)
    assert sb.graduate(CharacterRepository.get_by_id(d.id))["success"] is True
    print("✓ 出师 credit+门槛")


def test_theme_ring():
    init_db()
    WorldStateRepository.delete(sc._RING_KEY)
    WorldStateRepository.delete("sect_streak")
    c = _p("环客", sect="青云宗")
    r = sc.accept_theme(CharacterRepository.get_by_id(c.id), 1)
    assert r["success"] is True, r
    hook = r.get("hook")
    # 完成 hook
    res = sc.sync_ring(CharacterRepository.get_by_id(c.id), hook)
    # 可能 None 若 hook 不匹配 accepted - accept 已设 hook
    assert res is not None, (hook, sc.ensure_daily_ring(c))
    assert res.get("streak") == 1
    print("✓ 日环主题接取完成")


def test_rare_shop_locked():
    init_db()
    c = _p("穷环客", sect="青云宗")
    c.sect_contribution = 500
    CharacterRepository.save(c)
    r = sc.exchange(CharacterRepository.get_by_id(c.id), "赤霄剑")
    assert r["success"] is False  # streak 0
    sc._set_streak(CharacterRepository.get_by_id(c.id), 5)
    r2 = sc.exchange(CharacterRepository.get_by_id(c.id), "赤霄剑")
    assert r2["success"] is True, r2
    print("✓ 稀有兑换解锁")


def test_hunt_timeout_and_counter():
    init_db()
    WorldStateRepository.delete(hunt._HUNT_KEY)
    WorldStateRepository.delete(hunt._COUNTER_KEY)
    h = _p("限时猎", tier=2, loc="落霞山灵泉(野外)")
    t = _p("待宰", tier=2, loc="落霞山灵泉(野外)")
    t.karma.add_sin(100)
    CharacterRepository.save(t)
    assert hunt.accept(h, "待宰")["success"] is True
    info = hunt.my_target_info(CharacterRepository.get_by_id(h.id))
    assert info and info["remain_h"] > 40
    # 过期
    d = hunt._load()
    d[h.id]["expires_at"] = time.time() - 10
    hunt._save(d)
    assert hunt.my_target(CharacterRepository.get_by_id(h.id)) is None
    # 重新接并反悬赏
    hunt.accept(CharacterRepository.get_by_id(h.id), "待宰")
    r = hunt.place_counter(CharacterRepository.get_by_id(t.id))
    assert r["success"] is True, r
    assert CharacterRepository.get_by_id(t.id).spirit_stones == 300 - 50
    print("✓ 限时+反悬赏")


def test_schedule_follow():
    init_db()
    WorldStateRepository.delete(hunt._HUNT_KEY)
    v = _p("观察者", loc="落霞山灵泉(野外)")
    # 密封（活库）：排程血煞榜按全库在世血煞业力降序取前 8，存量 NPC
    # 业力可达数百且可能与旧夹具重名——自造凶犯须唯一名 + 业力居首，
    # 再按名从 actions 定位本人条目代号，不假设必占 B1
    blood = _p("排程煞星", tier=2, loc="落霞山灵泉(野外)")
    blood.karma.add_sin(10000)
    CharacterRepository.save(blood)
    try:
        r = format_world_schedule(viewer_id=v.id)
        assert f"【{blood.name}】" in r["text"]
        marks = [a for a in r["actions"] if a.get("kind") == "mark"]
        idx = next(
            i for i, a in enumerate(marks) if a.get("name") == blood.name
        )
        res = follow_action(CharacterRepository.get_by_id(v.id), f"B{idx + 1}")
        assert res["success"] is True, res
        assert hunt.my_target(CharacterRepository.get_by_id(v.id)) is not None
    finally:
        # 零残留：摘除接令登记/令实体/猎手索引/排程动作缓存、自造两角置死，
        # 免自造血煞留在活库榜上干扰后续运行
        hunt._unregister_from_order(v.id, blood.id)
        orders = hunt._load_orders()
        if blood.id in orders:
            orders.pop(blood.id)
            hunt._save_orders(orders)
        d = hunt._load()
        if v.id in d:
            d.pop(v.id)
            hunt._save(d)
        sched = WorldStateRepository.get(_ACTIONS_KEY)
        if isinstance(sched, dict) and v.id in sched:
            sched.pop(v.id)
            WorldStateRepository.set(_ACTIONS_KEY, sched)
        for c in (v, blood):
            cc = CharacterRepository.get_by_id(c.id)
            if cc is not None:
                cc.status = CharacterStatus.DEAD
                CharacterRepository.save(cc)
    print("✓ 世情 /追 本人条目接令")


if __name__ == "__main__":
    test_master_task_and_rebel()
    test_graduate_credit()
    test_theme_ring()
    test_rare_shop_locked()
    test_hunt_timeout_and_counter()
    test_schedule_follow()
    print("\n✅ depth-polish 测试通过")
