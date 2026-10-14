"""
锁妖古窟探索与 Roguelike 流程单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core.dungeon import DungeonEngine, _KEY


def _make_char(name="凌霄散人", stones=200):
    c = WorldClock.create_new_character(f"d_{name}", name)
    c.spirit_stones = stones
    c.realm.tier = 2
    c.realm.sub_tier = 1
    CharacterRepository.save(c)
    return c


def test_dungeon_start_and_fee():
    init_db()
    WorldStateRepository.delete(_KEY)
    c = _make_char("试探者", stones=100)

    res = DungeonEngine.start_dungeon(c, floor=1)
    assert res["success"] is True
    assert c.spirit_stones == 70  # 扣除了 30 灵石
    sess = res["session"]
    assert sess["floor"] == 1
    assert len(sess["nodes"]) >= 2
    assert sess["active"] is True


def test_dungeon_combat_and_stash():
    init_db()
    WorldStateRepository.delete(_KEY)
    c = _make_char("斩妖者", stones=200)

    # 启动古窟
    res = DungeonEngine.start_dungeon(c, floor=1)
    sess = res["session"]

    # 若当前节点是战斗，多次执行法宝大招与火系神通直到怪物被击杀
    if sess["state"] == "battle":
        # 释放法宝神威
        r1 = DungeonEngine.execute_combat_action(c, action="treasure")
        assert r1["success"] is True
        # 普攻或火炎持续输出直到战胜
        for _ in range(10):
            s = DungeonEngine.get_session(c.id)
            if not s or s.get("state") != "battle":
                break
            DungeonEngine.execute_combat_action(c, action="spell", spell_key="fire_blast")

        updated_sess = DungeonEngine.get_session(c.id)
        assert updated_sess is not None
        # 击败后战利品已暂存在 stash 中
        assert updated_sess["stash"]["stones"] > 0


def test_dungeon_retreat_and_award():
    init_db()
    WorldStateRepository.delete(_KEY)
    c = _make_char("撤退者", stones=100)

    DungeonEngine.start_dungeon(c, floor=1)
    sess = DungeonEngine.get_session(c.id)
    # 人为将当前状态置为非战斗（如灵泉或通关），并塞入暂存战利品
    sess["state"] = "event"
    sess["monster"] = None
    sess["stash"] = {
        "stones": 88,
        "items": [{"name": "千年朱果", "count": 1}]
    }
    WorldStateRepository.set(_KEY, {c.id: sess})

    # 捏碎遁符安全撤离
    ret = DungeonEngine.retreat(c)
    assert ret["success"] is True
    assert ret["stones"] == 88

    # 验证人物身上已真正获得 88 灵石
    reloaded = CharacterRepository.get_by_id(c.id)
    assert reloaded.spirit_stones == (70 + 88)

    # 验证会话已清除
    assert DungeonEngine.get_session(c.id) is None


def test_dungeon_boon_choice():
    init_db()
    WorldStateRepository.delete(_KEY)
    c = _make_char("顿悟者", stones=100)

    DungeonEngine.start_dungeon(c, floor=1)
    sess = DungeonEngine.get_session(c.id)
    sess["state"] = "choosing_boon"
    sess["boon_choices"] = [
        {"key": "pure_yang", "name": "纯阳烈煞"},
        {"key": "iron_wall", "name": "不动如山"},
        {"key": "sword_heart", "name": "剑心通明"},
    ]
    WorldStateRepository.set(_KEY, {c.id: sess})

    # 领悟纯阳烈煞
    ans = DungeonEngine.choose_boon(c, "pure_yang")
    assert ans["success"] is True
    assert "pure_yang" in ans["session"]["boons"]
    assert ans["session"]["state"] == "floor_cleared"
