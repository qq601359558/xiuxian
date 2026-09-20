"""
深化：导师快照 API 数据 + 质量自检 + 网页指令路由
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, WorldStateRepository
from core.world_director import director_snapshot, director_quality_report


def test_quality_report_checks_gate():
    init_db()
    q = director_quality_report()
    assert q["total"] >= 8
    names = {c["name"] for c in q["checks"]}
    assert "gate_rejects_illegal" in names
    assert "gate_strips_numeric" in names
    assert "world_arc" in names
    assert "faction" in names
    assert "player_echo" in names
    assert "era_reentry" in names
    ok_map = {c["name"]: c["ok"] for c in q["checks"]}
    assert ok_map["gate_rejects_illegal"] is True
    assert ok_map["gate_strips_numeric"] is True
    print("✓ 导师质量自检门禁项")


def test_snapshot_shape():
    init_db()
    snap = director_snapshot()
    assert snap["ok"] is True
    for key in ("director", "modifiers", "arcs", "faction", "echo", "era", "quality"):
        assert key in snap, key
    assert "board_text" in snap["director"]
    assert "checks" in snap["quality"]
    assert isinstance(snap["faction"].get("relations"), list)
    print("✓ /world/director 快照结构")


def test_server_ai_and_hud_commands():
    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    sess = w.join("深化修士", user_id="deepen_user")
    tok = sess["token"]
    for cmd in (
        "/ai",
        "/天道",
        "/世界弧",
        "/势力",
        "/望气",
        "/纪元回流",
        "/宗门令",
    ):
        r = w.handle(tok, cmd)
        assert r.get("ok") is True or cmd == "/ai", (cmd, r)
        assert r.get("text")
    ra = w.handle(tok, "/ai")
    assert ra.get("ok") is True
    assert "天道导演链路" in ra.get("text", "")
    assert "director_quality" in ra
    print("✓ 服务器深化指令与 /ai 链路自检")


if __name__ == "__main__":
    test_quality_report_checks_gate()
    test_snapshot_shape()
    test_server_ai_and_hud_commands()
    print("\ndeepen tests all passed")
