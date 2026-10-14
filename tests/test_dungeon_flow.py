"""
锁妖古窟探索、五行连携、道韵顿悟与安全撤离/濒死惩罚全流程端到端测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core.dungeon import DungeonEngine, _KEY
from core.spells import CombatEntity, SpellCombatEngine
from server.world import World


def test_full_dungeon_core_loop():
    init_db()
    WorldStateRepository.delete(_KEY)
    ws = World()

    # 1. 玩家入道
    join_res = ws.join("凌霄剑仙", user_id="u_dg_full_01")
    token = join_res["token"]
    char = CharacterRepository.get_by_name("凌霄剑仙")
    char.spirit_stones = 500
    char.realm.tier = 3
    char.realm.sub_tier = 1
    CharacterRepository.save(char)

    # 2. 叩关开启锁妖古窟第 3 层 (考验水火连携)
    r_enter = ws.handle(token, "/禁地 叩关 3")
    assert r_enter["ok"] is True
    assert char.spirit_stones == 500  # 重新查询前本地
    reloaded_c = CharacterRepository.get_by_id(char.id)
    assert reloaded_c.spirit_stones == 470  # 服务端已扣除 30 灵石
    st1 = r_enter["status"]
    dg1 = st1["dungeon"]
    assert dg1 is not None
    assert dg1["floor"] == 3
    assert dg1["active"] is True

    # 3. 战斗交锋：使用水系玄冰寒煞魄 + 火系九幽地煞火触发水火阴阳爆燃！
    if dg1["state"] == "battle":
        # 施展水系神通冻结
        r_water = ws.handle(token, "/施法 water_freeze")
        assert r_water["ok"] is True
        dg_water = r_water["status"]["dungeon"]

        # 若怪物尚存，施展火系神通触发爆燃
        if dg_water and dg_water["state"] == "battle" and dg_water.get("monster"):
            r_fire = ws.handle(token, "/施法 fire_blast")
            assert r_fire["ok"] is True
            assert any("爆燃" in line or "真火" in line for line in r_fire.get("text", "").split("\n"))

    # 4. 模拟推进本层节点直至荡平
    sess = DungeonEngine.get_session(char.id)
    for n in sess["nodes"]:
        n["cleared"] = True
    sess["monster"] = None
    sess["state"] = "choosing_boon"
    sess["boon_choices"] = [
        {"key": "pure_yang", "name": "纯阳烈煞", "icon": "🔥", "desc": "火系伤害+35%"},
        {"key": "iron_wall", "name": "不动如山", "icon": "🛡️", "desc": "灵盾+40%"},
        {"key": "sword_heart", "name": "剑心通明", "icon": "⚡", "desc": "剑气破盾1.5倍"},
    ]
    sess["stash"] = {
        "stones": 120,
        "items": [{"name": "千年朱果", "count": 1}, {"name": "筑基丹", "count": 1}],
    }
    WorldStateRepository.set(_KEY, {char.id: sess})

    # 5. 领悟道韵
    r_boon = ws.handle(token, "/择道韵 pure_yang")
    assert r_boon["ok"] is True
    assert "pure_yang" in r_boon["status"]["dungeon"]["boons"]
    assert r_boon["status"]["dungeon"]["state"] == "floor_cleared"

    # 6. 深入下一层 (第 4 层)
    r_next = ws.handle(token, "/禁地 深入")
    assert r_next["ok"] is True
    assert r_next["status"]["dungeon"]["floor"] == 4

    # 7. 见好就收，捏碎遁符安全撤离
    sess_f2 = DungeonEngine.get_session(char.id)
    sess_f2["state"] = "event"
    sess_f2["monster"] = None
    WorldStateRepository.set(_KEY, {char.id: sess_f2})

    r_retreat = ws.handle(token, "/禁地 撤离")
    assert r_retreat["ok"] is True
    assert "安全归仓" in r_retreat["text"]
    assert r_retreat["status"]["dungeon"] is None

    # 验证最终战利品真正入账（470 + 120 = 590 灵石）
    final_char = CharacterRepository.get_by_id(char.id)
    assert final_char.spirit_stones == 590


def test_defeat_and_penalty():
    init_db()
    WorldStateRepository.delete(_KEY)
    c = WorldClock.create_new_character("u_dg_die", "莽撞散修")
    c.spirit_stones = 100
    c.karma.dao_heart = 100
    CharacterRepository.save(c)

    # 开启古窟
    DungeonEngine.start_dungeon(c, floor=1)
    sess = DungeonEngine.get_session(c.id)
    sess["stash"] = {"stones": 50, "items": [{"name": "凝血草", "count": 2}]}

    # 模拟玩家在战斗中被击杀 (hp <= 0)
    p_ent = CombatEntity.from_dict(sess["player"])
    m_ent = CombatEntity.from_dict(sess["monster"])
    p_ent.hp = 1
    m_ent.attack = 100

    # 怪物一击将玩家打死
    res = SpellCombatEngine.step_round(p_ent, m_ent, action="attack")
    assert res["ended"] is True
    assert res["winner"] == "monster"

    # 触发阵亡逻辑
    DungeonEngine._handle_defeat(c, sess)
    assert sess["state"] == "defeated"
    assert sess["stash"]["stones"] == 0  # 战利品遗失

    reloaded = CharacterRepository.get_by_id(c.id)
    assert reloaded.location == "青云坊市客栈"  # 被传送回客栈
    assert reloaded.karma.dao_heart == 97  # 道心受损 -3
