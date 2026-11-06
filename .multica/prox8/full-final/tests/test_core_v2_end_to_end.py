"""
Core-V2 端到端集成验证 (test_core_v2_end_to_end.py)
验证完整闭环：
1. 入世与获取实体宝图；
2. /宝图 研读线索、谶语与目标节点；
3. 空间拓扑路径校验（未到达时阻拦并给出方向导引）；
4. 移动到达目标节点；
5. /挖宝 触发五行生克阵盘决策；
6. 成功破阵获取极品掉落与修为；
7. 破坏性操作引发世界疤痕与全服异象广播。
"""
import pytest
from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.items import ItemKind
from core.world_grid import WorldGridEngine
from core.treasure_system import TreasureEngine, TreasureArchetype


def test_full_treasure_gameplay_loop():
    # 1. 创建修士，初始位于青云坊市
    c = Character(
        user_id="u_player_e2e",
        name="楚天行",
        realm=Realm(tier=2, current_exp=200),
        lifespan=Lifespan(birth_base=120.0, death_timestamp=9999999999.0),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WATER]),
        location="青云坊市客栈",
        spirit_stones=300,
    )

    # 2. 历练/探险寻获一张指向黑水沼泽的藏宝图
    tmap = TreasureEngine.generate_treasure_map(c, tier=2, preferred_target="黑水沼泽")
    tmap.custom_metadata["archetype"] = TreasureArchetype.ELEMENT_PUZZLE
    c.add_item_entity(tmap)

    # 3. 查阅宝图
    read_res = TreasureEngine.read_map(c)
    assert read_res["success"] is True
    assert "黑水沼泽" in read_res["message"]
    assert "距宝藏地约" in read_res["message"]

    # 4. 原地直接挖宝：应当被地理罗盘拦截，且不浪费宝图
    wrong_dig = TreasureEngine.dig(c)
    assert wrong_dig["success"] is False
    assert wrong_dig["wrong_location"] is True
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 1

    # 5. 按照罗盘指引移动至黑水沼泽（通过 WorldServer._go 真实路由）
    path = WorldGridEngine.find_shortest_hops("node_qingyun_market", "node_heishui_swamp")
    assert path is not None
    from server.world import World
    w = World(auto_tick=False)
    go_res = w._go(c, "黑水沼泽")
    assert go_res.get("ok") is True
    assert c.location == "黑水沼泽"



    # 6. 在黑水沼泽启动勘探
    step1 = TreasureEngine.dig(c)
    assert step1["success"] is True
    assert step1.get("need_choice") is True
    assert "以水克火" in step1["message"]

    # 7. 做出决策：选择 1（以水克火）
    stones_before = c.spirit_stones
    exp_before = c.realm.current_exp
    step2 = TreasureEngine.dig(c, choice_id="1")
    assert step2["success"] is True
    assert step2["outcome"] == "perfect_solve"
    assert c.spirit_stones > stones_before
    assert c.realm.current_exp > exp_before
    # 验证宝图已消耗，且收获了新丹药实体
    assert len(c.find_items_by_kind(ItemKind.TREASURE_MAP)) == 0
    assert any(it.kind == ItemKind.PILL for it in c.items)


def test_free_action_and_scar_e2e():
    # 测试自由破局与世界疤痕端到端
    c = Character(
        user_id="u_scar_tester",
        name="厉无咎",
        realm=Realm(tier=3, current_exp=500),
        lifespan=Lifespan(birth_base=200.0, death_timestamp=9999999999.0),
        spiritual_root=SpiritualRoot(root_type=RootType.MUTANT, elements=[Element.FIRE]),
        location="落霞山灵泉",
    )

    tmap = TreasureEngine.generate_treasure_map(c, tier=3, preferred_target="落霞山灵泉")
    tmap.custom_metadata["archetype"] = TreasureArchetype.RUIN_HAZARD
    c.add_item_entity(tmap)

    # 触发破坏性破局
    res = TreasureEngine.dig(c)
    assert res["success"] is True
    assert res["outcome"] == "scar_created"
    assert "赤焰火海" in res["message"]

    # 验证全服地图节点已发生不可逆的地貌异变
    node = WorldGridEngine.get_node("落霞山灵泉")
    assert node is not None
    assert "赤焰火海" in node.display_name
    assert node.effective_danger >= 0.75
