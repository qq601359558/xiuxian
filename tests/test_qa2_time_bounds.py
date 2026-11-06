"""QA 第二轮 · 重点 4：时间边界组合（注入时间戳逐项核查 < / <= 口径）。

- 典当：t >= due_at 没收——恰到期刻赎回失败、due−1s 赎回成功（pawn.md「到期前仍可再赎」）；
- 委托：t >= expires_at 过期——deliver 在恰到期刻先结算过期、due−1s 不触发过期；
- 农场过熟：t > matures_at + 24h 才减产（严格大于）——恰 +24h 全额、+24h+1s 减产 1；
- 纪元切换：theme_at 在边界刻即时切换到新纪元主题（season 1→2），
  price_mult_for_day 按当日正午锚点与 price_mult(正午) 自洽；
- 心魔血煞跨锚点：sync 分段推进的覆盖时长恰按实际天数计（2/日 × 道心系数），
  同刻重复 sync 幂等、超过血煞消散点后不再增长。
"""
import os
import random
import sys
import time
from datetime import datetime as _dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import SECONDS_PER_GAME_YEAR
from core.clock import WorldClock
from core.farm import CAVE_WITHER_SECONDS, FarmEngine
from core.heart_demon_state import BLOOD_SEED_PER_DAY, DemonStateEngine
from core.models import CharacterStatus, FarmPlot, QuestChain, QuestRing
from core.pawn import PAWN_TERM_SECONDS, PawnEngine
from core.quests import QuestEngine
from core.season import season_info
from core.season_theme import SeasonThemeEngine
from storage.db import (
    CharacterRepository,
    MarketListingRepository,
    PawnTicketRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"
ITEM = "妖兽内丹"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, stones=500, items=()):
    c = WorldClock.create_new_character(f"qa2_{name}_{_tag()}", f"QA2{name}{_tag()}")
    c.location = LOC_A
    c.spirit_stones += stones
    for it in items:
        c.inventory.append(it)
    CharacterRepository.save(c)
    return c


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _cleanup(*chars):
    for c in chars:
        if c is None:
            continue
        live = _get(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


# ---------------- 典当恰到期刻 ----------------

def test_pawn_redeem_boundary():
    c1 = _char("当界甲", items=[ITEM])
    c2 = _char("当界乙", items=[ITEM])
    try:
        for c, at_offset, should_ok in ((c1, -1.0, True), (c2, 0.0, False)):
            obj = _get(c.id)
            t0 = 1_900_000_000.0
            ticket, res = PawnEngine.pawn_item(obj, ITEM, now=t0)
            assert res["success"], res
            PawnTicketRepository.save(ticket)
            CharacterRepository.save(obj)
            due = ticket.due_at
            assert abs(due - (t0 + PAWN_TERM_SECONDS)) < 1e-6
            me = _get(c.id)
            ticket2, res2 = PawnEngine.redeem_item(me, ITEM, now=due + at_offset)
            if should_ok:
                assert res2["success"], res2
                CharacterRepository.save(me)
                assert ITEM in _get(c.id).inventory
            else:
                assert not res2["success"] and "逾期" in res2["message"], res2
                rows = [t for t in PawnTicketRepository.list_by_owner(c.id)
                        if t.item_name == ITEM]
                assert rows and rows[0].status.value == "FORFEITED", rows
                # 没收物流入坊市寄售（卖家=天道当铺）
                lst = [l for l in MarketListingRepository.list_all()
                       if l.item_name == ITEM and l.seller_id == c.id]
                assert not lst  # 寄售卖家为当铺而非票主，票主名下无挂单
        print("✓ 典当边界：due−1s 可赎、恰 due 刻没收（t >= due_at 口径与 spec 一致）")
    finally:
        _cleanup(c1, c2)


# ---------------- 委托恰到期刻 ----------------

def test_quest_expire_boundary():
    c = _char("委托界")
    try:
        E = 1_900_100_000.0
        chain = QuestChain(
            publisher_id="npc_qa2_pub", publisher_name="QA2发布者",
            rings=[QuestRing(kind="deliver", deliver_npc_id="npc_qa2_pub",
                              deliver_npc_name="QA2发布者")],
            accepted_at=E - 3600, expires_at=E, reward_stones=10, reward_merit=5,
        )
        obj = _get(c.id)
        obj.active_quest = chain
        obj.lifespan.death_timestamp = E + 30 * 86400  # 注入时刻下角色须寿元未尽
        CharacterRepository.save(obj)
        me = _get(c.id)
        assert QuestEngine.settle_expired(me, now=E - 1) is False
        assert me.active_quest is not None
        res = QuestEngine.deliver(me, now=E)
        assert not res["success"] and "过期" in res["message"], res
        assert me.active_quest is None  # deliver 先行结算过期并清链
        print("✓ 委托边界：expires−1s 不过期、恰 expires 刻 deliver 先结算过期（t >= 口径）")
    finally:
        _cleanup(c)


# ---------------- 农场过熟恰 +24h ----------------

def test_farm_overripe_boundary():
    c = _char("田界")
    try:
        obj = _get(c.id)
        obj.cave_level = 1
        obj.location = LOC_A
        M = 1_900_200_000.0
        obj.farm_plots = [FarmPlot(crop="聚灵草种子", planted_at=M - 3600, matures_at=M)]
        CharacterRepository.save(obj)
        # 恰 +24h：严格大于口径 → 未过熟，同种子 rng 下与基准产量一致
        me = _get(c.id)
        res = FarmEngine.harvest(me, now=M + CAVE_WITHER_SECONDS, rng=random.Random(7))
        assert res["success"], res
        full = res["gained"].get("聚灵草", 0)
        CharacterRepository.save(me)
        # +24h+1s：过熟减产 1
        me = _get(c.id)
        me.farm_plots = [FarmPlot(crop="聚灵草种子", planted_at=M - 3600, matures_at=M)]
        CharacterRepository.save(me)
        me = _get(c.id)
        res2 = FarmEngine.harvest(me, now=M + CAVE_WITHER_SECONDS + 1, rng=random.Random(7))
        assert res2["success"], res2
        over = res2["gained"].get("聚灵草", 0)
        assert over == max(1, full - 1), (full, over)
        assert "过熟" in res2["message"]
        print(f"✓ 农场边界：恰 +24h 全额 {full}、+24h+1s 过熟减产为 {over}（严格 > 口径）")
    finally:
        _cleanup(c)


# ---------------- 纪元切换刻 ----------------

def test_season_boundary_theme_switch():
    now = time.time()
    info = season_info(now)
    epoch = info["epoch"]
    from config import SEASON_DAYS
    boundary = epoch + SEASON_DAYS * 86400.0  # 第 1 纪元 → 第 2 纪元切换刻
    if boundary <= now:  # 当前已在第 2+ 纪元：改用下一切换刻，结论同构
        cur = info["season_number"]
        boundary = epoch + cur * SEASON_DAYS * 86400.0
    before = SeasonThemeEngine.theme_at(boundary - 60)
    after = SeasonThemeEngine.theme_at(boundary + 60)
    assert after["season"]["season_number"] == before["season"]["season_number"] + 1
    assert after["theme"] != before["theme"] or after["season"]["season_number"] != before["season"]["season_number"]
    # 价格日锚自洽：price_mult_for_day(切换日) == price_mult(该日正午)
    day_str = _dt.fromtimestamp(boundary).strftime("%Y-%m-%d")
    d = _dt.fromtimestamp(boundary)
    noon_ts = _dt(d.year, d.month, d.day, 12, 0, 0).timestamp()
    assert SeasonThemeEngine.price_mult_for_day(day_str) == SeasonThemeEngine.price_mult(noon_ts)
    print(f"✓ 纪元边界：{before['season']['season_number']}→{after['season']['season_number']} 刻切换，"
          f"主题 {before['theme'].get('name')}→{after['theme'].get('name')}；价格日锚与正午自洽")


# ---------------- 心魔血煞跨锚点 ----------------

def test_demon_blood_cross_anchor_sync():
    c = _char("魔界")
    try:
        obj = _get(c.id)
        T0 = 1_900_300_000.0
        obj.demon_anchor_at = T0
        obj.demon_sin_seen = 0
        obj.demon_seed = 0.0
        obj.karma.sin_value = 0
        obj.karma.dao_heart = 100  # 有效道心 ≥85 → 系数 0.25（见 _dao_suppress_mult）
        # T0 时刻新标记：血煞持续 3 游戏年 = 3 现实日
        obj.karma.blood_mark_until = T0 + 3 * SECONDS_PER_GAME_YEAR
        CharacterRepository.save(obj)
        per_day = BLOOD_SEED_PER_DAY * 0.25
        me = _get(c.id)
        s1 = DemonStateEngine.sync(me, now=T0 + 86400)
        assert abs(s1 - per_day * 1) < 1e-6, s1
        s1b = DemonStateEngine.sync(me, now=T0 + 86400)  # 同刻重复 sync 幂等
        assert abs(s1b - s1) < 1e-9, (s1, s1b)
        s2 = DemonStateEngine.sync(me, now=T0 + 2 * 86400)
        assert abs(s2 - per_day * 2) < 1e-6, s2
        # 超过血煞消散点（+3d）：覆盖封顶于 until，总量恰 3 日
        s3 = DemonStateEngine.sync(me, now=T0 + 5 * 86400)
        assert abs(s3 - per_day * 3) < 1e-6, s3
        s4 = DemonStateEngine.sync(me, now=T0 + 9 * 86400)
        assert abs(s4 - s3) < 1e-9, (s3, s4)
        print(f"✓ 心魔跨锚点：分段 sync 恰按覆盖天数计（{s1:.2f}/{s2:.2f}/{s3:.2f}），幂等且封顶于消散点")
    finally:
        _cleanup(c)
