"""
九霄坊市水墨地摊与市井仙商互动回归测试
覆盖：/摆摊、/撤回、/买寄售、/收益、/捡漏、/招徕与还价、满格拦截
"""
import uuid
import pytest
from server.world import World
from core.models import Character, CharacterStatus
from core.items import ItemEntity, ItemKind
from storage.db import CharacterRepository, MarketListingRepository


def _create_world():
    return World(auto_tick=False)


def test_bazaar_stall_and_cancel_lifecycle():
    w = _create_world()
    name = f"地摊掌柜_{uuid.uuid4().hex[:6]}"
    r = w.join(name)
    tok = r["token"]
    c = w.get_char(tok)
    c.spirit_stones = 500

    item = ItemEntity.create(
        name="极品千年雷击木",
        kind=ItemKind.MATERIAL,
        tier=3,
        description="天雷淬炼万年的雷击神木",
    )
    c.add_item_entity(item)
    CharacterRepository.save(c)

    # 1. 摆摊挂牌
    res = w.handle(tok, "/摆摊 极品千年雷击木 300")
    assert res["ok"] is True
    c = w.get_char(tok)
    assert not any(it.name == "极品千年雷击木" for it in c.items)
    assert res["status"]["stall_items"]
    assert any(it["name"] == "极品千年雷击木" for it in res["status"]["stall_items"])

    # 2. 撤回摊位
    res_cancel = w.handle(tok, "/撤回 极品千年雷击木")
    assert res_cancel["ok"] is True
    c = w.get_char(tok)
    assert any(it.name == "极品千年雷击木" for it in c.items)
    assert not any(it["name"] == "极品千年雷击木" for it in res_cancel["status"]["stall_items"])


def test_bazaar_bag_full_interceptions():
    w = _create_world()
    name = f"满格侠_{uuid.uuid4().hex[:6]}"
    r = w.join(name)
    tok = r["token"]
    c = w.get_char(tok)
    c.spirit_stones = 2000

    # 挂牌一件物品
    rare = ItemEntity.create(name="绝品避水珠", kind=ItemKind.MATERIAL, tier=3)
    c.add_item_entity(rare)
    CharacterRepository.save(c)
    w.handle(tok, "/摆摊 绝品避水珠 150")

    # 把纳戒填满至 64 格
    c = w.get_char(tok)
    while len(c.items) < 64:
        c.add_item_entity(ItemEntity.create(name=f"杂灵砂_{len(c.items)}", kind=ItemKind.MATERIAL, tier=1))
    CharacterRepository.save(c)
    assert c.is_bag_full() is True

    # 1. 纳戒满时撤回应被拦截
    res_cancel = w.handle(tok, "/撤回 绝品避水珠")
    assert res_cancel["ok"] is False
    assert "满" in res_cancel["error"]

    # 2. 纳戒满时捡漏盲匣应被拦截
    res_gamble = w.handle(tok, "/捡漏")
    assert res_gamble["ok"] is False
    assert "满" in res_gamble["error"]


def test_bazaar_buy_listing_and_claim_earnings():
    w = _create_world()
    name_s = f"卖家_{uuid.uuid4().hex[:6]}"
    name_b = f"买家_{uuid.uuid4().hex[:6]}"
    r_seller = w.join(name_s)
    r_buyer = w.join(name_b)
    tok_s = r_seller["token"]
    tok_b = r_buyer["token"]

    seller = w.get_char(tok_s)
    buyer = w.get_char(tok_b)
    seller.spirit_stones = 200
    buyer.spirit_stones = 1000

    item = ItemEntity.create(name="三转纯阳还魂丹", kind=ItemKind.CONSUMABLE, tier=3)
    seller.add_item_entity(item)
    CharacterRepository.save(seller)
    CharacterRepository.save(buyer)

    # 卖家挂牌
    r_list = w.handle(tok_s, "/摆摊 三转纯阳还魂丹 400")
    assert r_list["ok"] is True

    # 买家购买
    r_buy = w.handle(tok_b, "/买寄售 三转纯阳还魂丹")
    assert r_buy["ok"] is True
    buyer = w.get_char(tok_b)
    assert any(it.name == "三转纯阳还魂丹" for it in buyer.items)
    assert buyer.spirit_stones == 1000 - 400

    # 卖家查收收益并提取
    seller = w.get_char(tok_s)
    assert getattr(seller, "stall_earnings", 0) == 400
    r_earn = w.handle(tok_s, "/收益")
    assert r_earn["ok"] is True
    seller = w.get_char(tok_s)
    assert seller.stall_earnings == 0
    assert seller.spirit_stones >= 500


def test_bazaar_blind_box_gamble():
    w = _create_world()
    name = f"捡漏王_{uuid.uuid4().hex[:6]}"
    r = w.join(name)
    tok = r["token"]
    c = w.get_char(tok)
    c.spirit_stones = 200
    CharacterRepository.save(c)

    res = w.handle(tok, "/捡漏")
    assert res["ok"] is True
    c = w.get_char(tok)
    assert c.spirit_stones == 120
    assert len(c.items) >= 1
    assert "解石" in res["text"] or "盲匣" in res["text"]


def test_bazaar_solicit_and_haggle():
    w = _create_world()
    name = f"小贩_{uuid.uuid4().hex[:6]}"
    r = w.join(name)
    tok = r["token"]
    c = w.get_char(tok)
    c.spirit_stones = 500

    # 空摊位招徕被阻断
    res_empty = w.handle(tok, "/招徕")
    assert res_empty["ok"] is False

    # 挂牌一件
    item = ItemEntity.create(name="太华山残破道符", kind=ItemKind.MATERIAL, tier=2)
    c.add_item_entity(item)
    CharacterRepository.save(c)
    w.handle(tok, "/摆摊 太华山残破道符 100")

    # 招徕修士
    res_solicit = w.handle(tok, "/招徕")
    assert res_solicit["ok"] is True
    assert "text" in res_solicit

    # 模拟还价同意
    open_l = [l for l in MarketListingRepository.list_all() if l.seller_id == c.id and l.is_open()]
    if open_l:
        l_id = open_l[0].id
        res_agree = w.handle(tok, f"/还价 成交 {l_id} 80")
        assert res_agree["ok"] is True
        c = w.get_char(tok)
        assert c.stall_earnings >= 80
