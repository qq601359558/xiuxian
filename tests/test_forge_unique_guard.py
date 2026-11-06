"""天工造化去重守卫：组合名与无名兜底序号全被占位时，forge 仍须产出不撞名的新名。

缺陷背景：_local_name 的随机组合 40 次全撞后，兜底名 无名{kind}{10~99}
不查排除集就返回；该序号空间只有 90 个，历次落库后被占满即必然撞名，
且 Repository.save 的 ON CONFLICT DO NOTHING 会把撞名静默吞掉。
本测试把某 kind 的全部组合名 + 无名 10~99 全部预落库占位，迫使 forge
走兜底路径，断言其产出仍不在排除集内且真实落库。夹具零残留。
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["USE_CCSWITCH"] = "0"

import config
import ai.gateway as gw

config.LLM_API_KEY = str()
config.USE_CCSWITCH = False
gw.LLM_API_KEY = str()
gw.USE_CCSWITCH = False

from core import forge as forge_mod
from core.forge import forge, exclusion_names
from storage.db import GeneratedNameRepository, init_db


def _combo_names(kind: str):
    if kind == "pill":
        a, b, c = forge_mod._PILL_A, forge_mod._PILL_B, forge_mod._PILL_C
    elif kind == "equip":
        a, b, c = forge_mod._EQ_A, forge_mod._EQ_B, forge_mod._EQ_C
    else:
        a, b, c = forge_mod._MON_A, forge_mod._MON_B, forge_mod._MON_C
    return {x + y + z for x in a for y in b for z in c}


def _existing_names(names):
    conn = sqlite3.connect(config.DB_PATH)
    try:
        marks = ",".join("?" for _ in names)
        rows = conn.execute(
            f"SELECT name FROM generated_names WHERE name IN ({marks})",
            tuple(names),
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def _insert_placeholders(names, kind):
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.executemany(
            "INSERT INTO generated_names (name, kind, data_json, created_at) "
            "VALUES (?, ?, ?, 0) ON CONFLICT(name) DO NOTHING",
            [
                (n, kind, json.dumps({"kind": kind, "name": n}, ensure_ascii=False))
                for n in names
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _delete_names(names):
    if not names:
        return
    conn = sqlite3.connect(config.DB_PATH)
    try:
        marks = ",".join("?" for _ in names)
        conn.execute(
            f"DELETE FROM generated_names WHERE name IN ({marks})", tuple(names)
        )
        conn.commit()
    finally:
        conn.close()


def _assert_forge_skips_occupied(kind: str):
    init_db()
    universe = _combo_names(kind) | {f"无名{kind}{i}" for i in range(10, 100)}
    pre_existing = _existing_names(universe)
    inserted = sorted(universe - pre_existing)
    _insert_placeholders(inserted, kind)
    forged_name = None
    try:
        banned_before = exclusion_names()
        assert universe <= banned_before  # 占位确实进了排除集，兜底路径被迫触发
        r = forge(kind)
        assert r["success"], r
        forged_name = r["item"]["name"]
        assert forged_name not in banned_before, (
            f"{kind} 兜底产出撞名：{forged_name} 已在排除集内"
        )
        assert GeneratedNameRepository.get(forged_name) is not None
        assert forged_name in exclusion_names()
    finally:
        cleanup = list(inserted)
        if forged_name and forged_name not in pre_existing and forged_name not in inserted:
            cleanup.append(forged_name)
            config.ITEM_CATALOG.pop(forged_name, None)
        _delete_names(cleanup)


def test_forge_fallback_skips_occupied_pill_names():
    _assert_forge_skips_occupied("pill")


def test_forge_fallback_skips_occupied_equip_names():
    _assert_forge_skips_occupied("equip")


def test_forge_fallback_skips_occupied_monster_names():
    _assert_forge_skips_occupied("monster")
