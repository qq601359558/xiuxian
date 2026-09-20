"""指令目录：模糊搜索与帮助"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")

from core.command_catalog import all_entries, search_commands, format_help, catalog_json


def test_catalog_and_fuzzy():
    entries = all_entries()
    assert len(entries) >= 40
    # 每条有 desc
    for e in entries:
        assert e.get("desc"), e
        assert e.get("cmd", "").startswith("/")
    hits = search_commands("天道")
    assert any(h["cmd"] == "/天道" for h in hits)
    hits2 = search_commands("/fac")
    assert any("势力" in h["cmd"] or "faction" in h["cmd"].lower() or h["cmd"] == "/势力" for h in hits2) or any(
        "/faction" == h["cmd"] for h in search_commands("faction")
    )
    hits3 = search_commands("望气")
    assert any(h["cmd"] == "/望气" for h in hits3)
    help_text = format_help("宗门")
    assert "宗门" in help_text and "—" in help_text
    help_all = format_help()
    assert "敕令目录" in help_all
    cj = catalog_json()
    assert cj["ok"] and cj["count"] >= 40
    print("✓ 指令目录与模糊搜索")


def test_server_help_and_commands_route():
    import config

    config.ALLOW_LOCAL_AI = True
    config.LLM_API_KEY = ""
    config.USE_CCSWITCH = False
    from server.world import World
    from storage.db import init_db
    import json
    from http.server import BaseHTTPRequestHandler
    # 只测 world.handle 帮助
    init_db()
    w = World(auto_tick=False)
    sess = w.join("帮主", user_id="cmd_help_user")
    tok = sess["token"]
    r = w.handle(tok, "/帮助")
    assert r.get("ok") is True
    assert "敕令目录" in r.get("text", "") or "观照" in r.get("text", "")
    r2 = w.handle(tok, "/帮助 天道")
    assert "天道" in r2.get("text", "")
    print("✓ /帮助 模糊筛选")


if __name__ == "__main__":
    test_catalog_and_fuzzy()
    test_server_help_and_commands_route()
    print("\ncommand catalog tests passed")
