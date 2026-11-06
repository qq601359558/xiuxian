"""
《天道因果录》静态配置总目录 (Catalogs Module)
解耦归类材料、丹药、装备与法门静态数据
"""
from typing import Dict, Any, Optional, List
from core.catalogs.materials import MATERIAL_CATALOG, RAW_MATERIALS
from core.catalogs.pills import PILL_CATALOG, RAW_PILLS, PILL_RECIPES
from core.catalogs.equipments import EQUIPMENT_CATALOG, RAW_EQUIPMENTS, EQUIPMENT_RECIPES, SET_BONUSES

__all__ = [
    "MATERIAL_CATALOG", "RAW_MATERIALS", "get_material", "format_material_for_client",
    "PILL_CATALOG", "RAW_PILLS", "PILL_RECIPES", "get_pill", "format_pill_for_client",
    "EQUIPMENT_CATALOG", "RAW_EQUIPMENTS", "EQUIPMENT_RECIPES", "SET_BONUSES", "get_equipment", "format_equipment_for_client", "get_set_bonus"
]


def get_material(key: str) -> Optional[Dict[str, Any]]:
    """根据中文名或英文 ID 检索材料配置"""
    if not key:
        return None
    return MATERIAL_CATALOG.get(key.strip())


def get_pill(key: str) -> Optional[Dict[str, Any]]:
    """根据中文名或英文 ID 检索丹药配置"""
    if not key:
        return None
    return PILL_CATALOG.get(key.strip())


def format_material_for_client(key: str, is_prod: bool = False) -> Optional[Dict[str, Any]]:
    """
    材料客户端展示格式化器
    规则：测试环境保留调试难度；生产环境自动剔除，保证代入感
    """
    mat = get_material(key)
    if not mat:
        return None
    
    out = dict(mat)
    if not is_prod:
        # 测试环境：透出检定难度
        out["_debug_difficulty"] = f"【难度: {mat.get('difficulty', 0)}/100】"
    else:
        # 生产环境：剔除敏感检定字段
        out.pop("difficulty", None)
        out["_debug_difficulty"] = None
        
    return out


def format_pill_for_client(key: str, is_prod: bool = False) -> Optional[Dict[str, Any]]:
    """丹药客户端展示格式化器"""
    pill = get_pill(key)
    if not pill:
        return None
    
    out = dict(pill)
    if not is_prod:
        out["_debug_difficulty"] = f"【炼制难度: {pill.get('difficulty', 0)}/100】"
    else:
        out.pop("difficulty", None)
        out["_debug_difficulty"] = None
        
    return out


def get_equipment(key: str) -> Optional[Dict[str, Any]]:
    """根据中文名或英文 ID 检索装备配置"""
    if not key:
        return None
    return EQUIPMENT_CATALOG.get(key.strip())


def format_equipment_for_client(key: str, is_prod: bool = False) -> Optional[Dict[str, Any]]:
    """装备客户端展示格式化器"""
    eq = get_equipment(key)
    if not eq:
        return None
    
    out = dict(eq)
    if not is_prod:
        out["_debug_difficulty"] = f"【锻造难度: {eq.get('difficulty', 0)}/100】"
    else:
        out.pop("difficulty", None)
        out["_debug_difficulty"] = None
        
    return out


def get_set_bonus(set_name: str) -> Optional[Dict[str, Any]]:
    """根据套装名检索天道套装羁绊定义"""
    if not set_name:
        return None
    return SET_BONUSES.get(set_name.strip())


