"""
闭关锁定：入定中不可迁跃/斗法
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.models import CharacterStatus


def test_meditate_blocks_travel():
    c = WorldClock.create_new_character("med_lock_user", "闭关锁客")
    # 跳过新手期便于测
    c.born_at = time.time() - 80 * 3600.0
    start = WorldClock.start_meditation(c, hours_planned=2.0)
    assert start["success"] is True
    assert c.status == CharacterStatus.MEDITATING

    # 模拟 world 层白名单逻辑
    med_ok = (
        "/look", "/here", "/who", "/help", "/emerge", "/出关",
        "/legacy", "/goals", "/qi", "/season", "/agenda", "/roster",
        "/bounty", "/profile", "/logout",
    )
    for blocked in ("/go", "/斗法", "/做", "/秘境 落霞古洞", "/寄存 10", "/拜入 青云宗"):
        assert blocked.split()[0] not in med_ok
    assert "/出关" in med_ok
    assert "/look" in med_ok

    # 出关后恢复
    res = WorldClock.settle_meditation(c, force_interrupt=True)
    assert res["success"] is True
    assert c.status == CharacterStatus.IDLE
    print("✓ 闭关锁定：只读敕令 + 出关")


def test_world_handle_gate():
    from server.world import World

    w = World(auto_tick=False)
    r = w.join("闭关门禁测")
    token = r["token"]
    char = w.get_char(token)
    char.born_at = time.time() - 80 * 3600.0
    WorldClock.start_meditation(char, hours_planned=1.0)
    from storage.db import CharacterRepository
    CharacterRepository.save(char)

    res = w.handle(token, "/go 青云宗外门山门")
    assert res.get("ok") is False
    assert "闭关" in (res.get("error") or "")
    assert res.get("meditating") is True

    res2 = w.handle(token, "/look")
    assert res2.get("ok") is True
    assert res2.get("status", {}).get("meditating") is True

    res3 = w.handle(token, "/出关")
    assert res3.get("ok") is True
    print("✓ World 层闭关门禁生效")


if __name__ == "__main__":
    test_meditate_blocks_travel()
    test_world_handle_gate()
    print("\n✅ 闭关锁定测试通过")
