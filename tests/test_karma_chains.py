"""AI 天道事件链（karma-event-chains）后端测试：K-1~K-18（后端负责条目）。

Spec：docs/compose/spec/karma-event-chains.md §12。
隔离方式：沿用共享 DB + 唯一前缀（kc_ 玩家 / npc_kc_ NPC），
链行在每条用例结束时按 player_id 删除，自造角色收尾置死。
时间口径：1 游戏日 = SECONDS_PER_GAME_DAY = 240 现实秒；注入 now 推进。
"""
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

import pytest

from config import (
    EVENT_EFFECT_CAPS,
    SECONDS_PER_GAME_DAY,
    KARMA_CHAIN_DAILY_STONES_MAX,
    KARMA_CHAIN_EFFECT_CAPS,
)
from core.clock import WorldClock
from core.models import CharacterStatus
from storage.db import (
    init_db,
    CharacterRepository,
    KarmaChainRepository,
    KarmaLinkRepository,
    NpcAgendaRepository,
    NpcMindRepository,
    PromiseRepository,
)
from core.karma_chains import KarmaChain, KarmaChainEngine
from core.npc_mind import shift_attitude, attitude_toward
from core.collusion import ensure_link
from core.promises import PromiseEngine, PromiseStatus
from core.bounty import BountyEngine, Bounty, BountyStatus
from core import rumors

init_db()

DAY = SECONDS_PER_GAME_DAY
LOC = "青云坊市客栈"
LOC_WILD = "落霞山灵泉"


def _tag():
    return uuid.uuid4().hex[:6]


def _player(name="链客", location=LOC, old=False):
    c = WorldClock.create_new_character(f"kc_{_tag()}_{name}", f"{name}{_tag()}")
    c.location = location
    if old:
        c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def _npc(name="链翁", location=LOC, old=False, sect=None):
    c = WorldClock.create_new_character(f"npc_kc_{_tag()}_{name}", f"{name}{_tag()}")
    c.location = location
    c.sect = sect
    if old:
        c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def _chains(player_id=None, counterparty_id=None):
    out = KarmaChainRepository.list_all()
    if player_id is not None:
        out = [c for c in out if c.player_id == player_id]
    if counterparty_id is not None:
        out = [c for c in out if c.counterparty_id == counterparty_id]
    return out


def _active(player_id):
    return [c for c in _chains(player_id) if c.status in ("latent", "fermenting")]


def _cleanup(*chars):
    for c in chars:
        if c is None:
            continue
        for ch in KarmaChainRepository.list_all():
            if c.id in (ch.player_id, ch.counterparty_id, ch.delivery_actor_id):
                KarmaChainRepository.delete(ch.id)
        for p in PromiseRepository.list_all():
            if c.id in (p.promiser_id, p.promisee_id):
                PromiseRepository.delete(p.id)
        c.status = CharacterStatus.DEAD
        CharacterRepository.save(c)


def _set_att(npc, other_id, value):
    NpcMindRepository.set_attitude(npc.id, other_id, value)


def _att(npc_id, other_id):
    return attitude_toward(CharacterRepository.get_by_id(npc_id), other_id)["value"]


def _origin(player, npc, kind="en", polarity=1, strength=3, key=None, t0=None, ref=""):
    return KarmaChainEngine.note_origin(
        player, npc, kind=kind, polarity=polarity, strength=strength,
        chain_key=key or f"test:{uuid.uuid4().hex[:10]}",
        origin_summary="测试起因", source_ref=ref or f"test:{uuid.uuid4().hex[:8]}",
        now=t0,
    )


def _today_midday():
    """当日 UTC 正午时间戳：保证 +1 游戏日发酵/到期仍在同一现实日（预算口径）。"""
    return (int(time.time()) // 86400) * 86400 + 43200.0


def _rumor_hits(name: str):
    """直读传闻 raw pool（不用 list_rumors 展示口径：池满时按 heat/时间
    排序会把较早注入时刻的传闻挤出前 30，属读法脆弱而非未写入）。"""
    return [r for r in rumors._load() if name in (r.get("text") or "")]


# ---------------- K-1 S1 阈值与迟滞 ----------------

def test_att_cross_thresholds():
    p, npc = _player("恩客"), _npc("恩翁")
    t0 = time.time()
    _set_att(npc, p.id, 59)
    shift_attitude(npc, p.id, 1, reason="赠礼")  # 59→60 跨恩线
    chains = _chains(p.id, npc.id)
    assert len(chains) == 1 and chains[0].kind == "en" and chains[0].strength == 3
    assert chains[0].polarity == 1 and chains[0].status == "latent"
    # 段内小步进（60→69→70）不再起新链
    shift_attitude(npc, p.id, 9, reason="交谈")
    shift_attitude(npc, p.id, 1, reason="交谈")
    assert len(_chains(p.id, npc.id)) == 1
    # 跌回 50 后再跨 60：active 存在 → 续链 +1，不新建
    shift_attitude(npc, p.id, -20, reason="变故")
    shift_attitude(npc, p.id, 10, reason="再施恩")
    chains = _chains(p.id, npc.id)
    assert len(chains) == 1 and chains[0].strength == 4
    # 仇向跨阈（另一对）
    p2, npc2 = _player("仇客"), _npc("仇翁")
    _set_att(npc2, p2.id, -59)
    shift_attitude(npc2, p2.id, -1, reason="结怨")
    chains2 = _chains(p2.id, npc2.id)
    assert len(chains2) == 1 and chains2[0].kind == "chou" and chains2[0].strength == 3
    assert chains2[0].polarity == -1
    # 未跨阈的小步进不起链
    p3, npc3 = _player("路人"), _npc("路翁")
    _set_att(npc3, p3.id, 50)
    shift_attitude(npc3, p3.id, 5, reason="交谈")
    assert _chains(p3.id, npc3.id) == []
    _cleanup(p, npc, p2, npc2, p3, npc3)
    print("✓ K-1 S1 跨 ±60 起链、迟滞、active 续链")


def test_chain_attitude_no_self_trigger():
    p, npc = _player("自激客"), _npc("自激翁")
    _set_att(npc, p.id, -59)
    shift_attitude(npc, p.id, -5, reason="因果链·报复")  # 跨 -60 但为链自身落账
    assert _att(npc.id, p.id) == -64
    assert _chains(p.id, npc.id) == []
    _cleanup(p, npc)
    print("✓ K-2 reason=因果链 前缀防自激")


# ---------------- K-3 S2/S2b 边达阈与出师 ----------------

def test_link_threshold_and_graduation():
    p, npc = _player("积怨客"), _npc("积怨翁")
    link = ensure_link(p, npc, "仇", note="初怨")
    assert link.strength == 1 and _chains(p.id, npc.id) == []
    ensure_link(p, npc, "仇", note="再怨")
    assert _chains(p.id, npc.id) == []
    link = ensure_link(p, npc, "仇", note="三怨")  # strength 达 3 → 起链
    chains = _chains(p.id, npc.id)
    assert len(chains) == 1 and chains[0].kind == "chou" and chains[0].strength == 3
    link = ensure_link(p, npc, "仇", note="四怨")  # 再自增 → 只续链 +1
    chains = _chains(p.id, npc.id)
    assert len(chains) == 1 and chains[0].strength == 4
    # 出师改型：师徒边（弟子=玩家 tier1，师父=NPC tier3）strength≥3
    from core.bounty import KarmaLink
    from core import social_bonds

    disc = _player("弟子")
    mast = _npc("师父")
    mast.realm.tier = 3
    CharacterRepository.save(mast)
    grad_link = KarmaLink(
        a_id=disc.id, a_name=disc.name, b_id=mast.id, b_name=mast.name,
        link_type="师徒", strength=3, note="师徒", created_at=time.time(),
    )
    KarmaLinkRepository.save(grad_link)
    res = social_bonds.graduate(disc)
    assert res["success"], res
    saved = [l for l in KarmaLinkRepository.list_all() if l.id == grad_link.id]
    assert saved and saved[0].link_type == "恩"
    gchains = _chains(disc.id, mast.id)
    assert len(gchains) == 1 and gchains[0].kind == "en" and gchains[0].strength == 3
    # 同 link 键重放钩子不双起
    KarmaChainEngine.note_graduation(saved[0], disc, mast)
    assert len(_chains(disc.id, mast.id)) == 1
    KarmaLinkRepository.delete(grad_link.id) if hasattr(KarmaLinkRepository, "delete") else None
    _cleanup(p, npc, disc, mast)
    print("✓ K-3 S2 边达阈起链/续链 + S2b 出师转恩同键不双起")


# ---------------- K-4 S3 诺言终态 ----------------

def test_promise_settle_starts_chain():
    t0 = time.time()
    # KEPT → nuo+ strength 2
    p, npc = _player("践诺客"), _npc("践诺翁")
    pr = PromiseEngine.make_promise(p, npc, "quest", now=t0)["promise"]
    msg = PromiseEngine.note_quest_completed(p, now=t0 + 10)
    assert msg and "践诺" in msg
    chains = _chains(p.id, npc.id)
    assert len(chains) == 1 and chains[0].kind == "nuo"
    assert chains[0].polarity == 1 and chains[0].strength == 2
    assert chains[0].chain_key == f"promise:{pr.id}"
    # BROKEN → nuo- strength 3
    p2, npc2 = _player("背诺客"), _npc("背诺翁")
    pr2 = PromiseEngine.make_promise(p2, npc2, "arrive", "落霞", now=t0)["promise"]
    assert PromiseEngine.settle_due(p2, now=t0 + 3 * 86400.0 + 1)
    got = [x for x in PromiseRepository.list_all() if x.id == pr2.id][0]
    assert got.status == PromiseStatus.BROKEN
    chains2 = _chains(p2.id, npc2.id)
    assert len(chains2) == 1 and chains2[0].kind == "nuo"
    assert chains2[0].polarity == -1 and chains2[0].strength == 3
    # DISSOLVED（死亡消散）不起链
    p3, npc3 = _player("散诺客"), _npc("散诺翁")
    PromiseEngine.make_promise(p3, npc3, "quest", now=t0)
    PromiseEngine.on_owner_death(p3, now=t0 + 5)
    assert _chains(p3.id, npc3.id) == []
    # 玩家受诺（promisee 非 NPC）不起链
    p4, p5 = _player("立诺者"), _player("受诺者")
    pr4 = PromiseEngine.make_promise(p4, p5, "quest", now=t0)["promise"]
    assert PromiseEngine.accept(p5, now=t0 + 5)["success"]
    assert PromiseEngine.break_promise(p4, now=t0 + 6)["success"]
    assert _chains(p4.id, p5.id) == []
    _cleanup(p, npc, p2, npc2, p3, npc3, p4, p5)
    print("✓ K-4 S3 KEPT/BROKEN 起诺链，DISSOLVED/玩家受诺不起")


# ---------------- K-5 S4/S5 击杀合流 ----------------

def test_kill_and_bounty_single_chain(monkeypatch):
    import core.combat_fate as cf

    monkeypatch.setattr(cf, "ai_ready", lambda: True)
    monkeypatch.setattr(
        cf.AIGateway, "judge_combat",
        staticmethod(lambda a, d, rule_hint=0.5, facts=None, context="": {
            "outcome": "kill", "narrative": "一剑封喉。", "effects": {}, "source": "test",
        }),
    )
    killer = _player("猎手", location=LOC_WILD, old=True)
    victim = _npc("凶徒", location=LOC_WILD, old=True)
    issuer = _player("苦主")
    bounty = BountyEngine.place_bounty(issuer, victim, 100, reason="血仇")["bounty"]
    res = cf.CombatFateEngine.resolve_ambush(killer, victim)
    assert res["success"] and res["outcome"] == "kill", res
    CharacterRepository.save(killer)
    CharacterRepository.save(victim)
    chains = [c for c in _chains(killer.id, victim.id) if c.kind == "xue"]
    assert len(chains) == 1 and chains[0].strength == 5  # 双点（resolve_ambush+cascade）合流
    assert chains[0].chain_key == f"kill:{victim.id}"
    # CLI 口径结赏：只续链 +1，节点含 bounty source_ref
    pay = BountyEngine.settle_on_kill(killer, victim, [bounty])
    assert pay["bounty_paid"] is True
    chains = [c for c in _chains(killer.id, victim.id) if c.kind == "xue"]
    assert len(chains) == 1 and chains[0].strength == 6
    refs = [n.source_ref for n in chains[0].nodes]
    assert any(bounty.id in r for r in refs), refs
    # 重复结赏不再加强
    pay2 = BountyEngine.settle_on_kill(killer, victim, [bounty])
    assert pay2["bounty_paid"] is False
    chains = [c for c in _chains(killer.id, victim.id) if c.kind == "xue"]
    assert chains[0].strength == 6
    _cleanup(killer, victim, issuer)
    # R1/MF-2 无链不新建：另一对无任何 active 链，单独走 settle_on_kill
    # 结赏路径（paid）→ 链总数为 0、note_bounty_settled 返回 None
    killer2 = _player("赏客")
    victim2 = _npc("赏徒", location=LOC_WILD, old=True)
    issuer2 = _player("赏主")
    bounty2 = BountyEngine.place_bounty(issuer2, victim2, 100, reason="悬赏")["bounty"]
    assert KarmaChainEngine.note_bounty_settled(killer2, victim2, [bounty2]) is None
    pay3 = BountyEngine.settle_on_kill(killer2, victim2, [bounty2])
    assert pay3["bounty_paid"] is True
    assert _chains(killer2.id, victim2.id) == []
    _cleanup(killer2, victim2, issuer2)
    print("✓ K-5 S4 双点合流一条血仇链 + S5 结赏续链幂等 + 无链不新建（MF-2）")


# ---------------- K-1A 真实赠礼路径成本（R1/MF-1） ----------------

def test_real_gift_path_cost_to_en_chain():
    """K-1A 真实路径：只许走 chat_actions.do_gift / do_trade 人情支经营态度
    （禁止 set_attitude/shift_attitude 直设冒充经营段）。

    (i) 最省策略（1 灵石连赠、人情 1 灵石连投）累计实付 <300 时态度 <60、无恩链；
    (ii) 6 笔 × 50 灵石后态度恰 60 且恩链起链（总成本恰 300，下限紧而可达）；
    (iii) 恩链兑现净收益 = 灵石增支（≤60）− 实付（300）≤ −240 ≤ 0。
    """
    from core import chat_actions as CA

    t0 = _today_midday()
    # (i) 最省策略：交替 1 灵石赠礼与 1 灵石人情，累计 299 灵石仍不到 60
    p, npc = _player("省客"), _npc("省翁")
    p.spirit_stones = 100000
    CharacterRepository.save(p)
    spent = 0
    for i in range(299):
        if i % 2 == 0:
            out = CA.do_gift(p, npc, "", 1)
        else:
            out = CA.do_trade(p, npc, "", 1)
        assert out["ok"] is True, out
        assert out["attitude_delta"] == 0, out  # 1 灵石计价恒 0（§8.3.1）
        spent += 1
    assert spent == 299
    assert _att(npc.id, p.id) == 0 and _att(npc.id, p.id) < 60
    assert _chains(p.id, npc.id) == []
    assert CharacterRepository.get_by_id(p.id).spirit_stones == 100000 - 299
    _cleanup(p, npc)
    # (ii) 6 笔 × 50 灵石：每笔 +10（不触 cap 浪费），态度恰 60、恩链起链
    p2, npc2 = _player("经营客"), _npc("经营翁")
    p2.spirit_stones = 100000
    CharacterRepository.save(p2)
    total_paid = 0
    for _ in range(6):
        out = CA.do_gift(p2, npc2, "", 50)
        assert out["ok"] is True and out["attitude_delta"] == 10, out
        total_paid += 50
    assert total_paid == 300
    assert _att(npc2.id, p2.id) == 60
    chains = [c for c in _chains(p2.id, npc2.id) if c.kind == "en"]
    assert len(chains) == 1 and chains[0].status == "latent"
    chain = chains[0]
    # 起链时刻对齐回填口径：真实经营发生在现实当下，链 created_at≈now；
    # 兑现推进以链自身时刻为基准注入 now（单调），不改任何落账时刻。
    created = chain.created_at
    stones_before = CharacterRepository.get_by_id(p2.id).spirit_stones
    KarmaChainEngine.advance_for(p2, now=created + 9 * DAY)  # en duration 9 日
    got = KarmaChainRepository.get(chain.id)
    assert got.status == "resolved", got.resolution
    eff = got.resolution.get("effects") or {}
    stones_gain = int(eff.get("stones_gain") or 0)
    assert stones_gain <= 60
    # (iii) 净收益 ≤ −240（修为支时灵石增支计 0，净收益更低，断言同立）
    net = stones_gain - total_paid
    assert net <= -240 and net <= 0, net
    if stones_gain:
        assert CharacterRepository.get_by_id(p2.id).spirit_stones == stones_before + stones_gain
    _cleanup(p2, npc2)
    print("✓ K-1A 真实 do_gift/人情路径：<300 不起链、恰 300 起恩链、净收益 ≤ −240")


# ---------------- K-6 发酵迁移 ----------------

def test_ferment_transition_and_rumor():
    p, npc = _player("发酵客"), _npc("发酵翁")
    t0 = _today_midday()
    ch = _origin(p, npc, t0=t0)
    assert ch is not None and ch.status == "latent"
    before = _rumor_hits(npc.name)
    KarmaChainEngine.advance_for(p, now=t0 + 4 * DAY)  # 未到 ferment_at(4.5 日)
    got = KarmaChainRepository.get(ch.id)
    assert got.status == "latent"
    assert _rumor_hits(npc.name) == before
    KarmaChainEngine.advance_for(p, now=t0 + 5 * DAY)  # 过 ferment_at
    got = KarmaChainRepository.get(ch.id)
    assert got.status == "fermenting"
    after = _rumor_hits(npc.name)
    assert len(after) == len(before) + 1
    KarmaChainEngine.advance_for(p, now=t0 + 5 * DAY)  # 重复推进不重复发传闻
    assert len(_rumor_hits(npc.name)) == len(after)
    # 血仇链发酵预选兑现者 + 议程转寻仇
    killer = _player("血手")
    victim = _npc("亡者", sect="青云宗")
    avenger = _npc("同门", sect="青云宗")
    _set_att(avenger, killer.id, -80)
    victim.status = CharacterStatus.DEAD
    CharacterRepository.save(victim)
    xue = KarmaChainEngine.note_kill(killer, victim, now=t0)
    assert xue is not None
    KarmaChainEngine.advance_for(killer, now=t0 + 11 * DAY)  # xue ferment_at=10.5 日
    got = KarmaChainRepository.get(xue.id)
    assert got.status == "fermenting" and got.delivery_actor_id == avenger.id
    ag = NpcAgendaRepository.get(avenger.id)
    assert ag and ag["agenda_type"] == "revenge" and killer.name in (ag.get("target_hint") or "")
    _cleanup(p, npc, killer, victim, avenger)
    print("✓ K-6 发酵迁移/传闻一次/血仇预选兑现者并置寻仇议程")


# ---------------- K-7 到期兑现与窗口 ----------------

def test_mature_resolve_and_expire():
    p, npc = _player("兑现客"), _npc("兑现翁")
    t0 = _today_midday()
    ch = _origin(p, npc, strength=4, t0=t0)  # en, duration 9 日
    stones0 = CharacterRepository.get_by_id(p.id).spirit_stones
    KarmaChainEngine.advance_for(p, now=t0 + 9 * DAY)
    got = KarmaChainRepository.get(ch.id)
    assert got.status == "resolved" and got.resolution.get("outcome") == "repaid"
    eff = got.resolution.get("effects") or {}
    assert eff and "lifespan" not in eff
    now_p = CharacterRepository.get_by_id(p.id)
    if eff.get("stones_gain"):
        assert now_p.spirit_stones == stones0 + eff["stones_gain"]
    if eff.get("exp_gain"):
        assert now_p.realm.current_exp == eff["exp_gain"]
    assert _att(npc.id, p.id) == 5  # 报恩态度 +5
    # 窗口逾期 → 消散且零落账
    p2, npc2 = _player("逾期客"), _npc("逾期翁")
    ch2 = _origin(p2, npc2, kind="chou", polarity=-1, strength=3, t0=t0)
    KarmaChainEngine.advance_for(p2, now=t0 + 8 * DAY)  # chou ferment_at=7.5 日 → 发酵
    assert KarmaChainRepository.get(ch2.id).status == "fermenting"
    snap = CharacterRepository.get_by_id(p2.id)
    snap_vals = (snap.spirit_stones, snap.realm.current_exp, snap.karma.sin_value,
                 snap.karma.merit_value, snap.karma.dao_heart)
    KarmaChainEngine.advance_for(p2, now=t0 + (15 + 14 + 1) * DAY)  # 过 deadline
    got2 = KarmaChainRepository.get(ch2.id)
    assert got2.status == "dissipated"
    assert got2.budget_deferred is False  # 未被预算暂缓（R1/MF-3 修正后 K-7 口径）
    assert (got2.resolution or {}).get("reason") == "expired"
    after = CharacterRepository.get_by_id(p2.id)
    assert (after.spirit_stones, after.realm.current_exp, after.karma.sin_value,
            after.karma.merit_value, after.karma.dao_heart) == snap_vals
    _cleanup(p, npc, p2, npc2)
    print("✓ K-7 到期兑现落账 + 窗口逾期消散零落账")


# ---------------- K-8 公式与子顶 ----------------

def test_effects_formula_and_caps():
    def mk(kind, polarity, strength):
        return KarmaChain(
            kind=kind, polarity=polarity, strength=strength,
            player_id="p", counterparty_id="n", created_at=1000.0,
        )

    cases = [
        ("en", 1, 3), ("en", 1, 5), ("chou", -1, 4),
        ("nuo", 1, 2), ("nuo", -1, 3), ("xue", -1, 5),
    ]
    for kind, pol, s in cases:
        ch = mk(kind, pol, s)
        eff = KarmaChainEngine.compute_effects(ch, now=1000.0)
        assert "lifespan" not in eff or eff.get("lifespan") == 0
        for k, v in eff.items():
            cap = KARMA_CHAIN_EFFECT_CAPS[k]
            assert abs(v) <= cap, (kind, k, v, cap)
            if k == "stones_gain":
                assert v <= EVENT_EFFECT_CAPS["stones_gain"]
            if k == "stones_lose":
                assert v <= EVENT_EFFECT_CAPS["stones_lose"]
            if k == "exp_gain":
                assert v <= EVENT_EFFECT_CAPS["exp"]
            if k == "sin":
                assert v <= EVENT_EFFECT_CAPS["sin"]
            if k == "merit":
                assert v <= EVENT_EFFECT_CAPS["merit"]
        # 数值支 XOR：灵石支与修为支不同时出现
        assert not (("stones_gain" in eff or "stones_lose" in eff)
                    and ("exp_gain" in eff or "exp_lose" in eff)), (kind, eff)
    # 具体公式（eff=strength，无衰减）
    _en_chain = mk("en", 1, 3)
    en3 = KarmaChainEngine.compute_effects(_en_chain, now=1000.0)
    branch = KarmaChainEngine.branch_for(_en_chain)
    if branch == "stones":
        assert en3["stones_gain"] == 45
    else:
        assert en3["exp_gain"] == 60
    assert en3["attitude"] == 5
    nuo_kept = KarmaChainEngine.compute_effects(mk("nuo", 1, 2), now=1000.0)
    assert nuo_kept["merit"] == 5 and nuo_kept["attitude"] == 5
    nuo_broken = KarmaChainEngine.compute_effects(mk("nuo", -1, 3), now=1000.0)
    assert nuo_broken == {"sin": 5, "attitude": -12}
    xue = KarmaChainEngine.compute_effects(mk("xue", -1, 5), now=1000.0)
    assert xue == {"sin": 10, "attitude": -20}
    chou = KarmaChainEngine.compute_effects(mk("chou", -1, 4), now=1000.0)
    assert chou["attitude"] == -18 and chou["dao_heart"] == -3
    # flipped → 无数值
    flipped = mk("chou", -1, 4)
    flipped.flipped = True
    assert KarmaChainEngine.compute_effects(flipped, now=1000.0) == {}
    print("✓ K-8 五 kind 公式/子顶/XOR 支/flipped 空效")


def test_effects_exp_gain_actual_at_max_exp():
    """K-8 注脚（R1/OBS-2，§4.4）：exp 兑现落账钳 max_exp，
    resolution.effects["exp_gain"] 记实际落账值而非公式名义值。"""
    t0 = _today_midday()
    # 选一条走修为支（hash 定支）的链 id
    cand = None
    for i in range(200):
        probe = KarmaChain(id=f"expprobe{i}", kind="en", polarity=1, strength=3)
        if KarmaChainEngine.branch_for(probe) == "exp":
            cand = probe.id
            break
    assert cand is not None
    # 情形一：current_exp 距 max_exp 只剩 10 < 名义 exp_gain（en strength3 → 60）
    p, npc = _player("满格客"), _npc("满格翁")
    fresh = CharacterRepository.get_by_id(p.id)
    max_exp = fresh.realm.max_exp
    fresh.realm.current_exp = max_exp - 10
    CharacterRepository.save(fresh)
    chain = KarmaChain(
        id=cand, kind="en", polarity=1, strength=3,
        player_id=p.id, player_name=p.name,
        counterparty_id=npc.id, counterparty_name=npc.name,
        delivery_actor_id=npc.id, delivery_actor_name=npc.name,
        chain_key=f"test:expmax:{uuid.uuid4().hex[:8]}", status="fermenting",
        origin_summary="满格测试", created_at=t0 - 9 * DAY,
        ferment_at=t0 - 5 * DAY, mature_at=t0 - DAY, deadline_at=t0 + 14 * DAY,
    )
    KarmaChainRepository.save(chain)
    assert KarmaChainEngine._resolve(KarmaChainRepository.get(cand), t0) is True
    got = KarmaChainRepository.get(cand)
    assert got.status == "resolved"
    assert (got.resolution.get("effects") or {}).get("exp_gain") == 10, got.resolution
    assert CharacterRepository.get_by_id(p.id).realm.current_exp == max_exp
    # 情形二：已满格 → exp_gain 实际 0，effects 省略该键，落账仍为 max_exp
    p2, npc2 = _player("溢格客"), _npc("溢格翁")
    fresh2 = CharacterRepository.get_by_id(p2.id)
    fresh2.realm.current_exp = fresh2.realm.max_exp
    CharacterRepository.save(fresh2)
    chain2 = KarmaChain(
        id=cand, kind="en", polarity=1, strength=3,
        player_id=p2.id, player_name=p2.name,
        counterparty_id=npc2.id, counterparty_name=npc2.name,
        delivery_actor_id=npc2.id, delivery_actor_name=npc2.name,
        chain_key=f"test:expfull:{uuid.uuid4().hex[:8]}", status="fermenting",
        origin_summary="溢格测试", created_at=t0 - 9 * DAY,
        ferment_at=t0 - 5 * DAY, mature_at=t0 - DAY, deadline_at=t0 + 14 * DAY,
    )
    KarmaChainRepository.save(chain2)
    assert KarmaChainEngine._resolve(KarmaChainRepository.get(cand), t0) is True
    got2 = KarmaChainRepository.get(cand)
    assert "exp_gain" not in (got2.resolution.get("effects") or {}), got2.resolution
    assert CharacterRepository.get_by_id(p2.id).realm.current_exp == fresh2.realm.max_exp
    _cleanup(p, npc, p2, npc2)
    print("✓ K-8 注脚 exp 落账钳 max_exp、effects 记实际值（OBS-2）")


def test_effects_never_touch_lifespan():
    t0 = _today_midday()
    specs = [
        ("en", 1, 3, 9), ("chou", -1, 3, 15), ("nuo", 1, 2, 6), ("nuo", -1, 3, 9),
    ]
    for kind, pol, s, dur in specs:
        p, npc = _player(f"寿{kind}{pol}"), _npc(f"寿翁{kind}{pol}")
        ch = _origin(p, npc, kind=kind, polarity=pol, strength=s, t0=t0)
        before = CharacterRepository.get_by_id(p.id).lifespan
        KarmaChainEngine.advance_for(p, now=t0 + dur * DAY)
        got = KarmaChainRepository.get(ch.id)
        assert got.status == "resolved", (kind, got.status, got.resolution)
        after = CharacterRepository.get_by_id(p.id).lifespan
        assert (after.death_timestamp, after.birth_base, after.accumulated_gain) == \
               (before.death_timestamp, before.birth_base, before.accumulated_gain)
        _cleanup(p, npc)
    # 血仇（需兑现者）
    killer = _player("寿血手")
    victim = _npc("寿亡者", sect="青云宗")
    avenger = _npc("寿同门", sect="青云宗")
    victim.status = CharacterStatus.DEAD
    CharacterRepository.save(victim)
    xue = KarmaChainEngine.note_kill(killer, victim, now=t0)
    before = CharacterRepository.get_by_id(killer.id).lifespan
    KarmaChainEngine.advance_for(killer, now=t0 + 21 * DAY)
    assert KarmaChainRepository.get(xue.id).status == "resolved"
    after = CharacterRepository.get_by_id(killer.id).lifespan
    assert (after.death_timestamp, after.birth_base, after.accumulated_gain) == \
           (before.death_timestamp, before.birth_base, before.accumulated_gain)
    _cleanup(killer, victim, avenger)
    print("✓ K-9 全 kind 兑现寿元三字段逐值不变")


# ---------------- K-10 每日预算 ----------------

def test_daily_resolve_budget():
    """K-10（R1/MF-3 改写）：每日预算 + 暂缓豁免，全程只以单调递增的注入
    now 走正规入口（advance_for）推进；禁止回拨/改写任何落账时刻。"""
    p = _player("预算客")
    npcs = [_npc(f"预算翁{i}") for i in range(3)]
    t0 = _today_midday()  # 当日中段起链：同日内可大幅推进游戏日而不跨日界
    chains = [_origin(p, n, strength=3, t0=t0) for n in npcs]
    assert all(chains)
    # (i) 到期日推进：只兑现 2 条，第 3 条置 budget_deferred 保持 fermenting
    for _ in range(3):
        KarmaChainEngine.advance_for(p, now=t0 + 9 * DAY)
    states = [KarmaChainRepository.get(c.id) for c in chains]
    assert [c.status for c in states].count("resolved") == 2, [c.status for c in states]
    deferred = [c for c in states if c.status == "fermenting"]
    assert len(deferred) == 1, [c.status for c in states]
    deferred = deferred[0]
    assert deferred.budget_deferred is True
    stones_today = sum(
        (c.resolution.get("effects") or {}).get("stones_gain", 0) for c in states
    )
    assert stones_today <= KARMA_CHAIN_DAILY_STONES_MAX
    # (ii) 同一现实日内推过 deadline（+23 游戏日）与链龄 90 游戏日硬顶
    #（+150 游戏日 = +36000 现实秒，中段起链仍在同一现实日内）：豁免生效，
    # 第 3 条仍为 fermenting，不断言 expired/lifetime_cap 消散。
    t1 = t0 + 150 * DAY
    assert int(t1 // 86400) == int(t0 // 86400)  # 同一现实日（预算未重置）
    assert t1 > deferred.deadline_at
    assert t1 - deferred.created_at > 90 * DAY
    KarmaChainEngine.advance_for(p, now=t1)
    got = KarmaChainRepository.get(deferred.id)
    assert got.status == "fermenting" and got.budget_deferred is True, got.resolution
    # (iii) now 推过下一现实日界后再推进：第 3 条兑现为 resolved、只落一次账
    t2 = (int(t0 // 86400) + 1) * 86400.0 + 3600.0
    assert t2 > t1  # now 单调递增
    snap = CharacterRepository.get_by_id(p.id)
    snap_vals = (snap.spirit_stones, snap.realm.current_exp)
    KarmaChainEngine.advance_for(p, now=t2)
    got = KarmaChainRepository.get(deferred.id)
    assert got.status == "resolved", got.resolution
    eff = got.resolution.get("effects") or {}
    now_p = CharacterRepository.get_by_id(p.id)
    assert now_p.spirit_stones == snap_vals[0] + int(eff.get("stones_gain") or 0)
    assert now_p.realm.current_exp == snap_vals[1] + int(eff.get("exp_gain") or 0)
    assert _att(deferred.counterparty_id, p.id) == 5  # 报恩态度只落一次
    # 再推进不重复落账
    KarmaChainEngine.advance_for(p, now=t2 + DAY)
    now_p2 = CharacterRepository.get_by_id(p.id)
    assert (now_p2.spirit_stones, now_p2.realm.current_exp) == \
           (now_p.spirit_stones, now_p.realm.current_exp)
    _cleanup(p, *npcs)
    print("✓ K-10 每日兑现 ≤2、暂缓置标记、跨窗/硬顶豁免、跨日界后兑现（MF-3）")


# ---------------- K-11/K-12 幂等重放 ----------------

def test_resolve_idempotent_replay():
    p, npc = _player("重放客"), _npc("重放翁")
    t0 = _today_midday()
    ch = _origin(p, npc, strength=3, t0=t0)
    KarmaChainEngine.advance_for(p, now=t0 + 9 * DAY)
    got = KarmaChainRepository.get(ch.id)
    assert got.status == "resolved"
    snap_p = CharacterRepository.get_by_id(p.id)
    snap = (snap_p.spirit_stones, snap_p.realm.current_exp, snap_p.karma.merit_value,
            snap_p.karma.sin_value, _att(npc.id, p.id))
    resolution = dict(got.resolution)
    # 重复推进/重复结算：逐值不变
    KarmaChainEngine.tick_world(now=t0 + 10 * DAY)
    KarmaChainEngine.advance_for(p, now=t0 + 10 * DAY)
    assert KarmaChainEngine._resolve(KarmaChainRepository.get(ch.id), t0 + 10 * DAY) is False
    now_p = CharacterRepository.get_by_id(p.id)
    assert (now_p.spirit_stones, now_p.realm.current_exp, now_p.karma.merit_value,
            now_p.karma.sin_value, _att(npc.id, p.id)) == snap
    assert KarmaChainRepository.get(ch.id).resolution == resolution
    # 模拟「锚已落、效未发」：手工置 resolved 但不落账，再推进不补发
    p2, npc2 = _player("锚客"), _npc("锚翁")
    ch2 = _origin(p2, npc2, strength=3, t0=t0)
    ghost = KarmaChainRepository.get(ch2.id)
    ghost.status = "resolved"
    ghost.resolved_at = t0 + 9 * DAY
    ghost.resolution = {"outcome": "repaid", "effects": {"stones_gain": 45}, "narrative": "锚"}
    KarmaChainRepository.save(ghost)
    stones0 = CharacterRepository.get_by_id(p2.id).spirit_stones
    KarmaChainEngine.advance_for(p2, now=t0 + 10 * DAY)
    KarmaChainEngine.tick_world(now=t0 + 10 * DAY)
    assert CharacterRepository.get_by_id(p2.id).spirit_stones == stones0
    _cleanup(p, npc, p2, npc2)
    print("✓ K-11 终态锚重放不双发、锚后效失不补发")


def test_origin_hooks_replay():
    t0 = time.time()
    # S3：_settle 重放 + 钩子直调重放 → 恒一条
    p, npc = _player("诺放客"), _npc("诺放翁")
    pr = PromiseEngine.make_promise(p, npc, "quest", now=t0)["promise"]
    PromiseEngine.note_quest_completed(p, now=t0 + 5)
    from core.promises import Promise as _P
    settled = [x for x in PromiseRepository.list_all() if x.id == pr.id][0]
    assert PromiseEngine._settle(settled, PromiseStatus.KEPT, "重放", t0 + 6) is False
    KarmaChainEngine.note_promise_settled(settled, "KEPT", now=t0 + 7)
    KarmaChainEngine.note_promise_settled(settled, PromiseStatus.KEPT, now=t0 + 8)
    assert len(_chains(p.id, npc.id)) == 1
    # S4：双点各调两次 → 恒一条
    killer = _player("杀放客")
    victim = _npc("杀放者")
    victim.status = CharacterStatus.DEAD
    CharacterRepository.save(victim)
    for _ in range(2):
        KarmaChainEngine.note_kill(killer, victim, now=t0)
        from core.jianghu_sim import JianghuSimulator
        JianghuSimulator.cascade_kill(killer, victim, location=LOC, loot=0)
    assert len([c for c in _chains(killer.id, victim.id) if c.kind == "xue"]) == 1
    _cleanup(p, npc, killer, victim)
    print("✓ K-12 S3/S4 起链重放恒一条")


# ---------------- K-13 上限与冷却 ----------------

def test_caps_and_cooldowns():
    t0 = _today_midday()
    # 单玩家 active 满 4
    p = _player("满链客")
    ns = [_npc(f"满链翁{i}") for i in range(5)]
    made = []
    # 错开 created_at 规避单 NPC 间隔（不同 NPC 本互不影响），逐个起
    for i, n in enumerate(ns[:4]):
        made.append(_origin(p, n, t0=t0 + i * 11 * DAY))
    assert all(made) and len(_active(p.id)) == 4
    assert _origin(p, ns[4], t0=t0 + 50 * DAY) is None
    assert len(_active(p.id)) == 4
    _cleanup(p, *ns)
    # 单 NPC 对象满 2（跨玩家）：直存两条 active（旧时刻），第三玩家新起被拒
    npc = _npc("香饽翁")
    pa, pb, pc = _player("甲客"), _player("乙客"), _player("丙客")
    for pl in (pa, pb):
        KarmaChainRepository.save(KarmaChain(
            kind="en", polarity=1, strength=3, player_id=pl.id, player_name=pl.name,
            counterparty_id=npc.id, counterparty_name=npc.name,
            chain_key=f"seed:{pl.id}", status="latent", created_at=t0 - 40 * DAY,
            ferment_at=t0, mature_at=t0 + 9 * DAY, deadline_at=t0 + 23 * DAY,
        ))
    assert _origin(pc, npc, t0=t0) is None  # 对象 active 已满 2
    _cleanup(pa, pb, pc, npc)
    # 同对同 kind 终态冷却 30 游戏日：29 日拒、31 日可
    p2, npc2 = _player("冷却客"), _npc("冷却翁")
    KarmaChainRepository.save(KarmaChain(
        kind="en", polarity=1, strength=3, player_id=p2.id, player_name=p2.name,
        counterparty_id=npc2.id, counterparty_name=npc2.name,
        chain_key="att:seed:en:1", status="resolved", created_at=t0 - 9 * DAY,
        ferment_at=t0 - 5 * DAY, mature_at=t0, deadline_at=t0 + 14 * DAY,
        resolved_at=t0, resolution={"outcome": "repaid", "effects": {}},
    ))
    assert KarmaChainEngine.note_attitude_cross(npc2, p2.id, 50, 65, now=t0 + 29 * DAY) is None
    ok = KarmaChainEngine.note_attitude_cross(npc2, p2.id, 50, 65, now=t0 + 31 * DAY)
    assert ok is not None and ok.kind == "en"
    _cleanup(p2, npc2)
    # 同 NPC 新起链间隔 10 游戏日
    p3, p4 = _player("先到客"), _player("后到客")
    npc3 = _npc("独苗翁")
    first = _origin(p3, npc3, t0=t0)
    assert first is not None
    assert _origin(p4, npc3, t0=t0 + 5 * DAY) is None   # 10 日内第二条新链被拒
    assert _origin(p4, npc3, t0=t0 + 11 * DAY) is not None
    _cleanup(p3, p4, npc3)
    # 全服 active 满 40
    seeds = []
    for i in range(40):
        seeds.append(KarmaChain(
            kind="en", polarity=1, strength=1, player_id=f"seedp{i}", player_name="种子",
            counterparty_id=f"seedn{i}", counterparty_name="种子翁",
            chain_key=f"seed:global:{i}", status="latent", created_at=t0,
            ferment_at=t0 + DAY, mature_at=t0 + 9 * DAY, deadline_at=t0 + 23 * DAY,
        ))
        KarmaChainRepository.save(seeds[-1])
    p5, npc5 = _player("溢出客"), _npc("溢出翁")
    assert _origin(p5, npc5, t0=t0) is None
    for s in seeds:
        KarmaChainRepository.delete(s.id)
    _cleanup(p5, npc5)
    print("✓ K-13 玩家/NPC/全服上限 + 对偶冷却 + NPC 起链间隔")


# ---------------- K-14 翻转降级 ----------------

def test_flip_flop_narrative_only():
    p, npc = _player("横跳客"), _npc("横跳翁")
    t0 = _today_midday()
    en = KarmaChainEngine.note_attitude_cross(npc, p.id, 50, 65, now=t0)
    assert en is not None and en.flipped is False
    KarmaChainEngine.advance_for(p, now=t0 + 9 * DAY)
    assert KarmaChainRepository.get(en.id).status == "resolved"
    # 30 日内反向起 chou（已过 NPC 10 日间隔：起链日在 t0+12 日）
    chou = KarmaChainEngine.note_attitude_cross(npc, p.id, -50, -70, now=t0 + 12 * DAY)
    assert chou is not None and chou.kind == "chou" and chou.flipped is True
    snap_p = CharacterRepository.get_by_id(p.id)
    snap = (snap_p.spirit_stones, snap_p.realm.current_exp, snap_p.karma.sin_value,
            snap_p.karma.merit_value, snap_p.karma.dao_heart, _att(npc.id, p.id))
    KarmaChainEngine.advance_for(p, now=t0 + (12 + 15) * DAY)
    got = KarmaChainRepository.get(chou.id)
    assert got.status == "resolved"
    assert got.resolution.get("outcome") == "fizzled"
    assert got.resolution.get("effects") == {}
    now_p = CharacterRepository.get_by_id(p.id)
    assert (now_p.spirit_stones, now_p.realm.current_exp, now_p.karma.sin_value,
            now_p.karma.merit_value, now_p.karma.dao_heart, _att(npc.id, p.id)) == snap
    # flipped 终态后 30 日内再起链被拒
    assert KarmaChainEngine.note_attitude_cross(
        npc, p.id, 50, 65, now=t0 + (12 + 15 + 10) * DAY) is None
    _cleanup(p, npc)
    print("✓ K-14 翻转链只叙事不落数值、再犯窗口内拒起")


# ---------------- K-15/K-16 死亡衔接 ----------------

def test_death_dissipates_by_state():
    from core.legacy import LegacyAccount, LegacyEngine

    t0 = _today_midday()
    p = _player("将死客")
    n1, n2, n3 = _npc("死链翁一"), _npc("死链翁二"), _npc("死链翁三")
    c_ferm = _origin(p, n2, t0=t0)
    KarmaChainEngine.advance_for(p, now=t0 + 5 * DAY)  # n2 发酵
    assert KarmaChainRepository.get(c_ferm.id).status == "fermenting"
    c_latent = _origin(p, n1, t0=t0 + 5 * DAY)  # 死亡时仍潜伏（ferment 在 +9.5 日）
    c_mature = _origin(p, n3, kind="nuo", polarity=1, strength=2, t0=t0)
    # n3 已到期未推进（nuo+ 6 日）：单独把其状态推到 fermenting 而不兑现
    g = KarmaChainRepository.get(c_mature.id)
    g.status = "fermenting"
    KarmaChainRepository.save(g)
    snap_p = CharacterRepository.get_by_id(p.id)
    snap = (snap_p.spirit_stones, snap_p.realm.current_exp, snap_p.karma.sin_value,
            snap_p.karma.merit_value)
    out = KarmaChainEngine.on_owner_death(p, now=t0 + 7 * DAY)
    assert len(out) == 3
    for cid in (c_latent.id, c_ferm.id, c_mature.id):
        got = KarmaChainRepository.get(cid)
        assert got.status == "dissipated", (cid, got.status)
        assert (got.resolution or {}).get("reason") == "player_dead"
    now_p = CharacterRepository.get_by_id(p.id)
    assert (now_p.spirit_stones, now_p.realm.current_exp, now_p.karma.sin_value,
            now_p.karma.merit_value) == snap  # 消散零落账
    assert KarmaChainEngine.on_owner_death(p, now=t0 + 7 * DAY) == []  # 重放短路
    # 与影子/留痕零双重记账：带链死者 vs 无链对照，settle_death 逐值对照
    dead1 = _player("对照死甲")
    dead2 = _player("对照死乙")
    nx = _npc("对照翁")
    _origin(dead1, nx, t0=t0)
    KarmaChainEngine.on_owner_death(dead1, now=t0 + 1 * DAY)
    acc1, acc2 = LegacyAccount(user_id=dead1.user_id), LegacyAccount(user_id=dead2.user_id)
    s1 = LegacyEngine.settle_death(acc1, dead1, death_cause="寿尽", now=t0 + 2 * DAY)
    s2 = LegacyEngine.settle_death(acc2, dead2, death_cause="寿尽", now=t0 + 2 * DAY)
    t1, t2 = s1["trace"], s2["trace"]
    assert t1.shadow == t2.shadow == []
    assert t1.open_promises == t2.open_promises == []
    assert s1["points_gained"] == s2["points_gained"]
    _cleanup(p, n1, n2, n3, dead1, dead2, nx)
    print("✓ K-15 三态死亡全消散、零落账、留痕与对照逐值一致")


def test_counterparty_death_paths():
    t0 = _today_midday()
    # en 对象发酵中死亡 → counterparty_dead
    p, npc = _player("丧偶客"), _npc("先逝翁")
    ch = _origin(p, npc, t0=t0)
    KarmaChainEngine.advance_for(p, now=t0 + 5 * DAY)
    assert KarmaChainRepository.get(ch.id).status == "fermenting"
    npc.status = CharacterStatus.DEAD
    CharacterRepository.save(npc)
    KarmaChainEngine.advance_for(p, now=t0 + 6 * DAY)
    got = KarmaChainRepository.get(ch.id)
    assert got.status == "dissipated"
    assert (got.resolution or {}).get("reason") == "counterparty_dead"
    _cleanup(p, npc)
    # xue 死者无同宗在世 → no_avenger + 传闻收尾
    killer = _player("绝户手")
    victim = _npc("绝户者", sect=f"绝情谷{_tag()}")
    victim.status = CharacterStatus.DEAD
    CharacterRepository.save(victim)
    xue = KarmaChainEngine.note_kill(killer, victim, now=t0)
    KarmaChainEngine.advance_for(killer, now=t0 + 21 * DAY)
    got = KarmaChainRepository.get(xue.id)
    assert got.status == "dissipated"
    assert (got.resolution or {}).get("reason") == "no_avenger"
    assert _rumor_hits(victim.name)
    _cleanup(killer, victim)
    # 对象被主体亲杀 → superseded_by_kill 且 xue 另起
    p2, npc2 = _player("弑恩客"), _npc("被弑翁")
    ch2 = _origin(p2, npc2, t0=t0)
    npc2.status = CharacterStatus.DEAD
    CharacterRepository.save(npc2)
    # 亲杀在恩链起链 11 游戏日后（过单 NPC 新起链间隔闸，§8.1 全源共用）
    xue2 = KarmaChainEngine.note_kill(p2, npc2, now=t0 + 11 * DAY)
    assert xue2 is not None and xue2.kind == "xue"
    KarmaChainEngine.advance_for(p2, now=t0 + 12 * DAY)
    got2 = KarmaChainRepository.get(ch2.id)
    assert got2.status == "dissipated"
    assert (got2.resolution or {}).get("reason") == "superseded_by_kill"
    _cleanup(p2, npc2)
    print("✓ K-16 对象死亡/无仇主/亲杀取代三路径")


# ---------------- K-15 server 路径编年史断言（R1/MF-4） ----------------

def _chron_rows(event_type=None):
    import sqlite3

    import storage.db as dbmod

    conn = sqlite3.connect(dbmod.DB_PATH)
    if event_type is None:
        rows = conn.execute("SELECT event_type FROM world_chronicle").fetchall()
    else:
        rows = conn.execute(
            "SELECT event_type FROM world_chronicle WHERE event_type = ?",
            (event_type,)).fetchall()
    conn.close()
    return rows


def test_death_server_chronicle_traces():
    """K-15 server 断言组（走 World._settle_if_needed 真实路径）：
    (i) 只有 latent 链 → 链来源编年史（jianghu public 同步，event_type=
    karma_chain）零新增；(ii) 含 fermenting 链 → 恰增 1 条；
    (iii) 全库不存在 event_type == "KARMA_CHAIN_DEATH" 的记录。"""
    from server.world import World

    w = World(auto_tick=False)
    t0 = time.time()
    # (i) latent-only
    p1 = _player("服死甲")
    n1 = _npc("服链翁甲")
    ch1 = _origin(p1, n1, t0=t0)
    assert ch1 is not None and ch1.status == "latent"
    before = len(_chron_rows("karma_chain"))
    dead1 = CharacterRepository.get_by_id(p1.id)
    dead1.status = CharacterStatus.DEAD
    CharacterRepository.save(dead1)
    settle1 = w._settle_if_needed(dead1, cause="寿尽坐化")
    assert settle1 is not None
    assert KarmaChainRepository.get(ch1.id).status == "dissipated"
    assert len(_chron_rows("karma_chain")) == before  # latent 静默，零新增
    # (ii) fermenting
    p2 = _player("服死乙")
    n2 = _npc("服链翁乙")
    ch2 = _origin(p2, n2, t0=t0)
    KarmaChainEngine.advance_for(p2, now=t0 + 5 * DAY)  # 发酵（只写传闻）
    assert KarmaChainRepository.get(ch2.id).status == "fermenting"
    before2 = len(_chron_rows("karma_chain"))
    dead2 = CharacterRepository.get_by_id(p2.id)
    dead2.status = CharacterStatus.DEAD
    CharacterRepository.save(dead2)
    settle2 = w._settle_if_needed(dead2, cause="寿尽坐化")
    assert settle2 is not None
    assert KarmaChainRepository.get(ch2.id).status == "dissipated"
    assert len(_chron_rows("karma_chain")) == before2 + 1  # 引擎收尾恰一条
    # (iii) server 汇总编年史类型全库不存在
    assert _chron_rows("KARMA_CHAIN_DEATH") == []
    _cleanup(p1, n1, p2, n2)
    print("✓ K-15 server 路径：latent 编年史零新增、fermenting 恰 1 条、无 KARMA_CHAIN_DEATH")


# ---------------- K-20 了结留痕（R1/MF-5 必测清单 (a)–(e)） ----------------

def _jianghu_chain_events(chain_id):
    from storage.db import JianghuEventRepository

    return [
        e for e in JianghuEventRepository.list_recent(limit=300, kind="karma_chain")
        if (e.get("rule_result") or {}).get("chain_id") == chain_id
    ]


def _major_msgs_for(name):
    from storage.db import WorldMessageRepository

    return [
        m for m in WorldMessageRepository.list_recent(limit=300, since_ts=0.0)
        if m.level == "major" and name in (m.text or "")
    ]


def test_resolution_traces():
    t0 = _today_midday()
    # (a)(b) 任一链 resolved → jianghu karma_chain 恰 1 条 + 编年史同步恰 1 条
    p, npc = _player("留痕客"), _npc("留痕翁")
    ch = _origin(p, npc, strength=3, t0=t0)
    chron_before = len(_chron_rows("karma_chain"))
    KarmaChainEngine.advance_for(p, now=t0 + 9 * DAY)
    got = KarmaChainRepository.get(ch.id)
    assert got.status == "resolved"
    assert len(_jianghu_chain_events(ch.id)) == 1  # (a)
    assert len(_chron_rows("karma_chain")) == chron_before + 1  # (b)
    # (c) 非 xue resolved 不产生 major；xue resolved 恰 1 条 major
    assert _major_msgs_for(p.name) == []
    killer = _player("昭告手")
    victim = _npc("昭告者", sect="青云宗")
    avenger = _npc("昭告同门", sect="青云宗")
    victim.status = CharacterStatus.DEAD
    CharacterRepository.save(victim)
    now_real = time.time()
    xue = KarmaChainEngine.note_kill(killer, victim, now=now_real - 22 * DAY)
    assert xue is not None
    KarmaChainEngine.advance_for(killer, now=now_real)  # 发酵+兑现（真实时刻，免频道 TTL 清理）
    got_xue = KarmaChainRepository.get(xue.id)
    assert got_xue.status == "resolved", got_xue.resolution
    majors = _major_msgs_for(killer.name)
    assert len(majors) == 1 and majors[0].kind == "karma_chain", majors  # (c)
    # (d) 消散留痕差异：latent → jianghu/编年史零新增；fermenting → 各恰 1 条
    p3, n3 = _player("散痕甲"), _npc("散痕翁甲")
    ch3 = _origin(p3, n3, t0=t0)
    chron_before3 = len(_chron_rows("karma_chain"))
    KarmaChainEngine.on_owner_death(p3, now=t0 + DAY)
    assert KarmaChainRepository.get(ch3.id).status == "dissipated"
    assert _jianghu_chain_events(ch3.id) == []
    assert len(_chron_rows("karma_chain")) == chron_before3
    p4, n4 = _player("散痕乙"), _npc("散痕翁乙")
    ch4 = _origin(p4, n4, t0=t0)
    KarmaChainEngine.advance_for(p4, now=t0 + 5 * DAY)
    assert KarmaChainRepository.get(ch4.id).status == "fermenting"
    chron_before4 = len(_chron_rows("karma_chain"))
    KarmaChainEngine.on_owner_death(p4, now=t0 + 6 * DAY)
    assert KarmaChainRepository.get(ch4.id).status == "dissipated"
    assert len(_jianghu_chain_events(ch4.id)) == 1
    assert len(_chron_rows("karma_chain")) == chron_before4 + 1
    # (e) 账本隔离：链事件以 type="KARMA_CHAIN" 入 EventLedger，
    # 不入 RevengeEngine 种子集（query_feud_pairs 不含、force_callback 不取链）
    from storage.db import EventLedgerRepository
    from core.memory import RevengeEngine

    p5, n5 = _player("隔离客"), _npc("隔离翁")
    ch5 = _origin(p5, n5, strength=3, t0=t0)
    KarmaChainEngine.advance_for(p5, now=t0 + 9 * DAY)
    assert KarmaChainRepository.get(ch5.id).status == "resolved"
    mem = EventLedgerRepository.query_for_memory(p5.id, limit=20)
    assert any(e.get("type") == "KARMA_CHAIN" and e.get("chain_id") == ch5.id
               for e in mem), mem
    assert EventLedgerRepository.query_feud_pairs(p5.id, limit=20) == []
    assert RevengeEngine.force_callback(CharacterRepository.get_by_id(p5.id)) is None
    _cleanup(p, npc, killer, victim, avenger, p3, n3, p4, n4, p5, n5)
    print("✓ K-20 留痕 (a)–(e)：jianghu/编年史恰一条、xue major、消散差异、账本隔离")


def test_polish_only_presentation_copy(monkeypatch):
    """OBS-1（§9/§2.1）：AI 润色在落锚发效之后，只替换呈现副本，
    不回写 resolution["narrative"] 与 resolve 节点 summary（恒本地模板）。"""
    from core import ai_flavor

    monkeypatch.setattr(
        ai_flavor, "polish_karma_outcome",
        lambda *a, **k: "润色副本·此句只应出现在呈现层",
    )
    t0 = _today_midday()
    p, npc = _player("润色客"), _npc("润色翁")
    ch = _origin(p, npc, strength=3, t0=t0)
    KarmaChainEngine.advance_for(p, now=t0 + 5 * DAY)  # 发酵
    got0 = KarmaChainRepository.get(ch.id)
    assert got0.status == "fermenting"
    assert KarmaChainEngine._resolve(got0, t0 + 9 * DAY, allow_polish=True) is True
    got = KarmaChainRepository.get(ch.id)
    assert got.status == "resolved"
    # 模型字段恒本地模板：resolution 与 resolve 节点都不含润色文本
    assert "润色副本" not in (got.resolution.get("narrative") or "")
    resolve_nodes = [n for n in got.nodes if n.type == "resolve"]
    assert resolve_nodes and "润色副本" not in resolve_nodes[0].summary
    # 呈现副本（江湖账叙事）用了润色文本
    evs = _jianghu_chain_events(ch.id)
    assert len(evs) == 1 and "润色副本" in (evs[0].get("narrative") or "")
    _cleanup(p, npc)
    print("✓ OBS-1 润色只进呈现副本、不回写 resolution/节点")


# ---------------- K-17 旧存档兼容 ----------------

def test_old_save_compat(tmp_path):
    import sqlite3
    import storage.db as dbmod

    old_path = tmp_path / "old_tiandao.db"
    conn = sqlite3.connect(old_path)
    conn.execute("CREATE TABLE legacy_marker (id TEXT PRIMARY KEY)")  # 老库：无 karma_chains 表
    conn.commit()
    conn.close()
    old_db_path = dbmod.DB_PATH
    dbmod.DB_PATH = old_path
    try:
        dbmod.init_db()  # 自动补空表
        conn = sqlite3.connect(old_path)
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "karma_chains" in names
        assert KarmaChainRepository.list_all() == []
        p = _player("老档客")  # 对象构造不依赖库
        panel = KarmaChainEngine.panel_text(p, now=time.time())
        assert "眼下无因果缠身" in panel
    finally:
        dbmod.DB_PATH = old_db_path
    # 不追溯：老角色既有 ≥60 态度，小步进（不跨阈）不起链
    p2, npc2 = _player("老资历"), _npc("老相识")
    _set_att(npc2, p2.id, 70)
    shift_attitude(npc2, p2.id, 1, reason="交谈")
    assert _chains(p2.id, npc2.id) == []
    _cleanup(p2, npc2)
    print("✓ K-17 老库补空表、空面板、不追溯起链")


# ---------------- K-18 AI 降级 ----------------

def test_ai_down_chain_unbroken(monkeypatch):
    import ai.gateway as gw
    from core import ai_flavor

    t0 = _today_midday()
    results = []
    # 姿势一：AI 全关
    monkeypatch.setattr(gw, "ai_ready", lambda: False)
    assert ai_flavor.polish_karma_outcome("en", 1, "某翁", "某客", "报恩") is None
    p1, n1 = _player("降级甲"), _npc("降级翁甲")
    c1 = _origin(p1, n1, strength=4, t0=t0)
    KarmaChainEngine.tick_world(now=t0 + 9 * DAY)
    g1 = KarmaChainRepository.get(c1.id)
    assert g1.status == "resolved"
    results.append(g1.resolution.get("effects"))
    assert "近史" in KarmaChainEngine.panel_text(p1, now=t0 + 9 * DAY)
    # 姿势二：AI 抛异常
    def _boom(*a, **k):
        raise RuntimeError("ai down")

    monkeypatch.setattr(gw, "ai_ready", lambda: True)
    monkeypatch.setattr(gw, "_chat_json", _boom)
    assert ai_flavor.polish_karma_outcome("en", 1, "某翁", "某客", "报恩") is None
    p2, n2 = _player("降级乙"), _npc("降级翁乙")
    c2 = _origin(p2, n2, strength=4, t0=t0)
    # 链 id 不同会改变 hash 支；逐项只比「同支同值」：直接比对公式
    exp2 = KarmaChainEngine.compute_effects(KarmaChainRepository.get(c2.id), now=t0 + 9 * DAY)
    KarmaChainEngine.tick_world(now=t0 + 9 * DAY)
    g2 = KarmaChainRepository.get(c2.id)
    assert g2.status == "resolved"
    assert g2.resolution.get("effects") == exp2
    # 姿势三：润色层整体抛异常也不断链
    monkeypatch.setattr(ai_flavor, "polish_karma_outcome", _boom)
    p3, n3 = _player("降级丙"), _npc("降级翁丙")
    c3 = _origin(p3, n3, strength=4, t0=t0)
    KarmaChainEngine.tick_world(now=t0 + 9 * DAY)
    assert KarmaChainRepository.get(c3.id).status == "resolved"
    _cleanup(p1, n1, p2, n2, p3, n3)
    print("✓ K-18 AI 全关/抛异常/润色层爆炸三姿势链路不断、数值同公式")
