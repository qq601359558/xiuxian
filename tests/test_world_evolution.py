"""世界演变：/世情 升级 + 态势数据结构"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from core.schedule import build_world_evolution, format_world_schedule


def test_evolution_payload_and_schedule():
    init_db()
    c = WorldClock.create_new_character("evo_viewer", "观测者")
    c.location = "青云坊市客栈"
    CharacterRepository.save(c)
    ev = build_world_evolution(viewer_id=c.id)
    assert ev["ok"] is True
    assert ev["kind"] == "world_evolution"
    for key in ("director", "arcs", "faction", "echo", "era", "summary_lines"):
        assert key in ev, key
    r = format_world_schedule(viewer_id=c.id)
    text = r["text"]
    assert "世界演变" in text
    assert "天道导演" in text
    assert "世界弧" in text
    assert "势力格局" in text
    assert "望气" in text
    assert "纪元回流" in text
    assert "频道" in text or "近闻" in text
    assert r.get("evolution") and r["evolution"].get("kind") == "world_evolution"
    rs = format_world_schedule(viewer_id=c.id, simple=True)
    assert "世界演变" in rs["text"]
    print("✓ 世界演变 payload 与 /世情 文本")


def test_server_shiing_route():
    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World

    init_db()
    w = World(auto_tick=False)
    sess = w.join("演变客", user_id="evo_cli_user")
    tok = sess["token"]
    for cmd in ("/世情", "/世界演变", "/世情 简"):
        r = w.handle(tok, cmd)
        assert r.get("ok") is True, (cmd, r)
        assert "世界演变" in r.get("text", "") or "摘要" in r.get("text", "")
    r2 = w.handle(tok, "/世界演变")
    assert r2.get("evolution") is not None
    print("✓ 服务器 /世情 /世界演变")


if __name__ == "__main__":
    test_evolution_payload_and_schedule()
    test_server_shiing_route()
    print("\nworld evolution tests passed")
