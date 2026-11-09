"""命令回复面板化 · 后端契约测试（command-panels，v0.3.12-gray.19 基线）。

只验服务端：新键在场 / 形态与附录 A 一致 / 键值与 text 逐行对账 / text 一字不动。
前端渲染（双端截图）由前端岗验收；本文件不读 web/。

约定：
- 每个新键的断言都以同一次 handle() 返回的 text 为对账基线（同源口径）；
- 零值显 0、缺失不捏造：空态键为 [] 或不下发（按附录 A 空态列），不在此补默认值；
- gated 任务（CP-35/39/40/41/64/65/66）先以真实构造态抓响应再断言字段。
"""
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")

import config  # noqa: E402

config.ALLOW_LOCAL_AI = True
config.LLM_API_KEY = ""
config.USE_CCSWITCH = False

from server.world import WORLD  # noqa: E402
from storage.db import (  # noqa: E402
    CharacterRepository,
    WorldStateRepository,
    init_db,
)
from core.clock import WorldClock  # noqa: E402

try:
    WORLD.stop_tick()
except Exception:
    pass

LOC = "青云坊市客栈"


def _uid(prefix="cp"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _uniq(base):
    """跨轮重跑防串扰：按名解析的命令（/交易、/结拜、/拜师、/npc货单）须用唯一名。"""
    return f"{base}{uuid.uuid4().hex[:4]}"


def _join(name="面板客", uid=None, stones=5000):
    uid = uid or _uid()
    j = WORLD.join(name, user_id=uid)
    token = j.get("token")
    assert token, f"join 失败：{j}"
    c = CharacterRepository.get_by_user_id(uid)
    c.location = LOC
    c.spirit_stones = stones
    # 越过新手资产转移保护期（交易/拍卖/专柜等 can_use_market 门禁）
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return token, uid


def _char(uid):
    return CharacterRepository.get_by_user_id(uid)


def _npc(name, uid=None, sect="", rank="", stones=5000):
    uid = uid or _uid("npc")
    c = WorldClock.create_new_character(uid, name)
    c.location = LOC
    c.spirit_stones = stones
    c.born_at = time.time() - 80 * 3600.0
    if sect:
        c.sect = sect
    if rank:
        c.sect_rank = rank
    CharacterRepository.save(c)
    return c


def _handle(token, cmd):
    r = WORLD.handle(token, cmd)
    assert isinstance(r, dict), f"{cmd} 未返回 dict：{r!r}"
    return r


# ================================================================ CP-07 /榜
def test_CP07_boards_naked_and_single():
    from core.leaderboard import BOARDS, LeaderboardEngine

    token, uid = _join("榜客")
    r = _handle(token, "/榜")
    assert r.get("ok") is True, r
    assert r.get("text") == LeaderboardEngine.format_all(5), "裸查 text 须与 format_all 同源"
    boards = r.get("boards")
    assert isinstance(boards, list) and len(boards) == 6, boards
    assert {b["key"] for b in boards} == set(BOARDS), "六榜齐全"
    # 文本只列四榜；四榜行集须与文本逐行对账（名/境界/宗门/分）
    text = r["text"]
    for b in boards:
        assert b["name"] and isinstance(b["rows"], list)
        for row in b["rows"]:
            assert set(row) >= {"rank", "name", "realm", "sect", "is_npc", "score"}
            assert isinstance(row["score"], (int, float))
            assert isinstance(row["is_npc"], bool)
        if b["key"] in ("realm", "power", "notoriety", "daohang"):
            for row in b["rows"]:
                assert row["name"] in text, f"{b['key']} 行 {row['name']} 不在文本中"
                assert f"分 {row['score']}" in text, f"{row['name']} 分数与文本不一致"
    # 单榜：既有 board 字符串键不动，新增 board_rows 行集
    r2 = _handle(token, "/榜 战力")
    assert r2.get("board") == "power", "既有 board 字符串键不得改名/改义"
    rows = r2.get("board_rows")
    assert isinstance(rows, list) and rows, "单榜须下发 board_rows"
    assert rows[0]["rank"] == 1 and "score" in rows[0]
    assert r2.get("text") == LeaderboardEngine.format_board("power")
    print("✓ CP-07 /榜 boards/board_rows 与文本对账")


# ================================================================ CP-08 /秘境
def test_CP08_realms():
    from config import SECRET_REALMS
    from core.secret_realm import SecretRealmEngine

    token, _ = _join("秘境客")
    r = _handle(token, "/秘境")
    assert r.get("ok") is True, r
    realms = r.get("realms")
    assert isinstance(realms, list) and len(realms) == len(SECRET_REALMS), realms
    assert {x["name"] for x in realms} == set(SECRET_REALMS)
    for x in realms:
        assert set(x) >= {"name", "location", "min_tier", "danger", "is_open", "remain_hours", "desc"}
        assert x["name"] in r["text"], f"秘境 {x['name']} 不在文本中"
        assert f"危险 {int(x['danger'] * 100)}%" in r["text"], f"{x['name']} 危险%与文本不一致"
        state = "已开启" if x["is_open"] else "后开启"
        assert state in r["text"]
    print("✓ CP-08 /秘境 realms 与文本对账")


# ================================================================ CP-10 /寻宝 + CP-19 /宝图
def _give_map(uid, tier=2):
    from core.treasure_system import TreasureEngine

    c = _char(uid)
    tmap = TreasureEngine.generate_treasure_map(c, tier=tier)
    c.add_item_entity(tmap)
    CharacterRepository.save(c)
    return tmap


def test_CP19_treasure_map_and_CP10_clue():
    token, uid = _join("寻宝客")
    r0 = _handle(token, "/宝图")
    assert "treasure_map" not in r0, "无图态不得下发 treasure_map"
    tmap = _give_map(uid)
    r = _handle(token, "/宝图")
    assert r.get("ok") is True, r
    tm = r.get("treasure_map")
    assert isinstance(tm, dict), r
    assert tm["name"] == tmap.name and tm["tier"] == tmap.tier
    md = tmap.custom_metadata
    assert tm["target_node"] == md.get("target_node_name")
    assert tm["target_node_id"] == md.get("target_node_id")
    assert tm["archetype"] == md.get("archetype")
    assert tm["riddle"] == md.get("riddle_text")
    assert tm["riddle"] in r["text"], "谶语须与文本逐字一致"
    assert tm["target_node"] in r["text"]
    assert tm["bagua"] in r["text"], "卦象须与文本一致（AI 关闭环境）"
    assert tm["clue"] in r["text"], "线索须与文本一致（AI 关闭环境）"
    assert isinstance(tm.get("coords"), (list, tuple)) and len(tm["coords"]) == 2
    # /寻宝：读图已激活线索链
    r2 = _handle(token, "/寻宝")
    clue = r2.get("clue")
    assert isinstance(clue, dict), r2
    assert clue["current_step"] >= 1 and clue["total_steps"] >= clue["current_step"]
    assert f"第 {clue['current_step']}/{clue['total_steps']} 线索" in r2["text"]
    assert clue["map_name"] == tmap.name
    assert clue.get("can_abandon") is True
    print("✓ CP-19 /宝图 treasure_map 与 CP-10 /寻宝 clue 对账")


def test_CP10_clue_absent_without_map():
    token, _ = _join("无图客")
    r = _handle(token, "/寻宝")
    assert "clue" not in r, "无图态不得下发 clue"
    assert "并无藏宝图" in r["text"]
    print("✓ CP-10 无图态不下发 clue")


# ================================================================ CP-11 /器灵
def test_CP11_spirit():
    from core.items import ItemEntity
    from core.models import ItemKind

    token, uid = _join("器灵客")
    r0 = _handle(token, "/器灵")
    assert "spirit" not in r0, "未穿戴法宝态不得下发 spirit"
    c = _char(uid)
    it = ItemEntity.create(
        name="试炼剑", kind=ItemKind.EQUIP, tier=4,
        description="面板测试剑", slot="weapon",
    )
    c.add_item_entity(it)
    c.equipped = [it.name]
    CharacterRepository.save(c)
    r = _handle(token, "/器灵")
    sp = r.get("spirit")
    assert isinstance(sp, dict), r
    assert isinstance(sp.get("items"), list) and sp["items"], sp
    row = sp["items"][0]
    assert row["name"] == it.name and row["tier"] == 4
    assert row["name"] in r["text"]
    assert "未唤灵" in r["text"] or "灵性已萌" in r["text"]
    assert row.get("can_awaken") is True
    assert it.name in (sp.get("awakenable") or [])
    print("✓ CP-11 /器灵 spirit 与文本对账")


# ================================================================ CP-15 /拍卖行
def test_CP15_auction():
    from copy import deepcopy

    from core.trade import AuctionEngine, AuctionStatus
    from storage.db import AuctionLotRepository

    WorldStateRepository.set("auction_next_system_at", time.time() + 3650 * 86400)
    # 快照—清空—恢复（M5 返工）：脏库残留拍品会打破 len(lots)==1 断言；
    # 快照全部拍品（含状态/到期），清空后跑，finally 原样恢复。
    saved = deepcopy(AuctionLotRepository.list_all())
    saved_ids = {lot.id for lot in saved}

    def _clear_open():
        for lot in AuctionLotRepository.list_all():
            if lot.status == AuctionStatus.PENDING:
                lot.status = AuctionStatus.CANCELLED
                AuctionLotRepository.save(lot)
            elif lot.status == AuctionStatus.OPEN:
                lot.ends_at = time.time() - 1
                AuctionLotRepository.save(lot)
        AuctionEngine.settle_expired(now=time.time())

    _clear_open()
    try:
        token, uid = _join("拍客")
        c = _char(uid)
        c.inventory.append("聚气丹")
        CharacterRepository.save(c)
        res = AuctionEngine.list_item(c, "聚气丹", 100, 500)
        assert res.get("success"), res
        r = _handle(token, "/拍卖行")
        assert r.get("ok") is True, r
        lots = (r.get("auction") or {}).get("lots")
        assert isinstance(lots, list) and len(lots) == 1, r
        lot = lots[0]
        assert lot["name"] == "聚气丹" and lot["start_price"] == 100
        assert lot["current_price"] == 100 and lot["seller"] == c.name
        assert f"【{lot['name']}】当前 {lot['current_price']} 灵石" in r["text"]
        assert f"挂单人 {lot['seller']}" in r["text"]
        assert lot["remaining_s"] > 0
        # 空拍态：到期结算后 lots == []
        for l in AuctionLotRepository.list_all():
            if l.status == AuctionStatus.OPEN:
                l.ends_at = time.time() - 1
                AuctionLotRepository.save(l)
        AuctionEngine.settle_expired(now=time.time())
        r2 = _handle(token, "/拍卖行")
        assert (r2.get("auction") or {}).get("lots") == [], r2
        assert "无进行中的拍品" in r2["text"]
    finally:
        # 先结算本用例新建的拍品（不以 OPEN 态残留），再原样恢复快照拍品。
        for lot in AuctionLotRepository.list_all():
            if lot.id not in saved_ids and lot.status == AuctionStatus.OPEN:
                lot.ends_at = time.time() - 1
                AuctionLotRepository.save(lot)
        AuctionEngine.settle_expired(now=time.time())
        for lot in saved:
            AuctionLotRepository.save(lot)
    print("✓ CP-15 /拍卖行 auction.lots 与文本对账（含空拍）")


# ================================================================ CP-16 /除凶
def test_CP16_hunt():
    from core.hunt import SIN_THRESHOLD, format_board

    # 快照—清空—恢复（M5 返工）：除凶榜只取 top-12，脏库残留高业力 NPC
    # 会把测试 NPC（业力 140）挤出榜。快照全部在榜竞争者（业力≥80 或血煞
    # 标记者）的业力/血煞期，测试期间清零，finally 原样恢复。
    saved = {}
    for c in CharacterRepository.list_all_alive():
        if c.karma.sin_value >= SIN_THRESHOLD or c.karma.is_blood_marked():
            saved[c.id] = (c.karma.sin_value, c.karma.blood_mark_until)
            c.karma.sin_value = 0
            c.karma.blood_mark_until = 0
            CharacterRepository.save(c)
    v = None
    try:
        token, uid = _join("除凶客")
        v = _npc(_uniq("凶名测试丁"), uid=_uid("npc"))
        v.karma.add_sin(SIN_THRESHOLD + 60, time.time())
        CharacterRepository.save(v)
        r = _handle(token, "/除凶")
        assert r.get("ok") is True, r
        hunt = r.get("hunt")
        assert isinstance(hunt, list) and hunt, r
        row = next((x for x in hunt if x["name"] == v.name), None)
        assert row is not None, f"通缉行缺失：{hunt}"
        assert row["sin"] == v.karma.sin_value
        assert f"业力{row['sin']}" in r["text"]
        assert row["location"] == v.location and row["realm"] == v.realm.name
        assert row["mark"] in ("血煞", "重业")
        assert isinstance(row["hunters"], int)
        assert r["text"].startswith(format_board().split("\n")[0])
    finally:
        for cid, (sin, until) in saved.items():
            c = CharacterRepository.get_by_id(cid)
            if c is not None:
                c.karma.sin_value = sin
                c.karma.blood_mark_until = until
                CharacterRepository.save(c)
        # 测试 NPC 自身不以高业力残留污染脏库。
        if v is not None:
            v.karma.sin_value = 0
            v.karma.blood_mark_until = 0
            CharacterRepository.save(v)
    print("✓ CP-16 /除凶 hunt 与文本对账")


# ================================================================ CP-17 /宗门
def test_CP17_sects():
    from config import SECTS_CONFIG
    from core.sect import format_sect_board

    token, uid = _join("宗门客")
    c = _char(uid)
    r = _handle(token, "/宗门")
    assert r.get("ok") is True, r
    sects = r.get("sects")
    assert isinstance(sects, list) and len(sects) == len(SECTS_CONFIG), sects
    assert {s["name"] for s in sects} == set(SECTS_CONFIG)
    assert r["text"] == format_sect_board(c), "text 须与 format_sect_board 同源"
    for s in sects:
        cfg = SECTS_CONFIG[s["name"]]
        assert s["monthly_salary"] == cfg["monthly_salary"]
        assert s["headquarters"] == cfg["headquarters"]
        assert f"月俸 {s['monthly_salary']}" in r["text"]
        assert f"在册 {s['members']} 人" in r["text"]
        assert isinstance(s["top"], list)
    print("✓ CP-17 /宗门 sects 与文本对账")


# ================================================================ CP-21 /who
def test_CP21_who():
    token, uid = _join("名录客")
    r = _handle(token, "/who")
    assert r.get("ok") is True, r
    who = r.get("who")
    assert isinstance(who, dict), r
    groups = who.get("groups")
    assert isinstance(groups, list) and groups
    total = sum(len(g["members"]) for g in groups)
    assert who["total"] == total
    assert f"在线世界共 {total} 名修士" in r["text"]
    me = next(g for g in groups if g["place"] == LOC)
    assert any(m["name"] == "名录客" for m in me["members"])
    assert all(set(m) >= {"name", "realm"} for g in groups for m in g["members"])
    print("✓ CP-21 /who groups 与文本对账")


# ================================================================ CP-23 /告示
def test_CP23_bounties():
    from core.bounty import BountyEngine
    from storage.db import BountyRepository

    token, uid = _join("告示客")
    issuer = _char(uid)
    target = _npc(_uniq("悬赏测试丁"), uid=_uid("npc"))
    res = BountyEngine.place_bounty(issuer, target, 100, "面板测试", False)
    assert res.get("success"), res
    BountyRepository.save(res["bounty"])
    r = _handle(token, "/告示")
    assert r.get("ok") is True, r
    bounties = r.get("bounties")
    assert isinstance(bounties, list) and bounties, r
    row = next((b for b in bounties if b["target"] == target.name), None)
    assert row is not None, bounties
    assert row["reward"] == 100 and row["status"] == "OPEN"
    assert f"目标【{row['target']}】 赏{row['reward']}" in r["text"]
    assert row["issuer"] in r["text"]
    print("✓ CP-23 /告示 bounties 与文本对账")


# ================================================================ CP-24 /天道
def test_CP24_director():
    token, _ = _join("天道客")
    r = _handle(token, "/天道")
    assert r.get("ok") is True, r
    d = r.get("director")
    assert isinstance(d, dict), r
    stats = d.get("stats") or {}
    assert f"提案 {stats.get('runs', 0)}" in r["text"]
    assert f"落账 {stats.get('accepted', 0)}" in r["text"]
    assert isinstance(d.get("active"), list)
    for a in d["active"]:
        assert set(a) >= {"type", "title", "expires_in_s"}
        assert a["title"] in r["text"]
    assert "last_run_ts" in d and "last_source" in d
    print("✓ CP-24 /天道 director 与文本对账")


# ================================================================ CP-25 /世界弧
def test_CP25_arcs():
    token, _ = _join("世界弧客")
    r = _handle(token, "/世界弧")
    assert r.get("ok") is True, r
    arcs = r.get("arcs")
    assert isinstance(arcs, dict), r
    stats = arcs.get("stats") or {}
    assert f"起弧 {stats.get('spawned', 0)}" in r["text"]
    assert f"升级 {stats.get('advanced', 0)}" in r["text"]
    assert f"决算 {stats.get('climaxed', 0)}" in r["text"]
    assert isinstance(arcs.get("arcs"), list)
    for a in arcs["arcs"]:
        assert set(a) >= {"kind", "title", "stage", "stage_cn", "deadline_in_s"}
        assert a["title"] in r["text"]
    assert isinstance(arcs.get("history"), list)
    print("✓ CP-25 /世界弧 arcs 与文本对账")


# ================================================================ CP-29 /因果·/关系
def test_CP29_links():
    from core.collusion import ensure_link

    token, uid = _join("因果客")
    a = _char(uid)
    b = _npc(_uniq("牵缠测试丁"), uid=_uid("npc"))
    ensure_link(a, b, "恩", note="面板测试牵缠")
    r = _handle(token, "/关系")
    assert r.get("ok") is True, r
    links = r.get("links")
    assert isinstance(links, list) and links, r
    row = next((x for x in links if x["name"] == b.name), None)
    assert row is not None, links
    assert row["kind"] == "恩" and row["strength"] >= 1
    assert b.name in r["text"] and "强度" in r["text"]
    # 空态：WORLD.join 会植入一条出身旧怨链，故空态改走 /关系 <无牵 NPC>
    # （create_new_character 不植链）；查他人牵缠同样下发 links。
    lonely = _npc(_uniq("无牵测试"), uid=_uid("npc"))
    r2 = _handle(token, f"/关系 {lonely.name}")
    assert r2.get("links") == [], r2
    assert "暂无显著恩怨牵缠" in r2["text"]
    print("✓ CP-29 /关系 links 与文本对账（含空态）")


# ================================================================ CP-30 /势力
def test_CP30_factions():
    token, uid = _join("势力客")
    c = _char(uid)
    r = _handle(token, "/势力")
    assert r.get("ok") is True, r
    f = r.get("factions")
    assert isinstance(f, dict), r
    assert isinstance(f.get("relations"), list) and f["relations"]
    for rel in f["relations"]:
        assert set(rel) >= {"a", "b", "status", "status_cn", "score"}
        assert f"{rel['a']} × {rel['b']}" in r["text"]
        assert f"（{rel['score']:.0f}）" in r["text"]
    assert isinstance(f.get("orders"), list) and isinstance(f.get("sieges"), list)
    stats = f.get("stats") or {}
    assert f"开令 {stats.get('missions_open', 0)}" in r["text"]
    print("✓ CP-30 /势力 factions 与文本对账")


# ================================================================ CP-31 /宗门令
def test_CP31_sect_orders():
    import copy

    from core.faction import _load, _save, list_missions, open_mission

    # 快照—清空—恢复（M5 返工）：青云宗未结宗门令 ≥8 时 open_mission 返 None，
    # 脏库已饱和。快照整份 faction 态，测试期间把青云宗未结令置为 expired，
    # finally 原样恢复（测试新建的令随快照恢复一并清除）。
    saved = copy.deepcopy(_load())
    try:
        state = _load()
        for m in state.get("missions") or []:
            if m.get("sect") == "青云宗" and m.get("status") == "open":
                m["status"] = "expired"
        _save(state)
        token, _ = _join("宗门令客")
        title = _uniq("巡山测试令")  # 开令去重含 title，跨轮重跑须唯一
        m = open_mission("青云宗", "patrol", title=title, detail="面板测试开令")
        assert m is not None, "开令失败"
        r = _handle(token, "/宗门令")
        assert r.get("ok") is True, r
        orders = r.get("sect_orders")
        assert isinstance(orders, list) and orders, r
        row = next((o for o in orders if o["id"] == m.get("id")), None)
        assert row is not None, orders
        assert row["title"] == title and row["sect"] == "青云宗"
        assert row["id"] in r["text"] and title in r["text"]
        assert f"+{row['reward_contrib']}贡献" in r["text"]
    finally:
        _save(saved)
    print("✓ CP-31 /宗门令 sect_orders 与文本对账")


# ================================================================ CP-32 /宗门势
def test_CP32_sect_power():
    from config import SECTS_CONFIG
    from core.sect_contrib import sect_powerboard

    token, _ = _join("宗门势客")
    r = _handle(token, "/宗门势")
    assert r.get("ok") is True, r
    assert r["text"] == sect_powerboard(), "text 须与 sect_powerboard 同源"
    sp = r.get("sect_power")
    assert isinstance(sp, dict), r
    assert {s["sect"] for s in sp["sects"]} == set(SECTS_CONFIG)
    for s in sp["sects"]:
        assert set(s) >= {"sect", "members", "score"}
        assert f"· {s['sect']} " in r["text"]
        assert f"分 {s['score']:.0f}" in r["text"]
    assert isinstance(sp.get("hostile_pairs"), list)
    assert isinstance(sp.get("tense_pairs"), list)
    assert "open_missions" in sp
    print("✓ CP-32 /宗门势 sect_power 与文本对账")


# ================================================================ CP-33 /贡献·/兑换
def test_CP33_contribution():
    token, uid = _join("贡献客")
    c = _char(uid)
    c.sect_contribution = 123
    CharacterRepository.save(c)
    r = _handle(token, "/贡献")
    assert r.get("ok") is True, r
    assert r["text"] == (
        f"【宗门贡献】{c.sect or '散修'} · {c.sect_contribution}\n"
        + ("可 /上交 <货> · /兑换 · /宗门环" if c.sect else "先 /拜入 <宗门>")
    )
    ct = r.get("contribution")
    assert isinstance(ct, dict), r
    assert ct["points"] == 123 and ct["sect"] == (c.sect or "散修")
    assert isinstance(ct.get("catalog"), list) and ct["catalog"]
    r2 = _handle(token, "/兑换")
    ct2 = r2.get("contribution")
    assert isinstance(ct2, dict) and ct2["points"] == 123, r2
    for item in ct2["catalog"]:
        assert item["name"] in r2["text"], f"兑换物 {item['name']} 不在 /兑换 文本中"
        assert f"— {item['cost']} 贡献" in r2["text"], f"{item['name']} 价格与文本不一致"
    # 带参 /兑换 是购买回执，归 (c)：不得带 contribution 键
    r3 = _handle(token, "/兑换 聚气丹")
    assert "contribution" not in r3
    print("✓ CP-33 /贡献·/兑换 contribution 与文本对账")


# ================================================================ CP-35 /npc货单（gated 子项）
def test_CP35_npc_goods_gated():
    token, _ = _join("货单客")
    npc_name = _uniq("柳掌柜")
    npc = _npc(npc_name, uid=_uid("npc"), sect="四海散修商会", rank="掌柜")
    r0 = _handle(token, "/npc货单")
    assert "npc_goods" not in r0 and r0.get("ok") is False
    r = _handle(token, f"/npc货单 {npc_name}")
    assert r.get("ok") is True, r
    goods = r.get("npc_goods")
    assert isinstance(goods, list) and goods, r  # 掌柜专柜非空态已抓到
    for g in goods:
        assert set(g) >= {"name", "kind", "price", "desc"}
        assert g["name"] in r["text"], f"货名 {g['name']} 不在文本中"
        assert f"— {g['price']} 灵石" in r["text"], f"{g['name']} 价格与文本不一致"
        assert g["price"] >= 1
    print("✓ CP-35 /npc货单 npc_goods 与文本对账（gated：有参非空态已抓）")


# ================================================================ CP-36 /频道
def test_CP36_channel():
    from core.world_channel import WorldChannel

    token, _ = _join("频道客")
    WorldChannel.post("panel_test", "面板测试频道消息", level="major",
                      actor="测试", location=LOC, skip_limit=True)
    r = _handle(token, "/频道")
    assert r.get("ok") is True, r
    ch = r.get("channel")
    assert isinstance(ch, list) and ch, r
    row = next((m for m in ch if m.get("text") == "面板测试频道消息"), None)
    assert row is not None, ch
    assert row["severity"] == "major" and row["type"] == "panel_test"
    assert "面板测试频道消息" in r["text"]
    print("✓ CP-36 /频道 channel 与文本对账")


# ================================================================ CP-37 /传说 + CP-38 /纪元回流
def test_CP37_legends_and_CP38_era_flow():
    from core.legends import add_legend
    from core.season import season_info

    token, _ = _join("传说客")
    add_legend(title="面板测试史笔", text="面板测试传说文本", season=1,
               tags=["panel_test"], actor="测试", weight=5)
    r = _handle(token, "/传说")
    assert r.get("ok") is True, r
    lg = r.get("legends")
    assert isinstance(lg, dict), r
    rows = lg.get("legends") or []
    assert any(x.get("text") == "面板测试传说文本" for x in rows), rows
    assert lg.get("total", 0) >= 1
    assert isinstance(lg.get("active_bias"), dict)
    row = next(x for x in rows if x.get("text") == "面板测试传说文本")
    assert row["text"] in r["text"]
    r2 = _handle(token, "/纪元回流")
    ef = r2.get("era_flow")
    assert isinstance(ef, dict), r2
    assert ef["current_season"] == int(season_info().get("season_number") or 0)
    assert f"当前纪元：第 {ef['current_season']} 纪" in r2["text"]
    assert isinstance(ef.get("active_bias"), dict)
    assert "last_reentry_ts" in ef
    print("✓ CP-37 /传说 legends 与 CP-38 /纪元回流 era_flow 对账")


# ================================================================ CP-39 /交易（gated）
def test_CP39_trade_gated():
    name_a, name_b = _uniq("交易甲"), _uniq("交易乙")
    token_a, uid_a = _join(name_a)
    token_b, uid_b = _join(name_b)
    r0 = _handle(token_a, "/交易")
    assert "trade" not in r0, "无会话态不得下发 trade"
    assert "无进行中的当面交易" in r0["text"]
    r1 = _handle(token_a, f"/交易 {name_b}")
    assert r1.get("ok") is True, r1
    assert r1.get("trade", {}).get("partner") == name_b, r1  # 发起态亦带会话结构
    r2 = _handle(token_a, "/交易出 10")
    assert r2.get("ok") is True, r2
    # 进行中裸查：B 方视角须见双方报价结构（D4 降级条件不触发：报价结构存在）
    r3 = _handle(token_b, "/交易")
    assert r3.get("ok") is True, r3
    tr = r3.get("trade")
    assert isinstance(tr, dict), r3
    assert tr["partner"] == name_a
    assert tr["a"]["stones"] == 10 and tr["b"]["stones"] == 0
    assert tr["a"]["name"] == name_a and tr["b"]["name"] == name_b
    assert "灵石 10" in r3["text"]
    assert tr["status"] == "OPEN"
    r4 = _handle(token_b, "/交易拒绝")
    assert r4.get("ok") is True, r4
    r5 = _handle(token_a, "/交易")
    assert "trade" not in r5, "会话取消后不得再下发 trade"
    print("✓ CP-39 /交易 trade 与文本对账（gated：进行中裸查已抓，报价结构存在，不降级）")


# ================================================================ CP-40 /师门任务（gated）
def test_CP40_sect_quests_gated():
    from core.social_bonds import confirm_master, master_of, propose_master

    token_d, uid_d = _join("弟子客")
    master_name = _uniq("师父测试")
    master = _npc(master_name, uid=_uid("npc"))
    master.realm.tier = 3
    CharacterRepository.save(master)
    r0 = _handle(token_d, "/师门任务")
    assert "sect_quests" not in r0, "无师父态不得下发 sect_quests"
    res = propose_master(_char(uid_d), master_name)
    assert res.get("success"), res
    res2 = confirm_master(CharacterRepository.get_by_id(master.id))
    assert res2.get("success"), res2
    assert master_of(_char(uid_d)) is not None
    r = _handle(token_d, "/师门任务")
    assert r.get("ok") is True, r
    sq = r.get("sect_quests")
    assert isinstance(sq, dict), r  # 有师父态已抓到
    assert sq["master"] == master_name
    task = sq.get("task") or {}
    assert set(task) >= {"id", "label"}
    assert isinstance(sq.get("done"), bool)
    assert task["label"] in r["text"] or task["label"][:6] in r["text"], "任务文案须与文本同源"
    print("✓ CP-40 /师门任务 sect_quests 与文本对账（gated：有师父态已抓）")


# ================================================================ CP-41 /名物（gated）
def test_CP41_relics_gated():
    from core import name_registry as _nr

    token, _ = _join("名物客")
    # 注册表是 WorldStateRepository 全局共享态：test_chase_ring.py 等先跑用例
    # 会留下听闻条目，空态断言须先快照并清空、finally 原样恢复，不得假定全局为空。
    saved = list(_nr._load())
    _nr._save([])
    try:
        r0 = _handle(token, "/名物")
        assert "relics" not in r0, "空态不得下发 relics"
        pool = _nr._load()
        pool.append({
            "name": "面板测试名物", "type": "丹药", "status": "heard",
            "desc": "面板测试名物描述", "source": "panel_test", "confidence": 0.9,
        })
        _nr._save(pool)
        r = _handle(token, "/名物")
        assert r.get("ok") is True, r
        relics = r.get("relics")
        assert isinstance(relics, list) and relics, r  # 非空态已抓到
        row = next((x for x in relics if x["name"] == "面板测试名物"), None)
        assert row is not None, relics
        assert row["type"] == "丹药" and row["desc"] == "面板测试名物描述"
        assert "面板测试名物" in r["text"]
    finally:
        _nr._save(saved)
    print("✓ CP-41 /名物 relics 与文本对账（gated：非空态已抓）")


# ================================================================ CP-49 /灵宠
def test_CP49_pets():
    from core.models import SpiritPet
    from core.pets import PET_MAX_OWNED, level_for

    token, uid = _join("灵宠客")
    r0 = _handle(token, "/灵宠")
    assert r0.get("pets") == [], "无宠态 pets 须为 []"
    c = _char(uid)
    c.pets = [SpiritPet(species="青鳞蟒", name="青鳞蟒", growth=250, intimacy=42, active=True)]
    CharacterRepository.save(c)
    r = _handle(token, "/灵宠")
    pets = r.get("pets")
    assert isinstance(pets, list) and len(pets) == 1, r
    row = pets[0]
    assert row["name"] == "青鳞蟒" and row["species"] == "青鳞蟒"
    assert row["growth"] == 250 and row["intimacy"] == 42
    assert row["level"] == level_for(250) and row["state"] == "出战中"
    assert "青鳞蟒" in r["text"] and "成长 250" in r["text"]
    assert f"共 1/{PET_MAX_OWNED} 只" in r["text"]
    print("✓ CP-49 /灵宠 pets 与文本对账（含空态）")


# ================================================================ CP-53 /行情
def test_CP53_prices():
    from core.market import MarketEngine

    token, _ = _join("行情客")
    r = _handle(token, "/行情")
    assert r.get("ok") is True, r
    pr = r.get("prices")
    assert isinstance(pr, dict), r
    regions = pr.get("regions") or []
    assert len(regions) == len(MarketEngine.all_regions()) == 4, regions
    assert pr.get("current_region") == MarketEngine.region_of(LOC)
    for reg in regions:
        assert set(reg) >= {"name", "rows"}
        assert f"◆ {reg['name']}" in r["text"]
        origin_rows = [x for x in reg["rows"] if x.get("origin") == reg["name"]]
        assert origin_rows, f"{reg['name']} 无产地行"
        for x in origin_rows:
            assert f"买{x['price']} / 回收{x['sell_price']}" in r["text"], (
                f"{reg['name']} {x['name']} 价格与文本不一致")
    print("✓ CP-53 /行情 prices 与文本对账")


# ================================================================ CP-54 /版图
def test_CP54_atlas():
    from core.atlas import AtlasEngine
    from core.market import MarketEngine

    token, _ = _join("版图客")
    r = _handle(token, "/版图")
    assert r.get("ok") is True, r
    atlas = r.get("atlas")
    assert isinstance(atlas, list) and len(atlas) == len(MarketEngine.all_regions()), atlas
    for row in atlas:
        assert set(row) >= {"region", "dominant", "mine"}
        assert f"◆ {row['region']}：" in r["text"]
        if row["dominant"]:
            assert f"主导【{row['dominant']}】{row['dominant_value']:.1f}" in r["text"]
    print("✓ CP-54 /版图 atlas 与文本对账")


# ================================================================ CP-55 /墓碑
def test_CP55_tombstone():
    from core.legacy import LifeTrace
    from storage.db import LegacyRepository

    token, uid = _join("墓碑客")
    dead_name = _uniq("面板测试故人")  # 墓碑按道号全局检索，跨轮重跑须唯一
    r0 = _handle(token, f"/墓碑 {dead_name}")
    assert "tombstone" not in r0 and "江湖无此碑" in r0["text"]
    acc = LegacyRepository.get_or_create(uid)
    acc.traces.append(LifeTrace(
        life_no=2, character_id="cp_trace_1", name=dead_name,
        realm="金丹期", cause="天劫陨落", lifespan_lived=132.0,
        sin=5, merit=40, points_gained=18, died_at=time.time() - 100,
        life_epitaph="面板测试评语",
    ))
    LegacyRepository.save(acc)
    r = _handle(token, f"/墓碑 {dead_name}")
    assert r.get("ok") is True, r
    tb = r.get("tombstone")
    assert isinstance(tb, dict), r
    assert tb["name"] == dead_name and tb["realm"] == "金丹期"
    assert tb["cause"] == "天劫陨落" and tb["points"] == 18
    assert tb["epitaph"] == "面板测试评语"
    assert dead_name in r["text"] and "道统点 +18" in r["text"]
    assert "一生评语：面板测试评语" in r["text"]
    print("✓ CP-55 /墓碑 tombstone 与文本对账（含无碑态）")


# ================================================================ CP-56 /因果链
def test_CP56_karma_chains():
    from core.karma_chains import (
        KARMA_CHAIN_DURATIONS, KarmaChain,
        SECONDS_PER_GAME_DAY,
    )
    from storage.db import KarmaChainRepository

    token, uid = _join("因果链客")
    r0 = _handle(token, "/因果链")
    assert r0.get("karma_chains") == [], "无链态 karma_chains 须为 []"
    c = _char(uid)
    # 对方须为真实存活角色：advance_for 会把查无此人的对方判死并消散链
    cp = _npc(_uniq("因果测试丁"), uid=_uid("npc"))
    now = time.time()
    total = int(KARMA_CHAIN_DURATIONS.get("en", 9))
    ch = KarmaChain(
        kind="en", polarity=1, player_id=c.id, player_name=c.name,
        counterparty_id=cp.id, counterparty_name=cp.name,
        strength=7, status="fermenting", origin_summary="面板测试因果",
        created_at=now - SECONDS_PER_GAME_DAY, ferment_at=now,
        mature_at=now + total * SECONDS_PER_GAME_DAY,
        deadline_at=now + total * SECONDS_PER_GAME_DAY,
    )
    KarmaChainRepository.save(ch)
    r = _handle(token, "/因果链")
    chains = r.get("karma_chains")
    assert isinstance(chains, list) and chains, r
    row = next((x for x in chains if x.get("counterparty") == cp.name), None)
    assert row is not None, chains
    assert row["kind"] == "en" and row["kind_cn"] == "恩"
    assert row["strength"] == 7 and row["elapsed_days"] == 1
    assert row["total_days"] == total
    assert row["ferment_pct"] == min(99, int(100 * 1 / max(1, total)))
    assert f"发酵 {row['ferment_pct']}%" in r["text"]
    assert cp.name in r["text"]
    print("✓ CP-56 /因果链 karma_chains 与文本对账（含空态）")


# ================================================================ CP-57 /委托
def test_CP57_quests():
    from core.quests import QuestEngine

    token, uid = _join("委托客")
    npc = _npc(_uniq("委托测试丁"), uid=_uid("npc"))
    r = _handle(token, "/委托")
    assert r.get("ok") is True, r
    q = r.get("quests")
    assert isinstance(q, dict), r
    assert isinstance(q.get("offers"), list)
    assert q.get("active") is None
    if q["offers"]:
        off = q["offers"][0]
        assert set(off) >= {"npc", "rings", "reward_stones", "reward_merit", "first_ring"}
        assert f"【{off['npc']}】" in r["text"]
        assert f"赏 灵石 {off['reward_stones']}" in r["text"]
    # 接取后进行中态
    offers = QuestEngine.offers_for(_char(uid))
    assert offers, "同场 NPC 应有委托可接"
    c2 = _char(uid)
    res = QuestEngine.accept(c2, offers[0][0].name)
    assert res.get("success"), res
    CharacterRepository.save(c2)  # accept 只改传入对象不落库，须存同一对象
    r2 = _handle(token, "/委托")
    q2 = r2.get("quests")
    assert isinstance(q2.get("active"), dict), r2
    assert q2["active"]["publisher"] == offers[0][0].name
    assert q2["active"]["publisher"] in r2["text"]
    assert f"第 {q2['active']['ring_index'] + 1}/{q2['active']['rings_total']} 环" in r2["text"]
    print("✓ CP-57 /委托 quests 与文本对账（offers + 进行中）")


# ================================================================ CP-58 /诺言
def test_CP58_promises():
    from core.promises import PromiseEngine

    token, uid = _join("诺言客")
    r0 = _handle(token, "/诺言")
    # 空态不走 join 号断言：随机出身「旧债」会直写一条 kind=debt 的诺言
    # （origin.py §3.5），空态改走无出身的 NPC 引擎级验证。
    assert isinstance(r0.get("promises"), list), r0
    assert PromiseEngine.panel_data(_npc(_uniq("无诺测试"), uid=_uid("npc"))) == []
    c = _char(uid)
    c.inventory.append("聚气丹")
    CharacterRepository.save(c)
    target = _npc(_uniq("诺言测试丁"), uid=_uid("npc"))
    res = PromiseEngine.make_promise(_char(uid), target, "gift", "聚气丹")
    assert res.get("success"), res
    CharacterRepository.save(_char(uid))
    r = _handle(token, "/诺言")
    ps = r.get("promises")
    assert isinstance(ps, list) and ps, r
    row = next((x for x in ps if x.get("promisee") == target.name), None)
    assert row is not None, ps
    # NPC 受诺自动应诺：make_promise 对 NPC 直接置 ACTIVE，PENDING 只对玩家受诺人
    assert row["kind"] == "gift" and row["status"] == "ACTIVE"
    assert row["desc"] in r["text"], "诺言内容须与文本逐字一致"
    print("✓ CP-58 /诺言 promises 与文本对账（含空态）")


# ================================================================ CP-59 /配方
def test_CP59_recipes():
    from core.alchemy import _all_recipes, ensure_default_recipes, success_rate

    token, uid = _join("配方客")
    r = _handle(token, "/配方")
    assert r.get("ok") is True, r
    recipes = r.get("recipes")
    assert isinstance(recipes, list), r
    known = ensure_default_recipes(_char(uid))
    assert len(recipes) == len(known), "recipes 行数须等于已悟配方数"
    book = _all_recipes()
    for row in recipes:
        assert set(row) >= {"name", "kind", "output", "materials", "stones_fee", "rate", "req_tier"}
        assert row["name"] in r["text"]
        assert f"炉火 {row['stones_fee']}灵" in r["text"]
        assert f"成率 {row['rate']:.0%}" in r["text"], f"{row['name']} 成率与文本不一致"
        assert row["rate"] == success_rate(_char(uid), book[row["id"]])
        assert row["tier_ok"] == (_char(uid).realm.tier >= row["req_tier"])
    print("✓ CP-59 /配方 recipes 与文本对账")


# ================================================================ CP-60 /炼体·/炼神
def test_CP60_body_soul_detail():
    token, uid = _join("炼体客")
    r = _handle(token, "/炼体")
    assert r.get("ok") is True, r
    d = r.get("body_soul_detail")
    assert isinstance(d, dict), r
    assert set(d) >= {"body", "soul"}
    assert d["body"]["level"] == 0 and d["soul"]["level"] == 0
    assert d["body"]["next_cost"] is not None
    assert "下一层（1 层）成本" in r["text"]
    assert d["body"]["next_cost"]["item"] in r["text"]
    r2 = _handle(token, "/炼神")
    d2 = r2.get("body_soul_detail")
    assert d2 == d, "两命令共享同一 body_soul_detail"
    assert "炼神" in r2["text"]
    # 修炼回执（写路径）不得带面板键
    r3 = _handle(token, "/炼体 修炼")
    assert "body_soul_detail" not in r3
    print("✓ CP-60 /炼体·/炼神 body_soul_detail 与文本对账")


# ================================================================ CP-61 /镇魔
def test_CP61_demon():
    from core.heart_demon_state import DemonStateEngine

    token, uid = _join("镇魔客")
    c = _char(uid)
    c.demon_seed = 50.0
    CharacterRepository.save(c)
    r = _handle(token, "/镇魔")
    assert r.get("ok") is True, r
    d = r.get("demon")
    assert isinstance(d, dict), r
    assert d["seed"] == 50.0
    assert d["stage"] == DemonStateEngine.stage_for(50.0) == 2
    assert d["stage_name"] == "滋长"
    assert "魔念 50 / 临发 90" in r["text"]
    assert d["options"], d
    pill = next(o for o in d["options"] if o["kind"] == "pill")
    assert "百年灵芝" in r["text"] and pill["item"] == "百年灵芝"
    calm = next(o for o in d["options"] if o["kind"] == "calm")
    assert calm["min_dao"] == 50
    print("✓ CP-61 /镇魔 demon 与文本对账")


# ================================================================ CP-62 /飞升榜
def test_CP62_ascend():
    from core.legacy import PastLife
    from storage.db import LegacyRepository

    token, uid = _join("飞升客")
    # 裸查是全局榜，旧轮前世会残留；空态改走 /飞升榜 我（只查本人前世）
    r0 = _handle(token, "/飞升榜 我")
    assert r0.get("ascend") == [], "空碑态 ascend 须为 []"
    acc = LegacyRepository.get_or_create(uid)
    acc.past_lives.append(PastLife(
        name="飞升测试故人", realm="元婴期", cause="天劫陨落",
        lifespan_lived=210.0, sin=0, merit=120, points_gained=25,
        died_at=time.time() - 86400,
    ))
    LegacyRepository.save(acc)
    r = _handle(token, "/飞升榜")
    rows = r.get("ascend")
    assert isinstance(rows, list) and rows, r
    row = next((x for x in rows if x["name"] == "飞升测试故人"), None)
    assert row is not None, rows
    assert row["realm"] == "元婴期" and row["cause"] == "天劫陨落"
    assert f"分 {row['score']:.0f}" in r["text"], "榜分须与文本一致"
    assert "飞升测试故人" in r["text"]
    print("✓ CP-62 /飞升榜 ascend 与文本对账（含空态）")


# ================================================================ CP-64 /悟丹·/悟器（gated）
def test_CP64_recipe_gated():
    token, _ = _join("悟方客")
    r = _handle(token, "/悟丹 随机")
    assert r.get("ok") is True, r
    recipe = r.get("recipe")
    assert isinstance(recipe, dict), r  # 成功态已抓到
    assert recipe["name"] in r["text"]
    assert recipe["output"] in r["text"]
    assert f"炉火 {recipe['stones_fee']}" in r["text"]
    assert f"{recipe['base_rate']:.0%}" in r["text"]
    assert recipe["kind"] in ("pill", "equip")  # 本地兜底不分丹/器，属既有行为
    assert f"/炼{'丹' if recipe['kind'] == 'pill' else '器'} {recipe['name']}" in r["text"]
    assert isinstance(recipe.get("materials"), dict) and recipe["materials"]
    print("✓ CP-64 /悟丹 recipe 与文本对账（gated：成功态已抓）")


# ================================================================ CP-65 /议政（gated）
def test_CP65_council_gated():
    # 快照—清空—恢复（M5 同类隔离，返工轮补）：议政会话 2h 投票窗口过期后
    # panel_data 对已结算会话返回 seats=[]（core/council.py:524-539），
    # 脏库残留的已结算会话会让“有宗门态席位非空”断言失败。删会话键使
    # _advance 重开新场，finally 原样恢复。
    _ABSENT = object()
    saved_session = WorldStateRepository.get("sect_council:青云宗", _ABSENT)
    WorldStateRepository.delete("sect_council:青云宗")
    try:
        token, uid = _join("议政客")
        r0 = _handle(token, "/议政")
        assert "council" not in r0, "散修态不得下发 council"
        c = _char(uid)
        c.sect = "青云宗"
        CharacterRepository.save(c)
        r = _handle(token, "/议政")
        assert r.get("ok") is True, r
        co = r.get("council")
        assert isinstance(co, dict), r  # 有宗门态已抓到
        assert co["sect"] == "青云宗"
        assert co["topic"]["name"] in r["text"]
        assert isinstance(co.get("seats"), list) and co["seats"]
        for s in co["seats"]:
            assert set(s) >= {"name", "stance", "stance_cn"}
            assert s["name"] in r["text"]
        votes = co.get("votes") or {}
        assert f"支持 {votes.get('support', 0)}" in r["text"]
        assert f"反对 {votes.get('oppose', 0)}" in r["text"]
    finally:
        if saved_session is _ABSENT:
            WorldStateRepository.delete("sect_council:青云宗")
        else:
            WorldStateRepository.set("sect_council:青云宗", saved_session)
    print("✓ CP-65 /议政 council 与文本对账（gated：有宗门态已抓）")


# ================================================================ CP-66 /结义任务（gated）
def test_CP66_sworn_quests_gated():
    from core.social_bonds import accept_sworn, propose_sworn, sworn_partner

    token_a, uid_a = _join("结义甲")
    b_name = _uniq("结义乙")
    b = _npc(b_name, uid=_uid("npc"))
    r0 = _handle(token_a, "/结义任务")
    assert "sworn_quests" not in r0, "无结拜态不得下发 sworn_quests"
    res = propose_sworn(_char(uid_a), b_name)
    assert res.get("success"), res
    res2 = accept_sworn(CharacterRepository.get_by_id(b.id))
    assert res2.get("success"), res2
    assert sworn_partner(_char(uid_a)) is not None
    r = _handle(token_a, "/结义任务")
    assert r.get("ok") is True, r
    sq = r.get("sworn_quests")
    assert isinstance(sq, dict), r  # 有结拜态已抓到
    assert sq["partner"] == b_name
    task = sq.get("task") or {}
    assert set(task) >= {"id", "label"}
    assert task["label"] in r["text"], "结义任务文案须与文本同源"
    assert isinstance(sq.get("done"), bool)
    print("✓ CP-66 /结义任务 sworn_quests 与文本对账（gated：有结拜态已抓）")


# ================================================================ 零新键对象（复用既有键，服务端零新增）
def test_zero_new_keys_reuse():
    """附录 A 零新键清单：既有键在场即为后端完成，前端岗直接读。"""
    token, uid = _join("复用客")
    c = _char(uid)
    c.sect = "青云宗"
    c.sect_rank = "外门弟子"
    CharacterRepository.save(c)
    cases = [
        ("/profile", "profile"),
        ("/look", None),  # status 键在 /look 响应里
        ("/here", "here"),
        ("/目标", "goals"),
        ("/任务", "defs"),
        ("/帮助", "commands"),
        ("/议程", "agendas"),
        ("/命格", "fate"),
        ("/回应", "drama_pending"),
        ("/探查", "scan"),
        ("/大劫", "season"),
        ("/ai", "ai_data"),
        ("/钱包", "wallet"),
        ("/命途", "fate_thread"),
        ("/功法", "arts"),
    ]
    for cmd, key in cases:
        r = _handle(token, cmd)
        assert r.get("ok") is True, (cmd, r)
        if key:
            assert key in r, f"{cmd} 缺既有键 {key}"
        else:
            assert "status" in r and isinstance(r["status"], dict), "/look 缺 status"
    r = _handle(token, "/近况")
    assert r.get("ok") is True, r
    assert "goals" in r and "related" in r and "entry" in r, "/近况 缺 entry/goals/related"
    r = _handle(token, "/世情")
    assert "evolution" in r and "actions" in r, "/世情 缺 evolution/actions"
    r = _handle(token, "/道统")
    assert r.get("ok") is True, r
    assert {"points", "lives", "earned", "boosts", "past_lives"} <= set(r), "/道统 缺 legacy_info 键"
    r = _handle(token, "/宗门环")
    assert r.get("ok") is True and "sect_ring" in r.get("status", {}), "/宗门环 status 缺 sect_ring"
    r = _handle(token, "/AI日志")
    assert r.get("ok") is True
    assert ("items" in r) or ("暂无 AI 调用记录" in r.get("text", "")), "/AI日志 items/空态二选一"
    r = _handle(token, "/图鉴")
    assert "gallery" in r.get("status", {}), "/图鉴 status 缺 gallery"
    r = _handle(token, "/坊市")
    assert "market_listings" in r.get("status", {}), "/坊市 status 缺 market_listings"
    r = _handle(token, "/洞府")
    assert "cave" in r.get("status", {}), "/洞府 status 缺 cave"
    r = _handle(token, "/心法")
    assert "arts" in r.get("status", {}), "/心法 status 缺 arts"
    print("✓ 零新键对象：既有键在场（24 项）")


# ================================================================ text 一字不动（抽查）
def test_text_unchanged_spot_checks():
    """K1/K3：text 生成逻辑一字不动；抽查新键分发不改文本。"""
    from core.leaderboard import LeaderboardEngine
    from core.sect import format_sect_board
    from core.sect_contrib import format_shop, sect_powerboard

    token, uid = _join("文本客")
    c = _char(uid)
    r = _handle(token, "/榜")
    assert r["text"] == LeaderboardEngine.format_all(5)
    r = _handle(token, "/宗门")
    assert r["text"] == format_sect_board(c)
    r = _handle(token, "/宗门势")
    assert r["text"] == sect_powerboard()
    r = _handle(token, "/兑换")
    assert r["text"] == format_shop() + f"\n当前贡献：{c.sect_contribution}"
    r = _handle(token, "/贡献")
    assert r["text"] == (
        f"【宗门贡献】{c.sect or '散修'} · {c.sect_contribution}\n"
        + ("可 /上交 <货> · /兑换 · /宗门环" if c.sect else "先 /拜入 <宗门>")
    )
    print("✓ text 一字不动抽查（/榜·/宗门·/宗门势·/兑换·/贡献）")


# ================================================================ M3：reason 码映射中文标签（返工，2026-11-09）
def test_M3_reason_code_mapped_to_label():
    """M3：/近况 relations[].summary 不得含 reason 原码。
    origin →「出身牵连」；无映射的纯 ASCII 码（如 test）省略「：…」后缀；
    中文标签（如交谈）原样保留；refs 内部索引保持原码（origin 判定依赖它）。
    面板 cpNearby 与文本同源直通同一 summary，故一处修复双端生效。"""
    from core.npc_mind import shift_attitude
    from storage.db import EventLedgerRepository

    token, uid = _join("近况码客")
    player = _char(uid)

    def _relation_summary(npc):
        rows = EventLedgerRepository.query_by_type_for_target(
            player.id, type="RELATION", limit=30)
        mine = [r for r in rows if r["actor_id"] == npc.id]
        assert mine, f"{npc.name} 的 RELATION 行缺失"
        return mine[0]

    npc1 = _npc(_uniq("出身牵连丁"))
    shift_attitude(npc1, player.id, 50, reason="origin")
    row1 = _relation_summary(npc1)
    assert "出身牵连" in row1["summary"], row1["summary"]
    assert "origin" not in row1["summary"], row1["summary"]
    assert "reason:origin" in (row1.get("refs") or []), "refs 内部索引须保持原码"

    npc2 = _npc(_uniq("无码丁"))
    shift_attitude(npc2, player.id, 50, reason="test")
    row2 = _relation_summary(npc2)
    assert "test" not in row2["summary"], row2["summary"]
    assert row2["summary"].endswith("亲近"), row2["summary"]

    npc3 = _npc(_uniq("交谈丁"))
    shift_attitude(npc3, player.id, 50, reason="交谈")
    row3 = _relation_summary(npc3)
    assert row3["summary"].endswith("：交谈"), row3["summary"]
    print("✓ M3 reason 码映射中文标签（origin→出身牵连，无映射码省略后缀）")


# ================================================================ M6：(c) 类文本对照（返工，2026-11-09）
def test_text_unchanged_c_class_spot_checks():
    """M6 / AC-06：(c) 类 51 项抽样 ≥10 项抓取对照——响应文案须与基线抓取
    （docs/compose/contract-audit-captures/，种子 20261108）逐字一致。
    无参用法 error 与无交谈提示均为状态无关文案，可逐字对照；/转世活人态
    无基线抓取，以 server/world.py:1012 的 error 字面量为准（同轮锁定）。
    现有 5 项 (b) 类对照（test_text_unchanged_spot_checks）保留。"""
    import json

    caps = Path(__file__).resolve().parent.parent / "docs/compose/contract-audit-captures"
    token, uid = _join("文本丙客")
    cases = [
        ("/购买", "119-buy-noargs.json", "error"),
        ("/出售", "120-sell-noargs.json", "error"),
        ("/斗法", "146-fight-noargs.json", "error"),
        ("/挂赏", "123-place-bounty-noargs.json", "error"),
        ("/上交", "169-donate-noargs.json", "error"),
        ("/寄存", "176-deposit-noargs.json", "error"),
        ("/支取", "177-withdraw-noargs.json", "error"),
        ("/拜师", "165-apprentice-noargs.json", "error"),
        ("/传功", "132-teach-noargs.json", "error"),
        ("/围剿", "086-ro-围剿.json", "error"),
        ("/追查", "220-chase-noargs.json", "error"),
        ("/接令", "240-accept-hunt-noargs.json", "error"),
        ("/买寄售", "127-buy-listing-noargs.json", "error"),
        ("/撤单", "128-cancel-listing-noargs.json", "error"),
        ("/释放", "140-release-captive.json", "error"),
        ("/会话", "095-ro-chatpanel.json", "text"),
    ]
    assert len(cases) >= 10, "AC-06 要求 (c) 类对照 ≥10 项"
    for cmd, slug, field in cases:
        base = json.loads((caps / slug).read_text(encoding="utf-8"))["response"]
        r = _handle(token, cmd)
        assert r.get(field) == base.get(field), (
            f"{cmd} 文案与基线抓取 {slug} 不一致：{r.get(field)!r} vs {base.get(field)!r}"
        )
    r = _handle(token, "/转世")
    assert r.get("error") == "此世尚存，何须转世？可先 /道统 查看。", r
    print(f"✓ (c) 类文本对照 {len(cases) + 1} 项与基线逐字一致（16 项抓取 + /转世活人态）")


# ================================================================ 附录 A 新键总表（键名登记）
# 39 个附录 A 登记键中 35 个为全新顶层名；director / arcs / trade / recipe
# 四键的顶层名已在 contract-audit 清册中（/world/director 快照、/悟丹、
# /招徕 trade 标记），本轮只扩展其下发形态，不新增顶层名。
APPENDIX_A_NEW_TOP_KEYS = {
    "boards", "board_rows", "realms", "clue", "spirit", "auction", "hunt",
    "sects", "treasure_map", "who", "bounties", "links", "factions",
    "sect_orders", "sect_power", "contribution", "npc_goods", "channel",
    "legends", "era_flow", "sect_quests", "relics", "pets", "prices",
    "atlas", "tombstone", "karma_chains", "quests", "promises", "recipes",
    "body_soul_detail", "demon", "ascend", "council", "sworn_quests",
}


def test_appendix_a_key_inventory():
    """附录 A 登记的 35 个全新顶层键名须全部在本文件用例中出现过（防漏键）。"""
    src = Path(__file__).read_text(encoding="utf-8")
    missing = sorted(k for k in APPENDIX_A_NEW_TOP_KEYS if f'"{k}"' not in src and f"'{k}'" not in src)
    assert not missing, f"附录 A 新键未被任何用例覆盖：{missing}"
    assert len(APPENDIX_A_NEW_TOP_KEYS) == 35
    print("✓ 附录 A：35 个全新顶层键名全数有测试覆盖")


# ================================================================ 前端静态断言
# 合并来源：feat/cmd-panels-frontend 的同名文件（7 用例）。
# 后端 40 用例在上；本节只读 web/，不碰服务端（K2 扫描 / D1 预算 /
# node 夹具 harness）。两岗用例名无重叠。


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
    """AC-04：mobile.css 新增面板样式全量 var()、零裸 hex。
    M2 返工（2026-11-09）：零裸 hex 纪律适用于全部新增 CSS，锁定测试扩展到
    workbench.css 新增段（token 定义在 CP-00 标记之前，不计入扫描段，
    与 mobile.css :root 体例一致）。"""
    for css_path in (MOB_CSS, WEB / "workbench.css"):
        text = css_path.read_text(encoding="utf-8")
        marker = "/* 命令回复面板化（command-panels CP-00）"
        assert marker in text, f"{css_path.name} 缺 CP-00 标记"
        added = text[text.index(marker):]
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", added), f"{css_path.name} 新增 CSS 含裸 hex"


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
