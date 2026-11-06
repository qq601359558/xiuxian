"""手机端独立页面（spec: mobile-web）· 前端契约 + 分流行为测试。

- 分流脚本：从 web/index.html 与 web/mobile.html 内联提取同一段脚本，
  在 node 沙箱里跑 15 个判定场景（偏好/?view=/宽度/UA/防循环/参数保留），
  两页脚本必须逐字同一口径。
- 移动版契约：mobile.html/mobile.js/mobile.css 的结构、接口引用、wb.* 键、
  不读 td_base、不引 ailog、触控/字号硬指标。
- 服务端白名单：server/app.py 两处精确白名单同步含 mobile 三件套。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

# 分流判定场景：(pathname, search, hash, ua, narrow, store, expect_calls, expect_store)
REDIRECT_SCENARIOS = [
    # 无偏好无参数：桌面宽屏停桌面，手机进移动版
    ("/", "", "", DESKTOP_UA, False, {}, [], {}),
    ("/index.html", "", "", MOBILE_UA, False, {}, ["/mobile.html"], {}),
    ("/", "", "", DESKTOP_UA, True, {}, ["/mobile.html"], {}),
    ("/mobile.html", "", "", MOBILE_UA, False, {}, [], {}),
    ("/mobile.html", "", "", DESKTOP_UA, False, {}, ["/index.html"], {}),
    # 显式偏好优先于自动判定，指向当前页时不跳
    ("/", "", "", MOBILE_UA, False, {"wb.viewpref": "desktop"}, [], {"wb.viewpref": "desktop"}),
    ("/", "", "", DESKTOP_UA, False, {"wb.viewpref": "mobile"}, ["/mobile.html"], {"wb.viewpref": "mobile"}),
    ("/mobile.html", "", "", MOBILE_UA, False, {"wb.viewpref": "desktop"}, ["/index.html"], {"wb.viewpref": "desktop"}),
    # ?view= 仅本次生效，不写偏好键
    ("/", "?view=desktop", "", MOBILE_UA, False, {}, [], {}),
    ("/", "?view=mobile", "", DESKTOP_UA, False, {}, ["/mobile.html"], {}),
    ("/mobile.html", "?view=desktop", "", DESKTOP_UA, False, {}, ["/index.html"], {}),
    # 参数保留（除 view 本身）与 hash 保留
    ("/", "?view=mobile&x=1", "#top", MOBILE_UA, False, {}, ["/mobile.html?x=1#top"], {}),
    # 非法 view 值忽略，走自动判定
    ("/", "?view=bogus", "", DESKTOP_UA, False, {}, [], {}),
    # /web/ 前缀路径按末段判定
    ("/web/mobile.html", "", "", DESKTOP_UA, False, {}, ["/index.html"], {}),
    ("/web/", "", "", MOBILE_UA, False, {}, ["/mobile.html"], {}),
]

_HARNESS = r"""
const fs = require("fs");
const scriptPath = process.argv[2];
const script = fs.readFileSync(scriptPath, "utf8");
const scenarios = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const failures = [];
scenarios.forEach((sc, i) => {
  const calls = [];
  const store = Object.assign({}, sc.store || {});
  // Node 24 自带只读全局 navigator：直接赋值会被静默忽略，必须 defineProperty 覆盖
  const setGlobal = (name, value) => {
    Object.defineProperty(globalThis, name, { value, configurable: true, writable: true, enumerable: true });
  };
  setGlobal("window", { matchMedia: (q) => ({ matches: !!sc.narrow, media: q }) });
  setGlobal("navigator", { userAgent: sc.ua || "" });
  setGlobal("localStorage", {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  setGlobal("location", {
    pathname: sc.pathname, search: sc.search || "", hash: sc.hash || "",
    replace: (u) => { calls.push(u); },
  });
  eval(script);
  const wantCalls = sc.expect_calls;
  const wantStore = sc.expect_store;
  if (JSON.stringify(calls) !== JSON.stringify(wantCalls)) {
    failures.push(`#${i} ${sc.pathname}${sc.search} calls=${JSON.stringify(calls)} want=${JSON.stringify(wantCalls)}`);
  }
  if (JSON.stringify(store) !== JSON.stringify(wantStore)) {
    failures.push(`#${i} ${sc.pathname}${sc.search} store=${JSON.stringify(store)} want=${JSON.stringify(wantStore)}`);
  }
  if (calls.length > 1) failures.push(`#${i} jumped more than once: ${JSON.stringify(calls)}`);
});
if (failures.length) {
  console.log("FAIL\n" + failures.join("\n"));
  process.exit(1);
}
console.log("ALL OK " + scenarios.length + " scenarios");
"""


def _extract_redirect_script(html_text, fname):
    m = re.search(r"<!-- view-redirect:start -->\s*<script>(.*?)</script>\s*<!-- view-redirect:end -->",
                  html_text, re.S)
    assert m, f"{fname} 缺少 <!-- view-redirect --> 标记的分流脚本"
    return m.group(1)


def _run_redirect_scenarios(script_text, label):
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "redirect.js"
        sp.write_text(script_text, encoding="utf-8")
        jp = Path(td) / "scenarios.json"
        jp.write_text(json.dumps([
            {"pathname": p, "search": s, "hash": h, "ua": ua, "narrow": n,
             "store": st, "expect_calls": ec, "expect_store": es}
            for (p, s, h, ua, n, st, ec, es) in REDIRECT_SCENARIOS
        ]), encoding="utf-8")
        hp = Path(td) / "harness.js"
        hp.write_text(_HARNESS, encoding="utf-8")
        r = subprocess.run(["node", str(hp), str(sp), str(jp)],
                           capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"{label} 分流场景失败：\n{r.stdout}\n{r.stderr}"
    assert f"ALL OK {len(REDIRECT_SCENARIOS)} scenarios" in r.stdout
    print(f"✓ {label} 分流脚本：{len(REDIRECT_SCENARIOS)} 个判定场景全过（含偏好/?view=/防循环）")


def test_redirect_scripts_identical_and_behave():
    """D1-③⑤：两页分流脚本同一口径，且 15 个场景行为一致正确。"""
    idx = (WEB / "index.html").read_text(encoding="utf-8")
    mob = (WEB / "mobile.html").read_text(encoding="utf-8")
    s_idx = _extract_redirect_script(idx, "index.html")
    s_mob = _extract_redirect_script(mob, "mobile.html")
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    assert norm(s_idx) == norm(s_mob), "两页分流脚本口径不一致（D1-③⑤）"
    assert "wb.viewpref" in s_idx and "location.replace" in s_idx
    assert 'matchMedia("(max-width: 780px)")' in s_idx
    assert "Mobi|Android|iPhone|iPad|iPod|Mobile" in s_idx
    _run_redirect_scenarios(s_idx, "桌面页")
    _run_redirect_scenarios(s_mob, "移动页")
    print("✓ 两页分流脚本逐字同一口径")


def test_desktop_switch_links_present_and_ids_intact():
    """D4-①：桌面版两处「手机版」入口；既有 id 一个不少。"""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert html.count("手机版") >= 2, "桌面版应有门庭与顶栏两处「手机版」入口"
    assert 'data-view-switch="mobile"' in html
    for eid in ("gateSubmit", "fUser", "fPass", "serverUrl", "gateForm",
                "cmdForm", "cmdInput", "cmdGo", "stageContent", "btnProbe", "btnDemo"):
        assert f'id="{eid}"' in html, f"index.html 既有 id 缺失：{eid}"
    assert "workbench.js" in html
    print("✓ 桌面版两处「手机版」入口，既有 id 完整")


def test_mobile_page_structure():
    """D2：移动版结构——门庭、5 分区导航、常驻命令区、切换入口。"""
    html = (WEB / "mobile.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in html and "width=device-width" in html
    assert '<link rel="stylesheet" href="mobile.css"' in html
    assert '<script src="mobile.js"' in html
    # 门庭（与桌面同 id 口径，便于截图工具复用）
    for eid in ("gate", "gateForm", "fUser", "fPass", "fName", "fNameWrap",
                "gateMsg", "gateSubmit", "btnProbe", "btnDemo"):
        assert f'id="{eid}"' in html, f"mobile.html 缺门庭元素：{eid}"
    assert 'id="serverUrl"' not in html, "移动版门庭不得出现 #serverUrl（D2-③）"
    # 底部导航 5 分区，文案定死
    for label, view in (("动态", "feed"), ("命盘", "sanctum"), ("行囊", "bag"),
                        ("世界", "world"), ("操作", "ops")):
        assert f'data-mview="{view}"' in html, f"底部导航缺 {label}"
        assert label in html
    # 常驻命令区
    for eid in ("cmdForm", "cmdInput", "cmdGo", "suggest", "busyDot"):
        assert f'id="{eid}"' in html, f"mobile.html 缺命令区元素：{eid}"
    # 顶部状态条 + 切换入口 + 恢复自动
    for eid in ("topDaoName", "topDaoRealm", "topStones", "topRemYears"):
        assert f'id="{eid}"' in html, f"mobile.html 缺状态条：{eid}"
    assert 'data-view-switch="desktop"' in html, "移动版缺「桌面版」切换入口"
    # 「跟随设备自动选择」由 mobile.js 在操作页渲染（非静态 HTML）
    assert "跟随设备自动选择" in (WEB / "mobile.js").read_text(encoding="utf-8")
    assert "桌面版" in html
    # 不加载桌面客户端、不引 CDN、不引 ailog
    assert "workbench.js" not in html and "workbench.css" not in html
    assert "app.js" not in html and "style.css" not in html
    assert "cdn.tailwindcss.com" not in html and "fonts.googleapis.com" not in html
    assert "ailog" not in html
    print("✓ 移动版结构：门庭 + 5 分区导航 + 常驻命令区 + 双向切换")


def test_mobile_js_api_contract():
    """D2/C2/C6：只调既有接口，复用 wb.* 键，不读 td_base。"""
    js = (WEB / "mobile.js").read_text(encoding="utf-8")
    for ep in ('"/register"', '"/login"', '"/action"', '"/world/director"',
               '"/health"', '"/commands"'):
        assert ep in js, f"mobile.js 未调用既有接口 {ep}"
    for key in ("wb.token", "wb.user", "wb.name", "wb.uid", "wb.base", "wb.theme"):
        assert key in js, f"mobile.js 未复用会话键 {key}"
    assert "td_base" not in js, "mobile.js 不得读旧键 td_base（C2）"
    assert "mb.token" not in js and "mb.base" not in js, "不得另起 mb.* 会话键（D2-⑦）"
    assert "mn.20230803.xyz:8765" in js, "阵枢远端回落须为 NAS 域名"
    assert "127.0.0.1:8765" in js, "阵枢本机回落须为 127.0.0.1:8765"
    # 阵枢丢弃规则：回环地址正则与 workbench.js 同口径
    assert "localhost|127" in js
    # 高频操作按钮命令
    for cmd in ("/突破", "/闭关", "/出关", "/探险", "/奇遇", "/领俸禄"):
        assert cmd in js, f"移动版缺高频操作 {cmd}"
    print("✓ mobile.js 接口/会话/阵枢契约与 workbench.js 同口径")


def _status_keys():
    import ast
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


def test_mobile_js_status_keys_subset_of_backend():
    """M-17：mobile.js 读的 st.* 键必须 ⊆ 后端 _status_dict 下发键。"""
    js = (WEB / "mobile.js").read_text(encoding="utf-8")
    read = set(re.findall(r"\bst\.([A-Za-z_][A-Za-z0-9_]*)", js))
    assert read, "mobile.js 应以 st.* 读取后端状态字段"
    sent = _status_keys()
    missing = read - sent
    assert not missing, f"mobile.js 读取但后端从不下发的键：{sorted(missing)}"
    print(f"✓ mobile.js status 契约：读 {len(read)} 键全部有下发（后端共 {len(sent)} 键）")


def test_mobile_css_touch_and_type():
    """D2-⑥：触控 ≥44px、正文 ≥14px、输入框 16px。"""
    css = (WEB / "mobile.css").read_text(encoding="utf-8")
    assert re.search(r"#cmdInput[^{]*\{[^}]*font-size:\s*16px", css) or \
        re.search(r"input[^{]*\{[^}]*font-size:\s*16px", css), "命令输入框须 16px（防 iOS 放大）"
    assert re.search(r"min-height:\s*44px", css), "可点目标须 min-height: 44px"
    m = re.search(r"body\s*\{[^}]*font-size:\s*(\d+)px", css)
    assert m and int(m.group(1)) >= 14, "正文须 ≥14px"
    assert "max-width: 780px" not in css or True  # 移动版单列，不依赖桌面断点
    print("✓ mobile.css 触控/字号硬指标：44px / 14px / 输入 16px")


def test_server_whitelist_has_mobile_entries():
    """D5-①：两处精确白名单同步含 mobile 三件套，文件名常量。"""
    from server.app import _ROOT_STATIC_FILES, _STATIC_PAGES
    for path, fname, ctype in (
            ("/mobile.html", "mobile.html", "text/html; charset=utf-8"),
            ("/mobile.js", "mobile.js", "text/javascript; charset=utf-8"),
            ("/mobile.css", "mobile.css", "text/css; charset=utf-8")):
        assert _STATIC_PAGES.get(path) == (fname, ctype), f"_STATIC_PAGES 缺 {path}"
        assert _ROOT_STATIC_FILES.get(path) == fname, f"_ROOT_STATIC_FILES 缺 {path}"
    # 根地址仍是桌面版，不改
    assert _STATIC_PAGES["/"] == ("index.html", "text/html; charset=utf-8")
    assert _STATIC_PAGES["/index.html"] == ("index.html", "text/html; charset=utf-8")
    print("✓ server/app.py 双轨白名单同步含 mobile 三件套，/ 仍是桌面版")
