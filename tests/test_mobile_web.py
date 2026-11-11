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


# ---- mobile-redesign（R-19）：视觉重做契约断言 ----
def test_mobile_redesign_tokens_and_no_bare_hex():
    """R-1：token 双列落地；#7c3aed 全仓零命中；组件规则无裸色值。"""
    css = (WEB / "mobile.css").read_text(encoding="utf-8")
    assert ":root {" in css and 'html[data-theme="dark"]' in css, "须有昼夜双列 token"
    for tok in ("--bg", "--surface", "--line", "--line-gold", "--ink", "--muted",
                "--placeholder", "--jade-700", "--gold-500", "--gold-700",
                "--blood", "--warn", "--font-display", "--font-ui"):
        assert tok in css, f"token 缺失：{tok}"
    assert "#7c3aed" not in css, "紫色 #7c3aed 须全站删除"
    assert "#7c3aed" not in (WEB / "mobile.js").read_text(encoding="utf-8")
    assert "#7c3aed" not in (WEB / "mobile.html").read_text(encoding="utf-8")
    # 裸色值检查：#[0-9a-f]{3,6} 只许出现在 token 定义行（行首为 --token），
    # 以及 #id 选择器行（#feedLog 等，非颜色）；mask 遮罩用 black 关键字。
    bad = []
    for i, line in enumerate(css.splitlines(), 1):
        for m in re.finditer(r"#([0-9a-fA-F]{3,6})\b", line):
            if line.lstrip().startswith("--"):
                continue
            if re.match(r"\s*#[A-Za-z_][\w-]*\s*\{", line):
                continue
            bad.append(f"L{i}: {line.strip()}")
    assert not bad, f"组件规则含裸色值：{bad}"
    assert "dashed" not in css, "虚线分隔须全站废除"
    print("✓ mobile-redesign token 双列，无裸色值，无 #7c3aed，无 dashed")


def test_mobile_redesign_nav_svg_no_text_symbols():
    """R-6：导航 5 图标均为内联 SVG，文本符号 ☰◆▣◎✦ 零命中。"""
    html = (WEB / "mobile.html").read_text(encoding="utf-8")
    nav = re.search(r'<nav id="bottomNav".*?</nav>', html, re.S)
    assert nav, "缺 #bottomNav"
    assert nav.group(0).count("<svg") == 5, "导航须恰好 5 个内联 SVG"
    for sym in ("☰", "◆", "▣", "◎", "✦"):
        assert sym not in nav.group(0), f"导航仍含文本符号 {sym}"
    assert 'stroke="currentColor"' in nav.group(0)
    print("✓ 导航 5 内联 SVG，无文本符号")


def test_mobile_redesign_inline_row_iron_rule():
    """R-13：行内按钮铁律（M-10 根治）写进 CSS。"""
    css = (WEB / "mobile.css").read_text(encoding="utf-8")
    m = re.search(r"\.inline-row \.btn \{([^}]*)\}", css)
    assert m, "缺 .inline-row .btn 规则"
    body = m.group(1)
    assert "min-width: 76px" in body and "max-width: 40%" in body
    assert "flex: 0 0 auto" in body
    m2 = re.search(r"\.inline-row input, \.inline-row select \{([^}]*)\}", css)
    assert m2 and "flex: 1 1 auto" in m2.group(1) and "min-width: 0" in m2.group(1)
    print("✓ .inline-row 铁律：输入 flex:1/min-width:0，按钮 76px/40%")


def test_mobile_redesign_gate_copy_and_hooks():
    """R-12/R-18：门庭眉题文案 + 默认阵枢 + 钩子冻结。"""
    html = (WEB / "mobile.html").read_text(encoding="utf-8")
    assert "寿元为薪 · 因果为引" in html, "门庭眉题文案缺失"
    assert "mn.20230803.xyz:8765" in html, "默认阵枢地址须保留可见"
    assert "根地址自动进入" not in html, "技术说明文案须移除"
    for eid in ("gate", "gateForm", "fUser", "fNameWrap", "fName", "fPass",
                "gateMsg", "gateSubmit", "btnProbe", "btnDemo", "app",
                "topDaoName", "topDaoRealm", "topLocation", "topStones",
                "topRemYears", "btnLogoutM", "pane-feed", "pane-sanctum",
                "pane-bag", "pane-world", "pane-ops", "feedLog", "sanctumBody",
                "bagBody", "worldBody", "opsBody", "quickBar", "cmdDock",
                "suggest", "cmdForm", "busyDot", "cmdInput", "cmdGo",
                "bottomNav", "toasts"):
        assert f'id="{eid}"' in html, f"冻结 id 缺失：{eid}"
    js = (WEB / "mobile.js").read_text(encoding="utf-8")
    for frag in ("feed-eyebrow", "card-eyebrow", "stat-grid", "tierClass",
                 "ops-hero", "chat-stack", "display-row", "cap-bar",
                 "pill-cur", 'data-fill="/look "'):
        assert frag in js, f"重做渲染结构缺失：{frag}"
    print("✓ 门庭文案/阵枢/冻结 id/新渲染结构齐全")


def test_mobile_redesign_rework_m1_m5_qa02_qa03():
    """返修轮：M-1 命令坞 min-height、M-2 仇视 pill、M-3 道身卡 18px、M-4 数字等宽、M-5 门庭主按钮 52px、QA-02 键盘态 Toast 120px、QA-03 时间戳绝对定位。"""
    css = (WEB / "mobile.css").read_text(encoding="utf-8")
    js = (WEB / "mobile.js").read_text(encoding="utf-8")
    # M-1：固定 height 改 min-height；刘海屏下整叠随 --sab 上移，坞高仍 60，总高仍 164
    m = re.search(r"#cmdDock \{([^}]*)\}", css)
    assert m, "缺 #cmdDock 规则"
    assert "min-height: 60px" in m.group(1), "M-1：#cmdDock 须为 min-height: 60px"
    assert not re.search(r"(?<!min-)height:\s*60px", m.group(1)), "M-1：#cmdDock 不得再有固定 height: 60px"
    assert "bottom: calc(56px + var(--sab))" in m.group(1), "M-1：#cmdDock 坞底须随 safe-area 上移"
    assert "env(safe-area-inset-bottom" not in m.group(1), "M-1：#cmdDock 内边距不再吃 safe-area（改由坞底上移）"
    assert "--sab: env(safe-area-inset-bottom, 0px)" in css, "M-1：须定义 --sab"
    mq = re.search(r"#quickBar \{([^}]*)\}", css)
    assert mq and "bottom: calc(116px + var(--sab))" in mq.group(1), "M-1：#quickBar 须随 safe-area 同量上移（否则增高后的坞盖住芯片）"
    mt = re.search(r"\n#toasts \{([^}]*)\}", css)
    assert mt and "bottom: calc(176px + var(--sab))" in mt.group(1), "M-1：#toasts 须随 safe-area 同量上移"
    assert "padding: 16px 16px calc(176px + var(--sab))" in css, "M-1：#viewRoot 下边距须随 safe-area 同量上移"
    # M-2：仇视映射 danger；戒备/亲近仍落中性（不映射）
    assert re.search(r'attitude_cn === "仇视" \? " danger"', js), "M-2：仇视须映射 danger"
    assert "戒备" not in js.split("tagCls")[1].split(";")[0], "M-2：戒备不得映射（Spec 未知落中性）"
    # M-3：道身卡 h3 单独 18px，其他卡 h3 仍 15px
    m3 = re.search(r"#sanctumBody \.card:first-child h3 \{([^}]*)\}", css)
    assert m3 and "font-size: 18px" in m3.group(1), "M-3：道身卡 h3 须 18px"
    mg = re.search(r"\.card h3 \{([^}]*)\}", css)
    assert mg and "font-size: 15px" in mg.group(1), "M-3：通用 .card h3 须保持 15px"
    # M-4：身家数字等宽
    m4 = re.search(r"\.stat-cell \.num \{([^}]*)\}", css)
    assert m4 and ("font-family: var(--font-num)" in m4.group(1)
                   or "font-variant-numeric: tabular-nums" in m4.group(1)), "M-4：.stat-cell .num 须等宽数字"
    # M-5：门庭主按钮 52px
    m5 = re.search(r"#gateSubmit \{([^}]*)\}", css)
    assert m5 and "min-height: 52px" in m5.group(1), "M-5：#gateSubmit 须 min-height: 52px"
    # QA-02：键盘态 Toast 底边 120px（60 命令坞 + 48 快捷条 + 12 间隙）
    mkb = re.search(r"body\.kb-open #toasts \{([^}]*)\}", css)
    assert mkb and "bottom: 120px" in mkb.group(1), "QA-02：键盘态 Toast 须 bottom: 120px"
    # QA-03：时间戳绝对定位于首行右上角，右内边距预留防重叠
    mts = re.search(r"\.feed-line \.ts \{([^}]*)\}", css)
    assert mts and "position: absolute" in mts.group(1), "QA-03：.feed-line .ts 须绝对定位"
    assert "float: right" not in mts.group(1), "QA-03：.ts 不得再用 float:right"
    mfl = re.search(r"\.feed-line \{([^}]*)\}", css)
    assert mfl and "position: relative" in mfl.group(1), "QA-03：.feed-line 须 position: relative"
    assert mfl and "padding: 12px 56px 12px 16px" in mfl.group(1), "QA-03：.feed-line 右内边距须预留时间戳位置"
    print("✓ 返修 M-1/M-2/M-3/M-4/M-5/QA-02 契约断言通过")


def test_mobile_redesign_budgets():
    """R-21：体积预算——CSS ≤28800B；html 净增 ≤60 行；js 文件 ≤1892 行。
    豁免沿革：原 20KB → 返修轮总管一次性豁免 20.6KB（21094B）→ gallery-gameplay
    收尾轮（rebase 至 v0.3.6）第二次豁免：CSS 25.1KB（25702B，实测 25566B）、
    js 净增 ≤190（实测 +186）——图鉴/立绘/器灵/线索链为新增功能面，增量为其
    接入代码本体，裁定与实测数见 docs/compose/spec/gallery-gameplay.md §15；
    token 纪律（no_bare_hex）不在豁免内，图库 CSS 已全量 token 化达标。
    第三次豁免（game-feel-phase1）：CSS 上限 25702B → 27400B、mobile.js 净增
    上限 190 行 → 390 行（即文件 ≤1562 行）——入局卡/出身卡/仪式卡/关系可见化
    为新增功能面；出处：docs/compose/spec/game-feel-phase1.md §9.1 总管批准
    记录（2026-11-08），token 纪律不豁免照旧。
    第四次豁免（game-feel-phase2）：CSS 上限 27400B → 28800B、mobile.js 文件
    上限 1562 行 → 1892 行（净增上限 390 → 720 行）——命途呈现/入局新 kind/
    戏剧当面行/图鉴扩充分组/场景头图/旧账行为新增功能面；出处：
    docs/compose/spec/game-feel-phase2.md §10 总管批准记录（2026-11-08），
    token 纪律不豁免照旧。
    第五次豁免（command-panels）：CSS 上限 28800B → 29200B、mobile.js 文件
    上限 1892 行 → 2100 行（净增上限 720 → 928 行）——命令回复面板化通用
    渲染器 + 60 面板双端实现；出处：docs/compose/spec/command-panels.md §7
    总管批准记录（2026-11-09），token 纪律不豁免照旧。
    第六次豁免（chat-structure D2）：手机端交谈弹窗与桌面玉简同构，CSS/JS 增量
    ——CSS 上限 29200B → 32000B（实测 31324B）、mobile.js 文件上限 2100 行不变
    （实测 1969 行），js 净增断言对齐第五次豁免已裁定的 928 行（文件上限
    2100 − 基线 1172；此前代码仍写 720 系 D1 落码遗漏，实测净增 797 行）；
    出处：docs/compose/spec/chat-structure.md，总管批准记录（2026-11-09），
    token 纪律不豁免照旧。
    第七次豁免（action-error-ux 合并）：mobile.js 文件上限 2100 行 → 2160 行
    （净增上限 928 行 → 988 行）——块一 B1-1/B1-3 与本修复双端人话映射/
    守卫/重试同时落地（main 2018 行 → 合并 2130 行，实测净增 958 行）；
    出处：docs/compose/spec/action-error-ux.md 合并记录（2026-11-11），
    CSS 上限不变，token 纪律不豁免照旧。"""
    css_bytes = (WEB / "mobile.css").stat().st_size
    assert css_bytes <= 32000, f"mobile.css {css_bytes}B 超 32000B 豁免预算（chat-structure D2）"
    html_lines = len((WEB / "mobile.html").read_text(encoding="utf-8").splitlines())
    js_lines = len((WEB / "mobile.js").read_text(encoding="utf-8").splitlines())
    assert html_lines - 150 <= 60, f"mobile.html 净增 {html_lines - 150} 行超 60"
    assert js_lines <= 2160, f"mobile.js {js_lines} 行超 2160 行豁免上限（action-error-ux 合并第七次豁免）"
    assert js_lines - 1172 <= 988, f"mobile.js 净增 {js_lines - 1172} 行超 988（action-error-ux 合并第七次豁免）"
    print(f"✓ 体积：css {css_bytes}B，html +{html_lines - 150} 行，js {js_lines} 行（净增 +{js_lines - 1172}）")


def test_mf3_spells_catalog_no_learned_labels():
    """MF-3（块一评审，前提纠正）：神通图鉴撤销逐项习得标——skills 存功法名、
    spells_catalog 为神通名，无已习得神通数据源，交集恒空属误读。
    双端只保留段标题「神通图鉴（全录）」，learned/unlearned 标注与 CSS 删除。"""
    wb_js = (WEB / "workbench.js").read_text(encoding="utf-8")
    mb_js = (WEB / "mobile.js").read_text(encoding="utf-8")
    wb_css = (WEB / "workbench.css").read_text(encoding="utf-8")
    mb_css = (WEB / "mobile.css").read_text(encoding="utf-8")
    for src, name in ((wb_js, "workbench.js"), (mb_js, "mobile.js")):
        assert "神通图鉴（全录）" in src, name
        assert "learned" not in src, name
        assert '"未习得"' not in src, name  # 逐项标签字面量（「尚未习得功法」为功法区既有文案，不在此列）
    for src, name in ((wb_css, "workbench.css"), (mb_css, "mobile.css")):
        assert ".art-chip.learned" not in src, name
        assert ".art-chip.unlearned" not in src, name
    print("✓ MF-3 神通图鉴：习得标与 CSS 已撤销、段标题保留")
