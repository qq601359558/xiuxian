"""QA 审计 · 域3 战力叠序/道心三点 + 域2 死亡清理/legacy境界往返 + 域8 存档兼容（探索性测试）"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import REALM_NAMES, SUB_TIER_NAMES
from core import pawn as pawn_mod
from core.art_slots import ArtSlotEngine
from core.ascension import AscensionEngine, parse_realm, score_of
from core.legacy import LegacyAccount, LegacyEngine
from core.atlas import AtlasEngine
from core.body_soul import BodySoulEngine
from core.books import BookEngine
from core.clock import WorldClock
from core.combat import CombatEngine
from core.farm import FarmEngine
from core.heart_demon_state import DemonStateEngine
from core.models import Character, CharacterStatus, FarmPlot, Realm, SpiritPet
from core.models import QuestChain, QuestRing
from core.pets import PetEngine
from core.promises import PromiseEngine
from core.quests import QuestEngine
from storage.db import CharacterRepository, PawnTicketRepository, PromiseRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, npc=False):
    prefix = "npc_qa_" if npc else "qa_"
    c = WorldClock.create_new_character(f"{prefix}{name}_{_tag()}", f"QA{name}{_tag()}")
    c.location = LOC
    CharacterRepository.save(c)
    return c


def _kill(*chars):
    for c in chars:
        if c is None:
            continue
        live = CharacterRepository.get_by_id(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


# ---------------- 域3.1 战力全乘区叠序：组合倍率 == 单因子倍率之积 ----------------

def test_power_full_stack_multiplicative_consistency():
    c = _char("战力客")
    try:
        c.realm.tier = 2
        c.realm.sub_tier = 0
        c.karma.dao_heart = 100
        CharacterRepository.save(c)

        def power():
            return CombatEngine.calculate_power(CharacterRepository.get_by_id(c.id))

        p0 = power()
        assert p0 > 0
        ratios = {}

        cur = CharacterRepository.get_by_id(c.id); cur.sect = "万剑仙门"; CharacterRepository.save(cur)
        ratios["sect"] = power() / p0
        cur = CharacterRepository.get_by_id(c.id); cur.sect = None; CharacterRepository.save(cur)

        cur = CharacterRepository.get_by_id(c.id); cur.equipped = ["青锋剑"]; CharacterRepository.save(cur)
        ratios["equip"] = power() / p0
        cur = CharacterRepository.get_by_id(c.id); cur.equipped = []; CharacterRepository.save(cur)

        cur = CharacterRepository.get_by_id(c.id)
        cur.custom_arts = [{"name": "QA自创", "spells": [{"multiplier": 2.0}]}]
        CharacterRepository.save(cur)
        ratios["art"] = power() / p0
        cur = CharacterRepository.get_by_id(c.id); cur.custom_arts = []; CharacterRepository.save(cur)

        cur = CharacterRepository.get_by_id(c.id)
        cur.pets = [SpiritPet(species="青鳞蟒", name="QA宠", growth=800, intimacy=100, active=True, state="follow")]
        CharacterRepository.save(cur)
        ratios["pet"] = power() / p0
        cur = CharacterRepository.get_by_id(c.id); cur.pets = []; CharacterRepository.save(cur)

        cur = CharacterRepository.get_by_id(c.id)
        cur.skills = ["QA功法甲", "QA功法乙"]; cur.sub_arts = ["QA功法甲", "QA功法乙"]
        CharacterRepository.save(cur)
        ratios["sub"] = power() / p0
        cur = CharacterRepository.get_by_id(c.id); cur.skills = []; cur.sub_arts = []; CharacterRepository.save(cur)

        cur = CharacterRepository.get_by_id(c.id); cur.body_level = 10; CharacterRepository.save(cur)
        ratios["body"] = power() / p0
        cur = CharacterRepository.get_by_id(c.id); cur.body_level = 0; CharacterRepository.save(cur)

        # 各 spec 封顶
        assert ratios["pet"] <= 1.10 + 1e-9, f"灵宠环超封顶 {ratios['pet']}"
        assert ratios["sub"] <= 1.06 + 1e-9, f"辅修环超封顶 {ratios['sub']}"
        assert ratios["body"] <= 1.10 + 1e-9, f"炼体环超封顶 {ratios['body']}"
        assert ratios["equip"] <= 1.20 + 1e-9, f"装备环超封顶 {ratios['equip']}"
        assert ratios["art"] <= 1.20 + 1e-9, f"功法环超封顶 {ratios['art']}"

        # 全叠
        cur = CharacterRepository.get_by_id(c.id)
        cur.sect = "万剑仙门"
        cur.equipped = ["青锋剑"]
        cur.custom_arts = [{"name": "QA自创", "spells": [{"multiplier": 2.0}]}]
        cur.pets = [SpiritPet(species="青鳞蟒", name="QA宠", growth=800, intimacy=100, active=True, state="follow")]
        cur.skills = ["QA功法甲", "QA功法乙"]; cur.sub_arts = ["QA功法甲", "QA功法乙"]
        cur.body_level = 10
        CharacterRepository.save(cur)
        r_all = power() / p0
        prod = 1.0
        for v in ratios.values():
            prod *= v
        assert abs(r_all - prod) / prod < 1e-4, (
            f"全乘区组合倍率 {r_all:.6f} ≠ 单因子之积 {prod:.6f}（分项 {ratios}）——叠序/截断异常"
        )
    finally:
        _kill(c)


# ---------------- 域3.2 炼神有效道心：心魔状态机压制系数取有效值 ----------------

def test_demon_suppression_uses_effective_dao_heart():
    made = []
    try:
        probe = _mk_dao(50, 10); made.append(probe)
        assert BodySoulEngine.effective_dao_heart(probe) == 70
        # eff=70 → 压制 ×0.5：sin 增量 20 × 0.5（杀业系数） × 0.5（压制） = 5.0
        c = _mk_dao(50, 10); made.append(c)
        got = DemonStateEngine.sync(c, now=c.demon_anchor_at)
        assert abs(got - 5.0) < 1e-9, f"魔念杀业路 期望 5.0（有效道心70压制×0.5），实际 {got}"
        # eff=90（本体90无炼神） → 压制 ×0.25：20 × 0.5 × 0.25 = 2.5
        c2 = _mk_dao(90, 0); made.append(c2)
        got2 = DemonStateEngine.sync(c2, now=c2.demon_anchor_at)
        assert abs(got2 - 2.5) < 1e-9, f"魔念杀业路 期望 2.5（道心90压制×0.25），实际 {got2}"
        # eff=50（本体50无炼神） → 压制 ×1.0：20 × 0.5 = 10.0
        c3 = _mk_dao(50, 0); made.append(c3)
        got3 = DemonStateEngine.sync(c3, now=c3.demon_anchor_at)
        assert abs(got3 - 10.0) < 1e-9, f"魔念杀业路 期望 10.0（道心50压制×1.0），实际 {got3}"
    finally:
        _kill(*made)


def _mk_dao(dao, soul_level):
    c = _char("道心客")
    c.karma.dao_heart = dao
    c.soul_level = soul_level
    t0 = time.time()
    c.demon_anchor_at = t0
    c.demon_sin_seen = 0
    c.demon_seed = 0.0
    c.karma.sin_value = 20
    c.karma.blood_mark_until = 0.0
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


# ---------------- 域2.3 境界名往返：settle_death 写入名 ↔ 飞升榜解析 ----------------

def test_realm_name_roundtrip_for_ascension():
    bad = []
    for tier in range(len(REALM_NAMES)):
        for sub in range(len(SUB_TIER_NAMES)):
            name = Realm(tier=tier, sub_tier=sub).name
            pt, ps = parse_realm(name)
            if tier == 0 or tier >= 9:
                if pt != tier:
                    bad.append((tier, sub, name, pt, ps))
            elif (pt, ps) != (tier, sub):
                bad.append((tier, sub, name, pt, ps))
    assert not bad, f"境界名往返失败（前世落账名无法被飞升榜正确解析）：{bad}"


# ---------------- 域2.2 死亡清理矩阵（钩子项）+ 当票按 spec 保留 ----------------

def test_death_cleanup_matrix():
    from core.pets import PetEngine
    import sqlite3
    from storage.db import DB_PATH

    npc = _char("死诺翁", npc=True)
    c = _char("死客")
    ticket = None
    promise_ids = []
    try:
        cur = CharacterRepository.get_by_id(c.id)
        cur.pets = [SpiritPet(species="青鳞蟒", name="QA殁宠", growth=100, intimacy=50, active=True, state="follow")]
        cur.cave_level = 1
        cur.farm_plots = [FarmPlot(crop="灵谷种子", planted_at=time.time(), matures_at=time.time() + 1800)]
        now = time.time()
        cur.active_quest = QuestChain(
            publisher_id=npc.id, publisher_name=npc.name,
            rings=[QuestRing(kind="fetch", desc="寻物", deliver_npc_id=npc.id,
                             deliver_npc_name=npc.name, item_name="聚灵草", need=1)],
            ring_index=0, accepted_at=now, expires_at=now + 86400,
            reward_stones=50, reward_merit=5,
        )
        cur.inventory.append("聚气丹")
        CharacterRepository.save(cur)
        res = PromiseEngine.make_promise(CharacterRepository.get_by_id(c.id), npc, "quest", now=now)
        assert res["success"], res
        promise_ids = [p.id for p in PromiseRepository.list_all() if p.promiser_id == c.id]
        assert promise_ids, "诺言应已落库"
        ticket, pres = pawn_mod.PawnEngine.pawn_item(CharacterRepository.get_by_id(c.id), "聚气丹")
        assert ticket is not None, pres
        PawnTicketRepository.save(ticket)  # 成票由调用方落库（与 world/cli 同口径）

        # 死亡结算（与 server/world.py _settle_if_needed 同序调用四钩子）
        cur = CharacterRepository.get_by_id(c.id)
        cur.status = CharacterStatus.DEAD
        CharacterRepository.save(cur)
        PetEngine.on_owner_death(cur)
        FarmEngine.on_owner_death(cur)
        QuestEngine.on_owner_death(cur)
        PromiseEngine.on_owner_death(cur)
        CharacterRepository.save(cur)

        after = CharacterRepository.get_by_id(c.id)
        assert all(p.state == "dead" for p in after.pets), "灵宠应随主人殁"
        assert all(p.crop == "" for p in after.farm_plots), "灵田作物应荒废"
        assert after.active_quest is None, "委托链应随旧世清理"
        for pid in promise_ids:
            row = [p for p in PromiseRepository.list_all() if p.id == pid]
            st = getattr(row[0].status, "value", row[0].status) if row else "行丢失"
            assert row and st == "DISSOLVED", f"诺言应消散，实际 {st}"
        # 当票：pawn spec 明示旧票按 char_id 归属旧世、新世不可赎——死亡不清理（记录现状）
        trow = PawnTicketRepository.list_by_owner(c.id)
        tst = getattr(trow[0].status, "value", trow[0].status) if trow else "无票"
        assert trow and tst == "OPEN", f"当票按 spec 应保留 OPEN（归属旧世），实际 {tst}"
    finally:
        conn = sqlite3.connect(DB_PATH)
        for pid in promise_ids:
            conn.execute("DELETE FROM promises WHERE id = ?", (pid,))
        if ticket is not None:
            conn.execute("DELETE FROM pawn_tickets WHERE id = ?", (ticket.id,))
        conn.commit()
        conn.close()
        _kill(npc, c)


# ---------------- 域5.2 版图日上限 × NPC 权重（原始分计上限、权重折算入账） ----------------

def test_atlas_daily_cap_and_npc_weight_composition():
    from storage.db import WorldStateRepository
    region = "东荒·青州"
    key = f"sect_atlas:{region}"
    saved = WorldStateRepository.get(key)
    player = _char("版图员")
    npc = _char("版图仆", npc=True)
    try:
        for c in (player, npc):
            c.sect = "青云宗"
            CharacterRepository.save(c)
        t = time.time()
        inf0 = AtlasEngine.influence_map(region, t).get("青云宗", 0.0)
        # 玩家探险 +4/次：7 次满额 28，第 8 次只入剩余 2（部分入账），合计恰 30（日上限）
        gains = [AtlasEngine.record_activity(CharacterRepository.get_by_id(player.id), "explore", now=t) for _ in range(8)]
        assert abs(sum(gains) - 30.0) < 1e-9, f"玩家日入账应恰 30（28+部分2），实际分次 {gains}"
        # NPC：原始分上限 10，权重 0.5 折算入账：4→2、4→2、余 2→1，合计 5.0
        ngains = [AtlasEngine.record_activity(CharacterRepository.get_by_id(npc.id), "explore", now=t) for _ in range(3)]
        assert abs(sum(ngains) - 5.0) < 1e-9, f"NPC 日入账应恰 5.0（2+2+1），实际分次 {ngains}"
        inf1 = AtlasEngine.influence_map(region, t).get("青云宗", 0.0)
        assert abs((inf1 - inf0) - 35.0) < 0.01, f"区域影响力总增量应 35，实际 {inf1 - inf0}"
    finally:
        if saved is None:
            WorldStateRepository.delete(key)
        else:
            WorldStateRepository.set(key, saved)
        _kill(player, npc)


# ---------------- 域2.4 死亡结算 → legacy 落账 → 飞升榜分数/境界解析一致 ----------------

def test_death_legacy_to_ascension_score_consistency():
    c = _char("榜客")
    try:
        c.realm.tier = 3
        c.realm.sub_tier = 2
        c.lifespan.birth_base = 60.0
        c.lifespan.accumulated_gain = 25.0
        CharacterRepository.save(c)
        account = LegacyAccount(user_id=c.user_id)
        res = LegacyEngine.settle_death(account, CharacterRepository.get_by_id(c.id), death_cause="QA审计", now=time.time())
        assert res["success"]
        assert len(account.past_lives) == 1
        past = account.past_lives[0]
        assert abs(past.lifespan_lived - 85.0) < 1e-9, f"享寿应 60+25=85，实际 {past.lifespan_lived}"
        assert parse_realm(past.realm) == (3, 2), f"前世境界名 {past.realm} 应往返解析为 (3,2)"
        assert account.points == past.points_gained, "账号道统点应与前世落账点一致（无自尽惩罚场景）"
        entries = AscensionEngine.collect_entries([account])
        mine = [e for e in entries if e["name"] == c.name]
        assert len(mine) == 1, f"飞升榜应恰收录该前世一次，实际 {len(mine)}"
        exp_score = score_of(3, 2, past.points_gained, past.lifespan_lived)
        assert abs(mine[0]["score"] - exp_score) < 1e-9, (
            f"飞升榜分数应 {exp_score}（tier×1000+sub×100+点×10+min(享寿,300)×0.5），实际 {mine[0]['score']}"
        )
        assert mine[0]["rank"] == 1
    finally:
        _kill(c)


# ---------------- 域8.1 旧档组合剥离：全功能面板不崩、默认值正确 ----------------

def test_old_save_stripped_fields_panels_ok():
    c = _char("旧档客")
    try:
        data = CharacterRepository.get_by_id(c.id).model_dump()
        for k in ("body_level", "soul_level", "inspiration", "prestige",
                  "active_quest", "quest_cooldown_until",
                  "demon_seed", "demon_anchor_at", "demon_sin_seen", "demon_calm_at",
                  "cave_level", "farm_plots", "main_art", "sub_arts",
                  "art_slot_changed_at", "pets"):
            data.pop(k, None)
        old = Character.model_validate(data)
        assert old.body_level == 0 and old.soul_level == 0
        assert old.inspiration == 0 and old.prestige == 0
        assert old.active_quest is None and old.demon_seed == 0.0
        assert old.cave_level == 0 and old.farm_plots == [] and old.pets == []
        assert old.main_art == "" and old.sub_arts == []
        failures = {}
        for name, fn in {
            "body_panel": lambda: BodySoulEngine.panel_text(old, "body"),
            "soul_panel": lambda: BodySoulEngine.panel_text(old, "soul"),
            "books_panel": lambda: BookEngine.panel_text(old),
            "demon_summary": lambda: DemonStateEngine.summary(old),
            "farm_panel": lambda: FarmEngine.panel_text(old),
            "arts_panel": lambda: ArtSlotEngine.panel_text(old),
            "atlas_panel": lambda: AtlasEngine.panel_text(old),
            "quest_settle": lambda: QuestEngine.settle_expired(old),
            "power": lambda: CombatEngine.calculate_power(old),
            "pet_bonus": lambda: PetEngine.power_bonus(old),
        }.items():
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                failures[name] = f"{type(e).__name__}: {e}"
        assert not failures, f"旧档角色打开新功能面板崩溃：{failures}"
    finally:
        _kill(c)
