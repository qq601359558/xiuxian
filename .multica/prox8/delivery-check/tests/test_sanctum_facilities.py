import time
import pytest
from server.world import World
from storage.db import CharacterRepository


@pytest.fixture
def clean_world():
    w = World(auto_tick=False)
    dao_name = f"青玄子_{int(time.time() * 1000) % 100000}"
    r = w.join(dao_name)
    token = r["token"]
    char = w.get_char(token)
    char.born_at = time.time() - 80 * 3600.0
    char.spirit_stones = 500
    char.vault_stones = 1000
    CharacterRepository.save(char)
    return w, token, char


def test_meditate_and_emerge_status_contract(clean_world):
    w, token, char = clean_world

    # 1. 闭关测试
    res_med = w.handle(token, "/闭关 1")
    assert res_med["ok"] is True
    assert "status" in res_med, "闭关返回必须包含 status"
    assert res_med["status"]["is_meditating"] is True
    assert res_med["status"]["meditating"] is True

    # 2. 出关测试
    res_emerge = w.handle(token, "/出关")
    assert res_emerge["ok"] is True
    assert "status" in res_emerge, "出关返回必须包含 status"
    assert res_emerge["status"]["is_meditating"] is False


def test_deposit_and_withdraw_status_contract(clean_world):
    w, token, char = clean_world

    # 1. 寄存 100 灵石 (含 5% 契税，扣 105，存入 100)
    res_dep = w.handle(token, "/寄存 100")
    assert res_dep["ok"] is True
    assert "status" in res_dep, "寄存返回必须包含 status"
    assert res_dep["status"]["stones"] == 395
    assert res_dep["status"]["vault"] == 1100

    # 2. 支取 50 灵石 (取 50，随身增 50)
    res_with = w.handle(token, "/支取 50")
    assert res_with["ok"] is True
    assert "status" in res_with, "支取返回必须包含 status"
    assert res_with["status"]["stones"] == 445
    assert res_with["status"]["vault"] == 1050


def test_sanctum_facilities_commands(clean_world):
    w, token, char = clean_world

    # 1. 灵泉汲取 (验证实体道具已正确生成且进入 items)
    res_spring = w.handle(token, "/灵泉")
    assert res_spring["ok"] is True
    assert "status" in res_spring
    assert "玄冰玉露" in res_spring["text"]
    assert any(it.get("name") == "玄冰玉露" and it.get("kind") == "pill" for it in res_spring["status"]["items"]), "灵泉生成的玄冰玉露必须作为实体道具进入纳戒"

    # 2. 草园普通采摘
    res_herbs = w.handle(token, "/草园")
    assert res_herbs["ok"] is True
    assert "status" in res_herbs
    assert "紫菁芝草" in res_herbs["text"]

    # 3. 灵石催熟草园 (扣 50 灵石，500 -> 450)
    res_rush = w.handle(token, "/草园 催熟")
    assert res_rush["ok"] is True
    assert "status" in res_rush
    assert "千年紫菁芝草" in res_rush["text"]
    assert res_rush["status"]["stones"] == 450

    # 4. 仙鹤探路 (黑风绝渊赤焰扣除 30 灵石，450 -> 420，并衔回机缘入纳戒)
    res_crane = w.handle(token, "/灵鹤 黑风绝渊赤焰")
    assert res_crane["ok"] is True
    assert "status" in res_crane
    assert res_crane["status"]["stones"] == 420, f"仙鹤巡视应准确扣除 30 灵石，当前为: {res_crane['status']['stones']}"
    assert "青羽仙鹤" in res_crane["text"]
    assert len(res_crane["status"]["items"]) > 0, "仙鹤衔回的机缘必须出现在 status items 纳戒列表中"

    # 5. 灵石不足拦截
    char.spirit_stones = 10
    CharacterRepository.save(char)
    res_crane_fail = w.handle(token, "/灵鹤 南海碧波古墟") # 需要 50 灵石
    assert res_crane_fail["ok"] is False
    assert "不足" in res_crane_fail["error"]


def test_breakthrough_command(clean_world):
    w, token, char = clean_world
    # 注入圆满修为
    char.realm.current_exp = char.realm.max_exp
    CharacterRepository.save(char)

    res = w.handle(token, "/突破")
    assert res["ok"] is True
    assert "status" in res, "突破返回必须包含 status"
    assert res["status"]["realm"] is not None


def test_crane_bag_overflow_and_claim_contract(clean_world):
    w, token, char = clean_world
    from core.items import ItemEntity

    # 1. 塞满纳戒至 64 格
    char.spirit_stones = 500
    char.items = [
        ItemEntity.create(name=f"试炼旧石_{i}", quality=1)
        for i in range(64)
    ]
    char.crane_pending_item = None
    CharacterRepository.save(char)
    assert char.is_bag_full() is True

    # 2. 满格状态下派遣仙鹤探路：应扣除灵石，但机缘暂留于云巢灵囊
    res_scout = w.handle(token, "/灵鹤 黑风绝渊赤焰")
    assert res_scout["ok"] is True
    assert res_scout.get("overflow") is True
    assert res_scout["status"]["stones"] == 470
    assert "云巢" in res_scout["text"] or "灵囊" in res_scout["text"]
    assert res_scout["status"]["crane_pending_item"] is not None
    pending_name = res_scout["status"]["crane_pending_item"]["name"]

    # 3. 云巢尚有仙物时，禁止再次派遣
    res_scout_again = w.handle(token, "/灵鹤 落霞密林")
    assert res_scout_again["ok"] is False
    assert "未取" in res_scout_again["error"]

    # 4. 纳戒仍为 64 格满格时，尝试领取被拦截
    res_claim_blocked = w.handle(token, "/灵鹤 领取")
    assert res_claim_blocked["ok"] is False
    assert "已满" in res_claim_blocked["error"]

    # 5. 腾挪空间（移除 1 格，变为 63 格）
    char = w.get_char(token)
    removed = char.items.pop(0)
    CharacterRepository.save(char)
    assert char.is_bag_full() is False

    # 6. 成功自仙鹤云巢领取机缘
    res_claim_ok = w.handle(token, "/灵鹤 领取")
    assert res_claim_ok["ok"] is True
    assert pending_name in res_claim_ok["text"]
    assert res_claim_ok["status"]["crane_pending_item"] is None
    assert any(it.get("name") == pending_name for it in res_claim_ok["status"]["items"])

