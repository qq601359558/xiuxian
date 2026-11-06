"""人物详情 + NPC 主动互动测试"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.profile import build_profile, format_profile
from core.npc_proactive import NpcProactiveEngine
from storage.db import CharacterRepository, init_db
from core.models import CharacterStatus


def main():
    init_db()
    p = WorldClock.create_new_character("prof_p", "观相者")
    p.location = "青云坊市客栈"
    CharacterRepository.save(p)

    n = WorldClock.create_new_character("npc_prof_1", "相面客")
    n.location = "青云坊市客栈"
    n.sect = "四海散修商会"
    n.sect_rank = "牙人"
    n.spirit_stones = 9999
    CharacterRepository.save(n)

    # 自己
    me = build_profile(p, None)
    assert me["is_self"] and me["name"] == "观相者"
    assert "stones" in me
    print("✓ 自我档案含灵石")

    # 他人：脱敏
    other = build_profile(p, n)
    assert other["is_npc"]
    assert "stones" not in other
    assert other.get("stones_hint")
    print(f"✓ 他人档案脱敏：{other['stones_hint']}")

    # 性格/态度/议程字段
    assert "personality" in other
    assert "agenda" in other or other.get("agenda_key") is not None
    text = format_profile(p, other)
    assert "相面客" in text
    print(f"✓ 格式化可用：{text.splitlines()[0]}")

    # 主动互动
    NpcProactiveEngine.reset_cooldown(p.id)
    opens = NpcProactiveEngine.maybe_engage(p, force=True, max_speakers=1)
    assert isinstance(opens, list)
    if opens:
        assert opens[0]["line"]
        print(f"✓ NPC 主动：{opens[0]['text'][:40]}…")
    else:
        print("✓ 主动互动返回空列表（合法）")

    print("\n✅ 人物详情与主动互动 测试通过")


if __name__ == "__main__":
    main()
