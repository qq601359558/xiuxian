"""块一·内容面锁定测试（playability-block1 T2：B1-3/B1-4/B1-5/B1-6/B1-7 服务端）。

约定：ALLOW_LOCAL_AI=1 AI_REQUIRED=0 NPC_TICK_INTERVAL=0 前置（运行口径）；
本文件自建角色一律唯一名前缀 pb1ct_，用后按 user_id/id 清理（零残留）。
AI 强制关闭用 monkeypatch 改 config 运行时开关（不改 .env）。
"""
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")
os.environ.setdefault("USE_CCSWITCH", "0")

import config
from core.clock import WorldClock
from storage.db import (
    DB_PATH,
    CharacterRepository,
    WorldStateRepository,
    init_db,
)

init_db()

FORBIDDEN = ("CC Switch", "USE_CCSWITCH", "LLM_API", ".env", "server.log")
LOC = "青云坊市客栈"
FAR_LOC = "万剑仙门峰"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _cleanup(user_ids=(), char_ids=(), thread_ids=(), tokens=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        for uid in user_ids:
            conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
            conn.execute("DELETE FROM accounts WHERE user_id=?", (uid,))
        for cid in char_ids:
            conn.execute("DELETE FROM characters WHERE id=?", (cid,))
            conn.execute("DELETE FROM fate_threads WHERE player_id=?", (cid,))
            conn.execute("DELETE FROM event_ledger WHERE actor_id=? OR target_id=?", (cid, cid))
            conn.execute("DELETE FROM npc_minds WHERE npc_id=?", (cid,))
            conn.execute("DELETE FROM character_bios WHERE character_id=?", (cid,))
            conn.execute("DELETE FROM npc_agendas WHERE npc_id=?", (cid,))
        for tid in thread_ids:
            conn.execute("DELETE FROM fate_threads WHERE id=?", (tid,))
        for tok in tokens:
            conn.execute("DELETE FROM auth_sessions WHERE token=?", (tok,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _mk(uid_suffix: str, name: str, location: str = LOC):
    tag = _tag()
    uid = f"pb1ct_{uid_suffix}_{tag}"
    c = WorldClock.create_new_character(uid, f"{name}{tag}")
    c.location = location
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id), uid


def _force_ai_off(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "USE_CCSWITCH", False)
    monkeypatch.setattr(config, "ALLOW_LOCAL_AI", False)
    import ai.gateway as gw

    monkeypatch.setattr(gw, "LLM_API_KEY", "")
    monkeypatch.setattr(gw, "USE_CCSWITCH", False)


def _assert_clean(payload, label: str):
    blob = str(payload)
    for bad in FORBIDDEN:
        assert bad not in blob, f"{label} 泄漏运维词 {bad}：{blob[:400]}"


# ================= B1-3：交谈兜底 + 出口无运维词 =================

def test_b13_talk_fallback_no_ops_words_and_personality_differs(monkeypatch):
    _force_ai_off(monkeypatch)
    from core.npc_mind import NpcDialogueEngine
    from storage.db import NpcMindRepository

    player, puid = _mk("p_talk", "谈客")
    npc1, nuid1 = _mk("npc_danbo", "淡泊客")
    npc2, nuid2 = _mk("npc_hao", "豪爽客")
    try:
        NpcMindRepository.upsert(npc1.id, "淡泊避世", {}, {})
        NpcMindRepository.upsert(npc2.id, "豪爽仗义", {}, {})
        r1 = NpcDialogueEngine.talk(
            CharacterRepository.get_by_id(npc1.id), player, "幸会，道友近来可好")
        r2 = NpcDialogueEngine.talk(
            CharacterRepository.get_by_id(npc2.id), player, "幸会，道友近来可好")
        for r in (r1, r2):
            assert r.get("ok") is True, r
            line = (r.get("line") or "").strip()
            assert line and line != "嗯。", r
            _assert_clean(r, "交谈兜底")
        assert r1["line"] != r2["line"], "不同性格兜底回复应有别"
        print("✓ B1-3 交谈：AI 关闭走本地兜底、无运维词、性格有别")
    finally:
        _cleanup(user_ids=[puid, nuid1, nuid2],
                 char_ids=[player.id, npc1.id, npc2.id])


def test_b13_world_exits_no_ops_words(monkeypatch):
    _force_ai_off(monkeypatch)
    from server.world import World

    tag = _tag()
    uid = f"pb1ct_exit_{tag}"
    old_health = None
    try:
        old_health = WorldStateRepository.get("ai_health")
    except Exception:
        old_health = None
    w = World(auto_tick=False)
    r = w.join(f"出口客{tag}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    try:
        r_art = w.handle(tok, "/自创功法 测试玄功")
        _assert_clean(r_art, "/自创功法")
        r_ai = w.handle(tok, "/ai")
        _assert_clean(r_ai, "/ai")
        # /交谈：同场任一 NPC，兜底回复非空且无运维词
        from core.here import list_here

        rows = [x for x in list_here(char) if x.get("is_npc")]
        assert rows, "坊市应有 NPC"
        r_talk = w.handle(tok, f"/交谈 {rows[0]['name']} 道友近来可好")
        _assert_clean(r_talk, "/交谈")
        assert r_talk.get("ok") is True, r_talk
        assert (r_talk.get("text") or "").strip(), r_talk
        print("✓ B1-3 出口：/交谈、/自创功法、/ai 均无运维词")
    finally:
        _cleanup(user_ids=[uid], char_ids=[char.id] if char else [], tokens=[tok])
        try:
            if old_health is None:
                WorldStateRepository.delete("ai_health")
            else:
                WorldStateRepository.set("ai_health", old_health)
        except Exception:
            pass


def test_b13_npc_chat_pool_per_personality():
    from core import npc_chat
    from storage.db import NpcMindRepository

    player, puid = _mk("p_pool", "池客")
    made = []
    try:
        lines_by_pers = {}
        for pers, suffix in (("淡泊避世", "danbo"), ("豪爽仗义", "hao"),
                             ("市侩圆滑", "shik"), ("谨慎多疑", "jin")):
            npc, nuid = _mk(f"npc_{suffix}", f"池{suffix}")
            made.append((npc, nuid))
            NpcMindRepository.upsert(npc.id, pers, {}, {})
            npc = CharacterRepository.get_by_id(npc.id)
            lines = []
            for t in range(3):
                rec = {"willingness": 80, "turns": t,
                       "messages": [{"who": player.name, "text": "道友近来可好，可有消息"}]}
                out = npc_chat.local_hangup_or_reply(npc, player, rec)
                assert out.get("will_continue") is True, out
                lines.append(out["line"])
            assert len(set(lines)) >= 3, f"{pers} 兜底池应 ≥3 条互异回复：{lines}"
            for ln in lines:
                inner = ln.rsplit("「", 1)[-1].rstrip("」")
                assert inner != "嗯。" and len(ln) > 10, f"{pers} 兜底不得只剩「嗯。」：{ln}"
            lines_by_pers[pers] = lines
        assert lines_by_pers["淡泊避世"] != lines_by_pers["豪爽仗义"]
        print("✓ B1-3 兜底池：每性格 ≥3 条有内容回复、性格有别")
    finally:
        _cleanup(user_ids=[puid] + [u for _, u in made],
                 char_ids=[player.id] + [c.id for c, _ in made])


# ================= B1-5：/修炼 =================

def test_b15_xiulian_dispatch_gate_and_catalog():
    from core.command_catalog import format_help, search_commands, catalog_json
    from server.world import World

    by_cmd = {e["cmd"]: e for e in catalog_json()["commands"]}
    assert "/修炼" in by_cmd, "catalog 须含 /修炼 条目"
    assert "闭关" in by_cmd["/修炼"]["desc"] and "同源" in by_cmd["/修炼"]["desc"]
    assert "/修炼" in by_cmd["/闭关"]["desc"], "/闭关 条目须互指 /修炼"
    assert "/修炼" in format_help("修炼")
    assert any(h["cmd"] == "/修炼" for h in search_commands("修炼", limit=40))

    tag = _tag()
    uid = f"pb1ct_xiu_{tag}"
    w = World(auto_tick=False)
    r = w.join(f"修炼客{tag}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    try:
        char.born_at = time.time() - 80 * 3600.0
        char.spirit_stones = max(char.spirit_stones, 500)
        CharacterRepository.save(char)
        # /炼体 修炼 子命令不被 /修炼 精确分发吞掉
        r_body = w.handle(tok, "/炼体 修炼")
        assert "未知指令" not in str(r_body), r_body
        # /修炼 分发可用：回闭关反馈而非未知指令
        r1 = w.handle(tok, "/修炼 1")
        assert "未知指令" not in str(r1), r1
        assert r1.get("ok") is True, r1
        # 门禁口径：闭关中再发 /修炼 与 /闭关 同行为（锁门拦截）
        r2 = w.handle(tok, "/修炼")
        r3 = w.handle(tok, "/闭关")
        for rr in (r2, r3):
            assert rr.get("ok") is False, rr
            assert "闭关锁门" in (rr.get("error") or ""), rr
        print("✓ B1-5 /修炼：分发/门禁与 /闭关 同口径、catalog 互指、子命令无冲突")
    finally:
        try:
            w.handle(tok, "/出关")
        except Exception:
            pass
        _cleanup(user_ids=[uid], char_ids=[char.id] if char else [], tokens=[tok])


# ================= B1-6：行情去原码 =================

_RAW_ID = re.compile(r"(mat|equip|pill)_[a-z0-9_]+")


def _assert_rows_clean(rows, label: str):
    names = [g["name"] for g in rows]
    assert names, f"{label} 行集为空"
    assert len(names) == len(set(names)), f"{label} 显示名重复：{names[:10]}"
    for n in names:
        assert not _RAW_ID.search(n), f"{label} 显示名含原码：{n}"


def test_b16_market_rows_no_raw_ids_no_dupes():
    from core.chat_actions import _shop_stock_preview
    from core.market import MarketEngine
    from core.trade import NpcShopEngine

    _assert_rows_clean(MarketEngine.catalog(), "catalog()")
    _assert_rows_clean(MarketEngine.catalog(LOC), "catalog(loc)")
    data = MarketEngine.trade_board_data(LOC)
    for region in data["regions"]:
        _assert_rows_clean(region["rows"], f"trade_board_data[{region['name']}]")
    board = MarketEngine.trade_board(LOC)
    assert not _RAW_ID.search(board), "trade_board 文本含原码"

    player, puid = _mk("p_mkt", "行情客")
    npc, nuid = _mk("npc_shop", "柜客")
    try:
        npc.sect = "四海散修商会"
        npc.sect_rank = "掌柜"
        CharacterRepository.save(npc)
        res = NpcShopEngine.catalog(player, npc.name)
        assert res.get("success") is True, res
        _assert_rows_clean(res["goods"], "NPC专柜")
        assert not _RAW_ID.search(res["message"]), "NPC专柜文本含原码"
        preview = _shop_stock_preview(CharacterRepository.get_by_id(npc.id))
        assert preview and len(preview) == len(set(preview)), preview
        for n in preview:
            assert not _RAW_ID.search(n), f"专柜预览含原码：{n}"
        print("✓ B1-6 行情：行集无原码、无重复显示名（商会/行情/NPC专柜/预览）")
    finally:
        _cleanup(user_ids=[puid, nuid], char_ids=[player.id, npc.id])


def test_b16_world_market_and_hangqing_text():
    from server.world import World

    tag = _tag()
    uid = f"pb1ct_hq_{tag}"
    w = World(auto_tick=False)
    r = w.join(f"行情行客{tag}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    try:
        r_hq = w.handle(tok, "/行情")
        assert r_hq.get("ok") is True, r_hq
        assert not _RAW_ID.search(r_hq.get("text") or ""), "/行情 文本含原码"
        for region in (r_hq.get("prices") or {}).get("regions") or []:
            _assert_rows_clean(region["rows"], "/行情 prices")
        r_mk = w.handle(tok, "/坊市")
        assert r_mk.get("ok") is True, r_mk
        assert not _RAW_ID.search(r_mk.get("text") or ""), "/坊市 文本含原码"
        print("✓ B1-6 /行情 与 /坊市（_market 同源）：文本无原码、行集无重复")
    finally:
        _cleanup(user_ids=[uid], char_ids=[char.id] if char else [], tokens=[tok])


# ================= B1-4：fate current_target + briefing 文案 =================

def _mk_thread(player, npc_id: str):
    from core.fate_thread import FateThread
    from storage.db import FateThreadRepository

    tid = f"ft_pb1ct_{_tag()}"
    thread = FateThread(
        id=tid, player_id=player.id, user_id=player.user_id, status="active",
        seed_source="origin", title="出身牵命",
        final_proposition={"text": "立身", "status": "active"},
        chapters=[{
            "idx": 0, "group": "setup", "kind": "visit", "tier": "short",
            "title": "去见那个人", "goal_text": "前往其所在之地",
            "status": "active", "goal_id": "",
            "check": {"kind": "visit_location", "ref": LOC, "npc_id": npc_id},
        }],
        current_chapter=0, created_at=time.time(),
    )
    FateThreadRepository.save(thread)
    return tid


def test_b14_current_target_same_and_far_and_briefing():
    from core.briefing import build_entry
    from core.fate_thread import FateThreadEngine

    player, puid = _mk("p_fate", "命途客", location=LOC)
    npc, nuid = _mk("npc_fate", "引路客", location=LOC)
    tid = _mk_thread(player, npc.id)
    try:
        sd = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        assert sd is not None
        assert sd["chapters"][0].get("check", {}).get("kind") == "visit_location"
        assert sd["chapters"][0]["check"].get("npc_id") == npc.id
        ct = sd.get("current_target")
        assert ct and ct["npc_id"] == npc.id and ct["npc_name"] == npc.name, sd
        assert ct["npc_location"] == LOC and ct["same_location"] is True, ct
        entry = build_entry(CharacterRepository.get_by_id(player.id),
                            since=0, allow_proactive=False)
        fate_text = entry["lines"]["fate"]
        assert f"{npc.name} 正在此处（{LOC}），可直接上前交谈" in fate_text, fate_text

        # NPC 迁徙后现查：地点与 same_location 随之变化（不吃快照）
        npc2 = CharacterRepository.get_by_id(npc.id)
        npc2.location = FAR_LOC
        CharacterRepository.save(npc2)
        sd2 = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        ct2 = sd2.get("current_target")
        assert ct2 and ct2["npc_location"] == FAR_LOC and ct2["same_location"] is False, ct2
        entry2 = build_entry(CharacterRepository.get_by_id(player.id),
                             since=0, allow_proactive=False)
        assert f"{npc.name} 在{FAR_LOC}" in entry2["lines"]["fate"], entry2["lines"]["fate"]
        print("✓ B1-4 fate：current_target 现查（同场/异场）、briefing 文案随之")
    finally:
        _cleanup(user_ids=[puid, nuid], char_ids=[player.id, npc.id], thread_ids=[tid])


def test_b14_current_target_null_without_visit_chapter():
    from core.fate_thread import FateThread, FateThreadEngine
    from storage.db import FateThreadRepository

    player, puid = _mk("p_fate2", "无目标客", location=LOC)
    tid = f"ft_pb1ct_{_tag()}"
    try:
        FateThreadRepository.save(FateThread(
            id=tid, player_id=player.id, user_id=player.user_id, status="active",
            seed_source="origin", title="出身牵命",
            final_proposition={"text": "立身", "status": "active"},
            chapters=[{
                "idx": 0, "group": "setup", "kind": "treasure", "tier": "short",
                "title": "寻资", "goal_text": "寻一份立身之资",
                "status": "active", "goal_id": "",
                "check": {"kind": "stones_at_least", "amount": 200},
            }],
            current_chapter=0, created_at=time.time()))
        sd = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        assert sd is not None and sd.get("current_target") is None, sd
        print("✓ B1-4 fate：无 visit 类章时 current_target 为 null")
    finally:
        _cleanup(user_ids=[puid], char_ids=[player.id], thread_ids=[tid])


# ================= B1-7：briefing relations 过滤 origin =================

def test_b17_briefing_relations_filters_origin():
    from core.briefing import build_entry
    from core.npc_mind import shift_attitude
    from core.relations import relations_recent_and_marks

    player, puid = _mk("p_rel", "留痕客")
    npc_o, nuid_o = _mk("npc_org", "出身客")
    npc_r, nuid_r = _mk("npc_real", "交谈客")
    try:
        shift_attitude(CharacterRepository.get_by_id(npc_o.id), player.id, 20, reason="origin")
        shift_attitude(CharacterRepository.get_by_id(npc_r.id), player.id, 20, reason="交谈")
        # 数据层不动：relations_recent 仍含 origin 项
        recent, _marks = relations_recent_and_marks(player.id, recent_limit=30, pool=30)
        assert any(x.get("reason") == "origin" for x in recent), recent
        # briefing 层过滤：origin 不出现、真实变化仍出现
        entry = build_entry(CharacterRepository.get_by_id(player.id),
                            since=0, allow_proactive=False)
        rels = entry["lines"]["relations"]
        assert rels, "真实变化项应仍出现在 briefing relations"
        assert all(x.get("reason") != "origin" for x in rels), rels
        assert any(x.get("npc_id") == npc_r.id for x in rels), rels
        print("✓ B1-7 briefing：origin 留痕已过滤、真实变化仍在、数据层未动")
    finally:
        _cleanup(user_ids=[puid, nuid_o, nuid_r],
                 char_ids=[player.id, npc_o.id, npc_r.id])
