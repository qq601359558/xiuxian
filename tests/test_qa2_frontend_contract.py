"""QA 第二轮 · 重点 6：前端契约深查。

- status 键集合差：web/app.js 以 st.* 读取的全部键必须 ⊆ server _status_dict 下发键
  （前端读了但后端从不下发的键 = 静默 undefined，属契约缺陷）；
- data-cmd × server：index.html 全部命令基必须在 server/world.py 有处理器字面量；
- data-cmd × CLI：未在 CLI 派发的命令必须落在 CLI 帮助明示的「局域网专有」清单内，
  否则即未声明的双端平价缺口（QA2-03 证据：失败时列出未声明集合）。
"""
import ast
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

ROOT = Path(__file__).resolve().parent.parent


def _status_keys():
    tree = ast.parse((ROOT / "server" / "world.py").read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_status_dict":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Dict):
                    for k in sub.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.add(k.value)
    return keys


def _appjs_reads():
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    return set(re.findall(r"\bst\.([A-Za-z_][A-Za-z0-9_]*)", js))


def _data_cmd_bases():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    return sorted({c.split()[0] for c in re.findall(r'data-cmd="([^"]+)"', html)})


def _cli_dispatch_literals():
    cli = (ROOT / "cli" / "main.py").read_text(encoding="utf-8")
    lits = set()
    for line in cli.splitlines():
        if "action" in line:
            lits.update(re.findall(r'"([^"]{1,12})"', line))
    return lits


def _cli_documented_lan_only():
    cli = (ROOT / "cli" / "main.py").read_text(encoding="utf-8")
    m = re.search(r"局域网专有：([^\n]*)", cli)
    assert m, "CLI 帮助应有局域网专有声明行"
    return set(re.findall(r"/[^\s/]+", m.group(1)))


def test_status_keys_frontend_subset_of_backend():
    sent = _status_keys()
    read = _appjs_reads()
    missing = read - sent
    assert not missing, f"app.js 读取但后端从不下发的键：{sorted(missing)}"
    unread = sent - read
    print(f"✓ status 契约：前端读 {len(read)} 键全部有下发（后端共 {len(sent)} 键）；"
          f"下发未被 st.* 直读 {len(unread)} 键（多经解构/别名消费，记录备查）：{sorted(unread)}")


def test_data_cmd_all_handled_by_server():
    server = (ROOT / "server" / "world.py").read_text(encoding="utf-8")
    bases = _data_cmd_bases()
    missing = [b for b in bases if b not in server]
    assert not missing, f"index.html data-cmd 无 server 处理器：{missing}"
    print(f"✓ data-cmd × server：{len(bases)} 个命令基全部有 server 处理器")


def test_data_cmd_cli_parity_or_documented():
    bases = _data_cmd_bases()
    lits = _cli_dispatch_literals()
    documented = _cli_documented_lan_only()
    undocumented = []
    for b in bases:
        if b in lits or b.lstrip("/") in lits:
            continue
        if b in documented:
            continue
        undocumented.append(b)
    assert not undocumented, (
        f"CLI 未派发且未在帮助中声明为局域网专有的命令（双端平价缺口）：{undocumented}"
    )
    print("✓ data-cmd × CLI：全部命令或有 CLI 处理器、或已声明局域网专有")
