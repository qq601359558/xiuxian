"""playability-block1 复测再修 B1-2：tick 持锁再降。

- storage._connect()：WAL + synchronous=NORMAL，commit 不再逐次 fsync；
- core.collusion.try_collude_pair：熔断器非 closed 时不发锁内 AI 点缀调用。
约定：DB 一律 tmp_path 隔离（monkeypatch storage.db.DB_PATH），不碰真实存档。
"""
import os

os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")
os.environ.setdefault("USE_CCSWITCH", "0")
os.environ.setdefault("LLM_API_KEY", "")

import time

import pytest

import config

config.ALLOW_LOCAL_AI = True
config.AI_REQUIRED = False

from core.bounty import KarmaLink
from core.clock import WorldClock
from storage.db import (
    CharacterRepository,
    KarmaLinkRepository,
    WorldStateRepository,
    init_db,
)


@pytest.fixture()
def tmpdb(tmp_path, monkeypatch):
    test_db = tmp_path / "pb1tick.db"
    monkeypatch.setattr("storage.db.DB_PATH", test_db)
    init_db()
    yield test_db


def _npc(name, loc="青云坊市客栈"):
    c = WorldClock.create_new_character(f"npc_{name}", name)
    c.location = loc
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def test_storage_connect_wal_normal(tmpdb):
    from storage.db import _connect

    c = _connect()
    try:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert c.execute("PRAGMA synchronous").fetchone()[0] == 1
    finally:
        c.close()
    # 跨连接可见：写后另一连接可读
    WorldStateRepository.set("pb1tick_probe", {"v": 7})
    c2 = _connect()
    try:
        assert WorldStateRepository.get("pb1tick_probe") == {"v": 7}
    finally:
        c2.close()
    print("✓ B1-2 复测再修：_connect() WAL + synchronous=NORMAL，跨连接可见")


def test_collusion_skips_ai_when_breaker_open(tmpdb, monkeypatch):
    from ai.gateway import breaker, breaker_reset, breaker_state
    from core.collusion import try_collude_pair
    import ai.gateway as gw

    a = _npc("合谋甲")
    b = _npc("合谋乙")
    KarmaLinkRepository.save(KarmaLink(
        a_id=a.id, a_name=a.name, b_id=b.id, b_name=b.name,
        link_type="恩", strength=3, created_at=time.time()))
    try:
        for _ in range(3):
            breaker.record_failure("http_5xx")
        assert breaker_state()["state"] == "open"
        calls = []

        def _boom(*args, **kwargs):
            calls.append(1)
            raise AssertionError("熔断 open 时不得发 AI 调用")

        monkeypatch.setattr(gw, "_chat_json", _boom)
        res = try_collude_pair(a, b)
        assert res is not None, "合谋应回本地句而非 None"
        assert res.get("source") == "rule", res
        assert calls == [], "熔断 open 时 _chat_json 不得被调用"
        assert a.name in res["narrative"] and b.name in res["narrative"], res
        print("✓ B1-2 复测再修：熔断 open 时合谋不发 AI、走本地句")
    finally:
        breaker_reset()


def test_collusion_uses_ai_when_breaker_closed(tmpdb, monkeypatch):
    from ai.gateway import breaker_reset, breaker_state
    from core.collusion import try_collude_pair
    import ai.gateway as gw

    a = _npc("合谋丙")
    b = _npc("合谋丁")
    KarmaLinkRepository.save(KarmaLink(
        a_id=a.id, a_name=a.name, b_id=b.id, b_name=b.name,
        link_type="恩", strength=3, created_at=time.time()))
    try:
        breaker_reset()
        assert breaker_state()["state"] == "closed"
        calls = []

        def _fake(prompt, timeout=2.0, count_failure=False):
            calls.append(prompt)
            return {"narrative": "AI 句：两人相视一笑。"}

        monkeypatch.setattr(gw, "_chat_json", _fake)
        res = try_collude_pair(a, b)
        assert res is not None, res
        assert res.get("source") == "ai", res
        assert res["narrative"] == "AI 句：两人相视一笑。", res
        assert calls, "_chat_json 应被调用"
        print("✓ B1-2 复测再修对照：熔断 closed 时合谋仍走 AI 点缀")
    finally:
        breaker_reset()
