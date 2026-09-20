"""
Wave2：师徒结拜 · 宗门贡献日环 · 除凶围剿 · 世情
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
from core.schedule import format_world_schedule
from core.collusion import ensure_link


def _p(name, tier=1, stones=200, loc="青云坊市客栈", sect=None, rank="外门弟子"):
    c = WorldClock.create_new_character(f"w2_{name}", name)
    c.realm.tier = tier
    c.spirit_stones = stones
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    if sect:
        c.sect = sect
        c.sect_rank = rank
    CharacterRepository.save(c)
    return c


def test_master_disciple():
    init_db()
    WorldStateRepository.delete(sb._PENDING_KEY)
    master = _p("师父", tier=3)
    disc = _p("弟子", tier=1)
    r1 = sb.propose_master(disc, "师父")
    assert r1["success"] is True, r1
    r2 = sb.confirm_master(CharacterRepository.get_by_id(master.id))
    assert r2["success"] is True, r2
    links = sb.links_between(master.id, disc.id)
    assert any(l.link_type == "师徒" for l in links)
    assert sb.transmit_cost_mult(master, disc) == 0.5
    # 出师门槛：strength 未到且境界差大 → 拒
    g_fail = sb.graduate(CharacterRepository.get_by_id(disc.id))
    assert g_fail["success"] is False
    # 抬 strength 后可出师
    for l in links:
        if l.link_type == "师徒":
            l.strength = 3
            KarmaLinkRepository.save(l)
    g = sb.graduate(CharacterRepository.get_by_id(disc.id))
    assert g["success"] is True, g
    print("✓ 拜师/确认/出师门槛")


def test_sworn():
    init_db()
    WorldStateRepository.delete(sb._PENDING_KEY)
    a = _p("兄")
    b = _p("弟")
    assert sb.propose_sworn(a, "弟")["success"] is True
    r = sb.accept_sworn(CharacterRepository.get_by_id(b.id))
    assert r["success"] is True, r
    assert sb.combat_sworn_bonus(a, b) == 0.05
    print("✓ 结拜同场加成")


def test_sect_contrib_donate_exchange():
    init_db()
    WorldStateRepository.delete(sc._RING_KEY)
    c = _p("上交客", sect="青云宗")
    c.inventory.append("百年灵芝")
    CharacterRepository.save(c)
    r = sc.donate_item(CharacterRepository.get_by_id(c.id), "百年灵芝", 1)
    assert r["success"] is True, r
    c = CharacterRepository.get_by_id(c.id)
    assert c.sect_contribution >= 1
    # 新日环：需先接主题才有 donate hook
    # 兑换
    c.sect_contribution = 20
    CharacterRepository.save(c)
    r2 = sc.exchange(CharacterRepository.get_by_id(c.id), "聚气丹")
    assert r2["success"] is True, r2
    c = CharacterRepository.get_by_id(c.id)
    assert "聚气丹" in c.inventory
    assert c.sect_contribution == 20 - 8
    print("✓ 上交/兑换")


def test_hunt_board_and_settle():
    init_db()
    WorldStateRepository.delete(hunt._HUNT_KEY)
    hunter = _p("猎人", tier=2, loc="落霞山灵泉(野外)")
    target = _p("血煞客", tier=2, loc="落霞山灵泉(野外)")
    target.karma.add_sin(120)
    CharacterRepository.save(target)
    board = hunt.format_board()
    assert "血煞客" in board
    r = hunt.accept(CharacterRepository.get_by_id(hunter.id), "血煞客")
    assert r["success"] is True, r
    res = hunt.settle_kill(CharacterRepository.get_by_id(hunter.id), CharacterRepository.get_by_id(target.id))
    assert res is not None
    h = CharacterRepository.get_by_id(hunter.id)
    assert h.karma.merit_value >= 40
    print("✓ 除凶榜/接令/结算")


def test_siege_multiplier():
    init_db()
    WorldStateRepository.delete(hunt._HUNT_KEY)
    a = _p("甲猎", tier=2, loc="落霞山灵泉(野外)")
    b = _p("乙猎", tier=2, loc="落霞山灵泉(野外)")
    t = _p("凶人", tier=2, loc="落霞山灵泉(野外)")
    t.karma.add_sin(100)
    CharacterRepository.save(t)
    hunt.accept(a, "凶人")
    hunt.accept(b, "凶人")
    m = hunt.siege_multiplier(a, CharacterRepository.get_by_id(t.id))
    assert m >= 1.15
    print("✓ 围剿系数", m)


def test_schedule_text():
    init_db()
    r = format_world_schedule()
    text = r["text"] if isinstance(r, dict) else r
    assert "世情" in text
    assert "NPC" in text or "血煞" in text
    print("✓ 世情日程")


if __name__ == "__main__":
    test_master_disciple()
    test_sworn()
    test_sect_contrib_donate_exchange()
    test_hunt_board_and_settle()
    test_siege_multiplier()
    test_schedule_text()
    print("\n✅ Wave2 测试通过")
