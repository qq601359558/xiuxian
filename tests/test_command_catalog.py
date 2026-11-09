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


def test_catalog_phase2_new_commands():
    """二期 §8.4 目录侧断言（集成岗收口）：主命令 106→108（实测口径）。

    Spec §8.4 的名义计数为 100→102，与目录在一期基线的实测 106 条
    主命令相差 6 条既有命令（all_entries 按主命令去重、别名不另计行）；
    此处以实测口径落断言，并逐条验新命令的主命令/别名/用法齐备。
    """
    cj = catalog_json()
    # B1-5（playability-block1）：新增 /修炼 主命令，实测计数 108→109。
    assert cj["count"] == 109
    by_cmd = {e["cmd"]: e for e in cj["commands"]}
    assert "/命途" in by_cmd and "/回应" in by_cmd
    assert "/fate_thread" in by_cmd["/命途"]["aliases"]
    assert "/respond_drama" in by_cmd["/回应"]["aliases"]
    assert any(h["cmd"] == "/命途" for h in search_commands("命途"))
    assert any(h["cmd"] == "/回应" for h in search_commands("回应"))
    assert "命途" in format_help("命途") and "回应" in format_help("回应")
    print("✓ 二期新命令目录补登：/命途 /回应（108 条主命令）")


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
