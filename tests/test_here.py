"""同场一览测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.here import list_here, format_here
from storage.db import CharacterRepository, init_db


def main():
    init_db()
    viewer = WorldClock.create_new_character("here_viewer", "观者")
    viewer.location = "落霞山灵泉(野外)"
    CharacterRepository.save(viewer)

    npc = WorldClock.create_new_character("npc_here_1", "山中客")
    npc.location = "落霞山灵泉(野外)"
    npc.karma.add_sin(50)
    CharacterRepository.save(npc)

    far = WorldClock.create_new_character("npc_here_2", "远方人")
    far.location = "青云坊市客栈"
    CharacterRepository.save(far)

    rows = list_here(viewer)
    names = {r["name"] for r in rows}
    assert "山中客" in names
    assert "远方人" not in names
    assert "观者" not in names  # 默认不含自己

    text = format_here(viewer, rows)
    assert "山中客" in text
    assert "落霞山灵泉" in text

    # 含自己
    rows2 = list_here(viewer, include_self=True)
    assert any(r["name"] == "观者" for r in rows2)

    print("✓ 同场检索只含当前地点")
    print("✓ 默认不含自己，可 include_self")
    print("✓ 文本格式化可用")
    print("\n✅ 同场一览 测试通过")


if __name__ == "__main__":
    main()
