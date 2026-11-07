"""game-feel-phase2 线一后端验收（Spec game-feel-phase2）。

覆盖：§2 S4-01~S4-05（幂等键收紧）、§3 FT-*（命途主线）、
§4 VD-*（世仇）、§7 EP-*（评语润色）、§8 UI-* 后端侧。
播种口径沿一期：唯一 uid 后缀 + WorldClock 建角，rng 注入可复算。
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")
os.environ.setdefault("USE_CCSWITCH", "0")

from config import SECONDS_PER_GAME_DAY
from core.clock import WorldClock
from core.goals import GoalEngine
from storage.db import CharacterRepository, init_db

init_db()

LOC = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name="试炼者", uid_prefix="gf2", location=LOC, save=False):
    c = WorldClock.create_new_character(f"{uid_prefix}_{name}_{_tag()}", f"{name}{_tag()}")
    c.location = location
    if save:
        CharacterRepository.save(c)
        return CharacterRepository.get_by_id(c.id)
    return c


def _npc(name="试炼NPC", tier=1, location=LOC, sect=""):
    c = WorldClock.create_new_character(f"npc_gf2_{name}_{_tag()}", f"{name}{_tag()}")
    c.realm.tier = tier
    c.location = location
    c.sect = sect
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


# ================= §2 S-4 幂等键收紧 =================

def test_s4_01_instance_key_allows_parallel_and_dedups_same_instance():
    char = _char("S4甲")
    chk = {"kind": "chain_resolved", "ref": "npc_x"}
    g1 = GoalEngine.add_checked_goal(
        char, source="origin", title="章一", detail="d", check=dict(chk),
        instance="ft_abc:c1")
    g2 = GoalEngine.add_checked_goal(
        char, source="origin", title="章二", detail="d", check=dict(chk),
        instance="ft_abc:c2")
    assert g1["id"] != g2["id"]
    assert g1["status"] == g2["status"] == "active"
    assert g1["check"]["instance"] == "ft_abc:c1"
    n_before = len(char.goals)
    g1b = GoalEngine.add_checked_goal(
        char, source="origin", title="章一重挂", detail="d", check=dict(chk),
        instance="ft_abc:c1")
    assert g1b["id"] == g1["id"], "同 instance 重挂须命中幂等返回既有项"
    assert len(char.goals) == n_before


def test_s4_02_legacy_no_instance_compat():
    char = _char("S4乙")
    legacy_goal = {
        "id": "g_origin_legacy1", "source": "origin", "title": "旧目标",
        "detail": "d", "status": "active", "progress": 0,
        "created_at": time.time(), "tier": "short",
        "check": {"kind": "stones_at_least", "amount": 100}, "deadline_at": 0.0,
    }
    char.goals = [legacy_goal]
    # 无 instance 重挂 → 一期行为：返回既有项不新增
    again = GoalEngine.add_checked_goal(
        char, source="origin", title="新", detail="d",
        check={"kind": "stones_at_least", "amount": 100})
    assert again["id"] == "g_origin_legacy1"
    assert len(char.goals) == 1
    # 带 instance 重挂 → 新增成功且旧项仍 active
    new = GoalEngine.add_checked_goal(
        char, source="origin", title="新二", detail="d",
        check={"kind": "stones_at_least", "amount": 100},
        instance="ft_xyz:c1")
    assert new["id"] != "g_origin_legacy1"
    assert len(char.goals) == 2
    assert char.goals[0]["status"] == "active"


def test_s4_03_missing_ref_no_collision_with_instance():
    char = _char("S4丙")
    chk = {"kind": "npc_attitude_at_least", "npc_id": "npc_1", "value": 10}  # 无 ref 键
    g1 = GoalEngine.add_checked_goal(
        char, source="origin", title="甲", detail="d", check=dict(chk),
        instance="ft_a:c1")
    g2 = GoalEngine.add_checked_goal(
        char, source="origin", title="乙", detail="d", check=dict(chk),
        instance="ft_a:c2")
    assert g1["id"] != g2["id"], "无 ref 目标不得因 ref=None 互撞"
    # 两条均无 ref 且均无 instance → 仍互斥（一期行为）
    char2 = _char("S4丁")
    h1 = GoalEngine.add_checked_goal(
        char2, source="origin", title="甲", detail="d", check=dict(chk))
    h2 = GoalEngine.add_checked_goal(
        char2, source="origin", title="乙", detail="d", check=dict(chk))
    assert h1["id"] == h2["id"] and len(char2.goals) == 1


def test_s4_05_evaluation_does_not_cross_instances():
    char = _char("S4戊")
    char.spirit_stones = 0
    t0 = time.time()
    chk = {"kind": "stones_at_least", "amount": 10 ** 9}
    g1 = GoalEngine.add_checked_goal(
        char, source="origin", title="短限", detail="d", check=dict(chk),
        deadline_days=1, instance="ft_e:c1", now=t0)
    g2 = GoalEngine.add_checked_goal(
        char, source="origin", title="长限", detail="d", check=dict(chk),
        deadline_days=10, instance="ft_e:c2", now=t0)
    flipped = GoalEngine.evaluate_checked_goals(
        char, t0 + 2 * SECONDS_PER_GAME_DAY)
    assert [g["id"] for g in flipped] == [g1["id"]]
    assert g1["status"] == "failed"
    assert g2["status"] == "active", "instance 不参与求值，到期只翻转到期者"
