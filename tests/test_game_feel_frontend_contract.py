"""游戏感第一期（game-feel-phase1）双端前端契约（spec §2.5/§3.11/§4.1/§4.5/§5.4/§9.1）。

纯静态契约：只读 web/ 源码断言结构与字段引用，不依赖后端字段落地——
后端（同 Spec 并行实现）落地 entry/origin/ceremony/status 新键后，
test_mobile_web 的 st.* 子集断言再行复跑对账。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def _read(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_desktop_entry_view_nav_first_and_default():
    """§2.5 桌面：entry 视图列 nav 首位；登录默认落点 entry；briefing 刷新合并。"""
    html = _read("index.html")
    assert html.index('data-view="entry"') < html.index('data-view="sanctum"'), \
        "桌面 nav 首位须为入局（entry）"
    js = _read("workbench.js")
    assert '["entry", "sanctum"' in js, "setView 视图集须含 entry 且列首"
    assert "renderEntry" in js and "state.view === \"entry\"" in js
    assert "/world/briefing" in js and "Bearer " in js, "进入入局视图须以 Bearer 拉 briefing 刷新"
    assert "refreshEntry" in js, "setView(entry) 须触发 entry 刷新合并"
    assert 'state.entry || state.entryPending' in js, "登录默认落点须按 entry 有无决定（缺失回退 sanctum）"
    assert "江湖无事，可自由行动" in js, "空队列须显示 empty 文案（§2.3 B3）"
    assert "data-entry-view" in js, "队列 view 目标须有分发通道"
    assert "entryPending" in js and "入局信息待补" in js, "entry_pending 须有轻提示"
    print("✓ 桌面入局：nav 首位 + 默认落点 + briefing 刷新 + 空队列文案 + 待补提示")


def test_desktop_origin_ceremony_fate_relations():
    """§3.11/§4.5/§5.4 桌面：出身整卡+折叠段、仪式弹窗、命格待选、关系两处。"""
    js = _read("workbench.js")
    for needle in ("origin_card", "originCardHtml", "originFoldHtml", "前世曰：",
                   "data-origin-close", "renderSanctum() + renderSanctumExtras()"):
        assert needle in js, f"workbench.js 缺出身呈现：{needle}"
    for needle in ("maybeShowCeremony", "result_ref", "CEREMONY_STAGE_CN",
                   "data-ceremony-autoskip", "data-ceremony-unskip",
                   "ceremony_skip_", "data-fate-choice", "/命格 ",
                   "fateSectionHtml", "openJadeDialog"):
        assert needle in js, f"workbench.js 缺仪式/命格呈现：{needle}"
    for needle in ("relations_recent", "relations_marks", "relationsSectionHtml",
                   "relationMarkHtml"):
        assert needle in js, f"workbench.js 缺关系可见化：{needle}"
    print("✓ 桌面出身/仪式/命格/关系四件呈现齐全")


def test_mobile_entry_card_before_feedlog():
    """§2.5 移动：feed pane 内 #entryCard 置顶于 #feedLog 之前，renderFeed 前渲染。"""
    html = _read("mobile.html")
    assert html.index('id="entryCard"') < html.index('id="feedLog"'), \
        "移动入局卡容器须在 #feedLog 之前"
    js = _read("mobile.js")
    assert "renderEntryCardM" in js, "mobile.js 缺入局卡渲染"
    feed = js[js.index("function renderFeed()"):]
    assert feed.index("renderEntryCardM();") < feed.index('$("feedLog")'), \
        "renderFeed 须先渲染入局卡再渲染 feedLog"
    assert "江湖无事，可自由行动" in js
    assert "/world/briefing" in js and "Bearer " in js
    print("✓ 移动入局卡：置顶容器 + renderFeed 前渲染 + briefing 合并")


def test_mobile_origin_ceremony_fate_relations():
    """§3.11/§4.5/§5.4 移动：出身全屏卡、仪式全屏卡、命格待选、关系两处、ops 取消入口。"""
    js = _read("mobile.js")
    for needle in ("origin_card", "showOriginOverlayM", "originBodyHtmlM", "前世曰：",
                   "data-origin-close", "st.origin"):
        assert needle in js, f"mobile.js 缺出身呈现：{needle}"
    for needle in ("maybeShowCeremonyM", "ceremonyOverlay", "data-ceremony-close",
                   "data-ceremony-autoskip", "data-ceremony-unskip", "ceremonySkipOps",
                   "ceremony_skip_", "data-fate-choice", "/命格 ",
                   "fateSectionHtmlM", "st.fate"):
        assert needle in js, f"mobile.js 缺仪式/命格呈现：{needle}"
    for needle in ("st.relations_recent", "relations_marks", "relationsSectionHtmlM",
                   "relationMarkM"):
        assert needle in js, f"mobile.js 缺关系可见化：{needle}"
    print("✓ 移动出身/仪式/命格/关系四件呈现齐全")


def test_ceremony_skip_key_shared_both_ends():
    """§4.1：同类自动略过键 ceremony_skip_<kind> 双端同键，只存 localStorage。"""
    for fname in ("workbench.js", "mobile.js"):
        js = _read(fname)
        assert "ceremony_skip_" in js, f"{fname} 缺 ceremony_skip_ 键"
        assert "localStorage" in js
    print("✓ ceremony_skip_<kind> 双端同键")


def test_mobile_budgets_game_feel_phase1():
    """§9.1 总管批准豁免：mobile.css ≤27400B、mobile.js ≤1562 行；新 CSS 类齐全。
    二期修订（game-feel-phase2 spec §10 总管批准豁免，集成收口销账）：上限改为
    mobile.css ≤28800B、mobile.js ≤1892 行；本测试保留一期类齐全断言，预算数值
    以二期 §10 为准（test_mobile_web.py 同口径）。
    第六次豁免（chat-structure D2）：手机端交谈弹窗与桌面玉简同构，CSS/JS 增量
    ——上限统一改为 mobile.css ≤32000B（实测 31324B）、mobile.js ≤2100 行
    （实测 1969 行）；出处：docs/compose/spec/chat-structure.md
    （2026-11-09 总管批准），本测试预算数值以 D2 为准。"""
    css = _read("mobile.css")
    css_bytes = (WEB / "mobile.css").stat().st_size
    assert css_bytes <= 32000, f"mobile.css {css_bytes}B 超 32000B（chat-structure D2）"
    js_lines = len(_read("mobile.js").splitlines())
    assert js_lines <= 2100, f"mobile.js {js_lines} 行超 2100 行（chat-structure D2）"
    for cls in (".gf-overlay", ".gf-card", ".rel-mark", "#entryCard"):
        assert cls in css, f"mobile.css 缺第一期样式：{cls}"
    print(f"✓ 预算实测：css {css_bytes}B / 32000B，js {js_lines} 行 / 2100 行（chat-structure D2）")
