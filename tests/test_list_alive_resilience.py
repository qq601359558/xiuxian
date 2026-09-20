"""list_all_alive / get_by_* 不应因单行坏数据整段崩溃。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, DB_PATH
from core.models import CharacterStatus
from core.clock import WorldClock


def _delete_char_rows(*user_ids: str) -> None:
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    try:
        for uid in user_ids:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()


def test_list_all_alive_skips_invalid_status_row():
    init_db()
    good = WorldClock.create_new_character("t_ok_row", "完好道友")
    CharacterRepository.save(good)

    # 手工写入未知 status（模拟旧枚举/脏数据）
    import sqlite3
    import json
    import time

    bad_payload = good.model_dump()
    bad_payload["id"] = "badstat1"
    bad_payload["user_id"] = "t_bad_row"
    bad_payload["name"] = "脏数据修士"
    bad_payload["status"] = "NOT_A_REAL_STATUS"
    raw = json.dumps(bad_payload, ensure_ascii=False)
    now = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO characters (id, user_id, name, status, data_json, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("badstat1", "t_bad_row", "脏数据修士", "NOT_A_REAL_STATUS", raw, now, now),
    )
    conn.commit()
    conn.close()

    try:
        alive = CharacterRepository.list_all_alive()
        names = {c.name for c in alive}
        assert "完好道友" in names
        assert "脏数据修士" not in names

        assert CharacterRepository.get_by_id("badstat1") is None
        assert CharacterRepository.get_by_name("脏数据修士") is None
        assert CharacterRepository.get_by_user_id("t_bad_row") is None
        ok = CharacterRepository.get_by_id(good.id)
        assert ok is not None and ok.status in list(CharacterStatus)
        print("✓ list_all_alive 跳过坏数据行")
    finally:
        # 测试数据不得残留在正式库（非法 status 会在启动时刷 warning）
        _delete_char_rows("t_bad_row", "t_ok_row")


if __name__ == "__main__":
    test_list_all_alive_skips_invalid_status_row()
    print("\n✅ list_alive_resilience 测试通过")
