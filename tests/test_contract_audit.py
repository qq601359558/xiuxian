"""前后端数据口径全量核查契约层（contract-audit，v0.3.12-gray.19）。

三类断言（Spec §5，缺一类即未验）：
1. 双向差集：服务端顶层响应键集合 vs 三端引用键集合（B.2 最终差集表定稿，
   见 test_CT01_bidirectional_diff）；死键须在台账中有行，否则变红。
2. 全仓坏模式扫描：写死中文 stat 键、联机捏造、函数内 import 遮蔽、
   根目录陈旧前端副本。
3. 真实 payload 渲染执行：把面板纯渲染 helper 抽出，用 node 跑真实抓取
   payload 断言无 undefined/NaN、无误导数值。

方法（先红后绿，CT-01）：本文件先在未修复代码上跑出失败留档，再修复、再全绿。
每行 P0/P1 修复有对应用例，用例名含台账 ID（CT-02）。
"""
import ast
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CAPTURES = ROOT / "docs" / "compose" / "contract-audit-captures"

from server.world import WORLD  # noqa: E402

try:
    WORLD.stop_tick()
except Exception:
    pass


# ---------------------------------------------------------------- helpers
def _read_js(name="workbench.js"):
    return (WEB / name).read_text(encoding="utf-8")


def _extract_helper(js, name):
    """抽出 workbench.js 里的纯渲染 helper 源码（沿 treasurePanelStatLine 先例）。

    花括号配对扫描（可处理模板字面量 ${} 与多层嵌套），而非单层正则。
    """
    m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{", js)
    assert m, f"workbench.js 缺纯渲染 helper {name}"
    start = m.start()
    i = m.end() - 1  # 函数体开括号
    depth = 0
    # 帧栈：'brace' 普通花括号 / 'interp' 模板插值 ${ / 'sq' / 'dq' / 'tpl' / 'line' / 'block'
    stack = []
    j = i
    n = len(js)
    while j < n:
        ch = js[j]
        top = stack[-1] if stack else None
        if top in ("sq", "dq", "tpl"):
            if ch == "\\":
                j += 2
                continue
            if top == "sq" and ch == "'":
                stack.pop()
            elif top == "dq" and ch == '"':
                stack.pop()
            elif top == "tpl" and ch == "`":
                stack.pop()
            elif top == "tpl" and ch == "$" and j + 1 < n and js[j + 1] == "{":
                stack.append("interp")
                depth += 1
                j += 2
                continue
            j += 1
            continue
        if top == "line":
            if ch == "\n":
                stack.pop()
            j += 1
            continue
        if top == "block":
            if ch == "*" and j + 1 < n and js[j + 1] == "/":
                stack.pop()
                j += 2
                continue
            j += 1
            continue
        # 代码态
        if ch == "'" or ch == '"':
            stack.append("sq" if ch == "'" else "dq")
        elif ch == "`":
            stack.append("tpl")
        elif ch == "/" and j + 1 < n and js[j + 1] == "/":
            stack.append("line")
            j += 2
            continue
        elif ch == "/" and j + 1 < n and js[j + 1] == "*":
            stack.append("block")
            j += 2
            continue
        elif ch == "{":
            stack.append("brace")
            depth += 1
        elif ch == "}":
            depth -= 1
            if stack and stack[-1] in ("brace", "interp"):
                stack.pop()
            if depth == 0:
                return js[start:j + 1]
        j += 1
    raise AssertionError(f"workbench.js 中 {name} 的函数体花括号未闭合")


def _node_call(helper_name, args_js):
    """用 node 执行抽出的 helper；args_js 为 JS 入参表达式（逗号分隔）。"""
    js = _read_js()
    src = _extract_helper(js, helper_name)
    driver = src + f"\nconsole.log(JSON.stringify({helper_name}({args_js})));\n"
    tmp = Path("/tmp") / f"contract_audit_{helper_name}.js"
    tmp.write_text(driver, encoding="utf-8")
    r = subprocess.run(["node", str(tmp)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"node 执行 {helper_name} 失败：{r.stderr}"
    return json.loads(r.stdout.strip())


def _capture_payload(fname):
    return json.loads((CAPTURES / fname).read_text(encoding="utf-8"))["response"]


def _join():
    """建一个全新测试角色，返回 token（全局 WORLD，user_id 唯一防串扰）。"""
    uid = "ca_" + uuid.uuid4().hex[:10]
    j = WORLD.join("契约审计员", user_id=uid)
    token = j.get("token")
    assert token, f"join 失败：{j}"
    return token, uid


def _char(uid):
    from storage.db import CharacterRepository

    return CharacterRepository.get_by_user_id(uid)


def _grant_map(uid, archetype, tier=2):
    """给角色一张指向当前节点的指定原型宝图（沿 capture harness 的 grant_map）。"""
    from core.items import ItemKind
    from core.treasure_system import TreasureEngine
    from core.world_grid import WorldGridEngine
    from storage.db import CharacterRepository

    c = _char(uid)
    for it in list(c.find_items_by_kind(ItemKind.TREASURE_MAP)):
        c.remove_item_entity(it.uid)
    CharacterRepository.save(c)
    c = _char(uid)
    node = WorldGridEngine.get_node(c.location)
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=tier, preferred_target=node.id, preferred_archetype=archetype)
    c.add_item_entity(tmap)
    CharacterRepository.save(c)
    return tmap


def _grant_stones(uid, amount=100000):
    from storage.db import CharacterRepository

    c = _char(uid)
    c.spirit_stones = amount
    CharacterRepository.save(c)


# ---------------------------------------------------------------- CA-001
def test_CA_001_wudan_wuqi_gen_commands_no_crash():
    """CA-001（P0）：/悟丹 /悟器 /生成丹药 /生成法宝 不再恒崩溃。

    红：handle() 内 `import random` 使 random 成局部变量，:2716 未绑定即抛
    UnboundLocalError，/action 层返回 HTTP 500（抓取 failures 4 条同根因）。
    绿：四命令均返回 ok 且带 recipe（本地回退抽配方，既有设计意图）。
    """
    for cmd in ("/悟丹", "/悟器", "/生成丹药", "/生成法宝"):
        token, _ = _join()
        res = WORLD.handle(token, cmd)
        assert res.get("ok") is True, f"{cmd} 未恢复：{res}"
        assert res.get("recipe"), f"{cmd} 应返回抽到的配方：{res}"
    print("✓ CA-001：四命令均 ok 且带 recipe")


def test_CA_001_no_local_import_shadowing_repo_wide():
    """CA-001（P0）同型扫查：全仓函数内不得有遮蔽模块级名的局部 import。

    判定：函数体内 `import X`（X 亦为模块顶层已导入名）且该函数在该 import
    之前已引用 X，即同型遮蔽。server/world.py:3783/:4066/:4143 三处
    `import random` 皆属此类（handle() 在 :2716 先用 random）。
    """
    import ast as _ast

    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts or ".venv" in path.parts:
            continue
        try:
            tree = _ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        module_names = set()
        for node in tree.body:
            if isinstance(node, _ast.Import):
                module_names.update(a.asname or a.name.split(".")[0] for a in node.names)
            elif isinstance(node, _ast.ImportFrom):
                module_names.update(a.asname or a.name for a in node.names)
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            for child in _ast.walk(node):
                if isinstance(child, (_ast.Import, _ast.ImportFrom)):
                    names = []
                    if isinstance(child, _ast.Import):
                        names = [a.asname or a.name.split(".")[0] for a in child.names]
                    else:
                        names = [a.asname or a.name for a in child.names]
                    for name in names:
                        if name not in module_names:
                            continue
                        uses_before = [
                            u for u in _ast.walk(node)
                            if isinstance(u, _ast.Name) and u.id == name
                            and u.lineno < child.lineno
                        ]
                        if uses_before:
                            offenders.append(
                                f"{path.relative_to(ROOT)}:{node.name}:{child.lineno} "
                                f"局部 import {name} 遮蔽模块级同名（先用后引）")
    assert not offenders, "函数内 import 遮蔽（CA-001 同型）：\n" + "\n".join(offenders)
    print("✓ CA-001：全仓无函数内 import 遮蔽")


# ---------------------------------------------------------------- CA-002
def test_CA_002_brute_force_stone_loss_40():
    """CA-002（P0，§6.1）：brute_force 真实响应含 stone_loss == 40。

    引擎级：dig(choice 2) 返回 stone_loss 40，且灵石实扣 40；
    分发级：/挖宝 2 响应 stone_loss == 40、stone_gain == 0（不再以 +0 冒充无扣款）。
    """
    from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element
    from core.treasure_system import TreasureEngine, TreasureArchetype

    c = Character(
        user_id="u_ca002", name="蛮力审计员",
        realm=Realm(tier=2, current_exp=100),
        lifespan=Lifespan(birth_base=120.0, death_timestamp=9999999999.0),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WATER]),
        location="黑水沼泽",
    )
    c.spirit_stones = 100000
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target="黑水沼泽",
        preferred_archetype=TreasureArchetype.ELEMENT_PUZZLE)
    c.add_item_entity(tmap)
    res = TreasureEngine.dig(c, choice_id="2")
    assert res.get("outcome") == "brute_force", res
    assert res.get("stone_loss") == 40, f"引擎须如实填 stone_loss=40：{res}"
    assert c.spirit_stones == 100000 - 40, "扣款本体：实扣 40（扣款行一字不动）"

    token, uid = _join()
    _grant_stones(uid)
    _grant_map(uid, TreasureArchetype.ELEMENT_PUZZLE)
    before = _char(uid).spirit_stones
    resp = WORLD.handle(token, "/挖宝 2")
    assert resp.get("ok") is True, resp
    assert resp.get("stone_loss") == 40, f"分发须透传 stone_loss=40：{resp}"
    assert resp.get("stone_gain") == 0, "brute_force 无 stone_gain（分发补 0 口径不变）"
    assert _char(uid).spirit_stones == before - 40
    print("✓ CA-002：brute_force stone_loss == 40（引擎 + 分发）")


def test_CA_002_other_outcomes_stone_loss_zero():
    """CA-002（P0）：其余 outcome 的 stone_loss 皆为 0（引擎如实填 0）。"""
    from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element
    from core.treasure_system import TreasureEngine, TreasureArchetype

    def _char_at(loc, dao_heart=50):
        c = Character(
            user_id="u_ca002b", name="审计员",
            realm=Realm(tier=2, current_exp=100),
            lifespan=Lifespan(birth_base=120.0, death_timestamp=9999999999.0),
            spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WATER]),
            location=loc,
        )
        c.spirit_stones = 100000
        c.karma.dao_heart = dao_heart
        return c

    cases = []
    c = _char_at("黑水沼泽")
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target="黑水沼泽",
        preferred_archetype=TreasureArchetype.ELEMENT_PUZZLE)
    c.add_item_entity(tmap)
    cases.append(("need_choice", TreasureEngine.dig(c)))
    c = _char_at("黑水沼泽")
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target="黑水沼泽",
        preferred_archetype=TreasureArchetype.ELEMENT_PUZZLE)
    c.add_item_entity(tmap)
    cases.append(("perfect_solve", TreasureEngine.dig(c, choice_id="1")))
    c = _char_at("黑水沼泽")
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target="黑水沼泽",
        preferred_archetype=TreasureArchetype.COMBAT)
    c.add_item_entity(tmap)
    cases.append(("combat_victory", TreasureEngine.dig(c)))
    c = _char_at("黑水沼泽", dao_heart=5)
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target="黑水沼泽",
        preferred_archetype=TreasureArchetype.COMBAT)
    c.add_item_entity(tmap)
    cases.append(("combat_defeat", TreasureEngine.dig(c)))
    c = _char_at("落霞山灵泉")
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=3, preferred_target="落霞山灵泉",
        preferred_archetype=TreasureArchetype.RUIN_HAZARD)
    c.add_item_entity(tmap)
    cases.append(("scar_created", TreasureEngine.dig(c)))
    c = _char_at("青云坊市客栈")
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target="黑水沼泽",
        preferred_archetype=TreasureArchetype.ELEMENT_PUZZLE)
    c.add_item_entity(tmap)
    cases.append(("wrong_location", TreasureEngine.dig(c)))
    for outcome, res in cases:
        assert res.get("outcome") in (outcome, None) or outcome == "wrong_location", (
            f"{outcome} 分支未命中：{res}")
        assert res.get("stone_loss") == 0, f"{outcome} 的 stone_loss 须为 0：{res}"
    print("✓ CA-002：其余 outcome stone_loss 皆为 0")


def test_CA_002_dispatch_passthrough_not_hardcoded():
    """CA-002（P0）：分发层只透传引擎值，不得硬编码 40；扣款行一字不动。"""
    world = (ROOT / "server" / "world.py").read_text(encoding="utf-8")
    m = re.search(r'if action in \("/dig", "/挖宝"\):.*?return \{(.*?)\n                \}',
                  world, re.DOTALL)
    assert m, "未找到 /挖宝 分发 return"
    ret = m.group(1)
    assert '"stone_loss": res.get("stone_loss", 0)' in ret, "分发须只增透传 stone_loss"
    assert "40" not in ret, "分发层不得硬编码 40（只透传引擎值）"
    ts = (ROOT / "core" / "treasure_system.py").read_text(encoding="utf-8")
    assert "loss_stones = 40" in ts, "引擎 brute_force 扣款常量须在场"
    assert "c.spirit_stones = max(0, c.spirit_stones - loss_stones)" in ts, (
        "扣款行一字不动（FX-01）")
    print("✓ CA-002：分发只透传、扣款行未动")


def test_CA_002_frontend_stone_loss_row():
    """CA-002（P0）：宝图面板改读 stone_loss；>0 显「灵石 −40」，=0 整行省略。

    真实 payload 渲染执行：抓取 102（brute_force）/ 101（巧破）/ 零值三态。
    """
    js = _read_js()
    assert "res.stone_loss" in js or "stoneLoss" in js, "面板须读 stone_loss"
    assert "treasureStoneLinesHtml" in js, "面板石数行须走纯 helper treasureStoneLinesHtml"
    p102 = _capture_payload("102-dig-brute-force.json")
    p101 = _capture_payload("101-dig-element-clever.json")
    # 旧抓取 102 是红测试输入（无 stone_loss 键、stone_gain 0）；修复后真实值
    # 以 live 分发响应为准（test_CA_002_brute_force_stone_loss_40 已证 =40）。
    assert p102["stone_gain"] == 0, "抓取 102：brute_force stone_gain 为 0"
    assert p101["stone_gain"] == 360, "抓取 101 是对照输入"
    from core.treasure_system import TreasureArchetype

    token, uid = _join()
    _grant_stones(uid)
    _grant_map(uid, TreasureArchetype.ELEMENT_PUZZLE)
    live_loss = WORLD.handle(token, "/挖宝 2")
    assert live_loss.get("stone_loss") == 40, f"live 响应须含 stone_loss=40：{live_loss}"
    html_loss = _node_call(
        "treasureStoneLinesHtml",
        f"{live_loss.get('stone_gain', 0)}, {live_loss.get('stone_loss', 0)}")
    assert "−40" in html_loss, f"brute_force 面板须显「灵石 −40」：{html_loss}"
    assert "+0" not in html_loss, f"brute_force 面板不得再显「+0」：{html_loss}"
    html_gain = _node_call(
        "treasureStoneLinesHtml",
        f"{p101.get('stone_gain', 0)}, {p101.get('stone_loss', 0)}")
    assert "+360" in html_gain, f"巧破面板须显「+360」：{html_gain}"
    assert "−" not in html_gain, f"巧破面板不得有扣款行：{html_gain}"
    assert _node_call("treasureStoneLinesHtml", "0, 0") == "", "双零时石数行整行省略"
    print("✓ CA-002：面板石数行三态渲染正确")


# ---------------------------------------------------------------- CA-003
def test_CA_003_ceremony_defers_to_settlement():
    """CA-003（P0，§6.2）：得宝幕顶掉宝图 dialog 后，关闭得宝幕结算面板可达。

    修面限于面板/仪式叠演顺序：得宝幕仍按 GF3-QA-01 立即转交呈现（既有断言
    不动）；结算 HTML 写进已 detached 的 boxEl 后暂存一份
    state.pendingTreasureDialog，关闭得宝幕（略过 / ✕ / 背景）后恢复重开，
    含遗物行。自动略过时不弹幕、结算仍在原 dialog 中可见，不暂存。
    """
    js = _read_js()
    dig = js[js.index("const digChoiceArg"):]
    # 1) GF3-QA-01 立即转交原样保留（既有断言 test_gf3_qa01_... 不动）
    assert "maybeShowCeremonyQueue(res.ceremony, res.ceremony_next)" in dig, (
        "宝图流须保留立即转交 ceremony（GF3-QA-01）")
    assert "res.ceremony || res.ceremony_next" in dig, "转交须沿双键守卫口径"
    # 2) 弹幕与否先算出（ceremonyWillShow），供结算暂存决策
    assert "digCeremonyShown = !!ceremonyWillShow(res.ceremony, res.ceremony_next" in dig, (
        "须先算出本次是否真会弹幕")
    # 3) 结算渲染之后才暂存（结算 HTML 先写进 boxEl，再暂存）
    i_helper = dig.index("treasureStoneLinesHtml(stoneGain, stoneLoss)")
    i_settle = dig.rindex("boxEl.innerHTML = `", 0, i_helper)
    i_stash = dig.index("state.pendingTreasureDialog = {")
    assert i_settle < i_stash, "结算 HTML 落袋后才暂存"
    assert "if (digCeremonyShown && boxEl)" in dig, "仅真弹幕时暂存（自动略过不暂存）"
    assert "equipName" in dig, "暂存须含装备名以重绑佩戴"
    # 4) 关闭路径恢复
    assert "function restorePendingTreasureDialog()" in js, "须有恢复 helper"
    assert "restorePendingTreasureDialog()" in js, "关闭路径须调恢复 helper"
    cc = js[js.index("function closeCeremonyDialog()"):]
    cc = cc[:cc.index("\n  }\n")]
    assert "restorePendingTreasureDialog" in cc, "closeCeremonyDialog 须恢复结算"
    # 5) 弹幕可否判定为纯 helper（node 执行）
    assert _node_call("ceremonyWillShow",
                      '{"kind": "loot", "beats": []}, null, []') == "ceremony"
    assert _node_call("ceremonyWillShow",
                      '{"kind": "loot"}, null, ["loot"]') == ""
    assert _node_call("ceremonyWillShow",
                      'null, {"kind": "loot"}, []') == "next"
    print("✓ CA-003：立即弹幕 + 结算暂存，关幕恢复结算")


# ---------------------------------------------------------------- CA-004
def test_CA_004_sanctum_no_static_fabrication():
    """CA-004（P0）：renderSanctum 静态捏造清零，改读服务端真实数据。"""
    js = _read_js()
    san = js[js.index("function renderSanctum()"):]
    san = san[:san.index("function renderInventory()")]
    for fabricated in ("4,850步", "太上长老", "九天碧玉太虚剑", "太虚玄青雀", "9,880"):
        assert fabricated not in san, f"洞府仍含静态捏造「{fabricated}」"
    # 注：「太上长老」另在 demo 种子 state.here（:7597）作 NPC 职衔属性值，
    # 非洞府 live 视图捏造，不在本项清除范围。
    assert "s.rank" in san, "宗门行须读真实 status.rank"
    assert "s.equipped" in san, "法宝卡须读真实 status.equipped"
    assert "spirit" in san, "法宝卡须读真实 equipped[].spirit（有灵才显）"
    assert "treasurePanelStatLine" in san, "法宝主属性须走既有真实口径 helper"
    print("✓ CA-004：洞府静态捏造清零，改读真实 rank/equipped/spirit")


# ---------------------------------------------------------------- CA-005
def test_CA_005_rem_years_unified():
    """CA-005（P2，口径裁决）：寿元全仓定死 toFixed(1) + 「载」，缺失显「—」。"""
    js = _read_js()
    san = js[js.index("function renderSanctum()"):]
    san = san[:san.index("function renderInventory()")]
    assert "rem_years || 100" not in san, "罗盘不得再用 100 假缺省"
    assert "rem_years || 145" not in san, "命盘格不得再用 145 假缺省"
    assert "toFixed(0)" not in san, "寿元不得再用 toFixed(0)"
    assert "fmtRemYears(s.rem_years)" in san, "两处寿元须走统一 helper"
    assert _node_call("fmtRemYears", "80.03") == "80.0"
    assert _node_call("fmtRemYears", "null") == "—"
    assert _node_call("fmtRemYears", "0") == "0.0"
    print("✓ CA-005：寿元口径统一 toFixed(1)，缺失显「—」")


# ---------------------------------------------------------------- CA-011
def test_CA_011_custom_arts_status_echo():
    """CA-011（P3，总管已批）：_status_dict 只增 custom_arts 只读回显。

    数据源为角色行上已存储的自创功法（c.custom_arts，不新增计算/存储语义）；
    既有键的值与形状不动。
    """
    from core.models import Character, Realm, Lifespan, SpiritualRoot, RootType, Element

    art = {"name": "测试玄功", "rank": "EARTH", "nature": "ORTHODOX",
           "cultivation_modifiers": {"exp_gain_multiplier": 1.2}}
    c = Character(
        user_id="u_ca011", name="功法审计员",
        realm=Realm(tier=2, current_exp=100),
        lifespan=Lifespan(birth_base=120.0, death_timestamp=9999999999.0),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WATER]),
        location="青云坊市客栈",
    )
    c.custom_arts = [art]
    token, uid = _join()
    from storage.db import CharacterRepository

    ch = _char(uid)
    ch.custom_arts = [art]
    CharacterRepository.save(ch)
    st = WORLD._status_dict(_char(uid))
    assert st.get("custom_arts") == [art], f"custom_arts 须原样回显已存储数据：{st.get('custom_arts')}"
    st2 = WORLD._status_dict(c)
    assert st2.get("custom_arts") == [art]
    c.custom_arts = []
    assert WORLD._status_dict(c).get("custom_arts") == [], "无自创功法时回显 []"
    js = _read_js()
    assert "s.custom_arts" in js, "洞府功法行读 s.custom_arts（既有消费点，现可得值）"
    print("✓ CA-011：custom_arts 只读回显已存储自创功法")


# ---------------------------------------------------------------- CA-013
def test_CA_013_dungeon_debuff_generic_chips():
    """CA-013（P2）：地牢负面状态未知 effect 通用渲染，不得只判空。"""
    js = _read_js()
    assert "dungeonDebuffChipsHtml" in js, "地牢负面行须走通用 helper"
    assert "m.status_effects?.burn" not in js, "不得再只写 burn/freeze/chill/stun 四枚硬编码 chip"
    html = _node_call("dungeonDebuffChipsHtml",
                      '{"poison": 2, "weaken": 1, "bleed": 3}')
    for label in ("阴冥尸毒", "元气虚浮", "血气溃散"):
        assert label in html, f"poison/weaken/bleed 须有 chip：{html}"
    assert "2回合" in html and "3回合" in html, "须带回合数"
    assert "无异常" in _node_call("dungeonDebuffChipsHtml", "{}"), "空 effect 显「无异常」"
    assert "未知异状" not in html and "undefined" not in html, "未知键不得产出 undefined"
    html_unknown = _node_call("dungeonDebuffChipsHtml", '{"reflect": 2}')
    assert "reflect" in html_unknown, "服务端新 effect 键须原样呈现键名（兜底）"
    print("✓ CA-013：地牢负面状态通用渲染")


# ------------------------------------------------- CA-014 ~ CA-021 / CA-037
def test_CA_014_unequip_returns_status():
    """CA-014（P2）：/卸下 后透传 status，HUD 不再陈旧。"""
    from core.items import ItemFactory

    token, uid = _join()
    c = _char(uid)
    w = ItemFactory.create_equip(name="审计试剑", tier=3, slot="weapon", base_power=60.0)
    c.add_item_entity(w)
    from storage.db import CharacterRepository

    CharacterRepository.save(c)
    assert WORLD.handle(token, "/穿戴 审计试剑").get("ok") is True
    resp = WORLD.handle(token, "/卸下 审计试剑")
    assert resp.get("ok") is True, resp
    assert isinstance(resp.get("status"), dict), f"/卸下 须透传 status：{resp}"
    print("✓ CA-014：/卸下 透传 status")


def test_CA_015_auction_list_returns_status():
    """CA-015（P2）：/上拍 后透传 status。"""
    from core.items import ItemFactory

    token, uid = _join()
    c = _char(uid)
    w = ItemFactory.create_equip(name="审计试剑", tier=3, slot="weapon", base_power=60.0)
    c.add_item_entity(w)
    from storage.db import CharacterRepository

    CharacterRepository.save(c)
    resp = WORLD.handle(token, "/上拍 审计试剑 100")
    assert "status" in resp, f"/上拍 须透传 status：{resp}"
    print("✓ CA-015：/上拍 透传 status")


def test_CA_016_adventure_board_returns_status():
    """CA-016（P2）：/探险 无参榜单路亦透传 status（成功路本已透传）。

    注：台账行文称「/探险不透传」仅对无参榜单路成立；成功路 payload
    本已含 status 与 adventure（见 test_CA_007_adventure_success_path）。
    """
    token, _ = _join()
    resp = WORLD.handle(token, "/探险")
    assert resp.get("ok") is True, resp
    assert isinstance(resp.get("status"), dict), f"/探险榜单路须透传 status：{resp}"
    print("✓ CA-016：/探险榜单路透传 status")


def test_CA_017_create_art_returns_status():
    """CA-017（P2）：/自创功法 成功后透传 status（洞府功法行同步）。"""
    token, _ = _join()
    resp = WORLD.handle(token, "/自创功法 测试玄功")
    assert resp.get("ok") is True, f"本地降级应可自创功法：{resp}"
    assert isinstance(resp.get("status"), dict), f"/自创功法 须透传 status：{resp}"
    assert resp["status"].get("custom_arts"), "status 须含新创功法（CA-011 联动）"
    print("✓ CA-017：/自创功法 透传 status")


def test_CA_018_herbs_returns_status():
    """CA-018（P2·定性核验）：/采药 本已透传 status（抓取 157 证实），无代码改动。"""
    token, _ = _join()
    resp = WORLD.handle(token, "/采药")
    assert resp.get("ok") is True, resp
    assert isinstance(resp.get("status"), dict), resp
    print("✓ CA-018：/采药 透传 status（既有行为，锁定）")


def test_CA_019_spring_returns_status():
    """CA-019（P2·定性核验）：/汲取 本已透传 status（抓取 159 证实），无代码改动。"""
    token, _ = _join()
    resp = WORLD.handle(token, "/汲取")
    assert resp.get("ok") is True, resp
    assert isinstance(resp.get("status"), dict), resp
    print("✓ CA-019：/汲取 透传 status（既有行为，锁定）")


def test_CA_020_crane_returns_status():
    """CA-020（P2·定性核验）：/探路 本已透传 status（抓取 160 证实），无代码改动。"""
    token, uid = _join()
    _grant_stones(uid)
    resp = WORLD.handle(token, "/探路")
    assert resp.get("ok") is True, resp
    assert isinstance(resp.get("status"), dict), resp
    print("✓ CA-020：/探路 透传 status（既有行为，锁定）")


def test_CA_021_sell_returns_status():
    """CA-021（P2）：/出售 后透传 status。"""
    from core.items import ItemEntity, ItemKind

    token, uid = _join()
    c = _char(uid)
    pill = ItemEntity.create(name="审计试丹", kind=ItemKind.PILL, quality=2,
                             description="契约审计试丹。")
    c.add_item_entity(pill)
    from storage.db import CharacterRepository

    CharacterRepository.save(c)
    resp = WORLD.handle(token, "/出售 审计试丹")
    assert resp.get("ok") is True, resp
    assert isinstance(resp.get("status"), dict), f"/出售 须透传 status：{resp}"
    print("✓ CA-021：/出售 透传 status")


def test_CA_037_mobile_status_consumption():
    """CA-037（P2·移动端）：移动端 sendCmdM 本已读 data.status；服务端透传后自动同步。

    移动端零代码改动（硬线内）：本用例只锁「移动端消费点在场」，修复由服务端侧完成。
    """
    js = _read_js("mobile.js")
    assert "data.status" in js, "sendCmdM 须读 data.status"
    assert "applyStatus" in js, "移动端须有 applyStatus 消费 status"
    print("✓ CA-037：移动端 status 消费点在场，服务端透传即同步")


# ---------------------------------------------------------------- CA-023
def test_CA_023_omen_catalog_alignment():
    """CA-023（P1，总管裁决）：改目录，不改分发。

    /omen 别名从 /奇遇 条目移到 /天象 条目；分发 :1959 一字不动；
    :2058 元组中已不可达的 /omen 删除（死代码清理，行为不变）。
    """
    from core.command_catalog import all_entries

    entries = all_entries()
    # 注：目录中无独立 /天象 条目，/天象 只在 /望气 条目的 aliases 中（:51）；
    # 故 /omen 挂在载有 /天象 的同一条目（/望气）下，与 /天象 并列为别名。
    # 另立 /天象 条目会使主命令数 108→109，触 existing 断言 count==108，故不取。
    tianxiang = next(e for e in entries if "/天象" in e["aliases"])
    qiyu = next(e for e in entries if e["cmd"] == "/奇遇")
    assert "/omen" in tianxiang["aliases"], "/天象所在条目的 aliases 须含 /omen"
    assert "/omen" not in qiyu["aliases"], "/奇遇 aliases 不得再含 /omen"
    world = (ROOT / "server" / "world.py").read_text(encoding="utf-8")
    m1959 = re.search(r'if action in \("/omen", "/天象"\):', world)
    assert m1959, "分发 :1959（/omen、/天象 → 纪元天象）一字不动"
    m2058 = re.search(r'if action in \([^)]*"/奇遇"[^)]*\):', world)
    assert m2058 and "/omen" not in m2058.group(0), ":2058 元组中的 /omen 须删除"
    token, _ = _join()
    resp = WORLD.handle(token, "/omen")
    assert resp.get("ok") is True, resp
    assert "season_theme" in resp, "/omen 仍走天象（行为不变）"
    print("✓ CA-023：目录 /omen 归天象，分发不动，行为不变")


# ---------------------------------------------------------------- CT-01
# B.2 最终差集表（按顶层口径重算，定稿）：
# 服务端顶层响应键 = 抓取 top_keys（261 文件，剔除 253-status-snapshot 这一
# 份裸 _status_dict 快照的 77 个内键）∪ /world/director 快照顶层键
# ∪ 静态清册补集（未抓子路径的返回键）∪ 本轮新增 stone_loss
# ∪ 命令面板化新增 35 键（附录 A 全新顶层名，实算皆不在抓取 top_keys 与
# 三端引用键中）∪ chat-structure 新增 chat_lines（抓取早于本功能，静态补集）；
# 共 174 个。
# 三端引用键 = workbench(res/j/data/payload) ∪ app.js(j/data) ∪
# mobile(data/j/payload) 的顶层属性读（排除方法调用、赋值写入与 fetch 的 statusText）；
# 修复后共 137 个（2026-11-09 command-panels 合并后 135 个：前端新读 19 个已下发键
# + 附录 A 36 个待补键中 35 个后端已落地、仅 legacy_info 仍未下发；
# 2026-11-09 chat-structure：移动端交谈弹窗新读 avatar + 双端新读 chat_lines，
# 三端引用 135 → 137）。
# 未读 45 个（备查，不强制修）；死键 8 个（旧 7 个 + legacy_info，须在台账中有行，见注）。
SERVER_TOP_KEYS_EXTRA = {
    # /world/director 快照顶层键（director_snapshot + app.py 补 evolution/summary_lines）
    "server_time", "director", "modifiers", "arcs", "faction", "echo", "era",
    "quality", "arc_board_text", "summary_lines",
    # 静态清册补集：未抓子路径的返回键（清册 §2/§4，逐键核对过代码）
    "tribulation", "pending_heart_demon", "heart_demon_options", "heart_demon",
    "target_died", "action", "board", "chased", "crafted", "drama",
    "drama_pending", "haggle", "is_player", "item_name", "listing_id",
    "messages", "new_location", "offer_price", "omen_ended", "omen_status",
    "original_price", "output", "recipe", "rejected", "scene_image", "trade",
    "protect",
    # 本轮新增（CA-002）：/挖宝 响应 +stone_loss
    "stone_loss",
    # /探险 成功路 payload 含 adventure（清册静态 union 漏列，代码 :2615 实证；
    # 亦见 CA-007 勘误——台账 CA-007 行称「从不下发」仅对无参榜单路成立）
    "adventure",
    # 命令面板化新增（command-panels，附录 A 全新顶层名 35 个；实算皆不在
    # 抓取 top_keys 与基线三端引用键中；合并后前端已渲染读取，故不进未读集）：
    # /榜 boards/board_rows · /秘境 realms · /寻宝 clue · /器灵 spirit
    # /拍卖行 auction · /除凶 hunt · /宗门 sects · /宝图 treasure_map
    # /who who · /告示 bounties · /关系 links · /势力 factions
    # /宗门令 sect_orders · /宗门势 sect_power · /贡献·/兑换 contribution
    # /npc货单 npc_goods · /频道 channel · /传说 legends · /纪元回流 era_flow
    # /师门任务 sect_quests · /名物 relics · /灵宠 pets · /行情 prices
    # /版图 atlas · /墓碑 tombstone · /因果链 karma_chains · /委托 quests
    # /诺言 promises · /配方 recipes · /炼体·/炼神 body_soul_detail
    # /镇魔 demon · /飞升榜 ascend · /议政 council · /结义任务 sworn_quests
    "boards", "board_rows", "realms", "clue", "spirit", "auction", "hunt",
    "sects", "treasure_map", "who", "bounties", "links", "factions",
    "sect_orders", "sect_power", "contribution", "npc_goods", "channel",
    "legends", "era_flow", "sect_quests", "relics", "pets", "prices",
    "atlas", "tombstone", "karma_chains", "quests", "promises", "recipes",
    "body_soul_detail", "demon", "ascend", "council", "sworn_quests",
    # chat-structure 新增（2026-11-09）：交谈响应 chat_lines（server/world.py
    # 交谈分支多点下发；抓取文件早于本功能，未含此键，故入静态补集，
    # 与 CA-002 stone_loss 同例）
    "chat_lines",
}
# 死键 8 个：前端读、服务端从不下发顶层键（旧 7 个皆有台账行或兜底说明，备查不修；
# + legacy_info：2026-11-09 command-panels 合并后定稿。附录 A 36 个前端待补键中
# 35 个已随后端落地移出死键集；仅 legacy_info 仍为死键——服务端 /道统 只平铺
# points/lives/earned/boosts/past_lives 等键，从不下发 legacy_info 顶层键，而
# 前端 cpLegacy 读 data.legacy_info 时以 data 本身为回落，故渲染不受影响。）
KNOWN_DEAD_TOP_KEYS = {
    # app.js /world/director 兜底读：evoSrc/server_time 覆盖，无可见异常（CA-044）
    "blood", "realms_open", "updated_at",
    "detail",       # CA-049：app.js j.detail 兜底链，P4 定性不修
    "entry_pending",  # CA-009/CA-036：P3，维持台账处置
    "message",      # CA-034/CA-049：j.message 兜底链，P4 定性不修
    "new_realm",    # CA-008：P3，维持台账处置
    "legacy_info",  # command-panels：前端 cpLegacy 读 data.legacy_info（回落 data），服务端从不下发
}
# 未读 45 个（服务端下发、三端皆不读顶层键；备查，不强制修）
# 2026-11-09 command-panels 合并后定稿：后端新增 35 键皆已被前端渲染读取，
# 故不进未读集；未读集与前端分支的 46 键版一致。
# 2026-11-09 chat-structure 定稿：avatar 由移动端交谈弹窗消费
# （web/mobile.js openChatM/renderChatHeadM 读 data.avatar），由未读转已读，
# 未读 46 → 45。
FINAL_UNREAD_TOP_KEYS = {
    "action", "actions", "ai_ok", "alive", "arc_board_text", "attitude",
    "bagua", "board", "boosts", "bystanders", "character_id",
    "chased", "crafted", "direction_text", "earned", "event_id", "first_night",
    "intent", "is_new_life", "karma_shadow", "lives", "lock_fallback", "lost_stones",
    "max_boosts", "modifiers", "new_location", "omen_status", "outcome", "output",
    "past_lives", "points", "qi", "quality", "rejected", "related",
    "scene_image", "season_theme", "session_issued", "settled", "settlement_pending", "source",
    "target_node_id", "target_node_name", "traces", "wrong_location",
}


def _server_top_keys():
    keys = set()
    for path in CAPTURES.glob("*.json"):
        if path.name == "index.json" or path.name.startswith("253-"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        keys.update(data.get("top_keys") or [])
    keys |= SERVER_TOP_KEYS_EXTRA
    return keys


def _frontend_top_keys():
    aliases = {
        "workbench.js": ["res", "j", "data", "payload"],
        "app.js": ["j", "data"],
        "mobile.js": ["data", "j", "payload"],
    }
    keys = set()
    for name, als in aliases.items():
        text = _read_js(name)
        for a in als:
            for m in re.finditer(r"\b" + a + r"\.([A-Za-z_][A-Za-z0-9_]*)", text):
                rest = text[m.end():].lstrip()
                if rest.startswith("("):
                    continue
                if rest.startswith("=") and not rest.startswith("=="):
                    continue  # 赋值写入非响应键读（如 mobile chatSendM 的请求体 payload.to）
                keys.add(m.group(1))
    keys.discard("statusText")  # fetch Response 属性，非游戏响应键
    return keys


def test_CT01_bidirectional_diff():
    """CT-01（B.2 定稿）：双向差集断言。

    服务端顶层键 174 个 vs 三端引用键 137 个；未读差集须恰为 FINAL_UNREAD_TOP_KEYS
    （45 个），死键差集须恰为 KNOWN_DEAD_TOP_KEYS（8 个）。任一差集漂移即变红，
    须同步更新台账 B.2 与本文件的定稿表。
    2026-11-09 command-panels 合并后定稿：服务端 138→173（后端新增附录 A 35 键）；
    三端读 80→135（前端新读 19 个已下发键 + 36 个附录 A 待补键，board 因 cpRank
    去复用仍留未读）；未读 65→46；死键 7→8（36 个待补键中 35 个随后端落地移出，
    仅 legacy_info 仍为死键——/道统 平铺键，前端以 data 回落渲染）。
    2026-11-09 chat-structure 定稿：移动端交谈弹窗消费 avatar（openChatM/
    renderChatHeadM 读 data.avatar）→ 未读 46→45；服务端新增 chat_lines
    （抓取早于本功能，入 SERVER_TOP_KEYS_EXTRA 静态补集）→ 服务端 173→174；
    双端新读 chat_lines + avatar → 三端读 135→137；mobile chatSendM 的请求体
    赋值 payload.to 系写入非响应键读，采集口径排除赋值目标，不入差集；死键仍 8。
    """
    srv = _server_top_keys()
    fe = _frontend_top_keys()
    assert len(srv) == 174, f"服务端顶层键须为 174 个，实得 {len(srv)}：{sorted(srv)}"
    unread = srv - fe
    dead = fe - srv
    assert unread == FINAL_UNREAD_TOP_KEYS, (
        f"未读差集漂移（{len(unread)} vs 定稿 45）："
        f"新增 {sorted(unread - FINAL_UNREAD_TOP_KEYS)}；"
        f"消失 {sorted(FINAL_UNREAD_TOP_KEYS - unread)}")
    assert dead == KNOWN_DEAD_TOP_KEYS, (
        f"死键差集漂移（{len(dead)} vs 定稿 8）："
        f"新增 {sorted(dead - KNOWN_DEAD_TOP_KEYS)}（须先补台账行）；"
        f"消失 {sorted(KNOWN_DEAD_TOP_KEYS - dead)}")
    print(f"✓ CT-01：双向差集定稿（服务端 174 / 三端读 137 / 未读 45 / 死键 8）")


def test_CT01_no_bad_patterns_repo_wide():
    """CT-01（坏模式扫描）：全仓无写死中文 stat 键、无根目录陈旧前端副本。"""
    assert "攻伐威能" not in _read_js(), "workbench.js 仍含写死中文 stat 键「攻伐威能」"
    js_files = set()
    r = subprocess.run(["git", "ls-files", "*.js"], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        js_files.update(ROOT / p for p in r.stdout.splitlines() if p.strip())
    js_files.update(p for p in ROOT.rglob("*.js") if ".git" not in p.parts)
    assert WEB / "workbench.js" in js_files, "扫描集须含 web/workbench.js"
    offenders = [str(p.relative_to(ROOT)) for p in js_files
                 if "攻伐威能" in p.read_text(encoding="utf-8")]
    assert not offenders, f"以下 *.js 仍含写死中文 stat 键：{offenders}"
    stale = [n for n in ("index.html", "workbench.js", "workbench.css")
             if (ROOT / n).is_file()]
    assert not stale, f"根目录陈旧前端副本复现：{stale}"
    print(f"✓ CT-01：全仓 {len(js_files)} 个 *.js 无坏模式，根目录无陈旧副本")


def test_CT04_mobile_budget_guard():
    """CT-04（预算断言，第五次豁免）：command-panels spec §7（2026-11-09 总管批准 D1）——
    mobile.js ≤2100 行、mobile.css ≤29200B；token 纪律不豁免。
    第六次豁免（chat-structure D2）：手机端交谈弹窗与桌面玉简同构，CSS/JS 增量
    ——mobile.css 上限 29200B → 32000B（实测 31324B）、mobile.js 上限 2100 行
    不变（实测 1969 行）；出处：docs/compose/spec/chat-structure.md
    （2026-11-09 总管批准），token 纪律不豁免照旧。"""
    lines = len((WEB / "mobile.js").read_text(encoding="utf-8").splitlines())
    size = (WEB / "mobile.css").stat().st_size
    assert lines <= 2100, f"mobile.js {lines} 行，超 D2 豁免上限 2100 行（chat-structure D2）"
    assert size <= 32000, f"mobile.css {size}B，超 D2 豁免上限 32000B（chat-structure D2）"
    print(f"✓ CT-04：mobile.js {lines} 行 / mobile.css {size}B，均在硬线内")


# ================================================================ 返工（2026-11-08）
# 评审 must-fix M1–M4 + 总管裁决⑥ CA-006、⑧ CA-007 / V2。
# V2 先红后绿证据：~/workspace/reviews/contract-audit-rework-V2-failfirst.md
# （M1/M2/CA-006 在未修复代码上跑红留档；M3/CA-007 以变异植入跑红留档——
#  见该文件；本文件头注释「先在未修复代码上跑出失败留档」以该文件为准）。

# ---------------------------------------------------------------- M1（CA-005）
def test_CA_005_M1_missing_rem_years_no_unit():
    """M1（评审）：fmtRemYears 缺失态渲染为「—载」。

    口径：缺失时整串为「—」不带单位；有值时保持 toFixed(1) + 「载」。
    fmtRemYears 本身保持纯数值（既有 test_CA_005 断言 "80.0" / "—" 不动）；
    调用点保持 fmtRemYears(s.rem_years) 形态（既有 test_CA_005 断言该字面在场），
    单位由新 helper remYearsUnit(v) 收口（缺失返 ""，有值返「载」）。
    （2026-11-08 修订：初版用 fmtRemYearsUnit(s.rem_years) 包裹调用点，
    与既有 test_CA_005_rem_years_unified 的字面断言冲突；改此形态后两测试同绿。
    行为口径不变，见 V2 留档补记。）
    """
    js = _read_js()
    san = _extract_helper(js, "renderSanctum")
    # 行为：两 helper 拼合后的整串
    assert _node_call("fmtRemYears", "null") + _node_call("remYearsUnit", "null") == "—", "缺失须整串为「—」，不带单位"
    assert _node_call("fmtRemYears", "80.03") + _node_call("remYearsUnit", "80.03") == "80.0载"
    assert _node_call("fmtRemYears", "0") + _node_call("remYearsUnit", "0") == "0.0载"
    assert _node_call("remYearsUnit", "null") == "", "缺失时单位后缀须为空"
    assert _node_call("remYearsUnit", "80.03") == "载"
    assert san.count("fmtRemYears(s.rem_years)") == 2, "罗盘与命盘格两处须走统一 helper"
    assert san.count("remYearsUnit(s.rem_years)") == 2, "两处单位后缀须走 remYearsUnit"
    assert "${fmtRemYears(s.rem_years)}载" not in san, "命盘格不得再外挂「载」"
    assert "${fmtRemYears(s.rem_years)} <span" not in san, "罗盘不得再外挂「载」span"
    assert _node_call("fmtRemYears", "80.03") == "80.0", "fmtRemYears 本身不动（既有断言）"
    print("✓ M1：缺失寿元显「—」不带单位，有值 toFixed(1) + 「载」")


# ---------------------------------------------------------------- M2（CA-003）
_M2_FAKE_DOM = r"""
class FakeEl {
  constructor(tag) { this.tagName = tag; this.id = ""; this.className = ""; this.innerHTML = ""; this.children = []; this.listeners = {}; this.parent = null; this._closeBtn = null; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  appendChild(el) { el.parent = this; this.children.push(el); return el; }
  remove() {
    if (this.parent) { const i = this.parent.children.indexOf(this); if (i >= 0) this.parent.children.splice(i, 1); this.parent = null; }
    if (this.id === "jadeDialogHost") document._host = null;
  }
  querySelector(sel) {
    if (sel === "#jadeDialogClose") return this._closeBtn;
    return null; // #btnEquipNowAfterDig 等一律返回 null（恢复 onMount 跳过佩戴重绑）
  }
  click(type, event) { const fns = (this.listeners[type] || []).slice(); for (const fn of fns) fn(event || {}); }
}
const document = {
  _host: null,
  createElement(tag) { return new FakeEl(tag); },
  getElementById(id) {
    if (id === "jadeDialogHost") return this._host;
    if (id === "jadeDialogClose") return this._host ? this._host._closeBtn : null;
    return null;
  },
  body: { appendChild(el) {
    if (el.id === "jadeDialogHost") { document._host = el; el._closeBtn = new FakeEl("button"); el._closeBtn.id = "jadeDialogClose"; }
  } },
};
const localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
const state = { ceremony: null, ceremonyNext: null, pendingTreasureDialog: null };
const $ = (id) => document.getElementById(id);
"""

_M2_DRIVER = r"""
const CEREMONY = { kind: "loot", beats: [{ stage: "reveal", text: "得宝" }], result_ref: { name: "纯阳离火印", kind: "relic", tier: 3 } };
// 人工构造 payload：/挖宝从不返回 ceremony_next，此处手工拼一个下一幕，覆盖有 ceremonyNext 的组合
const NEXT = { kind: "tribulation", beats: [{ stage: "prelude", text: "天劫将至" }], result_ref: {} };
function hostHtml() { return document._host ? document._host.innerHTML : ""; }
function stagePending() {
  state.pendingTreasureDialog = { title: "天机秘宝 · 古阵现世破阵大典", icon: "⚡", cardClass: "max-w-xl", bodyHtml: "SETTLEMENT-纯阳离火印", footerHtml: "", equipName: "纯阳离火印" };
}
function runCombo(path, hasNext) {
  document._host = null;
  state.ceremony = null; state.ceremonyNext = null; state.pendingTreasureDialog = null;
  maybeShowCeremonyQueue(CEREMONY, hasNext ? NEXT : null);
  stagePending(); // 生产顺序：得宝幕先弹，结算随后暂存
  if (!hostHtml().includes("得宝仪式")) return { path, hasNext, error: "ceremony not shown" };
  const out = { path, hasNext, nextShown: false, settlementNow: false, settlementAfterNext: false, nextConsumed: null, pendingConsumed: null };
  if (path === "skip") {
    closeCeremonyDialog(); // 「略过」按钮的 onclick 即调此函数
    if (hostHtml().includes("天劫仪式")) {
      out.nextShown = true;
      document._host._closeBtn.click("click", {}); // 再以 ✕ 关掉下一幕
      out.settlementAfterNext = hostHtml().includes("SETTLEMENT-纯阳离火印");
      out.nextConsumed = state.ceremonyNext === null;
    } else {
      out.settlementNow = hostHtml().includes("SETTLEMENT-纯阳离火印");
    }
  } else if (path === "close") {
    document._host._closeBtn.click("click", {}); // ✕：默认关幕监听先触发，onMount 恢复监听后触发
    out.settlementNow = hostHtml().includes("SETTLEMENT-纯阳离火印");
    out.nextShown = hostHtml().includes("天劫仪式");
    out.nextConsumed = state.ceremonyNext === null;
  } else { // backdrop
    const host = document._host;
    host.click("click", { target: host }); // 背景点：默认关幕监听先触发，onMount 恢复监听后触发
    out.settlementNow = hostHtml().includes("SETTLEMENT-纯阳离火印");
    out.nextShown = hostHtml().includes("天劫仪式");
    out.nextConsumed = state.ceremonyNext === null;
  }
  out.pendingConsumed = state.pendingTreasureDialog === null;
  return out;
}
const results = [];
for (const path of ["skip", "close", "backdrop"]) for (const hasNext of [false, true]) results.push(runCombo(path, hasNext));
console.log(JSON.stringify(results));
"""


def _m2_run_node():
    """抽出仪式/结算相关函数 + 最小 fake DOM，在 node 里跑 M2 的 6 种组合。"""
    js = _read_js()
    parts = [_M2_FAKE_DOM]
    for const_name in ("CEREMONY_KIND_CN", "CEREMONY_STAGE_CN"):
        m = re.search(r"const " + const_name + r" = \{[^}]*\};", js)
        assert m, f"workbench.js 缺 {const_name}"
        parts.append(m.group(0))
    for name in ("esc", "galleryImg", "fateChoicesHtml", "fateCandidateDescHtml",
                 "ceremonySkipped", "maybeShowCeremony", "maybeShowCeremonyQueue",
                 "closeCeremonyDialog", "restorePendingTreasureDialog",
                 "openJadeDialog", "closeJadeDialog"):
        parts.append(_extract_helper(js, name))
    parts.append(_M2_DRIVER)
    tmp = Path("/tmp") / "contract_audit_m2.js"
    tmp.write_text("\n".join(parts), encoding="utf-8")
    r = subprocess.run(["node", str(tmp)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"node 执行 M2 组合失败：{r.stderr}"
    return json.loads(r.stdout.strip())


def test_CA_003_M2_close_paths_restore_with_or_without_next():
    """M2（评审）：CA-003 的 ✕/背景关幕路径在 ceremonyNext 在场时丢弃结算。

    口径：三条关幕路径（略过/✕/背景）× 有/无 ceremonyNext 共 6 种组合，结算一律
    不得丢；✕/背景的语义仍是「不顺延下一幕」（不推进 ceremonyNext），但结算本身
    须恢复。/挖宝从不返回 ceremony_next，有 ceremonyNext 的组合以人工构造
    payload（NEXT）在 node 里覆盖。
    """
    js = _read_js()
    # 静态锁：maybeShowCeremony 的 onMount 内不得再有丢弃暂存的分支
    msc = _extract_helper(js, "maybeShowCeremony")
    onmount = msc[msc.index("onMount"):]
    assert "pendingTreasureDialog = null" not in onmount, (
        "✕/背景处理不得再丢弃暂存结算（M2）")
    results = _m2_run_node()
    assert len(results) == 6, f"须覆盖 6 种组合，实得 {results}"
    by = {(r["path"], r["hasNext"]): r for r in results}
    for r in results:
        assert "error" not in r, f"组合 {r['path']}/next={r['hasNext']} 未弹幕：{r}"
        assert r["pendingConsumed"] is True, f"组合 {r['path']}/next={r['hasNext']} 暂存须被消费：{r}"
    # 略过：无下一幕立即恢复；有下一幕先演下一幕、关下一幕后恢复
    assert by[("skip", False)]["settlementNow"] is True, "略过（无下一幕）须立即恢复结算"
    assert by[("skip", True)]["nextShown"] is True, "略过（有下一幕）须先演下一幕"
    assert by[("skip", True)]["settlementAfterNext"] is True, "略过（有下一幕）关下一幕后须恢复结算"
    # ✕/背景：有/无下一幕都立即恢复，且下一幕永不弹出、不被消费
    for path in ("close", "backdrop"):
        for has_next in (False, True):
            r = by[(path, has_next)]
            assert r["settlementNow"] is True, f"{path}（next={has_next}）须立即恢复结算：{r}"
            assert r["nextShown"] is False, f"{path}（next={has_next}）下一幕不得弹出：{r}"
        assert by[(path, True)]["nextConsumed"] is False, (
            f"{path}（有下一幕）不得顺延/推进 ceremonyNext")
    print("✓ M2：三条关幕路径 × 有/无 ceremonyNext 共 6 种组合，结算一律恢复")


# ---------------------------------------------------------------- M3（Spec §5.2）
def _all_js_files():
    js_files = set()
    r = subprocess.run(["git", "ls-files", "*.js"], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        js_files.update(ROOT / p for p in r.stdout.splitlines() if p.strip())
    js_files.update(p for p in ROOT.rglob("*.js") if ".git" not in p.parts)
    return js_files


def test_CT01_M3_no_chinese_stats_bracket_reads():
    """M3(b)（评审）：通用的 stats['中文键'] 全仓扫描（不只「攻伐威能」一词）。

    只扫括号读法 stats['中文'] / stats["中文"]；合法的展示映射表
    （treasurePanelStatLine 标签表、dungeonDebuffChipsHtml CN 映射）是
    「键→中文标签」的对象字面量而非 stats[...] 读法，不在扫射面内；
    demo 假数据的中文 stat 键是对象字面量定义（stats: {"护身甲御": ...}），
    由 test_CT01_M3_demo_fabrications_guarded 另锁，不由本项扫。
    """
    rx = re.compile(r"stats\s*\[\s*['\"][^'\"]*[\u4e00-\u9fff]")
    js_files = _all_js_files()
    for must in ("web/workbench.js", "web/app.js", "web/mobile.js"):
        assert (ROOT / must) in js_files, f"扫描集须含 {must}"
    offenders = {}
    for p in sorted(js_files):
        text = p.read_text(encoding="utf-8")
        hits = [(i + 1, m.group(0)) for i, line in enumerate(text.splitlines())
                for m in [rx.search(line)] if m]
        if hits:
            offenders[str(p.relative_to(ROOT))] = hits
    assert not offenders, f"全仓仍有 stats['中文键'] 读法：{offenders}"
    assert "stats[key]" in _read_js(), "对照：变量键读法 stats[key] 须在场且不被误报"
    print(f"✓ M3(b)：全仓 {len(js_files)} 个 *.js 无 stats['中文键'] 读法")


def test_CT01_M3_demo_fabrications_guarded():
    """M3(c)（评审）：§3-G 设防检查——CA-067/068 demo 假数据中文 stat 键锁死。

    CA-068 的两处假数据（假道袍 {"护身甲御": 90, "避火抗性": 50}、仙鹤奖励
    {"纯阳火威": 50}，另含同批假数据的 "风雷遁速"/"神识念力"/"回气速度"）
    须仅出现在 demo 种子区，且不在任何联机渲染 helper 内；种子可被联机覆盖
    的机制（applyStatus 在非 demo 时以真实 items 覆盖 inventory）一并锁死。
    出现位置按 `"键":` 形式判定（坊市描述文案含「神识念力」字样，非 stat 键，
    不计入）。
    """
    js = _read_js()
    fake_keys = ["护身甲御", "避火抗性", "纯阳火威", "风雷遁速", "神识念力", "回气速度"]
    for other in ("mobile.js", "app.js"):
        text = _read_js(other)
        for k in fake_keys:
            assert k not in text, f"假 stat 键「{k}」不得出现在 {other}"
    edi = _extract_helper(js, "ensureDefaultInventory")
    crane = _extract_helper(js, "handleCraneReturned")
    i_edi = js.index(edi)
    i_crane = js.index(crane)
    # 仙鹤回调：`if (!state.demo) {...; return; }` 之后才是 demo 分支（rewards 数组起）
    i_demo_branch = i_crane + crane.index("const rewards = [")
    for k in fake_keys:
        rx = re.compile(r'"' + re.escape(k) + r'"\s*:')
        for m in rx.finditer(js):
            i = m.start()
            in_edi = i_edi <= i < i_edi + len(edi)
            in_demo_crane = i_demo_branch <= i < i_crane + len(crane)
            assert in_edi or in_demo_crane, (
                f"假 stat 键「{k}」出现在非 demo 区（workbench.js 偏移 {i}）")
    for helper in ("treasurePanelStatLine", "dungeonDebuffChipsHtml",
                   "treasureStoneLinesHtml"):
        src = _extract_helper(js, helper)
        for k in fake_keys:
            assert k not in src, f"假 stat 键「{k}」泄漏进联机渲染 helper {helper}"
    san = _extract_helper(js, "renderSanctum")
    for k in fake_keys:
        assert k not in san, f"假 stat 键「{k}」泄漏进洞府 live 视图 renderSanctum"
    assert "state.inventory = st.items.slice()" in js, "applyStatus 须以真实 items 覆盖 inventory"
    assert "if (!state.demo)" in js, "覆盖须以 state.demo 设防（联机时覆盖、demo 时合并）"
    print("✓ M3(c)：demo 假数据中文 stat 键锁死在 demo 种子区，不进联机渲染路径")


# ---------------------------------------------------------------- CA-006（总管裁决⑥）
def test_CA_006_merit_sin_zero_renders_zero():
    """CA-006（P3，总管裁决⑥纳入返工）：命盘功德/业力格假缺省。

    新角色功德/业力初值均为 0，`0 || 3650` 恒取假数。修复口径：改 ?? 判空
    （缺失显「—」，0 渲染 0），与 mobile.js:382 的 != null 口径一致。
    种子核查：renderSanctum 的 null-status fallback（:2177-2178）是 live
    渲染器的缺省分支、无 state.demo 门——进 live 视图，同修为 0（与服务端
    新号初值一致）；demoResult / loadDemo 的种子各有 state.demo 门，demo-only，不动。
    """
    js = _read_js()
    san = _extract_helper(js, "renderSanctum")
    assert "s.merit || 3650" not in js, "功德格不得再用 || 3650 假缺省"
    assert "s.sin || 120" not in js, "业力格不得再用 || 120 假缺省"
    assert 's.merit ?? "—"' in san, "功德格须 ?? 判空（缺失显「—」）"
    assert 's.sin ?? "—"' in san, "业力格须 ?? 判空（缺失显「—」）"
    assert "merit: 3650" not in san and "sin: 120" not in san, (
        "renderSanctum fallback 种子不得再捏造 3650/120")
    assert "merit: 0" in san and "sin: 0" in san, "fallback 种子须为真实初值 0"
    assert "merit: 3650" in js, "demoResult 的 demo 种子须保留（demo-only，不动）"
    token, uid = _join()
    st = WORLD._status_dict(_char(uid))
    assert st.get("merit") == 0 and st.get("sin") == 0, (
        f"新号功德/业力初值须为 0：merit={st.get('merit')} sin={st.get('sin')}")
    print("✓ CA-006：merit/sin 为 0 时渲染 0，缺失显「—」")


# ---------------------------------------------------------------- CA-007（总管裁决⑧）
def test_CA_007_adventure_success_path():
    """CA-007（总管裁决⑤⑧，台账勘误锁定、不修渲染）：

    台账「/探险从不下发 adventure 键」的前提不成立——成功路径真实下发
    "adventure": res（combat_success/exp_delta/stones_delta/narrative/loot），
    前端 workbench.js 的结构分支与之对应，保留不修。本测试只锁定、不改渲染。
    看板路（无参）确实无 adventure 键——审计抓取 151 号采的正是此路。
    """
    token, _ = _join()
    board = WORLD.handle(token, "/探险")
    assert board.get("ok") is True, board
    assert "adventure" not in board, "无参看板路无 adventure 键（与抓取 151 号一致）"
    resp = WORLD.handle(token, "/探险 野外山原")
    assert resp.get("ok") is True, resp
    adv = resp.get("adventure")
    assert isinstance(adv, dict), f"/探险成功路须下发 adventure：{resp}"
    for k in ("combat_success", "exp_delta", "stones_delta", "narrative", "loot"):
        assert k in adv, f"adventure 缺键 {k}：{adv}"
    assert isinstance(adv["combat_success"], bool), "combat_success 须为布尔"
    assert isinstance(adv["exp_delta"], int) and isinstance(adv["stones_delta"], int)
    assert isinstance(adv["narrative"], str) and adv["narrative"], "narrative 须为非空文本"
    assert isinstance(adv["loot"], list), "loot 须为列表"
    assert isinstance(resp.get("status"), dict), "成功路须透传 status"
    js = _read_js()
    i = js.index("res.adventure")
    region = js[i:i + 1200]
    for k in ("combat_success", "exp_delta", "stones_delta", "narrative", "loot"):
        assert k in region, f"前端 adventure 结构分支须读 {k}"
    print("✓ CA-007：/探险成功路下发 adventure，前端结构分支对应（锁定，不修）")
