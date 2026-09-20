"""
content-pack：内容量验收
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, WorldStateRepository
from core.content_pack import (
    EVENT_CHAIN_TEMPLATES,
    THEME_POOL,
    MASTER_TASKS,
    SWORN_TASKS,
    EXCHANGE_SHOP,
    RARE_SHOP,
    AMBIENT_RUMORS,
)


def test_pools_sizes():
    assert len(EVENT_CHAIN_TEMPLATES) >= 20, len(EVENT_CHAIN_TEMPLATES)
    assert len(THEME_POOL) >= 15
    assert len(MASTER_TASKS) >= 8
    assert len(SWORN_TASKS) >= 4
    assert len(EXCHANGE_SHOP) >= 10
    assert len(RARE_SHOP) >= 4
    assert len(AMBIENT_RUMORS) >= 20
    print(
        f"✓ 池规模 奇遇{len(EVENT_CHAIN_TEMPLATES)} 日环{len(THEME_POOL)} "
        f"师门{len(MASTER_TASKS)} 结义{len(SWORN_TASKS)} "
        f"兑换{len(EXCHANGE_SHOP)}+{len(RARE_SHOP)} 传闻{len(AMBIENT_RUMORS)}"
    )


def test_templates_shape():
    for tpl in EVENT_CHAIN_TEMPLATES:
        assert len(tpl["steps"]) >= 2, tpl["title"]
        for st in tpl["steps"]:
            assert len(st["choices"]) >= 2
            for ch in st["choices"]:
                assert "id" in ch and "label" in ch and "effects" in ch
    print("✓ 奇遇模板结构")


def test_theme_hooks():
    allowed = {"explore", "donate", "visit", "hunt"}
    for th in THEME_POOL:
        assert th["hook"] in allowed, th
        assert th.get("label") and th.get("lore")
    print("✓ 日环 hook 合法")


def test_ambient_rumor():
    init_db()
    WorldStateRepository.delete("rumor_pool")
    WorldStateRepository.delete("ambient_rumor_day")
    from core import rumors

    hit = None
    for _ in range(50):
        hit = rumors.maybe_ambient_tick(chance=1.0)
        if hit:
            break
    assert hit is not None
    rows = rumors.list_rumors(5)
    assert rows
    print("✓ 环境传闻可写入", hit["text"][:40])


def test_event_chains_uses_pack():
    from core import event_chains

    assert len(event_chains.TEMPLATES) >= 20
    print("✓ event_chains 挂载内容包")


if __name__ == "__main__":
    test_pools_sizes()
    test_templates_shape()
    test_theme_hooks()
    test_ambient_rumor()
    test_event_chains_uses_pack()
    print("\n✅ content-pack 测试通过")
