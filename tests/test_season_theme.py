"""F13 纪元天象主题：纪元编号纯函数推导（同号恒同/相邻必异）/三通道修正真实结算路径
（闭关 ×1.05 与 ×0.95、坊市价 ×1.05 且与 F09 折扣位序、事件权重 ×1.25）/中性路径逐值
一致/开季播报恰一次（惰性幂等）/天象 面板与 status 透出/双端 handle+闭关白名单"""
import os
import random
import sys
import time
from datetime import date as _date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

import core.season_theme as season_theme
from config import EVENT_WEIGHTS, ITEM_CATALOG, MARKET_SELL_BACK_RATE, SEASON_DAYS
from core.atlas import AtlasEngine
from core.clock import WorldClock
from core.events import EventEngine
from core.market import MarketEngine
from core.models import Character, CharacterStatus
from core.season import season_info
from core.season_theme import ANNOUNCED_KEY, SeasonThemeEngine
from core.world_channel import WorldChannel
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

HUB_LOC = "青云坊市客栈"
HUB_REGION = "东荒·青州"
QY = "青云宗"

_MADE_CHAR_IDS = []


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _fake_info(season_number: int):
    return {
        "season_number": season_number,
        "day_in_season": 1.0,
        "total_days": SEASON_DAYS,
        "remain_real_days": float(SEASON_DAYS - 1),
        "is_final_week": False,
        "is_ended": False,
        "epoch": 0.0,
        "game_years_left": SEASON_DAYS - 1,
    }


@pytest.fixture()
def _season(monkeypatch):
    """把 season_theme 命名空间内的 season_info 换成指定纪元（推导注入点）"""
    def _set(season_number: int):
        monkeypatch.setattr(
            season_theme, "season_info", lambda now=None: _fake_info(season_number)
        )
    return _set


@pytest.fixture(autouse=True, scope="module")
def _leave_no_trace():
    """残留控制：播报标记 KV 保存/还原、自造角色置死、随机流恢复。
    注：播报测试发出的世情消息是播报行为本体、无删除路径，留存于共享频道
    （与大劫播报等既有测试同口径），不计作状态残留。"""
    state = random.getstate()
    saved_announced = WorldStateRepository.get(ANNOUNCED_KEY)
    saved_atlas = WorldStateRepository.get(f"sect_atlas:{HUB_REGION}")
    yield
    random.setstate(state)
    try:
        if saved_announced is None:
            WorldStateRepository.delete(ANNOUNCED_KEY)
        else:
            WorldStateRepository.set(ANNOUNCED_KEY, saved_announced)
        if saved_atlas is None:
            WorldStateRepository.delete(f"sect_atlas:{HUB_REGION}")
        else:
            WorldStateRepository.set(f"sect_atlas:{HUB_REGION}", saved_atlas)
        for cid in _MADE_CHAR_IDS:
            c = CharacterRepository.get_by_id(cid)
            if c is not None:
                c.status = CharacterStatus.DEAD
                CharacterRepository.save(c)
    except Exception:
        pass


# ---------------- 推导确定性 ----------------

def test_theme_derivation_deterministic_and_rotating():
    names = []
    for n in range(1, 13):
        t1 = SeasonThemeEngine.theme_for_season(n)
        t2 = SeasonThemeEngine.theme_for_season(n)
        assert t1 == t2 and t1 is not t2  # 纯函数：同号恒同值；返回拷贝防污染轮转表
        names.append(t1["key"])
    for a, b in zip(names, names[1:]):
        assert a != b, (a, b)  # 相邻纪元主题必不同
    assert len(set(names[:6])) == 6  # 一轮 6 个主题互不相同
    assert names[6:] == names[:6]  # 周期 6 轮转
    # 第 1 纪元刻意为静默纪元（全中性，上线首纪元旧行为不变）
    assert SeasonThemeEngine.theme_for_season(1)["key"] == "silence"
    print("✓ 推导：同号恒同/相邻必异/周期 6 轮转/第 1 纪元静默")


def test_theme_at_uses_season_info(_season):
    _season(3)
    ctx = SeasonThemeEngine.theme_at()
    assert ctx["season"]["season_number"] == 3
    assert ctx["theme"]["key"] == "red_glow"
    assert SeasonThemeEngine.current_theme()["name"] == "赤霞纪元"
    print("✓ theme_at：第 3 纪元 → 赤霞纪元")


# ---------------- 中性路径 ----------------

def test_neutral_season_all_channels(_season):
    _season(1)  # 静默纪元
    assert SeasonThemeEngine.meditation_mult() == 1.0
    assert SeasonThemeEngine.price_mult() == 1.0
    w = SeasonThemeEngine.event_weights()
    assert w == dict(EVENT_WEIGHTS)  # 与原表逐值相等
    # 价格中性逐值：等于旧公式（标价 × 区域系数，四舍五入，下限 1）
    today = MarketEngine._day_str()
    for item in ("藏宝图", "聚灵草"):
        for loc in (HUB_LOC, "万剑仙门峰"):
            region = MarketEngine.region_of(loc)
            expected = max(
                1,
                int(round(ITEM_CATALOG[item]["price"] * MarketEngine.regional_factor(item, region, today))),
            )
            assert MarketEngine.market_price(item, loc) == expected, item
    print("✓ 中性：静默纪元三通道倍率 1.0/权重原表/价格逐值等于旧公式")


def test_event_weights_returns_copy_and_config_untouched(_season):
    _season(3)  # 赤霞
    w = SeasonThemeEngine.event_weights()
    assert w["fortune"] == EVENT_WEIGHTS["fortune"] * 1.25
    w["fortune"] = -999  # 改副本不污染 config
    assert EVENT_WEIGHTS["fortune"] == 45
    print("✓ 事件权重：返回副本，config 原表不被改写")


# ---------------- 事件通道 ----------------

def test_event_channel_weights(_season):
    _season(3)  # 赤霞：fortune ×1.25
    w = SeasonThemeEngine.event_weights()
    assert w["fortune"] == 56.25 and w["crisis"] == 35 and w["omen"] == 20
    assert SeasonThemeEngine.meditation_mult() == 1.0  # 其余通道中性
    assert SeasonThemeEngine.price_mult() == 1.0
    _season(6)  # 血月：crisis ×1.25
    w = SeasonThemeEngine.event_weights()
    assert w["crisis"] == 43.75 and w["fortune"] == 45
    # pick_type 走修正权重且只出合法类别
    picked = EventEngine.pick_type(rng=random.Random(7))
    assert picked in EVENT_WEIGHTS
    print("✓ 事件通道：赤霞 fortune 56.25 / 血月 crisis 43.75，其余通道中性")


# ---------------- 闭关灵气通道（真实结算路径） ----------------

def _settle_gain(snapshot, season_no, monkeypatch):
    monkeypatch.setattr(
        season_theme, "season_info", lambda now=None: _fake_info(season_no)
    )
    c = Character.model_validate(snapshot)
    c.realm.tier = 4  # max_exp 足够大，防修为封顶扭曲倍率（各变体同口径）
    start = WorldClock.start_meditation(c, hours_planned=2.0, stones_to_pledge=0)
    assert start["success"], start
    random.seed(20261104)  # 同种子 → 心境 roll 同口径
    res = WorldClock.settle_meditation(c, force_interrupt=False, now=time.time() + 7200.0)
    assert res["success"], res
    return float(res["exp_gained"])


def test_meditation_channel_on_real_settle_path(monkeypatch):
    base = WorldClock.create_new_character(f"st13_{_uniq('天象修士')}", _uniq("天象"))
    _MADE_CHAR_IDS.append(base.id)
    snap = base.model_dump()
    g_neutral = _settle_gain(snap, 1, monkeypatch)   # 静默
    g_rain = _settle_gain(snap, 2, monkeypatch)      # 灵雨 ×1.05
    g_cold = _settle_gain(snap, 5, monkeypatch)      # 寒潮 ×0.95
    assert g_neutral > 0
    assert abs(g_rain / g_neutral - 1.05) < 0.03, (g_neutral, g_rain)
    assert abs(g_cold / g_neutral - 0.95) < 0.03, (g_neutral, g_cold)
    print(f"✓ 闭关真实结算：静默 {g_neutral:.0f} / 灵雨 {g_rain:.0f}(×1.05) / 寒潮 {g_cold:.0f}(×0.95)")


# ---------------- 价格通道（真实价格公式 + F09 位序） ----------------

def _day_in_season(n: int, offset_days: int = 1) -> str:
    epoch = season_info()["epoch"]
    ts = epoch + (n - 1) * SEASON_DAYS * 86400.0 + offset_days * 86400.0
    return _date.fromtimestamp(ts).isoformat()


def test_price_channel_on_real_price_path():
    day_s1 = _day_in_season(1)   # 静默纪元某日
    day_s4 = _day_in_season(4)   # 金风纪元某日
    p_neutral = MarketEngine.market_price("藏宝图", HUB_LOC, day=day_s1)
    p_gold = MarketEngine.market_price("藏宝图", HUB_LOC, day=day_s4)
    assert p_neutral == 300, p_neutral           # 基准区系数 1.00、无波动
    assert p_gold == round(300 * 1.05) == 315, p_gold
    # 买卖同源：回收基准同步 ×1.05（回收率不变，不产生新套利）
    s_neutral = MarketEngine.sell_unit_base("藏宝图", HUB_LOC, day=day_s1)
    s_gold = MarketEngine.sell_unit_base("藏宝图", HUB_LOC, day=day_s4)
    assert s_neutral == int(300 * MARKET_SELL_BACK_RATE), s_neutral
    assert s_gold == int(315 * MARKET_SELL_BACK_RATE), s_gold
    print(f"✓ 价格真实路径：静默日 300 / 金风日 315（×1.05），回收同源 {s_neutral}→{s_gold}")


def test_price_theme_stacks_before_atlas_discount():
    # 位序断言：F03 区域价 → F13 天象 ×1.05 → F09 主导折扣 ×0.95
    WorldStateRepository.set(
        f"sect_atlas:{HUB_REGION}", {"inf": {QY: 500.0}, "ts": time.time()}
    )
    try:
        assert AtlasEngine.dominant_sect(HUB_REGION) == QY
        unit = MarketEngine.market_price("藏宝图", HUB_LOC, day=_day_in_season(4))
        assert unit == 315
        final = AtlasEngine.discount_unit(unit, QY, HUB_REGION)
        assert final == int(315 * (1.0 - 0.05)) == 299, final
        # 非主导宗门不享折扣：只剩天象价
        assert AtlasEngine.discount_unit(unit, "万剑仙门", HUB_REGION) == 315
    finally:
        WorldStateRepository.delete(f"sect_atlas:{HUB_REGION}")
    print("✓ 位序：市价 300 →(金风）315 →(F09 主导折扣）299；非主导停在 315")


# ---------------- 开季播报幂等 ----------------

def _season_msg_count(season_no: int) -> int:
    """按纪元号文本计数（世情存储有上限，按总数计数会被挤出误伤——评审建议 3）"""
    rows = WorldChannel.recent(limit=200)
    return sum(
        1
        for m in rows
        if getattr(m, "kind", "") == "season_theme" and f"第 {season_no} 纪元" in m.text
    )


def test_announce_exactly_once_per_season(_season):
    WorldStateRepository.set(ANNOUNCED_KEY, 0)
    before7 = _season_msg_count(7)
    before8 = _season_msg_count(8)
    _season(7)
    assert SeasonThemeEngine.ensure_announced() is True
    assert SeasonThemeEngine.ensure_announced() is False  # 惰性重复触发不重播
    assert SeasonThemeEngine.ensure_announced() is False
    assert _season_msg_count(7) == before7 + 1
    _season(8)  # 换季：新纪元再播一次
    assert SeasonThemeEngine.ensure_announced() is True
    assert _season_msg_count(8) == before8 + 1
    print("✓ 播报：同纪元恰一次、重复触发不重播、换季再播")


def test_announce_corrupt_marker_self_heals(_season):
    WorldStateRepository.set(ANNOUNCED_KEY, "不是数字")  # 标记损坏 → 按 0 处理
    _season(9)
    assert SeasonThemeEngine.ensure_announced() is True
    assert WorldStateRepository.get(ANNOUNCED_KEY) == 9  # 自愈重写
    assert SeasonThemeEngine.ensure_announced() is False
    print("✓ 播报：标记值损坏自愈重写，不抛错")


# ---------------- 异常回退（故障注入） ----------------

def test_channels_fall_back_when_theme_engine_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("theme down")

    monkeypatch.setattr(SeasonThemeEngine, "event_weights", staticmethod(_boom))
    monkeypatch.setattr(SeasonThemeEngine, "price_mult_for_day", staticmethod(_boom))
    # 事件：回退 config 原表权重，pick_type 正常工作
    assert EventEngine.pick_type(rng=random.Random(3)) in EVENT_WEIGHTS
    # 价格：回退中性，等于旧公式逐值
    today = MarketEngine._day_str()
    region = MarketEngine.region_of(HUB_LOC)
    expected = max(
        1,
        int(round(ITEM_CATALOG["藏宝图"]["price"] * MarketEngine.regional_factor("藏宝图", region, today))),
    )
    assert MarketEngine.market_price("藏宝图", HUB_LOC) == expected
    print("✓ 故障注入：主题引擎抛错时事件/价格通道回退旧行为")


# ---------------- 面板 / status / 双端 ----------------

def test_panel_text(_season):
    _season(2)
    text = SeasonThemeEngine.panel_text()
    assert "灵雨纪元" in text and "×1.05" in text and "第 2 纪元" in text
    summ = SeasonThemeEngine.summary()
    assert summ["name"] == "灵雨纪元" and summ["season_number"] == 2
    print("✓ 面板：主题名/修正/纪元号齐全；summary 口径一致")


def test_server_handle_status_and_meditation_whitelist():
    r = WORLD.join(_uniq("天象服客"), user_id=f"st13_{_uniq('srv')}")
    tok = r["token"]
    char = WORLD.get_char(tok)
    _MADE_CHAR_IDS.append(char.id)

    res = WORLD.handle(tok, "/天象")
    assert res["ok"] and "【天象】" in res["text"], res
    assert res["season_theme"]["name"] in res["text"]
    res = WORLD.handle(tok, "/omen")
    assert res["ok"] and "【天象】" in res["text"], res
    # status 透出（纯加法字段）
    sd = WORLD._status_dict(char)
    assert sd["season_theme"]["name"] == res["season_theme"]["name"]
    assert sd["season_theme"]["key"] == res["season_theme"]["key"]
    # 闭关放行（纯只读观照，与 /版图 /飞升榜 同口径）
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    res = WORLD.handle(tok, "/天象")
    assert res["ok"], res
    print("✓ 双端：server handle /天象 /omen 通路；status.season_theme 透出；闭关白名单放行")


def test_cli_source_parity():
    src = (Path(__file__).resolve().parent.parent / "cli" / "main.py").read_text(encoding="utf-8")
    assert '"/天象", "/omen"' in src  # 处理器在位
    assert "SeasonThemeEngine.panel_text()" in src  # 同引擎
    assert '"cave", "/天象", "/omen"' in src  # 闭关豁免名单在位
    assert "本纪元天象主题" in src  # 帮助行在位
    print("✓ CLI 源码对齐：处理器/豁免/帮助行在位")
