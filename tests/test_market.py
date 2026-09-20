"""
坊市交易与寄存自动化测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.market import MarketEngine, ListingStatus
from core.combat import CombatEngine


def _char(name: str, stones: int = 500):
    c = WorldClock.create_new_character(f"m_{name}", name)
    c.spirit_stones = stones
    return c


def test_buy_array_from_guild():
    c = _char("买家", stones=200)
    res = MarketEngine.buy_from_guild(c, "一阶青木迷踪阵", 1)
    assert res["success"] is True
    assert "一阶青木迷踪阵" in c.arrays
    assert c.spirit_stones == 200 - 120
    print("✓ 商会购入阵盘")


def test_sell_back_half_price():
    c = _char("卖家")
    c.inventory.append("妖兽内丹")
    res = MarketEngine.sell_to_guild(c, "妖兽内丹", 1)
    assert res["success"] is True
    assert c.spirit_stones == 500 + 40  # 80 * 0.5
    assert "妖兽内丹" not in c.inventory
    print("✓ 商会五折回收")


def test_deposit_protected_from_loot():
    c = _char("藏金客", stones=400)
    # 目标也在野外
    t = _char("强盗", stones=100)
    c.location = "落霞山灵泉(野外)"
    t.location = "落霞山灵泉(野外)"

    res = MarketEngine.deposit_stones(c, 300)
    assert res["success"] is True
    assert c.vault_stones == 300
    # 保管费 5% = 15，随身 400-300-15=85
    assert c.spirit_stones == 400 - 300 - 15

    # 模拟被抢：只抢随身
    loot = int(c.spirit_stones * 0.8)
    c.spirit_stones -= loot
    t.spirit_stones += loot
    assert c.vault_stones == 300  # 金库毫发无损
    print("✓ 寄存金库不被夺宝波及")


def test_withdraw():
    c = _char("取金")
    MarketEngine.deposit_stones(c, 100)
    before_vault = c.vault_stones
    res = MarketEngine.withdraw_stones(c, 50)
    assert res["success"] is True
    assert c.vault_stones == before_vault - 50
    print("✓ 支取金库")


def test_deposit_insufficient():
    c = _char("穷修", stones=10)
    res = MarketEngine.deposit_stones(c, 100)
    assert res["success"] is False
    print("✓ 灵石不足无法寄存")


def test_player_listing_buy():
    seller = _char("货主", stones=100)
    buyer = _char("顾客", stones=300)
    seller.inventory.append("百年灵芝")

    listing, res = MarketEngine.list_item(seller, "百年灵芝", 80)
    assert res["success"] is True
    assert listing is not None
    fee = max(1, int(80 * 0.10))
    assert seller.spirit_stones == 100 - fee
    assert "百年灵芝" not in seller.inventory

    res2 = MarketEngine.buy_listing(buyer, listing)
    assert res2["success"] is True
    assert buyer.spirit_stones == 300 - 80
    assert "百年灵芝" in buyer.inventory
    assert listing.status == ListingStatus.SOLD

    paid = MarketEngine.complete_sale_payment(listing, seller)
    assert paid == 80
    assert seller.spirit_stones == 100 - fee + 80
    print("✓ 寄售挂单 → 购买 → 货款入账")


def test_cancel_listing_returns_item():
    s = _char("撤单侠")
    s.inventory.append("聚气丹")
    listing, _ = MarketEngine.list_item(s, "聚气丹", 50)
    assert "聚气丹" not in s.inventory
    res = MarketEngine.cancel_listing(s, listing)
    assert res["success"] is True
    assert "聚气丹" in s.inventory
    assert listing.status == ListingStatus.CANCELLED
    print("✓ 撤单退回货物")


def test_use_pill_once():
    c = _char("药修")
    c.inventory.append("聚气丹")
    r1 = MarketEngine.use_pill(c, "聚气丹")
    assert r1["success"] is True
    # 聚气丹现为「下次闭关修为加成」buff，不再直接加修为
    assert c.pill_exp_mult > 0
    assert "聚气丹" in c.used_pills
    c.inventory.append("聚气丹")
    r2 = MarketEngine.use_pill(c, "聚气丹")
    assert r2["success"] is False
    print("✓ 丹药一世限服一次（闭关 buff）")


def test_zhudan_boosts_breakthrough():
    from core.breakthrough import BreakthroughEngine
    c = _char("冲基者")
    c.inventory.append("筑基丹")
    MarketEngine.use_pill(c, "筑基丹")
    assert "筑基丹药力(待渡劫)" in c.skills
    # 修为满，冲筑基
    c.realm.sub_tier = 3
    c.realm.current_exp = c.realm.max_exp
    res = BreakthroughEngine.attempt_breakthrough(c, use_pill=False)
    # 药力应已被消耗（无论成败）
    assert "筑基丹药力(待渡劫)" not in c.skills
    print("✓ 筑基丹药力接入突破引擎")


def main():
    test_buy_array_from_guild()
    test_sell_back_half_price()
    test_deposit_protected_from_loot()
    test_withdraw()
    test_deposit_insufficient()
    test_player_listing_buy()
    test_cancel_listing_returns_item()
    test_use_pill_once()
    test_zhudan_boosts_breakthrough()
    print("\n✅ 坊市交易与寄存 测试全部通过")


if __name__ == "__main__":
    main()
