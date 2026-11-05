"""
转世继承玩法（reincarnation-inheritance）后端测试：R-1~R-11 后端可测条目。
Spec：docs/compose/spec/reincarnation-inheritance.md §4
隔离方式：沿用既有共享 DB 做法（见 test_account_death.py），
用 ri_ 前缀玩家 / npc_ri_ 前缀 NPC + 模块级收尾（本模块角色全部置死）。
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

import pytest

from storage.db import (
    init_db,
    CharacterRepository,
    LegacyRepository,
    KarmaLinkRepository,
    NpcMindRepository,
    PromiseRepository,
)
from core.clock import WorldClock
from core.models import CharacterStatus
from core.legacy import LegacyAccount, LegacyEngine, LifeTrace, ShadowEntry
from core.bounty import KarmaLink
from core.promises import Promise, PromiseEngine, PromiseStatus
from core.npc_mind import ensure_mind
from core.inheritance import (
    applied_shadow_entries,
    apply_karma_shadow,
    causality_text,
    current_karma_shadow,
    find_tombstone,
    tombstone_text,
)
from core.ascension import AscensionEngine
from config import DB_PATH, LEGACY_BOOSTS

init_db()


def _tag():
    return uuid.uuid4().hex[:6]


def _player(name, user=None):
    uid = user or f"ri_{_tag()}_{name}"
    c = WorldClock.create_new_character(uid, f"{name}{_tag()}")
    c.location = "青云坊市客栈"
    CharacterRepository.save(c)
    return c


def _npc(name):
    uid = f"npc_ri_{_tag()}_{name}"
    c = WorldClock.create_new_character(uid, f"{name}{_tag()}")
    c.location = "青云坊市客栈"
    CharacterRepository.save(c)
    ensure_mind(c)
    return c


def _attitude(npc, other_id, value):
    NpcMindRepository.set_attitude(npc.id, other_id, value)


def _att_of(npc_id, other_id):
    mind = NpcMindRepository.get(npc_id) or {}
    return ((mind.get("attitudes") or {}).get(other_id) or {}).get("value", 0)


def _link(a, b, link_type, strength):
    KarmaLinkRepository.save(KarmaLink(
        a_id=a.id, a_name=a.name, b_id=b.id, b_name=b.name,
        link_type=link_type, strength=strength, created_at=time.time(),
    ))


def _tombstone_count(name):
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM world_chronicle WHERE event_type='TOMBSTONE' AND actor_name=?",
        (name,),
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def _trace_with_shadow(npc, value, life_no=1):
    return LifeTrace(
        life_no=life_no, character_id=f"old_{_tag()}", name="前人",
        realm="练气期初期", cause="寿尽坐化",
        shadow=[ShadowEntry(npc_id=npc.id, npc_name=npc.name, value=value)],
    )


@pytest.fixture(autouse=True, scope="module")
def _cleanup_module():
    yield
    try:
        for c in CharacterRepository.list_all_alive():
            if c.user_id.startswith(("ri_", "npc_ri_")):
                c.status = CharacterStatus.DEAD
                CharacterRepository.save(c)
    except Exception:
        pass


# ---------------- R-1 留痕落账 ----------------
def test_r1_trace_capture():
    player = _player("留痕客")
    player.skills.append("御风诀")
    player.inventory.extend(["青锋剑", "聚气丹"])
    player.equipped.append("玄铁护腕")
    player.sect = "青云宗"
    CharacterRepository.save(player)

    npc_hi = _npc("高谊")
    npc_lo = _npc("浅交")
    npc_link = _npc("结仇")
    npc_duan = _npc("断缘")
    _attitude(npc_hi, player.id, 80)     # ≥30 入快照
    _attitude(npc_lo, player.id, -20)    # <30 不入
    _link(player, npc_hi, "恩", 2)       # 折算 +20，与态度 80 合并取大
    _link(player, npc_link, "仇", 3)     # 折算 -30，kind=link
    _link(player, npc_duan, "断", 5)     # 断 → 跳过

    promise = Promise(
        promiser_id=player.id, promiser_name=player.name,
        promisee_id=npc_hi.id, promisee_name=npc_hi.name,
        promisee_is_npc=True, kind="quest",
        desc="3 日内办成一单连环委托（见证）",
        status=PromiseStatus.ACTIVE,
        created_at=time.time(), deadline=time.time() + 10000,
    )
    PromiseRepository.save(promise)
    dissolved = PromiseEngine.on_owner_death(player)
    assert len(dissolved) == 1
    assert dissolved[0]["other_name"] == npc_hi.name
    assert dissolved[0]["role"] == "我许诺"

    account = LegacyAccount(user_id=player.user_id)
    entries_before = AscensionEngine.collect_entries(accounts=[account])
    assert entries_before == []
    res = LegacyEngine.settle_death(
        account, player, death_cause="寿尽坐化", dissolved_promises=dissolved,
    )
    assert len(account.past_lives) == 1
    assert len(account.traces) == 1
    trace = account.traces[-1]
    assert trace.character_id == player.id
    assert trace.life_no == 1
    assert trace.points_gained == res["points_gained"] == account.past_lives[-1].points_gained
    assert trace.sect == "青云宗"
    assert trace.skills_learned == ["御风诀"]
    assert trace.belongings == ["青锋剑", "聚气丹", "玄铁护腕"]
    by_name = {e.npc_name: e for e in trace.shadow}
    assert by_name[npc_hi.name].value == 80
    assert by_name[npc_hi.name].kind == "attitude"
    assert by_name[npc_link.name].value == -30
    assert by_name[npc_link.name].kind == "link"
    assert npc_lo.name not in by_name
    assert npc_duan.name not in by_name
    assert len(trace.open_promises) == 1
    assert trace.open_promises[0].other_name == npc_hi.name
    assert trace.open_promises[0].desc == promise.desc
    assert _tombstone_count(player.name) == 1
    # R-4 飞升榜：trace 不入榜，条目数 == past_lives 数，分数稳定
    entries_after = AscensionEngine.collect_entries(accounts=[account])
    assert len(entries_after) == 1
    entries_again = AscensionEngine.collect_entries(accounts=[account])
    assert entries_again[0]["score"] == entries_after[0]["score"]


# ---------------- R-2 留痕幂等（引擎层重放防线） ----------------
def test_r2_trace_idempotent_on_replay():
    player = _player("重放客")
    account = LegacyAccount(user_id=player.user_id)
    LegacyEngine.settle_death(account, player, death_cause="身死道消")
    assert len(account.traces) == 1
    # MF-1：崩溃重放（先 save(account) 后 save(char) 两步间崩溃重入）——
    # 同角色连调两次，全部账目不变，第二次 points_gained==0
    snapshot = (
        account.points, account.total_points_earned, account.total_lives,
        len(account.past_lives), list(account.death_times), len(account.traces),
    )
    res2 = LegacyEngine.settle_death(account, player, death_cause="身死道消")
    assert res2["points_gained"] == 0
    assert res2["already_settled"] is True
    assert res2["past_life"] is None
    assert (
        account.points, account.total_points_earned, account.total_lives,
        len(account.past_lives), list(account.death_times), len(account.traces),
    ) == snapshot
    assert len(account.traces) == 1
    assert _tombstone_count(player.name) == 1


# ---------------- R-3 影子施加 ----------------
def test_r3_shadow_apply_and_idempotent():
    npc = _npc("影及")
    npc_small = _npc("影微")
    account = LegacyAccount(user_id=f"ri_{_tag()}_acct")
    trace = _trace_with_shadow(npc, 50)
    trace.shadow.append(ShadowEntry(npc_id=npc_small.id, npc_name=npc_small.name, value=10))
    account.traces.append(trace)
    new_char = _player("承影者")
    out = apply_karma_shadow(account, new_char, retention=0.4, cap=25)
    # 50*0.4=20 落账；10*0.4=4 < 8 跳过
    assert out == [{"npc_name": npc.name, "value": 20, "label": "friendly"}]
    assert _att_of(npc.id, new_char.id) == 20
    assert _att_of(npc_small.id, new_char.id) == 0
    assert account.shadow_applied["life_no"] == 1
    assert account.shadow_applied["char_id"] == new_char.id
    # 重复施加：值不翻倍
    out2 = apply_karma_shadow(account, new_char, retention=0.4, cap=25)
    assert out2 == out
    assert _att_of(npc.id, new_char.id) == 20
    # 硬顶：100 → clamp 到 25
    npc_cap = _npc("影顶")
    account2 = LegacyAccount(user_id=f"ri_{_tag()}_acct2")
    account2.traces.append(_trace_with_shadow(npc_cap, 100))
    new2 = _player("承顶者")
    apply_karma_shadow(account2, new2, retention=0.4, cap=25)
    assert _att_of(npc_cap.id, new2.id) == 25
    # 白板对照：无 trace 账户空操作
    blank = LegacyAccount(user_id=f"ri_{_tag()}_blank")
    orphan = _player("白板者")
    assert apply_karma_shadow(blank, orphan, retention=0.4, cap=25) == []
    assert _att_of(npc.id, orphan.id) == 0


# ---------------- MF-4 影子幂等重入按 marker 口径 ----------------
def test_mf4_shadow_reentry_uses_marker_params():
    npc = _npc("影幂等")
    account = LegacyAccount(user_id=f"ri_{_tag()}_acct")
    account.traces.append(_trace_with_shadow(npc, 50))
    new_char = _player("承幂等者")
    out = apply_karma_shadow(account, new_char, retention=0.4, cap=25)
    assert out == [{"npc_name": npc.name, "value": 20, "label": "friendly"}]
    assert _att_of(npc.id, new_char.id) == 20
    # 以不同参数重调：返回值须与首次一致（20 而非 50*0.75≈38），DB 不变
    out2 = apply_karma_shadow(account, new_char, retention=0.75, cap=50)
    assert out2 == out
    assert out2[0]["value"] == 20
    assert _att_of(npc.id, new_char.id) == 20


# ---------------- 观察4 展示口径：低于施加门槛不呈现 ----------------
def test_obs4_small_link_value_not_presented():
    account = LegacyAccount(user_id=f"ri_{_tag()}_obs4")
    trace = LifeTrace(
        life_no=1, character_id=f"old_{_tag()}", name="小值前人",
        realm="练气期初期", cause="寿尽坐化",
        # link 折算小值：15*0.4=6 < SHADOW_APPLY_MIN=8，实际从未落账
        shadow=[ShadowEntry(npc_id=f"npc_gone_{_tag()}", npc_name="小值缘客", value=15, kind="link")],
    )
    account.traces.append(trace)
    assert applied_shadow_entries(account, trace) == []
    text = causality_text(account)
    assert "本世 +6" not in text
    assert "小值缘客" not in text


# ---------------- R-5/R-6/R-7 抉择 ----------------
def _boost_account(points):
    account = LegacyAccount(user_id=f"ri_{_tag()}_boost", points=points)
    trace = LifeTrace(
        life_no=1, character_id=f"old_{_tag()}", name="旧世",
        realm="练气期初期", cause="寿尽坐化",
        skills_learned=["御风诀"], belongings=["青锋剑", "聚气丹"],
    )
    account.traces.append(trace)
    return account, trace


def test_r5_boost_limit_claims_and_bond_flag():
    # 超 3 项被拒（既有口径），不扣点
    account, trace = _boost_account(30)
    char = _player("贪求者")
    res = LegacyEngine.apply_birth_boosts(
        char, account, ["stones", "lifespan", "root", "skill"], old_trace=trace,
    )
    assert res["success"] is False
    assert account.points == 30
    # 三项新抉择同选可成，各自 claims 落账
    account2, trace2 = _boost_account(20)
    char2 = _player("全承者")
    res2 = LegacyEngine.apply_birth_boosts(
        char2, account2, ["heirloom:青锋剑", "art_memory", "bond_echo"], old_trace=trace2,
    )
    assert res2["success"] is True
    assert res2["bond_echo"] is True
    assert account2.points == 20 - 12
    assert account2.inheritance_claims == {"heirloom": 1, "art_memory": 1}
    assert char2.inventory.count("青锋剑") == 1
    assert "御风诀" in char2.skills
    # 点数不足：对应项失败、不扣点、不置 claims
    account3, trace3 = _boost_account(4)
    char3 = _player("囊涩者")
    res3 = LegacyEngine.apply_birth_boosts(
        char3, account3, ["heirloom:青锋剑"], old_trace=trace3,
    )
    assert res3["success"] is False
    assert account3.points == 4
    assert account3.inheritance_claims == {}
    assert "青锋剑" not in char3.inventory


def test_r6_r7_heirloom_constraints_and_reentry():
    account, trace = _boost_account(30)
    char = _player("承物者")
    # R-7：不在候选池 → 报错不扣点
    res = LegacyEngine.apply_birth_boosts(
        char, account, ["heirloom:斩仙剑"], old_trace=trace,
    )
    assert res["success"] is False and res["errors"]
    assert account.points == 30 and "斩仙剑" not in char.inventory
    # 裸 heirloom（无 param）→ 报错不扣点
    res = LegacyEngine.apply_birth_boosts(char, account, ["heirloom"], old_trace=trace)
    assert res["success"] is False and account.points == 30
    # 成功：恰 1 份、未穿戴
    res = LegacyEngine.apply_birth_boosts(
        char, account, ["heirloom:青锋剑"], old_trace=trace,
    )
    assert res["success"] is True
    assert char.inventory.count("青锋剑") == 1
    assert "青锋剑" not in char.equipped
    # R-6：同世重领被拒，物品不复制
    res = LegacyEngine.apply_birth_boosts(
        char, account, ["heirloom:聚气丹"], old_trace=trace,
    )
    assert res["success"] is False
    assert char.inventory.count("青锋剑") == 1
    assert "聚气丹" not in char.inventory
    # art_memory 同理：首领成功、重领被拒
    res = LegacyEngine.apply_birth_boosts(char, account, ["art_memory"], old_trace=trace)
    assert res["success"] is True and "御风诀" in char.skills
    n_skills = len(char.skills)
    res = LegacyEngine.apply_birth_boosts(char, account, ["art_memory"], old_trace=trace)
    assert res["success"] is False
    assert len(char.skills) == n_skills
    # 非 heirloom 带 param 视为非法
    account2, trace2 = _boost_account(30)
    char2 = _player("乱参者")
    res = LegacyEngine.apply_birth_boosts(char2, account2, ["stones:青锋剑"], old_trace=trace2)
    assert res["success"] is False and account2.points == 30


# ---------------- MF-2 skill+art_memory 同批不空扣、正反序一致 ----------------
def test_mf2_skill_and_art_memory_both_orders():
    # _boost_account 的 trace.skills_learned 首门恰为残篇表首门「御风诀」
    results = []
    for order in (["skill", "art_memory"], ["art_memory", "skill"]):
        account, trace = _boost_account(20)
        char = _player("双承者")
        before = set(char.skills)
        res = LegacyEngine.apply_birth_boosts(char, account, order, old_trace=trace)
        assert res["success"] is True, (order, res)
        assert res["spent"] == 6 and account.points == 20 - 6
        gained = [s for s in char.skills if s not in before]
        assert len(gained) == 2 and len(set(gained)) == 2, (order, gained)
        assert set(gained) == {"御风诀", "龟息敛气术"}
        # claims 只记 art_memory 一次（skill 不置 claims）
        assert account.inheritance_claims == {"art_memory": 1}
        results.append(set(gained))
    assert results[0] == results[1]


def test_art_memory_without_trace_rejected():
    # 观察1：无前世痕迹领 art_memory → 报错、不扣点、不置 claims
    account = LegacyAccount(user_id=f"ri_{_tag()}_notrace", points=20)
    char = _player("无痕者")
    before = list(char.skills)
    res = LegacyEngine.apply_birth_boosts(char, account, ["art_memory"])
    assert res["success"] is False
    assert any("无前世痕迹" in e for e in res["errors"])
    assert account.points == 20
    assert "art_memory" not in account.inheritance_claims
    assert char.skills == before


# ---------------- R-8 bond_echo 对照 ----------------
def test_r8_bond_echo_shadow_values():
    npc = _npc("旧缘人")
    # 基准：60*0.4=24
    acc_base = LegacyAccount(user_id=f"ri_{_tag()}_base")
    acc_base.traces.append(_trace_with_shadow(npc, 60))
    char_base = _player("基准承者")
    apply_karma_shadow(acc_base, char_base, retention=0.4, cap=25)
    assert _att_of(npc.id, char_base.id) == 24
    # bond_echo：60*0.75=45（cap 50 不截断）
    acc_bond = LegacyAccount(user_id=f"ri_{_tag()}_bond")
    acc_bond.traces.append(_trace_with_shadow(npc, 60))
    char_bond = _player("重续承者")
    apply_karma_shadow(acc_bond, char_bond, retention=0.75, cap=50)
    assert _att_of(npc.id, char_bond.id) == 45
    # current_karma_shadow 按实际施加口径重算展示
    shown = current_karma_shadow(acc_bond)
    assert shown and shown[0]["value"] == 45 and shown[0]["from_life"] == 1


# ---------------- R-10 墓碑 ----------------
def test_r10_tombstone_lookup():
    player = _player("碑下客")
    account = LegacyAccount(user_id=player.user_id)
    LegacyRepository.save(account)
    LegacyEngine.settle_death(account, player, death_cause="渡劫陨落")
    LegacyRepository.save(account)
    text = find_tombstone(player.name)
    assert text is not None
    assert player.name in text and "渡劫陨落" in text
    assert text == tombstone_text(account.traces[-1])
    assert find_tombstone(f"无此道号{_tag()}") is None


# ---------------- R-11 旧存档兼容 ----------------
def test_r11_old_save_compat():
    old = LegacyAccount.model_validate_json('{"user_id": "ri_old_compat", "points": 7}')
    assert old.traces == [] and old.shadow_applied == {} and old.inheritance_claims == {}
    # 旧角色（无 trace）死亡全流程不报错、影子为空
    char = _player("旧档客")
    res = LegacyEngine.settle_death(old, char, death_cause="寿尽坐化")
    assert res["success"] is True
    assert old.traces[-1].shadow == []
    blank = LegacyAccount(user_id=f"ri_{_tag()}_old2")
    assert apply_karma_shadow(blank, char, retention=0.4, cap=25) == []
    # 旧四 boost 行为不变
    acc = LegacyAccount(user_id=f"ri_{_tag()}_old3", points=10)
    char2 = _player("旧规客")
    r = LegacyEngine.apply_birth_boosts(char2, acc, ["stones"])
    assert r["success"] is True and acc.points == 9 and r["bond_echo"] is False


def test_boost_catalog_order_frozen():
    # 既有四键顺序与数值零变更，新键只追加末尾（数字序号映射铁律）
    assert list(LEGACY_BOOSTS.keys()) == [
        "stones", "lifespan", "root", "skill", "heirloom", "art_memory", "bond_echo",
    ]
    assert [LEGACY_BOOSTS[k]["cost"] for k in LEGACY_BOOSTS] == [1, 2, 4, 2, 5, 4, 3]


def test_cli_parse_boost_keys():
    from cli.main import _parse_boost_keys

    assert _parse_boost_keys("5") == ["heirloom"]
    assert _parse_boost_keys("6") == ["art_memory"]
    assert _parse_boost_keys("7") == ["bond_echo"]
    assert _parse_boost_keys("heirloom:青锋剑 6") == ["heirloom:青锋剑", "art_memory"]
    assert _parse_boost_keys("1 2") == ["stones", "lifespan"]


# ---------------- R-9/R-2/R-10 server 集成 ----------------
def test_r9_server_integration():
    from server.world import World

    w = World(auto_tick=False)
    uid = f"ri_{_tag()}_srv"
    name = f"集成客{_tag()}"
    joined = w.join(name, user_id=uid)
    token = joined["token"]
    char = CharacterRepository.get_by_user_id(uid)
    assert char is not None and char.name == name

    npc = _npc("集成缘")
    _attitude(npc, char.id, 50)

    dead = CharacterRepository.get_by_user_id(uid)
    dead.status = CharacterStatus.DEAD
    CharacterRepository.save(dead)
    settle = w._settle_if_needed(dead, cause="寿尽坐化")
    assert settle is not None
    # R-2：server 编排重入不双记
    again = w._settle_if_needed(CharacterRepository.get_by_user_id(uid), cause="寿尽坐化")
    assert again is None or not again.get("points_gained")
    account = LegacyRepository.get_or_create(uid)
    assert len(account.traces) == 1
    assert _tombstone_count(name) == 1

    # dead_payload.legacy 补 trace 与 past_lives
    payload = w.dead_payload(uid)
    assert payload is not None and payload["dead"] is True
    assert payload["legacy"]["trace"] is not None
    assert payload["legacy"]["trace"]["name"] == name
    assert len(payload["legacy"]["past_lives"]) == 1

    # legacy_info 补 traces / karma_shadow
    info = w.legacy_info(token)
    assert info["ok"] and len(info["traces"]) == 1
    assert info["traces"][0]["shadow_count"] == 1
    assert isinstance(info["karma_shadow"], list)
    info_id = w.legacy_info_id(uid)
    assert len(info_id["traces"]) == 1 and "karma_shadow" in info_id

    # _status_dict past_life 四键
    st = w._status_dict(CharacterRepository.get_by_user_id(uid))
    assert st["past_life"]["lives"] == 1
    assert st["past_life"]["last_name"] == name
    assert st["past_life"]["last_cause"] == "寿尽坐化"
    assert st["past_life"]["shadow_count"] == 1

    # /道统 文本含前世因果段；/前世 别名同源
    legacy_res = w.handle(token, "/道统")
    assert "前世因果" in (legacy_res.get("text") or "")
    alias_res = w.handle(token, "/前世")
    assert "前世因果" in (alias_res.get("text") or "")

    # /墓碑：他人 token 查得同源文本；查无 → 江湖无此碑
    guest = w.join(f"访碑客{_tag()}")
    tomb_res = w.handle(guest["token"], f"/墓碑 {name}")
    assert tomb_res["ok"] and tomb_res["text"] == find_tombstone(name)
    none_res = w.handle(guest["token"], f"/墓碑 无此道号{_tag()}")
    assert none_res["ok"] and none_res["text"] == "江湖无此碑。"

    # 转世：响应带 karma_shadow，NPC 对新角态度 == 50*0.4 = 20
    reborn = w.reincarnate(token, name=f"承集成{_tag()}", boosts=[])
    assert reborn["ok"] is True
    shadow = reborn.get("karma_shadow")
    assert shadow and shadow[0]["npc_name"] == npc.name and shadow[0]["value"] == 20
    new_char = CharacterRepository.get_by_user_id(uid)
    assert new_char is not None and new_char.id != char.id
    assert _att_of(npc.id, new_char.id) == 20
    # 活角重入转世被「此世尚存」拦截（既有）
    blocked = w.reincarnate(token, name="再转者", boosts=[])
    assert blocked["ok"] is False
