"""
阶段2：六榜 / 秘境事件链 / 宗门 / 灵气校准
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.leaderboard import LeaderboardEngine, score_realm, score_daohang, score_notoriety
from core.sect import join_sect, leave_sect, transmit_teaching, promote, evaluate_join
from core.secret_realm import SecretRealmEngine
from core.qi import global_qi_multiplier
from core.clock import WorldClock


def _make_char(name, tier=1, sub=0, loc="青云坊市客栈", sect=None, rank="散修"):
    now = time.time()
    c = Character(
        user_id=f"t2_{name}",
        name=name,
        realm=Realm(tier=tier, sub_tier=sub, current_exp=0),
        lifespan=Lifespan(birth_base=80.0, accumulated_gain=0.0, death_timestamp=now + 80 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.METAL], efficiency=1.1),
        location=loc,
        sect=sect,
        sect_rank=rank,
    )
    c.born_at = now - 80 * 3600.0
    return c


def test_qi_calibration():
    # 0 高阶 → 1.0；10 高阶不应打穿地板
    assert abs(global_qi_multiplier(0) - 1.0) < 1e-9
    m10 = global_qi_multiplier(10)
    assert m10 > 0.50  # 1/(1+0.8)=0.555
    m100 = global_qi_multiplier(100)
    assert m100 >= 0.50 - 1e-9
    print(f"✓ 灵气校准 m(0)=1.0 m(10)={m10:.3f} m(100)={m100:.3f}")


def test_leaderboard_scores():
    a = _make_char("甲", tier=2, sub=3)
    b = _make_char("乙", tier=1, sub=0)
    assert score_realm(a) > score_realm(b)
    a.karma.add_sin(200)
    assert score_notoriety(a) > score_notoriety(b)
    b.karma.add_merit(100)
    assert score_daohang(b) > score_daohang(a)
    # 格式化不抛错
    text = LeaderboardEngine.format_board("realm", n=3)
    assert "境界榜" in text
    print("✓ 六榜评分与格式化")


def test_sect_flow():
    # 非总坛不可拜
    c = _make_char("拜山人", loc="青云坊市客栈")
    r = join_sect(c, "青云宗")
    assert r["success"] is False

    c.location = "青云宗外门山门"
    c.karma.dao_heart = 80
    r = join_sect(c, "青云宗")
    assert r["success"] is True
    assert c.sect == "青云宗"
    assert c.sect_rank == "外门弟子"
    assert any("阵" in a for a in c.arrays)

    # 重复拜入
    r2 = join_sect(c, "万剑仙门")
    assert r2["success"] is False

    # 传功
    master = _make_char("师父", tier=3, loc="宗门玄元洞府", sect="青云宗", rank="内门弟子")
    r3 = transmit_teaching(master, c)
    assert r3["success"] is True
    assert c.realm.current_exp > 0

    # 晋升
    c.realm.tier = 2
    r4 = promote(c)
    assert r4["success"] is True
    assert c.sect_rank == "内门弟子"

    # 叛门
    r5 = leave_sect(c)
    assert r5["success"] is True
    assert c.sect is None
    print("✓ 宗门拜入/传功/晋升/叛门")


def test_secret_realm():
    c = _make_char("探秘者", tier=2, loc="落霞山灵泉")
    board = SecretRealmEngine.board_text()
    assert "落霞古洞" in board

    r = SecretRealmEngine.enter(c, "落霞古洞")
    assert r["success"] is True

    # 门槛
    weak = _make_char("练气仔", tier=1, loc="万星古岛")
    r2 = SecretRealmEngine.enter(weak, "万星遗迹残址")
    assert r2["success"] is False

    # 步进数次
    for _ in range(5):
        res = SecretRealmEngine.step(c)
        assert res.get("success")
        if SecretRealmEngine.active_chain(c) is None:
            break
    print("✓ 秘境进入与事件链步进")


def test_meditation_not_floor():
    c = _make_char("闭关者", tier=1)
    WorldClock.start_meditation(c, hours_planned=1.0, stones_to_pledge=0)
    settle = WorldClock.settle_meditation(c, force_interrupt=False, now=time.time() + 3600)
    assert settle["success"]
    assert settle["qi_multiplier"] >= 0.50 - 1e-9
    print("✓ 闭关结算稀释不低于 0.50")


if __name__ == "__main__":
    test_qi_calibration()
    test_leaderboard_scores()
    test_sect_flow()
    test_secret_realm()
    test_meditation_not_floor()
    print("\n✅ 阶段2 测试全部通过")
