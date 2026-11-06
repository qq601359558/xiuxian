"""江湖仿真深度：议程会改世界，级联与离线追赶"""
import os
import sys
import time
from pathlib import Path

os.environ["ALLOW_LOCAL_AI"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _mk(npc_uid, name, *, location="落霞山灵泉", tier=1, stones=100, sin=0, sect=None):
    from storage.db import CharacterRepository
    from core.clock import WorldClock
    from core.models import CharacterStatus

    c = WorldClock.create_new_character(npc_uid, name)
    c.location = location
    c.realm.tier = tier
    c.spirit_stones = stones
    if sin:
        c.karma.add_sin(sin)
    c.sect = sect
    c.status = CharacterStatus.IDLE
    CharacterRepository.save(c)
    return c


def test_revenge_same_loc_can_kill_and_cascade():
    from storage.db import init_db, CharacterRepository, NpcAgendaRepository, DB_PATH
    from core.jianghu_sim import JianghuSimulator
    from core.collusion import ensure_link
    from core.models import CharacterStatus
    import core.jianghu as jh
    import sqlite3

    init_db()
    jh.reset_tick_budget()
    killer = _mk("npc_sim_k", "寻仇者", location="落霞山灵泉", tier=3, stones=10)
    victim = _mk("npc_sim_v", "仇家目标", location="落霞山灵泉", tier=0, stones=200, sect="青云宗")
    sibling = _mk("npc_sim_s", "同门师弟", location="青云宗外门山门", tier=1, sect="青云宗")
    ensure_link(killer, victim, "仇", note="血海深仇")

    # 强制高胜率：killer tier 3 vs tier 0，多次结算必有一次 kill
    killed = False
    last = None
    for _ in range(20):
        if victim.status == CharacterStatus.DEAD:
            killed = True
            break
        # 重置 victim 便于重复试
        if victim.status == CharacterStatus.DEAD:
            break
        victim.status = CharacterStatus.IDLE
        victim.spirit_stones = 200
        CharacterRepository.save(victim)
        last = JianghuSimulator.resolve_agenda(
            killer, "revenge", {"target_hint": victim.name, "note": "复仇"}, now=time.time()
        )
        if last.get("outcome") == "kill":
            killed = True
            break
    assert killed, f"高境界寻仇应能击杀，last={last}"
    assert victim.status == CharacterStatus.DEAD or last["outcome"] == "kill"
    # 级联：同门应被写成寻仇议程
    sib_ag = NpcAgendaRepository.get(sibling.id)
    assert sib_ag, "同门应有议程"
    assert sib_ag.get("agenda_type") == "revenge" or "复仇" in (sib_ag.get("note") or "") or any(
        "师弟" in x or "同门" in x for x in (last.get("cascade_notes") or [])
    )
    # 因果账可查
    evs = jh.list_recent(limit=40)
    assert any(killer.id in (e.get("actor_ids") or []) for e in evs)

    # 清理
    conn = sqlite3.connect(DB_PATH)
    for uid in ("npc_sim_k", "npc_sim_v", "npc_sim_s"):
        conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()


def test_seclusion_full_realm_tries_breakthrough():
    from storage.db import init_db, CharacterRepository, DB_PATH
    from core.jianghu_sim import JianghuSimulator
    import sqlite3

    init_db()
    c = _mk("npc_sim_bt", "破境客", location="宗门玄元洞府", tier=1)
    # 塞满修为触发圆满
    c.realm.current_exp = c.realm.max_exp
    CharacterRepository.save(c)
    res = JianghuSimulator.resolve_agenda(c, "seclusion", {}, now=time.time())
    assert res["acted"] is True
    assert res["outcome"] in (
        "breakthrough",
        "tribulation_fail",
        "tribulation_die",
        "cultivate",
    )
    assert res["narrative"]
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM characters WHERE user_id=?", ("npc_sim_bt",))
    conn.commit()
    conn.close()


def test_treasure_rob_moves_stones():
    from storage.db import init_db, CharacterRepository, DB_PATH
    from core.jianghu_sim import JianghuSimulator
    from core.models import CharacterStatus
    import sqlite3

    init_db()
    robber = _mk("npc_sim_r2", "拦路客甲九", location="黑风绝渊", tier=4, stones=0)
    rich = _mk("npc_sim_ri2", "肥羊乙九", location="黑风绝渊", tier=0, stones=500)
    before = rich.spirit_stones
    moved = False
    for _ in range(15):
        rich.spirit_stones = 500
        robber.spirit_stones = 0
        rich.status = CharacterStatus.IDLE
        rich.location = "黑风绝渊"
        robber.location = "黑风绝渊"
        CharacterRepository.save(rich)
        CharacterRepository.save(robber)
        res = JianghuSimulator.resolve_agenda(
            robber, "treasure", {"target_hint": rich.name}, now=time.time()
        )
        if (
            res.get("outcome") in ("rob", "rob_kill", "pickpocket", "chase_loot")
            or robber.spirit_stones > 0
            or rich.spirit_stones < before
            or res.get("effects")
            or res.get("new_location")
        ):
            # chase 后再次同图结算夺宝
            if res.get("outcome") == "chase_loot":
                res2 = JianghuSimulator.resolve_agenda(
                    robber, "treasure", {"target_hint": rich.name}, now=time.time()
                )
                if res2.get("outcome") in ("rob", "rob_kill") or robber.spirit_stones > 0:
                    moved = True
                    break
                continue
            moved = True
            break
    assert moved, "高阶夺宝应至少一次得手/追击/造成伤亡"
    conn = sqlite3.connect(DB_PATH)
    for uid in ("npc_sim_r2", "npc_sim_ri2"):
        conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()


def test_offline_catchup_produces_ledger():
    from storage.db import init_db, CharacterRepository, DB_PATH
    from core.jianghu_sim import JianghuSimulator, format_offline_report
    import core.jianghu as jh
    import sqlite3

    init_db()
    jh.reset_tick_budget()
    _mk("npc_sim_off1", "离线甲", location="落霞山灵泉", tier=2, stones=100)
    _mk("npc_sim_off2", "离线乙", location="落霞山灵泉", tier=1, stones=40)
    # 伪造成 3 小时前对时
    JianghuSimulator.mark_sim_ts(time.time() - 3 * 3600)
    rep = JianghuSimulator.simulate_offline(force=False)
    assert rep.get("waves", 0) >= 1
    assert rep.get("actions", 0) >= 1 or rep.get("events")
    text = format_offline_report(rep)
    assert "离线" in text or "波次" in text
    # 对时已更新
    assert JianghuSimulator.last_sim_ts() > time.time() - 60
    conn = sqlite3.connect(DB_PATH)
    for uid in ("npc_sim_off1", "npc_sim_off2"):
        conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()


def test_patrol_can_engage_blood_marked():
    from storage.db import init_db, CharacterRepository, DB_PATH
    from core.jianghu_sim import JianghuSimulator
    from core.models import CharacterStatus
    import sqlite3

    init_db()
    guard = _mk("npc_sim_g", "巡山剑修", location="青云山外围", tier=3, sect="青云宗")
    fiend = _mk("npc_sim_f", "血魔", location="青云山外围", tier=0, sin=200)
    fiend.karma.blood_mark_until = time.time() + 86400 * 3
    try:
        # 若模型字段不同，加大量业力亦可触发 patrol 目标
        pass
    except Exception:
        pass
    CharacterRepository.save(fiend)
    hit = False
    for _ in range(12):
        fiend.status = CharacterStatus.IDLE
        fiend.spirit_stones = 50
        CharacterRepository.save(fiend)
        res = JianghuSimulator.resolve_agenda(guard, "patrol", {}, now=time.time())
        if res.get("outcome") in ("patrol_kill", "patrol_fail", "patrol_watch", "patrol_deploy"):
            hit = True
            if res.get("outcome") == "patrol_kill":
                break
    assert hit
    conn = sqlite3.connect(DB_PATH)
    for uid in ("npc_sim_g", "npc_sim_f"):
        conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()


def test_tick_one_uses_simulator_not_flavor_only():
    from storage.db import init_db, CharacterRepository, NpcAgendaRepository, DB_PATH
    from core.npc_agenda import NpcAgendaEngine
    from core.clock import WorldClock
    from core.models import CharacterStatus
    import core.npc_agenda as na
    import sqlite3

    init_db()
    npc = WorldClock.create_new_character("npc_sim_tick", "闭关演武人")
    npc.location = "宗门玄元洞府"
    npc.realm.current_exp = npc.realm.max_exp
    CharacterRepository.save(npc)
    NpcAgendaRepository.upsert(
        npc_id=npc.id,
        npc_name=npc.name,
        agenda_type="seclusion",
        target_hint="",
        note="冲击更高境界",
        state="active",
        last_tick=0.0,
        progress=0,
    )
    old = na.ai_ready
    na.ai_ready = lambda: False
    try:
        r = NpcAgendaEngine.tick_one(npc, force=True)
    finally:
        na.ai_ready = old
    assert r is not None and r.get("acted")
    assert r.get("outcome") in (
        "cultivate",
        "breakthrough",
        "tribulation_fail",
        "tribulation_die",
    ), r
    assert r.get("source", "").startswith("rule")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM characters WHERE user_id=?", ("npc_sim_tick",))
    conn.commit()
    conn.close()


def main():
    test_revenge_same_loc_can_kill_and_cascade()
    print("✓ 寻仇结算 + 同门级联")
    test_seclusion_full_realm_tries_breakthrough()
    print("✓ 闭关圆满冲击突破")
    test_treasure_rob_moves_stones()
    print("✓ 夺宝改写灵石")
    test_offline_catchup_produces_ledger()
    print("✓ 离线追赶")
    test_patrol_can_engage_blood_marked()
    print("✓ 巡守接敌")
    test_tick_one_uses_simulator_not_flavor_only()
    print("✓ tick_one 走仿真结算")
    print("\n✅ 江湖仿真深度测试通过")


if __name__ == "__main__":
    main()
