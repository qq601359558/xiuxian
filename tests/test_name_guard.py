"""
专名门禁 + 名物入册
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, WorldStateRepository
from core.name_guard import reject_player_creation, looks_like_name_creation
from core.name_registry import register_heard, review_and_register, format_board, _KEY


def test_guard_blocks_create():
    init_db()
    r = reject_player_creation("我在坊市东边建了一座幽冥血池，命名为血海宫")
    assert r is not None and r.get("rejected") is True
    r2 = reject_player_creation("我门派叫太虚剑宗")
    assert r2 is not None
    r3 = reject_player_creation("我师父叫赤焰老祖")
    assert r3 is not None
    print("✓ 拒绝口述造物")


def test_guard_allows_normal():
    init_db()
    assert reject_player_creation("我拱手向柳三娘见礼") is None
    assert reject_player_creation("我去青云坊市客栈") is None  # 已有地名
    assert reject_player_creation("请问哪里有丹药") is None
    print("✓ 正常言行不误伤")


def test_register_heard():
    init_db()
    WorldStateRepository.delete(_KEY)
    item = register_heard("无名荒谷", ntype="location", desc="听闻", source="npc_talk", confidence=0.7)
    assert item is not None
    assert register_heard("无名荒谷") is None  # 去重
    board = format_board()
    assert "无名荒谷" in board
    print("✓ 听闻册")


def test_player_source_forbidden():
    init_db()
    WorldStateRepository.delete(_KEY)
    r = review_and_register("我建了一座新城", source="player_do", author="甲")
    assert r["ok"] is False
    assert r["reason"] == "player_forbidden"
    print("✓ 玩家来源禁止入册")


def test_gm_rule_register():
    init_db()
    WorldStateRepository.delete(_KEY)
    r = review_and_register(
        "公告：新开秘境「太虚残界」位于万星古岛方向。",
        source="gm_broadcast",
        author="GM",
    )
    assert r["ok"] is True
    # 无 AI 时规则候选
    assert r.get("registered") is not None
    print("✓ GM 公告入册", [x["name"] for x in r["registered"]])


if __name__ == "__main__":
    test_guard_blocks_create()
    test_guard_allows_normal()
    test_register_heard()
    test_player_source_forbidden()
    test_gm_rule_register()
    print("\n✅ name-guard-registry 测试通过")
