"""
藏宝图全链路端到端集成测试：
从在非目标灵穴勘探返回文言八卦方位指引，到御风前往目标灵穴成功破阵开匣
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from core.models import Character, ItemKind
from core.world_grid import WorldGridEngine
from core.treasure_system import TreasureEngine, TreasureArchetype
from server.world import World


def test_treasure_wrong_location_to_success_flow():
    init_db()
    ws = World()
    
    # 1. 创建角色，初始身处【青云坊市客栈】
    char = WorldClock.create_new_character("u_tmap_flow", "寻龙剑仙")
    char.location = "青云坊市客栈"
    CharacterRepository.save(char)
    tok = ws.join(char.name, user_id=char.user_id)["token"]
    
    # 2. 赋予玩家一张目标为【黑水沼泽】的地品五行破阵藏宝图
    tmap = TreasureEngine.generate_treasure_map(
        char,
        tier=3,
        preferred_target="黑水沼泽",
        preferred_archetype=TreasureArchetype.ELEMENT_PUZZLE,
    )
    char.add_item_entity(tmap)
    CharacterRepository.save(char)

    # 3. 玩家在【青云坊市客栈】执行 /挖宝 1
    res1 = ws.handle(tok, "/挖宝 1")
    assert res1["ok"] is False
    assert res1.get("wrong_location") is True
    assert "【天机定盘 · 寻龙点穴】" in res1["text"]
    assert "黑水沼泽" in res1["text"]
    assert res1.get("target_node_name") == "黑水沼泽"
    assert res1.get("bagua") is not None
    
    # 宝图完好无损保存在背包中
    status1 = res1.get("status", {})
    tmap_items = [it for it in status1.get("items", []) if "图" in it["name"]]
    assert len(tmap_items) >= 1
    tmap_info = tmap_items[0]
    assert tmap_info["isAtTarget"] is False
    assert tmap_info["targetNodeName"] == "黑水沼泽"
    assert "位" in tmap_info["coords"]
    assert len(tmap_info["riddle"]) > 0

    # 4. 执行 /前往 黑水沼泽 动身奔赴灵穴
    res_move = ws.handle(tok, "/前往 黑水沼泽")
    assert res_move["ok"] is True

    # 验证此时状态中 isAtTarget 变为 True
    char_moved = CharacterRepository.get_by_id(char.id)
    assert "黑水沼泽" in char_moved.location
    status_moved = ws._status_dict(char_moved)
    tmap_items_moved = [it for it in status_moved.get("items", []) if "图" in it["name"]]
    assert len(tmap_items_moved) >= 1
    assert tmap_items_moved[0]["isAtTarget"] is True

    # 5. 抵达【黑水沼泽】后执行 /挖宝 1（五行相克破阵）
    res_dig = ws.handle(tok, "/挖宝 1")
    assert res_dig["ok"] is True
    assert "绝世宝匣现世" in res_dig["text"] or "洞府" in res_dig["text"] or "破" in res_dig["text"]
    assert res_dig.get("equipment") is not None
    assert res_dig.get("pill") is not None

    # 宝图已被消耗，背包中获得新法宝神兵与绝品仙丹
    status_final = res_dig.get("status", {})
    final_items = status_final.get("items", [])
    # 原宝图应已消耗扣除
    assert not any(it["uid"] == tmap.uid for it in final_items)
    # 背包中包含新出世的神兵和灵丹
    equip_names = [it["name"] for it in final_items]
    assert res_dig["equipment"]["name"] in equip_names


def test_treasure_read_map_directional_guidance():
    init_db()
    ws = World()
    char = WorldClock.create_new_character("u_read_map_flow", "勘脉道人")
    char.location = "青云坊市客栈"
    CharacterRepository.save(char)
    tok = ws.join(char.name, user_id=char.user_id)["token"]

    tmap = TreasureEngine.generate_treasure_map(char, tier=2, preferred_target="落霞山")
    char.add_item_entity(tmap)
    CharacterRepository.save(char)

    # 执行 /宝图 探查天机
    res = ws.handle(tok, f"/宝图 {tmap.name}")
    assert res["ok"] is True
    assert "【天机定盘 · 寻龙点穴】" in res["text"]
    assert "落霞山" in res["text"]
    assert "卦位" in res["text"] or "方位" in res["text"]


def test_treasure_combat_archetype_flow():
    init_db()
    ws = World()
    char = WorldClock.create_new_character("u_combat_tmap", "破阵战狂")
    char.location = "落霞山"
    char.realm.tier = 3
    CharacterRepository.save(char)
    tok = ws.join(char.name, user_id=char.user_id)["token"]

    tmap = TreasureEngine.generate_treasure_map(
        char,
        tier=3,
        preferred_target="落霞山",
        preferred_archetype=TreasureArchetype.COMBAT,
    )
    char.add_item_entity(tmap)
    CharacterRepository.save(char)

    # 身在落霞山执行 /挖宝
    res_dig = ws.handle(tok, "/挖宝")
    assert res_dig["ok"] is True
    assert "守墓" in res_dig["text"] or "巨傀" in res_dig["text"] or "斩首" in res_dig["text"]
    assert res_dig.get("equipment") is not None
    assert res_dig["equipment"]["name"] == "断魂幽煞剑"
