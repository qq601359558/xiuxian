"""
事件账 / 小传 / 记忆检索 / 复仇回访 测试
"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import WorldClock
from core.memory import (
    record_event,
    ensure_bio,
    memory_block_for,
    enrich_facts_with_memory,
    RevengeEngine,
)
from core.combat_fate import CombatFateEngine
from storage.db import EventLedgerRepository, CharacterBioRepository, init_db
from core.models import CharacterStatus


def _char(name, stones=200):
    c = WorldClock.create_new_character(f"m_{name}", name)
    c.spirit_stones = stones
    return c


def test_record_and_retrieve():
    init_db()
    a = _char("记主")
    b = _char("仇家")
    b.location = a.location = "落霞山灵泉(野外)"
    eid = record_event(
        type="KILL", actor=a, target=b,
        summary="张三于落霞山伏杀李四", location=a.location,
    )
    assert eid.startswith("ev_")
    rows = EventLedgerRepository.query_for_memory(a.id, location=a.location, limit=5)
    assert any(r["event_id"] == eid for r in rows)
    rows2 = EventLedgerRepository.query_for_memory(b.id, limit=5)
    assert any(r["event_id"] == eid for r in rows2)
    print("✓ 事件账写入与双向检索")


def test_bio_created():
    c = _char("小传主")
    c.karma.add_sin(150)
    bio = ensure_bio(c)
    assert c.name in bio
    assert CharacterBioRepository.get(c.id)
    print("✓ 角色小传自动生成")


def test_memory_block_budget():
    c = _char("预算")
    for i in range(20):
        record_event(type="FREE", actor=c, summary=f"琐事{i}" * 10, location=c.location)
    block = memory_block_for(c, kind="free_action")
    assert len(block) <= 900  # 允许略超一点截断前
    assert "角色小传" in block
    print(f"✓ 记忆块压预算（len={len(block)}）")


def test_enrich_facts():
    c = _char("富包")
    record_event(type="FREE", actor=c, summary="曾在坊市打听秘境", location=c.location)
    facts = enrich_facts_with_memory(c, kind="free_action")
    prompt = facts.to_prompt_block()
    assert "角色小传" in prompt or "近日账录" in prompt
    print("✓ 事实包含记忆块")


def test_kill_records_and_revenge():
    a = _char("杀手", stones=100)
    d = _char("死者", stones=400)
    a.location = d.location = "黑风绝渊"
    # 多打几次直到 kill 或直接构造
    killed = False
    for _ in range(8):
        d.status = CharacterStatus.IDLE
        d.lifespan.death_timestamp = time.time() + 80 * 86400
        d.spirit_stones = 400
        res = CombatFateEngine.resolve_ambush(a, d, use_ai=True)
        if res.get("target_died"):
            killed = True
            break
    if not killed:
        # 强制落一条 KILL 账以便测复仇
        record_event(type="KILL", actor=a, target=d, summary="测试账：斩杀", location=a.location)
        d.status = CharacterStatus.DEAD
    rows = EventLedgerRepository.query_feud_pairs(a.id, limit=5)
    assert rows, "应有杀戮/仇怨账"

    rv = RevengeEngine.force_callback(a)
    assert rv is not None
    assert rv.get("narrative")
    assert rv.get("event_id")
    print(f"✓ 复仇回访：{rv.get('source')} · {(rv.get('narrative') or '')[:40]}…")


def main():
    test_record_and_retrieve()
    test_bio_created()
    test_memory_block_budget()
    test_enrich_facts()
    test_kill_records_and_revenge()
    print("\n✅ 长期记忆工作流 测试全部通过")


if __name__ == "__main__":
    main()
