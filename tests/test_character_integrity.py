"""
单元测试：道体合规守恒核心引擎测试
"""
import pytest
import time
from core.models import (
    Character, Realm, Lifespan, SpiritualRoot, RootType, Element, CharacterStatus
)
from core.items import ItemEntity, ItemKind
from core.character_integrity import (
    CharacterIntegrity,
    CharacterDeadError,
    CharacterBusyError,
    InsufficientCurrencyError,
    BagFullError,
)


def _make_char() -> Character:
    now = time.time()
    return Character(
        user_id="u_audit_01",
        name="青玄子",
        realm=Realm(tier=1, sub_tier=1, current_exp=100),
        lifespan=Lifespan(
            birth_base=100.0,
            accumulated_gain=0.0,
            death_timestamp=now + 86400 * 10,
        ),
        spiritual_root=SpiritualRoot(
            root_type=RootType.TRUE,
            elements=[Element.FIRE, Element.WOOD],
            efficiency=1.0,
        ),
        spirit_stones=200,
    )


def test_assert_alive_ok():
    char = _make_char()
    CharacterIntegrity.assert_alive(char)


def test_assert_alive_raises_when_dead_or_lifespan_zero():
    char = _make_char()
    char.status = CharacterStatus.DEAD
    with pytest.raises(CharacterDeadError):
        CharacterIntegrity.assert_alive(char)

    char.status = CharacterStatus.IDLE
    char.lifespan.death_timestamp = time.time() - 100  # 寿尽
    with pytest.raises(CharacterDeadError):
        CharacterIntegrity.assert_alive(char)
    assert char.status == CharacterStatus.DEAD


def test_assert_idle_meditating():
    char = _make_char()
    char.status = CharacterStatus.MEDITATING
    # 白名单命令放行
    CharacterIntegrity.assert_idle(char, action="/出关")
    CharacterIntegrity.assert_idle(char, action="/look")
    # 非白名单命令拦截
    with pytest.raises(CharacterBusyError):
        CharacterIntegrity.assert_idle(char, action="/挖宝")


def test_assert_idle_captured():
    char = _make_char()
    char.status = CharacterStatus.CAPTURED
    CharacterIntegrity.assert_idle(char, action="/自救")
    with pytest.raises(CharacterBusyError):
        CharacterIntegrity.assert_idle(char, action="/探险")


def test_currency_and_deduct():
    char = _make_char()
    char.spirit_stones = 50
    with pytest.raises(InsufficientCurrencyError):
        CharacterIntegrity.assert_currency(char, 100)

    CharacterIntegrity.deduct_currency(char, 30)
    assert char.spirit_stones == 20


def test_assert_bag_space():
    char = _make_char()
    char.items = [
        ItemEntity(name=f"符箓_{i}", kind=ItemKind.CONSUMABLE) for i in range(63)
    ]
    CharacterIntegrity.assert_bag_space(char, 1)  # 64，刚好
    with pytest.raises(BagFullError):
        CharacterIntegrity.assert_bag_space(char, 2)  # 65 > 64


def test_audit_character_repairs():
    char = _make_char()
    # 模拟数据下溢与越界
    char.realm.tier = -1
    char.realm.sub_tier = 5
    char.realm.current_exp = -10
    char.spirit_stones = -50
    char.vault_stones = -10
    char.stall_earnings = -5
    char.karma.dao_heart = 150
    char.karma.sin_value = -20
    char.karma.merit_value = -10

    warns = CharacterIntegrity.audit_character(char, auto_repair=True)
    assert len(warns) >= 7
    assert char.realm.tier == 0
    assert char.realm.sub_tier == 3
    assert char.realm.current_exp == 0
    assert char.spirit_stones == 0
    assert char.vault_stones == 0
    assert char.stall_earnings == 0
    assert char.karma.dao_heart == 100
    assert char.karma.sin_value == 0
    assert char.karma.merit_value == 0
