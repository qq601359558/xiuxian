"""游戏感第三期（game-feel-phase3）双端前端契约（spec §7/§8/§9.5 FE-01～03）。

纯静态契约：只读 web/ 源码断言结构与字段引用（沿一期 frontend contract 先例）。
双幕队列的行为真实验收（截图 S-D3/S-M2 等）由 QA 岗在隔离副本做（spec §13），
本文件以源码结构销账 FE-01（新 kind 文案/略过名单/图标）、FE-02（双幕队列
顺序与独立略过、非突破响应零影响）、FE-03（预算硬线 + 现行断言上限双对照）。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

NEW_KINDS = ("tribulation", "loot", "spirit")
ALL_KINDS = ("breakthrough", "death", "rebirth", "tribulation", "loot", "spirit")
KIND_CN = {"tribulation": "天劫", "loot": "得宝", "spirit": "器灵认主"}


def _read(name):
    return (WEB / name).read_text(encoding="utf-8")


def _func_body(js, start_marker, end_marker=None):
    """截取函数定义段（start_marker 起至下一同级函数标记/给定 end 止）。"""
    i = js.index(start_marker)
    j = js.index(end_marker, i) if end_marker else len(js)
    return js[i:j]


def test_fe01_new_kind_labels_skip_lists_icons_both_ends():
    """FE-01：双端 kind 文案表含新三 kind、自动略过名单扩为六 kind、桌面图标两项。"""
    desk = _read("workbench.js")
    mob = _read("mobile.js")
    # 文案表（三处原地扩容之一）：CEREMONY_KIND_CN / CEREMONY_CN_M
    for js, table in ((desk, "CEREMONY_KIND_CN"), (mob, "CEREMONY_CN_M")):
        for kind in ALL_KINDS:
            assert kind in js, f"{table} 缺 kind：{kind}"
        for kind, cn in KIND_CN.items():
            assert re.search(r'%s:\s*"%s"' % (kind, cn), js), \
                f"{table} 缺文案 {kind}: {cn}"
    # 自动略过取消名单（双端各一处）：六 kind 全列
    desk_skip = _func_body(desk, "function ceremonySkipSectionHtml()",
                           "// ---- 件一")
    mob_skip = _func_body(mob, "function renderCeremonySkipOpsM()",
                          "// 件四")
    for body, name in ((desk_skip, "桌面 ceremonySkipSectionHtml"),
                       (mob_skip, "移动 renderCeremonySkipOpsM")):
        for kind in ALL_KINDS:
            assert '"%s"' % kind in body, f"{name} 略过名单缺 {kind}"
        assert "ceremony_skip_" in desk and "ceremony_skip_" in mob
    # 桌面标题图标：loot 💎 / spirit 🔮，tribulation 沿默认 ⚡（三元原地补两项）
    assert 'cer.kind === "loot" ? "💎"' in desk, "桌面缺 loot 图标 💎"
    assert 'cer.kind === "spirit" ? "🔮"' in desk, "桌面缺 spirit 图标 🔮"
    print("✓ FE-01 文案表/略过名单六 kind 双端齐全 + 桌面图标 loot💎/spirit🔮")


def test_fe01_generic_rendering_no_per_kind_branch_and_asset_fallback():
    """FE-01 续：新 kind 走既有通用渲染（beats 循环 + asset_key 图位），无专用渲染分支；
    配图沿 galleryImg 的 onerror 隐藏口径优雅降级；新幕 choices 恒 null 故呈现层
    不为新 kind 新增 choices 按钮逻辑（data-fate-choice 只在既有命格通道出现）。"""
    desk = _read("workbench.js")
    mob = _read("mobile.js")
    for js, fn in ((desk, "function maybeShowCeremony(cer)"),
                   (mob, "function maybeShowCeremonyM(cer)")):
        body = _func_body(js, fn, "function maybeShowCeremonyQueue")
        assert '"/assets/" + b.asset_key + ".webp"' in body, \
            f"{fn} 未按 asset_key 拼 /assets/<key>.webp"
        assert "galleryImg(" in body, f"{fn} 配图未走 galleryImg 降级口径"
        # choices 只走既有通用守卫（Array.isArray + length），null 时不渲染按钮
        assert "Array.isArray(b.choices)" in body, f"{fn} choices 守卫口径变了"
    for js in (desk, mob):
        # 无 per-kind 专用渲染函数
        for bad in ("maybeShowLoot", "maybeShowSpirit", "maybeShowTribulation",
                    "renderLootCeremony", "renderSpiritCeremony",
                    "renderTribulationCeremony"):
            assert bad not in js, f"出现新 kind 专用渲染分支：{bad}"
    # galleryImg 本体带 onerror 隐藏（桌面/移动同口径，加载失败不破版）
    assert "onerror=" in desk and "onerror=" in mob
    print("✓ FE-01 通用渲染：asset_key 图位 + galleryImg 降级 + 无新 kind 专用分支")


def test_fe02_dual_queue_order_and_independent_skip_desktop():
    """FE-02 桌面：ceremony_next 暂存 → 先演 ceremony → 专用关闭顺延下一幕；
    两幕 skip 按 kind 独立判定；通用 closeJadeDialog 未被队列逻辑劫持。"""
    js = _read("workbench.js")
    q = _func_body(js, "function maybeShowCeremonyQueue(cer, next)",
                   "// 仪式专用关闭")
    # 暂存先于呈现；ceremony_next 缺失/null 时暂存清空（单幕零影响）
    assert "state.ceremonyNext = next" in q and "? next : null" in q
    assert q.index("state.ceremonyNext") < q.index("maybeShowCeremony(cer)")
    # 第一幕自动略过判定在队列层（跳过第一幕不吞第二幕）
    assert "ceremonySkipped(cer.kind)" in q
    assert "maybeShowCeremony(nxt)" in q, "第一幕被略过时须顺延判定第二幕"
    # 第二幕自身的 skip 由 maybeShowCeremony 本体判定（双略过都不呈现）
    body = _func_body(js, "function maybeShowCeremony(cer)",
                      "function maybeShowCeremonyQueue")
    assert "ceremonySkipped(cer.kind)" in body
    # 专用关闭函数：关弹窗 → 清暂存 → 顺延呈现；且已导出供「略过」按钮调用
    c = _func_body(js, "function closeCeremonyDialog()",
                   "// ---- 件一")
    assert "closeJadeDialog()" in c and "state.ceremonyNext = null" in c
    assert "maybeShowCeremony(nxt)" in c
    assert "closeCeremonyDialog," in js, "closeCeremonyDialog 未导出到 workbench"
    assert 'onclick="workbench.closeCeremonyDialog()">略过</button>' in js, \
        "ceremony「略过」按钮未走专用关闭函数"
    # 通用关闭函数本体未被改动/劫持（不含队列状态）
    g = _func_body(js, "function closeJadeDialog()",
                   "function spawnFloatBadge")
    assert "ceremonyNext" not in g and "ceremony" not in g.lower().replace(
        "jade", ""), "通用 closeJadeDialog 被仪式队列劫持"
    # 队列函数不碰命格通道（第二幕 choices 沿既有 data-fate-choice//命格 口径）
    assert "/命格" not in q and "data-fate-choice" not in q
    assert "fateChoicesHtml(b.choices)" in body, "第二幕 choices 未沿既有命格按钮渲染"
    print("✓ FE-02 桌面双幕队列：暂存→先演→专用关闭顺延 + skip 独立 + 通用关闭未劫持")


def test_fe02_dual_queue_order_and_independent_skip_mobile():
    """FE-02 移动：与桌面同契约——maybeShowCeremonyQueueM 暂存/顺延、
    data-ceremony-close 走 closeCeremonyM、命格点选行为沿既有现状不变。"""
    js = _read("mobile.js")
    q = _func_body(js, "function maybeShowCeremonyQueueM(cer, next)",
                   "function closeCeremonyM()")
    assert "state.ceremonyNext = next" in q and "? next : null" in q
    assert q.index("state.ceremonyNext") < q.index("maybeShowCeremonyM(cer)")
    assert "ceremonySkippedM(cer.kind)" in q
    assert "maybeShowCeremonyM(nxt)" in q
    body = _func_body(js, "function maybeShowCeremonyM(cer)",
                      "function maybeShowCeremonyQueueM")
    assert "ceremonySkippedM(cer.kind)" in body
    c = _func_body(js, "function closeCeremonyM()",
                   "function renderCeremonySkipOpsM()")
    assert 'closeOverlayM("ceremonyOverlay")' in c
    assert "state.ceremonyNext = null" in c and "maybeShowCeremonyM(nxt)" in c
    # data-ceremony-close 委托走专用关闭；命格点选仍沿既有（关 overlay + 发 /命格）
    assert 'if (t.closest("[data-ceremony-close]")) { closeCeremonyM(); return; }' in js
    assert 'closeOverlayM("ceremonyOverlay"); sendCmd("/命格 "' in js
    assert "/命格" not in q and "data-fate-choice" not in q
    print("✓ FE-02 移动双幕队列：与桌面同顺序/同独立略过口径")


def test_fe02_call_sites_carry_ceremony_next_both_ends():
    """FE-02 接线：双端 /action 与登录/转世 payload 两路均改走队列入口并透传
    ceremony_next；非突破响应（无 ceremony_next）队列暂存恒空、呈现与基线一致。"""
    desk = _read("workbench.js")
    mob = _read("mobile.js")
    for js, fn in ((desk, "maybeShowCeremonyQueue(data.ceremony, data.ceremony_next)"),
                   (mob, "maybeShowCeremonyQueueM(data.ceremony, data.ceremony_next)")):
        assert fn in js, f"缺 /action 队列接线：{fn}"
    assert "maybeShowCeremonyQueue(payload.ceremony, payload.ceremony_next)" in desk
    assert "maybeShowCeremonyQueueM(payload.ceremony, payload.ceremony_next)" in mob
    # 旧的无队列直调不得残留在响应路径上（呈现函数本体定义除外）
    assert "if (data.ceremony) maybeShowCeremony(data.ceremony)" not in desk
    assert "if (payload.ceremony) maybeShowCeremony(payload.ceremony)" not in desk
    assert "if (data.ceremony) maybeShowCeremonyM(data.ceremony)" not in mob
    assert "if (payload.ceremony) maybeShowCeremonyM(payload.ceremony)" not in mob
    # 桌面突破兜底弹窗不得吞掉 ceremony_next 单边在场时的第二幕
    assert "!data.ceremony && !data.ceremony_next" in desk
    print("✓ FE-02 双端两路接线齐全（/action + 登录 payload），旧直调无残留")


def test_fe03_mobile_budgets_hardline_and_caps():
    """FE-03：交付实测对本轮硬线与现行断言上限双对照（spec §8）——
    第五次豁免（command-panels spec §7，2026-11-09 总管批准 D1）：
    mobile.js 硬线 1660 行 → 2100 行、现行上限 1892 行 → 2100 行
    （净增上限 720 → 928）；mobile.css 硬线 27455B → 29200B、现行上限
    28800B → 29200B；token 纪律（no_bare_hex）不在豁免内，复核仍交
    test_mobile_web。超新上限时停工回主策岗，不得擅自再改。
    第六次豁免（chat-structure D2）：手机端交谈弹窗与桌面玉简同构，CSS/JS 增量
    ——mobile.css 上限 29200B → 32000B（实测 31324B）、mobile.js 上限 2100 行
    不变（实测 1969 行）；出处：docs/compose/spec/chat-structure.md
    （2026-11-09 总管批准），token 纪律不豁免照旧。
    第七次豁免（action-error-ux 合并）：mobile.js 上限 2100 行 → 2160 行
    （实测 2130 行）；出处：docs/compose/spec/action-error-ux.md
    合并记录（2026-11-11），token 纪律不豁免照旧。"""
    js_lines = len(_read("mobile.js").splitlines())
    css_bytes = (WEB / "mobile.css").stat().st_size
    assert js_lines <= 2160, f"mobile.js {js_lines} 行超第七次豁免上限 2160 行（action-error-ux 合并）"
    assert css_bytes <= 32000, f"mobile.css {css_bytes}B 超 D2 豁免上限 32000B（chat-structure D2）"
    print(f"✓ FE-03 预算实测：mobile.js {js_lines} 行（第七次豁免上限 2160），"
          f"mobile.css {css_bytes}B（D2 豁免上限 32000）")


def test_gf3_qa01_desktop_treasure_flow_forwards_loot_ceremony():
    """GF3-QA-01 回归（QA 必现用例的仓内版）：桌面 /挖宝 被 sendCmd 拦截进
    handleTreasureAction 宝图专用流，该流自调 /action 消费响应时必须把
    res.ceremony 转交 maybeShowCeremonyQueue（与通用 sendCmd 路径同口径、
    含 ceremony_next 透传），否则得宝幕在桌面真实 UI 路径永不呈现。"""
    desk = _read("workbench.js")
    seg = _func_body(desk, "联机模式：向服务端调用 /挖宝", "若服务端未返回具体装备")
    assert "maybeShowCeremonyQueue(res.ceremony, res.ceremony_next)" in seg, \
        "宝图流 dig 成功段未转交 ceremony（GF3-QA-01 再发）"
    assert "res.ceremony || res.ceremony_next" in seg, \
        "宝图流转交须沿通用路径的双键守卫口径"
    print("✓ GF3-QA-01 桌面宝图流 dig 段已转交 ceremony（队列入口 + ceremony_next 透传）")


def test_gf3_qa01_desktop_blind_box_ceremony_not_clobbered():
    """GF3-QA-01 自查（得宝幕第二挂点 /捡漏）：桌面 /捡漏 无专用拦截流——
    sendCmd 拦截段只有探险/挖宝/穿戴/卸下，/捡漏 走通用 /action 路径并在
    :6709 口径转交 ceremony；坊市 gamble 按钮经 sendCmd 后，其自有解石
    面板不得在达幕时叠开（openJadeDialog 会关掉刚呈现的得宝幕）。"""
    desk = _read("workbench.js")
    send = _func_body(desk, "async function sendCmd(cmd)", "function demoResult(c)")
    assert '"/捡漏"' not in send, "/捡漏 被 sendCmd 专用流拦截（须走通用路径）"
    assert "maybeShowCeremonyQueue(data.ceremony, data.ceremony_next)" in send, \
        "通用 sendCmd 路径未转交 ceremony"
    gamble = _func_body(desk, 'if (act === "gamble")', 'if (act === "solicit")')
    assert 'await sendCmd("/捡漏")' in gamble
    assert "!res.ceremony" in gamble, \
        "gamble 解石面板在得宝幕已呈现时仍叠开，会关掉得宝幕（GF3-QA-01 同型）"
    print("✓ GF3-QA-01 自查：/捡漏 通用路径转交 + gamble 面板达幕不叠开")
