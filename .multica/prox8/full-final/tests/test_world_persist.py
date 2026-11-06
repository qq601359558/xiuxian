"""
C2 世界态持久化 + C1 AI 通道健康探测
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, WorldStateRepository


def test_world_state_kv():
    init_db()
    WorldStateRepository.set("t_key", {"a": 1, "b": "二"})
    got = WorldStateRepository.get("t_key")
    assert got == {"a": 1, "b": "二"}
    WorldStateRepository.set("t_key", {"a": 2})
    assert WorldStateRepository.get("t_key")["a"] == 2
    assert WorldStateRepository.get("t_missing", "默认") == "默认"
    WorldStateRepository.delete("t_key")
    assert WorldStateRepository.get("t_key") is None
    print("✓ WorldStateRepository KV")


def test_secret_realm_persists_across_reload():
    init_db()
    import core.secret_realm as sr

    # 清缓存模拟新进程
    sr._loaded = False
    sr._realm_open_ts.clear()
    sr._active_chains.clear()
    WorldStateRepository.delete(sr._REALM_TS_KEY)
    WorldStateRepository.delete(sr._CHAINS_KEY)

    from core.clock import WorldClock
    from storage.db import CharacterRepository

    c = WorldClock.create_new_character("ws_sr", "秘境持久化客")
    now = time.time()
    # 直接写开启时间并 persist
    sr._ensure_loaded()
    rid = next(iter(sr.SECRET_REALMS))
    sr._realm_open_ts[rid] = now - 100
    sr._persist_realm_ts()
    sr._active_chains[c.id] = {
        "id": "abc",
        "realm_id": rid,
        "step": 2,
        "max_steps": 3,
        "danger": 0.3,
        "started_at": now,
        "title": f"秘境·{rid}",
    }
    sr._persist_chains()

    # 模拟重启
    sr._loaded = False
    sr._realm_open_ts.clear()
    sr._active_chains.clear()
    sr._ensure_loaded()
    assert rid in sr._realm_open_ts
    assert abs(sr._realm_open_ts[rid] - (now - 100)) < 1.0
    assert c.id in sr._active_chains
    assert sr._active_chains[c.id]["step"] == 2
    print("✓ 秘境冷却与探索链重启后仍在")


def test_ai_budget_persists():
    init_db()
    import core.npc_proactive as np

    np._budget_loaded = False
    np._ai_budget_used = 0
    np._budget_window_start = 0.0
    WorldStateRepository.delete(np._BUDGET_KEY)

    assert np._consume_ai_budget() is True
    assert np._ai_budget_used == 1

    # 模拟重启
    np._budget_loaded = False
    np._ai_budget_used = 0
    np._budget_window_start = 0.0
    np._ensure_budget_loaded()
    assert np._ai_budget_used >= 1
    print("✓ AI 开口预算重启后仍在")


def test_probe_writes_health():
    init_db()
    from ai.gateway import probe_ai_channel, ai_health_status

    # 无 Key 时应写入 ok=False（或有 Key 则 ok 可能 True，只断言结构）
    health = probe_ai_channel(force=True)
    assert "ok" in health
    assert "checked_at" in health
    assert health.get("mode") in ("OPENAI", "CCSWITCH")
    cached = ai_health_status()
    assert cached.get("checked_at") == health.get("checked_at")
    print(f"✓ AI 探测写入 health ok={health.get('ok')} err={health.get('error','')[:40]}")


if __name__ == "__main__":
    test_world_state_kv()
    test_secret_realm_persists_across_reload()
    test_ai_budget_persists()
    test_probe_writes_health()
    print("\n✅ 世界态持久化与 AI 健康 测试通过")
