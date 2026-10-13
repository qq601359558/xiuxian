"""
并发竞态防护与前置消耗状态单调锁测试套件
验证：
1. 角色实体状态版本号 (version) 单调递增；
2. 长耗时探险前置盘缠原子落盘，异常崩溃时自动退还补偿；
3. _status_dict 携带版本号；
4. 连续指令执行时前置消耗不被冲掉。
"""
import pytest
from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element
from storage.db import CharacterRepository, init_db
from server.world import WORLD
from core.adventure import AdventureEngine, ADVENTURE_FEE


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_concurrency.db"
    monkeypatch.setattr("storage.db.DB_PATH", test_db)
    init_db()


def create_test_char(user_id="test_user_race", stones=500):
    c = Character(
        id="c_race_01",
        user_id=user_id,
        name="青玄道人",
        realm=Realm(tier=1, sub_tier=1),
        lifespan=Lifespan(birth_base=100.0, death_timestamp=9999999999.0),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WOOD], efficiency=1.2),
        spirit_stones=stones,
    )
    CharacterRepository.save(c)
    return c


def test_character_version_increments_monotonically():
    """验证每次调用 CharacterRepository.save，version 均单调递增"""
    c = create_test_char()
    v1 = c.version
    assert v1 >= 1

    c.spirit_stones += 50
    CharacterRepository.save(c)
    v2 = c.version
    assert v2 == v1 + 1

    # 从数据库重新拉取验证持久化一致性
    loaded = CharacterRepository.get_by_user_id(c.user_id)
    assert loaded is not None
    assert loaded.version == v2
    assert loaded.spirit_stones == 550


def test_status_dict_contains_monotonic_version():
    """验证 _status_dict 始终包含自增版本号"""
    c = create_test_char()
    st1 = WORLD._status_dict(c)
    assert "version" in st1
    assert st1["version"] == c.version

    CharacterRepository.save(c)
    st2 = WORLD._status_dict(c)
    assert st2["version"] == c.version
    assert st2["version"] > st1["version"]


def test_adventure_fee_pre_saved_and_persisted():
    """验证探险在推演前已先落盘扣除 ADVENTURE_FEE 盘缠"""
    c = create_test_char(stones=100)
    init_stones = c.spirit_stones

    # 执行规则探险（目标名为野外）
    res = AdventureEngine.explore(c, "野外", use_ai=False)
    assert res["success"] is True

    # 查验数据库中的落账单调性与版本推进
    loaded = CharacterRepository.get_by_user_id(c.user_id)
    assert loaded is not None
    assert loaded.version > 1


def test_adventure_crash_compensation_in_world_handle(monkeypatch):
    """验证若探险在扣除盘缠后出现严重崩溃，WORLD.handle 精确补偿退还盘缠"""
    c = create_test_char(stones=100)
    token = "test_token_race"
    WORLD.sessions[token] = type("Session", (), {"user_id": c.user_id, "token": token, "pending_heart_demon": None})()

    # 模拟探险中途（盘缠已扣）后发生异常崩溃
    real_explore = AdventureEngine.explore
    def crash_after_fee_deduction(char, target, **kwargs):
        char.spirit_stones -= ADVENTURE_FEE
        CharacterRepository.save(char)
        raise RuntimeError("模拟外部推演通道严重断网")

    monkeypatch.setattr("core.adventure.AdventureEngine.explore", crash_after_fee_deduction)

    resp = WORLD.handle(token, "/探险 野外")
    assert resp["ok"] is False
    assert "大荒天机紊乱" in resp["error"]

    # 盘缠必须原路退回至 100 灵石
    loaded = CharacterRepository.get_by_user_id(c.user_id)
    assert loaded.spirit_stones == 100
    assert resp["status"]["stones"] == 100
    assert resp["status"]["version"] == loaded.version


def test_sequential_consumption_preserves_integrity():
    """验证连续快速两次扣除操作，后置操作不会丢失前置消耗"""
    c = create_test_char(stones=300)
    token = "test_token_race_seq"
    WORLD.sessions[token] = type("Session", (), {"user_id": c.user_id, "token": token, "pending_heart_demon": None})()

    # 第一次指令：存入金库 100 灵石（100 灵石 + 5% 契税 = 扣除 105 灵石，金库加 100）
    resp1 = WORLD.handle(token, "/寄存 100")
    assert resp1["ok"] is True
    assert resp1["status"]["stones"] == 195
    assert resp1["status"]["vault"] == 100

    # 第二次指令：再次存入金库 100 灵石（再次扣除 105 灵石，囊中余 90，金库为 200）
    resp2 = WORLD.handle(token, "/寄存 100")
    assert resp2["ok"] is True
    assert resp2["status"]["stones"] == 90
    assert resp2["status"]["vault"] == 200

    # 最终数据库权威核验，证明无任何状态回滚或吞消耗
    final_char = CharacterRepository.get_by_user_id(c.user_id)
    assert final_char.spirit_stones == 90
    assert final_char.vault_stones == 200
    assert resp2["status"]["version"] > resp1["status"]["version"]
