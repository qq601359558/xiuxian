"""
锁妖古窟与神通系统在 World 接口层的端到端链路测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core.dungeon import _KEY
from server.world import World


def test_world_status_and_dungeon_commands():
    init_db()
    WorldStateRepository.delete(_KEY)
    ws = World()

    # 1. 玩家加入世界
    join_res = ws.join("古窟行者", user_id="u_dg_link_01")
    token = join_res["token"]
    char = CharacterRepository.get_by_name("古窟行者")
    char.spirit_stones = 300
    char.realm.tier = 2
    char.realm.sub_tier = 1
    CharacterRepository.save(char)

    # 2. 检查 _status_dict 字段投影
    st = ws._status_dict(char)
    assert "dungeon" in st
    assert "spells_catalog" in st
    assert len(st["spells_catalog"]) >= 5
    assert "dungeon_floors" in st
    assert len(st["dungeon_floors"]) == 9

    # 3. 发送 /禁地 叩关 1
    r_enter = ws.handle(token, "/禁地 叩关 1")
    assert r_enter["ok"] is True
    assert "status" in r_enter
    dg_sess = r_enter["status"]["dungeon"]
    assert dg_sess is not None
    assert dg_sess["floor"] == 1
    assert dg_sess["active"] is True

    # 4. 执行战斗出招 /施法 fire_blast 或 /出招
    if dg_sess["state"] == "battle":
        r_cast = ws.handle(token, "/施法 fire_blast")
        assert r_cast["ok"] is True
        assert "status" in r_cast
        assert r_cast["status"]["dungeon"] is not None

        if r_cast["status"]["dungeon"] and r_cast["status"]["dungeon"]["state"] == "battle":
            r_atk = ws.handle(token, "/出招")
            assert r_atk["ok"] is True

    # 5. 人工置为 event 状态后执行 /禁地 撤离
    dg_sess["state"] = "event"
    dg_sess["monster"] = None
    dg_sess["stash"]["stones"] = 66
    WorldStateRepository.set(_KEY, {char.id: dg_sess})

    r_retreat = ws.handle(token, "/禁地 撤离")
    assert r_retreat["ok"] is True
    assert "安全归仓" in r_retreat["text"]
    assert r_retreat["status"]["dungeon"] is None
