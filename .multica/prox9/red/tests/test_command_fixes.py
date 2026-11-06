"""回归：指令冲突修复后的关键探针"""
import os
import sys
from pathlib import Path

os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ.setdefault("AI_REQUIRED", "0")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_server_ai_aliases_lowercase():
    from server.world import WORLD

    WORLD.stop_tick()
    j = WORLD.join("别名探针", user_id="cmd_alias_p")
    t = j["token"]
    r1 = WORLD.handle(t, "/AI日志")
    r2 = WORLD.handle(t, "/ailog")
    r3 = WORLD.handle(t, "/AI自检")
    r4 = WORLD.handle(t, "/ai")
    assert r1.get("ok") is True, r1
    assert r2.get("ok") is True, r2
    # AI自检 may fail without key but must not be 未知指令
    assert "未知" not in (r3.get("error") or r3.get("text") or ""), r3
    assert "未知" not in (r4.get("error") or r4.get("text") or ""), r4
    print("✓ /AI日志 /ailog /AI自检 /ai 均可路由")


def test_server_briefing_and_worldinfo():
    from server.world import WORLD

    WORLD.stop_tick()
    j = WORLD.join("近况探针", user_id="cmd_brief_p")
    t = j["token"]
    r = WORLD.handle(t, "/近况")
    assert r.get("ok") is True, r
    assert r.get("text")
    r2 = WORLD.handle(t, "/世情")
    assert r2.get("ok") is True, r2
    text = r2.get("text") or ""
    assert len(text) > 20
    print("✓ /近况 /世情 可用且含文本")


def test_cli_karma_alias_not_shadowed():
    """CLI 源码：/因果 不得再出现在 revenge 分支"""
    src = Path(r"D:\codex\xiuxian\cli\main.py").read_text(encoding="utf-8")
    assert 'elif action in ["/回访", "/因果", "revenge"]' not in src
    assert 'elif action in ["/因果", "karma", "/仇怨"]' in src
    print("✓ CLI /因果 专指因果链，/回访 专指回访")


def test_cli_help_no_ghost_commands():
    src = Path(r"D:\codex\xiuxian\cli\main.py").read_text(encoding="utf-8")
    # 帮助不再宣称 CLI 实现了 /说 /释放
    assert "[bold yellow]/说 <内容>" not in src
    assert "局域网专有" in src
    print("✓ CLI 帮助不再列未实现的 /说 /释放")


def main():
    test_server_ai_aliases_lowercase()
    test_server_briefing_and_worldinfo()
    test_cli_karma_alias_not_shadowed()
    test_cli_help_no_ghost_commands()
    print("\n✅ 指令修复回归通过")


if __name__ == "__main__":
    main()
