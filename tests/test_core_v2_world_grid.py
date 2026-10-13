"""
Core-V2 空间拓扑图谱与世界疤痕测试 (test_core_v2_world_grid.py)
"""
import time
import pytest
from core.world_grid import WorldGridEngine, EnvironmentState


def test_grid_initialization_and_lookup():
    node = WorldGridEngine.get_node("node_qingyun_market")
    assert node is not None
    assert node.base_name == "青云坊市客栈"
    assert node.region == "东荒·青州"

    # 按名字查找
    node_by_name = WorldGridEngine.get_node("落霞山灵泉")
    assert node_by_name is not None
    assert node_by_name.id == "node_luoxia_spring"


def test_pathfinding_and_distance():
    # 曼哈顿距离
    dist = WorldGridEngine.calculate_distance("node_qingyun_market", "node_luoxia_spring")
    # (0, 0) to (1, -2) => |1-0| + |-2-0| = 3
    assert dist == 3

    # BFS 路网跳数路径: 青云坊市 -> 落霞山灵泉 -> 黑水沼泽
    path = WorldGridEngine.find_shortest_hops("node_qingyun_market", "node_heishui_swamp")
    assert path is not None
    assert path[0] == "node_qingyun_market"
    assert path[-1] == "node_heishui_swamp"
    assert len(path) == 3


def test_world_scar_injection_and_healing():
    # 初始状态与测试隔离
    nodes = WorldGridEngine._load_nodes()
    node = nodes.get("node_heishui_swamp")
    assert node is not None
    node.environmental_states = []
    WorldGridEngine._save_nodes(nodes)

    orig_density = node.effective_density
    orig_danger = node.effective_danger


    # 施加疤痕：引爆地火化为赤焰火海
    now = time.time()
    scar = EnvironmentState(
        scar_id="scar_test_fire_sea",
        scar_type="fire_sea",
        title="赤焰火海",
        hazard_desc="地脉崩塌，炽热岩浆喷涌而出。",
        caused_by="测试狂徒",
        density_mult=0.5,
        danger_delta=0.3,
        expires_at=now + 2.0,  # 2秒后过期
    )
    updated = WorldGridEngine.apply_scar("node_heishui_swamp", scar, broadcast=False)
    assert updated is not None
    assert "赤焰火海" in updated.display_name
    assert updated.effective_density < orig_density
    assert updated.effective_danger > orig_danger
    assert "炽热岩浆喷涌" in updated.effective_desc

    # 过期自愈测试
    time.sleep(2.1)
    pruned = WorldGridEngine.prune_expired_scars()
    assert pruned >= 1
    healed = WorldGridEngine.get_node("node_heishui_swamp")
    assert "赤焰火海" not in healed.display_name
    assert healed.effective_density == orig_density
