"""
端到端集成测试：道体合规守恒与全功能基准门禁测试
"""
import pytest
import time
from server.world import World
from storage.db import CharacterRepository
from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element, CharacterStatus


@pytest.fixture
def clean_world():
    w = World()
    return w


def test_e2e_dead_character_gate(clean_world):
    """死者行动门禁拦截测试"""
    w = clean_world
    join_res = w.join("坐化老祖", user_id="u_dead_test")
    token = join_res["token"]
    char = w.get_char(token)
    assert char is not None

    # 模拟在世期间寿尽道消
    char.status = CharacterStatus.DEAD
    char.lifespan.death_timestamp = time.time() - 100.0
    char.death_cause = "大限已至"
    CharacterRepository.save(char)

    # 世俗指令应当被前置门禁拦截
    res = w.handle(token, "/前往 散修营地")
    assert not res.get("ok")
    assert "道身已殒" in res.get("error", "")

    res_explore = w.handle(token, "/探险")
    assert not res_explore.get("ok")
    assert "道身已殒" in res_explore.get("error", "")

    # 免控指令放行
    res_help = w.handle(token, "/help")
    assert res_help.get("ok")


def test_e2e_captured_character_gate(clean_world):
    """被擒角色门禁拦截测试"""
    w = clean_world
    join_res = w.join("被擒散修", user_id="u_captured_test")
    token = join_res["token"]
    char = w.get_char(token)
    assert char is not None

    # 标记为被擒状态
    char.status = CharacterStatus.CAPTURED
    CharacterRepository.save(char)

    # 尝试移动或探险被拦截
    res = w.handle(token, "/前往 散修营地")
    assert not res.get("ok")
    assert "身陷囹圄" in res.get("error", "")


def test_e2e_post_action_audit_repair():
    """入库后置审计自动修复下溢脏数据测试"""
    now = time.time()
    c = Character(
        user_id="u_repair_test",
        name="数据异常散修",
        realm=Realm(tier=-2, sub_tier=9, current_exp=-100),
        lifespan=Lifespan(
            birth_base=100.0,
            accumulated_gain=0.0,
            death_timestamp=now + 86400 * 30,
        ),
        spiritual_root=SpiritualRoot(
            root_type=RootType.TRUE,
            elements=[Element.WOOD],
            efficiency=1.0,
        ),
        spirit_stones=-200,
        vault_stones=-50,
        stall_earnings=-20,
    )
    # 调用 CharacterRepository.save 落盘
    CharacterRepository.save(c)

    # 重新加载核验已被强制修复
    loaded = CharacterRepository.get_by_user_id("u_repair_test")
    assert loaded is not None
    assert loaded.realm.tier == 0
    assert loaded.realm.sub_tier == 3
    assert loaded.realm.current_exp == 0
    assert loaded.spirit_stones == 0
    assert loaded.vault_stones == 0
    assert loaded.stall_earnings == 0
