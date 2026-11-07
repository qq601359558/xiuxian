"""game-feel-phase3 后端验收（Spec §9 的 LT/SP/TR/BR 后端部分）。

覆盖：LT-01~07（得宝幕）、SP-01~06（器灵认主幕）、TR-01~08（天劫
独立幕，后端侧；TR-06 的前端呈现面归前端岗，本文件只验后端可达性）、
BR-01~05（briefing ⑤.6 的 S-1/S-2/S-4）。
铁律口径：先结算后演出、ceremony 纯读拼装、零 AI、result_ref 逐项
对账、跳过等价（后端侧：拼装零写 + 同播种两路最终状态一致）。
"""
import copy
import os
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"
os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

import pytest

from core.clock import WorldClock
from core.models import CharacterStatus
from storage.db import (
    AccountRepository,
    CharacterRepository,
    WorldStateRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

REPO = Path(__file__).resolve().parent.parent
LOC = "青云坊市客栈"


def _tag():
    return uuid.uuid4().hex[:8]


def _join(name="三期客"):
    uid = AccountRepository.create(f"gf3_{_tag()}", "h", "s")
    snap = WORLD.join(f"{name}{_tag()}", user_id=uid)
    assert snap.get("token"), snap
    char = CharacterRepository.get_by_user_id(uid)
    assert char is not None
    return snap["token"], char


def _char(name="三期散修"):
    c = WorldClock.create_new_character(f"gf3_{_tag()}_{name}", f"{name}{_tag()}")
    c.location = LOC
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


def _reload(char_id):
    return CharacterRepository.get_by_id(char_id)


def _git_diff(*paths):
    out = subprocess.run(
        ["git", "diff", "HEAD", "--", *paths],
        cwd=str(REPO), capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


# ================= LT · 得宝幕 =================

def _give_map(char, *, tier, archetype, target):
    from core.treasure_system import TreasureEngine

    tmap = TreasureEngine.generate_treasure_map(
        char, tier=tier, preferred_target=target)
    tmap.custom_metadata["archetype"] = archetype
    char.add_item_entity(tmap)
    CharacterRepository.save(char)
    return tmap


def _dig(token, char_id, *, tier, archetype, target, choice=None):
    from core.treasure_system import TreasureArchetype

    char = _reload(char_id)
    char.location = target
    CharacterRepository.save(char)
    char = _reload(char_id)
    _give_map(char, tier=tier, archetype=archetype, target=target)
    if archetype == TreasureArchetype.ELEMENT_PUZZLE:
        first = WORLD.handle(token, "/挖宝")
        assert first.get("ok"), first
    return WORLD.handle(token, f"/挖宝 {choice}" if choice else "/挖宝")


def test_lt07_predicate_truth_table_and_single_ceremony():
    from core.ceremony import loot_ceremony_candidate as cand

    assert cand("equip", 3) is False and cand("equip", 4) is True
    assert cand("equip", 5) is True
    assert cand("relic", 2) is False and cand("relic", 3) is True
    assert cand("relic", 4) is True
    for kind in ("pill", "material", "treasure_map", "herb", "consumable"):
        for tier in (1, 3, 5):
            assert cand(kind, tier) is False, (kind, tier)
    # 连续两次达线开匣各演一幕、result_ref 互不串扰
    from core.treasure_system import TreasureArchetype

    token, char = _join("连珠客")
    r1 = _dig(token, char.id, tier=4,
              archetype=TreasureArchetype.ELEMENT_PUZZLE,
              target="黑水沼泽", choice="1")
    r2 = _dig(token, char.id, tier=5,
              archetype=TreasureArchetype.ELEMENT_PUZZLE,
              target="黑水沼泽", choice="1")
    assert r1["ceremony"]["kind"] == "loot" and r2["ceremony"]["kind"] == "loot"
    u1 = r1["ceremony"]["result_ref"]["uid"]
    u2 = r2["ceremony"]["result_ref"]["uid"]
    assert u1 != u2
    assert u1 == r1["equipment"]["uid"] and u2 == r2["equipment"]["uid"]


def test_lt01_lt02_dig_equip_tier4_reconciles():
    from core.treasure_system import TreasureArchetype

    token, char = _join("掘宝人")
    resp = _dig(token, char.id, tier=4,
                archetype=TreasureArchetype.ELEMENT_PUZZLE,
                target="黑水沼泽", choice="1")
    assert resp.get("ok") and resp.get("equipment"), resp
    cer = resp.get("ceremony")
    assert cer and cer["kind"] == "loot" and cer["skippable"] is True
    # LT-01 锚断言：落账先于拼装——DB 重读角色行已含该 uid 实体
    fresh = _reload(char.id)
    ent = next((it for it in fresh.items if it.uid == cer["result_ref"]["uid"]), None)
    assert ent is not None, "result_ref.uid 必须能在落账后 items 中查到"
    # LT-02 逐项对账（vs dig 返回 equipment dict）
    eq = resp["equipment"]
    ref = cer["result_ref"]
    assert ref["uid"] == eq["uid"] == ent.uid
    assert ref["name"] == eq["name"] == ent.name
    assert ref["kind"] == eq["kind"] == ent.kind.value
    assert ref["tier"] == eq["tier"] == ent.tier
    assert ref["tier_name"] == eq["tierName"] == ent.tier_name
    assert ref["slot"] == eq["slot"] == ent.slot
    assert ref["source"] == "treasure_dig"
    assert ref["affixes_text"] == "、".join(a["name"] for a in eq["affixes"])
    # beats：三段齐全、choices 恒 null（§2.2）
    assert [b["stage"] for b in cer["beats"]] == ["prelude", "reveal", "aftermath"]
    assert all(b["text"] for b in cer["beats"])
    assert all(b["choices"] is None for b in cer["beats"])
    # tier4 equip 的 aftermath 必须含器灵预告（穿戴 + /器灵 唤）
    assert "/器灵 唤" in cer["beats"][2]["text"]
    assert "穿戴" in cer["beats"][2]["text"]


def test_lt01_lt02_dig_relic_ruin_reconciles():
    from core.treasure_system import TreasureArchetype

    token, char = _join("探渊人")
    resp = _dig(token, char.id, tier=3,
                archetype=TreasureArchetype.RUIN_HAZARD,
                target="落霞山灵泉")
    assert resp.get("ok") and resp.get("equipment"), resp
    cer = resp.get("ceremony")
    assert cer and cer["kind"] == "loot"
    eq = resp["equipment"]
    assert eq["name"] == "纯阳离火印" and eq["kind"] == "relic" and eq["tier"] == 3
    ref = cer["result_ref"]
    fresh = _reload(char.id)
    ent = next((it for it in fresh.items if it.uid == ref["uid"]), None)
    assert ent is not None
    assert ref["uid"] == eq["uid"] and ref["name"] == eq["name"]
    assert ref["kind"] == "relic" and ref["tier"] == 3
    assert ref["tier_name"] == eq["tierName"]
    assert ref["source"] == "treasure_dig"


def test_lt01_lt02_blind_box_relic_reconciles(monkeypatch):
    token, char = _join("捡漏人")
    char = _reload(char.id)
    char.spirit_stones = 500
    CharacterRepository.save(char)
    monkeypatch.setattr(random, "random", lambda: 0.05)  # roll<0.15 → tier4 relic
    resp = WORLD.handle(token, "/捡漏")
    assert resp.get("ok") and resp.get("loot") == "太古遗迹真仙古卷", resp
    cer = resp.get("ceremony")
    assert cer and cer["kind"] == "loot"
    fresh = _reload(char.id)
    ent = next((it for it in fresh.items if it.name == "太古遗迹真仙古卷"), None)
    assert ent is not None
    ref = cer["result_ref"]
    assert ref["uid"] == ent.uid and ref["name"] == ent.name
    assert ref["kind"] == ent.kind.value == "relic"
    assert ref["tier"] == ent.tier == 4
    assert ref["tier_name"] == ent.tier_name
    assert ref["slot"] == ent.slot
    assert ref["source"] == "blind_box"
    assert ref["affixes_text"] == "、".join(a.name for a in ent.affixes)


def test_lt03_threshold_negatives(monkeypatch):
    from core.treasure_system import TreasureArchetype

    # dig 得 equip tier3（tier3 图巧破）→ 无幕
    token, char = _join("低阶客")
    resp = _dig(token, char.id, tier=3,
                archetype=TreasureArchetype.ELEMENT_PUZZLE,
                target="黑水沼泽", choice="1")
    assert resp.get("equipment") and resp["equipment"]["tier"] == 3
    assert resp.get("ceremony") is None
    # 盲匣 tier3 剑 → 无幕
    token2, char2 = _join("捡漏乙")
    c2 = _reload(char2.id)
    c2.spirit_stones = 500
    CharacterRepository.save(c2)
    monkeypatch.setattr(random, "random", lambda: 0.30)  # 0.15≤roll<0.45 → tier3 剑
    resp2 = WORLD.handle(token2, "/捡漏")
    assert resp2.get("loot") == "古修断纹玄阴剑"
    assert resp2.get("ceremony") is None
    # 盲匣 tier2 丹 → 无幕
    token3, char3 = _join("捡漏丙")
    c3 = _reload(char3.id)
    c3.spirit_stones = 500
    CharacterRepository.save(c3)
    monkeypatch.setattr(random, "random", lambda: 0.60)  # 0.45≤roll<0.75 → tier2 丹
    resp3 = WORLD.handle(token3, "/捡漏")
    assert resp3.get("loot") == "千年雪魄定颜丹"
    assert resp3.get("ceremony") is None


def test_lt03_adventure_and_craft_have_no_loot_ceremony():
    """§3.1 第 5/6 条销账：探险/炼器 handler 级各构造一例，响应无得宝幕。"""
    token, char = _join("远行客")
    c = _reload(char.id)
    c.spirit_stones = 500
    c.adventure_cd_until = 0
    CharacterRepository.save(c)
    resp = WORLD.handle(token, "/探险 野外")
    assert "ceremony" not in resp or resp.get("ceremony") is None, resp
    # 炼器：默认配方 + 材料就位后开炉（成败均可），响应无 ceremony 键
    from core.alchemy import ensure_default_recipes

    token2, char2 = _join("炼器客")
    c2 = _reload(char2.id)
    c2.spirit_stones = 500
    ensure_default_recipes(c2)
    c2.inventory.append("百年灵芝")
    CharacterRepository.save(c2)
    resp2 = WORLD.handle(token2, "/炼丹 聚气丹方")
    assert "ceremony" not in resp2, resp2


def test_lt04_skip_equivalence_backend(monkeypatch):
    """C2 后端侧：ceremony 拼装零写（拼装前后角色行逐字段一致）+
    同播种两次达线开匣的最终状态一致（看/跳在后端无差别）。"""
    from core.ceremony import build_loot_ceremony
    from core.treasure_system import TreasureArchetype

    token, char = _join("等价客")
    resp = _dig(token, char.id, tier=4,
                archetype=TreasureArchetype.ELEMENT_PUZZLE,
                target="黑水沼泽", choice="1")
    assert resp.get("ceremony")
    fresh = _reload(char.id)
    before = copy.deepcopy(fresh.model_dump())
    eq = resp["equipment"]
    info = {
        "uid": eq["uid"], "name": eq["name"], "kind": eq["kind"],
        "tier": eq["tier"], "tier_name": eq["tierName"], "slot": eq["slot"],
        "affixes": eq["affixes"], "lore": eq.get("lore", ""),
    }
    build_loot_ceremony(fresh, info, source="treasure_dig")
    assert fresh.model_dump() == before, "builder 必须纯读、零写"

    def _run_once():
        tk, ch = _join("同播客")
        ch = _reload(ch.id)
        ch.spirit_stones = 1000  # 统一出身灵石差异，只比开匣结算本身
        CharacterRepository.save(ch)
        random.seed(20261108)
        r = _dig(tk, ch.id, tier=4,
                 archetype=TreasureArchetype.ELEMENT_PUZZLE,
                 target="黑水沼泽", choice="1")
        assert r.get("ceremony")
        f = _reload(ch.id)
        return (
            f.spirit_stones, f.realm.current_exp,
            sorted((it.name, it.kind.value, it.tier) for it in f.items),
        )

    assert _run_once() == _run_once()


def test_lt05_no_key_beats_complete_and_asset_valid():
    from core.ceremony import build_loot_ceremony
    from core.gallery_assets import GALLERY_ASSET_KEYS

    char = _char("无钥客")
    info = {
        "uid": "lt05uid001", "name": "斩龙古剑", "kind": "equip", "tier": 4,
        "tier_name": "天品", "slot": "weapon",
        "affixes": [{"name": "破煞", "desc": "破罡煞之气"}],
        "lore": "古剑沉渊，今日重光。",
    }
    cer = build_loot_ceremony(char, info, source="treasure_dig")
    assert [b["stage"] for b in cer["beats"]] == ["prelude", "reveal", "aftermath"]
    assert all(b["text"].strip() for b in cer["beats"])
    assert "斩龙古剑" in cer["beats"][1]["text"]
    assert "破煞" in cer["beats"][1]["text"]
    for b in cer["beats"]:
        assert b.get("asset_key") is None or b["asset_key"] in GALLERY_ASSET_KEYS


def test_lt06_ceremony_module_has_no_ai_or_director_refs():
    src = (REPO / "core" / "ceremony.py").read_text(encoding="utf-8")
    for forbidden in ("ai.gateway", "AIGateway", "_chat_json",
                      "WorldDirector", "run_cycle", "world_director"):
        assert forbidden not in src, f"ceremony.py 不得引用 {forbidden}"
    # builder 直调拼装耗时毫秒级（<50ms）
    from core.ceremony import build_loot_ceremony

    char = _char("计时客")
    info = {
        "uid": "lt06uid001", "name": "太乙玄天戈", "kind": "equip", "tier": 5,
        "tier_name": "仙品", "slot": "weapon", "affixes": [], "lore": "",
    }
    t0 = time.perf_counter()
    build_loot_ceremony(char, info, source="treasure_dig")
    assert time.perf_counter() - t0 < 0.05


# ================= SP · 器灵认主幕 =================

def _spirit_char(name="御灵客", item_name="镇海宝镜", tier=4, equip=True):
    from core.items import ItemFactory

    token, char = _join(name)
    char = _reload(char.id)
    it = ItemFactory.create_equip(item_name, tier=tier, slot="trinket")
    char.add_item_entity(it)
    if equip:
        char.equipped.append(it.name)
    CharacterRepository.save(char)
    return token, char.id, it.uid


def test_sp01_first_awaken_triggers_and_negatives():
    token, char_id, _uid = _spirit_char()
    resp = WORLD.handle(token, "/器灵 唤 镇海宝镜")
    assert resp.get("ok"), resp
    cer = resp.get("ceremony")
    assert cer and cer["kind"] == "spirit" and cer["skippable"] is True
    assert [b["stage"] for b in cer["beats"]] == ["prelude", "reveal", "aftermath"]
    assert all(b["choices"] is None for b in cer["beats"])
    # 重复唤（changed=False）→ 无幕
    resp2 = WORLD.handle(token, "/器灵 唤 镇海宝镜")
    assert resp2.get("ok") and not resp2.get("ceremony")
    # /温养、/灵语 响应无 spirit 幕
    resp3 = WORLD.handle(token, "/温养")
    assert not resp3.get("ceremony")
    resp4 = WORLD.handle(token, "/灵语 你好")
    assert resp4.get("ok") and not resp4.get("ceremony")


def test_sp01_awaken_failures_have_no_ceremony():
    # 未穿戴 tier4 → 失败无幕
    token, char_id, _ = _spirit_char(name="未穿客", item_name="紫金葫芦", equip=False)
    resp = WORLD.handle(token, "/器灵 唤 紫金葫芦")
    assert not resp.get("ok") and not resp.get("ceremony")
    # tier3 已穿戴 → 失败无幕
    token2, char_id2, _ = _spirit_char(name="低阶客", item_name="青锋利剑", tier=3)
    resp2 = WORLD.handle(token2, "/器灵 唤 青锋利剑")
    assert not resp2.get("ok") and not resp2.get("ceremony")
    # 器物不存在 → 失败无幕
    token3, char3 = _join("寻器客")
    resp3 = WORLD.handle(token3, "/器灵 唤 不存在的法宝")
    assert not resp3.get("ok") and not resp3.get("ceremony")


def test_sp02_spirit_result_ref_reconciles():
    token, char_id, uid = _spirit_char()
    resp = WORLD.handle(token, "/器灵 唤 镇海宝镜")
    ref = resp["ceremony"]["result_ref"]
    fresh = _reload(char_id)
    ent = next(it for it in fresh.items if it.uid == uid)
    spirit = ent.custom_metadata["spirit"]
    assert ref["item_uid"] == ent.uid and ref["item_name"] == ent.name
    assert ref["tier"] == ent.tier
    assert ref["spirit_name"] == spirit["name"]
    assert ref["personality"] == spirit["personality"]
    assert ref["stage"] == 0 and spirit["growth"] == 0
    assert ref["mood"] == 60 == spirit["mood"]
    from core.artifact_spirit import PERSONALITIES

    assert ref["personality_cn"] == PERSONALITIES[spirit["personality"]]["cn"]


def test_sp03_spirit_line_is_local_pool():
    from core.artifact_spirit import PERSONALITIES

    token, char_id, uid = _spirit_char()
    resp = WORLD.handle(token, "/器灵 唤 镇海宝镜")
    cer = resp["ceremony"]
    assert all(b["text"].strip() for b in cer["beats"])
    fresh = _reload(char_id)
    ent = next(it for it in fresh.items if it.uid == uid)
    personality = ent.custom_metadata["spirit"]["personality"]
    pool = PERSONALITIES[personality]["lines"]
    reveal = cer["beats"][1]["text"]
    assert any(line in reveal for line in pool), "第一句话必须出自本地性格台词池"


def test_sp04_spirit_builder_is_readonly():
    from core.artifact_spirit import ArtifactSpiritEngine
    from core.ceremony import build_spirit_ceremony
    from core.items import ItemFactory

    char = _char("只读客")
    it = ItemFactory.create_equip("镇海宝镜", tier=4, slot="trinket")
    char.add_item_entity(it)
    char.equipped.append(it.name)
    res = ArtifactSpiritEngine.awaken(char, it.name)
    assert res["success"] and res["changed"]
    before = copy.deepcopy(char.model_dump())
    cer = build_spirit_ceremony(char, it)
    assert cer["kind"] == "spirit"
    assert char.model_dump() == before, "认主幕拼装必须零写"


def test_sp05_spirit_existing_behavior_unchanged():
    from core.artifact_spirit import (
        ArtifactSpiritEngine,
        panel_text,
        public_spirit_dict,
    )
    from core.items import ItemFactory

    char = _char("面板客")
    it = ItemFactory.create_equip("镇海宝镜", tier=4, slot="trinket")
    char.add_item_entity(it)
    char.equipped.append(it.name)
    ArtifactSpiritEngine.awaken(char, it.name)
    assert "镇海宝镜" in panel_text(char)
    pub = public_spirit_dict(it)
    assert pub and pub["stage"] == 0 and pub["mood"] == 60
    assert ArtifactSpiritEngine.power_bonus(char) == 1.0  # 萌生无加成（基线口径）


def test_sp06_spirit_builder_timing():
    from core.artifact_spirit import ArtifactSpiritEngine
    from core.ceremony import build_spirit_ceremony
    from core.items import ItemFactory

    char = _char("计时灵客")
    it = ItemFactory.create_equip("镇海宝镜", tier=4, slot="trinket")
    char.add_item_entity(it)
    char.equipped.append(it.name)
    ArtifactSpiritEngine.awaken(char, it.name)
    t0 = time.perf_counter()
    build_spirit_ceremony(char, it)
    assert time.perf_counter() - t0 < 0.05


# ================= TR · 天劫独立幕 =================

def _attempt(success=True, fail_tier=None, *, prob=55.0):
    return {
        "success": success,
        "is_major": True,
        "is_fatal": fail_tier == "DEATH",
        "fail_tier": fail_tier,
        "prob_pct": prob,
        "judge_source": "rule",
        "judge_reason": "",
        "new_realm": "筑基期初期" if success else None,
        "lifespan_gained": 30.0 if success else 0.0,
    }


def test_tr01_builder_matrix_and_fail_tiers():
    from core.ceremony import build_tribulation_ceremony

    char = _char("渡劫客")
    char.realm.tier = 2  # 成功后口径：char 已升 tier
    cer = build_tribulation_ceremony(char, _attempt(True))
    assert cer["kind"] == "tribulation" and cer["skippable"] is True
    assert [b["stage"] for b in cer["beats"]] == ["prelude", "reveal", "aftermath"]
    assert all(b["text"].strip() for b in cer["beats"])
    assert all(b["choices"] is None for b in cer["beats"])
    char2 = _char("劫难客")
    char2.realm.tier = 1
    for ft in ("DEATH", "BASE_COLLAPSE", "HEART_DEMON", "WOUNDED"):
        cer2 = build_tribulation_ceremony(char2, _attempt(False, ft))
        assert cer2["result_ref"]["fail_tier"] == ft
        assert cer2["result_ref"]["is_fatal"] is (ft == "DEATH")
        assert all(b["text"].strip() for b in cer2["beats"])
        assert all(b["choices"] is None for b in cer2["beats"])


def test_tr02_tribulation_result_ref_reconciles():
    from core.ceremony import build_tribulation_ceremony

    char = _char("对账劫客")
    char.realm.tier = 2
    att = _attempt(True)
    ref = build_tribulation_ceremony(char, att)["result_ref"]
    assert ref["success"] is True and ref["is_major"] is True
    assert ref["is_fatal"] is False and ref["fail_tier"] is None
    assert ref["prob_pct"] == att["prob_pct"]
    assert ref["judge_source"] == att["judge_source"]
    assert ref["new_realm"] == att["new_realm"]
    assert ref["target_tier"] == 2
    char2 = _char("对账劫客乙")
    char2.realm.tier = 1
    att2 = _attempt(False, "WOUNDED", prob=41.5)
    ref2 = build_tribulation_ceremony(char2, att2)["result_ref"]
    assert ref2["success"] is False and ref2["fail_tier"] == "WOUNDED"
    assert ref2["prob_pct"] == 41.5 and ref2["judge_source"] == "rule"
    # 失败返回无 new_realm 键时口径为「结算后境界名」（§5.4 注明）
    assert ref2["new_realm"] == char2.realm.name
    assert ref2["target_tier"] == 2


def _force_major_char(name="破境客"):
    _token, char = _join(name)
    char = _reload(char.id)
    char.realm.tier = 1
    char.realm.sub_tier = 3
    char.realm.current_exp = char.realm.max_exp
    char.karma.dao_heart = 100
    CharacterRepository.save(char)
    return _token, _reload(char.id)


def _judge(monkeypatch, success):
    from ai.gateway import AIGateway

    monkeypatch.setattr(
        AIGateway, "judge_tribulation",
        staticmethod(lambda c, prob, target: {
            "success": success, "source": "rule", "reason": "",
            "adj_prob": prob,
        }),
    )


def _major_via_handle(token):
    """handle 级大境界真实路径：/突破 先开心魔问心，选项后继段
    （出口②）才 attempt——双幕挂在该出口的响应上。"""
    r1 = WORLD.handle(token, "/突破")
    assert r1.get("pending_heart_demon"), r1
    return WORLD.handle(token, "1")


def test_tr01_tr03_handle_major_success_dual_ceremony(monkeypatch):
    _judge(monkeypatch, True)
    token, char = _force_major_char()
    res = _major_via_handle(token)
    assert res.get("tribulation", {}).get("success"), res
    assert res["ceremony"] and res["ceremony"]["kind"] == "tribulation"
    assert res["ceremony_next"] and res["ceremony_next"]["kind"] == "breakthrough"


def test_tr01_tr03_handle_fatal_has_no_second_ceremony(monkeypatch):
    _judge(monkeypatch, False)
    monkeypatch.setattr(random, "randint", lambda a, b: 1)  # fail_roll≤15 → DEATH
    token, char = _force_major_char("殒落客")
    res = _major_via_handle(token)
    assert res.get("death") is True, res
    assert res["ceremony"] and res["ceremony"]["kind"] == "tribulation"
    assert res["ceremony"]["result_ref"]["is_fatal"] is True
    assert res["ceremony_next"] is None


def test_tr01_handle_minor_breakthrough_no_ceremony(monkeypatch):
    _judge(monkeypatch, True)
    _token, char = _join("小阶客")
    char = _reload(char.id)
    char.realm.tier = 1
    char.realm.sub_tier = 1
    char.realm.current_exp = char.realm.max_exp
    CharacterRepository.save(char)
    res = WORLD._breakthrough(_reload(char.id), None)
    assert res.get("success"), res
    assert res.get("ceremony") is None
    assert res.get("ceremony_next") is None


def test_tr04_fate_choices_only_in_second_ceremony(monkeypatch):
    _judge(monkeypatch, True)
    token, char = _force_major_char("命格客")
    res = _major_via_handle(token)
    assert res.get("tribulation", {}).get("success"), res
    fresh = _reload(char.id)
    assert fresh.fate_pending, "大境界成功必须已抽定命格待选"
    nxt = res["ceremony_next"]
    after = [b for b in nxt["beats"] if b["stage"] == "aftermath"][0]
    assert after["choices"] == list(fresh.fate_pending[0]["candidates"])
    assert nxt["result_ref"]["fate_pending_count"] == len(fresh.fate_pending)
    trib = res["ceremony"]
    assert all(b["choices"] is None for b in trib["beats"])


def test_tr05_skip_equivalence_and_fate_choice_reachable(monkeypatch):
    """C2 后端侧：同播种两路突破最终状态一致；忽略两幕后待选仍可
    经 /命格 择定（TR-06 的后端可达性面，前端略过呈现归前端岗）。"""
    _judge(monkeypatch, True)

    def _run():
        token, char = _force_major_char("等价劫客")
        # 灵根统一口径：命格候选池按灵根首元素过滤，两路须同池可比
        char = _reload(char.id)
        from core.models import Element

        char.spiritual_root.elements = [Element.WATER]
        CharacterRepository.save(char)
        r1 = WORLD.handle(token, "/突破")
        assert r1.get("pending_heart_demon"), r1
        random.seed(20261108)
        res = WORLD.handle(token, "1")
        assert res.get("tribulation", {}).get("success"), res
        assert res["ceremony"] and res["ceremony_next"]
        fresh = _reload(char.id)
        return token, fresh

    token1, f1 = _run()
    _token2, f2 = _run()
    assert (f1.realm.tier, f1.realm.sub_tier, f1.realm.current_exp) == \
        (f2.realm.tier, f2.realm.sub_tier, f2.realm.current_exp)
    assert f1.lifespan.accumulated_gain == f2.lifespan.accumulated_gain
    assert [c["key"] for c in f1.fate_pending[0]["candidates"]] == \
        [c["key"] for c in f2.fate_pending[0]["candidates"]]
    # 双幕皆不看（后端零交互）→ 命盘/命令通道仍可达且走同一选择函数
    key = f1.fate_pending[0]["candidates"][0]["key"]
    pick = WORLD.handle(token1, f"/命格 {key}")
    assert pick.get("ok"), pick
    after = _reload(f1.id)
    assert [b["key"] for b in after.fate_boons] == [key]
    assert after.fate_pending == []


def test_tr07_no_demon_silent_line_and_beats_complete():
    from core.ceremony import build_tribulation_ceremony

    char = _char("守一客")
    char.realm.tier = 2
    cer = build_tribulation_ceremony(char, _attempt(True))
    assert all(b["text"].strip() for b in cer["beats"])
    assert "道心守一" in cer["beats"][1]["text"]  # 无心魔数据 → 定稿静默句
    char2 = _char("殒劫客")
    char2.realm.tier = 1
    cer2 = build_tribulation_ceremony(char2, _attempt(False, "DEATH"))
    assert all(b["text"].strip() for b in cer2["beats"])
    assert "再入轮回" in cer2["beats"][2]["text"]  # 致死桥接句指向死亡幕


def test_tr08_breakthrough_py_diff_empty():
    assert _git_diff("core/breakthrough.py").strip() == "", \
        "core/breakthrough.py 本轮 diff 必须为空（TR-08）"


# ================= BR · S-1/S-2/S-4 =================

def _pending_events(char_id, specs, *, now=None):
    """specs: [(id, npc_name)]，created_at 按列出顺序递增（旧→新）。"""
    t = now if now is not None else time.time()
    evs = []
    for i, (eid, npc) in enumerate(specs):
        evs.append({
            "id": eid, "npc_name": npc, "npc": npc, "type": "provoke",
            "text": f"{npc}有事相商（{eid}）", "options": [],
            "created_at": t + i, "expires_at": t + 100000,
        })
    WorldStateRepository.set(f"drama_pending:{char_id}", evs)
    return evs


def _drama_refs(entry):
    return [q["ref_id"] for q in entry["queue"] if q.get("kind") == "drama"]


def test_br01_pending_latest_first_cap2():
    from core.briefing import build_entry

    now = time.time()
    char = _char("常驻甲")
    _pending_events(char.id, [("ev_old", "旧翁"), ("ev_mid", "中翁"),
                              ("ev_new", "新翁")], now=now)
    entry = build_entry(_reload(char.id), since=0, allow_proactive=False, now=now)
    refs = _drama_refs(entry)
    assert set(refs) == {"ev_new", "ev_mid"} and "ev_old" not in refs
    assert len(refs) <= 2
    # 4 件时恰为最新两件
    char2 = _char("常驻乙")
    _pending_events(char2.id, [("e1", "翁一"), ("e2", "翁二"),
                               ("e3", "翁三"), ("e4", "翁四")], now=now)
    entry2 = build_entry(_reload(char2.id), since=0, allow_proactive=False, now=now)
    assert set(_drama_refs(entry2)) == {"e4", "e3"}


def test_br02_latest_in_highlight_and_relative_order():
    from core.briefing import build_entry

    now = time.time()
    char = _char("高亮客")
    _pending_events(char.id, [("ev_old", "旧翁"), ("ev_mid", "中翁"),
                              ("ev_new", "新翁")], now=now)
    entry = build_entry(_reload(char.id), since=0, allow_proactive=False, now=now)
    refs = _drama_refs(entry)
    assert refs == ["ev_new", "ev_mid"], "同级相对序必须新→旧"
    hl_refs = [q["ref_id"] for q in entry["highlight"]]
    assert "ev_new" in hl_refs, "最新待回应必须进 highlight（未触顶场景）"


def test_br02_truncation_boundary_negative(monkeypatch):
    """触顶负例（§6.3 保证界）：priority≤2 事项塞满 8 条总截断时，
    drama 补列项仍可能被既有截断挤出——本条只断言截断行为与既有
    口径一致（queue ≤8、高优先级在前），不作必含断言。"""
    from core.briefing import build_entry
    from core.karma_chains import KarmaChainEngine

    monkeypatch.setattr(
        KarmaChainEngine, "advance_for",
        staticmethod(lambda c, now=None: [
            {"chain_id": f"c{i}", "action": "resolved", "text": "因果已了"}
            for i in range(8)
        ]),
    )
    now = time.time()
    char = _char("触顶客")
    _pending_events(char.id, [("ev_old", "旧翁"), ("ev_mid", "中翁"),
                              ("ev_new", "新翁")], now=now)
    entry = build_entry(_reload(char.id), since=0, allow_proactive=False, now=now)
    assert len(entry["queue"]) == 8
    assert entry["queue"][0]["kind"] == "karma_resolved"


def test_br03_duplicate_pending_id_deduped_by_self_registration():
    from core.briefing import build_entry

    now = time.time()
    char = _char("去重客")
    # 返回序（旧→新）为 [y, x, x]：逆序补列先取 x、再遇重复 x——
    # 无 S-2 自登记时 x 会被补列两次且占满 cap、y 被挤出。
    _pending_events(char.id, [("ev_y", "乙翁"), ("ev_x", "甲翁"),
                              ("ev_x", "甲翁")], now=now)
    entry = build_entry(_reload(char.id), since=0, allow_proactive=False, now=now)
    refs = _drama_refs(entry)
    assert refs.count("ev_x") == 1, "重复 id 只许补列一次（S-2）"
    assert set(refs) == {"ev_x", "ev_y"}


def test_br04_comment_aligned_and_npc_proactive_diff_empty():
    src = (REPO / "core" / "briefing.py").read_text(encoding="utf-8")
    seg = src[src.index("⑤.6"):src.index("queue.sort")]
    assert "最新优先" in seg and "S-1" in seg and "S-2" in seg
    assert "list_pending" in seg  # 注释点明读口本体不变
    assert _git_diff("core/npc_proactive.py").strip() == "", \
        "core/npc_proactive.py 本轮必须零改动（BR-04）"


def test_br05_list_pending_order_and_login_coexistence(monkeypatch):
    from core.briefing import build_entry
    from core.npc_proactive import DramaEngine

    now = time.time()
    char = _char("共存客")
    evs = _pending_events(char.id, [("ev_old", "旧翁"), ("ev_mid", "中翁"),
                                    ("ev_new", "新翁")], now=now)
    # list_pending 返回序仍为旧→新（本体口径不变）
    pend = DramaEngine.list_pending(_reload(char.id), now=now)
    assert [e["id"] for e in pend] == ["ev_old", "ev_mid", "ev_new"]
    # /回应 面板列序不变（旧→新）
    panel = DramaEngine.panel_text(_reload(char.id), now=now)
    assert panel.index("旧翁") < panel.index("中翁") < panel.index("新翁")
    # 登录路径共存：⑤.5 新建最新件入队后，⑤.6 补列取次新两件、不重复
    monkeypatch.setattr(
        DramaEngine, "evaluate",
        staticmethod(lambda player, trigger="login", now=None: [evs[-1]]),
    )
    entry = build_entry(_reload(char.id), since=0, allow_proactive=True, now=now)
    refs = _drama_refs(entry)
    assert refs.count("ev_new") == 1
    assert set(refs) == {"ev_new", "ev_mid", "ev_old"}
