"""
Core-V2 实体道具系统测试 (test_core_v2_items.py)
"""
import pytest
from core.items import ItemEntity, ItemKind, ItemFactory, ItemAffix


def test_item_entity_serialization():
    aff = ItemAffix(name="破煞", desc="破除煞气", stat_key="pierce", value=0.15)
    item = ItemEntity(
        name="纯阳剑",
        kind=ItemKind.EQUIP,
        slot="weapon",
        tier=3,
        stats={"power": 120.0},
        affixes=[aff],
        lineage_lore="纯阳道人初入江湖时佩剑。",
    )
    assert item.tier_name == "地品"
    assert "破煞" in item.display_name
    dumped = item.model_dump()
    loaded = ItemEntity.model_validate(dumped)
    assert loaded.name == "纯阳剑"
    assert len(loaded.affixes) == 1
    assert loaded.affixes[0].name == "破煞"


def test_treasure_map_creation_and_tooltip():
    tmap = ItemFactory.create_treasure_map(
        target_node_id="node_luoxia_spring",
        target_node_name="落霞山灵泉",
        tier=2,
        archetype="element_puzzle",
        riddle="五行颠倒，金火同炉。",
    )
    assert tmap.kind == ItemKind.TREASURE_MAP
    assert tmap.custom_metadata["target_node_id"] == "node_luoxia_spring"
    tooltip = tmap.format_tooltip()
    assert "落霞山灵泉" in tooltip
    assert "五行颠倒，金火同炉" in tooltip
    assert "五行天机阵" in tooltip


def test_from_legacy_name():
    # 测试旧字符串升级
    sword = ItemFactory.from_legacy_name("青锋剑")
    assert sword.kind == ItemKind.EQUIP
    assert sword.slot == "weapon"

    tmap = ItemFactory.from_legacy_name("藏宝图")
    assert tmap.kind == ItemKind.TREASURE_MAP
    assert "target_node_id" in tmap.custom_metadata

    pill = ItemFactory.from_legacy_name("九转培元丹")
    assert pill.kind == ItemKind.PILL
