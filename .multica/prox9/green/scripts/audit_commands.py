"""指令盘点：别名冲突、CLI/服是否覆盖、帮助与实现差集"""
from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\codex\xiuxian")
CLI = ROOT / "cli" / "main.py"
SRV = ROOT / "server" / "world.py"


def extract_cli_aliases(src: str):
    """cli: elif action in ["/a", "b"]:"""
    aliases = []  # list of (cmd, line)
    for i, line in enumerate(src.splitlines(), 1):
        m = re.search(r'(?:elif|if)\s+action\s+in\s+\[([^\]]+)\]', line)
        if not m:
            continue
        parts = re.findall(r'["\']([^"\']+)["\']', m.group(1))
        for p in parts:
            aliases.append((p, i))
    return aliases


def extract_srv_aliases(src: str):
    aliases = []
    for i, line in enumerate(src.splitlines(), 1):
        m = re.search(r'(?:if|elif)\s+action\s+in\s+\(([^)]+)\)', line)
        if not m:
            continue
        parts = re.findall(r'["\']([^"\']+)["\']', m.group(1))
        for p in parts:
            aliases.append((p, i))
    return aliases


def extract_cli_help(src: str):
    helps = []
    for line in src.splitlines():
        for m in re.finditer(r'\[bold yellow\](/[^\s<\[]+)', line):
            helps.append(m.group(1))
    return helps


def main():
    cli_src = CLI.read_text(encoding="utf-8")
    srv_src = SRV.read_text(encoding="utf-8")
    cli = extract_cli_aliases(cli_src)
    srv = extract_srv_aliases(srv_src)
    help_cmds = extract_cli_help(cli_src)

    print("=" * 60)
    print("1) CLI 别名冲突（同一别名被多个分支声明）")
    print("=" * 60)
    cli_map = defaultdict(list)
    for cmd, ln in cli:
        cli_map[cmd].append(ln)
    conflicts = {k: v for k, v in cli_map.items() if len(v) > 1}
    if not conflicts:
        print("  （无）")
    else:
        for cmd, lines in sorted(conflicts.items(), key=lambda x: -len(x[1])):
            print(f"  CONFLICT {cmd!r} 出现在 CLI 行 {lines} → 先命中 {min(lines)}，后者死代码")
    # 显示死分支：同一 cmd 后面的 elif 永远不可达
    print()
    print("=" * 60)
    print("2) 服端别名冲突")
    print("=" * 60)
    srv_map = defaultdict(list)
    for cmd, ln in srv:
        srv_map[cmd].append(ln)
    sconf = {k: v for k, v in srv_map.items() if len(v) > 1}
    if not sconf:
        print("  （无）")
    else:
        for cmd, lines in sorted(sconf.items(), key=lambda x: -len(x[1])):
            print(f"  CONFLICT {cmd!r} 服端行 {lines}")

    print()
    print("=" * 60)
    print("3) CLI vs 服端：只在一端存在的指令（玩法不对等）")
    print("=" * 60)
    cli_set = set(cli_map)
    srv_set = set(srv_map)
    only_cli = sorted(cli_set - srv_set)
    only_srv = sorted(srv_set - cli_set)
    print(f"  CLI 共 {len(cli_set)} 别名；服端共 {len(srv_set)} 别名")
    print(f"  仅 CLI（{len(only_cli)}）：")
    for c in only_cli:
        print(f"    {c} @ L{cli_map[c][0]}")
    print(f"  仅服端（{len(only_srv)}）：")
    for c in only_srv:
        print(f"    {c} @ L{srv_map[c][0]}")

    print()
    print("=" * 60)
    print("4) 帮助菜单 vs CLI 实现")
    print("=" * 60)
    help_set = set(help_cmds)
    # help 里指令可能带参数说明前缀已截取
    impl_cmds = {c for c in cli_map if c.startswith("/")}
    # 帮助有但 CLI 无
    help_not_impl = []
    for h in sorted(help_set):
        # 帮助可能写 /闭关 <...>，我们已只取 /token
        if h not in impl_cmds:
            help_not_impl.append(h)
    impl_not_help = sorted(impl_cmds - help_set)
    print(f"  帮助出现但 CLI 分支无此精确别名: {help_not_impl}")
    print(f"  CLI 有但帮助未列（{len(impl_not_help)}）:")
    for c in impl_not_help:
        print(f"    {c} @ L{cli_map[c][0]}")
    # 帮助重复
    print()
    print("  帮助菜单重复项:")
    hc = defaultdict(int)
    for h in help_cmds:
        hc[h] += 1
    dups = {k: v for k, v in hc.items() if v > 1}
    print(f"    {dups or '（无）'}")

    print()
    print("=" * 60)
    print("5) 语义别名撞车（不同玩法共享前缀/别名）")
    print("=" * 60)
    # 已在 conflicts；额外：近义
    semantic = [
        ("/因果", "CLI: karma@746 vs revenge@957"),
        ("/回访", "revenge 专用，帮助有"),
        ("/世情", "CLI world tick vs 服 /worldinfo"),
        ("/npc", "CLI npctick vs 服 /tick /npc 同义"),
        ("/交谈", "帮助重复两次"),
    ]
    for row in semantic:
        print(f"  · {row[0]} — {row[1]}")

    print()
    print("=" * 60)
    print("6) 数量统计")
    print("=" * 60)
    print(f"  CLI 分支声明总次数={len(cli)} 唯一={len(cli_set)}")
    print(f"  服端分支声明总次数={len(srv)} 唯一={len(srv_set)}")
    print(f"  帮助条目={len(help_cmds)} 唯一={len(help_set)}")
    print(f"  冲突数 CLI={len(conflicts)} 服={len(sconf)}")


if __name__ == "__main__":
    main()
