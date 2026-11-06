"""F12 飞升榜：公式算例/tier 主导/tie-break 确定性/收录范围（现世不入、NPC 不入）/纪元过滤/自查查名/空榜/损坏行/与六榜互不污染/双端 handle+闭关白名单"""
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import DB_PATH, SEASON_DAYS
from core.ascension import (
    AscensionEngine,
    cause_category,
    parse_realm,
    score_of,
    season_of,
)
from core.clock import WorldClock
from core.leaderboard import LeaderboardEngine
from core.legacy import LegacyAccount, PastLife
from core.models import CharacterStatus
from core.season import season_info
from storage.db import CharacterRepository, LegacyRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

_MADE_USER_IDS = []
_MADE_CHAR_IDS = []


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _life(name, realm="筑基期初期", cause="寿尽坐化", lived=80.0, points=20, died_at=1000.0):
    return PastLife(
        name=name,
        realm=realm,
        cause=cause,
        lifespan_lived=lived,
        points_gained=points,
        died_at=died_at,
    )


def _account(user_id, lives):
    _MADE_USER_IDS.append(user_id)
    return LegacyAccount(user_id=user_id, past_lives=list(lives))


@pytest.fixture(autouse=True, scope="module")
def _leave_no_trace():
    """零残留：自造 legacy 行删除、自造角色置死、恢复随机流"""
    state = random.getstate()
    yield
    random.setstate(state)
    try:
        conn = sqlite3.connect(DB_PATH)
        for uid in _MADE_USER_IDS:
            conn.execute("DELETE FROM player_legacy WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        for cid in _MADE_CHAR_IDS:
            c = CharacterRepository.get_by_id(cid)
            if c is not None:
                c.status = CharacterStatus.DEAD
                CharacterRepository.save(c)
    except Exception:
        pass


# ---------------- 公式与反解 ----------------

def test_realm_parse_and_score_examples():
    assert parse_realm("金丹期圆满") == (3, 3)
    assert parse_realm("筑基期初期") == (2, 0)
    assert parse_realm("凡人") == (0, 0)
    assert parse_realm("渡劫飞升") == (9, 0)
    assert parse_realm("未知境界") == (0, 0)
    # spec 算例
    assert score_of(3, 3, 25, 120) == 3610.0
    assert score_of(2, 0, 20, 80) == 2240.0
    # tier 严格主导：凡人拉满（道统 25 + 享寿封顶 300）仍低于练气白板
    assert score_of(0, 0, 25, 300) == 400.0
    assert score_of(0, 0, 25, 300) < score_of(1, 0, 0, 0)
    # 享寿封顶：超过 300 岁不再加分
    assert score_of(2, 0, 0, 9999) == score_of(2, 0, 0, 300)
    print("✓ 公式算例与 tier 严格主导、享寿封顶")


def test_cause_category_rules():
    assert cause_category("渡劫陨落") == "渡劫陨落"
    assert cause_category("心魔反噬") == "心魔入魔"
    assert cause_category("被仇家斩杀") == "陨于斗法"
    assert cause_category("寿尽坐化") == "寿尽坐化"
    assert cause_category("身死道消") == "道陨身死"
    print("✓ 死因大类关键词规则")


# ---------------- 排序与 tie-break ----------------

def test_ranking_order_and_tiebreak_deterministic():
    same = dict(realm="筑基期初期", cause="寿尽坐化", lived=80.0, points=20)
    accounts = [
        _account(f"asc12_{_uniq('u1')}", [_life(_uniq("同分晚"), died_at=2000.0, **same)]),
        _account(f"asc12_{_uniq('u2')}", [_life(_uniq("同分早"), died_at=1000.0, **same)]),
        _account(f"asc12_{_uniq('u3')}", [
            _life(_uniq("高分客"), realm="金丹期圆满", lived=120.0, points=25, died_at=3000.0),
            _life(_uniq("低分客"), realm="练气期初期", lived=30.0, points=1, died_at=500.0),
        ]),
    ]
    entries = AscensionEngine.collect_entries(accounts)
    names = [e["name"] for e in entries]
    assert names[0].startswith("高分客") and entries[0]["score"] == 3610.0
    assert names[-1].startswith("低分客")
    # 同分：died_at 早者居前
    mid = [n for n in names if n.startswith("同分")]
    assert mid[0].startswith("同分早") and mid[1].startswith("同分晚")
    assert [e["rank"] for e in entries] == [1, 2, 3, 4]
    # 确定性：同数据再排逐字一致
    again = AscensionEngine.collect_entries(accounts)
    assert [(e["rank"], e["name"], e["score"]) for e in again] == [
        (e["rank"], e["name"], e["score"]) for e in entries
    ]
    print("✓ 排序、tie-break（先坐化者居前）与确定性")


def test_tiebreak_name_and_user_legs():
    same = dict(realm="筑基期初期", cause="寿尽坐化", lived=80.0, points=20, died_at=1500.0)
    sfx = _uniq("同戳")
    accounts = [
        _account(f"asc12_{_uniq('zz')}", [_life(f"{sfx}甲", **same)]),
        _account(f"asc12_{_uniq('aa')}", [_life(f"{sfx}乙", **same)]),
        _account(f"asc12_{_uniq('mm')}", [_life(f"{sfx}乙", **same)]),
    ]
    entries = AscensionEngine.collect_entries(accounts)
    # 同分同戳：先按名升序（乙 U+4E59 < 甲 U+7532），同名再按 user_id 升序
    assert [e["name"] for e in entries] == [f"{sfx}乙", f"{sfx}乙", f"{sfx}甲"]
    assert entries[0]["user_id"] < entries[1]["user_id"]
    assert entries[0]["user_id"].split("_")[1] != ""  # 两条同名确为不同账号
    print("✓ tie-break 后段：名升序、同名 user_id 升序")


def test_parse_realm_terminal_no_sub_and_nan_season():
    assert parse_realm("渡劫飞升后期") == (9, 0)  # tier 9 无小阶后缀口径（评审 S4）
    assert parse_realm("凡人初期") == (0, 0)
    assert season_of(float("nan")) is None
    assert season_of(float("inf")) is None
    print("✓ 终局境界不解析小阶、NaN/Inf 时间戳不入纪元")


# ---------------- 收录范围 ----------------

def test_scope_excludes_npc_and_test_accounts():
    life = _life(_uniq("应入榜"))
    accounts = [
        _account(f"asc12_{_uniq('player')}", [life]),
        _account(f"npc_asc12_{_uniq('n')}", [_life(_uniq("NPC前世"))]),
        _account(f"ai_npc_asc12_{_uniq('n')}", [_life(_uniq("AINPC前世"))]),
        _account(f"t_asc12_{_uniq('n')}", [_life(_uniq("测试号前世"))]),
        _account(f"asc12_{_uniq('empty')}", []),
    ]
    entries = AscensionEngine.collect_entries(accounts)
    names = [e["name"] for e in entries]
    assert len(entries) == 1 and names[0] == life.name
    print("✓ 收录范围：NPC/ai_npc/t_ 账号与空账不入榜")


def test_season_derivation_and_filter():
    info = season_info()
    epoch, current = info["epoch"], info["season_number"]
    ss = SEASON_DAYS * 86400.0
    died_cur = epoch + (current - 1) * ss + 3600.0
    died_next = epoch + current * ss + 3600.0
    assert season_of(died_cur) == current
    assert season_of(died_next) == current + 1
    assert season_of(0) is None
    accounts = [
        _account(f"asc12_{_uniq('s1')}", [_life(_uniq("本纪元客"), died_at=died_cur)]),
        _account(f"asc12_{_uniq('s2')}", [_life(_uniq("下纪元客"), died_at=died_next)]),
        _account(f"asc12_{_uniq('s3')}", [_life(_uniq("无戳客"), died_at=0.0)]),
    ]
    # 再添一条更高分的下纪元条目：本纪元客全局第 2、本纪元内第 1（钉死 global_rank，评审 S2）
    accounts.append(
        _account(f"asc12_{_uniq('s4')}", [
            _life(_uniq("下纪元高分"), realm="化神期圆满", lived=280.0, points=25, died_at=died_next)
        ])
    )
    rows = AscensionEngine.ranked(season=current, accounts=accounts)
    names = [e["name"] for e in rows]
    assert len(rows) == 1 and names[0].startswith("本纪元客")
    assert rows[0]["rank"] == 1 and rows[0]["global_rank"] == 2
    text = AscensionEngine.panel_text(None, "本纪元", accounts=accounts)
    assert "本纪元客" in text and "下纪元客" not in text and "无戳客" not in text
    full = AscensionEngine.panel_text(None, None, accounts=accounts)
    assert "纪元不详" in full  # died_at=0 的旧记录
    print("✓ 纪元推导、本纪元过滤重排、无戳纪元不详")


# ---------------- 面板：空榜/自查/查名 ----------------

def test_empty_board_texts():
    text = AscensionEngine.panel_text(None, None, accounts=[])
    assert "虚位以待" in text
    text = AscensionEngine.panel_text(None, "本纪元", accounts=[])
    assert "尚无前世落账" in text
    print("✓ 空榜友好文案（全局/本纪元）")


def test_self_and_search_views():
    me = _account(f"asc12_{_uniq('me')}", [
        _life(_uniq("吾之前世甲"), realm="金丹期圆满", lived=120.0, points=25, died_at=3000.0),
        _life(_uniq("吾之前世乙"), realm="练气期中期", lived=40.0, points=5, died_at=2000.0),
    ])
    other = _account(f"asc12_{_uniq('other')}", [
        _life(_uniq("他人前世"), realm="筑基期后期", lived=90.0, points=15, died_at=2500.0),
    ])
    accounts = [me, other]
    viewer = type("V", (), {"user_id": me.user_id, "name": "今世道号"})()
    text = AscensionEngine.panel_text(viewer, "我", accounts=accounts)
    assert "最佳一世：第 1 名" in text and "吾之前世甲" in text and "吾之前世乙" in text
    # 无落账者
    nobody = type("V", (), {"user_id": f"asc12_{_uniq('none')}", "name": "路人"})()
    text = AscensionEngine.panel_text(nobody, "自己", accounts=accounts)
    assert "尚无前世落账" in text
    # 查名：精确、子串、未命中
    text = AscensionEngine.panel_text(None, other.past_lives[0].name, accounts=accounts)
    assert "最佳：第 2 名" in text
    text = AscensionEngine.panel_text(None, "前世乙", accounts=accounts)
    assert "吾之前世乙" in text
    text = AscensionEngine.panel_text(None, "不存在的道号xyz", accounts=accounts)
    assert "榜上无道号" in text
    print("✓ 自查（最佳名次/无落账）与查名（精确/子串/未命中）")


# ---------------- 仓储集成：落账一致性与损坏行 ----------------

def test_repository_roundtrip_and_corrupt_row():
    uid = f"asc12_{_uniq('repo')}"
    acc = _account(uid, [_life(_uniq("落账客"), realm="元婴期初期", lived=200.0, points=25, died_at=4000.0)])
    LegacyRepository.save(acc)
    entries = AscensionEngine.collect_entries()
    mine = [e for e in entries if e["user_id"] == uid]
    assert len(mine) == 1 and mine[0]["tier"] == 4 and mine[0]["score"] == score_of(4, 0, 25, 200)
    # 损坏行不崩榜：list_all 跳过坏 JSON；飞升榜照常
    bad_uid = f"asc12_{_uniq('bad')}"
    _MADE_USER_IDS.append(bad_uid)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO player_legacy (user_id, data_json, updated_at) VALUES (?, ?, ?)",
        (bad_uid, "{not-json", time.time()),
    )
    conn.commit()
    conn.close()
    all_accounts = LegacyRepository.list_all()
    assert all(a.user_id != bad_uid for a in all_accounts)
    assert any(e["user_id"] == uid for e in AscensionEngine.collect_entries())
    print("✓ 仓储往返：落账即入榜、分数可复算、损坏行跳过不崩")


def test_old_record_defaults():
    raw = (
        '{"user_id": "asc12_oldrec", "past_lives": ['
        '{"name": "太古道人", "realm": "化神期后期", "cause": "身死道消", "lifespan_lived": 260.0}'
        "]}"
    )
    acc = LegacyAccount.model_validate_json(raw)
    _MADE_USER_IDS.append("asc12_oldrec")
    entries = AscensionEngine.collect_entries([acc])
    assert len(entries) == 1
    e = entries[0]
    assert e["tier"] == 5 and e["sub_tier"] == 2 and e["season"] is None and e["died_at"] == 0.0
    text = AscensionEngine.panel_text(None, None, accounts=[acc])
    assert "太古道人" in text and "纪元不详" in text
    print("✓ 旧档缺省字段（died_at=0）兼容，纪元不详展示")


# ---------------- 与六榜互不污染 ----------------

def test_no_pollution_with_current_boards():
    alive_name = _uniq("现世真君")
    c = WorldClock.create_new_character(f"asc12_{_uniq('alive')}", alive_name)
    c.realm.tier = 5
    CharacterRepository.save(c)
    _MADE_CHAR_IDS.append(c.id)
    past_name = _uniq("已逝前辈")
    acc = _account(f"asc12_{_uniq('gone')}", [_life(past_name, realm="化神期圆满", lived=280.0, points=25, died_at=5000.0)])
    LegacyRepository.save(acc)

    board_names = [r["name"] for r in LeaderboardEngine.board("realm", n=200)["rows"]]
    assert alive_name in board_names and past_name not in board_names
    asc_names = [e["name"] for e in AscensionEngine.collect_entries()]
    assert past_name in asc_names and alive_name not in asc_names
    print("✓ 互不污染：现世只在六榜、前世只在飞升榜")


# ---------------- 双端：server handle + 闭关白名单 ----------------

def test_server_handle_and_meditation_whitelist():
    uid = f"asc12_{_uniq('srv')}"
    past_name = _uniq("服内前世")
    acc = _account(uid, [_life(past_name, realm="金丹期中期", lived=110.0, points=18, died_at=6000.0)])
    LegacyRepository.save(acc)
    r = WORLD.join(_uniq("飞升榜服客"), user_id=uid)
    tok = r["token"]
    char = WORLD.get_char(tok)
    _MADE_CHAR_IDS.append(char.id)

    res = WORLD.handle(tok, "/飞升榜")
    assert res["ok"] and "历世纪念碑" in res["text"], res
    res = WORLD.handle(tok, "/飞升榜 我")
    assert res["ok"] and past_name in res["text"], res
    # 全局榜只断言通路与榜头（不与共享 DB 存量 top20 耦合，评审 S3）；查名走精确路径断言条目
    res = WORLD.handle(tok, "/ascend")
    assert res["ok"] and "历世纪念碑" in res["text"], res
    res = WORLD.handle(tok, f"/飞升榜 {past_name}")
    assert res["ok"] and past_name in res["text"], res
    res = WORLD.handle(tok, "/飞升榜 本纪元")
    assert res["ok"] and "飞升榜" in res["text"], res
    # 闭关放行（纯只读观照，与 /版图 同口径）
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    res = WORLD.handle(tok, "/飞升榜")
    assert res["ok"], res
    print("✓ 双端：server handle /飞升榜 全通路；闭关白名单放行")


def test_cli_source_parity():
    src = (Path(__file__).resolve().parent.parent / "cli" / "main.py").read_text(encoding="utf-8")
    assert '"/飞升榜", "/ascend"' in src  # 处理器在位（同引擎 AscensionEngine.panel_text）
    assert "AscensionEngine.panel_text(player" in src
    assert '"/飞升榜", "/ascend", "/洞府"' in src  # 闭关豁免名单在位
    assert "/飞升榜 [我|本纪元|道号]" in src  # 帮助行在位
    print("✓ CLI 源码对齐：处理器/豁免/帮助行在位")
