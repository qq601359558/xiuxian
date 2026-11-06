"""
藏宝图与实体道具交易流转测试：
1. NPC 专柜与商会货单绝不上架藏宝图（仅限玩家发掘与交易）；
2. 玩家坊市寄售（/寄售）完整保留 ItemEntity 实体属性（坐标、谶语、词缀）；
3. 玩家当面交易（/交易）原子互换完整保留 ItemEntity 实体属性。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.items import ItemFactory, ItemKind
from core.market import MarketEngine, MarketListing
from core.trade import TradeEngine, NpcShopEngine, _trade_sessions, _trade_by_user
from core.treasure_system import TreasureEngine


def _mk_char(name: str, stones: int = 1000, loc: str = "青云坊市客栈") -> Character:
    now = time.time()
    c = Character(
        user_id=f"test_{name}",
        name=name,
        realm=Realm(tier=1, sub_tier=0, current_exp=1000),
        lifespan=Lifespan(birth_base=80, accumulated_gain=0, death_timestamp=now + 80 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.METAL], efficiency=1.2),
        location=loc,
        spirit_stones=stones,
    )
    c.born_at = now - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def test_npc_shop_excludes_treasure_map():
    init_db()
    # 1. 验证商会货单无藏宝图
    catalog = MarketEngine.catalog()
    assert not any(item["name"] == "藏宝图" for item in catalog), "商会货单不应上架藏宝图"

    # 2. 验证玩家无法从商会直接购买藏宝图
    buyer = _mk_char("寻图人", stones=1000)
    res = MarketEngine.buy_from_guild(buyer, "藏宝图")
    assert res["success"] is False
    assert "商会无从兜售" in res["message"] or "并无" in res["message"]
    print("✓ NPC商会货单与购买接口成功屏蔽藏宝图")


def test_market_consignment_preserves_item_entity():
    init_db()
    seller = _mk_char("卖家甲", stones=500)
    buyer = _mk_char("买家乙", stones=500)

    # 卖家持有一张指向黑水沼泽的实体藏宝图
    tmap = ItemFactory.create_treasure_map(target_node_id="node_heishui_swamp", target_node_name="黑水沼泽", tier=2)
    seller.add_item_entity(tmap)
    map_uid = tmap.uid
    assert seller.find_item(map_uid) is not None

    # 1. 挂单寄售
    listing, res = MarketEngine.list_item(seller, tmap.name, price=200)
    assert res["success"] is True, res
    assert listing is not None
    assert listing.item_entity is not None
    assert listing.item_entity.uid == map_uid
    assert listing.item_entity.custom_metadata["target_node_name"] == "黑水沼泽"
    # 卖家随身实体已移除
    assert seller.find_item(map_uid) is None
    assert tmap.name not in seller.inventory

    # 2. 买家购买
    buy_res = MarketEngine.buy_listing(buyer, listing)
    assert buy_res["success"] is True, buy_res
    # 买家成功获得实体藏宝图，且坐标与元数据丝毫不差
    acquired = buyer.find_item(map_uid)
    assert acquired is not None
    assert acquired.uid == map_uid
    assert acquired.custom_metadata["target_node_name"] == "黑水沼泽"
    assert tmap.name in buyer.inventory
    print("✓ 坊市寄售 ItemEntity 完整流转（元数据无损）")


def test_market_consignment_cancel_restores_entity():
    init_db()
    seller = _mk_char("悔单客", stones=500)
    tmap = ItemFactory.create_treasure_map(target_node_id="node_heishui_swamp", target_node_name="黑水沼泽", tier=1)
    seller.add_item_entity(tmap)
    map_uid = tmap.uid

    listing, res = MarketEngine.list_item(seller, tmap.name, price=150)
    assert res["success"] is True
    assert seller.find_item(map_uid) is None

    # 撤单
    cancel_res = MarketEngine.cancel_listing(seller, listing)
    assert cancel_res["success"] is True
    restored = seller.find_item(map_uid)
    assert restored is not None
    assert restored.uid == map_uid
    assert tmap.name in seller.inventory
    print("✓ 坊市寄售撤单 ItemEntity 完好退回")


def test_face_to_face_trade_preserves_item_entity():
    init_db()
    _trade_sessions.clear()
    _trade_by_user.clear()

    a = _mk_char("道友A", stones=300, loc="青云坊市客栈")
    b = _mk_char("道友B", stones=300, loc="青云坊市客栈")

    # A 拥有一张实体藏宝图
    tmap = ItemFactory.create_treasure_map(target_node_id="node_wanjian_peak", target_node_name="万剑仙门峰", tier=3)
    a.add_item_entity(tmap)
    map_uid = tmap.uid

    # 发起交易
    res_open = TradeEngine.open_trade(a, "道友B")
    assert res_open["success"] is True

    # A 出宝图 + 50 灵石
    res_offer_a = TradeEngine.set_offer(a, 50, [tmap.name])
    assert res_offer_a["success"] is True
    session = res_offer_a["session"]
    assert len(session.a_entities) == 1
    assert session.a_entities[0].uid == map_uid
    CharacterRepository.save(a)

    # B 出 100 灵石
    res_offer_b = TradeEngine.set_offer(b, 100, [])
    assert res_offer_b["success"] is True
    CharacterRepository.save(b)

    # 双方同意
    TradeEngine.accept(a)
    exec_res = TradeEngine.accept(b)
    assert exec_res["success"] is True

    # 查验交割结果
    a_updated = CharacterRepository.get_by_id(a.id)
    b_updated = CharacterRepository.get_by_id(b.id)

    # A 失去了宝图，净得 50 灵石（出50进100）
    assert a_updated.find_item(map_uid) is None
    assert a_updated.spirit_stones == 300 - 50 + 100

    # B 得到了宝图，净出 50 灵石（出100进50）
    acquired_b = b_updated.find_item(map_uid)
    assert acquired_b is not None
    assert acquired_b.uid == map_uid
    assert acquired_b.custom_metadata["target_node_name"] == "万剑仙门峰"
    assert b_updated.spirit_stones == 300 - 100 + 50
    print("✓ 当面交易 ItemEntity 原子互换完好交割")


if __name__ == "__main__":
    test_npc_shop_excludes_treasure_map()
    test_market_consignment_preserves_item_entity()
    test_market_consignment_cancel_restores_entity()
    test_face_to_face_trade_preserves_item_entity()
    print("\n✅ 藏宝图交易与流转测试全部通过！")
