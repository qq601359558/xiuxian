"""F14 诺言账闭环：立诺/应诺/四类事实核验/到期结算/幂等/死亡消散/毁诺/交谈不立诺/双端/旧档兼容"""
import os
import sys
import time
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import DB_PATH, EVENT_EFFECT_CAPS
from core.clock import WorldClock
from core.models import CharacterStatus, QuestChain, QuestRing
from core.promises import (
    Promise,
    PromiseEngine,
    PromiseStatus,
    PROMISE_ACCEPT_TTL_SECONDS,
    PROMISE_ATTITUDE_DELTA,
    PROMISE_KINDS,
    PROMISE_MAX_OPEN,
    PROMISE_MERIT_KEPT,
    PROMISE_SIN_BROKEN,
)
from core.chat_actions import do_gift, execute_chat_action
from core.combat_fate import CombatFateEngine
from core.npc_mind import attitude_toward
from core.quests import QuestEngine, QUEST_CHAIN_TTL_SECONDS, QUEST_REWARD_MERIT
from storage.db import (
    CharacterRepository,
    KarmaLinkRepository,
    PromiseRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"
LOC_B = "落霞山灵泉"


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _tag() -> str:
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name="立诺客", location=LOC_A, old=False):
    c = WorldClock.create_new_character(f"promise_{_uniq(name)}", f"{name}{_tag()}")
    c.location = location
    if old:
        c.born_at = time.time() - 80 * 3600.0  # 过新手庇护，斗法可出手
    CharacterRepository.save(c)
    return c


def _npc(name="诺言翁", location=LOC_A, old=False):
    c = WorldClock.create_new_character(f"npc_promise_{_uniq(name)}", f"{name}{_tag()}")
    c.location = location
    if old:
        c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def _cleanup(*chars):
    """零残留：删诺行、自造角色处决（与 F08/F09 夹具口径一致）"""
    for c in chars:
        if c is None:
            continue
        for p in PromiseRepository.list_all():
            if c.id in (p.promiser_id, p.promisee_id):
                PromiseRepository.delete(p.id)
        c.status = CharacterStatus.DEAD
        CharacterRepository.save(c)


def _get(pid: str) -> Promise:
    for p in PromiseRepository.list_all():
        if p.id == pid:
            return p
    raise AssertionError(f"promise {pid} 不在库中")


def _set_deadline(pid: str, deadline: float):
    p = _get(pid)
    p.deadline = deadline
    PromiseRepository.save(p)


def _links_between(a_id: str, b_id: str):
    return [
        l for l in KarmaLinkRepository.list_all()
        if l.link_type == "诺" and {l.a_id, l.b_id} == {a_id, b_id}
    ]


# ---------------- 常量与立诺成立条件 ----------------

def test_constants_within_caps():
    assert PROMISE_MERIT_KEPT <= EVENT_EFFECT_CAPS["merit"]
    assert PROMISE_SIN_BROKEN <= EVENT_EFFECT_CAPS["sin"]
    assert PROMISE_KINDS["gift"]["ttl"] == 3 * 86400.0
    assert PROMISE_KINDS["no_attack"]["ttl"] == 7 * 86400.0
    print("✓ 常量在 EVENT_EFFECT_CAPS 内")


def test_make_npc_promise_active_immediately():
    p = _char("立诺甲")
    npc = _npc("受诺翁")
    t0 = time.time()
    res = PromiseEngine.make_promise(p, npc, "quest", now=t0)
    assert res["success"], res
    pr = res["promise"]
    assert pr.status == PromiseStatus.ACTIVE
    assert pr.activated_at == t0
    assert abs(pr.deadline - (t0 + 3 * 86400.0)) < 1e-6
    assert pr.promisee_is_npc is True
    _cleanup(p, npc)
    print("✓ NPC 立诺即生效，期限写死")


def test_make_validation():
    p = _char("立诺乙")
    far = _npc("远方翁", location=LOC_B)
    res = PromiseEngine.make_promise(p, far, "quest")
    assert not res["success"] and "当面" in res["message"]  # 不同场
    res = PromiseEngine.make_promise(p, p, "quest")
    assert not res["success"]  # 对自己
    npc = _npc("近翁")
    res = PromiseEngine.make_promise(p, npc, "gift", "")
    assert not res["success"]  # 赠物无物品名
    other = _char("玩家友", location=LOC_A)
    res = PromiseEngine.make_promise(p, other, "gift", "聚灵草")
    assert not res["success"] and "只可对同场 NPC" in res["message"]  # 赠物对玩家拒绝
    res = PromiseEngine.make_promise(p, npc, "arrive", "不存在的山")
    assert not res["success"]  # 未知地点
    res = PromiseEngine.make_promise(p, npc, "arrive", "客栈")
    assert not res["success"] and "已身在" in res["message"]  # 已在目标地
    res = PromiseEngine.make_promise(p, npc, "arrive", "落霞")
    assert res["success"], res
    assert res["promise"].param == LOC_B  # 子串解析为地点全名
    dead = _npc("亡翁")
    dead.status = CharacterStatus.DEAD
    CharacterRepository.save(dead)
    p2 = _char("立诺丙")
    res = PromiseEngine.make_promise(p2, dead, "quest")
    assert not res["success"]  # 对象已死
    _cleanup(p, far, npc, other, dead, p2)
    print("✓ 立诺成立条件：同场/对象/类型/地点全校验")


def test_make_cap_and_dup():
    p = _char("连立客")
    n1, n2, n3, n4 = _npc("翁一"), _npc("翁二"), _npc("翁三"), _npc("翁四")
    assert PromiseEngine.make_promise(p, n1, "quest")["success"]
    res = PromiseEngine.make_promise(p, n1, "quest")
    assert not res["success"] and "不可叠诺" in res["message"]  # 同对象同类型
    assert PromiseEngine.make_promise(p, n2, "quest")["success"]
    assert PromiseEngine.make_promise(p, n3, "no_attack")["success"]
    res = PromiseEngine.make_promise(p, n4, "quest")
    assert not res["success"] and "上限" in res["message"]  # 第 4 条触上限
    assert len(PromiseEngine._open_of(p.id)) == PROMISE_MAX_OPEN
    _cleanup(p, n1, n2, n3, n4)
    print("✓ 未结上限 3 + 同对象同类型防叠诺")


# ---------------- 玩家确认流 ----------------

def test_player_pending_accept_flow():
    p1 = _char("立诺丁")
    p2 = _char("应诺友")
    t0 = time.time()
    res = PromiseEngine.make_promise(p1, p2, "no_attack", now=t0)
    assert res["success"], res
    pr = res["promise"]
    assert pr.status == PromiseStatus.PENDING and pr.deadline == 0.0  # 待应诺、期限未起算
    res = PromiseEngine.accept(p2, now=t0 + 10)
    assert res["success"], res
    pr = _get(pr.id)
    assert pr.status == PromiseStatus.ACTIVE
    assert abs(pr.deadline - (t0 + 10 + 7 * 86400.0)) < 1e-6  # 期限自应诺起算
    p2r = CharacterRepository.get_by_id(p2.id)
    assert p2r.karma.merit_value == 0 and p2r.karma.sin_value == 0  # 应诺方无义务无账
    res = PromiseEngine.accept(p2)
    assert not res["success"]  # 无待应诺再应
    _cleanup(p1, p2)
    print("✓ 玩家诺 PENDING→应诺→ACTIVE，期限自应诺起算")


def test_accept_needs_hint_when_multiple():
    p1, p3 = _char("立诺戊"), _char("立诺己")
    p2 = _char("众诺友")
    assert PromiseEngine.make_promise(p1, p2, "quest")["success"]
    assert PromiseEngine.make_promise(p3, p2, "arrive", "落霞")["success"]
    res = PromiseEngine.accept(p2)
    assert not res["success"] and "指明" in res["message"]
    res = PromiseEngine.accept(p2, p1.name)
    assert res["success"], res
    res = PromiseEngine.accept(p2, p3.name)
    assert res["success"], res
    _cleanup(p1, p3, p2)
    print("✓ 多条待应诺须指明立诺者")


def test_pending_expires_dissolved():
    p1 = _char("立诺庚")
    p2 = _char("不应友")
    t0 = time.time()
    pr = PromiseEngine.make_promise(p1, p2, "quest", now=t0)["promise"]
    changed = PromiseEngine.settle_due(p1, now=t0 + PROMISE_ACCEPT_TTL_SECONDS + 1)
    assert changed
    pr = _get(pr.id)
    assert pr.status == PromiseStatus.DISSOLVED
    p1r = CharacterRepository.get_by_id(p1.id)
    assert p1r.karma.sin_value == 0 and p1r.karma.merit_value == 0  # 未成之诺无功无过
    _cleanup(p1, p2)
    print("✓ 待应诺逾一日未应 → 消散，无结算")


# ---------------- 赠物诺（真实赠礼路径） ----------------

def test_gift_fulfilled_via_real_gift():
    p = _char("赠诺客")
    npc = _npc("受赠翁")
    pr = PromiseEngine.make_promise(p, npc, "gift", "聚灵草")["promise"]
    # 先赠错物：不践诺
    p.inventory.append("灵谷")
    CharacterRepository.save(p)
    res = do_gift(p, npc, "灵谷", 0)
    assert res["ok"], res
    assert _get(pr.id).status == PromiseStatus.ACTIVE
    assert attitude_toward(npc, p.id)["value"] == 7  # 赠礼本身态度 +7（与诺无关）
    # 真赠诺物 → 践诺
    p = CharacterRepository.get_by_id(p.id)
    p.inventory.append("聚灵草")
    CharacterRepository.save(p)
    merit0 = p.karma.merit_value
    res = do_gift(p, npc, "聚灵草", 0)
    assert res["ok"] and "践诺" in res["text"], res
    assert _get(pr.id).status == PromiseStatus.KEPT
    pr2 = CharacterRepository.get_by_id(p.id)
    assert pr2.karma.merit_value == merit0 + PROMISE_MERIT_KEPT  # 功德恰 +10
    # 因果链留痕（诺）+ NPC 态度：两次赠礼各 +7，践诺另 +8，合计 +22
    links = _links_between(p.id, npc.id)
    assert len(links) == 1 and links[0].note.startswith("践诺")
    assert attitude_toward(npc, p.id)["value"] == 7 + 7 + PROMISE_ATTITUDE_DELTA
    # 重复赠同物不再重复结算
    p = CharacterRepository.get_by_id(p.id)
    p.inventory.append("聚灵草")
    CharacterRepository.save(p)
    merit1 = p.karma.merit_value
    res = do_gift(p, npc, "聚灵草", 0)
    assert res["ok"] and "践诺" not in res["text"]
    assert CharacterRepository.get_by_id(p.id).karma.merit_value == merit1
    assert len(_links_between(p.id, npc.id)) == 1
    _cleanup(p, npc)
    print("✓ 赠物诺：真赠礼践诺（功德/态度/因果链），错赠不算，重复不重结")


def test_gift_after_deadline_breaks():
    p = _char("迟赠客")
    npc = _npc("久等翁")
    pr = PromiseEngine.make_promise(p, npc, "gift", "聚灵草")["promise"]
    _set_deadline(pr.id, time.time() - 5)  # 期限已过
    p.inventory.append("聚灵草")
    CharacterRepository.save(p)
    res = do_gift(p, npc, "聚灵草", 0)
    assert res["ok"] and "践诺" not in res["text"]  # 迟赠不践诺
    assert _get(pr.id).status == PromiseStatus.BROKEN
    pr2 = CharacterRepository.get_by_id(p.id)
    assert pr2.karma.sin_value == PROMISE_SIN_BROKEN and pr2.karma.merit_value == 0
    _cleanup(p, npc)
    print("✓ 逾期后赠物 → 按违约结算，不补践诺")


# ---------------- 委托诺（真实交付路径） ----------------

def test_quest_fulfilled_via_real_deliver():
    p = _char("办诺客")
    npc = _npc("托事翁")
    pr = PromiseEngine.make_promise(p, npc, "quest")["promise"]
    now = time.time()
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=npc.id,
                     deliver_npc_name=npc.name, item_name="聚灵草", need=1)
    p.active_quest = QuestChain(
        publisher_id=npc.id, publisher_name=npc.name, rings=[ring], ring_index=0,
        accepted_at=now, expires_at=now + QUEST_CHAIN_TTL_SECONDS,
        reward_stones=100, reward_merit=QUEST_REWARD_MERIT,
    )
    p.inventory.append("聚灵草")
    CharacterRepository.save(p)
    res = QuestEngine.deliver(p)
    assert res["success"] and res.get("completed"), res
    assert "践诺" in res["message"]
    assert _get(pr.id).status == PromiseStatus.KEPT
    p2 = CharacterRepository.get_by_id(p.id)
    # 功德 = 委托赏 5 + 践诺 10（add_merit 口径，sin 为 0 无干扰）
    assert p2.karma.merit_value == QUEST_REWARD_MERIT + PROMISE_MERIT_KEPT
    _cleanup(p, npc)
    print("✓ 委托诺：整链真实交付践诺，功德与委托赏分账可对")


# ---------------- 抵达诺（引擎钩子 + 到期） ----------------

def test_arrive_fulfilled_by_hook():
    p = _char("赴诺客")
    npc = _npc("见证翁")
    pr = PromiseEngine.make_promise(p, npc, "arrive", "落霞")["promise"]
    assert PromiseEngine.note_arrival(p, LOC_A) is None  # 落点不符不践
    assert _get(pr.id).status == PromiseStatus.ACTIVE
    msg = PromiseEngine.note_arrival(p, LOC_B)
    assert msg and "践诺" in msg
    assert _get(pr.id).status == PromiseStatus.KEPT
    assert CharacterRepository.get_by_id(p.id).karma.merit_value == PROMISE_MERIT_KEPT
    _cleanup(p, npc)
    print("✓ 抵达诺：落点命中践诺，不符不算")


def test_expiry_broken_and_idempotent():
    p = _char("失诺客")
    npc = _npc("望诺翁")
    t0 = time.time()
    pr = PromiseEngine.make_promise(p, npc, "arrive", "落霞", now=t0)["promise"]
    t1 = t0 + 3 * 86400.0 + 1
    assert PromiseEngine.settle_due(p, now=t1)
    pr = _get(pr.id)
    assert pr.status == PromiseStatus.BROKEN and "期满未践诺" in pr.settle_note
    pr2 = CharacterRepository.get_by_id(p.id)
    assert pr2.karma.sin_value == PROMISE_SIN_BROKEN and pr2.karma.merit_value == 0
    # 幂等：再推进/再开面板/迟到的钩子都不重复结算
    assert not PromiseEngine.settle_due(p, now=t1 + 100)
    assert PromiseEngine.note_arrival(p, LOC_B, now=t1 + 200) is None
    pr3 = CharacterRepository.get_by_id(p.id)
    assert pr3.karma.sin_value == PROMISE_SIN_BROKEN
    links = _links_between(p.id, npc.id)
    assert len(links) == 1 and links[0].note.startswith("违约")
    # 违约入世情播报
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT data_json FROM jianghu_events WHERE kind='promise' AND data_json LIKE ?",
        (f"%{p.name}%",),
    ).fetchall()
    conn.close()
    assert rows and "背诺" in rows[0][0]
    _cleanup(p, npc)
    print("✓ 到期违约：业力恰 +15、世情播报、结算幂等")


# ---------------- 不攻诺（真实斗法路径） ----------------

def test_no_attack_breach_via_real_combat():
    a = _char("毁诺客", location=LOC_B, old=True)
    npc = _npc("受诺长者", location=LOC_B, old=True)
    pr = PromiseEngine.make_promise(a, npc, "no_attack")["promise"]
    res = CombatFateEngine.resolve_ambush(a, npc)
    assert res["success"], res
    assert "诺破" in res["report"], res["report"]
    assert _get(pr.id).status == PromiseStatus.BROKEN
    a2 = CharacterRepository.get_by_id(a.id)
    assert a2.karma.sin_value >= PROMISE_SIN_BROKEN  # 斗法本身或另有业力，只断下限
    links = _links_between(a.id, npc.id)
    assert len(links) == 1 and links[0].note.startswith("违约")
    _cleanup(a, npc)
    print("✓ 不攻诺：真实斗法出手当场判毁诺，战报明示")


def test_no_attack_expires_kept():
    a = _char("守诺客", location=LOC_B, old=True)
    npc = _npc("安坐翁", location=LOC_B, old=True)
    t0 = time.time()
    pr = PromiseEngine.make_promise(a, npc, "no_attack", now=t0)["promise"]
    assert PromiseEngine.settle_due(a, now=t0 + 7 * 86400.0 + 1)
    assert _get(pr.id).status == PromiseStatus.KEPT
    assert CharacterRepository.get_by_id(a.id).karma.merit_value == PROMISE_MERIT_KEPT
    _cleanup(a, npc)
    print("✓ 不攻诺：期满未出手自动践诺")


def test_attack_after_expiry_not_breach():
    a = _char("期后客", location=LOC_B, old=True)
    npc = _npc("期后翁", location=LOC_B, old=True)
    pr = PromiseEngine.make_promise(a, npc, "no_attack")["promise"]
    _set_deadline(pr.id, time.time() - 5)  # 诺期已满（期内未出手）
    res = CombatFateEngine.resolve_ambush(a, npc)
    assert res["success"], res
    assert "诺破" not in res["report"]
    assert _get(pr.id).status == PromiseStatus.KEPT  # 先按履约结算，本次出手不背诺
    _cleanup(a, npc)
    print("✓ 诺期已满后出手：先践诺，不判违约")


def test_blocked_attack_not_breach():
    # 安全区出手被硬拦（未遂）→ 不算出手，诺不破
    a = _char("未遂客", location=LOC_A, old=True)
    npc = _npc("坊市翁", location=LOC_A, old=True)
    pr = PromiseEngine.make_promise(a, npc, "no_attack")["promise"]
    res = CombatFateEngine.resolve_ambush(a, npc)
    assert not res["success"]  # 安全区硬拦
    assert _get(pr.id).status == PromiseStatus.ACTIVE
    _cleanup(a, npc)
    print("✓ 被硬拦的未遂出手不判违约")


# ---------------- 毁诺 / 死亡消散 ----------------

def test_break_promise_paths():
    p = _char("毁诺人")
    npc = _npc("被毁翁")
    pr = PromiseEngine.make_promise(p, npc, "quest")["promise"]
    res = PromiseEngine.break_promise(p)
    assert res["success"], res
    assert _get(pr.id).status == PromiseStatus.BROKEN
    assert CharacterRepository.get_by_id(p.id).karma.sin_value == PROMISE_SIN_BROKEN
    # 待应诺者毁诺 = 撤回，无代价
    p2 = _char("收诺友")
    pr2 = PromiseEngine.make_promise(p, p2, "quest")["promise"]
    assert pr2.status == PromiseStatus.PENDING
    res = PromiseEngine.break_promise(p, p2.name)
    assert res["success"] and "撤回" in res["message"]
    assert _get(pr2.id).status == PromiseStatus.DISSOLVED
    assert CharacterRepository.get_by_id(p.id).karma.sin_value == PROMISE_SIN_BROKEN  # 未叠加
    _cleanup(p, npc, p2)
    print("✓ 毁诺：已生效同额违约，待应诺无代价撤回")


def test_death_dissolves_both_directions():
    # 立诺者身死 → on_owner_death 消散
    p = _char("殁诺客")
    npc = _npc("送殁翁")
    pr = PromiseEngine.make_promise(p, npc, "quest")["promise"]
    PromiseEngine.on_owner_death(p)
    assert _get(pr.id).status == PromiseStatus.DISSOLVED
    assert CharacterRepository.get_by_id(p.id).karma.sin_value == 0
    # 受诺人身死 → 惰性消散，不判违约
    p2 = _char("守殁客")
    npc2 = _npc("先殁翁")
    pr2 = PromiseEngine.make_promise(p2, npc2, "quest")["promise"]
    npc2.status = CharacterStatus.DEAD
    CharacterRepository.save(npc2)
    assert PromiseEngine.settle_due(p2)
    assert _get(pr2.id).status == PromiseStatus.DISSOLVED
    p2r = CharacterRepository.get_by_id(p2.id)
    assert p2r.karma.sin_value == 0 and p2r.karma.merit_value == 0
    assert _links_between(p2.id, npc2.id) == []  # 消散不写因果链
    _cleanup(p, npc, p2, npc2)
    print("✓ 死亡口径：任一方身死 → 消散，无功无过不留链")


# ---------------- 交谈不立诺 ----------------

def test_chat_text_creates_no_promise():
    p = _char("口诺客")
    npc = _npc("听诺翁")
    p.inventory.append("聚灵草")
    CharacterRepository.save(p)
    # 口头应承（哪怕说得再像）+ AI 式应答文本都不产生诺言
    res = execute_chat_action(p, npc, "我答应你，三日之内必为你办成此事，你放一百个心。", use_ai_classify=False)
    assert res["ok"], res
    assert PromiseRepository.list_all() == [] or all(
        p.id not in (x.promiser_id, x.promisee_id) for x in PromiseRepository.list_all()
    )
    assert _links_between(p.id, npc.id) == []
    panel = PromiseEngine.panel_text(CharacterRepository.get_by_id(p.id))
    assert "口头应承" in panel and "眼下无未结之诺" in panel
    _cleanup(p, npc)
    print("✓ 交谈口头应承不立诺（面板明示口径）")


# ---------------- 面板 / 旧档兼容 ----------------

def test_panel_and_legacy_compat():
    p = _char("观账客")
    npc = _npc("账上翁")
    PromiseEngine.make_promise(p, npc, "gift", "灵谷")
    panel = PromiseEngine.panel_text(CharacterRepository.get_by_id(p.id))
    assert "我立之诺" in panel and "灵谷" in panel
    # 旧式最小 JSON（缺新字段）可反序列化补默认——旧档行不炸
    legacy = Promise.model_validate_json(
        '{"promiser_id": "x1", "promiser_name": "甲", "promisee_id": "y1", "promisee_name": "乙"}'
    )
    assert legacy.status == PromiseStatus.PENDING and legacy.kind == "quest" and legacy.param == ""
    # 仓储往返
    PromiseRepository.save(legacy)
    got = _get(legacy.id)
    assert got.promiser_name == "甲"
    PromiseRepository.delete(legacy.id)
    _cleanup(p, npc)
    print("✓ 面板呈现 + 旧档最小行兼容 + 仓储往返")


# ---------------- server 双端 handle ----------------

def test_server_handle_flow_and_meditation_lock():
    r = WORLD.join(f"诺言服客{_uniq('')}")
    tok = r["token"]
    char = WORLD.get_char(tok)
    npc = _npc("服内诺翁", location=char.location)
    res = WORLD.handle(tok, f"/许诺 {npc.name} 赠物 聚灵草")
    assert res["ok"], res
    res = WORLD.handle(tok, "/诺言")
    assert res["ok"] and "我立之诺" in res["text"] and "聚灵草" in res["text"], res
    # 抵达诺经 /go 真践行
    if char.location != LOC_B:
        dest_cmd, dest_full = "落霞", LOC_B
    else:
        dest_cmd, dest_full = "客栈", LOC_A
    res = WORLD.handle(tok, f"/许诺 {npc.name} 抵达 {dest_cmd}")
    assert res["ok"], res
    res = WORLD.handle(tok, f"/go {dest_cmd}")
    assert res["ok"] and "践诺" in res["text"], res
    mine = [x for x in PromiseRepository.list_all() if x.promiser_id == char.id and x.kind == "arrive"]
    assert mine and mine[0].status == PromiseStatus.KEPT
    # 玩家间应诺流（第二名玩家同场）
    r2 = WORLD.join(f"诺言应诺客{_uniq('')}")
    tok2 = r2["token"]
    char2 = WORLD.get_char(tok2)
    char = WORLD.get_char(tok)
    char2.location = char.location
    CharacterRepository.save(char2)
    res = WORLD.handle(tok, f"/许诺 {char2.name} 不攻")
    assert res["ok"], res
    res = WORLD.handle(tok2, "/应诺")
    assert res["ok"], res
    mine = [x for x in PromiseRepository.list_all() if x.promiser_id == char.id and x.kind == "no_attack"]
    assert mine and mine[0].status == PromiseStatus.ACTIVE
    # 闭关锁门：四指令均不在白名单
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    for cmd in (f"/许诺 {npc.name} 不攻", "/应诺", "/诺言", "/毁诺"):
        res = WORLD.handle(tok, cmd)
        assert res["ok"] is False and "闭关锁门" in (res.get("error") or ""), (cmd, res)
    char.status = CharacterStatus.IDLE
    CharacterRepository.save(char)
    _cleanup(char, char2, npc)
    print("✓ server handle：立诺/面板/迁跃践诺/应诺流 + 闭关锁门")


def test_cli_source_parity():
    src = (Path(__file__).resolve().parent.parent / "cli" / "main.py").read_text(encoding="utf-8")
    for token in ('"/诺言"', '"/许诺"', '"/应诺"', '"/毁诺"', "PromiseEngine", "note_arrival"):
        assert token in src, token
    wsrc = (Path(__file__).resolve().parent.parent / "server" / "world.py").read_text(encoding="utf-8")
    for token in ('"/诺言"', '"/许诺"', '"/应诺"', '"/毁诺"', "on_owner_death"):
        assert token in wsrc, token
    print("✓ CLI/server 源码对齐：四指令 + 钩子齐备")


# ---------------- 评审整改回归（M1/S2/S3） ----------------

def test_one_fact_fulfills_multiple_witnesses_quest():
    # M1：见证人不消费事实——一单委托同时践两条不同见证人的委托诺
    p = _char("多证客")
    w1, w2 = _npc("见证甲"), _npc("见证乙")
    pr1 = PromiseEngine.make_promise(p, w1, "quest")["promise"]
    pr2 = PromiseEngine.make_promise(p, w2, "quest")["promise"]
    now = time.time()
    ring = QuestRing(kind="fetch", desc="寻物", deliver_npc_id=w1.id,
                     deliver_npc_name=w1.name, item_name="聚灵草", need=1)
    p.active_quest = QuestChain(
        publisher_id=w1.id, publisher_name=w1.name, rings=[ring], ring_index=0,
        accepted_at=now, expires_at=now + QUEST_CHAIN_TTL_SECONDS,
        reward_stones=100, reward_merit=QUEST_REWARD_MERIT,
    )
    p.inventory.append("聚灵草")
    CharacterRepository.save(p)
    res = QuestEngine.deliver(p)
    assert res["success"] and res.get("completed"), res
    assert res["message"].count("【践诺】") == 2  # 两条诺同次结算
    assert _get(pr1.id).status == PromiseStatus.KEPT
    assert _get(pr2.id).status == PromiseStatus.KEPT
    p2 = CharacterRepository.get_by_id(p.id)
    assert p2.karma.merit_value == QUEST_REWARD_MERIT + 2 * PROMISE_MERIT_KEPT
    _cleanup(p, w1, w2)
    print("✓ M1：一单委托同时践多位见证人之诺，功德逐诺入账")


def test_one_arrival_fulfills_multiple_witnesses():
    # M1：同一次抵达同时践两条同目标抵达诺，不再误判第二条违约
    p = _char("双证客")
    w1, w2 = _npc("迎客甲"), _npc("迎客乙")
    pr1 = PromiseEngine.make_promise(p, w1, "arrive", "落霞")["promise"]
    pr2 = PromiseEngine.make_promise(p, w2, "arrive", "落霞")["promise"]
    msg = PromiseEngine.note_arrival(p, LOC_B)
    assert msg and msg.count("【践诺】") == 2
    assert _get(pr1.id).status == PromiseStatus.KEPT
    assert _get(pr2.id).status == PromiseStatus.KEPT
    assert CharacterRepository.get_by_id(p.id).karma.merit_value == 2 * PROMISE_MERIT_KEPT
    _cleanup(p, w1, w2)
    print("✓ M1：一次抵达同时践多条同目标抵达诺")


def test_expired_promises_free_slots_on_make():
    # S3：立新诺时先惰性结算，过期旧诺不占上限名额
    p = _char("腾挪客")
    ns = [_npc(f"旧证{i}") for i in range(3)]
    t0 = time.time()
    for n in ns:
        assert PromiseEngine.make_promise(p, n, "quest", now=t0)["success"]
    n4 = _npc("新证人")
    t1 = t0 + 3 * 86400.0 + 10  # 三条旧诺均已过期
    res = PromiseEngine.make_promise(p, n4, "quest", now=t1)
    assert res["success"], res  # 旧诺已被惰性判违约腾位，而非卡上限
    assert len(PromiseEngine._open_of(p.id)) == 1
    _cleanup(p, n4, *ns)
    print("✓ S3：立诺前惰性结算释放名额")


def test_gift_param_normalized_to_full_name():
    # S2：简称立诺时按行囊全名规范化，赠礼模糊命中后核验不落空
    p = _char("简称客")
    npc = _npc("全名翁")
    p.inventory.append("聚灵草")
    CharacterRepository.save(p)
    pr = PromiseEngine.make_promise(p, npc, "gift", "聚灵")["promise"]
    assert pr.param == "聚灵草"
    res = do_gift(p, npc, "聚灵", 0)  # 赠礼侧子串命中「聚灵草」
    assert res["ok"] and "践诺" in res["text"], res
    assert _get(pr.id).status == PromiseStatus.KEPT
    _cleanup(p, npc)
    print("✓ S2：赠物诺面规范为全名，简称赠出亦践诺")
