"""
坊市交易系统的道体合规守恒测试
"""
import pytest
from core.clock import WorldClock
from core.market import MarketEngine, MarketListing, ListingStatus
from core.models import CharacterStatus
from core.items import ItemEntity, ItemKind
from storage.db import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def _make_trader(name: str, stones: int = 100):
    c = WorldClock.create_new_character(f"m_{name}", name)
    c.spirit_stones = stones
    return c


def test_guild_buy_insufficient_stones():
    c = _make_trader("穷修士", stones=10)
    # 聚气丹单价 50 灵石，买不起
    res = MarketEngine.buy_from_guild(c, "聚气丹", 1)
    assert res["success"] is False
    assert "随身灵石不足" in res["message"]


def test_guild_buy_bag_full():
    c = _make_trader("满包修士", stones=5000)
    # 纳戒塞满 64 格
    c.items = [
        ItemEntity(name=f"废铁_{i}", kind=ItemKind.CONSUMABLE) for i in range(64)
    ]
    res = MarketEngine.buy_from_guild(c, "聚气丹", 1)
    assert res["success"] is False
    assert "纳戒百宝囊已满" in res["message"]


def test_guild_buy_dead_blocked():
    c = _make_trader("亡魂", stones=500)
    c.status = CharacterStatus.DEAD
    c.death_cause = "寿尽"
    res = MarketEngine.buy_from_guild(c, "聚气丹", 1)
    assert res["success"] is False
    assert "已坐化道消" in res["message"]


def test_deposit_insufficient_stones():
    c = _make_trader("存银修士", stones=50)
    # 存 100 灵石超出当前拥有量
    res = MarketEngine.deposit_stones(c, 100)
    assert res["success"] is False
    assert "随身灵石不足" in res["message"]


def test_buy_listing_bag_full_and_insufficient():
    buyer = _make_trader("买主", stones=30)
    listing = MarketListing(
        seller_id="seller_01",
        seller_name="摊主",
        item_name="千年灵芝",
        price=100,
        status=ListingStatus.OPEN,
    )
    # 灵石不足
    res1 = MarketEngine.buy_listing(buyer, listing)
    assert res1["success"] is False
    assert "随身灵石不足" in res1["message"]

    # 灵石充足但纳戒已满 64 格
    buyer.spirit_stones = 500
    buyer.items = [
        ItemEntity(name=f"杂物_{i}", kind=ItemKind.CONSUMABLE) for i in range(64)
    ]
    res2 = MarketEngine.buy_listing(buyer, listing)
    assert res2["success"] is False
    assert "纳戒百宝囊已满" in res2["message"]
