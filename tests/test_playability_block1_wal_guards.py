"""playability-block1 修复轮3 · M5 WAL 周边三处守卫。

① tools/reset_world.backup_db：wal_checkpoint busy 非 0 时重试后抛错，不静默拷库；
② tools/reset_world.reset：删主库时一并清理 -wal/-shm 兄弟文件；
③ storage.db._connect：WAL 设置失败记 logging 告警再退化返回，不静默吞。
约定：ALLOW_LOCAL_AI=1 AI_REQUIRED=0 NPC_TICK_INTERVAL=0；一律 tmp 隔离，零残留。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")
os.environ.setdefault("USE_CCSWITCH", "0")

import logging
import sqlite3

import pytest


def test_m5_connect_wal_failure_logs_warning(monkeypatch, caplog):
    """③ _connect：PRAGMA 抛错时须有 warning（含异常信息），且仍返回连接。"""
    import storage.db as db_mod

    class _BadConn:
        def execute(self, *args, **kwargs):
            raise RuntimeError("wal boom pb1m5")

    monkeypatch.setattr(db_mod.sqlite3, "connect", lambda *a, **k: _BadConn())
    with caplog.at_level(logging.WARNING, logger="storage.db"):
        conn = db_mod._connect()
    assert conn is not None, "WAL 设置失败应退化返回连接而非抛错/返回 None"
    assert any("wal boom pb1m5" in r.getMessage() for r in caplog.records), \
        f"_connect 失败须记告警含异常信息：{[r.getMessage() for r in caplog.records]}"
    print("✓ M5③ _connect WAL 失败记告警并退化返回")


def test_m5_backup_db_checkpoint_busy_raises(tmp_path, monkeypatch):
    """① backup_db：checkpoint 恒 busy 时重试后抛错，且不产生备份文件。"""
    import tools.reset_world as rw

    db_file = tmp_path / "tiandao.db"
    db_file.write_bytes(b"fake")
    monkeypatch.setattr(rw, "DB_PATH", db_file)
    monkeypatch.setattr(rw, "DATA_DIR", tmp_path)

    class _BusyCursor:
        def fetchone(self):
            return (1, 10, 0)  # busy=1

    class _BusyConn:
        def execute(self, *args, **kwargs):
            return _BusyCursor()

        def close(self):
            pass

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: _BusyConn())
    with pytest.raises(RuntimeError, match="wal_checkpoint"):
        rw.backup_db()
    assert not list(tmp_path.glob("tiandao_backup_*.db")), \
        "checkpoint busy 时不得静默拷库产生备份"
    print("✓ M5① backup_db checkpoint busy 抛错不拷库")


def test_m5_backup_db_checkpoint_ok_copies(tmp_path, monkeypatch):
    """① 对照：checkpoint busy=0 时正常拷贝备份。"""
    import tools.reset_world as rw

    db_file = tmp_path / "tiandao.db"
    db_file.write_bytes(b"fake-db-bytes")
    monkeypatch.setattr(rw, "DB_PATH", db_file)
    monkeypatch.setattr(rw, "DATA_DIR", tmp_path)

    class _OkCursor:
        def fetchone(self):
            return (0, 0, 0)

    class _OkConn:
        def execute(self, *args, **kwargs):
            return _OkCursor()

        def close(self):
            pass

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: _OkConn())
    dest = rw.backup_db()
    assert Path(dest).exists() and Path(dest).read_bytes() == b"fake-db-bytes"
    print("✓ M5① 对照 backup_db checkpoint ok 正常备份")


def test_m5_reset_removes_wal_shm_siblings(tmp_path, monkeypatch):
    """② reset：删主库时 -wal/-shm 兄弟文件一并清理。"""
    import tools.reset_world as rw

    db_file = tmp_path / "tiandao.db"
    db_file.write_bytes(b"main")
    Path(f"{db_file}-wal").write_bytes(b"wal")
    Path(f"{db_file}-shm").write_bytes(b"shm")
    monkeypatch.setattr(rw, "DB_PATH", db_file)
    monkeypatch.setattr(rw, "init_db", lambda: None)
    monkeypatch.setattr(rw, "seed_roster", lambda: {"created": 0, "skipped": 0})

    class _Repo:
        @staticmethod
        def get_by_name(name):
            return None

        @staticmethod
        def list_all_alive():
            return []

    monkeypatch.setattr(rw, "CharacterRepository", _Repo)
    stats = rw.reset()
    assert isinstance(stats, dict)
    assert not Path(f"{db_file}-wal").exists(), "-wal 兄弟文件须一并删除"
    assert not Path(f"{db_file}-shm").exists(), "-shm 兄弟文件须一并删除"
    print("✓ M5② reset 一并清理 -wal/-shm")
