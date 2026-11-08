"""宝图开箱结算面板 stats 键契约（缺陷：面板显示「攻伐 +undefined」）。

契约来源（实测，非推测）：
- 联机 /挖宝 返回的 equipment.stats 来自服务端 ItemFactory.create_equip
  （core/items.py:150-152）：weapon 掉落恒为 {"power": N}，armor/trinket
  多一个 "defense"；scar_created 分支的遗物（core/treasure_system.py:683-698）
  直接构造 ItemEntity，stats 恒为 {}、affixes 恒为 []。
- catalog 模板（core/catalogs/equipments.py）另有 max_hp / phys_atk /
  spell_atk 等键；面板渲染口径须覆盖上述全部真实键，且不得引用
  服务端不存在的中文键（如「攻伐威能」——此前只存在于
  web/workbench.js 两个本地对象）。

测试分两层：
1. 静态契约：面板渲染只引用真实键集合；写死中文键与写死词缀芯片消失；
   本地 fallback 对象的 stats 键 ⊆ 真实键集合；无装备/无丹药/无灵石
   的 outcome 分支不再由前端凭空捏造战利品（仅 Demo 模式允许本地推断）。
2. 渲染执行：把 workbench.js 里的纯函数 treasurePanelStatLine 抽出，
   用 node 对真实 payload 跑渲染断言——任何输入不得出现 undefined/NaN。
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

from core.catalogs.equipments import EQUIPMENT_CATALOG, RAW_EQUIPMENTS, SET_BONUSES  # noqa: E402
from core.items import AFFIX_POOL, ItemEntity, ItemFactory, ItemKind  # noqa: E402


def _read_js():
    return (WEB / "workbench.js").read_text(encoding="utf-8")


def _collect_stats_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "stats" and isinstance(v, dict):
                out.update(v.keys())
            else:
                _collect_stats_keys(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_stats_keys(v, out)


def real_engine_stat_keys():
    """服务端真实可能出现在装备 stats 里的键集合（实测推导）。"""
    keys = set()
    # 1) /挖宝 四个 outcome 分支的实际生产者
    for slot in ("weapon", "armor", "trinket"):
        for tier in (1, 3, 5):
            it = ItemFactory.create_equip(
                name="契约探针", tier=tier, slot=slot,
                base_power=30.0 * tier, affix_count=2,
            )
            keys.update(it.stats.keys())
    relic = ItemEntity(
        name="纯阳离火印", kind=ItemKind.RELIC, tier=3,
        lineage_lore="自崩塌火海中夺得的上古纯阳法印。",
    )
    keys.update(relic.stats.keys())  # scar_created：恒为 {}，不断言键
    # 2) 词缀 stat_key（附在 affix 上，不直接进 stats，但口径须认识）
    keys.update(cfg["stat_key"] for cfg in AFFIX_POOL.values())
    # 3) catalog 模板 / 套装阈值里的 stats 键
    for src in (EQUIPMENT_CATALOG, RAW_EQUIPMENTS, SET_BONUSES):
        _collect_stats_keys(src, keys)
    keys.discard("power_bonus")  # 套装加成系数，不是平铺 stat
    return keys


def frontend_known_stat_keys(js):
    """从面板渲染 helper 的标签表里抽出前端认识的键。"""
    m = re.search(
        r"function treasurePanelStatLine\(stats\) \{.*?\n  \}",
        js, re.DOTALL,
    )
    assert m, "workbench.js 缺面板主属性渲染 helper treasurePanelStatLine"
    helper = m.group(0)
    labels = re.findall(r"\[\s*\"([a-z_]+)\"\s*,", helper)
    assert labels, "treasurePanelStatLine 须含 [key, 中文名] 优先序表"
    return set(labels), helper


def test_treasure_drop_real_stats_are_renderable():
    """真实掉落 stats 键 ⊆ 前端渲染口径；power 一定在列。"""
    js = _read_js()
    known, _ = frontend_known_stat_keys(js)
    real = real_engine_stat_keys()
    assert "power" in known, "挖宝武器掉落恒为 {power: N}，渲染口径须含 power"
    assert "power" in real, "探针：create_equip(weapon) 须产出 power 键"
    missing = real - known
    assert not missing, f"服务端真实 stat 键未被面板渲染口径覆盖：{sorted(missing)}"
    print(f"✓ 真实 stat 键 {sorted(real)} 均在面板渲染口径内")


def test_panel_has_no_hardcoded_chinese_stat_key():
    """面板不得再引用服务端不存在的中文 stat 键。"""
    js = _read_js()
    assert "攻伐威能" not in js, "workbench.js 仍含服务端不存在的「攻伐威能」键"
    assert "stats['攻伐威能']" not in js, "开箱面板仍在写死 stats['攻伐威能']"
    assert "treasurePanelStatLine(excavatedEquip.stats" in js, \
        "开箱面板须经 treasurePanelStatLine 渲染主属性"
    print("✓ 面板无写死中文 stat 键，改走 treasurePanelStatLine")


def test_local_fallback_stats_use_real_engine_keys():
    """两个本地 fallback 对象的 stats 键 ⊆ 服务端真实键集合。

    只校验任务指定的两处：ensureDefaultInventory 的演示剑「斩煞青锋剑」
    与开箱本地推断对象；其它演示物品（道袍/灵佩/材料等）走纳戒通用
    Object.entries 渲染、显示即键名，不在本轮双轨消除范围内。
    """
    js = _read_js()
    real = real_engine_stat_keys()
    # 演示剑：name "斩煞青锋剑" 所在对象字面量内的 stats
    m = re.search(r'name:\s*"斩煞青锋剑".*?stats:\s*\{([^}]*)\}', js, re.DOTALL)
    assert m, "未找到演示剑「斩煞青锋剑」的 stats"
    sword_keys = re.findall(r'"([^"]+)"\s*:', m.group(1))
    assert sword_keys, "演示剑 stats 为空"
    assert set(sword_keys) <= real, f"演示剑 stats 含非引擎键：{sword_keys}"
    # 开箱本地推断：if (!excavatedEquip && state.demo) 块内的 stats
    m2 = re.search(
        r"if \(!excavatedEquip && state\.demo\) \{.*?stats:\s*\{([^}]*)\}",
        js, re.DOTALL,
    )
    assert m2, "未找到开箱本地推断对象的 stats（须以 state.demo 设防）"
    dig_keys = re.findall(r'"([^"]+)"\s*:', m2.group(1))
    assert dig_keys, "开箱本地推断 stats 为空"
    assert set(dig_keys) <= real, f"开箱本地推断 stats 含非引擎键：{dig_keys}"
    print(f"✓ 两处 fallback stats 均为真实引擎键：剑 {sword_keys} / 开箱 {dig_keys}")


def test_panel_affixes_come_from_payload_not_hardcoded():
    """词缀芯片须渲染服务端返回的 affixes，而非写死【破煞】【斩龙】。"""
    js = _read_js()
    assert "【破煞】词缀" not in js and "【斩龙】词缀" not in js, \
        "开箱面板仍在写死词缀芯片（服务端 affixes 是随机抽取的）"
    assert "excavatedEquip.affixes" in js, "开箱面板须渲染 excavatedEquip.affixes"
    print("✓ 词缀改走服务端 payload affixes")


def test_offline_fallback_only_in_demo_mode():
    """无装备/无丹药/无灵石时，联机模式不得凭空捏造战利品。"""
    js = _read_js()
    assert "if (!excavatedEquip && state.demo)" in js, \
        "开箱装备本地推断须仅限 Demo 模式（联机 combat_defeat 等分支无装备）"
    assert "if (!dropPill && state.demo)" in js, \
        "开箱丹药本地推断须仅限 Demo 模式（brute_force/combat_victory/scar_created 无丹药）"
    assert "if (stoneGain === 0 && state.demo)" in js, \
        "开箱灵石本地推断须仅限 Demo 模式（brute_force 实为扣灵石、combat_defeat 无灵石）"
    print("✓ 联机缺失分支不再捏造战利品，仅 Demo 模式本地推断")


def _run_helper_in_node(helper, cases):
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("本机无 node，跳过 JS 渲染执行断言（静态契约仍覆盖）")
    driver = helper + """
const cases = %s;
const out = cases.map((c) => treasurePanelStatLine(c));
console.log(JSON.stringify(out));
""" % json.dumps(cases)
    r = subprocess.run([node, "-e", driver], capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 0, f"node 执行渲染 helper 失败：{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_panel_stat_line_renders_real_payloads_without_undefined():
    """对真实 /挖宝 payload 做渲染断言：不得出现 undefined/NaN。"""
    js = _read_js()
    _, helper = frontend_known_stat_keys(js)
    # 真实 payload：perfect_solve tier3 武器（浮点噪声值）、scar_created 遗物 {}
    weapon = ItemFactory.create_equip(
        name="斩龙古剑", tier=3, slot="weapon",
        base_power=90.0, affix_count=2,
    )
    relic = ItemEntity(name="纯阳离火印", kind=ItemKind.RELIC, tier=3,
                       lineage_lore="自崩塌火海中夺得的上古纯阳法印。")
    cases = [
        weapon.stats, relic.stats,
        {"phys_atk": 15, "spell_atk": 30}, {"spell_atk": 30},
        {"defense": 45}, {"max_hp": 220},
        {"crit_rate": 0.04}, {"power": 0}, {"power": "x"},
        {"攻伐威能": 160}, None,
    ]
    outs = _run_helper_in_node(helper, cases)
    for payload, out in zip(cases, outs):
        assert "undefined" not in out and "NaN" not in out, \
            f"渲染 {payload} 出现 undefined/NaN：{out!r}"
    assert "攻伐 +198" in outs[0], f"tier3 武器 power 应渲染为「攻伐 +198」，得 {outs[0]!r}"
    assert outs[1] == "", f"遗物 stats={{}} 应整行省略，得 {outs[1]!r}"
    assert "物攻 +15" in outs[2], f"phys_atk 优先于 spell_atk，得 {outs[2]!r}"
    assert "法攻 +30" in outs[3], f"仅 spell_atk 时应渲染法攻，得 {outs[3]!r}"
    assert "防御 +45" in outs[4] and "气血 +220" in outs[5], \
        f"防御/气血回退渲染异常：{outs[4]!r} / {outs[5]!r}"
    assert "暴击 +0.04" in outs[6], f"crit_rate 应原样渲染，得 {outs[6]!r}"
    assert outs[7] == "" and outs[8] == "" and outs[10] == "", \
        f"零值/非数值/缺失 stats 应整行省略，得 {outs[7]!r}/{outs[8]!r}/{outs[10]!r}"
    assert outs[9] == "", f"旧中文键须被忽略而非渲染 undefined，得 {outs[9]!r}"
    print("✓ 真实 payload 渲染断言通过：无 undefined/NaN，主属性口径正确")
