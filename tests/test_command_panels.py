"""命令回复面板化（command-panels spec §5 CP-00 / §6 AC-05·AC-07·AC-08）。

- 渲染断言在 tests/command_panels_fixture.mjs（node）：真实抓取响应 +
  附录 A 合成 payload，双端探针逐案对照；此处以 subprocess 调用并断言
  零失败（node 缺失时跳过该用例，其余静态断言仍跑）。
- 静态断言（本文件，纯 Python）：K2 禁文本解析扫描、预算硬线（D1 豁免
  已批准：mobile.js ≤2100 行、mobile.css ≤29200B，见 spec §7）、
  mobile.css 新增零裸 hex、app.js 零改动。
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "web"
WB = WEB / "workbench.js"
MOB = WEB / "mobile.js"
MOB_CSS = WEB / "mobile.css"
MOB_HTML = WEB / "mobile.html"
APP_JS = WEB / "app.js"


def _panel_block(path):
    text = path.read_text(encoding="utf-8")
    a = text.index("== command-panels: begin ==")
    b = text.index("== command-panels: end ==")
    return text[a:b]


def test_command_panels_fixture_harness():
    """AC-05：node 夹具全绿（真实抓取 + 附录 A 合成 + 双端探针对照）。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用，跳过 JS 渲染夹具（预算与静态断言仍覆盖）")
    r = subprocess.run(
        [node, str(REPO / "tests" / "command_panels_fixture.mjs")],
        capture_output=True, text=True, cwd=str(REPO), timeout=120,
    )
    assert r.returncode == 0, (
        "command_panels_fixture.mjs 失败：\nSTDOUT:\n" + r.stdout[-4000:]
        + "\nSTDERR:\n" + r.stderr[-2000:]
    )
    assert "0 failed" in r.stdout


def test_command_panels_no_text_parsing():
    """AC-05 / §4-K2：面板块内禁解析 data.text、禁 Math.random 捏造源。"""
    for path in (WB, MOB):
        blk = _panel_block(path)
        for pat in ("data.text", ".text.split", ".text.match", "text.indexOf",
                    "text.slice", "text.replace", "Math.random"):
            assert pat not in blk, f"{path.name} 面板块含禁用的 {pat!r}"
        assert "buildCommandPanel" in blk


def test_command_panels_budgets():
    """AC-08：D1 豁免已批准（spec §7，2026-11-09 总管裁决）——
    mobile.js ≤2100 行、mobile.css ≤29200B、mobile.html 净增 ≤60 行。"""
    js_lines = len(MOB.read_text(encoding="utf-8").splitlines())
    css_bytes = MOB_CSS.stat().st_size
    html_lines = len(MOB_HTML.read_text(encoding="utf-8").splitlines())
    assert js_lines <= 2100, f"mobile.js {js_lines} 行超 D1 豁免上限 2100 行"
    assert css_bytes <= 29200, f"mobile.css {css_bytes}B 超 D1 豁免上限 29200B"
    assert html_lines - 150 <= 60, f"mobile.html 净增 {html_lines - 150} 行超 60"
    print(f"✓ 预算实测：mobile.js {js_lines} 行，mobile.css {css_bytes}B，"
          f"mobile.html +{html_lines - 150} 行（D1 豁免上限 2100 行 / 29200B）")


def test_command_panels_mobile_css_no_bare_hex():
    """AC-04：mobile.css 新增面板样式全量 var()、零裸 hex。"""
    text = MOB_CSS.read_text(encoding="utf-8")
    marker = "/* 命令回复面板化（command-panels CP-00）"
    assert marker in text
    added = text[text.index(marker):]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", added), "新增 CSS 含裸 hex"


def test_command_panels_app_js_untouched():
    """§10-7：app.js 本轮零改动（遗留客户端，只审计）。"""
    assert "command-panels" not in APP_JS.read_text(encoding="utf-8")
    assert "buildCommandPanel" not in APP_JS.read_text(encoding="utf-8")


def test_command_panels_builders_present_both_ends():
    """D2 同构：双端 builder 集合一致（移动端多 CP-46/47 两项）。"""
    def builders(path):
        blk = _panel_block(path)
        m = re.search(r"CP_BUILDERS(?:_M)? = \{(.*?)\};", blk, re.S)
        assert m, f"{path.name} 未找到 CP_BUILDERS 表"
        return set(re.findall(r"(\w+): cp\w+", m.group(1)))
    desk = builders(WB)
    mob = builders(MOB)
    assert len(desk) >= 60, f"桌面 builder 仅 {len(desk)} 项"
    assert desk <= mob, f"桌面独有 builder：{sorted(desk - mob)}"
    assert sorted(mob - desk) == ["adventure", "dig"], f"移动独有 builder 应仅为 CP-46/47：{sorted(mob - desk)}"


def test_command_panels_desktop_dark_text_stays_dark():
    """AC-04（深色可读，2026-11-09 截图复核回归）：桌面面板卡沿用 .jade-panel
    浅色半透面（与既有卡片一致，workbench.css 无深色覆盖），故面板标记内
    不得含 dark:text-*——浅色字落浅卡在深色主题下不可读。移动端不适用
    此条：mobile .card 经 var(--surface) 切深色面，文字色由 token 驱动。"""
    blk = _panel_block(WB)
    assert "dark:text-" not in blk, "桌面面板块含 dark:text-*（深色字落浅卡不可读）"
    css = (WEB / "workbench.css").read_text(encoding="utf-8")
    marker = "/* 命令回复面板化（command-panels CP-00）"
    added = css[css.index(marker):]
    assert '[data-theme="dark"] .cp-' not in added, "workbench.css 新增 .cp-* 不得假设深色卡面"
