"""
depth-polish：师门任务/叛师/日环主题/除凶限时/反悬赏/世情追
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository, KarmaLinkRepository
from core.clock import WorldClock
from core import social_bonds as sb
from core import sect_contrib as sc
from core import hunt
from core.schedule import format_world_schedule, follow_action


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
    blood = _p("煞星", tier=2, loc="落霞山灵泉(野外)")
    blood.karma.add_sin(100)
    CharacterRepository.save(blood)
    r = format_world_schedule(viewer_id=v.id)
    assert "B1" in r["text"] or "血煞" in r["text"]
    # /追 B1
    res = follow_action(CharacterRepository.get_by_id(v.id), "B1")
    assert res["success"] is True, res
    assert hunt.my_target(CharacterRepository.get_by_id(v.id)) is not None
    print("✓ 世情 /追 B1 接令")


if __name__ == "__main__":
    test_master_task_and_rebel()
    test_graduate_credit()
    test_theme_ring()
    test_rare_shop_locked()
    test_hunt_timeout_and_counter()
    test_schedule_follow()
    print("\n✅ depth-polish 测试通过")
