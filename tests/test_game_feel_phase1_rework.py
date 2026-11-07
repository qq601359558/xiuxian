"""game-feel-phase1 评审返工验收（Spec §7.5 返工单 MF-1/MF-2/MF-3 + S-2/文案项）。

每条对应返工单一条：先以原 bug 场景构造，修复前红、修复后绿。
"""
import os
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import SECONDS_PER_GAME_DAY
from core.clock import WorldClock
from core.models import CharacterStatus
from storage.db import (
    CharacterRepository,
    KarmaChainRepository,
    PromiseRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name="试炼者", uid_prefix="rw", location=LOC):
    c = WorldClock.create_new_character(f"{uid_prefix}_{name}_{_tag()}", f"{name}{_tag()}")
    c.location = location
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


def _npc(name="试炼NPC", tier=1, location="万剑仙门峰"):
    c = WorldClock.create_new_character(f"npc_rw_{name}_{_tag()}", f"{name}{_tag()}")
    c.realm.tier = tier
    c.location = location
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id)


# ================= MF-1 入局拼装陈旧覆写 =================

def test_mf1_join_karma_resolution_not_rolled_back():
    """因果链到期 + 诺言到期同一次 join：链兑现落账不得被 join 回存回滚，
    链须为终态，且 ③ 判定式求值须基于兑现后灵石。"""
    from core.goals import add_checked_goal
    from core.karma_chains import KarmaChain, KarmaChainEngine
    from core.promises import Promise, PromiseStatus

    t0 = time.time()
    char = _char("链诺同登")
    char.spirit_stones = 100
    char.karma.merit_value = 0
    char.karma.sin_value = 0
    CharacterRepository.save(char)
    char = CharacterRepository.get_by_id(char.id)

    npc_chain = _npc("链恩人")
    npc_promise = _npc("诺证人")

    # 选一个灵石支的 chain id（branch_for 由 id 哈希定，XOR 支只落一侧）
    chain_id = None
    for i in range(1000):
        cand = KarmaChain(id=f"mf1c{i:04d}")
        if KarmaChainEngine.branch_for(cand) == "stones":
            chain_id = cand.id
            break
    assert chain_id, "应能找到灵石支 chain id"
    chain = KarmaChain(
        id=chain_id,
        chain_key=f"mf1:{char.id}:{npc_chain.id}",
        kind="nuo", polarity=1,
        player_id=char.id, player_name=char.name,
        counterparty_id=npc_chain.id, counterparty_name=npc_chain.name,
        delivery_actor_id=npc_chain.id, delivery_actor_name=npc_chain.name,
        strength=3, status="fermenting",
        origin_summary="践诺余绪",
        created_at=t0, ferment_at=t0 - 10, mature_at=t0 - 10,
        deadline_at=t0 + 7 * SECONDS_PER_GAME_DAY,
    )
    KarmaChainRepository.save(chain)
    expected = KarmaChainEngine.compute_effects(chain, t0)
    stones_gain = int(expected.get("stones_gain") or 0)
    merit_gain = int(expected.get("merit") or 0)
    assert stones_gain > 0 and merit_gain > 0, f"nuo 正向链应含灵石+功德：{expected}"

    # 同一次登录到期的诺言（quest 到期未践 → BROKEN，只落业力不扰灵石/功德断言）
    p = Promise(
        promiser_id=char.id, promiser_name=char.name,
        promisee_id=npc_promise.id, promisee_name=npc_promise.name,
        promisee_is_npc=True, kind="quest", desc="到期旧诺",
        status=PromiseStatus.ACTIVE,
        created_at=t0 - 1000, activated_at=t0 - 1000, deadline=t0 - 10,
    )
    PromiseRepository.save(p)

    # ③ 判定式：门槛在兑现前灵石（100）与兑现后（100+gain）之间——
    # 只有基于兑现后数值求值才会翻 done。
    goal_amount = 100 + stones_gain - 5
    assert 100 < goal_amount <= 100 + stones_gain
    add_checked_goal(
        char, source="origin", title="攒下安身钱", detail="",
        check={"kind": "stones_at_least", "amount": goal_amount},
        deadline_days=10, now=t0)
    CharacterRepository.save(char)

    snap = WORLD.join(char.name, user_id=char.user_id)
    assert snap.get("entry") is not None and not snap.get("lock_fallback")
    kinds = [q["kind"] for q in snap["entry"]["queue"]]
    assert "karma_resolved" in kinds and "promise_settled" in kinds

    after = CharacterRepository.get_by_id(char.id)
    assert after.spirit_stones == 100 + stones_gain, (
        f"链兑现灵石被回滚：期望 {100 + stones_gain}，实际 {after.spirit_stones}")
    assert after.karma.merit_value == merit_gain, (
        f"链兑现功德被回滚：期望 {merit_gain}，实际 {after.karma.merit_value}")
    chain_after = KarmaChainRepository.get(chain.id)
    assert chain_after is not None and chain_after.status == "resolved"
    goal_after = [g for g in after.goals
                  if (g.get("check") or {}).get("kind") == "stones_at_least"]
    assert goal_after and goal_after[0]["status"] == "done", (
        f"③ 求值未基于兑现后灵石：{goal_after}")
    p_after = [x for x in PromiseRepository.list_all() if x.id == p.id][0]
    assert p_after.status.value == "BROKEN"
