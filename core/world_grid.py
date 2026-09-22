"""
Core-V2 空间拓扑图谱与动态世界疤痕引擎 (Spatial World Grid & Scars)
从静态字典升华为活的拓扑路网，支持环境状态栈、世界疤痕演化与空间距离寻路。
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from storage.db import WorldStateRepository

_STORAGE_KEY = "world_grid_v2"


class EnvironmentState(BaseModel):
    """环境状态（世界疤痕）"""
    scar_id: str
    scar_type: str                  # fire_sea | poison_mist | celestial_omen | ruin_collapse
    title: str                      # 异象标题 (如: "赤焰火海", "上古凶煞")
    hazard_desc: str                # 环境变迁与灾变叙事描述
    caused_by: str = "天地异动"     # 始作俑者（玩家名或天道事件）
    density_mult: float = 1.0       # 灵气浓度修正倍率 (如 0.6 代表灵气枯竭)
    danger_delta: float = 0.0       # 危险指数增减 (如 +0.4)
    environmental_damage: int = 0   # 每行动环境气血侵蚀点数
    immune_item: Optional[str] = None  # 辟火珠等免疫法宝
    created_at: float = Field(default_factory=time.time)
    expires_at: float = 0.0         # 过期时间戳（0 代表永久或未设定）

    def is_active(self, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.time()
        if self.expires_at <= 0.0:
            return True
        return self.expires_at > t


class WorldNode(BaseModel):
    """空间拓扑节点实体"""
    id: str                                  # 唯一锚点 (如: "node_qingyun_market")
    base_name: str                           # 物理基准名 ("青云坊市客栈")
    region: str                              # 所属大区 ("东荒·青州")
    coordinates: Tuple[int, int] = (0, 0)    # (x, y) 相对地理坐标
    adjacent_node_ids: List[str] = Field(default_factory=list)  # 物理连通路网
    is_safe: bool = True                     # 原生安全区标记
    density: float = 1.0                     # 原生灵气浓度
    danger: float = 0.1                      # 原生危险指数 (0.0~1.0)
    desc: str = ""                           # 原生地貌说明
    environmental_states: List[EnvironmentState] = Field(default_factory=list)

    @property
    def active_scars(self) -> List[EnvironmentState]:
        now = time.time()
        return [s for s in self.environmental_states if s.is_active(now)]

    @property
    def display_name(self) -> str:
        scars = self.active_scars
        if scars:
            return f"{self.base_name} [⚠️异象:{scars[0].title}]"
        return self.base_name

    @property
    def effective_density(self) -> float:
        d = self.density
        for s in self.active_scars:
            d *= s.density_mult
        return max(0.1, round(d, 2))

    @property
    def effective_danger(self) -> float:
        d = self.danger
        for s in self.active_scars:
            d += s.danger_delta
        return max(0.0, min(1.0, round(d, 2)))

    @property
    def effective_desc(self) -> str:
        scars = self.active_scars
        if not scars:
            return self.desc
        scar_texts = "\n".join(f"【地貌异象 · {s.title}】{s.hazard_desc}（起因：{s.caused_by}）" for s in scars)
        return f"{self.desc}\n{scar_texts}"

    @property
    def is_effectively_safe(self) -> bool:
        if not self.is_safe:
            return False
        # 若有极度危险的环境疤痕，安全大阵告破
        return self.effective_danger < 0.4


# ==================== 默认拓扑蓝图 ====================

DEFAULT_TOPOLOGY_NODES: List[Dict[str, Any]] = [
    # --- 东荒·青州 ---
    {
        "id": "node_qingyun_market",
        "base_name": "青云坊市客栈",
        "region": "东荒·青州",
        "coordinates": (0, 0),
        "adjacent_node_ids": ["node_qingyun_sect", "node_luoxia_spring"],
        "is_safe": True,
        "density": 1.0,
        "danger": 0.1,
        "desc": "青州第一大散修坊市，受元婴级禁制庇护，绝灵止戈，灵气平稳。",
    },
    {
        "id": "node_qingyun_sect",
        "base_name": "青云宗外门山门",
        "region": "东荒·青州",
        "coordinates": (2, 1),
        "adjacent_node_ids": ["node_qingyun_market", "node_xuanyuan_cave"],
        "is_safe": True,
        "density": 1.3,
        "danger": 0.15,
        "desc": "正道名门青云宗山门，仙鹤腾飞，云海茫茫。散修可在此叩门接受考核。",
    },
    {
        "id": "node_xuanyuan_cave",
        "base_name": "宗门玄元洞府",
        "region": "东荒·青州",
        "coordinates": (3, 2),
        "adjacent_node_ids": ["node_qingyun_sect"],
        "is_safe": True,
        "density": 1.8,
        "danger": 0.1,
        "desc": "青云宗三阶灵脉洞府，护山大阵日夜运转。宗门弟子可免费闭关。",
    },
    {
        "id": "node_luoxia_spring",
        "base_name": "落霞山灵泉",
        "region": "东荒·青州",
        "coordinates": (1, -2),
        "adjacent_node_ids": ["node_qingyun_market", "node_heishui_swamp"],
        "is_safe": False,
        "density": 1.6,
        "danger": 0.35,
        "desc": "深山无主微型灵泉，灵气活泼，常有妖兽散修争夺，需阵法自保。",
    },
    {
        "id": "node_heishui_swamp",
        "base_name": "黑水沼泽",
        "region": "东荒·青州",
        "coordinates": (3, -3),
        "adjacent_node_ids": ["node_luoxia_spring", "node_wanjian_peak"],
        "is_safe": False,
        "density": 1.2,
        "danger": 0.65,
        "desc": "终年阴云笼罩的毒瘴沼泽，泥潭深处盘踞上古毒蟒，险象环生。",
    },
    # --- 中土·万岳 ---
    {
        "id": "node_wanjian_peak",
        "base_name": "万剑仙门峰",
        "region": "中土·万岳",
        "coordinates": (6, 0),
        "adjacent_node_ids": ["node_heishui_swamp", "node_xijian_pool"],
        "is_safe": True,
        "density": 1.5,
        "danger": 0.2,
        "desc": "插天万刃如巨剑耸立，剑气冲霄，杀伐凛冽，乃万剑仙门总坛。",
    },
    {
        "id": "node_xijian_pool",
        "base_name": "洗剑池洞天",
        "region": "中土·万岳",
        "coordinates": (7, 1),
        "adjacent_node_ids": ["node_wanjian_peak"],
        "is_safe": True,
        "density": 2.0,
        "danger": 0.1,
        "desc": "万剑仙门禁地洗剑池，剑意凝练成液，天地灵气如白虹贯日。",
    },
]


class WorldGridEngine:
    """空间拓扑与世界疤痕管理器"""

    @staticmethod
    def _load_nodes() -> Dict[str, WorldNode]:
        raw = WorldStateRepository.get(_STORAGE_KEY)
        if isinstance(raw, dict) and raw:
            nodes = {}
            for nid, data in raw.items():
                try:
                    nodes[nid] = WorldNode.model_validate(data)
                except Exception:
                    continue
            if nodes:
                return nodes

        # 初始化默认节点拓扑
        nodes = {}
        for d in DEFAULT_TOPOLOGY_NODES:
            node = WorldNode.model_validate(d)
            nodes[node.id] = node
        WorldGridEngine._save_nodes(nodes)
        return nodes

    @staticmethod
    def _save_nodes(nodes: Dict[str, WorldNode]) -> None:
        raw = {nid: n.model_dump() for nid, n in nodes.items()}
        WorldStateRepository.set(_STORAGE_KEY, raw)

    @staticmethod
    def get_node(identifier: str) -> Optional[WorldNode]:
        """通过 node_id 或 地名 精确/模糊查找节点"""
        identifier = (identifier or "").strip()
        if not identifier:
            return None
        nodes = WorldGridEngine._load_nodes()
        if identifier in nodes:
            return nodes[identifier]

        # 按 base_name 或 display_name 查找
        for n in nodes.values():
            if n.base_name == identifier or identifier in n.base_name or n.base_name in identifier:
                return n
            if identifier in n.display_name:
                return n
        return None

    @staticmethod
    def list_nodes(region: Optional[str] = None) -> List[WorldNode]:
        nodes = list(WorldGridEngine._load_nodes().values())
        if region:
            nodes = [n for n in nodes if n.region == region]
        return nodes

    @staticmethod
    def calculate_distance(start_id: str, end_id: str) -> int:
        """计算两节点在网格上的曼哈顿坐标距离"""
        start = WorldGridEngine.get_node(start_id)
        end = WorldGridEngine.get_node(end_id)
        if not start or not end:
            return 999
        dx = abs(start.coordinates[0] - end.coordinates[0])
        dy = abs(start.coordinates[1] - end.coordinates[1])
        return dx + dy

    @staticmethod
    def find_shortest_hops(start_id: str, end_id: str) -> Optional[List[str]]:
        """广度优先搜索计算物理路网最短路径跳数"""
        nodes = WorldGridEngine._load_nodes()
        s_node = WorldGridEngine.get_node(start_id)
        e_node = WorldGridEngine.get_node(end_id)
        if not s_node or not e_node:
            return None
        if s_node.id == e_node.id:
            return [s_node.id]

        queue: List[Tuple[str, List[str]]] = [(s_node.id, [s_node.id])]
        visited: Set[str] = {s_node.id}

        while queue:
            curr_id, path = queue.pop(0)
            curr = nodes.get(curr_id)
            if not curr:
                continue
            for neighbor_id in curr.adjacent_node_ids:
                if neighbor_id == e_node.id:
                    return path + [neighbor_id]
                if neighbor_id not in visited and neighbor_id in nodes:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [neighbor_id]))
        return None

    @staticmethod
    def apply_scar(
        node_identifier: str,
        scar: EnvironmentState,
        broadcast: bool = True,
    ) -> Optional[WorldNode]:
        """为目标节点施加世界疤痕（地貌永久/长期改变）"""
        nodes = WorldGridEngine._load_nodes()
        node = WorldGridEngine.get_node(node_identifier)
        if not node:
            return None

        # 检查是否已存在同名/同类型疤痕，存在则更新覆盖
        target = nodes[node.id]
        target.environmental_states = [
            s for s in target.environmental_states if s.scar_id != scar.scar_id
        ]
        target.environmental_states.append(scar)
        WorldGridEngine._save_nodes(nodes)

        # 全服世界频道广播异变
        if broadcast:
            try:
                from core.world_channel import WorldChannel
                WorldChannel.broadcast(
                    kind="world_omen",
                    content=(
                        f"【天地异象】{target.base_name}地脉突遭剧变，化作【{scar.title}】！"
                        f"{scar.hazard_desc}（始作俑者：{scar.caused_by}）"
                    ),
                    importance="high",
                )
            except Exception:
                pass

        return target

    @staticmethod
    def prune_expired_scars() -> int:
        """清理所有已过期的世界疤痕（自然自愈）"""
        nodes = WorldGridEngine._load_nodes()
        now = time.time()
        pruned_count = 0
        for n in nodes.values():
            before_len = len(n.environmental_states)
            n.environmental_states = [s for s in n.environmental_states if s.is_active(now)]
            pruned_count += (before_len - len(n.environmental_states))
        if pruned_count > 0:
            WorldGridEngine._save_nodes(nodes)
        return pruned_count
